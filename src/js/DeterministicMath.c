/*
 * Deterministic host math (see include/trech/js/DeterministicMath.h for the contract).
 *
 * Adapted from fdlibm 5.3 (http://www.netlib.org/fdlibm) and its FreeBSD msun / V8
 * (src/base/ieee754.cc) descendants:
 *
 * ====================================================
 * Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.
 *
 * Developed at SunSoft, a Sun Microsystems, Inc. business.
 * Permission to use, copy, modify, and distribute this
 * software is freely granted, provided that this notice
 * is preserved.
 * ====================================================
 *
 * Portions (log2, cbrt, log1p, cosh, sinh, the bit-access helpers) follow the FreeBSD and
 * V8 revisions: Copyright 2016 the V8 project authors (BSD-style license); FreeBSD msun
 * (BSD license). Modified for TRECH: portable bit access through memcpy, no signed-shift or
 * signed-overflow undefined behaviour, and one canonical NaN result.
 *
 * Every constant is written in decimal with its IEEE-754 words in a comment;
 * scripts/check_dmath_constants.py verifies the two spellings agree.
 *
 * This file must be compiled with floating-point contraction off (-ffp-contract=off) and
 * without fast-math: fused multiply-add would change rounding and break cross-host identity.
 */
#include "trech/js/DeterministicMath.h"

#include <float.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#if defined(FLT_EVAL_METHOD) && FLT_EVAL_METHOD != 0 && FLT_EVAL_METHOD != -1
#error "trech deterministic math needs binary64 evaluation (FLT_EVAL_METHOD == 0; use SSE2 on x86)"
#endif
#if defined(__FAST_MATH__)
#error "trech deterministic math must not be compiled with fast-math"
#endif

/* ---------------------------------------------------------------- bit access */

static inline uint64_t d2u(double d) {
  uint64_t u;
  memcpy(&u, &d, sizeof u);
  return u;
}
static inline double u2d(uint64_t u) {
  double d;
  memcpy(&d, &u, sizeof d);
  return d;
}
static inline int32_t high_word(double d) { return (int32_t)(uint32_t)(d2u(d) >> 32); }
static inline uint32_t low_word(double d) { return (uint32_t)d2u(d); }
static inline double from_words(uint32_t hi, uint32_t lo) {
  return u2d(((uint64_t)hi << 32) | lo);
}
static inline double with_high_word(double d, uint32_t hi) {
  return u2d((d2u(d) & 0x00000000FFFFFFFFull) | ((uint64_t)hi << 32));
}
static inline double with_low_word(double d, uint32_t lo) {
  return u2d((d2u(d) & 0xFFFFFFFF00000000ull) | lo);
}
/* k << 20 for a possibly negative exponent adjustment, without UB. */
static inline int32_t shl20(int32_t k) { return (int32_t)((uint32_t)k << 20); }

#define EXTRACT_WORDS(hi, lo, d) \
  do {                           \
    uint64_t b_ = d2u(d);        \
    (hi) = (int32_t)(b_ >> 32);  \
    (lo) = (uint32_t)b_;         \
  } while (0)

static const double one = 1.0, zero = 0.0, half = 0.5;
static const double huge = 1.0e300, tiny = 1.0e-300;

static double canonical(double r) { return r != r ? u2d(0x7ff8000000000000ull) : r; }

/* scalbn is exact (or exactly under/overflowing); implemented here so no libm call remains
 * besides sqrt/fabs/floor, which IEEE-754 and C99 define exactly. */
static double dm_scalbn(double x, int n) {
  static const double two54 = 1.80143985094819840000e+16;  /* 0x43500000, 0x00000000 */
  static const double twom54 = 5.55111512312578270212e-17; /* 0x3C900000, 0x00000000 */
  int32_t k, hx;
  uint32_t lx;
  EXTRACT_WORDS(hx, lx, x);
  k = (hx & 0x7ff00000) >> 20;
  if (k == 0) {                                   /* 0 or subnormal x */
    if ((lx | (hx & 0x7fffffff)) == 0) return x;  /* +-0 */
    x *= two54;
    hx = high_word(x);
    k = ((hx & 0x7ff00000) >> 20) - 54;
    if (n < -50000) return tiny * x; /* underflow */
  }
  if (k == 0x7ff) return x + x; /* NaN or Inf */
  if (n > 50000) return huge * copysign(huge, x);
  if (n < -50000) return tiny * copysign(tiny, x);
  k = k + n;
  if (k > 0x7fe) return huge * copysign(huge, x); /* overflow */
  if (k > 0) return with_high_word(x, (uint32_t)((hx & 0x800fffff) | (k << 20)));
  if (k <= -54) return tiny * copysign(tiny, x); /* underflow */
  k += 54;                                       /* subnormal result */
  x = with_high_word(x, (uint32_t)((hx & 0x800fffff) | (k << 20)));
  return x * twom54;
}

/* ------------------------------------------------------- argument reduction */

static const int32_t two_over_pi[] = {
    0xA2F983, 0x6E4E44, 0x1529FC, 0x2757D1, 0xF534DD, 0xC0DB62, 0x95993C, 0x439041, 0xFE5163,
    0xABDEBB, 0xC561B7, 0x246E3A, 0x424DD2, 0xE00649, 0x2EEA09, 0xD1921C, 0xFE1DEB, 0x1CB129,
    0xA73EE8, 0x8235F5, 0x2EBB44, 0x84E99C, 0x7026B4, 0x5F7E41, 0x3991D6, 0x398353, 0x39F49C,
    0x845F8B, 0xBDF928, 0x3B1FF8, 0x97FFDE, 0x05980F, 0xEF2F11, 0x8B5A0A, 0x6D1F6D, 0x367ECF,
    0x27CB09, 0xB74F46, 0x3F669E, 0x5FEA2D, 0x7527BA, 0xC7EBE5, 0xF17B3D, 0x0739F7, 0x8A5292,
    0xEA6BFB, 0x5FB11F, 0x8D5D08, 0x560330, 0x46FC7B, 0x6BABF0, 0xCFBC20, 0x9AF436, 0x1DA9E3,
    0x91615E, 0xE61B08, 0x659985, 0x5F14A0, 0x68408D, 0xFFD880, 0x4D7327, 0x310606, 0x1556CA,
    0x73A8C9, 0x60E27B, 0xC08C6B,
};

static const int32_t npio2_hw[] = {
    0x3FF921FB, 0x400921FB, 0x4012D97C, 0x401921FB, 0x401F6A7A, 0x4022D97C, 0x4025FDBB,
    0x402921FB, 0x402C463A, 0x402F6A7A, 0x4031475C, 0x4032D97C, 0x40346B9C, 0x4035FDBB,
    0x40378FDB, 0x403921FB, 0x403AB41B, 0x403C463A, 0x403DD85A, 0x403F6A7A, 0x40407E4C,
    0x4041475C, 0x4042106C, 0x4042D97C, 0x4043A28C, 0x40446B9C, 0x404534AC, 0x4045FDBB,
    0x4046C6CB, 0x40478FDB, 0x404858EB, 0x404921FB,
};

static const double PIo2[] = {
    1.57079625129699707031e+00, /* 0x3FF921FB, 0x40000000 */
    7.54978941586159635335e-08, /* 0x3E74442D, 0x00000000 */
    5.39030252995776476554e-15, /* 0x3CF84698, 0x80000000 */
    3.28200341580791294123e-22, /* 0x3B78CC51, 0x60000000 */
    1.27065575308067607349e-29, /* 0x39F01B83, 0x80000000 */
    1.22933308981111328932e-36, /* 0x387A2520, 0x40000000 */
    2.73370053816464559624e-44, /* 0x36E38222, 0x80000000 */
    2.16741683877804819444e-51, /* 0x3569F31D, 0x00000000 */
};

static const double two24 = 1.67772160000000000000e+07;  /* 0x41700000, 0x00000000 */
static const double twon24 = 5.96046447753906250000e-08; /* 0x3E700000, 0x00000000 */

