#include "trech/ml/MethodArbiter.hpp"

#include "trech/core/Trace.hpp"
#include "trech/ml/ComputeBudget.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <map>
#include <numeric>
#include <stdexcept>

namespace trech::ml {
namespace {
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
// Lean pair (optional, for validation): Trech.Methods.Arbiter (formal/Trech/Methods/Arbiter.lean)
// proves that the squared error graded below is a strictly proper score for the mean and that
// log(error + floor) keeps the order of errors; tests/test_formal_laws.cpp checks this arbiter.
// Errors are learned as log(error + floor), floor = 1e-6 x the output scale: an absolute
// error regressed by local laws goes negative near zero and would then win every selection;
// the log keeps predicted errors positive and makes the ranking relative.
constexpr double kErrorFloor = 1e-6;
double rmseOf(double sq, double n) { return n > 0 ? std::sqrt(sq / n) : kNaN; }
}  // namespace

struct MethodArbiter::Impl {
  MethodArbiterOptions o;
  std::size_t M = 0, F = 0, K = 1, fallback = 0;
  // One error learner per method: each learns from the elements its method predicts, so a
  // method that covers only part of the elements (or abstains) never blinds the others.
  std::vector<std::unique_ptr<DomainLearner>> learners;
  long calls = 0;
  double floor = kErrorFloor;  // error floor of the latest batch (raw units)
  // Run totals. Own rows: elements the method predicted. Common rows: elements every method
  // predicted (the fair comparison of single methods).
  std::vector<double> sumSq, count, commonSq, selected;
  double common = 0.0, arbitratedSq = 0.0, oracleSq = 0.0, graded = 0.0;
  double learnedSelections = 0.0, totalSelections = 0.0, learnedSq = 0.0, learnedGraded = 0.0, learnedPolicyCalls = 0.0;
  nlohmann::json lastDomains = nlohmann::json::object();
  struct CallRecord { double time, n, arbitratedSq, oracleSq, common; std::vector<double> sq, cnt, commonSq, selected; };
  std::vector<CallRecord> history;
  // Decayed (options.policyForgetting per graded call) squared error and rows of every method
  // (the recent leader has the lowest mean), and the score of the two selection policies.
  std::vector<double> ewSq, ewN;
  // Decayed mean of log(call RMSE) per method (calls where it predicted): the leader ranking,
  // in which each graded call counts equally.
  std::vector<double> ewLog, ewCalls;
  // Decayed prequential RMSE (log units) of each method's error learner: its own uncertainty.
  std::vector<double> learnerSq, learnerW;
  // Decayed sum of log(leader call error / learned call error): each graded call counts equally,
  // so one early transient cannot outweigh many later calls. Positive = learned has been better.
  double policyScore = 0.0;
  // Decayed total squared error of the two policies (0 = recent leader, 1 = learned): the
  // learned policy must also not lose in total, so rare large losses are not traded for many
  // small wins.
  std::array<double, 2> policyTotal{0.0, 0.0};
  bool informative = false;
  bool frozen = false;  // restored for deployment: select and grade, never learn
  double unseenSelections = 0.0;  // run total: elements far from every error law (median prior)
  bool restored = false;  // laws come from an earlier run (fromState)
  std::string tracedLeader;  // engine trace only: last leader reported (never exported)

  // Variance (log units) of a method's error learner; unknown until it has been graded.
  double uncertainty(std::size_t m) const { return learnerW[m] > 0 ? learnerSq[m] / learnerW[m] : std::numeric_limits<double>::infinity(); }
  double toLog(double error) const { return std::log(error + floor); }
  double fromLog(double value) const { return std::isfinite(value) ? std::max(0.0, std::exp(value) - floor) : kNaN; }

