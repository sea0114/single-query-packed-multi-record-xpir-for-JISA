"""Synthetic statistics tests only: never experimental observations."""
import importlib.util
from pathlib import Path
import unittest

script = Path(__file__).resolve().parents[1] / 'scripts/recompute_historical.py'
spec = importlib.util.spec_from_file_location('replay', script)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class HistoricalStatisticsTests(unittest.TestCase):
    def test_median_paired_ratio_does_not_imply_separate_median_order(self):
        result = replay.median_claim_evidence([100, 110, 120], [101, 109, 122])
        self.assertEqual(result['median_paired_ratio'], 1.01)
        self.assertEqual(result['packed_separate_median_ns'], 110)
        self.assertEqual(result['repeated_separate_median_ns'], 109)
        self.assertFalse(result['packed_separate_median_lower'])

    def test_even_medians_do_not_commute_with_nonlinear_reduction(self):
        result = replay.median_claim_evidence([100, 100], [100, 200])
        self.assertEqual(result['median_pair_reduction_relative_to_repeated'], .25)
        self.assertNotEqual(result['median_pair_reduction_relative_to_repeated'], result['transform_of_median_ratio'])

    def test_type7_percentiles(self):
        self.assertEqual(replay.quantile([0, 10, 20, 30], .25), 7.5)
        self.assertEqual(replay.quantile([0, 10, 20, 30], .975), 29.25)

    def test_diff_requires_exact_values(self):
        self.assertEqual(replay.differences({'a': [1.0, 2]}, {'a': [1, 2]}), [])
        self.assertEqual(len(replay.differences({'a': [1.0]}, {'a': [1.000000000000001]})), 1)

    def test_no_imputation_of_incomplete_pairs(self):
        with self.assertRaises(ValueError):
            replay.median_claim_evidence([100, 200], [110])


if __name__ == '__main__':
    unittest.main(verbosity=2)