/* Payne-Hanek reduction of a large argument (prec = 2: 53+53 bits). */
static int kernel_rem_pio2(const double* x, double* y, int e0, int nx) {
  enum { jk = 4, jp = 4 }; /* init_jk[prec = 2] */
  int32_t jz, jx, jv, carry, n, iq[20], i, j, k, m, q0, ih;
  double z, fw, f[20], fq[20], q[20];

  jx = nx - 1;
  jv = (e0 - 3) / 24;
  if (jv < 0) jv = 0;
  q0 = e0 - 24 * (jv + 1);

  j = jv - jx;
  m = jx + jk;
  for (i = 0; i <= m; i++, j++) f[i] = (j < 0) ? zero : (double)two_over_pi[j];

  for (i = 0; i <= jk; i++) {
    for (j = 0, fw = 0.0; j <= jx; j++) fw += x[j] * f[jx + i - j];
    q[i] = fw;
  }

  jz = jk;
recompute:
  for (i = 0, j = jz, z = q[jz]; j > 0; i++, j--) {
    fw = (double)((int32_t)(twon24 * z));
    iq[i] = (int32_t)(z - two24 * fw);
    z = q[j - 1] + fw;
  }

  z = dm_scalbn(z, q0);
  z -= 8.0 * floor(z * 0.125);
  n = (int32_t)z;
  z -= (double)n;
  ih = 0;
  if (q0 > 0) {
    i = (iq[jz - 1] >> (24 - q0));
    n += i;
    iq[jz - 1] -= i << (24 - q0);
    ih = iq[jz - 1] >> (23 - q0);
  } else if (q0 == 0) {
    ih = iq[jz - 1] >> 23;
  } else if (z >= 0.5) {
    ih = 2;
  }

  if (ih > 0) {
    n += 1;
    carry = 0;
    for (i = 0; i < jz; i++) {
      j = iq[i];
      if (carry == 0) {
        if (j != 0) {
          carry = 1;
          iq[i] = 0x1000000 - j;
        }
      } else {
        iq[i] = 0xffffff - j;
      }
    }
    if (q0 > 0) {
      switch (q0) {
        case 1: iq[jz - 1] &= 0x7fffff; break;
        case 2: iq[jz - 1] &= 0x3fffff; break;
        default: break;
      }
    }
    if (ih == 2) {
      z = one - z;
      if (carry != 0) z -= dm_scalbn(one, q0);
    }
  }

  if (z == zero) {
    j = 0;
    for (i = jz - 1; i >= jk; i--) j |= iq[i];
    if (j == 0) {
      for (k = 1; iq[jk - k] == 0; k++) {
      }
      for (i = jz + 1; i <= jz + k; i++) {
        f[jx + i] = (double)two_over_pi[jv + i];
        for (j = 0, fw = 0.0; j <= jx; j++) fw += x[j] * f[jx + i - j];
        q[i] = fw;
      }
      jz += k;
      goto recompute;
    }
  }

  if (z == 0.0) {
    jz -= 1;
    q0 -= 24;
    while (iq[jz] == 0) {
      jz--;
      q0 -= 24;
    }
  } else {
    z = dm_scalbn(z, -q0);
    if (z >= two24) {
      fw = (double)((int32_t)(twon24 * z));
      iq[jz] = (int32_t)(z - two24 * fw);
      jz += 1;
      q0 += 24;
      iq[jz] = (int32_t)fw;
    } else {
      iq[jz] = (int32_t)z;
    }
  }

  fw = dm_scalbn(one, q0);
  for (i = jz; i >= 0; i--) {
    q[i] = fw * (double)iq[i];
    fw *= twon24;
  }

  for (i = jz; i >= 0; i--) {
    for (fw = 0.0, k = 0; k <= jp && k <= jz - i; k++) fw += PIo2[k] * q[i + k];
    fq[jz - i] = fw;
  }

  fw = 0.0;
  for (i = jz; i >= 0; i--) fw += fq[i];
  y[0] = (ih == 0) ? fw : -fw;
  fw = fq[0] - fw;
  for (i = 1; i <= jz; i++) fw += fq[i];
  y[1] = (ih == 0) ? fw : -fw;
  return n & 7;
}

/* Returns n with x - n*pi/2 = y[0] + y[1]. */
static int32_t rem_pio2(double x, double* y) {
  static const double
      invpio2 = 6.36619772367581382433e-01, /* 0x3FE45F30, 0x6DC9C883 */
      pio2_1 = 1.57079632673412561417e+00,  /* 0x3FF921FB, 0x54400000 */
      pio2_1t = 6.07710050650619224932e-11, /* 0x3DD0B461, 0x1A626331 */
      pio2_2 = 6.07710050630396597660e-11,  /* 0x3DD0B461, 0x1A600000 */
      pio2_2t = 2.02226624879595063154e-21, /* 0x3BA3198A, 0x2E037073 */
      pio2_3 = 2.02226624871116645580e-21,  /* 0x3BA3198A, 0x2E000000 */
      pio2_3t = 8.47842766036889956997e-32; /* 0x397B839A, 0x252049C1 */
  double z, w, t, r, fn;
  double tx[3];
  int32_t e0, i, j, nx, n, ix, hx;
  uint32_t low;

  hx = high_word(x);
  ix = hx & 0x7fffffff;
  if (ix <= 0x3fe921fb) { /* |x| <= pi/4: no reduction */
    y[0] = x;
    y[1] = 0;
    return 0;
  }
  if (ix < 0x4002d97c) { /* |x| < 3pi/4: n = +-1 */
    if (hx > 0) {
      z = x - pio2_1;
      if (ix != 0x3ff921fb) {
        y[0] = z - pio2_1t;
        y[1] = (z - y[0]) - pio2_1t;
      } else {
        z -= pio2_2;
        y[0] = z - pio2_2t;
        y[1] = (z - y[0]) - pio2_2t;
      }
      return 1;
    } else {
      z = x + pio2_1;
      if (ix != 0x3ff921fb) {
        y[0] = z + pio2_1t;
        y[1] = (z - y[0]) + pio2_1t;
      } else {
        z += pio2_2;
        y[0] = z + pio2_2t;
        y[1] = (z - y[0]) + pio2_2t;
      }
      return -1;
    }
  }
  if (ix <= 0x413921fb) { /* |x| <= 2^19 * pi/2: medium size */
    t = fabs(x);
    n = (int32_t)(t * invpio2 + half);
    fn = (double)n;
    r = t - fn * pio2_1;
    w = fn * pio2_1t;
    if (n < 32 && ix != npio2_hw[n - 1]) {
      y[0] = r - w;
    } else {
      j = ix >> 20;
      y[0] = r - w;
      i = j - ((high_word(y[0]) >> 20) & 0x7ff);
      if (i > 16) { /* second iteration, good to 118 bits */
        t = r;
        w = fn * pio2_2;
        r = t - w;
        w = fn * pio2_2t - ((t - r) - w);
        y[0] = r - w;
        i = j - ((high_word(y[0]) >> 20) & 0x7ff);
        if (i > 49) { /* third iteration, 151 bits */
          t = r;
          w = fn * pio2_3;
          r = t - w;
          w = fn * pio2_3t - ((t - r) - w);
          y[0] = r - w;
        }
      }
    }
    y[1] = (r - y[0]) - w;
    if (hx < 0) {
      y[0] = -y[0];
      y[1] = -y[1];
      return -n;
    }
    return n;
  }
  if (ix >= 0x7ff00000) { /* Inf or NaN */
    y[0] = y[1] = x - x;
    return 0;
  }
  /* z = scalbn(|x|, ilogb(x) - 23) */
  low = low_word(x);
  e0 = (ix >> 20) - 1046;
  z = from_words((uint32_t)(ix - shl20(e0)), low);
  for (i = 0; i < 2; i++) {
    tx[i] = (double)((int32_t)z);
    z = (z - tx[i]) * two24;
  }
  tx[2] = z;
  nx = 3;
  while (tx[nx - 1] == zero) nx--;
  n = kernel_rem_pio2(tx, y, e0, nx);
  if (hx < 0) {
    y[0] = -y[0];
    y[1] = -y[1];
    return -n;
  }
  return n;
}

/* ------------------------------------------------------------ trig kernels */

static double kernel_sin(double x, double y, int iy) {
  static const double
      S1 = -1.66666666666666324348e-01, /* 0xBFC55555, 0x55555549 */
      S2 = 8.33333333332248946124e-03,  /* 0x3F811111, 0x1110F8A6 */
      S3 = -1.98412698298579493134e-04, /* 0xBF2A01A0, 0x19C161D5 */
      S4 = 2.75573137070700676789e-06,  /* 0x3EC71DE3, 0x57B1FE7D */
      S5 = -2.50507602534068634195e-08, /* 0xBE5AE5E6, 0x8A2B9CEB */
      S6 = 1.58969099521155010221e-10;  /* 0x3DE5D93A, 0x5ACFD57C */
  double z, r, v;
  int32_t ix = high_word(x) & 0x7fffffff;
  if (ix < 0x3e400000) { /* |x| < 2^-27 */
    if ((int)x == 0) return x;
  }
  z = x * x;
  v = z * x;
  r = S2 + z * (S3 + z * (S4 + z * (S5 + z * S6)));
  if (iy == 0) return x + v * (S1 + z * r);
  return x - ((z * (half * y - v * r) - y) - v * S1);
}

static double kernel_cos(double x, double y) {
  static const double
      C1 = 4.16666666666666019037e-02,  /* 0x3FA55555, 0x5555554C */
      C2 = -1.38888888888741095749e-03, /* 0xBF56C16C, 0x16C15177 */
      C3 = 2.48015872894767294178e-05,  /* 0x3EFA01A0, 0x19CB1590 */
      C4 = -2.75573143513906633035e-07, /* 0xBE927E4F, 0x809C52AD */
      C5 = 2.08757232129817482790e-09,  /* 0x3E21EE9E, 0xBDB4B1C4 */
      C6 = -1.13596475577881948265e-11; /* 0xBDA8FAE9, 0xBE8838D4 */
  double a, iz, z, r, qx;
  int32_t ix = high_word(x) & 0x7fffffff;
  if (ix < 0x3e400000) { /* |x| < 2^-27 */
    if ((int)x == 0) return one;
  }
  z = x * x;
  r = z * (C1 + z * (C2 + z * (C3 + z * (C4 + z * (C5 + z * C6)))));
  if (ix < 0x3FD33333) { /* |x| < 0.3 */
    return one - (half * z - (z * r - x * y));
  }
  if (ix > 0x3fe90000) { /* |x| > 0.78125 */
    qx = 0.28125;
  } else {
    qx = from_words((uint32_t)(ix - 0x00200000), 0); /* x/4 */
  }
  iz = half * z - qx;
  a = one - qx;
  return a - (iz - (z * r - x * y));
}

