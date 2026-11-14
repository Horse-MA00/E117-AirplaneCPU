import { analysisDiagnostics, analysisUnavailable, analysisLabel } from './analysis-diagnostics.js';
// A read-only view of saved price-round feedback. Viewing a run never starts calls.
const $ = id => document.getElementById(id);
const analystDiagnostics = analysisDiagnostics($('feedback-analysis-diagnostics'));
const safeId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);
const money = value => value !== null && value !== undefined && Number.isFinite(Number(value))
  ? `HK$${Number(value).toLocaleString('en-HK', { maximumFractionDigits: 2 })}` : '—';
const roundNumber = (round, index) => round.round ?? index + 1;
let selectedRun = null;
let requestSequence = 0;

function node(tag, content, className) {
  const result = document.createElement(tag);
  if (content !== undefined) result.textContent = content;
  if (className) result.className = className;
  return result;
}
async function get(path) {
  const response = await fetch(path);
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`Unreadable saved feedback (${response.status}).`); }
  if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : `Unable to load saved feedback (${response.status}).`);
  return data;
}
function showError(error) {
  $('feedback-error').hidden = !error;
  $('feedback-error').textContent = error?.message || '';
}
function setBusy(busy) {
  $('view-customers').setAttribute('aria-busy', String(busy));
  $('feedback-refresh').disabled = busy;
  $('feedback-run').disabled = busy || !$('feedback-run').value;
  $('feedback-round').disabled = busy || !selectedRun?.rounds?.length;
}
function empty(message) {
  $('feedback-content').hidden = true;
  $('feedback-empty').hidden = false;
  $('feedback-empty-message').textContent = message;
  $('feedback-round').replaceChildren(new Option('No completed rounds', ''));
  $('feedback-round').disabled = true;
}
function rememberSelection() {
  if (location.hash !== '#customers' || !safeId(selectedRun?.run_id)) return;
  const url = new URL(location.href);
  url.searchParams.set('run', selectedRun.run_id);
  const round = $('feedback-round').value;
  if (round) url.searchParams.set('round', round);
  else url.searchParams.delete('round');
  history.replaceState(null, '', url);
}
function renderRound() {
  const rounds = selectedRun?.rounds || [];
  const index = rounds.findIndex((round, i) => String(roundNumber(round, i)) === $('feedback-round').value);
  const round = rounds[index];
  if (!round) return;
  $('feedback-empty').hidden = true;
  $('feedback-content').hidden = false;
  const analysis = round.analysis || {};
  analystDiagnostics.update(selectedRun,{round:selectedRun.status==='failed'?null:roundNumber(round,index)});
  $('feedback-summary').textContent = analysisUnavailable(round) ? `Analysis unavailable. ${round.analysis_error || 'The analyst could not provide a usable response.'}` : typeof analysis === 'string' ? analysis : analysis.summary || analysis.interpretation || 'No written summary was saved for this round. Recorded member decisions are shown below.';
  $('feedback-source').textContent = analysisUnavailable(round) ? 'Valid customer choices remain available below. Thompson continues without an analyst direction for this round.'
    : round.analysis_attempts?.length>1 ? `${analysisLabel(round)}. Earlier rejected responses remain in Analyst checks.`
    : round.reused_analysis
    ? 'Reused summary from an earlier identical price; this is not a new analysis call.'
    : round.analysis_source === 'provider_live' ? 'Saved LLM summary of this round’s recorded decisions.'
    : round.analysis_source === 'synthetic_analysis' ? 'Saved summary of offline simulated customer choices.'
    : 'Saved analysis; its provenance is included in the experiment export.';
  const scope = selectedRun.scope || {};
  const route = scope.origin && scope.destination ? `${scope.origin} → ${scope.destination}` : selectedRun.config?.flight_id || scope.flight_id;
  const day = scope.as_of_day ?? selectedRun.config?.forecast_day;
  const scenario = selectedRun.scenario || scope.scenario;
  const scenarioText = scenario ? `${scenario.label || 'Low-fare stress test'}: assumed normal fare ${money(scenario.normal_base_fare)}, ticket budgets ${Number(scenario.budget_multiplier)*100}% of standard; source NHPP quota ${scenario.source_scope?.releasable_seats ?? '—'} seats held fixed. Hypothetical inputs, not a new flight forecast.` : null;
  $('feedback-context').textContent = [selectedRun.config?.name, route, scope.departure_date || scope.departure_at?.slice(0, 10), day !== undefined ? `D${day}` : null, `Round ${roundNumber(round, index)}`, `Member base fare ${money(round.price)}`, scenarioText].filter(Boolean).join(' · ');
  const hypothesis = round.hypothesis_test;
  $('feedback-hypothesis').hidden = !hypothesis;
  if (hypothesis) {
    const label = { supported: 'Above initial revenue', not_supported: 'Below initial revenue' }[hypothesis.status] || String(hypothesis.status || 'not_tested').replaceAll('_', ' ');
    const origin = typeof hypothesis.source_round === 'number' && Number.isFinite(hypothesis.source_round) ? `From round ${hypothesis.source_round}: ` : '';
    $('feedback-hypothesis').textContent = `${origin}${String(hypothesis.direction || 'none').replaceAll('_', ' ')} · ${label}. ${hypothesis.summary || ''}`;
  }
  const decisions = Array.isArray(round.decisions) ? round.decisions : [];
  $('feedback-list').replaceChildren(...decisions.map(item => {
    const person = item.person || item.observation?.person || {};
    const decision = item.decision || item;
    const card = node('article', undefined, 'member-feedback-card');
    card.append(node('h2', person.segment_label || person.segment || item.segment || 'Simulated member'));
    card.append(node('p', String(decision.action || 'Decision recorded').replaceAll('_', ' '), 'feedback-decision'));
    card.append(node('p', decision.reason || 'No written reason recorded.'));
    const source = item.forced ? 'Environment-forced action' : item.cache_hit ? 'Cached model response' : item.source === 'provider_live' ? 'New LLM response' : String(item.source || 'Saved decision').replaceAll('_', ' ');
    card.append(node('small', [person.customer_id, source, item.settlement?.status].filter(Boolean).join(' · ')));
    return card;
  }));
  $('feedback-note').textContent = `${decisions.length ? `${decisions.length} recorded decisions. ` : 'Individual decisions were not saved in this report. '}These are simulated member choices, not observed customer purchases. Reasons are not additional independent purchase observations.`;
  $('feedback-pricing-link').href = `/adaptive-pricing?run=${encodeURIComponent(selectedRun.run_id)}`;
  $('feedback-export').href = `/api/adaptive-pricing/runs/${encodeURIComponent(selectedRun.run_id)}/export`;
  rememberSelection();
}
function renderRun(run, preferredRound) {
  if(run.version!=='member-thompson-v5-marketing'||run.config?.profile!=='flexible_deal_seekers')throw new Error('This experiment is no longer available. Choose a current Thompson Sampling experiment.');
  selectedRun = run;
  analystDiagnostics.update(run, {round:run.status==='failed'?null:Number(preferredRound)||null});
  const rounds = Array.isArray(run.rounds) ? run.rounds : [];
  $('feedback-status').textContent = `${run.config?.mode === 'live' ? 'Live LLM' : 'Offline simulated customers'} · ${String(run.status || 'saved').replaceAll('_', ' ')} · ${rounds.length} saved price rounds. Viewing feedback makes no new model calls.`;
  if (!rounds.length) {
    empty('This experiment has no completed price rounds yet. Refresh after a round is saved.');
    rememberSelection();
    return;
  }
  $('feedback-round').replaceChildren(...rounds.map((round, i) => new Option(`Round ${roundNumber(round, i)} · ${money(round.price)}`, String(roundNumber(round, i)))));
  const preferred = rounds.findIndex((round, i) => String(roundNumber(round, i)) === String(preferredRound));
  $('feedback-round').value = String(roundNumber(rounds[preferred >= 0 ? preferred : rounds.length - 1], preferred >= 0 ? preferred : rounds.length - 1));
  renderRound();
}
async function loadRun(id, preferredRound) {
  if (!safeId(id)) return;
  const sequence = ++requestSequence;
  analystDiagnostics.clear();
  showError();
  setBusy(true);
  $('feedback-content').hidden = true;
  $('feedback-empty').hidden = true;
  $('feedback-status').textContent = 'Loading saved member feedback…';
  try {
    const run = await get(`/api/adaptive-pricing/runs/${id}`);
    if (sequence !== requestSequence) return;
    renderRun(run, preferredRound);
  } catch (error) {
    if (sequence !== requestSequence) return;
    selectedRun = null;
    empty('The selected experiment could not be loaded. Choose another saved run or refresh.');
    $('feedback-status').textContent = 'Feedback unavailable.';
    showError(error);
  } finally { if (sequence === requestSequence) setBusy(false); }
}
async function loadSaved() {
  analystDiagnostics.clear();
  const sequence = ++requestSequence;
  const params = new URL(location.href).searchParams;
  const requested = params.get('run');
  const preferred = safeId(requested) ? requested : selectedRun?.run_id;
  const preferredRound = params.get('round') || $('feedback-round').value;
  showError();
  setBusy(true);
  $('feedback-status').textContent = 'Loading saved experiments…';
  try {
    const data = await get('/api/adaptive-pricing/runs');
    if (sequence !== requestSequence) return;
    const runs = (data.runs || []).filter(run => safeId(run.run_id));
    $('feedback-run').replaceChildren(...runs.map(run => new Option(`${run.config?.name ? `${run.config.name} · ` : ''}${run.config?.flight_id || run.scope?.flight_id || run.run_id} · ${run.config?.mode === 'live' ? 'Live LLM' : 'Offline customers'} · ${String(run.status || 'saved').replaceAll('_', ' ')} · ${run.run_id.slice(-8)}`, run.run_id)));
    if (preferred && !runs.some(run => run.run_id === preferred)) $('feedback-run').prepend(new Option(`Selected experiment · ${preferred}`, preferred));
    const id = preferred || runs[0]?.run_id;
    if (!id) {
      selectedRun = null;
      $('feedback-run').append(new Option('No saved experiments', ''));
      $('feedback-status').textContent = 'No saved price experiments.';
      empty('Run a price experiment to save member feedback, then return here to review it.');
      return;
    }
    $('feedback-run').value = id;
    await loadRun(id, preferredRound);
  } catch (error) {
    if (sequence !== requestSequence) return;
    selectedRun = null;
    empty('Saved experiments could not be loaded. Use Refresh feedback to try again.');
    $('feedback-status').textContent = 'Feedback unavailable.';
    showError(error);
  } finally { if (sequence === requestSequence) setBusy(false); }
}
$('feedback-run').addEventListener('change', () => loadRun($('feedback-run').value));
$('feedback-round').addEventListener('change', renderRound);
$('feedback-refresh').addEventListener('click', loadSaved);
document.addEventListener('uoption:view', event => { if (event.detail?.name === 'customers') loadSaved(); });
if (location.hash === '#customers') loadSaved();
