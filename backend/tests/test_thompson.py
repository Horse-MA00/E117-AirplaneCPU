"""Mathematical invariants and simulated-response checks for adaptive pricing."""
import math
import unittest

import numpy as np

from backend.thompson import PurchasePosterior, capacity_expectation, fare_cap, recommend


def person(i, segment="budget", budget=1000., weight=1.):
    return dict(customer_id=f"P{i}", segment=segment, base_fare_budget=budget,
                flexibility_days=2, eligible=True, population_weight=weight)


class CapacityTests(unittest.TestCase):
    def test_capacity_uses_distribution_not_minimum_of_mean(self):
        # E[min(1,Binomial(2,.5))] = P(at least one buy) = .75, not 1.
        self.assertAlmostEqual(capacity_expectation([.5, .5], 1), .75)
        self.assertAlmostEqual(capacity_expectation([.2, .7], 1), .76)
        self.assertEqual(capacity_expectation([1., 1.], 1), 1.)
        self.assertEqual(capacity_expectation([.2, .7], 0), 0.)
        self.assertAlmostEqual(capacity_expectation([.2, .7], 2), .9)

    def test_invalid_values(self):
        for ps, quota in [([1.1], 1), ([float("nan")], 1), ([.5], -1), ([.5], True)]:
            with self.assertRaises(ValueError):
                capacity_expectation(ps, quota)


class PosteriorTests(unittest.TestCase):
    def test_price_cap_rounds_down(self):
        self.assertEqual(fare_cap(410), 328)
        self.assertEqual(fare_cap(410.01), 328)
        self.assertEqual(fare_cap(1.01), .8)
        with self.assertRaises(ValueError):
            fare_cap(float("inf"))

    def test_all_sampled_curves_monotone_and_constraints_obeyed(self):
        model = PurchasePosterior(["budget"])
        people = [person(1, budget=250), {**person(2), "eligible": False}]
        rng = np.random.default_rng(5)
        for _ in range(30):
            parameters = model.sample(rng)
            curve = np.array([model.predict(people, p, 410, draw=parameters)
                              for p in [0, 50, 150, 250, 328]])
            self.assertTrue(np.all(np.diff(curve[:, 0]) <= 0))
            self.assertTrue(np.all(curve[:, 1] == 0))
            self.assertEqual(curve[-1, 0], 0)

    def test_observations_change_predictions_without_divergence(self):
        yes = PurchasePosterior(["budget"])
        no = PurchasePosterior(["budget"])
        people = [person(i) for i in range(35)]
        yes.fit([dict(person=p, price=200, normal_fare=410, bought=True) for p in people])
        no.fit([dict(person=p, price=200, normal_fare=410, bought=False) for p in people])
        self.assertGreater(yes.predict(people[:1], 200, 410)[0], .8)
        self.assertLess(no.predict(people[:1], 200, 410)[0], .2)
        self.assertTrue(np.all(np.isfinite(yes.covariance)))
        self.assertTrue(yes.summary()["converged"])

    def test_duplicate_persona_decisions_do_not_create_information(self):
        rows = [dict(person=person(i), price=100 + i * 5, normal_fare=410,
                     bought=i % 3 != 0, sample_weight=1 + i % 2) for i in range(12)]
        once = PurchasePosterior(["budget"]).fit(rows)
        duplicate = PurchasePosterior(["budget"]).fit(rows * 8)
        np.testing.assert_allclose(once.mean, duplicate.mean, atol=1e-8)
        np.testing.assert_allclose(once.covariance, duplicate.covariance, atol=1e-8)
        self.assertLessEqual(duplicate.summary()["effective_likelihood_mass"], 12)

    def test_known_constraints_and_invalid_labels(self):
        model = PurchasePosterior(["budget"])
        model.fit([dict(person=person(1, budget=10), price=100, normal_fare=410, bought=False)])
        self.assertEqual(model.summary()["unaffordable"], 1)
        self.assertEqual(model.summary()["likelihood_rows"], 0)
        with self.assertRaises(ValueError):
            model.fit([dict(person=person(1, budget=10), price=100, normal_fare=410, bought=True)])
        with self.assertRaises(ValueError):
            model.predict([person(1)], float("nan"), 410)