  bool predicts(const MethodArbiterBatch& b, std::size_t e, std::size_t m) const {
    for (std::size_t k = 0; k < K; ++k)
      if (!std::isfinite(b.predictions[(e * M + m) * K + k])) return false;
    return true;
  }
  // Squared error of one method for one element, mean over outputs (NaN if not finite).
  double squaredError(const MethodArbiterBatch& b, std::size_t e, std::size_t m) const {
    double sum = 0.0;
    for (std::size_t k = 0; k < K; ++k) {
      const double p = b.predictions[(e * M + m) * K + k], r = b.reference[e * K + k];
      if (!std::isfinite(p) || !std::isfinite(r)) return kNaN;
      sum += (p - r) * (p - r);
    }
    return sum / static_cast<double>(K);
  }
  // Methods by decayed mean error (lowest first); the declared fallback first before evidence.
  std::vector<std::size_t> leaderOrder() const {
    std::vector<std::size_t> order(M);
    std::iota(order.begin(), order.end(), 0);
    auto mean = [&](std::size_t m) { return ewCalls[m] > 0 ? ewLog[m] / ewCalls[m] : std::numeric_limits<double>::infinity(); };
    std::stable_sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
      if (!informative) return a == fallback && b != fallback;
      return mean(a) < mean(b);
    });
    return order;
  }
};

MethodArbiter::MethodArbiter(MethodArbiterOptions options) : impl_(std::make_unique<Impl>()) {
  auto& s = *impl_;
  if (options.methods.empty()) throw std::invalid_argument("method arbiter needs at least one method");
  if (options.features.empty()) throw std::invalid_argument("method arbiter needs at least one context feature");
  if (options.outputs == 0) throw std::invalid_argument("method arbiter needs at least one output");
  if (!(options.policyForgetting > 0.0 && options.policyForgetting <= 1.0))
    throw std::invalid_argument("method arbiter policy forgetting must be in (0, 1]");
  s.o = std::move(options);
  s.M = s.o.methods.size(); s.F = s.o.features.size(); s.K = s.o.outputs;
  if (!s.o.fallback.empty()) {
    const auto it = std::find(s.o.methods.begin(), s.o.methods.end(), s.o.fallback);
    if (it == s.o.methods.end()) throw std::invalid_argument("method arbiter fallback is not a candidate");
    s.fallback = static_cast<std::size_t>(it - s.o.methods.begin());
  }
  for (auto* v : {&s.sumSq, &s.count, &s.commonSq, &s.selected, &s.ewSq, &s.ewN, &s.ewLog, &s.ewCalls, &s.learnerSq, &s.learnerW}) v->assign(s.M, 0.0);
  for (std::size_t m = 0; m < s.M; ++m) {
    DomainLearnerOptions lo;
    lo.features = s.o.features;
    lo.targets = {"log_error_" + s.o.methods[m]};
    lo.seed = s.o.seed + m; lo.minElements = s.o.minElements; lo.forgetting = s.o.forgetting;
    lo.budget = hostComputeBudget(); lo.capacity = learnerCapacity(lo.budget, s.F, 1);
    s.learners.push_back(std::make_unique<DomainLearner>(lo));
  }
}

MethodArbiter::~MethodArbiter() = default;
MethodArbiter::MethodArbiter(MethodArbiter&&) noexcept = default;
MethodArbiter& MethodArbiter::operator=(MethodArbiter&&) noexcept = default;
const MethodArbiterOptions& MethodArbiter::options() const { return impl_->o; }

MethodArbiterResult MethodArbiter::step(const MethodArbiterBatch& b) {
  MethodArbiterResult r = stepUntraced(b);
  if (!trace::active()) return r;
  auto& s = *impl_;
  std::map<std::string, std::size_t> chosen;
  std::size_t learned = 0, unchosen = 0;
  for (std::size_t e = 0; e < r.selection.size(); ++e) {
    const int k = r.selection[e];
    if (k < 0) { ++unchosen; continue; }
    chosen[s.o.methods[static_cast<std::size_t>(k)]] += 1;
    if (e < r.learned.size() && r.learned[e]) ++learned;
  }
  if (trace::enabled(trace::Level::Debug, "arbiter")) {
    nlohmann::json rmse = nlohmann::json::object();
    for (std::size_t m = 0; m < s.M && m < r.callRmse.size(); ++m)
      if (std::isfinite(r.callRmse[m])) rmse[s.o.methods[m]] = r.callRmse[m];
    nlohmann::json data = {{"call", s.calls}, {"methods", s.o.methods}, {"policy", r.policy},
                           {"leader", r.leader}, {"elements", r.selection.size()},
                           {"selected", chosen}, {"selected_from_learned_errors", learned},
                           {"unpredicted", unchosen}, {"graded", r.graded},
                           {"frozen", s.frozen}};
    if (r.graded) {
      data["arbitrated_rmse"] = r.arbitratedRmse;
      data["oracle_rmse"] = r.oracleRmse;
      data["method_rmse"] = rmse;
    }
    trace::record(trace::Level::Debug, "arbiter", "method arbiter step", std::move(data));
  }
  if (r.leader != s.tracedLeader) {
    trace::record(trace::Level::Info, "arbiter",
                  s.tracedLeader.empty() ? "method arbiter leader" : "method arbiter leader changed",
                  {{"call", s.calls}, {"from", s.tracedLeader}, {"to", r.leader}, {"policy", r.policy},
                   {"methods", s.o.methods}});
    s.tracedLeader = r.leader;
  }
  return r;
}

