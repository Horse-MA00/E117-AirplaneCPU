"""Read-only UI projections; complete experiment reports remain audit evidence.

Keep these projections independent of the pricing engine. They select saved
values without recomputing recommendations, customer choices or curve points.
"""
import copy


VIEW_VERSION = 1
SUMMARY_KEYS = ('run_id', 'version', 'status', 'created_at', 'updated_at',
                'config', 'scope', 'counts', 'recommendation', 'validation')
_RECOMMENDATION_KEYS = ('price', 'raw_price', 'selection', 'marketing_adjustment',
                        'revenue_fraction', 'reason', 'revenue_max_price', 'volume_max_price')
_CURVE_KEYS = ('price', 'expected_buyers', 'expected_member_buyers',
               'expected_revenue', 'expected_member_revenue')
_ROUND_KEYS = ('round', 'price', 'member_buyers', 'regular_buyers', 'buyers',
               'member_revenue', 'regular_revenue', 'revenue', 'weighted_revenue',
               'weighted_member_revenue', 'weighted_conversion', 'weighted_fulfilled_conversion',
               'weighted_buyers', 'member_intents', 'quota', 'remaining_quota', 'remaining_seats',
               'inventory_denials', 'capacity_binding', 'analysis', 'analysis_status',
               'analysis_error', 'analysis_attempts', 'unique_customers',
               'cumulative_unique_customers', 'paired_delta_vs_initial', 'hypothesis_test',
               'analysis_source', 'learning_updates', 'reused_analysis', 'selection')


def _pick(value, keys):
    return copy.deepcopy({key: value[key] for key in keys if key in value})


def summary(report):
    """List metadata, excluding fitted arrays and posterior model state."""
    result = _pick(report, (key for key in SUMMARY_KEYS if key != 'recommendation'))
    recommendation = report.get('recommendation')
    result['recommendation'] = (_pick(recommendation, _RECOMMENDATION_KEYS)
                                if isinstance(recommendation, dict) else recommendation)
    return result


def progress(report):
    """Heartbeat data that can be persisted and polled without reading reports."""
    result = _pick(report, ('run_id', 'version', 'status', 'created_at', 'updated_at',
                           'config', 'counts', 'progress', 'error', 'elapsed_seconds',
                           'analysis_unavailable_rounds', 'storage'))
    rounds = report.get('rounds') or []
    result['saved_rounds'] = len(rounds)
    result['has_recommendation'] = report.get('recommendation') is not None
    result['has_validation'] = report.get('validation') is not None
    return result


def _curve(rows):
    return [_pick(row, _CURVE_KEYS) for row in rows if isinstance(row, dict)]


def _decision(item):
    # Old saved reports sometimes keep the public identity in observation.
    # The observation itself repeats the full customer/prompt context.
    person = item.get('person') or (item.get('observation') or {}).get('person') or {}
    result = _pick(item, ('source', 'provider_call', 'cache_hit', 'forced', 'segment'))
    result['decision'] = _pick(item.get('decision') or item,
                               ('action', 'fallback_action', 'reason', 'reason_code'))
    result['person'] = _pick(person, ('customer_id', 'segment', 'segment_label'))
    if isinstance(item.get('settlement'), dict):
        result['settlement'] = _pick(item['settlement'], ('status',))
    return result


def detail(report):
    """Saved UI results and member feedback, with audit-only repetitions omitted."""
    result = summary(report)
    result.update(_pick(report, ('population', 'scenario', 'progress', 'error', 'elapsed_seconds',
                                 'analysis_unavailable_rounds', 'cumulative_unique_customers', 'storage')))
    result['rounds'] = []
    rounds = report.get('rounds') or []
    for saved in rounds:
        item = _pick(saved, _ROUND_KEYS)
        if isinstance(saved.get('decisions'), list):
            item['decisions'] = [_decision(decision) for decision in saved['decisions']]
        result['rounds'].append(item)
    recommendation = report.get('recommendation')
    # Match the UI's existing curve precedence while keeping every plotted point.
    if isinstance(recommendation, dict) and recommendation.get('model_curve') is not None:
        result['recommendation']['model_curve'] = _curve(recommendation['model_curve'])
    elif report.get('model_curve') is not None:
        result['model_curve'] = _curve(report['model_curve'])
    elif isinstance(recommendation, dict) and recommendation.get('curve') is not None:
        result['recommendation']['curve'] = _curve(recommendation['curve'])
    elif report.get('curve') is not None:
        result['curve'] = _curve(report['curve'])
    elif rounds and rounds[-1].get('curve') is not None:
        result['rounds'][-1]['curve'] = _curve(rounds[-1]['curve'])
    return result