static double kernel_tan(double x, double y, int iy) {
  static const double T[] = {
      3.33333333333334091986e-01,  /* 0x3FD55555, 0x55555563 */
      1.33333333333201242699e-01,  /* 0x3FC11111, 0x1110FE7A */
      5.39682539762260521377e-02,  /* 0x3FABA1BA, 0x1BB341FE */
      2.18694882948595424599e-02,  /* 0x3F9664F4, 0x8406D637 */
      8.86323982359930005737e-03,  /* 0x3F8226E3, 0xE96E8493 */
      3.59207910759131235356e-03,  /* 0x3F6D6D22, 0xC9560328 */
      1.45620945432529025516e-03,  /* 0x3F57DBC8, 0xFEE08315 */
      5.88041240820264096874e-04,  /* 0x3F4344D8, 0xF2F26501 */
      2.46463134818469906812e-04,  /* 0x3F3026F7, 0x1A8D1068 */
      7.81794442939557092300e-05,  /* 0x3F147E88, 0xA03792A6 */
      7.14072491382608190305e-05,  /* 0x3F12B80F, 0x32F0A7E9 */
      -1.85586374855275456654e-05, /* 0xBEF375CB, 0xDB605373 */
      2.59073051863633712884e-05,  /* 0x3EFB2A70, 0x74BF7AD4 */
  };
  static const double
      pio4 = 7.85398163397448278999e-01,   /* 0x3FE921FB, 0x54442D18 */
      pio4lo = 3.06161699786838301793e-17; /* 0x3C81A626, 0x33145C07 */
  double z, r, v, w, s, a, t;
  int32_t ix, hx;
  hx = high_word(x);
  ix = hx & 0x7fffffff;
  if (ix < 0x3e300000) { /* |x| < 2^-28 */
    if ((int)x == 0) {
      if (((ix | (int32_t)low_word(x)) | (iy + 1)) == 0) return one / fabs(x);
      if (iy == 1) return x;
      /* -1 / (x + y), carefully */
      z = w = x + y;
      z = with_low_word(z, 0);
      v = y - (z - x);
      t = a = -one / w;
      t = with_low_word(t, 0);
      s = one + t * z;
      return t + a * (s + t * v);
    }
  }
  if (ix >= 0x3FE59428) { /* |x| >= 0.6744 */
    if (hx < 0) {
      x = -x;
      y = -y;
    }
    z = pio4 - x;
    w = pio4lo - y;
    x = z + w;
    y = 0.0;
  }
  z = x * x;
  w = z * z;
  r = T[1] + w * (T[3] + w * (T[5] + w * (T[7] + w * (T[9] + w * T[11]))));
  v = z * (T[2] + w * (T[4] + w * (T[6] + w * (T[8] + w * (T[10] + w * T[12])))));
  s = z * x;
  r = y + z * (s * (r + v) + y);
  r += T[0] * s;
  w = x + r;
  if (ix >= 0x3FE59428) {
    v = (double)iy;
    return (double)(hx < 0 ? -1 : 1) * (v - 2.0 * (x - (w * w / (w + v) - r)));
  }
  if (iy == 1) return w;
  /* -1.0 / (x + r), accurately */
  z = w;
  z = with_low_word(z, 0);
  v = r - (z - x);
  t = a = -1.0 / w;
  t = with_low_word(t, 0);
  s = 1.0 + t * z;
  return t + a * (s + t * v);
}

static double dm_sin(double x) {
  double y[2];
  int32_t n, ix = high_word(x) & 0x7fffffff;
  if (ix <= 0x3fe921fb) return kernel_sin(x, 0.0, 0);
  if (ix >= 0x7ff00000) return x - x;
  n = rem_pio2(x, y);
  switch (n & 3) {
    case 0: return kernel_sin(y[0], y[1], 1);
    case 1: return kernel_cos(y[0], y[1]);
    case 2: return -kernel_sin(y[0], y[1], 1);
    default: return -kernel_cos(y[0], y[1]);
  }
}

static double dm_cos(double x) {
  double y[2];
  int32_t n, ix = high_word(x) & 0x7fffffff;
  if (ix <= 0x3fe921fb) return kernel_cos(x, 0.0);
  if (ix >= 0x7ff00000) return x - x;
  n = rem_pio2(x, y);
  switch (n & 3) {
    case 0: return kernel_cos(y[0], y[1]);
    case 1: return -kernel_sin(y[0], y[1], 1);
    case 2: return -kernel_cos(y[0], y[1]);
    default: return kernel_sin(y[0], y[1], 1);
  }
}

static double dm_tan(double x) {
  double y[2];
  int32_t n, ix = high_word(x) & 0x7fffffff;
  if (ix <= 0x3fe921fb) return kernel_tan(x, 0.0, 1);
  if (ix >= 0x7ff00000) return x - x;
  n = rem_pio2(x, y);
  return kernel_tan(y[0], y[1], 1 - ((n & 1) << 1));
}

/* -------------------------------------------------------- inverse trig */

static const double
    pio2_hi = 1.57079632679489655800e+00, /* 0x3FF921FB, 0x54442D18 */
    pio2_lo = 6.12323399573676603587e-17, /* 0x3C91A626, 0x33145C07 */
    pio4_hi = 7.85398163397448278999e-01, /* 0x3FE921FB, 0x54442D18 */
    pS0 = 1.66666666666666657415e-01,     /* 0x3FC55555, 0x55555555 */
    pS1 = -3.25565818622400915405e-01,    /* 0xBFD4D612, 0x03EB6F7D */
    pS2 = 2.01212532134862925881e-01,     /* 0x3FC9C155, 0x0E884455 */
    pS3 = -4.00555345006794114027e-02,    /* 0xBFA48228, 0xB5688F3B */
    pS4 = 7.91534994289814532176e-04,     /* 0x3F49EFE0, 0x7501B288 */
    pS5 = 3.47933107596021167570e-05,     /* 0x3F023DE1, 0x0DFDF709 */
    qS1 = -2.40339491173441421878e+00,    /* 0xC0033A27, 0x1C8A2D4B */
    qS2 = 2.02094576023350569471e+00,     /* 0x40002AE5, 0x9C598AC8 */
    qS3 = -6.88283971605453293030e-01,    /* 0xBFE6066C, 0x1B8D0159 */
    qS4 = 7.70381505559019352791e-02;     /* 0x3FB3B8C5, 0xB12E9282 */

static double asin_p(double t) {
  return t * (pS0 + t * (pS1 + t * (pS2 + t * (pS3 + t * (pS4 + t * pS5)))));
}
static double asin_q(double t) { return one + t * (qS1 + t * (qS2 + t * (qS3 + t * qS4))); }

static double dm_asin(double x) {
  double t = 0.0, w, p, q, c, r, s;
  int32_t hx = high_word(x), ix = hx & 0x7fffffff;
  if (ix >= 0x3ff00000) { /* |x| >= 1 */
    if (((ix - 0x3ff00000) | (int32_t)low_word(x)) == 0) return x * pio2_hi + x * pio2_lo;
    return (x - x) / (x - x);
  } else if (ix < 0x3fe00000) { /* |x| < 0.5 */
    if (ix < 0x3e400000) {      /* |x| < 2^-27 */
      if (huge + x > one) return x;
    } else {
      t = x * x;
    }
    p = asin_p(t);
    q = asin_q(t);
    w = p / q;
    return x + x * w;
  }
  w = one - fabs(x);
  t = w * 0.5;
  p = asin_p(t);
  q = asin_q(t);
  s = sqrt(t);
  if (ix >= 0x3FEF3333) { /* |x| > 0.975 */
    w = p / q;
    t = pio2_hi - (2.0 * (s + s * w) - pio2_lo);
  } else {
    w = with_low_word(s, 0);
    c = (t - w * w) / (s + w);
    r = p / q;
    p = 2.0 * s * r - (pio2_lo - 2.0 * c);
    q = pio4_hi - 2.0 * w;
    t = pio4_hi - (p - q);
  }
  return hx > 0 ? t : -t;
}

static double dm_acos(double x) {
  static const double pi = 3.14159265358979311600e+00; /* 0x400921FB, 0x54442D18 */
  double z, p, q, r, w, s, c, df;
  int32_t hx = high_word(x), ix = hx & 0x7fffffff;
  if (ix >= 0x3ff00000) { /* |x| >= 1 */
    if (((ix - 0x3ff00000) | (int32_t)low_word(x)) == 0) {
      if (hx > 0) return 0.0;
      return pi + 2.0 * pio2_lo;
    }
    return (x - x) / (x - x);
  }
  if (ix < 0x3fe00000) {                           /* |x| < 0.5 */
    if (ix <= 0x3c600000) return pio2_hi + pio2_lo; /* |x| < 2^-57 */
    z = x * x;
    r = asin_p(z) / asin_q(z);
    return pio2_hi - (x - (pio2_lo - x * r));
  } else if (hx < 0) { /* x < -0.5 */
    z = (one + x) * 0.5;
    p = asin_p(z);
    q = asin_q(z);
    s = sqrt(z);
    r = p / q;
    w = r * s - pio2_lo;
    return pi - 2.0 * (s + w);
  }
  z = (one - x) * 0.5; /* x > 0.5 */
  s = sqrt(z);
  df = with_low_word(s, 0);
  c = (z - df * df) / (s + df);
  p = asin_p(z);
  q = asin_q(z);
  r = p / q;
  w = r * s + c;
  return 2.0 * (df + w);
}

