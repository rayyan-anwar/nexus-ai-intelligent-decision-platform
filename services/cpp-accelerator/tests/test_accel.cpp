// Minimal dependency-free C++ tests for the accelerator kernels.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <vector>

extern "C" {
int nexus_column_stats(const double*, int64_t, int64_t*, double*);
int nexus_bin_counts(const double*, int64_t, const double*, int64_t, int64_t*);
}

static int failures = 0;
#define CHECK(cond)                                                       \
    do {                                                                  \
        if (!(cond)) {                                                    \
            std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);   \
            ++failures;                                                   \
        }                                                                 \
    } while (0)

int main() {
    {  // basic moments with NaN and inf
        const double x[] = {1.0, 2.0, 3.0, 4.0, NAN, INFINITY, -INFINITY};
        int64_t c[3];
        double v[4];
        CHECK(nexus_column_stats(x, 7, c, v) == 0);
        CHECK(c[0] == 4 && c[1] == 1 && c[2] == 2);
        CHECK(v[0] == 1.0 && v[1] == 4.0);
        CHECK(std::fabs(v[2] - 2.5) < 1e-12);
        CHECK(std::fabs(v[3] - 5.0) < 1e-12);  // sum of squared deviations
    }
    {  // all invalid
        const double x[] = {NAN, NAN};
        int64_t c[3];
        double v[4];
        CHECK(nexus_column_stats(x, 2, c, v) == 0);
        CHECK(c[0] == 0 && c[1] == 2);
        CHECK(std::isnan(v[0]) && std::isnan(v[2]));
    }
    {  // bad arguments
        int64_t c[3];
        double v[4];
        CHECK(nexus_column_stats(nullptr, 5, c, v) == 1);
        CHECK(nexus_column_stats(nullptr, 0, c, v) == 0);
    }
    {  // histogram semantics: bin = number of edges <= x
        const double edges[] = {0.0, 10.0};
        const double x[] = {-1.0, 0.0, 5.0, 10.0, 11.0, NAN, INFINITY, -INFINITY};
        int64_t out[3];
        CHECK(nexus_bin_counts(x, 8, edges, 2, out) == 0);
        CHECK(out[0] == 2);  // -1, -inf
        CHECK(out[1] == 2);  // 0, 5
        CHECK(out[2] == 3);  // 10, 11, +inf
    }
    {  // unsorted edges rejected; empty edges -> single bin
        const double bad[] = {2.0, 1.0};
        const double x[] = {1.0};
        int64_t out[3];
        CHECK(nexus_bin_counts(x, 1, bad, 2, out) == 2);
        int64_t one[1];
        CHECK(nexus_bin_counts(x, 1, nullptr, 0, one) == 0 && one[0] == 1);
    }
    if (failures == 0) std::printf("all C++ tests passed\n");
    return failures == 0 ? 0 : 1;
}
