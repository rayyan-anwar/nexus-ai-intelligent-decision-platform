import unittest

import numpy as np

from helpers import BACKEND  # noqa: F401
from app.ml import accel

NATIVE = accel.native_available()


class FallbackTests(unittest.TestCase):
    """These run everywhere (the fallback is always available)."""

    def test_column_stats_python(self):
        st = accel.column_stats([1, 2, 3, 4, np.nan, np.inf, -np.inf], force_python=True)
        self.assertEqual((st["valid"], st["nan"], st["inf"]), (4, 1, 2))
        self.assertAlmostEqual(st["mean"], 2.5)
        self.assertAlmostEqual(st["std"], np.std([1, 2, 3, 4], ddof=1))

    def test_empty_and_all_nan(self):
        st = accel.column_stats([], force_python=True)
        self.assertEqual(st["valid"], 0)
        self.assertTrue(np.isnan(st["mean"]))
        self.assertEqual(accel.bin_counts([], [0.0], force_python=True).tolist(), [0, 0])

    def test_bin_counts_semantics(self):
        out = accel.bin_counts([-1, 0, 5, 10, 11, np.nan, np.inf, -np.inf], [0.0, 10.0], force_python=True)
        self.assertEqual(out.tolist(), [2, 2, 3])

    def test_unsorted_edges_rejected(self):
        with self.assertRaises(ValueError):
            accel.bin_counts([1.0], [2.0, 1.0])


@unittest.skipUnless(NATIVE, "native library not built (run `make -C services/cpp-accelerator`)")
class NativeEquivalenceTests(unittest.TestCase):
    def test_column_stats_matches_fallback(self):
        rng = np.random.default_rng(1)
        for n in (1, 2, 17, 10_000):
            x = rng.normal(5, 3, n)
            x[:: max(n // 7, 1)] = np.nan
            if n > 5:
                x[2] = np.inf
                x[3] = -np.inf
            a, b = accel.column_stats(x), accel.column_stats(x, force_python=True)
            for key in ("valid", "nan", "inf"):
                self.assertEqual(a[key], b[key])
            for key in ("min", "max", "mean", "std"):
                if np.isnan(b[key]):
                    self.assertTrue(np.isnan(a[key]))
                else:
                    self.assertAlmostEqual(a[key], b[key], places=7)

    def test_bin_counts_matches_fallback(self):
        rng = np.random.default_rng(2)
        x = rng.normal(size=50_000)
        x[::13] = np.nan
        x[5], x[6] = np.inf, -np.inf
        for edges in (np.quantile(x[~np.isnan(x)], np.linspace(0, 1, 11)[1:-1]), np.array([0.0]), np.array([])):
            np.testing.assert_array_equal(accel.bin_counts(x, edges), accel.bin_counts(x, edges, force_python=True))

    def test_integer_input_and_non_contiguous_views(self):
        x = np.arange(100)[::2]
        self.assertEqual(accel.column_stats(x)["valid"], 50)
        self.assertEqual(accel.bin_counts(x, [10, 20]).tolist(), accel.bin_counts(x, [10, 20], force_python=True).tolist())


if __name__ == "__main__":
    unittest.main()
