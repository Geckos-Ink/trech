#include "trech/core/FormalLaws.hpp"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace trech {
namespace formal {
namespace {

LawCheck start(const std::string& law, const std::string& lean, const char* kind, double tolerance) {
  LawCheck check;
  check.law = law;
  check.leanDeclaration = lean;
  check.kind = kind;
  check.tolerance = tolerance;
  return check;
}

void note(LawCheck& check, double error, const std::string& what) {
  if (!(error <= check.maxAbsError)) check.maxAbsError = error;  // NaN propagates as a violation
  ++check.violations;
  if (check.detail.empty()) check.detail = what;
}

void track(LawCheck& check, double error) {
  if (error > check.maxAbsError) check.maxAbsError = error;
}

LawCheck finish(LawCheck check) {
  check.passed = check.violations == 0 && std::isfinite(check.maxAbsError);
  return check;
}

}  // namespace

nlohmann::json LawCheck::toJson() const {
  return {{"law", law},
          {"lean_declaration", leanDeclaration},
          {"lean_status", "not_checked_by_this_check"},
          {"kind", kind},
          {"samples", samples},
          {"violations", violations},
          {"max_abs_error", maxAbsError},
          {"tolerance", tolerance},
          {"passed", passed},
          {"detail", detail}};
}

double compensatedSum(const double* values, std::size_t count) {
  double sum = 0.0, carry = 0.0;
  for (std::size_t i = 0; i < count; ++i) {
    const double x = values[i], t = sum + x;
    carry += std::abs(sum) >= std::abs(x) ? (sum - t) + x : (x - t) + sum;
    sum = t;
  }
  return sum + carry;
}

LawCheck checkConservedTotal(const std::string& law, const std::string& lean,
                             const std::vector<double>& before, const std::vector<double>& after,
                             double relativeTolerance) {
  LawCheck check = start(law, lean, "invariant", relativeTolerance);
  check.samples = 1;
  const double b = compensatedSum(before.data(), before.size());
  const double a = compensatedSum(after.data(), after.size());
  const double error = std::abs(a - b) / std::max(1.0, std::abs(b));
  if (!(error <= relativeTolerance)) {
    std::ostringstream what;
    what.precision(17);
    what << "total " << b << " became " << a;
    note(check, error, what.str());
  } else {
    track(check, error);
  }
  return finish(check);
}

LawCheck checkWithinBounds(const std::string& law, const std::string& lean,
                           const std::vector<double>& values, const std::vector<double>& lower,
                           const std::vector<double>& upper, double tolerance) {
  LawCheck check = start(law, lean, "invariant", tolerance);
  if (lower.size() != values.size() || upper.size() != values.size()) {
    note(check, 0.0, "bound arrays do not match the sample count");
    return finish(check);
  }
  check.samples = values.size();
  for (std::size_t i = 0; i < values.size(); ++i) {
    const double below = lower[i] - values[i], above = values[i] - upper[i];
    const double error = std::max({0.0, below, above});
    if (!std::isfinite(values[i]) || error > tolerance) {
      std::ostringstream what;
      what.precision(17);
      what << "sample " << i << " = " << values[i] << " outside [" << lower[i] << ", " << upper[i] << "]";
      note(check, std::isfinite(values[i]) ? error : NAN, what.str());
    } else {
      track(check, error);
    }
  }
  return finish(check);
}

LawCheck checkProbabilityVector(const std::string& law, const std::string& lean,
                                const std::vector<double>& probabilities, double tolerance) {
  LawCheck check = start(law, lean, "invariant", tolerance);
  check.samples = probabilities.size();
  for (std::size_t i = 0; i < probabilities.size(); ++i) {
    const double p = probabilities[i];
    if (!std::isfinite(p) || p < -tolerance) {
      note(check, std::isfinite(p) ? -p : NAN, "entry " + std::to_string(i) + " is negative or non-finite");
    } else if (p < 0) {
      track(check, -p);
    }
  }
  const double error = std::abs(compensatedSum(probabilities.data(), probabilities.size()) - 1.0);
  if (!(error <= tolerance)) note(check, error, "probabilities do not sum to 1");
  else track(check, error);
  return finish(check);
}

LawCheck checkAgreement(const std::string& law, const std::string& lean, const std::vector<double>& a,
                        const std::vector<double>& b, double absTolerance, double relTolerance) {
  LawCheck check = start(law, lean, "agreement", absTolerance);
  if (a.size() != b.size()) {
    note(check, 0.0, "implementations returned different sample counts");
    return finish(check);
  }
  check.samples = a.size();
  for (std::size_t i = 0; i < a.size(); ++i) {
    const double error = std::abs(a[i] - b[i]);
    const double allowed = absTolerance + relTolerance * std::max(std::abs(a[i]), std::abs(b[i]));
    if (!(error <= allowed)) {
      std::ostringstream what;
      what.precision(17);
      what << "sample " << i << ": " << a[i] << " vs " << b[i];
      note(check, error, what.str());
    } else {
      track(check, error);
    }
  }
  return finish(check);
}

LawCheck checkPermutation(const std::string& law, const std::string& lean, const int32_t* map,
                          std::size_t count) {
  LawCheck check = start(law, lean, "hypothesis", 0.0);
  check.samples = count;
  std::vector<unsigned char> hit(count, 0);
  for (std::size_t k = 0; k < count; ++k) {
    const int32_t target = map[k];
    if (target < 0 || static_cast<std::size_t>(target) >= count) {
      note(check, 0.0, "link " + std::to_string(k) + " maps outside the lattice");
    } else if (hit[static_cast<std::size_t>(target)]++) {
      note(check, 0.0, "slot " + std::to_string(target) + " is the source of two links");
    }
  }
  return finish(check);
}

LawCheck checkInvolution(const std::string& law, const std::string& lean, const int32_t* map,
                         std::size_t count) {
  LawCheck check = start(law, lean, "hypothesis", 0.0);
  check.samples = count;
  for (std::size_t k = 0; k < count; ++k) {
    const int32_t target = map[k];
    if (target < 0 || static_cast<std::size_t>(target) >= count ||
        map[static_cast<std::size_t>(target)] != static_cast<int32_t>(k)) {
      note(check, 0.0, "entry " + std::to_string(k) + " is not its opposite's opposite");
    }
  }
  return finish(check);
}

LawCheck checkVelocityMoments(const std::string& law, const std::string& lean, std::size_t q,
                              const double* cx, const double* cy, const double* cz, const double* w,
                              double cs2, int dimensions, double tolerance) {
  LawCheck check = start(law, lean, "hypothesis", tolerance);
  const double* axes[3] = {cx, cy, cz};
  auto moment = [&](const double* a, const double* b) {
    std::vector<double> terms(q);
    for (std::size_t k = 0; k < q; ++k) terms[k] = w[k] * (a ? a[k] : 1.0) * (b ? b[k] : 1.0);
    return compensatedSum(terms.data(), q);
  };
  auto expect = [&](double value, double target, const std::string& what) {
    ++check.samples;
    const double error = std::abs(value - target);
    if (!(error <= tolerance)) note(check, error, what);
    else track(check, error);
  };
  expect(moment(nullptr, nullptr), 1.0, "sum w != 1");
  static const char* names[3] = {"x", "y", "z"};
  for (int a = 0; a < 3; ++a) {
    expect(moment(axes[a], nullptr), 0.0, std::string("sum w c_") + names[a] + " != 0");
    for (int b = a; b < 3; ++b)
      expect(moment(axes[a], axes[b]), a == b && a < dimensions ? cs2 : 0.0,
             std::string("sum w c_") + names[a] + " c_" + names[b] + " != cs2 delta");
  }
  return finish(check);
}

}  // namespace formal
}  // namespace trech
