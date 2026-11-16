/*
 * Deterministic host math for the JavaScript hook layer.
 *
 * One portable, fdlibm-derived implementation of every transcendental that JavaScript's Math
 * object (and the `**` operator) exposes, so hook-layer numerics replay byte for byte across
 * platforms, toolchains and C libraries instead of depending on the platform libm.
 *
 * Contract:
 *  - Results depend only on the IEEE-754 binary64 inputs. The implementation uses integer bit
 *    manipulation and IEEE add/sub/mul/div/sqrt only (all correctly rounded), and its
 *    translation unit is compiled with floating-point contraction disabled, so no FMA fusing
 *    can change a result. It requires binary64 evaluation (FLT_EVAL_METHOD == 0: SSE2 on x86).
 *  - Every NaN result is the single canonical quiet NaN (bits 0x7ff8000000000000), so even NaN
 *    payloads/signs do not depend on the CPU.
 *  - Accuracy is fdlibm's (< 1 ulp); these are not correctly rounded and need not agree with a
 *    given platform libm. The point is identity across hosts, not a better error bound.
 *  - pow/hypot follow C99 special cases; JavaScript-specific special cases (for example
 *    1 ** Infinity is NaN) stay in the engine wrapper.
 *
 * QuickJS is compiled with its libm transcendental names redirected here
 * (cmake/TrechDeterministicMath.h), and the C++ host uses these functions directly.
 */
#ifndef TRECH_JS_DETERMINISTIC_MATH_H
#define TRECH_JS_DETERMINISTIC_MATH_H

#ifdef __cplusplus
extern "C" {
#endif

/* Implementation identity recorded with runs that rely on host math. */
#define TRECH_DMATH_ID "trech-dmath-fdlibm-5.3/1"
const char* trech_dmath_id(void);

double trech_dmath_sin(double x);
double trech_dmath_cos(double x);
double trech_dmath_tan(double x);
double trech_dmath_asin(double x);
double trech_dmath_acos(double x);
double trech_dmath_atan(double x);
double trech_dmath_atan2(double y, double x);
double trech_dmath_exp(double x);
double trech_dmath_expm1(double x);
double trech_dmath_log(double x);
double trech_dmath_log1p(double x);
double trech_dmath_log2(double x);
double trech_dmath_log10(double x);
double trech_dmath_pow(double x, double y);
double trech_dmath_sinh(double x);
double trech_dmath_cosh(double x);
double trech_dmath_tanh(double x);
double trech_dmath_asinh(double x);
double trech_dmath_acosh(double x);
double trech_dmath_atanh(double x);
double trech_dmath_cbrt(double x);
double trech_dmath_hypot(double x, double y);

#ifdef __cplusplus
}
#endif

#endif /* TRECH_JS_DETERMINISTIC_MATH_H */
