// Deterministic host math: cross-host identity, IEEE special cases, accuracy guard, and the
// QuickJS routing of Math.* and `**` through it (include/trech/js/DeterministicMath.h).
//
// The golden digests below are FNV-1a 64 over the output bits of every function on a fixed
// pseudo-random input set. They are the portable contract: any platform, compiler or C
// library must reproduce them exactly. A mismatch means hook-layer math no longer replays
// byte for byte across hosts (or the implementation changed: then bump TRECH_DMATH_ID and
// re-record the goldens deliberately).
//
// Define TRECH_DMATH_STANDALONE to build only the library checks (no QuickJS), for example to
// confirm the goldens on another architecture:
//   cc -std=c11 -O2 -ffp-contract=off -Iinclude -c src/js/DeterministicMath.c -o dm.o
//   c++ -std=c++17 -O2 -ffp-contract=off -DTRECH_DMATH_STANDALONE -Iinclude \
//       tests/test_deterministic_math.cpp dm.o -o dmath_check
#include "trech/js/DeterministicMath.h"
#ifndef TRECH_DMATH_STANDALONE
#include "trech/js/JsRuntime.hpp"
#include "TemporaryDirectory.hpp"
#endif

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

#ifndef TRECH_DMATH_STANDALONE
#include <nlohmann/json.hpp>
#endif

namespace {

int failures = 0;

void expect(bool condition, const std::string& message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << "\n";
    ++failures;
  }
}

std::uint64_t bitsOf(double value) {
  std::uint64_t bits = 0;
  std::memcpy(&bits, &value, sizeof bits);
  return bits;
}

double fromBits(std::uint64_t bits) {
  double value = 0.0;
  std::memcpy(&value, &bits, sizeof value);
  return value;
}

std::string hex(std::uint64_t value) {
  char buffer[17];
  std::snprintf(buffer, sizeof buffer, "%016llx", static_cast<unsigned long long>(value));
  return buffer;
}

struct XorShift {
  std::uint64_t state;
  std::uint64_t next() {
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return state;
  }
  double unit() { return static_cast<double>(next() >> 11) * (1.0 / 9007199254740992.0); }
  double anyFinite() {
    for (;;) {
      const double value = fromBits(next());
      if (std::isfinite(value)) return value;
    }
  }
};

struct Fnv {
  std::uint64_t hash = 1469598103934665603ull;
  void add(double value) {
    std::uint64_t bits = bitsOf(value);
    for (int i = 0; i < 8; ++i) {
      hash ^= (bits >> (8 * i)) & 0xffu;
      hash *= 1099511628211ull;
    }
  }
};

// Ordered distance in ulps between two finite doubles (or both NaN).
double ulpDistance(double a, double b) {
  if (std::isnan(a) && std::isnan(b)) return 0.0;
  if (std::isnan(a) || std::isnan(b)) return std::numeric_limits<double>::infinity();
  if (a == b) return 0.0;
  const auto ordered = [](double v) {
    const auto i = static_cast<std::int64_t>(bitsOf(v));
    return i < 0 ? static_cast<std::int64_t>(0x8000000000000000ull) - i : i;
  };
  return std::fabs(static_cast<double>(ordered(a) - ordered(b)));
}

constexpr int kSamples = 4096;
constexpr std::uint64_t kCanonicalNaN = 0x7ff8000000000000ull;

struct Unary {
  const char* name;
  double (*dm)(double);
  double (*ref)(double);
  double lo, hi;
  double maxUlp;  // loose guard against the platform libm; fdlibm is < 1 ulp from the truth
  std::uint64_t golden;
};

struct Binary {
  const char* name;
  double (*dm)(double, double);
  double (*ref)(double, double);
  double maxUlp;
  std::uint64_t golden;
};