MethodArbiterResult MethodArbiter::stepUntraced(const MethodArbiterBatch& b) {
  auto& s = *impl_;
  const std::size_t n = b.count, M = s.M, K = s.K;
  if (b.features.size() != n * s.F) throw std::invalid_argument("method arbiter features do not match the elements");
  if (b.predictions.size() != n * M * K) throw std::invalid_argument("method arbiter predictions do not match elements x methods x outputs");
  if (!b.reference.empty() && b.reference.size() != n * K) throw std::invalid_argument("method arbiter reference does not match the elements");
  if (!b.scale.empty() && b.scale.size() != K) throw std::invalid_argument("method arbiter scale needs one value per output");
  ++s.calls;
  {
    double scale2 = 0.0;
    for (std::size_t k = 0; k < K; ++k) { const double v = b.scale.empty() ? 1.0 : b.scale[k]; scale2 += v * v; }
    s.floor = kErrorFloor * std::sqrt(scale2 / static_cast<double>(K));
  }
  MethodArbiterResult r;
  r.graded = !b.reference.empty();
  r.selection.assign(n, -1); r.learned.assign(n, 0); r.value.assign(n * K, kNaN); r.unseen.assign(n, 0);
  // Predicted errors before anything of this call is learned (no side effects).
  r.predictedError.assign(n * M, kNaN);
  // Per element: how many methods have an error law there, and how many of those laws are
  // remote (the context lies beyond the support they were learned on, remoteness > 1).
  std::vector<std::size_t> laws(n, 0), remoteLaws(n, 0);
  std::vector<double> remoteness;
  for (std::size_t m = 0; m < M; ++m) {
    const auto p = s.learners[m]->predict(b.features, n, b.time, s.restored ? &remoteness : nullptr);
    for (std::size_t e = 0; e < n; ++e) {
      r.predictedError[e * M + m] = s.fromLog(p[e]);
      if (!std::isfinite(p[e]) || !s.predicts(b, e, m)) continue;
      ++laws[e];
      if (s.restored && remoteness[e] > 1.0) ++remoteLaws[e];
    }
  }
  const auto order = s.leaderOrder();
  const bool useLearned = s.informative && s.policyScore > 0.0 && s.policyTotal[1] <= s.policyTotal[0];
  r.policy = useLearned ? "learned_domains" : s.informative ? "recent_leader" : "candidate_median";
  r.leader = s.o.methods[order.front()];
  std::vector<int> leaderSel(n, -1), learnedSel(n, -1);
  for (std::size_t e = 0; e < n; ++e) {
    double bestError = std::numeric_limits<double>::infinity();
    for (std::size_t m = 0; m < M; ++m) {
      const double pe = r.predictedError[e * M + m];
      if (std::isfinite(pe) && s.predicts(b, e, m) && pe < bestError) { bestError = pe; learnedSel[e] = static_cast<int>(m); }
    }
    // A restored arbiter far from every error law (each method's law, learned in an earlier run,
    // is remote here) meets a regime its evidence says nothing about: the same position as
    // before any evidence, so the same prior. Within the run that learned them, remote laws
    // still extrapolate this system's own evidence and are kept (unchanged behaviour).
    const bool unseen = s.restored && laws[e] > 0 && remoteLaws[e] == laws[e];
    if (!s.informative || unseen) {
      // No evidence distinguishes the methods yet: the lower median of the candidates' distinct
      // predictions (first output), a prior that privileges no method.
      std::vector<std::pair<double, int>> values;
      for (std::size_t m = 0; m < M; ++m)
        if (s.predicts(b, e, m)) values.push_back({b.predictions[(e * M + m) * K], static_cast<int>(m)});
      std::sort(values.begin(), values.end());
      // Identical predictions (e.g. a method falling back to another's answer) are one vote.
      values.erase(std::unique(values.begin(), values.end(), [](const auto& a, const auto& c) { return a.first == c.first; }), values.end());
      if (!values.empty()) leaderSel[e] = values[(values.size() - 1) / 2].second;
    } else {
      for (std::size_t m : order) if (s.predicts(b, e, m)) { leaderSel[e] = static_cast<int>(m); break; }
    }
    if (learnedSel[e] < 0 || unseen) learnedSel[e] = leaderSel[e];  // no (trusted) law here
    if (unseen) { r.unseen[e] = 1; s.unseenSelections += 1.0; }
    // Hysteresis from evidence: leave the leader only when the predicted advantage exceeds the
    // error learners' own prequential uncertainty (log units, both methods combined).
    if (learnedSel[e] != leaderSel[e] && leaderSel[e] >= 0) {
      const auto a = static_cast<std::size_t>(learnedSel[e]), l = static_cast<std::size_t>(leaderSel[e]);
      const double pl = r.predictedError[e * M + l];
      if (std::isfinite(pl)) {
        const double margin = std::sqrt(s.uncertainty(a) + s.uncertainty(l));
        if (!(s.toLog(r.predictedError[e * M + a]) + margin < s.toLog(pl))) learnedSel[e] = leaderSel[e];
      }
    }
    const int best = useLearned ? learnedSel[e] : leaderSel[e];
    r.learned[e] = useLearned && std::isfinite(bestError) && !unseen ? 1 : 0;
    r.selection[e] = best;
    if (best >= 0) {
      for (std::size_t k = 0; k < K; ++k) r.value[e * K + k] = b.predictions[(e * M + static_cast<std::size_t>(best)) * K + k];
      s.selected[static_cast<std::size_t>(best)] += 1.0;
      s.totalSelections += 1.0;
      if (r.learned[e]) s.learnedSelections += 1.0;
    }
  }
  if (useLearned) s.learnedPolicyCalls += 1.0;
  r.callRmse.assign(M, kNaN);
  r.arbitratedRmse = r.oracleRmse = kNaN;
  if (!r.graded) return r;
  // Grade and learn: every method on the elements it predicted.
  std::vector<DomainLearnerBatch> batches(M);
  std::vector<double> callSq(M, 0.0), callN(M, 0.0), callCommonSq(M, 0.0);
  double arbitratedSq = 0.0, oracleSq = 0.0, callCommon = 0.0;
  std::array<double, 2> policySq{0.0, 0.0};
  std::vector<double> errors(M);
  for (std::size_t e = 0; e < n; ++e) {
    if (r.selection[e] < 0) continue;
    bool all = true;
    double best = std::numeric_limits<double>::infinity();
    for (std::size_t m = 0; m < M; ++m) {
      errors[m] = s.squaredError(b, e, m);
      if (!std::isfinite(errors[m])) { all = false; continue; }
      callSq[m] += errors[m]; callN[m] += 1.0; best = std::min(best, errors[m]);
      auto& batch = batches[m];
      batch.features.insert(batch.features.end(), b.features.begin() + static_cast<std::ptrdiff_t>(e * s.F),
                            b.features.begin() + static_cast<std::ptrdiff_t>((e + 1) * s.F));
      batch.targets.push_back(s.toLog(std::sqrt(errors[m])));
      ++batch.count;
    }
    const double chosen = errors[static_cast<std::size_t>(r.selection[e])];
    if (!std::isfinite(chosen)) continue;  // reference not finite here
    if (all) { for (std::size_t m = 0; m < M; ++m) callCommonSq[m] += errors[m]; callCommon += 1.0; }
    arbitratedSq += chosen; oracleSq += best;
    policySq[0] += errors[static_cast<std::size_t>(leaderSel[e])];
    policySq[1] += errors[static_cast<std::size_t>(learnedSel[e])];
    if (r.learned[e]) { s.learnedSq += chosen; s.learnedGraded += 1.0; }
    ++r.gradedElements;
  }
  if (!r.gradedElements) return r;
  const double g = static_cast<double>(r.gradedElements);
  for (std::size_t m = 0; m < M; ++m) {
    s.sumSq[m] += callSq[m]; s.count[m] += callN[m]; s.commonSq[m] += callCommonSq[m];
    r.callRmse[m] = rmseOf(callSq[m], callN[m]);
    if (s.frozen) continue;
    s.ewSq[m] = s.o.policyForgetting * s.ewSq[m] + callSq[m];
    s.ewN[m] = s.o.policyForgetting * s.ewN[m] + callN[m];
    s.ewLog[m] *= s.o.policyForgetting; s.ewCalls[m] *= s.o.policyForgetting;
    if (callN[m] > 0) { s.ewLog[m] += s.toLog(r.callRmse[m]); s.ewCalls[m] += 1.0; }
  }
  s.common += callCommon;
  s.arbitratedSq += arbitratedSq; s.oracleSq += oracleSq; s.graded += g;
  r.arbitratedRmse = std::sqrt(arbitratedSq / g); r.oracleRmse = std::sqrt(oracleSq / g);
  if (!s.frozen) {
    const double tiny = g * s.floor * s.floor;
    s.policyScore = s.o.policyForgetting * s.policyScore + std::log((policySq[0] + tiny) / (policySq[1] + tiny));
    for (std::size_t p = 0; p < 2; ++p) s.policyTotal[p] = s.o.policyForgetting * s.policyTotal[p] + policySq[p];
    // Evidence distinguishes the methods once their decayed mean errors differ above the floor.
    double lo = std::numeric_limits<double>::infinity(), hi = 0.0;
    for (std::size_t m = 0; m < M; ++m)
      if (s.ewN[m] > 0) { lo = std::min(lo, s.ewSq[m] / s.ewN[m]); hi = std::max(hi, s.ewSq[m] / s.ewN[m]); }
    s.informative = s.informative || (std::isfinite(lo) && hi - lo > s.floor * s.floor);
  }
  {
    Impl::CallRecord rec{b.time, g, arbitratedSq, oracleSq, callCommon, callSq, callN, callCommonSq, std::vector<double>(M, 0.0)};
    for (int k : r.selection) if (k >= 0) rec.selected[static_cast<std::size_t>(k)] += 1.0;
    s.history.push_back(std::move(rec));
  }
  if (std::getenv("TRECH_DEBUG_ARBITER")) {  // legacy raw dump; prefer --trace debug:arbiter
    std::fprintf(stderr, "[call %ld] policy=%s leader=%s arb=%.4f leaderPol=%.4f learnedPol=%.4f |", s.calls, r.policy.c_str(), r.leader.c_str(),
                 r.arbitratedRmse, std::sqrt(policySq[0] / g), std::sqrt(policySq[1] / g));
    for (std::size_t m = 0; m < M; ++m) std::fprintf(stderr, " %s=%.4f(%g)", s.o.methods[m].c_str(), r.callRmse[m], callN[m]);
    std::fprintf(stderr, "\n");
  }
  nlohmann::json domains = nlohmann::json::object();
  for (std::size_t m = 0; m < M; ++m) {
    nlohmann::json list = nlohmann::json::array();
    if (batches[m].count && !s.frozen) {
      batches[m].time = b.time;
      const auto learned = s.learners[m]->update(batches[m]);
      if (learned.scored && !learned.routedRmse.empty() && std::isfinite(learned.routedRmse[0])) {
        s.learnerSq[m] = s.o.policyForgetting * s.learnerSq[m] + learned.routedRmse[0] * learned.routedRmse[0];
        s.learnerW[m] = s.o.policyForgetting * s.learnerW[m] + 1.0;
      }
      for (const auto& d : learned.domains) {
        if (!d.elements) continue;
        nlohmann::json envelope = nlohmann::json::object();
        for (std::size_t f = 0; f < s.F && f < d.featureMin.size(); ++f) envelope[s.o.features[f]] = {d.featureMin[f], d.featureMax[f]};
        list.push_back({{"id", d.id}, {"elements", d.elements}, {"model", d.model},
                        {"predicted_error_at_mean", d.valueAtMean.empty() ? kNaN : s.fromLog(d.valueAtMean[0])},
                        {"context_envelope", envelope}});
      }
    }
    domains[s.o.methods[m]] = list;
  }
  s.lastDomains = domains;
  r.report = {{"policy", r.policy}, {"leader", r.leader}, {"policy_score", s.policyScore},
              {"policy_rmse", {{"recent_leader", std::sqrt(policySq[0] / g)}, {"learned_domains", std::sqrt(policySq[1] / g)}}},
              {"rows", r.gradedElements}, {"domains", domains}};
  return r;
}

