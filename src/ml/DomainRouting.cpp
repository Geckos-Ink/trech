#include "trech/ml/DomainRouting.hpp"

#include <algorithm>
#include <cstdio>
#include <numeric>

namespace trech::ml {

std::string domainGroupId(const std::vector<std::string>& path) {
  std::uint32_t hash = 2166136261u;
  auto mix = [&hash](unsigned char c) {
    hash ^= c;
    hash *= 16777619u;
  };
  for (std::size_t i = 0; i < path.size(); ++i) {
    if (i) mix(0x1f);  // unit separator: ["ab","c"] != ["a","bc"]
    for (unsigned char c : path[i]) mix(c);
  }
  char buffer[16];
  std::snprintf(buffer, sizeof buffer, "d%08x", hash);
  return buffer;
}

void DomainRouter::plan(const std::vector<DomainRouterStage>& stages,
                        std::size_t elementCount) {
  stages_ = stages;
  setOf_.assign(stages_.size(), kNoSet);
  members_.clear();
  sets_.clear();

  // Union-find over routable stages of one band that share an output name.
  std::vector<std::size_t> parent(stages_.size());
  std::iota(parent.begin(), parent.end(), 0);
  auto find = [&parent](std::size_t i) {
    while (parent[i] != i) {
      parent[i] = parent[parent[i]];
      i = parent[i];
    }
    return i;
  };
  auto shares = [](const std::vector<std::string>& a, const std::vector<std::string>& b) {
    for (const std::string& name : a) {
      if (std::find(b.begin(), b.end(), name) != b.end()) return true;
    }
    return false;
  };
  for (std::size_t i = 0; i < stages_.size(); ++i) {
    if (!stages_[i].routable || !stages_[i].model) continue;
    for (std::size_t j = i + 1; j < stages_.size(); ++j) {
      if (!stages_[j].routable || !stages_[j].model) continue;
      if (stages_[i].scale != stages_[j].scale) continue;
      if (!shares(stages_[i].outputs, stages_[j].outputs)) continue;
      const std::size_t a = find(i), b = find(j);
      if (a != b) parent[std::max(a, b)] = std::min(a, b);
    }
  }
  // Components of two or more members become rival sets, numbered in the
  // execution order of their first member.
  std::vector<std::size_t> setOfRoot(stages_.size(), kNoSet);
  for (std::size_t i = 0; i < stages_.size(); ++i) {
    if (!stages_[i].routable || !stages_[i].model) continue;
    const std::size_t root = find(i);
    std::size_t count = 0;
    for (std::size_t j = 0; j < stages_.size(); ++j) {
      if (stages_[j].routable && stages_[j].model && find(j) == root) ++count;
    }
    if (count < 2) continue;
    if (setOfRoot[root] == kNoSet) {
      setOfRoot[root] = members_.size();
      members_.emplace_back();
      DomainRivalSet set;
      set.scale = stages_[i].scale;
      sets_.push_back(std::move(set));
    }
    const std::size_t s = setOfRoot[root];
    setOf_[i] = s;
    members_[s].push_back(i);
    sets_[s].models.push_back(stages_[i].name);
    sets_[s].domainMeasured.push_back(stages_[i].model->domainMeasured());
    sets_[s].elementsCovered.push_back(0);
  }
  // Envelope per set: for every feature any member measures (a declared input's
  // training range, or a routing feature), the union of the members' ranges.
  envelope_.assign(sets_.size(), {});
  for (std::size_t s = 0; s < sets_.size(); ++s) {
    auto widen = [&](const std::string& name, double lo, double hi) {
      for (EnvelopeFeature& feature : envelope_[s]) {
        if (feature.name == name) {
          feature.lo = std::min(feature.lo, lo);
          feature.hi = std::max(feature.hi, hi);
          return;
        }
      }
      envelope_[s].push_back({name, lo, hi});
    };
    for (std::size_t stage : members_[s]) {
      const GenericSurrogate& model = *stages_[stage].model;
      for (std::size_t i = 0; i < model.inputNames().size(); ++i) {
        double lo = 0.0, hi = 0.0;
        if (model.inputRange(i, &lo, &hi)) widen(model.inputNames()[i], lo, hi);
      }
      const GenericSurrogate::RoutingDomain& routing = model.routingDomain();
      for (std::size_t f = 0; f < routing.features.size(); ++f) {
        widen(routing.features[f], routing.min[f], routing.max[f]);
      }
    }
  }
  decided_.assign(sets_.size(), 0);
  admitted_.assign(stages_.size(), 1);
  groupPaths_.clear();
  groupCounts_.clear();
  elementGroup_.assign(elementCount, 0);
}

void DomainRouter::beginElement() {
  std::fill(decided_.begin(), decided_.end(), 0);
  std::fill(admitted_.begin(), admitted_.end(), 1);
  path_.clear();
}

void DomainRouter::noteValue(const std::string& name, double v) {
  for (const auto& entry : values_) {
    if (entry.first == name) return;  // first source wins; all members read the same element
  }
  values_.emplace_back(name, v);
}

void DomainRouter::decide(std::size_t set, const std::vector<Verdict>& verdicts,
                          bool inEnvelope) {
  decided_[set] = 1;
  DomainRivalSet& stats = sets_[set];
  const std::vector<std::size_t>& members = members_[set];
  std::size_t coveredCount = 0;
  std::size_t nearest = kNoSet;
  for (std::size_t m = 0; m < members.size(); ++m) {
    admitted_[members[m]] = 0;
    if (!verdicts[m].scorable) continue;
    if (verdicts[m].covered) ++coveredCount;
    if (nearest == kNoSet || verdicts[m].distance < verdicts[nearest].distance) nearest = m;
  }
  if (nearest == kNoSet) {
    ++stats.elementsUnscorable;
    return;
  }
  if (coveredCount > 0) {
    for (std::size_t m = 0; m < members.size(); ++m) {
      if (!verdicts[m].covered) continue;
      admitted_[members[m]] = 1;
      ++stats.elementsCovered[m];
      path_.push_back(stages_[members[m]].name);
    }
    if (coveredCount > 1) ++stats.elementsOverlapping;
    return;
  }
  if (!inEnvelope) {
    ++stats.elementsUncovered;
    return;
  }
  admitted_[members[nearest]] = 1;
  ++stats.elementsCovered[nearest];
  ++stats.elementsNearest;
  path_.push_back(stages_[members[nearest]].name);
}

void DomainRouter::endElement(std::size_t element) {
  // A set never reached for this element (every member skipped before the
  // check) contributes nothing to the path.
  std::size_t g = 0;
  while (g < groupPaths_.size() && groupPaths_[g] != path_) ++g;
  if (g == groupPaths_.size()) {
    groupPaths_.push_back(path_);
    groupCounts_.push_back(0);
  }
  ++groupCounts_[g];
  if (element < elementGroup_.size()) elementGroup_[element] = g;
}

DomainRouting DomainRouter::finish() {
  DomainRouting out;
  out.active = active();
  out.sets = sets_;
  // Groups sorted by id so the report order does not depend on which element
  // came first; remap the per-element indices accordingly.
  std::vector<std::size_t> order(groupPaths_.size());
  std::iota(order.begin(), order.end(), 0);
  std::vector<std::string> ids(groupPaths_.size());
  for (std::size_t g = 0; g < groupPaths_.size(); ++g) ids[g] = domainGroupId(groupPaths_[g]);
  std::sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
    return ids[a] != ids[b] ? ids[a] < ids[b] : groupPaths_[a] < groupPaths_[b];
  });
  std::vector<std::size_t> rank(groupPaths_.size());
  for (std::size_t r = 0; r < order.size(); ++r) {
    rank[order[r]] = r;
    DomainGroup group;
    group.id = ids[order[r]];
    group.path = groupPaths_[order[r]];
    group.elements = groupCounts_[order[r]];
    out.groups.push_back(std::move(group));
  }
  out.elementGroup.resize(elementGroup_.size());
  for (std::size_t e = 0; e < elementGroup_.size(); ++e) {
    out.elementGroup[e] = rank.empty() ? 0 : rank[elementGroup_[e]];
  }
  return out;
}

}  // namespace trech::ml
