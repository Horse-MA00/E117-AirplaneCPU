import copy
import io
import json
import os
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

from llm_agent import adaptive_customers as adapter
from llm_agent.weighted_population import DEFAULT_WEIGHTS, allocate, metadata, population, validate_weights


def observation(cid="ONE", fare=200., budget=500., eligible=True, quota=20):
    return {"person": {"customer_id": cid, "segment": "flexible_budget", "segment_label": "Flexible budget traveller",
            "base_fare_budget": budget, "flexibility_days": 3, "eligible": eligible,
            "eligibility_reason": "This route and date can be used." if eligible else "The trip date cannot be used.",
            "population_weight": .9, "latent_wtp": 999},
            "flight": {"flight_id": "TEST", "origin": "HKG", "destination": "KMQ", "profit": 123},
            "normal_fare": 410., "member_fare": fare, "quota": quota, "optimizer_goal": "hidden"}


def response(decision=None):
    decision = decision or {"action": "BUY_MEMBER", "fallback_action": "BUY_REGULAR", "reason_code": "PRICE",
                            "reason": "The basic fare fits my trip and budget."}
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(decision)}}],
            "usage": {"total_tokens": 23}}


ENV = {"LLM_API_URL": "https://api.deepseek.com/chat/completions", "LLM_MODEL": "test-model",
       "LLM_API_KEY": "test-primary-secret-key", "LLM_API_KEY_SECONDARY": "test-secondary-secret-key"}


class WeightedPopulationTests(unittest.TestCase):
    def test_strata_are_covered_without_equal_weighting(self):
        people = population(20, 117)
        self.assertEqual(len(people), 20)
        self.assertEqual(len({p['segment'] for p in people}), len(DEFAULT_WEIGHTS))
        self.assertAlmostEqual(sum(p['population_weight'] for p in people), 1)
        for key, weight in DEFAULT_WEIGHTS.items():
            self.assertAlmostEqual(sum(p['population_weight'] for p in people if p['segment'] == key), weight)
        self.assertNotEqual(len({p['population_weight'] for p in people}), 1)

    def test_allocation_and_reproducibility(self):
        self.assertEqual(sum(allocate(101).values()), 101)
        self.assertEqual(population(28, 42), population(28, 42))
        self.assertNotEqual(population(28, 42), population(28, 43))
        self.assertTrue(all(p['membership_active'] and p['party_size'] == 1 for p in population(28)))
        self.assertTrue(all(p['trip_purpose'] == 'optional_leisure' for p in population(28)))

    def test_zero_weights_and_invalid_configuration(self):
        weights = {key: float(key == 'student') for key in DEFAULT_WEIGHTS}
        people = population(3, weights=weights)
        self.assertEqual({p['segment'] for p in people}, {'student'})
        self.assertAlmostEqual(sum(p['population_weight'] for p in people), 1.)
        for count in (0, len(DEFAULT_WEIGHTS)-1, True):
            with self.assertRaises(ValueError): population(count)
        for weights in ({}, {**DEFAULT_WEIGHTS, 'student': -1}, {**DEFAULT_WEIGHTS, 'student': float('nan')},
                        {**DEFAULT_WEIGHTS, 'student': .5}):
            with self.assertRaises(ValueError): validate_weights(weights)

    def test_source_is_not_invented_demographic_evidence(self):
        result = metadata(people=population(28))
        self.assertIn('not_observed', result['source'])
        self.assertEqual(len(result['sources']), 2)
        self.assertEqual(sum(s['sample_count'] for s in result['segments']), 28)
        self.assertTrue(all(s['weight'] == s['assumed_weight'] for s in result['segments']))
        self.assertTrue(any('assumptions' in x for x in result['limitations']))