static double dm_atan(double x) {
  static const double atanhi[] = {
      4.63647609000806093515e-01, /* atan(0.5)hi 0x3FDDAC67, 0x0561BB4F */
      7.85398163397448278999e-01, /* atan(1.0)hi 0x3FE921FB, 0x54442D18 */
      9.82793723247329054082e-01, /* atan(1.5)hi 0x3FEF730B, 0xD281F69B */
      1.57079632679489655800e+00, /* atan(inf)hi 0x3FF921FB, 0x54442D18 */
  };
  static const double atanlo[] = {
      2.26987774529616870924e-17, /* atan(0.5)lo 0x3C7A2B7F, 0x222F65E2 */
      3.06161699786838301793e-17, /* atan(1.0)lo 0x3C81A626, 0x33145C07 */
      1.39033110312309984516e-17, /* atan(1.5)lo 0x3C700788, 0x7AF0CBBD */
      6.12323399573676603587e-17, /* atan(inf)lo 0x3C91A626, 0x33145C07 */
  };
  static const double aT[] = {
      3.33333333333329318027e-01,  /* 0x3FD55555, 0x5555550D */
      -1.99999999998764832476e-01, /* 0xBFC99999, 0x9998EBC4 */
      1.42857142725034663711e-01,  /* 0x3FC24924, 0x920083FF */
      -1.11111104054623557880e-01, /* 0xBFBC71C6, 0xFE231671 */
      9.09088713343650656196e-02,  /* 0x3FB745CD, 0xC54C206E */
      -7.69187620504482999495e-02, /* 0xBFB3B0F2, 0xAF749A6D */
      6.66107313738753120669e-02,  /* 0x3FB10D66, 0xA0D03D51 */
      -5.83357013379057348645e-02, /* 0xBFADDE2D, 0x52DEFD9A */
      4.97687799461593236017e-02,  /* 0x3FA97B4B, 0x24760DEB */
      -3.65315727442169155270e-02, /* 0xBFA2B444, 0x2C6A6C2F */
      1.62858201153657823623e-02,  /* 0x3F90AD3A, 0xE322DA11 */
  };
  double w, s1, s2, z;
  int32_t hx = high_word(x), ix = hx & 0x7fffffff, id;
  if (ix >= 0x44100000) { /* |x| >= 2^66 */
    if (ix > 0x7ff00000 || (ix == 0x7ff00000 && low_word(x) != 0)) return x + x;
    return hx > 0 ? atanhi[3] + atanlo[3] : -atanhi[3] - atanlo[3];
  }
  if (ix < 0x3fdc0000) {   /* |x| < 0.4375 */
    if (ix < 0x3e400000) { /* |x| < 2^-27 */
      if (huge + x > one) return x;
    }
    id = -1;
  } else {
    x = fabs(x);
    if (ix < 0x3ff30000) {   /* |x| < 1.1875 */
      if (ix < 0x3fe60000) { /* 7/16 <= |x| < 11/16 */
        id = 0;
        x = (2.0 * x - one) / (2.0 + x);
      } else { /* 11/16 <= |x| < 19/16 */
        id = 1;
        x = (x - one) / (x + one);
      }
    } else if (ix < 0x40038000) { /* |x| < 2.4375 */
      id = 2;
      x = (x - 1.5) / (one + 1.5 * x);
    } else { /* 2.4375 <= |x| < 2^66 */
      id = 3;
      x = -1.0 / x;
    }
  }
  z = x * x;
  w = z * z;
  s1 = z * (aT[0] + w * (aT[2] + w * (aT[4] + w * (aT[6] + w * (aT[8] + w * aT[10])))));
  s2 = w * (aT[1] + w * (aT[3] + w * (aT[5] + w * (aT[7] + w * aT[9]))));
  if (id < 0) return x - x * (s1 + s2);
  z = atanhi[id] - ((x * (s1 + s2) - atanlo[id]) - x);
  return hx < 0 ? -z : z;
}

static double dm_atan2(double y, double x) {
  static const double
      pi_o_4 = 7.8539816339744827900e-01, /* 0x3FE921FB, 0x54442D18 */
      pi_o_2 = 1.5707963267948965580e+00, /* 0x3FF921FB, 0x54442D18 */
      pi = 3.1415926535897931160e+00,     /* 0x400921FB, 0x54442D18 */
      pi_lo = 1.2246467991473531772e-16;  /* 0x3CA1A626, 0x33145C07 */
  double z;
  int32_t k, m, hx, hy, ix, iy;
  uint32_t lx, ly;

  EXTRACT_WORDS(hx, lx, x);
  ix = hx & 0x7fffffff;
  EXTRACT_WORDS(hy, ly, y);
  iy = hy & 0x7fffffff;
  if (x != x || y != y) return x + y;
  if (((hx - 0x3ff00000) | (int32_t)lx) == 0) return dm_atan(y); /* x = 1.0 */
  m = (hy < 0 ? 1 : 0) | (hx < 0 ? 2 : 0); /* 2*sign(x) + sign(y) */

  if ((iy | (int32_t)ly) == 0) { /* y = 0 */
    switch (m) {
      case 0:
      case 1: return y;
      case 2: return pi + tiny;
      default: return -pi - tiny;
    }
  }
  if ((ix | (int32_t)lx) == 0) return hy < 0 ? -pi_o_2 - tiny : pi_o_2 + tiny; /* x = 0 */
  if (ix == 0x7ff00000) { /* x is +-Inf */
    if (iy == 0x7ff00000) {
      switch (m) {
        case 0: return pi_o_4 + tiny;
        case 1: return -pi_o_4 - tiny;
        case 2: return 3.0 * pi_o_4 + tiny;
        default: return -3.0 * pi_o_4 - tiny;
      }
    }
    switch (m) {
      case 0: return zero;
      case 1: return -zero;
      case 2: return pi + tiny;
      default: return -pi - tiny;
    }
  }
  if (iy == 0x7ff00000) return hy < 0 ? -pi_o_2 - tiny : pi_o_2 + tiny; /* y is +-Inf */

  k = (iy - ix) >> 20;
  if (k > 60) { /* |y/x| > 2^60 */
    z = pi_o_2 + 0.5 * pi_lo;
    m &= 1;
  } else if (hx < 0 && k < -60) {
    z = 0.0; /* 0 > |y|/x > -2^-60 */
  } else {
    z = dm_atan(fabs(y / x));
  }
  switch (m) {
    case 0: return z;
    case 1: return -z;
    case 2: return pi - (z - pi_lo);
    default: return (z - pi_lo) - pi;
  }
}

/* -------------------------------------------------------------- exp family */

static const double
    ln2_hi = 6.93147180369123816490e-01, /* 0x3FE62E42, 0xFEE00000 */
    ln2_lo = 1.90821492927058770002e-10, /* 0x3DEA39EF, 0x35793C76 */
    invln2 = 1.44269504088896338700e+00, /* 0x3FF71547, 0x652B82FE */
    o_threshold = 7.09782712893383973096e+02, /* 0x40862E42, 0xFEFA39EF */
    two54 = 1.80143985094819840000e+16,  /* 0x43500000, 0x00000000 */
    two1023 = 8.98846567431157953865e+307; /* 0x7FE00000, 0x00000000 */

static double dm_exp(double x) {
  static const double
      u_threshold = -7.45133219101941108420e+02, /* 0xC0874910, 0xD52D3051 */
      P1 = 1.66666666666666019037e-01,           /* 0x3FC55555, 0x5555553E */
      P2 = -2.77777777770155933842e-03,          /* 0xBF66C16C, 0x16BEBD93 */
      P3 = 6.61375632143793436117e-05,           /* 0x3F11566A, 0xAF25DE2C */
      P4 = -1.65339022054652515390e-06,          /* 0xBEBBBD41, 0xC5D26BF1 */
      P5 = 4.13813679705723846039e-08,           /* 0x3E663769, 0x72BEA4D0 */
      E = 2.71828182845904509080e+00,            /* 0x4005BF0A, 0x8B145769 */
      twom1000 = 9.33263618503218878990e-302;    /* 0x01700000, 0x00000000 */
  static const double halF[2] = {0.5, -0.5};
  static const double ln2HI[2] = {6.93147180369123816490e-01, -6.93147180369123816490e-01};
  static const double ln2LO[2] = {1.90821492927058770002e-10, -1.90821492927058770002e-10};
  double y, hi = 0.0, lo = 0.0, c, t, twopk;
  int32_t k = 0, xsb;
  uint32_t hx = (uint32_t)high_word(x);

  xsb = (int32_t)((hx >> 31) & 1);
  hx &= 0x7fffffff;
  if (hx >= 0x40862E42) { /* |x| >= 709.78... */
    if (hx >= 0x7ff00000) {
      if (((hx & 0xfffff) | low_word(x)) != 0) return x + x; /* NaN */
      return xsb == 0 ? x : 0.0;
    }
    if (x > o_threshold) return huge * huge;
    if (x < u_threshold) return twom1000 * twom1000;
  }

  if (hx > 0x3fd62e42) {   /* |x| > 0.5 ln2 */
    if (hx < 0x3FF0A2B2) { /* and |x| < 1.5 ln2 */
      if (x == 1.0) return E; /* V8: the reduction below gets e's last bit wrong */
      hi = x - ln2HI[xsb];
      lo = ln2LO[xsb];
      k = 1 - xsb - xsb;
    } else {
      k = (int32_t)(invln2 * x + halF[xsb]);
      t = (double)k;
      hi = x - t * ln2HI[0];
      lo = t * ln2LO[0];
    }
    x = hi - lo;
  } else if (hx < 0x3e300000) { /* |x| < 2^-28 */
    if (huge + x > one) return one + x;
  } else {
    k = 0;
  }

  t = x * x;
  if (k >= -1021) {
    twopk = from_words((uint32_t)(0x3ff00000 + shl20(k)), 0);
  } else {
    twopk = from_words((uint32_t)(0x3ff00000 + shl20(k + 1000)), 0);
  }
  c = x - t * (P1 + t * (P2 + t * (P3 + t * (P4 + t * P5))));
  if (k == 0) return one - ((x * c) / (c - 2.0) - x);
  y = one - ((lo - (x * c) / (2.0 - c)) - hi);
  if (k >= -1021) {
    if (k == 1024) return y * 2.0 * two1023;
    return y * twopk;
  }
  return y * twopk * twom1000;
}

