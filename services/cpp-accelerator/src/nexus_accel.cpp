// NEXUS AI native accelerator.
//
// Two single-purpose numeric kernels with a plain C ABI (loaded via ctypes):
//   nexus_column_stats - one pass over a float64 column: counts of finite / NaN / +-inf values
//                        plus min, max, mean and the sum of squared deviations (Welford).
//   nexus_bin_counts   - histogram with explicit ascending edges; bin index == number of edges <= x
//                        (identical to numpy.searchsorted(edges, x, side="right")). NaNs are skipped.
//
// Both mirror the pure-Python fallback in backend/app/ml/accel.py exactly.

#include <algorithm>
#include <cmath>
#include <cstdint>

extern "C" {

#if defined(_WIN32)
#define NEXUS_EXPORT __declspec(dllexport)
#else
#define NEXUS_EXPORT __attribute__((visibility("default")))
#endif

// counts_out[3] = {valid, nan, inf}; vals_out[4] = {min, max, mean, m2}
NEXUS_EXPORT int nexus_column_stats(const double* x, int64_t n, int64_t* counts_out, double* vals_out) {
    if ((x == nullptr && n > 0) || n < 0 || counts_out == nullptr || vals_out == nullptr) return 1;
    int64_t valid = 0, nan_count = 0, inf_count = 0;
    double mn = INFINITY, mx = -INFINITY, mean = 0.0, m2 = 0.0;
    for (int64_t i = 0; i < n; ++i) {
        const double v = x[i];
        if (std::isnan(v)) { ++nan_count; continue; }
        if (std::isinf(v)) { ++inf_count; continue; }
        ++valid;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
        const double delta = v - mean;
        mean += delta / static_cast<double>(valid);
        m2 += delta * (v - mean);
    }
    counts_out[0] = valid;
    counts_out[1] = nan_count;
    counts_out[2] = inf_count;
    if (valid == 0) {
        vals_out[0] = vals_out[1] = vals_out[2] = NAN;
        vals_out[3] = 0.0;
    } else {
        vals_out[0] = mn;
        vals_out[1] = mx;
        vals_out[2] = mean;
        vals_out[3] = m2;
    }
    return 0;
}

// counts_out must have n_edges + 1 slots (it is zeroed here).
NEXUS_EXPORT int nexus_bin_counts(const double* x, int64_t n, const double* edges, int64_t n_edges, int64_t* counts_out) {
    if ((x == nullptr && n > 0) || n < 0 || n_edges < 0 || (edges == nullptr && n_edges > 0) || counts_out == nullptr) return 1;
    for (int64_t i = 0; i <= n_edges; ++i) counts_out[i] = 0;
    for (int64_t i = 1; i < n_edges; ++i)
        if (edges[i] < edges[i - 1]) return 2;  // edges must be ascending
    for (int64_t i = 0; i < n; ++i) {
        const double v = x[i];
        if (std::isnan(v)) continue;
        const int64_t bin = std::upper_bound(edges, edges + n_edges, v) - edges;
        ++counts_out[bin];
    }
    return 0;
}

}  // extern "C"
