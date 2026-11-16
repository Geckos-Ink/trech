/*
 * Force-included into every QuickJS translation unit (see the top-level CMakeLists.txt) so the
 * vendored engine computes Math.* and the `**` operator with TRECH's deterministic host math
 * instead of the platform libm, without patching the QuickJS submodule.
 *
 * <math.h> is included first so its own declarations keep their libm names; the object-like
 * macros below then rename every later reference -- calls and the function pointers QuickJS
 * stores in its Math function table alike. Exact operations (sqrt, fabs, floor, ceil, trunc,
 * fmod, rint, ...) stay on libm: IEEE-754/C99 define their results bit for bit.
 */
#ifndef TRECH_QUICKJS_MATH_REDIRECT_H
#define TRECH_QUICKJS_MATH_REDIRECT_H

#include <math.h>

#include "trech/js/DeterministicMath.h"

#define sin trech_dmath_sin
#define cos trech_dmath_cos
#define tan trech_dmath_tan
#define asin trech_dmath_asin
#define acos trech_dmath_acos
#define atan trech_dmath_atan
#define atan2 trech_dmath_atan2
#define exp trech_dmath_exp
#define expm1 trech_dmath_expm1
#define log trech_dmath_log
#define log1p trech_dmath_log1p
#define log2 trech_dmath_log2
#define log10 trech_dmath_log10
#define pow trech_dmath_pow
#define sinh trech_dmath_sinh
#define cosh trech_dmath_cosh
#define tanh trech_dmath_tanh
#define asinh trech_dmath_asinh
#define acosh trech_dmath_acosh
#define atanh trech_dmath_atanh
#define cbrt trech_dmath_cbrt
#define hypot trech_dmath_hypot

#endif /* TRECH_QUICKJS_MATH_REDIRECT_H */
