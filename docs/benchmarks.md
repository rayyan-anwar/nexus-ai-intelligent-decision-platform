# Benchmarks: native accelerator vs NumPy fallback

These numbers are from **one run on one machine** (a single-CPU Linux sandbox) and will differ on yours. Reproduce with `make accel && make bench`.

The C++ library provides two kernels used by data profiling, data-quality checks and drift analysis:

* `column_stats`: one pass for finite/NaN/infinite counts plus min, max, mean and standard deviation (Welford).
* `bin_counts`: histogram counts for explicit bin edges (used for PSI).

| kernel | n | NumPy fallback (best ms) | native (best ms) | speed-up (best) |
|---|---:|---:|---:|---:|
| column_stats | 10,000 | 0.10 | 0.12 | 0.82x |
| bin_counts | 10,000 | 0.30 | 0.24 | 1.24x |
| column_stats | 1,000,000 | 19.10 | 11.51 | 1.66x |
| bin_counts | 1,000,000 | 32.96 | 18.29 | 1.80x |
| column_stats | 10,000,000 | 168.20 | 118.83 | 1.42x |
| bin_counts | 10,000,000 | 316.07 | 190.77 | 1.66x |

(Header line from the same run: Python 3.12.3, NumPy 2.4.4, x86_64, 1 CPU. Best of 7 repetitions; arrays contain 1% NaN.)

## Reading the results

* At one million values and above the native kernels were about **1.4x to 1.8x faster**. That is a real but modest gain.
* For 10,000 values `column_stats` was **slower** (0.82x): the fixed cost of calling through `ctypes` outweighs the work.
* The application's default limits (10 MB upload, 200,000 rows) are well below the sizes where the gain appears, and model training dominates runtime by orders of magnitude. **The accelerator therefore does not materially change the experience for the default workload.** It stays optional and disabled-safe: the Python fallback is always used when the library is absent or `NEXUS_DISABLE_ACCEL=1`.
* Correctness is covered by equivalence tests that compare native and fallback results exactly (counts) or to 7 decimals (moments), plus C++ tests that run under AddressSanitizer and UBSan.

Not measured: multi-core behaviour, other CPUs/compilers, memory use, or end-to-end request latency.