void checkUnary(const Unary& f) {
  XorShift rng{0x9E3779B97F4A7C15ull};
  for (const char* c = f.name; *c; ++c) rng.state = rng.state * 31 + static_cast<unsigned char>(*c);
  Fnv digest;
  double worst = 0.0, worstX = 0.0;
  for (int i = 0; i < kSamples; ++i) {
    const bool wide = (i % 4) == 3;
    const double x = wide ? rng.anyFinite() : f.lo + (f.hi - f.lo) * rng.unit();
    const double y = f.dm(x);
    digest.add(y);
    if (!wide) {
      const double d = ulpDistance(y, f.ref(x));
      if (d > worst) {
        worst = d;
        worstX = x;
      }
    }
  }
  expect(worst <= f.maxUlp, std::string(f.name) + " differs from the platform libm by " +
                                std::to_string(worst) + " ulp at x=" + hex(bitsOf(worstX)));
  expect(digest.hash == f.golden, std::string(f.name) + " digest " + hex(digest.hash) +
                                      " != golden " + hex(f.golden) +
                                      " (cross-host identity broken)");
}

void checkBinary(const Binary& f) {
  XorShift rng{0x243F6A8885A308D3ull};
  for (const char* c = f.name; *c; ++c) rng.state = rng.state * 31 + static_cast<unsigned char>(*c);
  Fnv digest;
  double worst = 0.0;
  for (int i = 0; i < kSamples; ++i) {
    const bool wide = (i % 4) == 3;
    double x, y;
    if (wide) {
      x = rng.anyFinite();
      y = rng.anyFinite();
    } else if (std::strcmp(f.name, "pow") == 0) {
      // Inputs come from trech_dmath too: a libm-derived input would differ across hosts.
      x = trech_dmath_exp((rng.unit() * 2 - 1) * 20);
      y = (rng.unit() * 2 - 1) * 30;
      if (i % 7 == 0) {
        x = -x;
        y = std::floor(y);
      }
    } else {
      x = (rng.unit() * 2 - 1) * trech_dmath_exp((rng.unit() * 2 - 1) * 40);
      y = (rng.unit() * 2 - 1) * trech_dmath_exp((rng.unit() * 2 - 1) * 40);
    }
    const double r = f.dm(x, y);
    digest.add(r);
    if (!wide) worst = std::max(worst, ulpDistance(r, f.ref(x, y)));
  }
  expect(worst <= f.maxUlp, std::string(f.name) + " differs from the platform libm by " +
                                std::to_string(worst) + " ulp");
  expect(digest.hash == f.golden, std::string(f.name) + " digest " + hex(digest.hash) +
                                      " != golden " + hex(f.golden) +
                                      " (cross-host identity broken)");
}

void expectBits(const char* what, double got, std::uint64_t want) {
  expect(bitsOf(got) == want, std::string(what) + " = " + hex(bitsOf(got)) + ", want " + hex(want));
}

