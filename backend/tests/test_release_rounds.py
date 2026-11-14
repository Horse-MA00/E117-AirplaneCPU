"""Release target applies before subtracting previously issued valid quota."""
import unittest
from backend.release_policy import release_budget


class ReleaseBudgetTests(unittest.TestCase):
    def test_fraction_is_total_target_before_carry_subtraction(self):
        result = release_budget(90, 30, 20, .5)
        self.assertEqual((result['target_quota'], result['new_allocation'], result['remaining_quota']), (30, 10, 30))