static double dm_expm1(double x) {
  static const double
      Q1 = -3.33333333333331316428e-02, /* 0xBFA11111, 0x111110F4 */
      Q2 = 1.58730158725481460165e-03,  /* 0x3F5A01A0, 0x19FE5585 */
      Q3 = -7.93650757867487942473e-05, /* 0xBF14CE19, 0x9EAADBB7 */
      Q4 = 4.00821782732936239552e-06,  /* 0x3ED0CFCA, 0x86E65239 */
      Q5 = -2.01099218183624371326e-07; /* 0xBE8AFDB7, 0x6E09C32D */
  double y, hi, lo, c = 0.0, t, e, hxs, hfx, r1, twopk;
  int32_t k, xsb;
  uint32_t hx = (uint32_t)high_word(x);

  xsb = (int32_t)(hx & 0x80000000);
  hx &= 0x7fffffff;
  if (hx >= 0x4043687A) {   /* |x| >= 56 ln2 */
    if (hx >= 0x40862E42) { /* |x| >= 709.78... */
      if (hx >= 0x7ff00000) {
        if (((hx & 0xfffff) | low_word(x)) != 0) return x + x; /* NaN */
        return xsb == 0 ? x : -1.0;
      }
      if (x > o_threshold) return huge * huge;
    }
    if (xsb != 0) { /* x < -56 ln2 */
      if (x + tiny < 0.0) return tiny - one;
    }
  }

  if (hx > 0x3fd62e42) {   /* |x| > 0.5 ln2 */
    if (hx < 0x3FF0A2B2) { /* and |x| < 1.5 ln2 */
      if (xsb == 0) {
        hi = x - ln2_hi;
        lo = ln2_lo;
        k = 1;
      } else {
        hi = x + ln2_hi;
        lo = -ln2_lo;
        k = -1;
      }
    } else {
      k = (int32_t)(invln2 * x + ((xsb == 0) ? 0.5 : -0.5));
      t = (double)k;
      hi = x - t * ln2_hi;
      lo = t * ln2_lo;
    }
    x = hi - lo;
    c = (hi - x) - lo;
  } else if (hx < 0x3c900000) { /* |x| < 2^-54 */
    t = huge + x;
    return x - (t - (huge + x));
  } else {
    k = 0;
  }

  hfx = 0.5 * x;
  hxs = x * hfx;
  r1 = one + hxs * (Q1 + hxs * (Q2 + hxs * (Q3 + hxs * (Q4 + hxs * Q5))));
  t = 3.0 - r1 * hfx;
  e = hxs * ((r1 - t) / (6.0 - x * t));
  if (k == 0) return x - (x * e - hxs);
  twopk = from_words((uint32_t)(0x3ff00000 + shl20(k)), 0);
  e = (x * (e - c) - c);
  e -= hxs;
  if (k == -1) return 0.5 * (x - e) - 0.5;
  if (k == 1) {
    if (x < -0.25) return -2.0 * (e - (x + 0.5));
    return one + 2.0 * (x - e);
  }
  if (k <= -2 || k > 56) {
    y = one - (e - x);
    if (k == 1024) {
      y = y * 2.0 * two1023;
    } else {
      y = y * twopk;
    }
    return y - one;
  }
  t = one;
  if (k < 20) {
    t = with_high_word(t, (uint32_t)(0x3ff00000 - (0x200000 >> k))); /* 1 - 2^-k */
    y = t - (e - x);
    y = y * twopk;
  } else {
    t = with_high_word(t, (uint32_t)shl20(0x3ff - k)); /* 2^-k */
    y = x - (e + t);
    y += one;
    y = y * twopk;
  }
  return y;
}

/* -------------------------------------------------------------- log family */

static const double
    Lg1 = 6.666666666666735130e-01, /* 0x3FE55555, 0x55555593 */
    Lg2 = 3.999999999940941908e-01, /* 0x3FD99999, 0x9997FA04 */
    Lg3 = 2.857142874366239149e-01, /* 0x3FD24924, 0x94229359 */
    Lg4 = 2.222219843214978396e-01, /* 0x3FCC71C5, 0x1D8E78AF */
    Lg5 = 1.818357216161805012e-01, /* 0x3FC74664, 0x96CB03DE */
    Lg6 = 1.531383769920937332e-01, /* 0x3FC39A09, 0xD078C69F */
    Lg7 = 1.479819860511658591e-01; /* 0x3FC2F112, 0xDF3E5244 */

static double neg_inf(void) { return -u2d(0x7ff0000000000000ull); }
static double nan_value(void) { return u2d(0x7ff8000000000000ull); }

static double dm_log(double x) {
  double hfsq, f, s, z, R, w, t1, t2, dk;
  int32_t k, hx, i, j;
  uint32_t lx;

  EXTRACT_WORDS(hx, lx, x);
  k = 0;
  if (hx < 0x00100000) { /* x < 2^-1022 */
    if (((hx & 0x7fffffff) | (int32_t)lx) == 0) return neg_inf();
    if (hx < 0) return nan_value();
    k -= 54;
    x *= two54; /* subnormal: scale up */
    hx = high_word(x);
  }
  if (hx >= 0x7ff00000) return x + x;
  k += (hx >> 20) - 1023;
  hx &= 0x000fffff;
  i = (hx + 0x95f64) & 0x100000;
  x = with_high_word(x, (uint32_t)(hx | (i ^ 0x3ff00000))); /* normalize x or x/2 */
  k += (i >> 20);
  f = x - 1.0;
  if ((0x000fffff & (2 + hx)) < 3) { /* -2^-20 <= f < 2^-20 */
    if (f == zero) {
      if (k == 0) return zero;
      dk = (double)k;
      return dk * ln2_hi + dk * ln2_lo;
    }
    R = f * f * (0.5 - 0.33333333333333333 * f);
    if (k == 0) return f - R;
    dk = (double)k;
    return dk * ln2_hi - ((R - dk * ln2_lo) - f);
  }
  s = f / (2.0 + f);
  dk = (double)k;
  z = s * s;
  i = hx - 0x6147a;
  w = z * z;
  j = 0x6b851 - hx;
  t1 = w * (Lg2 + w * (Lg4 + w * Lg6));
  t2 = z * (Lg1 + w * (Lg3 + w * (Lg5 + w * Lg7)));
  i |= j;
  R = t2 + t1;
  if (i > 0) {
    hfsq = 0.5 * f * f;
    if (k == 0) return f - (hfsq - s * (hfsq + R));
    return dk * ln2_hi - ((hfsq - (s * (hfsq + R) + dk * ln2_lo)) - f);
  }
  if (k == 0) return f - s * (f - R);
  return dk * ln2_hi - ((s * (f - R) - dk * ln2_lo) - f);
}

static double dm_log1p(double x) {
  double hfsq, f = 0.0, c = 0.0, s, z, R, u;
  int32_t k, hx, hu = 0, ax;

  hx = high_word(x);
  ax = hx & 0x7fffffff;
  k = 1;
  if (hx < 0x3FDA827A) {    /* 1 + x < sqrt(2)+ */
    if (ax >= 0x3ff00000) { /* x <= -1.0 */
      if (x == -1.0) return neg_inf();
      return nan_value();
    }
    if (ax < 0x3e200000) {                        /* |x| < 2^-29 */
      if (two54 + x > zero && ax < 0x3c900000) return x; /* |x| < 2^-54 */
      return x - x * x * 0.5;
    }
    if (hx > 0 || hx <= (int32_t)0xbfd2bec4) { /* sqrt(2)/2- <= 1 + x < sqrt(2)+ */
      k = 0;
      f = x;
      hu = 1;
    }
  }
  if (hx >= 0x7ff00000) return x + x;
  if (k != 0) {
    if (hx < 0x43400000) {
      u = 1.0 + x;
      hu = high_word(u);
      k = (hu >> 20) - 1023;
      c = (k > 0) ? 1.0 - (u - x) : x - (u - 1.0); /* correction term */
      c /= u;
    } else {
      u = x;
      hu = high_word(u);
      k = (hu >> 20) - 1023;
      c = 0;
    }
    hu &= 0x000fffff;
    if (hu < 0x6a09e) { /* u ~< sqrt(2) */
      u = with_high_word(u, (uint32_t)(hu | 0x3ff00000));
    } else {
      k += 1;
      u = with_high_word(u, (uint32_t)(hu | 0x3fe00000));
      hu = (0x00100000 - hu) >> 2;
    }
    f = u - 1.0;
  }
  hfsq = 0.5 * f * f;
  if (hu == 0) { /* |f| < 2^-20 */
    if (f == zero) {
      if (k == 0) return zero;
      c += k * ln2_lo;
      return k * ln2_hi + c;
    }
    R = hfsq * (1.0 - 0.66666666666666666 * f);
    if (k == 0) return f - R;
    return k * ln2_hi - ((R - (k * ln2_lo + c)) - f);
  }
  s = f / (2.0 + f);
  z = s * s;
  R = z * (Lg1 + z * (Lg2 + z * (Lg3 + z * (Lg4 + z * (Lg5 + z * (Lg6 + z * Lg7))))));
  if (k == 0) return f - (hfsq - s * (hfsq + R));
  return k * ln2_hi - ((hfsq - (s * (hfsq + R) + (k * ln2_lo + c))) - f);
}