namespace {
nlohmann::json finiteOrNull(double v) { return std::isfinite(v) ? nlohmann::json(v) : nlohmann::json(nullptr); }
double numberOr(const nlohmann::json& j, double fallback) { return j.is_number() ? j.get<double>() : fallback; }
std::vector<double> readSeries(const nlohmann::json& j, std::size_t n, const char* name) {
  if (!j.is_array() || j.size() != n) throw std::invalid_argument(std::string("method arbiter state: bad ") + name);
  std::vector<double> out;
  for (const auto& v : j) out.push_back(numberOr(v, kNaN));
  return out;
}
nlohmann::json writeSeries(const std::vector<double>& v) {
  nlohmann::json out = nlohmann::json::array();
  for (double x : v) out.push_back(finiteOrNull(x));
  return out;
}
}  // namespace

bool MethodArbiter::frozen() const { return impl_->frozen; }

nlohmann::json MethodArbiter::exportState(bool includeRows) const {
  const auto& s = *impl_;
  nlohmann::json learners = nlohmann::json::array();
  for (const auto& l : s.learners) learners.push_back(l->exportState(includeRows));
  return {{"format", "trech_method_arbiter_v1"},
          {"options", {{"methods", s.o.methods}, {"features", s.o.features}, {"outputs", s.o.outputs},
                       {"fallback", s.o.methods[s.fallback]}, {"min_elements", s.o.minElements},
                       {"forgetting", s.o.forgetting}, {"policy_forgetting", s.o.policyForgetting},
                       {"seed", s.o.seed}}},
          {"informative", s.informative},
          {"policy_score", finiteOrNull(s.policyScore)},
          {"policy_total", {finiteOrNull(s.policyTotal[0]), finiteOrNull(s.policyTotal[1])}},
          {"ew_sq", writeSeries(s.ewSq)}, {"ew_n", writeSeries(s.ewN)},
          {"ew_log", writeSeries(s.ewLog)}, {"ew_calls", writeSeries(s.ewCalls)},
          {"learner_sq", writeSeries(s.learnerSq)}, {"learner_w", writeSeries(s.learnerW)},
          {"learners", learners}};
}

