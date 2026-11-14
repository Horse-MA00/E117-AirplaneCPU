"""Public-feature purchase-response learning and whole-HKD Thompson selection.

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

from .fare_policy import member_fare_cap as _member_fare_cap

VERSION = "public-member-response-v1"
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


def whole_price(value, name="price"):
    value = _finite(value, name, 0)
    if not value.is_integer():
        raise ValueError(f"{name} must be a whole HKD amount")
    return int(value)


def fare_cap(normal_fare):
    """Shared whole-HKD cap after converting any raw source to its quote."""
    normal_fare = _finite(normal_fare, "normal_fare", .01)
    return _member_fare_cap(normal_fare)


def learner_view(person):
    """Project only ex-ante, declared public attributes to the price learner.

    Private budget, urgency, value context and simulator eligibility must not
    decide a price or become numerical willingness-to-pay labels. The clearing
    environment can still use those private constraints to execute choices.
    """
    customer_id, segment = person.get("customer_id"), person.get("segment")
    if not isinstance(customer_id, str) or not customer_id:
        raise ValueError("customer_id required for cluster-aware learning")
    if not isinstance(segment, str) or not segment:
        raise ValueError("A public customer segment is required")
    return {"customer_id": customer_id, "segment": segment,
            "flexibility_days": _finite(person.get("flexibility_days", 0), "flexibility_days", 0),
            "population_weight": _finite(person.get("population_weight", 1.), "population_weight", 0)}


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
    """Aggregate response from public context and observed purchase intentions.

    logit(q) = intercept + segment + flex_coef*log1p(flex)/log1p(28)
               - softplus(price_slope_raw)*price/normal_fare.

    Hidden affordability and private travel motivation are marginalized by
    learning observed yes/no choices. No private-budget mask is available to
    this learner. All exposed members' decisions, including forced insufficient-
    budget declines, are valid aggregate conversion observations. Availability
    failures must be excluded by the experiment's exposure design, not inferred
    here from private fields.
    """

    def __init__(self, segment_ids):
        self.segments = list(segment_ids)
        if (not self.segments or len(set(self.segments)) != len(self.segments)
                or any(not isinstance(s, str) or not s for s in self.segments)):
            raise ValueError("Unique nonempty segment identifiers required")
        self.segment_index = {segment: i for i, segment in enumerate(self.segments)}
        size = 3 + len(self.segments)
        # Proper weak priors also prevent separation/all-buy/all-decline divergence.
        self.prior_mean = np.zeros(size)
        self.prior_mean[:3] = [1., math.log(math.expm1(3.)), 0.]
        self.prior_sd = np.array([2., 2., .7] + [.8] * len(self.segments))
        self.precision = 1. / self.prior_sd ** 2
        self.mean = self.prior_mean.copy()
        self.covariance = np.diag(self.prior_sd ** 2)
        self.diagnostics = dict(observations=0, unique_personas=0, likelihood_rows=0,
                                effective_likelihood_mass=0., duplicate_exposures=0,
                                converged=True, iterations=0, objective=0.)

    def _features(self, people, normal_fare):
        _finite(normal_fare, "normal_fare", .01)
        x = np.zeros((len(people), len(self.mean)))
        for i, supplied in enumerate(people):
            person = learner_view(supplied)
            segment = person["segment"]
            if segment not in self.segment_index:
                raise ValueError(f"Unknown customer segment: {segment}")
            x[i, 0] = 1.
            # Smooth scale preserves differences between a two-week and a
            # six-week declared window; an annual cap guards malformed inputs.
            x[i, 2] = math.log1p(min(365., person["flexibility_days"])) / math.log1p(28.)
            x[i, 3 + self.segment_index[segment]] = 1.
        return x

    @staticmethod
    def _logits(parameters, features, ratios):
        return features @ parameters - _softplus(parameters[1]) * ratios

    def fit(self, rows):
        """Refit from unique search exposures; validation data are rejected.

        One persona can see paired counterfactual quotes but supplies at most
        one unit of likelihood power in total. Exact duplicate quotes are
        deduplicated, and inconsistent labels for an identical quote rejected.
        No private constraint is used to remove negative choices from learning.
        """
        rows = list(rows)
        valid, clusters, seen = [], defaultdict(list), {}
        duplicates = 0
        for row in rows:
            if row.get("phase", "search") != "search":
                raise ValueError("Only search observations may fit the response model")
            person = learner_view(row["person"])
            customer_id = person["customer_id"]
            price = whole_price(row["price"])
            normal = _finite(row["normal_fare"], "normal_fare", .01)
            bought = row["bought"]
            if bought not in (True, False, 0, 1):
                raise ValueError("bought must be binary")
            weight = _finite(row.get("sample_weight", 1.), "sample_weight", 0)
            feature = self._features([person], normal)
            key = (customer_id, price, normal)
            value = (person, bool(bought), weight)
            if key in seen:
                if seen[key] != value:
                    raise ValueError("Conflicting observation for the same persona and quote")
                duplicates += 1
                continue
            seen[key] = value
            if not weight:
                continue
            clusters[customer_id].append(len(valid))
            valid.append((feature[0], price / normal, float(bought), weight))
        self.mean = self.prior_mean.copy()
        self.covariance = np.diag(self.prior_sd ** 2)
        self.diagnostics = dict(observations=len(rows), unique_personas=len(clusters),
                                likelihood_rows=len(valid), effective_likelihood_mass=0.,
                                duplicate_exposures=duplicates,
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
        price = whole_price(price)
        normal_fare = _finite(normal_fare, "normal_fare", .01)
        x = self._features(people, normal_fare)
        parameters = self.mean if draw is None else np.asarray(draw, dtype=float)
        if parameters.shape != self.mean.shape or not np.all(np.isfinite(parameters)):
            raise ValueError("Invalid posterior draw")
        probabilities = _sigmoid(self._logits(parameters, x, price / normal_fare))
        return probabilities

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
            "observable_features": ["segment", "flexibility_days"],
            "private_constraints_used": False,
            **self.diagnostics,
            "limitations": [
                "Synthetic choice response, not calibrated human demand.",
                "Repeated choices are tempered by persona; the posterior is not an exact independent-observation posterior.",
                "Gaussian local approximation and proper priors remain influential for small panels.",
                "Private budgets and simulator eligibility are not features or hard probability gates; response averages over unobserved constraints.",
                "Public segment and declared flexibility are assumed available; no private persona text becomes a willingness-to-pay target.",
            ],
        }


def recommend(model, people, normal_fare, quota, rng, *, draw=True,
              revenue_fraction=.95, candidate_prices=None, target_customers=None):
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
    public_people = [learner_view(person) for person in people]
    population_weights = np.array([person["population_weight"] for person in public_people])
    if population_weights.sum() <= 0:
        raise ValueError("Population weights must have positive mass")
    population_weights /= population_weights.sum()
    target_customers = len(public_people) if target_customers is None else target_customers
    if isinstance(target_customers, bool) or not isinstance(target_customers, (int, np.integer)) or not 1 <= target_customers <= 10000:
        raise ValueError("target_customers must be an integer in 1..10000")
    if candidate_prices is None:
        # Numerical evaluation only; it does not call customers at every price.
        # No persona budget or private value determines this integer domain.
        prices = range(cap + 1)
    else:
        prices = {whole_price(p, "candidate price") for p in candidate_prices}
        if not prices or max(prices) > cap:
            raise ValueError("Candidate price must be within the integer 80% cap")
    prices = sorted(prices)
    parameters = [model.sample(rng) for _ in range(1 if draw else 48)]
    curve = []
    # A real response model shares its feature matrix across every price and
    # posterior draw. Bounded blocks avoid allocating prices x draws x support
    # for the entire domain. Preserve predict-only wrappers/test doubles.
    fast_path = isinstance(model, PurchasePosterior) and type(model).predict is PurchasePosterior.predict
    if fast_path:
        features = model._features(public_people, normal_fare)
        draws = np.asarray(parameters, dtype=float)
        if draws.shape != (len(parameters), len(model.mean)) or not np.all(np.isfinite(draws)):
            raise ValueError("Invalid posterior draw")
        intercepts = draws @ features.T
        slopes = _softplus(draws[:, 1])
    for start in range(0, len(prices), 64):
        block = prices[start:start+64]
        if fast_path:
            ratios = np.asarray(block, dtype=float) / normal_fare
            logits = intercepts[None, :, :] - ratios[:, None, None] * slopes[None, :, None]
            probabilities = _sigmoid(logits)
            mixture = probabilities @ population_weights
        else:
            mixture = np.array([[np.asarray(model.predict(public_people, price, normal_fare, draw=theta))
                                 @ population_weights for theta in parameters] for price in block])
        sales = _binomial_capacity(mixture.reshape(-1), int(target_customers), int(quota)).reshape(mixture.shape)
        revenues = np.asarray(block)[:, None] * sales
        means = np.mean(revenues, axis=1)
        bounds = np.quantile(revenues, [.1, .9], axis=1)
        for index, price in enumerate(block):
            curve.append({
                "price": price,
                "expected_buyers": float(np.mean(sales[index])),
                "expected_member_revenue": float(means[index]),
                "purchase_probability": float(np.mean(mixture[index])),
                "revenue_low": float(bounds[0, index]),
                "revenue_high": float(bounds[1, index]),
            })
    best = max(curve, key=lambda row: (row["expected_member_revenue"], row["price"]))
    most_buyers = max(curve, key=lambda row: (row["expected_buyers"], row["expected_member_revenue"], row["price"]))
    if draw or best["expected_member_revenue"] <= 0:
        chosen = best
    else:
        acceptable = [row for row in curve
                      if row["expected_member_revenue"] + 1e-9 >= fraction * best["expected_member_revenue"]]
        chosen = max(acceptable, key=lambda row: (row["expected_buyers"], row["expected_member_revenue"], row["price"]))
    return {
        **chosen, "cap": cap, "cap_ratio": CAP_RATIO, "curve": curve,
        "selection_kind": "thompson_joint_posterior_draw" if draw else "posterior_mean_revenue_volume_rule",
        "candidate_scope": "tested_prices" if candidate_prices is not None else "whole_hkd_domain",
        "selection_parameters": parameters[0].tolist() if draw else None,
        "revenue_fraction": fraction, "best_expected_member_revenue": best["expected_member_revenue"],
        "positive_expected_revenue": best["expected_member_revenue"] > 0,
        "target_customers": int(target_customers), "support_customers": len(public_people), "quota": int(quota),
        "best_revenue_candidate": dict(best), "most_buyers_candidate": dict(most_buyers),
        "private_constraints_used": False, "price_step_hkd": 1,
        "capacity_model": "exact Binomial capacity expectation for iid weighted target cohort",
        "uncertainty_kind": "model mean-revenue percentiles, not realized-revenue or validated human intervals",
        "posterior": model.summary(),
    }