/* log(1 + f) - f for 1 + f in ~[sqrt(2)/2, sqrt(2)] (FreeBSD k_log.h). */
static double k_log1p(double f) {
  double hfsq, s, z, R, w, t1, t2;
  s = f / (2.0 + f);
  z = s * s;
  w = z * z;
  t1 = w * (Lg2 + w * (Lg4 + w * Lg6));
  t2 = z * (Lg1 + w * (Lg3 + w * (Lg5 + w * Lg7)));
  R = t2 + t1;
  hfsq = 0.5 * f * f;
  return s * (hfsq + R);
}

static double dm_log2(double x) {
  static const double
      ivln2hi = 1.44269504072144627571e+00, /* 0x3FF71547, 0x65200000 */
      ivln2lo = 1.67517131648865118353e-10; /* 0x3DE705FC, 0x2EEFA200 */
  double f, hfsq, hi, lo, r, val_hi, val_lo, w, y;
  int32_t i, k, hx;
  uint32_t lx;

  EXTRACT_WORDS(hx, lx, x);
  k = 0;
  if (hx < 0x00100000) { /* x < 2^-1022 */
    if (((hx & 0x7fffffff) | (int32_t)lx) == 0) return neg_inf();
    if (hx < 0) return nan_value();
    k -= 54;
    x *= two54;
    hx = high_word(x);
  }
  if (hx >= 0x7ff00000) return x + x;
  if (hx == 0x3ff00000 && lx == 0) return zero;
  k += (hx >> 20) - 1023;
  hx &= 0x000fffff;
  i = (hx + 0x95f64) & 0x100000;
  x = with_high_word(x, (uint32_t)(hx | (i ^ 0x3ff00000)));
  k += (i >> 20);
  y = (double)k;
  f = x - 1.0;
  hfsq = 0.5 * f * f;
  r = k_log1p(f);
  hi = f - hfsq;
  hi = with_low_word(hi, 0);
  lo = (f - hi) - hfsq + r;
  val_hi = hi * ivln2hi;
  val_lo = (lo + hi) * ivln2lo + lo * ivln2hi;
  w = y + val_hi;
  val_lo += (y - w) + val_hi;
  val_hi = w;
  return val_lo + val_hi;
}

static double dm_log10(double x) {
  static const double
      ivln10 = 4.34294481903251816668e-01,    /* 0x3FDBCB7B, 0x1526E50E */
      log10_2hi = 3.01029995663611771306e-01, /* 0x3FD34413, 0x509F6000 */
      log10_2lo = 3.69423907715893078616e-13; /* 0x3D59FEF3, 0x11F12B36 */
  double y, z;
  int32_t i, k, hx;
  uint32_t lx;

  EXTRACT_WORDS(hx, lx, x);
  k = 0;
  if (hx < 0x00100000) { /* x < 2^-1022 */
    if (((hx & 0x7fffffff) | (int32_t)lx) == 0) return neg_inf();
    if (hx < 0) return nan_value();
    k -= 54;
    x *= two54;
    EXTRACT_WORDS(hx, lx, x);
  }
  if (hx >= 0x7ff00000) return x + x;
  if (hx == 0x3ff00000 && lx == 0) return zero;
  k += (hx >> 20) - 1023;
  i = k < 0 ? 1 : 0;
  hx = (hx & 0x000fffff) | shl20(0x3ff - i);
  y = (double)(k + i);
  x = from_words((uint32_t)hx, lx);
  z = y * log10_2lo + ivln10 * dm_log(x);
  return z + y * log10_2hi;
}

/* -------------------------------------------------------------------- pow */