class AdaptiveCustomerTests(unittest.TestCase):
    def test_public_observation_excludes_hidden_state_and_fees(self):
        obj = adapter.public_observation(observation())
        text = json.dumps(obj)
        self.assertNotIn('latent_wtp', text)
        self.assertNotIn('population_weight', text)
        self.assertNotIn('optimizer_goal', text)
        self.assertNotIn('profit', text)
        self.assertTrue(obj['person']['membership_active'])
        self.assertNotIn('membership_fee', obj)

    def test_optional_travel_scenario_is_visible_without_optimizer_state(self):
        obj = observation()
        fields = {
            'scenario_profile': 'flexible_deal_seekers', 'trip_purpose': 'optional_leisure',
            'booking_trigger': 'An unusually attractive fare can inspire a short trip.',
            'trip_commitment': 'not_planned_until_a_compelling_offer',
            'destination_openness': 'any_served_destination', 'travel_window_days': 30,
            'departure_time_tolerance': 'Can use early and late departures.',
            'price_sensitivity': 'very_high',
            'value_context': 'A ticket being affordable does not make this optional trip worthwhile.',
            'outside_option': 'Skip the trip and retain the ticket budget.',
        }
        obj['person'].update(fields, target_conversion=.9, candidate_profit=9000)
        visible = adapter.public_observation(obj)
        for key, value in fields.items():
            self.assertEqual(visible['person'][key], value)
        text = json.dumps(visible)
        for hidden in ('target_conversion', 'candidate_profit', 'population_weight', 'optimizer_goal'):
            self.assertNotIn(hidden, text)

    @patch.dict(os.environ, ENV)
    def test_affordable_optional_trip_can_decline_and_is_audited_as_real_choice(self):
        audit, requests = [], []
        decision = {'action': 'DECLINE', 'fallback_action': 'DECLINE', 'reason_code': 'OPTIONAL_TRIP_VALUE',
                    'reason': 'HKD 200 is affordable, but I only start an unplanned trip for a compelling bargain; I prefer to retain my ticket budget.'}
        obj = observation()
        obj['person'].update(scenario_profile='flexible_deal_seekers', trip_purpose='optional_leisure',
                             outside_option='Skip the trip and retain the ticket budget.')
        def transport(req):
            requests.append(json.loads(req.data))
            return io.BytesIO(json.dumps(response(decision)).encode())
        client = adapter.DecisionClient(max_calls=1, audit_callback=audit.append)
        with patch.object(adapter, '_transport', side_effect=transport):
            result = client.choose(obj)
        self.assertEqual(result['decision'], decision)
        self.assertFalse(result['forced'])
        self.assertTrue(result['learning_eligible'])
        self.assertEqual(result['source'], 'provider_live')
        self.assertEqual(requests[0]['messages'][0]['content'], adapter.PROMPTS['customer'].read_text())
        sent_person = json.loads(requests[0]['messages'][1]['content'])['person']
        self.assertEqual(sent_person['outside_option'], obj['person']['outside_option'])
        self.assertTrue(any(row['event'] == 'customer_response' for row in audit))

    @patch.dict(os.environ, ENV)
    def test_scenario_change_invalidates_exact_request_cache(self):
        first, second = observation(), observation()
        first['person']['value_context'] = 'A cheap unplanned getaway would be appealing.'
        second['person']['value_context'] = 'Only an exceptional bargain would trigger a trip.'
        client = adapter.DecisionClient(max_calls=2, use_cache=True)
        with patch.object(adapter, '_transport', side_effect=lambda req: io.BytesIO(json.dumps(response()).encode())) as call:
            client.choose(first)
            client.choose(second)
            replay = client.choose(second)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(replay['source'], 'provider_cache')
        self.assertEqual(client.stats()['cache_hits'], 1)

    def test_ineligible_is_forced_without_provider_or_training_exposure(self):
        client = adapter.DecisionClient(mode='synthetic', max_calls=0)
        result = client.choose(observation(eligible=False))
        self.assertTrue(result['forced'])
        self.assertFalse(result['learning_eligible'])
        self.assertEqual(client.stats()['provider_calls'], 0)

    def test_unaffordable_offer_is_valid_negative_price_evidence(self):
        client = adapter.DecisionClient(mode='synthetic')
        result = client.choose(observation(fare=200, budget=100))
        self.assertEqual(result['decision']['action'], 'DECLINE')
        self.assertTrue(result['learning_eligible'])

    def test_stockout_not_price_rejection(self):
        client = adapter.DecisionClient(mode='synthetic')
        result = client.choose(observation(quota=0, budget=100))
        self.assertFalse(result['learning_eligible'])
        self.assertNotIn('BUY_MEMBER', result['observation']['allowed_actions'])

    def test_fallback_must_be_legal(self):
        visible = adapter.public_observation(observation(budget=300))
        decision = response()['choices'][0]['message']['content']
        with self.assertRaises(ValueError): adapter.validate_decision(json.loads(decision), visible)

    def test_fallback_permission_list_encodes_budget_and_member_availability(self):
        for budget in (372, 387.77):
            visible = adapter.public_observation(observation(fare=300, budget=budget))
            self.assertIn('BUY_MEMBER', visible['allowed_actions'])
            self.assertEqual(visible['allowed_fallback_actions'], ['DECLINE'])
        visible = adapter.public_observation(observation(fare=300, budget=410))
        self.assertEqual(visible['allowed_fallback_actions'], ['DECLINE', 'BUY_REGULAR'])
        visible = adapter.public_observation(observation(quota=0, budget=500))
        self.assertEqual(visible['allowed_fallback_actions'], ['DECLINE'])

    @patch.dict(os.environ, ENV)
    def test_unaffordable_fallback_is_rejected_audited_and_never_repaired(self):
        audit = []
        wrong = {'action': 'BUY_MEMBER', 'fallback_action': 'BUY_REGULAR', 'reason_code': 'PRICE',
                 'reason': 'The member ticket is attractive and the normal ticket also fits my budget.'}
        client = adapter.DecisionClient(max_calls=2, concurrency=1, audit_callback=audit.append)
        with patch.object(adapter, '_transport', return_value=io.BytesIO(json.dumps(response(wrong)).encode())) as transport:
            with self.assertRaisesRegex(ValueError, 'failed validation'):
                client.choose(observation(fare=300, budget=387.77))
            self.assertEqual(transport.call_count, 1)
            with self.assertRaisesRegex(ValueError, 'stopped'):
                client.choose(observation('NEXT', fare=300, budget=387.77))
            self.assertEqual(transport.call_count, 1)
        self.assertEqual(client.stats()['failures'], 1)
        self.assertEqual(client.stats()['fresh_responses'], 1)
        raw = next(row for row in audit if row['event'] == 'customer_response')
        self.assertEqual(json.loads(json.loads(raw['raw_response_text'])['choices'][0]['message']['content']), wrong)
        self.assertTrue(any(row['event'] == 'customer_failed' for row in audit))

    def test_synthetic_common_random_numbers_monotone(self):
        client = adapter.DecisionClient(mode='synthetic', seed=11)
        low = client.choose_many([observation(str(i), 80) for i in range(100)])
        high = client.choose_many([observation(str(i), 300) for i in range(100)])
        lo_ids = {i for i, row in enumerate(low) if row['decision']['action'] == 'BUY_MEMBER'}
        hi_ids = {i for i, row in enumerate(high) if row['decision']['action'] == 'BUY_MEMBER'}
        self.assertTrue(hi_ids < lo_ids)
        self.assertGreater(len(hi_ids), 0)
        self.assertLess(len(lo_ids), 100)
        self.assertEqual(client.stats()['provider_calls'], 0)

    @patch.dict(os.environ, ENV)
    def test_parallel_order_keys_budget_and_audit(self):
        audit, headers = [], []
        guard = threading.Lock()
        def transport(req):
            with guard: headers.append(req.get_header('Authorization'))
            # Force a real overlap; no paid request is made by this test.
            time.sleep(.015)
            return io.BytesIO(json.dumps(response()).encode())
        client = adapter.DecisionClient(max_calls=8, concurrency=4, audit_callback=audit.append)
        with patch.object(adapter, '_transport', side_effect=transport):
            results = client.choose_many([observation(str(i)) for i in range(8)])
        self.assertEqual([r['observation']['person']['customer_id'] for r in results], list(map(str, range(8))))
        stats = client.stats()
        self.assertEqual(stats['provider_calls'], 8)
        self.assertEqual(stats['key_slots'], {'primary': 4, 'secondary': 4})
        self.assertGreaterEqual(stats['peak_parallel_calls'], 2)
        self.assertLessEqual(stats['peak_parallel_calls'], 4)
        self.assertEqual(stats['peak_parallel'], stats['peak_parallel_calls'])
        self.assertEqual(stats['total_tokens'], 8*23)
        self.assertEqual(len(set(headers)), 2)
        text = json.dumps(audit)
        for secret in (ENV['LLM_API_KEY'], ENV['LLM_API_KEY_SECONDARY']): self.assertNotIn(secret, text)
        self.assertTrue(any(r['event'] == 'customer_response' and 'raw_response_text' in r for r in audit))
        with patch.object(adapter, '_transport') as transport:
            with self.assertRaises(ValueError): client.choose(observation('nine'))
            transport.assert_not_called()

    @patch.dict(os.environ, ENV)
    def test_concurrent_budget_cannot_overshoot(self):
        client = adapter.DecisionClient(max_calls=2, concurrency=8)
        def transport(req):
            time.sleep(.01)
            return io.BytesIO(json.dumps(response()).encode())
        with patch.object(adapter, '_transport', side_effect=transport) as call:
            with self.assertRaises(ValueError): client.choose_many([observation(str(i)) for i in range(20)])
            self.assertEqual(call.call_count, 2)
        self.assertEqual(client.stats()['provider_calls'], 2)

    @patch.dict(os.environ, ENV)
    def test_non_english_output_is_audited_and_not_substituted(self):
        audit = []
        bad = {'action': 'BUY_MEMBER', 'fallback_action': 'DECLINE', 'reason_code': 'PRICE', 'reason': '太便宜了'}
        client = adapter.DecisionClient(max_calls=1, audit_callback=audit.append)
        with patch.object(adapter, '_transport', return_value=io.BytesIO(json.dumps(response(bad)).encode())):
            with self.assertRaises(ValueError): client.choose(observation())
        self.assertEqual(client.stats()['failures'], 1)
        self.assertEqual(client.stats()['provider_calls'], 1)
        self.assertTrue(any(r['event'] == 'customer_response' for r in audit))
        self.assertTrue(any(r['event'] == 'customer_failed' for r in audit))

    @patch.dict(os.environ, ENV)
    def test_provider_failure_stops_queued_dispatch_and_redacts_error_body(self):
        audit = []
        client = adapter.DecisionClient(max_calls=100, concurrency=4, audit_callback=audit.append)
        def fail(req):
            # An untrusted upstream error may echo the credential. Neither
            # the audit nor the surfaced error is allowed to expose it.
            secret = ENV['LLM_API_KEY']
            raise urllib.error.HTTPError(req.full_url, 401, 'Unauthorized ' + secret, {}, io.BytesIO(secret.encode()))
        with patch.object(adapter, '_transport', side_effect=fail) as transport:
            with self.assertRaises(ValueError) as error:
                client.choose_many([observation(str(i)) for i in range(30)])
            self.assertLessEqual(transport.call_count, 4)
            count = transport.call_count
            with self.assertRaises(ValueError): client.choose(observation('after-error'))
            self.assertEqual(transport.call_count, count)
        self.assertTrue(client.stats()['stopped_after_failure'])
        self.assertNotIn(ENV['LLM_API_KEY'], str(error.exception))
        self.assertNotIn(ENV['LLM_API_KEY'], json.dumps(audit))
        self.assertTrue(any(r['event'] == 'customer_failed' and r['raw_response_text'] == '[REDACTED]' for r in audit))

    @patch.dict(os.environ, ENV)
    def test_cache_is_labelled_replay_and_not_new_call(self):
        client = adapter.DecisionClient(max_calls=1, use_cache=True)
        with patch.object(adapter, '_transport', return_value=io.BytesIO(json.dumps(response()).encode())) as call:
            first = client.choose(observation())
            second = client.choose(observation())
        self.assertEqual(call.call_count, 1)
        self.assertEqual(first['source'], 'provider_live')
        self.assertEqual(second['source'], 'provider_cache')
        self.assertEqual(client.stats()['cache_hits'], 1)

    @patch.dict(os.environ, ENV)
    def test_optional_null_usage_does_not_invalidate_choice(self):
        envelope = response(); envelope['usage'] = None
        client = adapter.DecisionClient(max_calls=1)
        with patch.object(adapter, '_transport', return_value=io.BytesIO(json.dumps(envelope).encode())):
            result = client.choose(observation())
        self.assertEqual(result['decision']['action'], 'BUY_MEMBER')
        self.assertEqual(client.stats()['total_tokens'], 0)
        self.assertEqual(client.stats()['failures'], 0)

    @patch.dict(os.environ, {**ENV, 'LLM_API_URL': 'http://example.com'})
    def test_insecure_provider_is_rejected(self):
        with self.assertRaises(ValueError): adapter.DecisionClient(max_calls=1)

    @patch.dict(os.environ, ENV)
    def test_retained_secret_redacted_even_after_env_change(self):
        audit = []
        client = adapter.DecisionClient(max_calls=1, audit_callback=audit.append)
        with patch.dict(os.environ, {'LLM_API_KEY': 'changed-env-value'}):
            client._audit({'raw_response_text': ENV['LLM_API_KEY']})
        self.assertNotIn(ENV['LLM_API_KEY'], json.dumps(audit))

    def test_analysis_evidence_and_counts_are_validated(self):
        context = {'feedback': [{'customer_id': 'ONE', 'decision': {'reason_code': 'PRICE'}}]}
        valid = {'summary': 'The fare was too high for one traveller.',
                 'reason_counts': {'price': 1, 'date': 0, 'companions': 0, 'availability': 0, 'other': 0},
                 'hypothesis': 'A lower fare may change that choice.', 'evidence_customer_ids': ['ONE']}
        self.assertEqual(adapter.validate_analysis(valid, context), valid)
        invalid = copy.deepcopy(valid); invalid['evidence_customer_ids'] = ['INVENTED']
        with self.assertRaises(ValueError): adapter.validate_analysis(invalid, context)
        invalid = copy.deepcopy(valid); invalid['reason_counts']['date'] = 1
        with self.assertRaises(ValueError): adapter.validate_analysis(invalid, context)


if __name__ == '__main__':
    unittest.main()
