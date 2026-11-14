"""Public-information response learning, paired evidence and whole-HKD prices."""
import copy
import math
import unittest
from unittest.mock import patch

import numpy as np

from backend.member_response import PurchasePosterior, fare_cap, learner_view, recommend, whole_price


def person(i, segment='student', flex=21, weight=1.):
    return dict(customer_id=f'PUBLIC-{i}', segment=segment, flexibility_days=flex,
                population_weight=weight)


def rows():
    return [dict(person=person(i), price=100+i*10, normal_fare=410,
                 bought=i % 3 != 0, sample_weight=1.) for i in range(24)]


class PublicLearningTests(unittest.TestCase):
    def test_private_attributes_are_not_exposed_or_required(self):
        visible = person(1)
        private = dict(visible, base_fare_budget=float('nan'), eligible=False,
                       latent_willingness=100000, value_context='Must buy',
                       future_choice=True, phase='validation')
        self.assertEqual(learner_view(private), visible)
        self.assertEqual(set(learner_view(private)),
                         {'customer_id', 'segment', 'flexibility_days', 'population_weight'})
        model = PurchasePosterior(['student'])
        np.testing.assert_array_equal(model.predict([private], 300, 410),
                                      model.predict([visible], 300, 410))
        self.assertGreater(model.predict([private], 300, 410)[0], 0.)

    def test_poisoning_budgets_cannot_change_fit_or_selected_price(self):
        clean = rows()
        poisoned = copy.deepcopy(clean)
        for i, row in enumerate(poisoned):
            row['person'].update(base_fare_budget=[0, float('nan'), 1e9][i % 3],
                                 eligible=False, value_context='hidden', latent_wtp=-999)
        a, b = PurchasePosterior(['student']).fit(clean), PurchasePosterior(['student']).fit(poisoned)
        np.testing.assert_array_equal(a.mean, b.mean)
        np.testing.assert_array_equal(a.covariance, b.covariance)
        support = [person(i+100) for i in range(8)]
        private_support = [dict(p, base_fare_budget=137.93, eligible=False) for p in support]
        left = recommend(a, support, 410, 6, np.random.default_rng(12))
        right = recommend(b, private_support, 410, 6, np.random.default_rng(12))
        self.assertEqual(left, right)
        self.assertEqual([p['price'] for p in left['curve']], list(range(329)))
        self.assertFalse(left['private_constraints_used'])

    def test_affordability_declines_are_aggregate_observations(self):
        people = [dict(person(i), base_fare_budget=1, eligible=False) for i in range(35)]
        no = PurchasePosterior(['student']).fit([
            dict(person=p, price=300, normal_fare=410, bought=False) for p in people])
        yes = PurchasePosterior(['student']).fit([
            dict(person=p, price=300, normal_fare=410, bought=True) for p in people])
        # It is the environment's responsibility to validate a buy. This model
        # never reads the supplied private budget or private feasibility flag.
        self.assertEqual(no.summary()['likelihood_rows'], 35)
        self.assertEqual(no.summary()['effective_likelihood_mass'], 35)
        self.assertLess(no.predict([person(100)], 300, 410)[0], .2)
        self.assertGreater(yes.predict([person(100)], 300, 410)[0], .8)

    def test_declared_flexibility_retains_two_vs_six_week_difference(self):
        model = PurchasePosterior(['student'])
        draw = model.mean.copy()
        draw[2] = 1.
        q = model.predict([person(1, flex=14), person(2, flex=45)], 200, 410, draw=draw)
        self.assertGreater(q[1], q[0])

    def test_all_draws_have_monotone_price_response(self):
        model = PurchasePosterior(['student'])
        rng = np.random.default_rng(117)
        for _ in range(15):
            draw = model.sample(rng)
            q = [model.predict([person(1)], p, 410, draw=draw)[0] for p in (0, 100, 200, 328)]
            self.assertTrue(np.all(np.diff(q) <= 0))
            self.assertTrue(all(0 < x < 1 for x in q))

    def test_duplicate_exposure_and_paired_quotes_do_not_create_people(self):
        baseline = rows()
        first = PurchasePosterior(['student']).fit(baseline)
        repeated = PurchasePosterior(['student']).fit(baseline*4)
        np.testing.assert_allclose(first.mean, repeated.mean, atol=1e-12)
        np.testing.assert_allclose(first.covariance, repeated.covariance, atol=1e-12)
        self.assertEqual(repeated.summary()['duplicate_exposures'], 72)
        paired = baseline + [dict(row, price=row['price']+1) for row in baseline]
        model = PurchasePosterior(['student']).fit(paired)
        self.assertEqual(model.summary()['likelihood_rows'], 48)
        self.assertEqual(model.summary()['unique_personas'], 24)
        self.assertLessEqual(model.summary()['effective_likelihood_mass'], 24.)

    def test_conflicting_replays_and_validation_rows_are_rejected(self):
        one = rows()[0]
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            PurchasePosterior(['student']).fit([one, dict(one, bought=not one['bought'])])
        for phase in ('validation', 'confirmation', 'holdout'):
            with self.assertRaisesRegex(ValueError, 'Only search'):
                PurchasePosterior(['student']).fit([dict(one, phase=phase)])

    def test_fit_rejects_invalid_observations(self):
        one = rows()[0]
        for field, value in [('price', 100.01), ('price', True), ('normal_fare', 0),
                             ('bought', 'yes'), ('sample_weight', float('nan'))]:
            with self.assertRaises(ValueError):
                PurchasePosterior(['student']).fit([dict(one, **{field: value})])
        with self.assertRaises(ValueError):
            PurchasePosterior(['student']).predict([person(1, segment='unknown')], 100, 410)

    def test_known_response_can_be_learned_without_personal_budgets(self):
        rng = np.random.default_rng(2026111701)
        observations = []
        for i in range(600):
            price = int(rng.integers(10, 329))
            q = 1/(1+math.exp(-(3-6*price/410)))
            observations.append(dict(person=person(i, flex=0), price=price,
                                     normal_fare=410, bought=bool(rng.random()<q)))
        model = PurchasePosterior(['student']).fit(observations)
        result = recommend(model, [person(i+1000, flex=0) for i in range(16)], 410, 16,
                           np.random.default_rng(17), draw=False, revenue_fraction=1.)
        grid = np.arange(329)
        true_curve = grid/(1+np.exp(-(3-6*grid/410)))
        chosen = result['price']
        self.assertGreater(true_curve[chosen]/max(true_curve), .95)
        self.assertTrue(model.summary()['converged'])