static double dm_pow(double x, double y) {
  static const double bp[] = {1.0, 1.5};
  static const double dp_h[] = {0.0, 5.84962487220764160156e-01}; /* 0x3FE2B803, 0x40000000 */
  static const double dp_l[] = {0.0, 1.35003920212974897128e-08}; /* 0x3E4CFDEB, 0x43CFD006 */
  static const double
      two53 = 9.00719925474099200000e+15,    /* 0x43400000, 0x00000000 */
      L1 = 5.99999999999994648725e-01,       /* 0x3FE33333, 0x33333303 */
      L2 = 4.28571428578550184252e-01,       /* 0x3FDB6DB6, 0xDB6FABFF */
      L3 = 3.33333329818377432918e-01,       /* 0x3FD55555, 0x518F264D */
      L4 = 2.72728123808534006489e-01,       /* 0x3FD17460, 0xA91D4101 */
      L5 = 2.30660745775561754067e-01,       /* 0x3FCD864A, 0x93C9DB65 */
      L6 = 2.06975017800338417784e-01,       /* 0x3FCA7E28, 0x4A454EEF */
      P1 = 1.66666666666666019037e-01,       /* 0x3FC55555, 0x5555553E */
      P2 = -2.77777777770155933842e-03,      /* 0xBF66C16C, 0x16BEBD93 */
      P3 = 6.61375632143793436117e-05,       /* 0x3F11566A, 0xAF25DE2C */
      P4 = -1.65339022054652515390e-06,      /* 0xBEBBBD41, 0xC5D26BF1 */
      P5 = 4.13813679705723846039e-08,       /* 0x3E663769, 0x72BEA4D0 */
      lg2 = 6.93147180559945286227e-01,      /* 0x3FE62E42, 0xFEFA39EF */
      lg2_h = 6.93147182464599609375e-01,    /* 0x3FE62E43, 0x00000000 */
      lg2_l = -1.90465429995776804525e-09,   /* 0xBE205C61, 0x0CA86C39 */
      ovt = 8.00856625953729443720e-17,      /* 0x3C971547, 0x652B82FE */
      cp = 9.61796693925975554329e-01,       /* 0x3FEEC709, 0xDC3A03FD */
      cp_h = 9.61796700954437255859e-01,     /* 0x3FEEC709, 0xE0000000 */
      cp_l = -7.02846165095275826516e-09,    /* 0xBE3E2FE0, 0x145B01F5 */
      ivln2 = 1.44269504088896338700e+00,    /* 0x3FF71547, 0x652B82FE */
      ivln2_h = 1.44269502162933349609e+00,  /* 0x3FF71547, 0x60000000 */
      ivln2_l = 1.92596299112661746887e-08;  /* 0x3E54AE0B, 0xF85DDF44 */
  double z, ax, z_h, z_l, p_h, p_l;
  double y1, t1, t2, r, s, t, u, v, w;
  int32_t i, j, k, yisint, n;
  int32_t hx, hy, ix, iy;
  uint32_t lx, ly;

  EXTRACT_WORDS(hx, lx, x);
  EXTRACT_WORDS(hy, ly, y);
  ix = hx & 0x7fffffff;
  iy = hy & 0x7fffffff;

  if ((iy | (int32_t)ly) == 0) return one;          /* x**0 = 1 */
  if (hx == 0x3ff00000 && lx == 0) return one;      /* 1**y = 1, even for NaN y */
  if (ix > 0x7ff00000 || (ix == 0x7ff00000 && lx != 0) || iy > 0x7ff00000 ||
      (iy == 0x7ff00000 && ly != 0)) {
    return (x + 0.0) + (y + 0.0); /* NaN */
  }

  /* yisint: 0 = not an integer, 1 = odd integer, 2 = even integer (only when x < 0) */
  yisint = 0;
  if (hx < 0) {
    if (iy >= 0x43400000) {
      yisint = 2;
    } else if (iy >= 0x3ff00000) {
      k = (iy >> 20) - 0x3ff;
      if (k > 20) {
        uint32_t jj = ly >> (52 - k);
        if ((jj << (52 - k)) == ly) yisint = 2 - (int32_t)(jj & 1);
      } else if (ly == 0) {
        j = iy >> (20 - k);
        if ((j << (20 - k)) == iy) yisint = 2 - (j & 1);
      }
    }
  }

  if (ly == 0) {
    if (iy == 0x7ff00000) { /* y is +-Inf */
      if (((ix - 0x3ff00000) | (int32_t)lx) == 0) return one; /* (-1)**+-Inf = 1 (C99) */
      if (ix >= 0x3ff00000) return hy >= 0 ? y : zero;          /* |x| > 1 */
      return hy < 0 ? -y : zero;                                /* |x| < 1 */
    }
    if (iy == 0x3ff00000) return hy < 0 ? one / x : x; /* y is +-1 */
    if (hy == 0x40000000) return x * x;                /* y is 2 */
    if (hy == 0x3fe00000) {                            /* y is 0.5 */
      if (hx >= 0) return sqrt(x);
    }
  }

  ax = fabs(x);
  if (lx == 0) {
    if (ix == 0x7ff00000 || ix == 0 || ix == 0x3ff00000) { /* x is +-0, +-Inf, +-1 */
      z = ax;
      if (hy < 0) z = one / z;
      if (hx < 0) {
        if (((ix - 0x3ff00000) | yisint) == 0) {
          z = nan_value(); /* (-1)**non-int */
        } else if (yisint == 1) {
          z = -z;
        }
      }
      return z;
    }
  }

  n = (int32_t)(((uint32_t)hx >> 31) - 1u);
  if ((n | yisint) == 0) return nan_value(); /* (x < 0)**(non-int) */

  s = one;
  if ((n | (yisint - 1)) == 0) s = -one; /* (-ve)**(odd int) */

  if (iy > 0x41e00000) {   /* |y| > 2^31 */
    if (iy > 0x43f00000) { /* |y| > 2^64: must over/underflow */
      if (ix <= 0x3fefffff) return hy < 0 ? huge * huge : tiny * tiny;
      if (ix >= 0x3ff00000) return hy > 0 ? huge * huge : tiny * tiny;
    }
    if (ix < 0x3fefffff) return hy < 0 ? s * huge * huge : s * tiny * tiny;
    if (ix > 0x3ff00000) return hy > 0 ? s * huge * huge : s * tiny * tiny;
    /* |1 - x| <= 2^-20: log(x) by x - x^2/2 + x^3/3 - x^4/4 */
    t = ax - one;
    w = (t * t) * (0.5 - t * (0.3333333333333333333333 - t * 0.25));
    u = ivln2_h * t;
    v = t * ivln2_l - w * ivln2;
    t1 = u + v;
    t1 = with_low_word(t1, 0);
    t2 = v - (t1 - u);
  } else {
    double ss, s2, s_h, s_l, t_h, t_l;
    n = 0;
    if (ix < 0x00100000) { /* subnormal x */
      ax *= two53;
      n -= 53;
      ix = high_word(ax);
    }
    n += ((ix) >> 20) - 0x3ff;
    j = ix & 0x000fffff;
    ix = j | 0x3ff00000;
    if (j <= 0x3988E) {
      k = 0; /* |x| < sqrt(3/2) */
    } else if (j < 0xBB67A) {
      k = 1; /* |x| < sqrt(3) */
    } else {
      k = 0;
      n += 1;
      ix -= 0x00100000;
    }
    ax = with_high_word(ax, (uint32_t)ix);

    u = ax - bp[k];
    v = one / (ax + bp[k]);
    ss = u * v;
    s_h = ss;
    s_h = with_low_word(s_h, 0);
    t_h = from_words((uint32_t)(((ix >> 1) | 0x20000000) + 0x00080000 + (k << 18)), 0);
    t_l = ax - (t_h - bp[k]);
    s_l = v * ((u - s_h * t_h) - s_h * t_l);
    s2 = ss * ss;
    r = s2 * s2 * (L1 + s2 * (L2 + s2 * (L3 + s2 * (L4 + s2 * (L5 + s2 * L6)))));
    r += s_l * (s_h + ss);
    s2 = s_h * s_h;
    t_h = 3.0 + s2 + r;
    t_h = with_low_word(t_h, 0);
    t_l = r - ((t_h - 3.0) - s2);
    u = s_h * t_h;
    v = s_l * t_h + t_l * ss;
    p_h = u + v;
    p_h = with_low_word(p_h, 0);
    p_l = v - (p_h - u);
    z_h = cp_h * p_h;
    z_l = cp_l * p_h + p_l * cp + dp_l[k];
    t = (double)n;
    t1 = (((z_h + z_l) + dp_h[k]) + t);
    t1 = with_low_word(t1, 0);
    t2 = z_l - (((t1 - t) - dp_h[k]) - z_h);
  }

  /* (y1 + y2) * (t1 + t2) */
  y1 = with_low_word(y, 0);
  p_l = (y - y1) * t1 + y * t2;
  p_h = y1 * t1;
  z = p_l + p_h;
  {
    uint32_t zi;
    EXTRACT_WORDS(j, zi, z);
    i = (int32_t)zi;
  }
  if (j >= 0x40900000) { /* z >= 1024 */
    if (((j - 0x40900000) | i) != 0) return s * huge * huge;
    if (p_l + ovt > z - p_h) return s * huge * huge;
  } else if ((j & 0x7fffffff) >= 0x4090cc00) { /* z <= -1075 */
    if ((((uint32_t)j - 0xc090cc00u) | (uint32_t)i) != 0) return s * tiny * tiny;
    if (p_l <= z - p_h) return s * tiny * tiny;
  }

  /* 2**(p_h + p_l) */
  i = j & 0x7fffffff;
  k = (i >> 20) - 0x3ff;
  n = 0;
  if (i > 0x3fe00000) { /* |z| > 0.5: n = [z + 0.5] */
    n = j + (0x00100000 >> (k + 1));
    k = ((n & 0x7fffffff) >> 20) - 0x3ff;
    t = from_words((uint32_t)(n & ~(0x000fffff >> k)), 0);
    n = ((n & 0x000fffff) | 0x00100000) >> (20 - k);
    if (j < 0) n = -n;
    p_h -= t;
  }
  t = p_l + p_h;
  t = with_low_word(t, 0);
  u = t * lg2_h;
  v = (p_l - (t - p_h)) * lg2 + t * lg2_l;
  z = u + v;
  w = v - (z - u);
  t = z * z;
  t1 = z - t * (P1 + t * (P2 + t * (P3 + t * (P4 + t * P5))));
  r = (z * t1) / (t1 - 2.0) - (w + z * w);
  z = one - (r - z);
  j = high_word(z);
  j = (int32_t)((uint32_t)j + (uint32_t)shl20(n));
  if ((j >> 20) <= 0) {
    z = dm_scalbn(z, n); /* subnormal output */
  } else {
    z = with_high_word(z, (uint32_t)j);
  }
  return s * z;
}

/* -------------------------------------------------------------- hyperbolic */

static double dm_sinh(double x) {
  static const double
      KSINH_OVERFLOW = 7.10475860073943863426e+02, /* 0x408633CE, 0x8FB9F87D */
      TWO_M28 = 3.72529029846191406250e-09,        /* 0x3E300000, 0x00000000 */
      LOG_MAXD = 7.09782226562500000000e+02,       /* 0x40862E42, 0x00000000 */
      shuge = 1.0e307;
  double h = (x < 0) ? -0.5 : 0.5;
  double ax = fabs(x), t, w;
  if (ax < 22) { /* |x| in [0, 22]: sign(x) * 0.5 * (E + E / (E + 1)) */
    if (ax < TWO_M28) return x;
    t = dm_expm1(ax);
    if (ax < 1) return h * (2 * t - t * t / (t + 1));
    return h * (t + t / (t + 1));
  }
  if (ax < LOG_MAXD) return h * dm_exp(ax);
  if (ax <= KSINH_OVERFLOW) {
    w = dm_exp(0.5 * ax);
    t = h * w;
    return t * w;
  }
  return x * shuge; /* overflow, Inf or NaN */
}

static double dm_cosh(double x) {
  static const double KCOSH_OVERFLOW = 7.10475860073943863426e+02; /* 0x408633CE, 0x8FB9F87D */
  double t, w;
  int32_t ix = high_word(x) & 0x7fffffff;
  if (ix < 0x3FD62E43) { /* |x| in [0, 0.5 ln2]: 1 + expm1(|x|)^2 / (2 exp(|x|)) */
    t = dm_expm1(fabs(x));
    w = one + t;
    if (ix < 0x3C800000) return w; /* |x| < 2^-55 */
    return one + (t * t) / (w + w);
  }
  if (ix < 0x40360000) { /* |x| in [0.5 ln2, 22] */
    t = dm_exp(fabs(x));
    return half * t + half / t;
  }
  if (ix < 0x40862E42) return half * dm_exp(fabs(x));
  if (fabs(x) <= KCOSH_OVERFLOW) {
    w = dm_exp(half * fabs(x));
    t = half * w;
    return t * w;
  }
  if (ix >= 0x7FF00000) return x * x; /* Inf or NaN */
  return huge * huge;
}

static double dm_tanh(double x) {
  double t, z;
  int32_t jx = high_word(x), ix = jx & 0x7fffffff;
  if (ix >= 0x7ff00000) { /* Inf or NaN */
    if (jx >= 0) return one / x + one;
    return one / x - one;
  }
  if (ix < 0x40360000) {   /* |x| < 22 */
    if (ix < 0x3e300000) { /* |x| < 2^-28 */
      if (huge + x > one) return x;
    }
    if (ix >= 0x3ff00000) { /* |x| >= 1 */
      t = dm_expm1(2.0 * fabs(x));
      z = one - 2.0 / (t + 2.0);
    } else {
      t = dm_expm1(-2.0 * fabs(x));
      z = -t / (t + 2.0);
    }
  } else {
    z = one - tiny; /* |x| >= 22: +-1 */
  }
  return jx >= 0 ? z : -z;
}