void checkSpecialCases() {
  const double inf = std::numeric_limits<double>::infinity();
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double oddNaN = fromBits(0xfff4000000000123ull);  // negative, signalling-style payload

  // Every NaN result is the one canonical quiet NaN, whatever the input payload/sign.
  expectBits("sin(Inf)", trech_dmath_sin(inf), kCanonicalNaN);
  expectBits("sin(odd NaN)", trech_dmath_sin(oddNaN), kCanonicalNaN);
  expectBits("log(-1)", trech_dmath_log(-1.0), kCanonicalNaN);
  expectBits("acosh(0.5)", trech_dmath_acosh(0.5), kCanonicalNaN);
  expectBits("pow(-8, 1/3)", trech_dmath_pow(-8.0, 1.0 / 3.0), kCanonicalNaN);
  expectBits("atan2(NaN, 1)", trech_dmath_atan2(oddNaN, 1.0), kCanonicalNaN);
  expectBits("asin(2)", trech_dmath_asin(2.0), kCanonicalNaN);

  // Exact and signed-zero results.
  expectBits("exp(1)", trech_dmath_exp(1.0), 0x4005bf0a8b145769ull);
  expectBits("sin(-0)", trech_dmath_sin(-0.0), bitsOf(-0.0));
  expectBits("tan(-0)", trech_dmath_tan(-0.0), bitsOf(-0.0));
  expectBits("cbrt(-0)", trech_dmath_cbrt(-0.0), bitsOf(-0.0));
  expect(trech_dmath_log(1.0) == 0.0 && !std::signbit(trech_dmath_log(1.0)), "log(1) = +0");
  expect(trech_dmath_cos(0.0) == 1.0, "cos(0) = 1");
  expect(trech_dmath_cbrt(27.0) == 3.0, "cbrt(27) = 3");
  expect(trech_dmath_log2(1024.0) == 10.0, "log2(1024) = 10");
  expect(trech_dmath_log10(1000.0) == 3.0, "log10(1000) = 3");
  expect(trech_dmath_pow(2.0, 10.0) == 1024.0, "pow(2, 10) = 1024");
  expect(trech_dmath_pow(-2.0, 3.0) == -8.0, "pow(-2, 3) = -8");
  expect(trech_dmath_pow(1.0, nan) == 1.0 && trech_dmath_pow(nan, 0.0) == 1.0,
         "C99 pow(1, NaN) = pow(NaN, 0) = 1 (JavaScript's NaN cases stay in the engine)");
  expect(trech_dmath_pow(0.0, -1.0) == inf && trech_dmath_pow(-0.0, -1.0) == -inf,
         "pow(+-0, -1) = +-Inf");
  expect(trech_dmath_hypot(3.0, 4.0) == 5.0, "hypot(3, 4) = 5");
  expect(trech_dmath_hypot(inf, nan) == inf && trech_dmath_hypot(nan, -inf) == inf,
         "hypot(Inf, NaN) = Inf");
  expect(trech_dmath_atan2(0.0, -0.0) == 3.141592653589793 &&
             trech_dmath_atan2(-0.0, -0.0) == -3.141592653589793,
         "atan2(+-0, -0) = +-pi");
  expect(trech_dmath_log(0.0) == -inf && trech_dmath_atanh(1.0) == inf &&
             trech_dmath_atanh(-1.0) == -inf,
         "log(0) = -Inf, atanh(+-1) = +-Inf");
  expect(trech_dmath_tanh(inf) == 1.0 && trech_dmath_tanh(-inf) == -1.0 &&
             trech_dmath_expm1(-inf) == -1.0 && trech_dmath_exp(-inf) == 0.0,
         "tanh(+-Inf), expm1(-Inf), exp(-Inf)");
  expect(trech_dmath_exp(710.0) == inf && trech_dmath_exp(-746.0) == 0.0, "exp overflow/underflow");
  expect(trech_dmath_sinh(-711.0) == -inf && trech_dmath_cosh(711.0) == inf, "sinh/cosh overflow");

  // Payne-Hanek reduction: the classic huge-argument values are correctly rounded.
  expect(trech_dmath_sin(1e22) == -0.8522008497671888, "sin(1e22)");
  expect(trech_dmath_cos(1e22) == 0.523214785395139, "cos(1e22)");
  expect(trech_dmath_sin(1.7976931348623157e308) == 0.004961954789184062, "sin(DBL_MAX)");
  expect(std::string(trech_dmath_id()) == TRECH_DMATH_ID, "implementation identity");
}

