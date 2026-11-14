"""Bind publishing suggestions to a validated flight/date/round experiment.

Inventory is recalculated at read time; experiment results never mint quota.
"""
from . import optimization, optimization_store
from .release_policy import release_budget


def suggestions(flight_id, day, inventory, forecast_for):
    if day not in (28, 14, 7):
        raise ValueError('Choose a D28, D14 or D7 release round')
    prediction = forecast_for(flight_id, day)
    ceiling = int(prediction['releasable_seats'])
    status = inventory.release_status(flight_id, day, ceiling)
    result = {'flight_id': flight_id, 'forecast_day': day,
              'current_release_limit': status['new_release_limit'], 'release_status': status,
              'suggestions': [], 'results': [], 'latest_run': None,
              'reason': status['blocked_reason'] or ''}
    current = optimization.provenance()
    with optimization_store.connection() as db:
        ids = [row[0] for row in db.execute('SELECT run_id FROM optimization_runs ORDER BY updated_at DESC, rowid DESC')]
    seen_modes, displayed_modes = set(), set()
    for run_id in ids:
        saved = optimization_store.run(run_id)
        scope = saved['config'].get('scope') or {}
        if scope.get('flight_id') != flight_id or scope.get('as_of_day', scope.get('forecast_day')) != day:
            continue
        if result['latest_run'] is not None and saved['status'] != 'completed':
            continue
        report = optimization.read(run_id)
        run = {'run_id': run_id, 'status': report.get('status', saved['status']),
               'updated_at': saved['updated_at'], 'provenance_current': saved['provenance'] == current,
               'model_version': saved['provenance'].get('version')}
        if result['latest_run'] is None:
            result['latest_run'] = run
        if run['status'] != 'completed':
            continue
        for track in report['tracks']:
            mode = track['mode']
            best, validation = track.get('best') or {}, track.get('validation') or {}
            if mode not in displayed_modes:
                displayed_modes.add(mode)
                result['results'].append({**run, 'mode': mode, 'decision': track.get('decision', 'PENDING'),
                    'validated': bool(validation), 'member_fare': best.get('member_fare'),
                    'membership_fee': best.get('membership_fee'),
                    'incremental_contribution': validation.get('incremental_contribution'),
                    'decision_reason': track.get('decision_reason')})
            if not run['provenance_current']:
                continue
            if mode in seen_modes:
                continue
            seen_modes.add(mode)
            # A newer NO_OFFER supersedes an older recommendation in this track.
            if status['blocked_reason'] or track.get('decision') != 'OFFER' or not validation or not best:
                continue
            fraction = float(saved['config']['release_fraction'])
            candidate_prediction = prediction
            if best.get('seat_calibration') is not None:
                from .seat_feedback import apply_profile
                candidate_prediction = apply_profile(prediction, best['seat_calibration'], day)
            candidate_ceiling = min(ceiling, int(candidate_prediction['releasable_seats']))
            allocation = release_budget(candidate_ceiling, status['member_sold'], status['total_active_unsold'], fraction)
            seats = min(status['new_release_limit'], allocation['new_allocation'])
            result['suggestions'].append({
                'run_id': run_id, 'mode': mode, 'decision': 'OFFER', 'flight_id': flight_id,
                'forecast_day': day, 'scope': scope, 'member_fare': best['member_fare'],
                'membership_fee': best['membership_fee'], 'release_fraction': fraction,
                'release_seats': seats, 'suggested_new_seats': seats,
                'validated_release_ceiling': candidate_ceiling,
                'incremental_contribution': track['validation']['incremental_contribution'],
                'total_contribution': track['validation'].get('total_contribution', track['validation'].get('contribution')),
                'mean_buyers': track['validation'].get('mean_buyers'),
                'profit_margin': track['validation'].get('profit_margin'),
            })
    if not result['suggestions'] and not result['reason']:
        latest = result['latest_run']
        if latest is None:
            result['reason'] = 'No optimization has been run for this flight and release round.'
        elif not latest['provenance_current']:
            result['reason'] = 'Previous optimization uses an earlier model or configuration. Rerun Optimize for a current suggestion.'
        elif latest['status'] != 'completed':
            result['reason'] = 'The latest optimization is not complete. Review its progress in Optimize.'
        elif result['results'] and all(row['decision'] == 'NO_OFFER' for row in result['results']):
            result['reason'] = 'Completed optimization recommends no offer for this flight and release round.'
        else:
            result['reason'] = 'No completed, validated optimization recommends an offer for this flight and release round.'
    return result


def validate_draft(body, inventory, forecast_for):
    """Optional experiment binding on publication; manual drafts remain supported."""
    if not body.get('optimization_run_id'):
        return
    candidates = suggestions(body['flight_id'], body['days_to_departure'], inventory, forecast_for)['suggestions']
    selected = next((row for row in candidates if row['run_id'] == body['optimization_run_id'] and row['mode'] == body.get('optimization_mode')), None)
    if selected is None:
        raise ValueError('Optimization suggestion is stale or belongs to a different flight or round; refresh suggestions')
    if body['base_fare'] != selected['member_fare'] or body['quantity'] > selected['release_seats']:
        raise ValueError('Draft exceeds the selected optimization suggestion; refresh or create a manual draft')
    if inventory.plan()['fee'] != selected['membership_fee']:
        raise ValueError('Save the suggested membership fee before publishing this optimized offer')
    return selected
