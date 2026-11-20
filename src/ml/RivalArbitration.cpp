#include "trech/ml/RivalArbitration.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace trech::ml {

nlohmann::json RivalArbitration::arbitrate(std::vector<RivalCandidates>& sets, const Call& call) {
  nlohmann::json reports = nlohmann::json::array();
  const std::size_t F = call.fieldNames.size();
  const bool graded = !call.reference.empty();
  for (RivalCandidates& rc : sets) {
    const std::size_t n = rc.elements.size(), K = rc.fields.size(), M = rc.members.size(), C = rc.candidates();
    rc.choice.assign(n, -1);
    if (!n || !K) continue;
    const bool ownFeatures = !rc.featureNames.empty();
    const std::vector<std::string>& featureNames = ownFeatures ? rc.featureNames : call.featureNames;
    const std::size_t A = featureNames.size();
    if (ownFeatures && rc.features.size() != n * A) continue;  // malformed set: unchanged
    std::string key;
    for (const auto& m : rc.members) key += (key.empty() ? "" : "+") + m;
    key += " |";
    for (std::size_t f : rc.fields) key += " " + call.fieldNames.at(f);
    auto it = arbiters_.find(key);
    if (it == arbiters_.end()) {
      if (!graded || frozen_) continue;  // no evidence yet (or a frozen pool): unchanged
      MethodArbiterOptions o;
      o.methods = rc.members;
      o.methods.push_back(call.combination);
      o.features = featureNames;
      for (const auto& m : rc.members) o.features.push_back(m + ".extrapolation");
      o.outputs = K;
      o.fallback = call.combination;
      o.minElements = call.minElements;
      o.seed = call.seed;
      Entry entry;
      entry.arbiter = std::make_unique<MethodArbiter>(o);
      for (std::size_t f : rc.fields) entry.fields.push_back(call.fieldNames[f]);
      entry.scale.assign(K, 0.0);
      entry.combination = call.combination;
      it = arbiters_.emplace(key, std::move(entry)).first;
    }
    Entry& entry = it->second;
    // A restored arbiter met a call whose context has another shape: leave the set unchanged.
    if (entry.arbiter->options().features.size() != A + M || entry.arbiter->options().outputs != K) {
      reports.push_back({{"models", rc.members}, {"fields", entry.fields}, {"elements", n}, {"graded", graded},
                         {"applied", false}, {"error", "context differs from the learned arbiter"}});
      continue;
    }
    MethodArbiterBatch b;
    b.time = static_cast<double>(++entry.calls);
    b.count = n;
    for (std::size_t j = 0; j < n; ++j) {
      const std::size_t e = rc.elements[j];
      for (std::size_t a = 0; a < A; ++a)
        b.features.push_back(ownFeatures ? rc.features[j * A + a] : call.features.at(e * A + a));
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
          if (std::isfinite(r) && !frozen_) entry.scale[k] = std::max(entry.scale[k], std::abs(r));
        }
    }
    for (double s : entry.scale) b.scale.push_back(s > 0 ? s : 1.0);
    const auto r = entry.arbiter->step(b);
    // Before evidence separates the candidates (median prior), keep the cooperating sum.
    const bool apply = r.policy != "candidate_median";
    nlohmann::json selected = nlohmann::json::object();
    for (std::size_t c = 0; c < C; ++c) selected[c < M ? rc.members[c] : entry.combination] = 0;
    for (std::size_t j = 0; j < n; ++j) {
      const int c = r.selection[j];
      if (c < 0) continue;
      const std::string name = static_cast<std::size_t>(c) < M ? rc.members[static_cast<std::size_t>(c)] : entry.combination;
      if (apply) {
        selected[name] = selected[name].get<int>() + 1;
        rc.choice[j] = c;  // M = the cooperating combination
      }
    }
    nlohmann::json callRmse = nlohmann::json::object();
    for (std::size_t c = 0; c < C; ++c) callRmse[c < M ? rc.members[c] : entry.combination] = r.callRmse[c];
    reports.push_back({{"models", rc.members}, {"fields", entry.fields}, {"elements", n}, {"graded", graded},
                       {"applied", apply}, {"policy", r.policy}, {"leader", r.leader}, {"selected", selected},
                       {"call_rmse", callRmse}, {"arbitrated_rmse", r.arbitratedRmse}, {"oracle_rmse", r.oracleRmse}});
  }
  return reports;
}

nlohmann::json RivalArbitration::exportState(bool includeRows) const {
  nlohmann::json sets = nlohmann::json::object();
  for (const auto& [key, entry] : arbiters_) {
    sets[key] = {{"fields", entry.fields}, {"scale", entry.scale}, {"calls", entry.calls},
                 {"combination", entry.combination}, {"arbiter", entry.arbiter->exportState(includeRows)}};
  }
  return {{"format", "trech_rival_arbitration_v1"}, {"sets", sets}};
}

void RivalArbitration::restore(const nlohmann::json& state, bool frozen) {
  if (!state.is_object() || state.value("format", "") != "trech_rival_arbitration_v1" ||
      !state.contains("sets") || !state.at("sets").is_object())
    throw std::invalid_argument("rival arbitration state: expected format trech_rival_arbitration_v1");
  std::map<std::string, Entry> restored;
  for (const auto& [key, item] : state.at("sets").items()) {
    Entry entry;
    entry.fields = item.at("fields").get<std::vector<std::string>>();
    entry.scale = item.at("scale").get<std::vector<double>>();
    entry.calls = item.at("calls").get<long>();
    entry.combination = item.at("combination").get<std::string>();
    if (entry.scale.size() != entry.fields.size())
      throw std::invalid_argument("rival arbitration state: one scale per field expected for " + key);
    entry.arbiter = std::make_unique<MethodArbiter>(MethodArbiter::fromState(item.at("arbiter"), frozen));
    restored.emplace(key, std::move(entry));
  }
  arbiters_ = std::move(restored);
  frozen_ = frozen;
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