#ifndef TRECH_DMATH_STANDALONE
// QuickJS evaluates Math.* and `**` through trech_dmath, bit for bit.
void checkQuickJsRouting() {
  const trech::test::TemporaryDirectory fixture("trech_deterministic_math");
  const auto script = fixture.path() / "math_routing.js";
  {
    std::ofstream out(script);
    out << R"JS(
const view = new DataView(new ArrayBuffer(8));
function bits(x) {
  view.setFloat64(0, x);
  let s = "";
  for (let i = 0; i < 8; i++) s += (view.getUint8(i) + 0x100).toString(16).slice(1);
  return s;
}
const unary = ["sin", "cos", "tan", "asin", "acos", "atan", "exp", "expm1", "log", "log1p",
               "log2", "log10", "sinh", "cosh", "tanh", "asinh", "acosh", "atanh", "cbrt"];
const rows = [];
for (let i = 0; i < 64; i++) {
  const x = ((i * 0.7919) % 11) - 5.5 + i * 1.0e-3;
  for (const name of unary) {
    const arg = name === "asin" || name === "acos" || name === "atanh" ? x / 6
              : name.startsWith("log") ? Math.abs(x) + 1.0e-3
              : name === "acosh" ? Math.abs(x) + 1 : x;
    rows.push([name, bits(arg), "", bits(Math[name](arg))]);
  }
  const base = Math.abs(x) + 1.0e-3, e = (((i * 5) % 64) * 0.7919 % 11 - 5.5) / 2;
  rows.push(["pow", bits(base), bits(e), bits(Math.pow(base, e))]);
  rows.push(["**", bits(base), bits(e), bits(base ** e)]);
  rows.push(["atan2", bits(x), bits(e), bits(Math.atan2(x, e))]);
  rows.push(["hypot", bits(x), bits(e), bits(Math.hypot(x, e))]);
}
globalThis.TRECH_CONFIG = {run: {nEvents: 1}, hooks: {inputs: {dmath: rows}}};
)JS";
  }
  trech::JsRuntime js;
  const auto config = nlohmann::json::parse(js.evalExperimentAndGetConfigJson(script.string()));
  const auto& rows = config.at("hooks").at("inputs").at("dmath");
  const auto parse = [](const std::string& h) { return fromBits(std::stoull(h, nullptr, 16)); };
  struct Named1 { const char* name; double (*fn)(double); };
  const Named1 unary[] = {
      {"sin", trech_dmath_sin},     {"cos", trech_dmath_cos},     {"tan", trech_dmath_tan},
      {"asin", trech_dmath_asin},   {"acos", trech_dmath_acos},   {"atan", trech_dmath_atan},
      {"exp", trech_dmath_exp},     {"expm1", trech_dmath_expm1}, {"log", trech_dmath_log},
      {"log1p", trech_dmath_log1p}, {"log2", trech_dmath_log2},   {"log10", trech_dmath_log10},
      {"sinh", trech_dmath_sinh},   {"cosh", trech_dmath_cosh},   {"tanh", trech_dmath_tanh},
      {"asinh", trech_dmath_asinh}, {"acosh", trech_dmath_acosh}, {"atanh", trech_dmath_atanh},
      {"cbrt", trech_dmath_cbrt}};
  int checked = 0, mismatched = 0;
  for (const auto& row : rows) {
    const auto name = row.at(0).get<std::string>();
    const double x = parse(row.at(1).get<std::string>());
    const std::uint64_t got = std::stoull(row.at(3).get<std::string>(), nullptr, 16);
    double want = std::numeric_limits<double>::quiet_NaN();
    if (name == "pow" || name == "**") {
      want = trech_dmath_pow(x, parse(row.at(2).get<std::string>()));
    } else if (name == "atan2") {
      want = trech_dmath_atan2(x, parse(row.at(2).get<std::string>()));
    } else if (name == "hypot") {
      want = trech_dmath_hypot(x, parse(row.at(2).get<std::string>()));
    } else {
      for (const auto& f : unary) {
        if (name == f.name) want = f.fn(x);
      }
    }
    ++checked;
    if (got != bitsOf(want)) {
      if (mismatched++ < 5) {
        std::cerr << "QuickJS " << name << "(" << row.at(1).get<std::string>() << ") = "
                  << hex(got) << ", trech_dmath = " << hex(bitsOf(want)) << "\n";
      }
    }
  }
  expect(checked == 64 * 23, "Expected every QuickJS routing row.");
  expect(mismatched == 0, "QuickJS Math.* / ** must evaluate through trech_dmath bit for bit (" +
                              std::to_string(mismatched) + " mismatches).");
}
#endif

}  // namespace