MethodArbiter MethodArbiter::fromState(const nlohmann::json& state, bool frozen) {
  if (!state.is_object() || state.value("format", "") != "trech_method_arbiter_v1")
    throw std::invalid_argument("method arbiter state: expected format trech_method_arbiter_v1");
  const auto& o = state.at("options");
  MethodArbiterOptions options;
  options.methods = o.at("methods").get<std::vector<std::string>>();
  options.features = o.at("features").get<std::vector<std::string>>();
  options.outputs = o.at("outputs").get<std::size_t>();
  options.fallback = o.at("fallback").get<std::string>();
  options.minElements = o.at("min_elements").get<std::size_t>();
  options.forgetting = o.at("forgetting").get<double>();
  options.policyForgetting = o.at("policy_forgetting").get<double>();
  options.seed = o.at("seed").get<std::uint64_t>();
  MethodArbiter arbiter(options);
  auto& s = *arbiter.impl_;
  const auto& learners = state.at("learners");
  if (!learners.is_array() || learners.size() != s.M)
    throw std::invalid_argument("method arbiter state: one learner per method expected");
  for (std::size_t m = 0; m < s.M; ++m)
    s.learners[m] = std::make_unique<DomainLearner>(DomainLearner::fromState(learners[m], frozen));
  s.informative = state.at("informative").get<bool>();
  s.policyScore = numberOr(state.at("policy_score"), 0.0);
  const auto& total = state.at("policy_total");
  if (!total.is_array() || total.size() != 2) throw std::invalid_argument("method arbiter state: bad policy_total");
  s.policyTotal = {numberOr(total[0], 0.0), numberOr(total[1], 0.0)};
  s.ewSq = readSeries(state.at("ew_sq"), s.M, "ew_sq");
  s.ewN = readSeries(state.at("ew_n"), s.M, "ew_n");
  s.ewLog = readSeries(state.at("ew_log"), s.M, "ew_log");
  s.ewCalls = readSeries(state.at("ew_calls"), s.M, "ew_calls");
  s.learnerSq = readSeries(state.at("learner_sq"), s.M, "learner_sq");
  s.learnerW = readSeries(state.at("learner_w"), s.M, "learner_w");
  s.frozen = frozen;
  s.restored = true;
  return arbiter;
}

