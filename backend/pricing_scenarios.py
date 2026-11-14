"""Explicit synthetic price stress inputs; never a target fare or demand label.

The production learner, prompts, NHPP and adoption rules are unchanged. These
named scenarios hold an original flight's inventory/forecast quota fixed while
assuming a lower normal quote and scaling the private simulated ticket wallet.
"""
from __future__ import annotations

import copy
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json

from .fare_policy import member_fare_cap
from llm_agent.weighted_population import population, DEFAULT_PROFILE

VERSION = 'zero-fare-stress-v1'
SCENARIOS = {
    'low_fare_55': {'flight_id': 'SYN-00017', 'forecast_day': 7, 'normal_base_fare': 55},
    'low_fare_60': {'flight_id': 'DEMO-HKG-OKA-20270515', 'forecast_day': 14, 'normal_base_fare': 60},
    'low_fare_65': {'flight_id': 'DEMO-HKG-NGO-20270515', 'forecast_day': 7, 'normal_base_fare': 65},
}
BUDGET_MULTIPLIER = 0.10
DISCLAIMER = (
    'Constructed low-fare stress scenario, not observed HK Express prices or budgets. '
    'The original flight inventory and NHPP quota are held fixed; NHPP is not '
    'reforecast for the assumed normal fare. A zero promotional quote does not '
    'override the independent revenue-adoption decision.'
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def validate_scenario_request(config):
    """Only the three declared inputs are accepted, tied to one flight/round."""
    name = config.get('demo_scenario')
    if name is None:
        return None
    if not isinstance(name, str) or name not in SCENARIOS:
        raise ValueError('demo_scenario must be low_fare_55, low_fare_60 or low_fare_65')
    definition = SCENARIOS[name]
    day = config.get('forecast_day', 28)
    if (config.get('flight_id') != definition['flight_id'] or isinstance(day, bool)
            or day != definition['forecast_day']):
        raise ValueError(f"demo_scenario {name} requires {definition['flight_id']} at D{definition['forecast_day']}")
    return {'id': name, 'version': VERSION, **definition,
            'budget_multiplier': BUDGET_MULTIPLIER}


def apply_pricing_scenario(config, source_scope):
    """Copy a declared what-if scope, preserving every original scope field."""
    definition = validate_scenario_request(config)
    if definition is None:
        return source_scope
    if ('scenario' in source_scope or source_scope.get('flight_id') != definition['flight_id']
            or source_scope.get('as_of_day') != definition['forecast_day']):
        raise ValueError('Scenario source must be the original matching flight scope')
    original = copy.deepcopy({key: value for key, value in source_scope.items() if key != 'history'})
    selected = copy.deepcopy(source_scope)
    normal = definition['normal_base_fare']
    cap = member_fare_cap(normal)
    scenario = {
        **definition, 'label': f'Constructed low-fare scenario · HK${normal} normal fare',
        'source_scope': original, 'source_scope_sha256': _digest(original),
        'definition_sha256': _digest(definition), 'disclaimer': DISCLAIMER,
    }
    selected.update(normal_base_fare=normal, initial_member_fare=cap, member_fare_cap=cap,
                    initial_fare_source='declared_scenario_normal_fare_x_member_cap',
                    scenario=scenario)
    return selected


def population_for_config(config, count, seed, scope, *, factory=None):
    """Change only scenario-private wallets/context before any price is shown."""
    definition = validate_scenario_request(config)
    factory = population if factory is None else factory
    people = factory(count, seed, weights=config.get('weights'), scope=scope,
                     profile=config.get('profile', DEFAULT_PROFILE))
    if definition is None:
        return people
    multiplier = Decimal(str(definition['budget_multiplier']))
    for person in people:
        original_budget = person['base_fare_budget']
        person['base_fare_budget'] = max(0, int((Decimal(str(original_budget)) * multiplier)
                                              .to_integral_value(rounding=ROUND_FLOOR)))
        person['pricing_scenario'] = {
            'id': definition['id'], 'version': VERSION,
            'budget_multiplier': definition['budget_multiplier'],
            'source_base_fare_budget': original_budget,
        }
        person['source'] = 'constructed_low_fare_stress_scenario'
        person['motivation_context'] += (
            ' This constructed low-spend scenario gives you the stated basic-fare '
            'budget; it is your available ticket money, not a suggested price or decision.'
        )
    return people