int main() {
  const Unary unary[] = {
      {"sin", trech_dmath_sin, [](double x) { return std::sin(x); }, -20, 20, 2,
       0xf950c0718dce35eeull},
      {"cos", trech_dmath_cos, [](double x) { return std::cos(x); }, -20, 20, 2,
       0x1c595e3854f12c9cull},
      {"tan", trech_dmath_tan, [](double x) { return std::tan(x); }, -20, 20, 4,
       0x6a8cf28866388275ull},
      {"asin", trech_dmath_asin, [](double x) { return std::asin(x); }, -1, 1, 2,
       0x7223dffda7f2878eull},
      {"acos", trech_dmath_acos, [](double x) { return std::acos(x); }, -1, 1, 2,
       0x6f87272125ffa1c3ull},
      {"atan", trech_dmath_atan, [](double x) { return std::atan(x); }, -20, 20, 2,
       0x8eab3457fa220309ull},
      {"exp", trech_dmath_exp, [](double x) { return std::exp(x); }, -745, 709, 2,
       0x72084fd86b549011ull},
      {"expm1", trech_dmath_expm1, [](double x) { return std::expm1(x); }, -40, 709, 2,
       0x64c96b37a60f0ccaull},
      {"log", trech_dmath_log, [](double x) { return std::log(x); }, 0, 1e6, 2,
       0x663f6fcd75883ac9ull},
      {"log1p", trech_dmath_log1p, [](double x) { return std::log1p(x); }, -1, 10, 2,
       0x3e294495395e058aull},
      {"log2", trech_dmath_log2, [](double x) { return std::log2(x); }, 0, 1e6, 2,
       0xdc966d06a729e6a2ull},
      {"log10", trech_dmath_log10, [](double x) { return std::log10(x); }, 0, 1e6, 3,
       0x1f75ed4425b293ccull},
      {"sinh", trech_dmath_sinh, [](double x) { return std::sinh(x); }, -712, 712, 3,
       0xe7dfb83bea0ba90eull},
      {"cosh", trech_dmath_cosh, [](double x) { return std::cosh(x); }, -712, 712, 3,
       0x8c526ded799b0590ull},
      {"tanh", trech_dmath_tanh, [](double x) { return std::tanh(x); }, -25, 25, 3,
       0xc0d9f025c1f6d29aull},
      {"asinh", trech_dmath_asinh, [](double x) { return std::asinh(x); }, -50, 50, 3,
       0xf7bd4e90b6b5a1d4ull},
      {"acosh", trech_dmath_acosh, [](double x) { return std::acosh(x); }, 1, 50, 3,
       0xdfa110d7b32c001eull},
      {"atanh", trech_dmath_atanh, [](double x) { return std::atanh(x); }, -1, 1, 3,
       0x3e615194275ede03ull},
      {"cbrt", trech_dmath_cbrt, [](double x) { return std::cbrt(x); }, -1e6, 1e6, 2,
       0x4a00968eb9e43161ull},
  };
  const Binary binary[] = {
      {"pow", trech_dmath_pow, [](double x, double y) { return std::pow(x, y); }, 2,
       0xa4ac0207dd1eee8full},
      {"atan2", trech_dmath_atan2, [](double y, double x) { return std::atan2(y, x); }, 2,
       0x1e832240feed4e01ull},
      {"hypot", trech_dmath_hypot, [](double x, double y) { return std::hypot(x, y); }, 2,
       0x2af482de47fcd7f8ull},
  };
  for (const auto& f : unary) checkUnary(f);
  for (const auto& f : binary) checkBinary(f);
  checkSpecialCases();
#ifndef TRECH_DMATH_STANDALONE
  try {
    checkQuickJsRouting();
  } catch (const std::exception& ex) {
    expect(false, std::string("QuickJS routing check threw: ") + ex.what());
  }
#endif
  if (failures != 0) {
    std::cerr << failures << " deterministic math check(s) failed\n";
    return 1;
  }
  std::cout << "deterministic math: all checks passed (" << TRECH_DMATH_ID << ")\n";
  return 0;
}