nlohmann::json MethodArbiter::summary() const {
  const auto& s = *impl_;
  nlohmann::json methods = nlohmann::json::object();
  std::size_t best = 0;
  for (std::size_t m = 0; m < s.M; ++m) {
    methods[s.o.methods[m]] = {{"rmse", rmseOf(s.sumSq[m], s.count[m])}, {"rmse_common", rmseOf(s.commonSq[m], s.common)},
                               {"coverage", s.graded > 0 ? s.count[m] / s.graded : kNaN},
                               {"selected_share", s.totalSelections > 0 ? s.selected[m] / s.totalSelections : kNaN}};
    if (s.commonSq[m] < s.commonSq[best]) best = m;
  }
  nlohmann::json out = {{"calls", s.calls}, {"graded_elements", s.graded}, {"common_elements", s.common}, {"features", s.o.features},
          {"methods", methods}, {"best_single_method", s.o.methods[best]},
          {"arbitrated_rmse", rmseOf(s.arbitratedSq, s.graded)}, {"oracle_rmse", rmseOf(s.oracleSq, s.graded)},
          {"learned_selection_share", s.totalSelections > 0 ? s.learnedSelections / s.totalSelections : kNaN},
          {"learned_policy_share", s.calls > 0 ? s.learnedPolicyCalls / static_cast<double>(s.calls) : kNaN},
          {"arbitrated_rmse_learned", rmseOf(s.learnedSq, s.learnedGraded)},
          {"final_domains", s.lastDomains}, {"phases", phases(3)}};
  if (s.frozen) out["frozen"] = true;  // only restored deployments carry the flag
  if (s.unseenSelections > 0)  // only runs that met unseen contexts carry the share
    out["unseen_context_share"] = s.totalSelections > 0 ? s.unseenSelections / s.totalSelections : kNaN;
  return out;
}