class RecommendationTests(unittest.TestCase):
    def test_seed_reproducible_joint_draw_and_bounded_price(self):
        model = PurchasePosterior(["budget"])
        people = [person(i) for i in range(12)]
        one = recommend(model, people, 410, 5, np.random.default_rng(123))
        two = recommend(model, people, 410, 5, np.random.default_rng(123))
        self.assertEqual(one, two)
        self.assertLessEqual(one["price"], 328)
        self.assertEqual(one["selection_kind"], "thompson_joint_posterior_draw")
        self.assertLessEqual(max(row["expected_buyers"] for row in one["curve"]), 5 + 1e-8)

    def test_prior_sampling_explores_without_predefined_probe_sequence(self):
        model = PurchasePosterior(["budget"])
        people = [person(i) for i in range(20)]
        prices = [recommend(model, people, 410, 20, np.random.default_rng(seed))["price"]
                  for seed in range(16)]
        self.assertGreater(len(set(prices)), 5)
        self.assertTrue(all(0 <= p <= 328 for p in prices))

    def test_target_weights_change_mixture_not_integer_ledger(self):
        model = PurchasePosterior(["budget"])
        people = [person(1, budget=500, weight=.9), person(2, budget=0, weight=.1)]
        result = recommend(model, people, 410, 1, np.random.default_rng(4), candidate_prices=[100])
        theta = np.array(result["selection_parameters"])
        q = model.predict(people, 100, 410, draw=theta)
        mixture_q = .9 * q[0] + .1 * q[1]
        self.assertAlmostEqual(result["expected_buyers"], 1 - (1 - mixture_q) ** 2)
        self.assertEqual(result["target_customers"], 2)

    def test_final_selection_stays_among_tested_prices(self):
        result = recommend(PurchasePosterior(["budget"]), [person(i) for i in range(20)],
                           410, 20, np.random.default_rng(42), draw=False,
                           candidate_prices=[100, 150, 200, 328])
        self.assertIn(result["price"], [100, 150, 200, 328])
        self.assertGreaterEqual(result["expected_member_revenue"] + 1e-8,
                                .95 * result["best_expected_member_revenue"])
        self.assertEqual(result["candidate_scope"], "tested_prices")
        with self.assertRaises(ValueError):
            recommend(PurchasePosterior(["budget"]), [person(1)], 410, 1,
                      np.random.default_rng(0), candidate_prices=[328.01])

    def test_learning_known_response_finds_near_reference_revenue(self):
        # This assesses a synthetic known-demand family, not real customer fit.
        # Independent people avoid counting repeated personas as new evidence.
        rng = np.random.default_rng(20261114)
        normal = 410
        rows = []
        for i in range(600):
            p = float(rng.uniform(10, 328))
            q = 1 / (1 + math.exp(-(3. - 6. * p / normal)))
            rows.append(dict(person=person(i, budget=normal), price=p,
                             normal_fare=normal, bought=bool(rng.random() < q)))
        model = PurchasePosterior(["budget"]).fit(rows)
        panel = [person(i, budget=normal) for i in range(30)]
        result = recommend(model, panel, normal, 30, np.random.default_rng(99),
                           draw=False, revenue_fraction=1.)
        prices = np.linspace(0, 328, 2001)
        expected_revenue = prices / (1 + np.exp(-(3 - 6 * prices / normal)))
        chosen = result["price"]
        achieved = chosen / (1 + math.exp(-(3 - 6 * chosen / normal)))
        self.assertGreater(achieved / max(expected_revenue), .95)
        self.assertGreater(model.summary()["map_price_sensitivity"], 4.)

    def test_sequential_thompson_search_across_independent_panels(self):
        # The latent uniforms stay fixed within a panel: querying the same
        # synthetic customer again does not create an independent person.
        ratios = []
        grid = np.linspace(0, 328, 10001)
        oracle = max(grid / (1 + np.exp(-(3 - 6 * grid / 410))))
        initial_revenue = 328 / (1 + math.exp(-(3 - 6 * 328 / 410)))
        for seed in [11, 23, 47, 89, 117]:
            rng = np.random.default_rng(seed)
            model = PurchasePosterior(["budget"])
            people = [{**person(i, budget=410, weight=1 / 40), "flexibility_days": 0}
                      for i in range(40)]
            latent = rng.random(40)
            rows, prices = [], [328.]
            for _ in range(10):
                price = prices[-1]
                q = 1 / (1 + math.exp(-(3 - 6 * price / 410)))
                rows.extend(dict(person=p, price=price, normal_fare=410, bought=bool(u < q))
                            for p, u in zip(people, latent))
                model.fit(rows)
                prices.append(recommend(model, people, 410, 40, rng)["price"])
            selected = recommend(model, people, 410, 40, np.random.default_rng(seed + 1000),
                                 draw=False, candidate_prices=prices[:-1], revenue_fraction=1.)["price"]
            true_revenue = selected / (1 + math.exp(-(3 - 6 * selected / 410)))
            self.assertGreater(true_revenue, initial_revenue)
            ratios.append(true_revenue / oracle)
        self.assertGreater(float(np.mean(ratios)), .93)
        self.assertGreater(min(ratios), .85)


if __name__ == "__main__":
    unittest.main()
