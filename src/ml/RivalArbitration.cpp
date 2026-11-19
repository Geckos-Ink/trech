#include "trech/ml/RivalArbitration.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace trech::ml {

nlohmann::json RivalArbitration::arbitrate(std::vector<RivalCandidates>& sets, const Call& call) {
  nlohmann::json reports = nlohmann::json::array();
  const std::size_t F = call.fieldNames.size(), A = call.featureNames.size();
  const bool graded = !call.reference.empty();
  for (RivalCandidates& rc : sets) {
    const std::size_t n = rc.elements.size(), K = rc.fields.size(), M = rc.members.size(), C = rc.candidates();
    rc.choice.assign(n, -1);
    if (!n || !K) continue;
    std::string key;
    for (const auto& m : rc.members) key += (key.empty() ? "" : "+") + m;
    key += " |";
    for (std::size_t f : rc.fields) key += " " + call.fieldNames.at(f);
    auto it = arbiters_.find(key);
    if (it == arbiters_.end()) {
      if (!graded) continue;  // no evidence yet: cooperating sum, as before
      MethodArbiterOptions o;
      o.methods = rc.members;
      o.methods.push_back(kSum);
      o.features = call.featureNames;
      for (const auto& m : rc.members) o.features.push_back(m + ".extrapolation");
      o.outputs = K;
      o.fallback = kSum;
      o.minElements = call.minElements;
      o.seed = call.seed;
      Entry entry;
      entry.arbiter = std::make_unique<MethodArbiter>(o);
      for (std::size_t f : rc.fields) entry.fields.push_back(call.fieldNames[f]);
      entry.scale.assign(K, 0.0);
      it = arbiters_.emplace(key, std::move(entry)).first;
    }
    Entry& entry = it->second;
    MethodArbiterBatch b;
    b.time = static_cast<double>(++entry.calls);
    b.count = n;
    for (std::size_t j = 0; j < n; ++j) {
      const std::size_t e = rc.elements[j];
      for (std::size_t a = 0; a < A; ++a) b.features.push_back(call.features.at(e * A + a));
      for (std::size_t m = 0; m < M; ++m) {
        const double x = rc.extrapolation[j * M + m];
        b.features.push_back(std::isfinite(x) ? x : 10.0);  // did not run: far
      }
    }
    b.predictions.assign(rc.totals.begin(), rc.totals.end());  // [element][candidate][field]
    if (graded) {
      for (std::size_t j = 0; j < n; ++j)
        for (std::size_t k = 0; k < K; ++k) {
          const double r = call.reference.at(rc.elements[j] * F + rc.fields[k]);
          b.reference.push_back(r);
          if (std::isfinite(r)) entry.scale[k] = std::max(entry.scale[k], std::abs(r));
        }
    }
    for (double s : entry.scale) b.scale.push_back(s > 0 ? s : 1.0);
    const auto r = entry.arbiter->step(b);
    // Before evidence separates the candidates (median prior), keep the cooperating sum.
    const bool apply = r.policy != "candidate_median";
    nlohmann::json selected = nlohmann::json::object();
    for (std::size_t c = 0; c < C; ++c) selected[c < M ? rc.members[c] : std::string(kSum)] = 0;
    for (std::size_t j = 0; j < n; ++j) {
      const int c = r.selection[j];
      if (c < 0) continue;
      const std::string name = static_cast<std::size_t>(c) < M ? rc.members[static_cast<std::size_t>(c)] : std::string(kSum);
      if (apply) {
        selected[name] = selected[name].get<int>() + 1;
        rc.choice[j] = static_cast<std::size_t>(c) < M ? c : -1;
      }
    }
    nlohmann::json callRmse = nlohmann::json::object();
    for (std::size_t c = 0; c < C; ++c) callRmse[c < M ? rc.members[c] : std::string(kSum)] = r.callRmse[c];
    reports.push_back({{"models", rc.members}, {"fields", entry.fields}, {"elements", n}, {"graded", graded},
                       {"applied", apply}, {"policy", r.policy}, {"leader", r.leader}, {"selected", selected},
                       {"call_rmse", callRmse}, {"arbitrated_rmse", r.arbitratedRmse}, {"oracle_rmse", r.oracleRmse}});
  }
  return reports;
}

nlohmann::json RivalArbitration::summary() const {
  nlohmann::json out = nlohmann::json::object();
  for (const auto& [key, entry] : arbiters_) {
    auto s = entry.arbiter->summary();
    s["fields"] = entry.fields;
    s.erase("final_domains");  // per-method domains stay in the arbiter; keep summaries compact
    out[key] = s;
  }
  return out;
}

}  // namespace trech::ml
