"""Benchmark native vs NumPy fallback. Prints a Markdown table; run on your own hardware.

Usage: make bench   (from services/cpp-accelerator)
"""

import os
import platform
import statistics
import sys
import time

import numpy as np

from app.ml import accel

if not accel.native_available():
    sys.exit("Native library not built. Run `make` first.")


def best_of(fn, repeats=7):
    times = []
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t)
    return min(times), statistics.median(times)


def main():
    rng = np.random.default_rng(0)
    print(f"Python {platform.python_version()} | NumPy {np.__version__} | {platform.machine()} | cpus={os.cpu_count()}\n")
    print("| kernel | n | NumPy fallback (best ms) | native (best ms) | speed-up (best) |")
    print("|---|---:|---:|---:|---:|")
    for n in (10_000, 1_000_000, 10_000_000):
        x = rng.normal(size=n)
        x[:: max(n // 100, 1)] = np.nan
        edges = np.quantile(x[~np.isnan(x)], np.linspace(0, 1, 11)[1:-1])
        for name, f in (
            ("column_stats", lambda force: accel.column_stats(x, force_python=force)),
            ("bin_counts", lambda force: accel.bin_counts(x, edges, force_python=force)),
        ):
            py = best_of(lambda: f(True))[0]
            nat = best_of(lambda: f(False))[0]
            print(f"| {name} | {n:,} | {py * 1e3:.2f} | {nat * 1e3:.2f} | {py / nat:.2f}x |")


if __name__ == "__main__":
    main()