nlohmann::json MethodArbiter::phases(std::size_t windows) const {
  const auto& s = *impl_;
  nlohmann::json out = nlohmann::json::array();
  const std::size_t H = s.history.size();
  if (!H || !windows) return out;
  windows = std::min(windows, H);
  for (std::size_t w = 0; w < windows; ++w) {
    const std::size_t a = w * H / windows, b = (w + 1) * H / windows;
    double n = 0, arb = 0, ora = 0, sel = 0, common = 0;
    std::vector<double> sq(s.M, 0.0), cnt(s.M, 0.0), csq(s.M, 0.0), selected(s.M, 0.0);
    for (std::size_t i = a; i < b; ++i) {
      const auto& h = s.history[i];
      n += h.n; arb += h.arbitratedSq; ora += h.oracleSq; common += h.common;
      for (std::size_t m = 0; m < s.M; ++m) {
        sq[m] += h.sq[m]; cnt[m] += h.cnt[m]; csq[m] += h.commonSq[m];
        selected[m] += h.selected[m]; sel += h.selected[m];
      }
    }
    nlohmann::json methods = nlohmann::json::object();
    std::size_t best = 0;
    for (std::size_t m = 0; m < s.M; ++m) {
      methods[s.o.methods[m]] = {{"rmse", rmseOf(sq[m], cnt[m])}, {"rmse_common", rmseOf(csq[m], common)},
                                 {"coverage", n > 0 ? cnt[m] / n : kNaN}, {"selected_share", sel > 0 ? selected[m] / sel : kNaN}};
      if (csq[m] < csq[best]) best = m;
    }
    out.push_back({{"calls", {a + 1, b}},
                   {"time_s", {s.history[a].time, s.history[b - 1].time}},
                   {"arbitrated_rmse", rmseOf(arb, n)}, {"oracle_rmse", rmseOf(ora, n)},
                   {"best_single_method", s.o.methods[best]}, {"methods", methods}});
  }
  return out;
}

}  // namespace trech::ml