static const double ln2 = 6.93147180559945286227e-01; /* 0x3FE62E42, 0xFEFA39EF */

static double dm_asinh(double x) {
  double t, w;
  int32_t hx = high_word(x), ix = hx & 0x7fffffff;
  if (ix >= 0x7ff00000) return x + x; /* Inf or NaN */
  if (ix < 0x3e300000) {              /* |x| < 2^-28 */
    if (huge + x > one) return x;
  }
  if (ix > 0x41b00000) { /* |x| > 2^28 */
    w = dm_log(fabs(x)) + ln2;
  } else if (ix > 0x40000000) { /* 2^28 > |x| > 2.0 */
    t = fabs(x);
    w = dm_log(2.0 * t + one / (sqrt(x * x + one) + t));
  } else { /* 2.0 > |x| > 2^-28 */
    t = x * x;
    w = dm_log1p(fabs(x) + t / (one + sqrt(one + t)));
  }
  return hx > 0 ? w : -w;
}

static double dm_acosh(double x) {
  double t;
  int32_t hx;
  uint32_t lx;
  EXTRACT_WORDS(hx, lx, x);
  if (hx < 0x3ff00000) return nan_value(); /* x < 1 */
  if (hx >= 0x41b00000) {                  /* x > 2^28 */
    if (hx >= 0x7ff00000) return x + x;    /* Inf or NaN */
    return dm_log(x) + ln2;
  }
  if (((hx - 0x3ff00000) | (int32_t)lx) == 0) return 0.0; /* acosh(1) = 0 */
  if (hx > 0x40000000) {                                  /* 2^28 > x > 2 */
    t = x * x;
    return dm_log(2.0 * x - one / (x + sqrt(t - one)));
  }
  t = x - one; /* 1 < x < 2 */
  return dm_log1p(t + sqrt(2.0 * t + t * t));
}

static double dm_atanh(double x) {
  double t;
  int32_t hx, ix;
  uint32_t lx;
  EXTRACT_WORDS(hx, lx, x);
  ix = hx & 0x7fffffff;
  if (x != x) return x + x;
  if (ix > 0x3ff00000 || (ix == 0x3ff00000 && lx != 0)) return nan_value(); /* |x| > 1 */
  if (ix == 0x3ff00000) return x > 0 ? -neg_inf() : neg_inf();
  if (ix < 0x3e300000 && (huge + x) > zero) return x; /* |x| < 2^-28 */
  x = with_high_word(x, (uint32_t)ix);                /* |x| */
  if (ix < 0x3fe00000) {                              /* |x| < 0.5 */
    t = x + x;
    t = 0.5 * dm_log1p(t + t * x / (one - x));
  } else {
    t = 0.5 * dm_log1p((x + x) / (one - x));
  }
  return hx >= 0 ? t : -t;
}

/* ---------------------------------------------------------- cbrt and hypot */

static double dm_cbrt(double x) {
  static const uint32_t
      B1 = 715094163, /* (1023 - 1023/3 - 0.03306235651) * 2^20 */
      B2 = 696219795; /* (1023 - 1023/3 - 54/3 - 0.03306235651) * 2^20 */
  static const double
      P0 = 1.87595182427177009643e+00,  /* 0x3FFE03E6, 0x0F61E692 */
      P1 = -1.88497979543377169875e+00, /* 0xBFFE28E0, 0x92F02420 */
      P2 = 1.62142972010535446614e+00,  /* 0x3FF9F160, 0x4A49D6C2 */
      P3 = -7.58397934778766047437e-01, /* 0xBFE844CB, 0xBEE751D9 */
      P4 = 1.45996192886612446982e-01;  /* 0x3FC2B000, 0xD4E4EDD7 */
  int32_t hx;
  double r, s, t = 0.0, w;
  uint32_t sign, high, low;
  uint64_t bits;

  EXTRACT_WORDS(hx, low, x);
  sign = (uint32_t)hx & 0x80000000u;
  hx = (int32_t)((uint32_t)hx ^ sign);
  if (hx >= 0x7ff00000) return x + x; /* NaN, Inf */
  if (hx < 0x00100000) {              /* zero or subnormal */
    if ((hx | (int32_t)low) == 0) return x;
    t = from_words(0x43500000, 0); /* 2^54 */
    t *= x;
    high = (uint32_t)high_word(t);
    t = from_words(sign | ((high & 0x7fffffff) / 3 + B2), 0);
  } else {
    t = from_words(sign | ((uint32_t)hx / 3 + B1), 0);
  }

  /* cbrt to 23 bits: t * P(t^3 / x) */
  r = (t * t) * (t / x);
  t = t * ((P0 + r * (P1 + r * P2)) + ((r * r) * r) * (P3 + r * P4));

  /* round t away from zero to 23 bits */
  bits = d2u(t);
  bits = (bits + 0x80000000ull) & 0xffffffffc0000000ull;
  t = u2d(bits);

  /* one Newton step to 53 bits, error < 0.667 ulp */
  s = t * t;
  r = x / s;
  w = t + t;
  r = (r - t) / (w + r);
  t = t + t * r;
  return t;
}

static double dm_hypot(double x, double y) {
  double a, b, t1, t2, y1, y2, w;
  int32_t j, k, ha, hb;

  ha = high_word(x) & 0x7fffffff;
  hb = high_word(y) & 0x7fffffff;
  if (hb > ha) {
    a = y;
    b = x;
    j = ha;
    ha = hb;
    hb = j;
  } else {
    a = x;
    b = y;
  }
  a = fabs(a);
  b = fabs(b);
  if (ha >= 0x7ff00000 || hb >= 0x7ff00000) { /* Inf or NaN: Inf wins over NaN */
    if (isinf(a) || isinf(b)) return u2d(0x7ff0000000000000ull);
    return a + b;
  }
  if ((ha - hb) > 0x3c00000) return a + b; /* a / b > 2^60 */
  k = 0;
  if (ha > 0x5f300000) { /* a > 2^500: scale by 2^-600 */
    ha -= 0x25800000;
    hb -= 0x25800000;
    k += 600;
    a = with_high_word(a, (uint32_t)ha);
    b = with_high_word(b, (uint32_t)hb);
  }
  if (hb < 0x20b00000) {     /* b < 2^-500 */
    if (hb <= 0x000fffff) { /* subnormal b or 0 */
      if ((hb | (int32_t)low_word(b)) == 0) return a;
      t1 = from_words(0x7fd00000, 0); /* 2^1022 */
      b *= t1;
      a *= t1;
      k -= 1022;
    } else { /* scale by 2^600 */
      ha += 0x25800000;
      hb += 0x25800000;
      k -= 600;
      a = with_high_word(a, (uint32_t)ha);
      b = with_high_word(b, (uint32_t)hb);
    }
  }
  w = a - b;
  if (w > b) {
    t1 = from_words((uint32_t)ha, 0);
    t2 = a - t1;
    w = sqrt(t1 * t1 - (b * (-b) - t2 * (a + t1)));
  } else {
    a = a + a;
    y1 = from_words((uint32_t)hb, 0);
    y2 = b - y1;
    t1 = from_words((uint32_t)(ha + 0x00100000), 0);
    t2 = a - t1;
    w = sqrt(t1 * y1 - (w * (-w) - (t1 * y2 + t2 * b)));
  }
  if (k != 0) {
    t1 = from_words((uint32_t)(0x3ff00000 + shl20(k)), 0);
    return t1 * w;
  }
  return w;
}

/* ------------------------------------------------------------ public API */

const char* trech_dmath_id(void) { return TRECH_DMATH_ID; }

double trech_dmath_sin(double x) { return canonical(dm_sin(x)); }
double trech_dmath_cos(double x) { return canonical(dm_cos(x)); }
double trech_dmath_tan(double x) { return canonical(dm_tan(x)); }
double trech_dmath_asin(double x) { return canonical(dm_asin(x)); }
double trech_dmath_acos(double x) { return canonical(dm_acos(x)); }
double trech_dmath_atan(double x) { return canonical(dm_atan(x)); }
double trech_dmath_atan2(double y, double x) { return canonical(dm_atan2(y, x)); }
double trech_dmath_exp(double x) { return canonical(dm_exp(x)); }
double trech_dmath_expm1(double x) { return canonical(dm_expm1(x)); }
double trech_dmath_log(double x) { return canonical(dm_log(x)); }
double trech_dmath_log1p(double x) { return canonical(dm_log1p(x)); }
double trech_dmath_log2(double x) { return canonical(dm_log2(x)); }
double trech_dmath_log10(double x) { return canonical(dm_log10(x)); }
double trech_dmath_pow(double x, double y) { return canonical(dm_pow(x, y)); }
double trech_dmath_sinh(double x) { return canonical(dm_sinh(x)); }
double trech_dmath_cosh(double x) { return canonical(dm_cosh(x)); }
double trech_dmath_tanh(double x) { return canonical(dm_tanh(x)); }
double trech_dmath_asinh(double x) { return canonical(dm_asinh(x)); }
double trech_dmath_acosh(double x) { return canonical(dm_acosh(x)); }
double trech_dmath_atanh(double x) { return canonical(dm_atanh(x)); }
double trech_dmath_cbrt(double x) { return canonical(dm_cbrt(x)); }
double trech_dmath_hypot(double x, double y) { return canonical(dm_hypot(x, y)); }
