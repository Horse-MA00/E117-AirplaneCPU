// Read-only analyst audit projection. Raw provider text is fetched only on disclosure.
const safeId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);
const node = (tag, text, className) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
};
export const analysisUnavailable = round => round?.analysis_status === 'unavailable' || round?.analysis_source === 'analysis_unavailable';
export function analysisLabel(round) {
  if (analysisUnavailable(round)) return 'Analysis unavailable';
  const attempts = round?.analysis_attempts || [];
  const retries = Math.max(0, attempts.filter(a => a.provider_call !== false).length - 1);
  return retries ? `Available after ${retries} ${retries === 1 ? 'retry' : 'retries'}` : 'Analysis available';
}
async function read(path) {
  const response = await fetch(path);
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`Unreadable analyst audit (${response.status}).`); }
  if (!response.ok) throw new Error(data.error || `Analyst audit unavailable (${response.status}).`);
  return data;
}

export function analysisDiagnostics(host) {
  let generation = 0, signature = '';
  function clear() { generation++; signature = ''; host.replaceChildren(); host.hidden = true; }
  function update(run, {round: selectedRound = null} = {}) {
    if (!safeId(run?.run_id) || (run.config?.mode !== 'live' && !(run.rounds || []).some(r => r.analysis_attempts?.length))) { clear(); return; }
    const stamp = JSON.stringify([run.run_id, run.status, selectedRound, run.rounds?.map(r => [r.round, r.analysis_status, r.analysis_attempts, r.analysis_error]), run.counts?.analyst_calls, run.counts?.failures]);
    if (stamp === signature) return;
    signature = stamp;
    const token = ++generation, runId = run.run_id;
    const endpoint = `/api/adaptive-pricing/runs/${encodeURIComponent(runId)}/analysis-attempts`;
    const rounds = run.rounds || [];
    const current = () => token === generation;
    host.hidden = false;
    host.replaceChildren(node('h3', 'Analyst checks'));
    const notice = node('p', undefined, 'analysis-notice');
    notice.setAttribute('role', 'status');
    const list = node('div', undefined, 'analysis-attempt-list');
    host.append(notice, list);
    const availableRounds = selectedRound === null ? rounds : rounds.filter(r => r.round === selectedRound);
    const unavailable = availableRounds.filter(analysisUnavailable);
    notice.textContent = unavailable.length
      ? `${unavailable.length} ${unavailable.length === 1 ? 'round has' : 'rounds have'} no usable analysis. Valid customer decisions remain saved; Thompson continues without those analyst suggestions.`
      : run.status === 'failed' ? 'This saved experiment stopped. Inspect its original analyst attempts below; viewing them does not resume it.'
      : 'Each analysis allows at most 3 attempts within the total call budget. Viewing saved responses makes no model calls.';

    function render(attempts) {
      if (!current()) return;
      const grouped = new Map();
      for (const attempt of attempts) {
        if (!Number.isInteger(attempt.round) || (selectedRound !== null && attempt.round !== selectedRound)) continue;
        if (!grouped.has(attempt.round)) grouped.set(attempt.round, []);
        grouped.get(attempt.round).push(attempt);
      }
      for (const round of availableRounds) if (analysisUnavailable(round) && !grouped.has(round.round)) grouped.set(round.round, []);
      list.replaceChildren();
      if (!grouped.size) { list.append(node('p', 'No analyst attempts are saved for this selection.', 'hint')); return; }
      for (const [number, items] of [...grouped].sort((a,b) => a[0]-b[0])) {
        items.sort((a,b) => a.attempt-b.attempt);
        const saved = rounds.find(r => r.round === number);
        const last = items.at(-1);
        const label = saved?.analysis_status ? analysisLabel(saved)
          : last?.status === 'passed' ? (items.length > 1 ? `Available after ${items.length-1} ${items.length === 2 ? 'retry' : 'retries'}` : 'Analysis available')
          : last?.status === 'failed' ? (run.status === 'failed' ? 'Analysis failed · experiment stopped' : 'Analysis pending or unavailable')
          : 'Analysis pending';
        const details = node('details', undefined, 'analysis-round');
        details.dataset.analysisRound = String(number);
        details.append(node('summary', `Round ${number} · ${label}`));
        const failures = items.filter(item => item.status === 'failed');
        for (const item of failures) details.append(node('p', `Attempt ${item.attempt} · ${item.failure_kind || item.error_type || 'Error'}: ${item.error || 'Provider response could not be used.'}`, 'analysis-error'));
        if (!failures.length && saved?.analysis_error) details.append(node('p', saved.analysis_error, 'analysis-error'));
        if (analysisUnavailable(saved)) details.append(node('p', 'No analyst direction was used. Customer choices still feed Thompson Sampling.', 'hint'));
        const raw = node('details', undefined, 'analysis-raw');
        raw.append(node('summary', 'View original responses'));
        const content = node('div');
        raw.append(content); details.append(raw); list.append(details);
        let loaded = false, loading = false;
        async function loadRaw() {
          if (loaded || loading || !current()) return;
          loading = true; content.replaceChildren(node('p', 'Loading saved responses…', 'hint'));
          try {
            const result = await read(`${endpoint}?round=${number}`);
            if (!current()) return;
            content.replaceChildren(node('p', 'Original provider output, with credentials redacted. Rejected text is retained for inspection and is not a validated analysis.', 'hint'));
            for (const item of result.attempts || []) {
              const article = node('article', undefined, 'analysis-response');
              article.append(node('strong', `Attempt ${item.attempt} · ${item.status || 'recorded'}`));
              if (item.error) article.append(node('p', item.error, 'analysis-error'));
              if (typeof item.raw_response_text === 'string' && item.raw_response_text.length) article.append(node('pre', item.raw_response_text));
              else article.append(node('p', item.provider_call === false ? 'No new provider response was saved for this attempt.' : 'No provider response was received for this attempt.', 'hint'));
              content.append(article);
            }
            if (!result.attempts?.length) content.append(node('p', 'No response records are saved for this round.', 'hint'));
            loaded = true;
          } catch (error) {
            if (!current()) return;
            content.replaceChildren(node('p', error.message, 'analysis-error'));
            const retry = node('button', 'Retry loading responses', 'text-button');
            retry.type = 'button'; retry.addEventListener('click', loadRaw); content.append(retry);
          } finally { loading = false; }
        }
        raw.addEventListener('toggle', () => { if (raw.open) loadRaw(); });
      }
    }
    const local = rounds.flatMap(r => (r.analysis_attempts || []).map(a => ({...a, round:r.round})));
    render(local);
    async function loadMetadata() {
      try {
        const result = await read(endpoint);
        if (current()) render(result.attempts || []);
      } catch (error) {
        if (!current()) return;
        list.append(node('p', error.message, 'analysis-error'));
        const retry = node('button', 'Retry loading analyst checks', 'text-button');
        retry.type = 'button'; retry.addEventListener('click', () => { retry.disabled = true; loadMetadata(); }); list.append(retry);
      }
    }
    loadMetadata();
  }
  return {update, clear};
}
