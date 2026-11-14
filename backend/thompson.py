"""Constrained Bayesian purchase-response learning and Thompson price selection.

The Gaussian posterior is a *local Laplace approximation* to a deliberately
tempered likelihood, not a calibrated population confidence interval. Repeated
decisions by the same synthetic persona are one cluster. Their combined power
is at most one, so repeated API calls cannot masquerade as new people.

Post-stratification estimates a target cohort, rather than fractional bookings:
its people are independent draws from the configured segment mixture. Thus its
count is Binomial(N, sum_i population_weight_i * q_i), conditional on one sampled
parameter vector. Actual seats must still be settled by the market engine.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

VERSION = "member-purchase-thompson-v1"
CAP_RATIO = .8


def _finite(value, name, lower=None):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value) or (lower is not None and value < lower):
        raise ValueError(f"Invalid {name}")
    return value


def _sigmoid(x):
    return 1. / (1. + np.exp(-np.clip(x, -40., 40.)))


def _softplus(x):
    return np.logaddexp(0., x)


def fare_cap(normal_fare):
    normal_fare = _finite(normal_fare, "normal_fare", .01)
    return math.floor(round(normal_fare * CAP_RATIO * 100, 6)) / 100


def capacity_expectation(probabilities, quota):
    """Exact E[min(quota, sum Bernoulli(p_i))] for independent conditional p_i.

    State quota is absorbing. This deliberately differs from min(quota,sum p).
    """
    if isinstance(quota, bool) or not isinstance(quota, (int, np.integer)) or quota < 0:
        raise ValueError("quota must be a nonnegative integer")
    ps = np.asarray(probabilities, dtype=float)
    if ps.ndim != 1 or not np.all(np.isfinite(ps)) or np.any((ps < 0) | (ps > 1)):
        raise ValueError("Invalid purchase probabilities")
    quota = min(int(quota), len(ps))
    if not quota:
        return 0.
    if quota == len(ps):
        return float(ps.sum())
    mass = np.zeros(quota + 1)
    mass[0] = 1.
    for p in ps:
        next_mass = mass * (1. - p)
        next_mass[1:] += mass[:-1] * p
        next_mass[-1] += mass[-1] * p
        mass = next_mass
    return float(np.dot(mass, np.arange(quota + 1)))


def _binomial_capacity(probabilities, n, quota):
    """Vectorized exact binomial capacity expectation for multiple parameter draws."""
    p = np.asarray(probabilities, dtype=float)
    quota = min(quota, n)
    if not quota:
        return np.zeros_like(p)
    if quota == n:
        return p * n
    mass = np.zeros((len(p), quota + 1))
    mass[:, 0] = 1.
    for _ in range(n):
        nxt = mass * (1. - p[:, None])
        nxt[:, 1:] += mass[:, :-1] * p[:, None]
        nxt[:, -1] += mass[:, -1] * p
        mass = nxt
    return mass @ np.arange(quota + 1)


class PurchasePosterior:
    """Shared price slope and shrunk segment intercepts, learned from intents.

    logit(q) = intercept + segment + budget_coef*log(budget/normal_fare)
               + flexibility_coef*flexibility/7 - softplus(slope_raw)*p/normal_fare.

    The affordability and route/date eligibility masks are known constraints.
    They are not inferred from a language model's textual justification.
    """

    def __init__(self, segment_ids):
        self.segments = list(segment_ids)
        if (not self.segments or len(set(self.segments)) != len(self.segments)
                or any(not isinstance(s, str) or not s for s in self.segments)):
            raise ValueError("Unique nonempty segment identifiers required")
        self.segment_index = {segment: i for i, segment in enumerate(self.segments)}
        size = 4 + len(self.segments)
        # Proper weak priors also prevent separation/all-buy/all-decline divergence.
        self.prior_mean = np.zeros(size)
        self.prior_mean[:4] = [1., math.log(math.expm1(3.)), 1., 0.]
        self.prior_sd = np.array([2., 2., .8, .7] + [.8] * len(self.segments))
        self.precision = 1. / self.prior_sd ** 2
        self.mean = self.prior_mean.copy()
        self.covariance = np.diag(self.prior_sd ** 2)
        self.diagnostics = dict(observations=0, unique_personas=0, likelihood_rows=0,
                                effective_likelihood_mass=0., ineligible=0, unaffordable=0,
                                converged=True, iterations=0, objective=0.)

    def _features(self, people, normal_fare):
        normal_fare = _finite(normal_fare, "normal_fare", .01)
        x = np.zeros((len(people), len(self.mean)))
        budgets, eligible = [], []
        for i, person in enumerate(people):
            segment = person.get("segment")
            if segment not in self.segment_index:
                raise ValueError(f"Unknown customer segment: {segment}")
            budget = _finite(person.get("base_fare_budget"), "base_fare_budget", 0)
            flex = _finite(person.get("flexibility_days", 0), "flexibility_days", 0)
            x[i, 0] = 1.
            x[i, 2] = np.clip(math.log(max(.02, budget / normal_fare)), -4., 4.)
            x[i, 3] = min(2., flex / 7.)
            x[i, 4 + self.segment_index[segment]] = 1.
            budgets.append(budget)
            eligible.append(bool(person.get("eligible", True)))
        return x, np.asarray(budgets), np.asarray(eligible, dtype=bool)

    @staticmethod
    def _logits(parameters, features, ratios):
        return features @ parameters - _softplus(parameters[1]) * ratios

    def fit(self, rows):
        """Refit from all search observations. Holdout observations must not enter.

        bought means submitted purchase intent, including subsequently rationed
        requests. A person who was never shown a purchasable offer is not a zero.
        A true budget-infeasible quote has deterministic probability zero and is
        recorded, but supplies no extra slope evidence.
        """
        rows = list(rows)
        valid, clusters = [], defaultdict(list)
        ineligible = unaffordable = 0
        for index, row in enumerate(rows):
            person = row["person"]
            customer_id = person.get("customer_id")
            if not isinstance(customer_id, str) or not customer_id:
                raise ValueError("customer_id required for cluster-aware learning")
            price = _finite(row["price"], "price", 0)
            normal = _finite(row["normal_fare"], "normal_fare", .01)
            bought = row["bought"]
            if bought not in (True, False, 0, 1):
                raise ValueError("bought must be binary")
            weight = _finite(row.get("sample_weight", 1.), "sample_weight", 0)
            feature, budgets, eligibility = self._features([person], normal)
            if not eligibility[0]:
                if bought:
                    raise ValueError("Ineligible customer cannot buy")
                ineligible += 1
                continue
            if price > budgets[0] + 1e-9:
                if bought:
                    raise ValueError("Purchase exceeds base-fare budget")
                unaffordable += 1
                continue
            if not weight:
                continue
            clusters[customer_id].append(len(valid))
            valid.append((feature[0], price / normal, float(bought), weight))
        self.mean = self.prior_mean.copy()
        self.covariance = np.diag(self.prior_sd ** 2)
        self.diagnostics = dict(observations=len(rows), unique_personas=len(clusters),
                                likelihood_rows=len(valid), effective_likelihood_mass=0.,
                                ineligible=ineligible, unaffordable=unaffordable,
                                converged=True, iterations=0, objective=0.)
        if not valid:
            return self
        x = np.stack([r[0] for r in valid])
        ratios = np.array([r[1] for r in valid])
        y = np.array([r[2] for r in valid])
        raw_weights = np.array([r[3] for r in valid])
        # Preserve post-stratification relative cluster weights, capped at one
        # effective observation per unique person. Duplicate trials add no mass.
        cluster_means = {key: float(raw_weights[indices].mean()) for key, indices in clusters.items()}
        largest_mean = max(cluster_means.values())
        weights = np.zeros(len(valid))
        for key, indices in clusters.items():
            power = cluster_means[key] / largest_mean
            weights[indices] = power * raw_weights[indices] / raw_weights[indices].sum()
        self.diagnostics["effective_likelihood_mass"] = float(weights.sum())

        def objective(theta):
            z = self._logits(theta, x, ratios)
            return float(np.sum(weights * (np.logaddexp(0., z) - y * z))
                         + .5 * np.sum(self.precision * (theta - self.prior_mean) ** 2))

        theta = self.mean.copy()
        converged = False
        for iteration in range(100):
            z = self._logits(theta, x, ratios)
            q = _sigmoid(z)
            jacobian = x.copy()
            jacobian[:, 1] = -_sigmoid(theta[1]) * ratios
            gradient = jacobian.T @ (weights * (q - y)) + self.precision * (theta - self.prior_mean)
            hessian = jacobian.T @ ((weights * q * (1. - q))[:, None] * jacobian) + np.diag(self.precision)
            step = np.linalg.solve(hessian, gradient)
            old = objective(theta)
            scale = 1.
            while scale > 1e-8:
                candidate = theta - scale * step
                if objective(candidate) <= old - 1e-4 * scale * float(gradient @ step):
                    break
                scale *= .5
            theta -= scale * step
            if np.max(np.abs(scale * step)) < 1e-7:
                converged = True
                break
        self.mean = theta
        z = self._logits(theta, x, ratios)
        q = _sigmoid(z)
        jacobian = x.copy()
        slope_derivative = float(_sigmoid(theta[1]))
        jacobian[:, 1] = -slope_derivative * ratios
        hessian = jacobian.T @ ((weights * q * (1. - q))[:, None] * jacobian) + np.diag(self.precision)
        hessian[1, 1] += float(np.sum(weights * (q - y) * -ratios
                                       * slope_derivative * (1. - slope_derivative)))
        eigenvalues, eigenvectors = np.linalg.eigh(hessian)
        # Numerical positive-definiteness guard for a local approximate posterior.
        self.covariance = (eigenvectors * (1. / np.maximum(eigenvalues, 1e-5))) @ eigenvectors.T
        self.diagnostics.update(converged=converged, iterations=iteration + 1, objective=objective(theta))
        return self

    def predict(self, people, price, normal_fare, *, draw=None):
        price = _finite(price, "price", 0)
        normal_fare = _finite(normal_fare, "normal_fare", .01)
        x, budgets, eligible = self._features(people, normal_fare)
        parameters = self.mean if draw is None else np.asarray(draw, dtype=float)
        if parameters.shape != self.mean.shape or not np.all(np.isfinite(parameters)):
            raise ValueError("Invalid posterior draw")
        probabilities = _sigmoid(self._logits(parameters, x, price / normal_fare))
        return np.where(eligible & (price <= budgets + 1e-9), probabilities, 0.)

    def sample(self, rng):
        """One joint parameter draw, shared by all prices and people in this round."""
        return rng.multivariate_normal(self.mean, self.covariance, check_valid="raise")

    def summary(self):
        return {
            "version": VERSION,
            "posterior": "cluster-tempered Laplace approximation",
            "segments": self.segments,
            "map_parameters": self.mean.tolist(),
            "posterior_covariance": self.covariance.tolist(),
            "map_price_sensitivity": float(_softplus(self.mean[1])),
            **self.diagnostics,
            "limitations": [
                "Synthetic choice response, not calibrated human demand.",
                "Repeated choices are tempered by persona; the posterior is not an exact independent-observation posterior.",
                "Gaussian local approximation and proper priors remain influential for small panels.",
                "Budget and route/date infeasibility are deterministic constraints, not learned willingness to pay.",
            ],
        }


def recommend(model, people, normal_fare, quota, rng, *, draw=True,
              revenue_fraction=.95, candidate_prices=None):
    """Numerically optimize a sampled curve, or select a final tested candidate.

    Search maximizes revenue under ONE jointly sampled parameter vector. Final
    choice averages posterior curves, then maximizes buyers subject to the
    configurable revenue fraction. Candidate grids are only cheap arithmetic;
    only the returned price needs new customer calls. They are not probe scripts.
    """
    if not people:
        raise ValueError("A nonempty customer panel is required")
    if isinstance(quota, bool) or not isinstance(quota, (int, np.integer)) or quota < 0:
        raise ValueError("quota must be a nonnegative integer")
    fraction = _finite(revenue_fraction, "revenue_fraction", .01)
    if fraction > 1:
        raise ValueError("revenue_fraction must be at most one")
    cap = fare_cap(normal_fare)
    population_weights = np.array([_finite(p.get("population_weight", 1. / len(people)),
                                                   "population_weight", 0) for p in people])
    if population_weights.sum() <= 0:
        raise ValueError("Population weights must have positive mass")
    population_weights /= population_weights.sum()
    if candidate_prices is None:
        # The affordable-budget discontinuities are real known constraints and
        # are included alongside a bounded numerical integration grid.
        prices = {round(float(p), 2) for p in np.linspace(0., cap, 201)}
        prices.update(math.floor(p["base_fare_budget"] * 100) / 100
                      for p in people if 0 <= p["base_fare_budget"] <= cap)
    else:
        prices = set()
        for p in candidate_prices:
            p = _finite(p, "candidate price", 0)
            if p > cap + 1e-9 or abs(p * 100 - round(p * 100)) > 1e-6:
                raise ValueError("Candidate price is outside cap or not in cents")
            prices.add(round(p, 2))
        if not prices:
            raise ValueError("At least one candidate price is required")
    prices = sorted(prices)
    parameters = [model.sample(rng) for _ in range(1 if draw else 48)]
    curve = []
    for price in prices:
        probabilities = np.array([model.predict(people, price, normal_fare, draw=theta)
                                  for theta in parameters])
        mixture_probabilities = probabilities @ population_weights
        sales = _binomial_capacity(mixture_probabilities, len(people), int(quota))
        revenues = price * sales
        curve.append({
            "price": price,
            "expected_buyers": float(np.mean(sales)),
            "expected_member_revenue": float(np.mean(revenues)),
            "purchase_probability": float(np.mean(mixture_probabilities)),
            "revenue_low": float(np.quantile(revenues, .1)),
            "revenue_high": float(np.quantile(revenues, .9)),
        })
    best = max(curve, key=lambda row: (row["expected_member_revenue"], row["price"]))
    if draw or best["expected_member_revenue"] <= 0:
        chosen = best
    else:
        acceptable = [row for row in curve
                      if row["expected_member_revenue"] + 1e-9 >= fraction * best["expected_member_revenue"]]
        chosen = max(acceptable, key=lambda row: (row["expected_buyers"], row["expected_member_revenue"], row["price"]))
    return {
        **chosen, "cap": cap, "cap_ratio": CAP_RATIO, "curve": curve,
        "selection_kind": "thompson_joint_posterior_draw" if draw else "posterior_mean_revenue_volume_rule",
        "candidate_scope": "tested_prices" if candidate_prices is not None else "bounded_numerical_grid",
        "selection_parameters": parameters[0].tolist() if draw else None,
        "revenue_fraction": fraction, "best_expected_member_revenue": best["expected_member_revenue"],
        "positive_expected_revenue": best["expected_member_revenue"] > 0,
        "target_customers": len(people), "quota": int(quota),
        "capacity_model": "exact Binomial capacity expectation for iid weighted target cohort",
        "uncertainty_kind": "model mean-revenue percentiles, not realized-revenue or validated human intervals",
        "posterior": model.summary(),
    }