class WholePriceRecommendationTests(unittest.TestCase):
    def test_whole_price_and_decimal_safe_cap(self):
        self.assertEqual(whole_price(293.), 293)
        for value in (293.90, True, -1, float('inf')):
            with self.assertRaises(ValueError): whole_price(value)
        self.assertEqual(fare_cap(410), 328)
        self.assertEqual(fare_cap(410.99), 328)
        self.assertEqual(fare_cap(411.9), 328)  # quoted normal is HK$411, not HK$411.9
        self.assertEqual(fare_cap(293.90), 234)  # normal quote floors to HK$293 first
        self.assertEqual(fare_cap(1.01), 0)
        self.assertIsInstance(fare_cap(410), int)

    def test_candidate_grid_is_integer_and_selected_diagnostics_are_separate(self):
        model = PurchasePosterior(['student'])
        result = recommend(model, [person(i) for i in range(12)], 410, 12,
                           np.random.default_rng(42), draw=False, candidate_prices=[100, 200, 328])
        self.assertTrue(all(type(row['price']) is int for row in result['curve']))
        self.assertIn(result['price'], [100, 200, 328])
        self.assertIn(result['best_revenue_candidate']['price'], [100, 200, 328])
        self.assertEqual(result['most_buyers_candidate']['price'], 100)
        self.assertGreaterEqual(result['expected_member_revenue']+1e-8,
                                .95*result['best_expected_member_revenue'])
        self.assertTrue(all(row['revenue_low'] <= row['expected_member_revenue'] <= row['revenue_high']
                            for row in result['curve']))
        for candidates in ([], [-1], [328.01], [329]):
            with self.assertRaises(ValueError):
                recommend(model, [person(1)], 410, 1, np.random.default_rng(0), candidate_prices=candidates)

    def test_independent_support_size_is_not_market_size(self):
        model = PurchasePosterior(['student'])
        support = [person(i, weight=1/100) for i in range(100)]
        result = recommend(model, support, 410, 1, np.random.default_rng(3),
                           target_customers=16, candidate_prices=[100])
        q = result['purchase_probability']
        self.assertAlmostEqual(result['expected_buyers'], 1-(1-q)**16)
        self.assertEqual(result['target_customers'], 16)
        self.assertEqual(result['support_customers'], 100)
        self.assertLessEqual(result['expected_buyers'], 1.)

    def test_batched_curve_matches_scalar_and_builds_features_once(self):
        model = PurchasePosterior(['student']).fit(rows())
        support = [person(i+100, flex=14+i%30, weight=1/128) for i in range(128)]
        with patch.object(model, '_features', wraps=model._features) as features:
            result = recommend(model, support, 410, 3, np.random.default_rng(5), target_customers=16)
            self.assertEqual(features.call_count, 1)
        draw = np.array(result['selection_parameters'])
        for point in result['curve'][::73]:
            q = float(np.mean(model.predict(support, point['price'], 410, draw=draw)))
            mass = [math.comb(16, k)*q**k*(1-q)**(16-k) for k in range(17)]
            expected = sum(min(3,k)*p for k,p in enumerate(mass))
            self.assertAlmostEqual(point['expected_buyers'], expected)
            self.assertAlmostEqual(point['expected_member_revenue'], point['price']*expected)

    def test_predict_only_wrapper_keeps_equivalent_diagnostics(self):
        model = PurchasePosterior(['student']).fit(rows())

        class Wrapper:
            def sample(self, rng): return model.sample(rng)
            def predict(self, *args, **kwargs): return model.predict(*args, **kwargs)
            def summary(self): return model.summary()

        support = [person(i+100, flex=14+i) for i in range(16)]
        first = recommend(model, support, 410, 4, np.random.default_rng(5), draw=False,
                          candidate_prices=[100, 200, 328])
        wrapped = recommend(Wrapper(), support, 410, 4, np.random.default_rng(5), draw=False,
                            candidate_prices=[100, 200, 328])
        self.assertEqual(first['price'], wrapped['price'])
        for a,b in zip(first['curve'],wrapped['curve']):
            for key in a: self.assertAlmostEqual(a[key],b[key])

    def test_seeded_joint_draw_is_reproducible(self):
        model = PurchasePosterior(['student'])
        people = [person(i) for i in range(8)]
        a = recommend(model, people, 410, 6, np.random.default_rng(50))
        b = recommend(model, people, 410, 6, np.random.default_rng(50))
        self.assertEqual(a,b)
        self.assertEqual(a['selection_kind'], 'thompson_joint_posterior_draw')
        draws = [recommend(model,people,410,8,np.random.default_rng(seed))['price'] for seed in range(8)]
        self.assertGreater(len(set(draws)), 2)


if __name__ == '__main__':
    unittest.main()
