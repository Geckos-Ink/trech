#include "trech/core/FormalLaws.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <tuple>

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

namespace {

#ifndef TRECH_FORMAL_MANIFEST_SHA256
#define TRECH_FORMAL_MANIFEST_SHA256 ""
#endif
#ifndef TRECH_FORMAL_SOURCES_SHA256
#define TRECH_FORMAL_SOURCES_SHA256 ""
#endif

struct Merged {
  LawCheck check;
  std::size_t count = 0;
  std::string failingDetail, passingDetail;
};

std::mutex& runMutex() {
  static std::mutex m;
  return m;
}
std::map<std::tuple<std::string, std::string, std::string>, Merged>& runChecks() {
  static std::map<std::tuple<std::string, std::string, std::string>, Merged> m;
  return m;
}

void keepFirst(std::string& slot, const std::string& detail) {
  if (!detail.empty() && (slot.empty() || detail < slot)) slot = detail;
}

}  // namespace

void recordRunCheck(const LawCheck& check, const std::string& origin) {
  std::lock_guard<std::mutex> lock(runMutex());
  Merged& m = runChecks()[{origin, check.law, check.leanDeclaration}];
  if (m.count == 0) {
    m.check = check;
    m.check.samples = 0;
    m.check.violations = 0;
    m.check.maxAbsError = 0.0;
    m.check.tolerance = 0.0;
    m.check.passed = true;
  }
  ++m.count;
  m.check.samples += check.samples;
  m.check.violations += check.violations;
  if (!(check.maxAbsError <= m.check.maxAbsError)) m.check.maxAbsError = check.maxAbsError;  // NaN sticks
  m.check.tolerance = std::max(m.check.tolerance, check.tolerance);
  m.check.passed = m.check.passed && check.passed;
  keepFirst(check.passed ? m.passingDetail : m.failingDetail, check.detail);
}

nlohmann::json takeRunChecks() {
  std::lock_guard<std::mutex> lock(runMutex());
  nlohmann::json out = nlohmann::json::array();
  for (auto& [key, m] : runChecks()) {
    m.check.detail = m.failingDetail.empty() ? m.passingDetail : m.failingDetail;
    nlohmann::json record = m.check.toJson();
    record["origin"] = std::get<0>(key);
    record["count"] = m.count;
    out.push_back(std::move(record));
  }
  runChecks().clear();
  return out;
}

const std::string& manifestSha256() {
  static const std::string value = TRECH_FORMAL_MANIFEST_SHA256;
  return value;
}

const std::string& sourcesSha256() {
  static const std::string value = TRECH_FORMAL_SOURCES_SHA256;
  return value;
}

nlohmann::json provenanceBlock(const nlohmann::json& checks, const std::string& auditPath) {
  std::set<std::string> declarations;
  std::size_t failed = 0;
  for (const auto& check : checks) {
    const std::string lean = check.value("lean_declaration", "");
    if (!lean.empty()) declarations.insert(lean);
    if (!check.value("passed", false)) ++failed;
  }
  nlohmann::json block = {{"schema", "trech_formal_provenance_v1"},
                          {"manifest", {{"path", "formal/laws.json"}, {"sha256", manifestSha256()}}},
                          {"sources_sha256", sourcesSha256()},
                          {"declarations", declarations},
                          {"checks", checks.size()},
                          {"failed_checks", failed},
                          {"lean_status", "not_checked_by_this_run"}};
  if (auditPath.empty()) return block;
  nlohmann::json audit;
  {
    std::ifstream in(auditPath);
    if (in) audit = nlohmann::json::parse(in, nullptr, false);
  }
  if (!audit.is_object() || audit.value("schema", "") != "trech_lean_audit_v1") {
    block["lean_status"] = "audit_unreadable";
    block["audit"] = {{"path", auditPath}};
    return block;
  }
  const std::string auditManifest = audit.contains("manifest") ? audit["manifest"].value("sha256", "") : "";
  std::set<std::string> proved;
  if (audit.contains("declarations") && audit["declarations"].is_array())
    for (const auto& d : audit["declarations"])
      if (d.value("standard_only", false)) proved.insert(d.value("name", ""));
  std::vector<std::string> unproved;
  for (const auto& d : declarations)
    if (!proved.count(d)) unproved.push_back(d);
  const std::string auditSources = audit.value("sources_sha256", "");
  const bool matches = !manifestSha256().empty() && auditManifest == manifestSha256() &&
                       !sourcesSha256().empty() && auditSources == sourcesSha256();
  block["audit"] = {{"path", auditPath},
                    {"passed", audit.value("passed", false)},
                    {"lean_version", audit.value("lean_version", "")},
                    {"toolchain", audit.value("toolchain", "")},
                    {"mathlib_revision", audit.value("mathlib_revision", "")},
                    {"manifest_sha256", auditManifest},
                    {"sources_sha256", auditSources},
                    {"matches_manifest", matches},
                    {"modules", audit.value("modules", nlohmann::json::array())},
                    {"declarations_not_proved", unproved}};
  block["lean_status"] = !matches ? "audit_mismatch"
                         : (audit.value("passed", false) && unproved.empty()) ? "audited"
                                                                              : "audit_incomplete";
  return block;
}

}  // namespace formal
}  // namespace trech
