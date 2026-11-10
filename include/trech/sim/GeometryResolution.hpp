#pragma once

// Geant4-free record of how DetectorConstruction resolved the declared
// geometry. Construction substitutes a medium for an unknown material, places a
// volume with an unknown parent in the world and drops a volume whose shape is
// invalid or whose name is a duplicate. Those substitutions used to be silent;
// this report keeps each one so provenance can say what Geant4 actually built.

#include <string>
#include <utility>
#include <vector>

namespace trech::sim {

struct GeometryResolutionIssue {
  // "material_fallback", "parent_fallback", "volume_skipped" or "overlap".
  std::string kind;
  // "world", "medium" or "volume".
  std::string role;
  std::string volume;
  // What the config asked for (material or parent name).
  std::string requested;
  // What construction used instead ("" when the volume was not built).
  std::string resolved;
  // "unknown_material", "unknown_parent", "parent_not_built_yet",
  // "no_medium_box", "invalid_shape", "duplicate_name"; for an overlap,
  // "overlaps_sibling" (requested = the sibling) or "protrudes_parent"
  // (requested = the mother volume).
  std::string reason;
  // Overlap only: deepest sampled penetration (mm).
  double depthMm = 0.0;
};

// Summary of the post-construction overlap check (see OverlapSampling.hpp).
struct GeometryOverlapCheckSummary {
  bool ran = false;
  int samplesPerVolume = 0;
  double toleranceMm = 0.0;
  int volumesChecked = 0;
  int pairsChecked = 0;
};

struct GeometryResolutionReport {
  std::vector<GeometryResolutionIssue> issues;
  GeometryOverlapCheckSummary overlapCheck;

  void add(GeometryResolutionIssue issue) { issues.push_back(std::move(issue)); }
  bool empty() const { return issues.empty(); }
  int count(const std::string& kind) const {
    int n = 0;
    for (const auto& issue : issues) {
      n += issue.kind == kind ? 1 : 0;
    }
    return n;
  }
};

// Result of walking a material candidate chain.
template <typename T>
struct MaterialChoice {
  T value{};
  std::string name;
  // True when a non-empty request did not resolve and a later candidate was used.
  bool fallback = false;
};

// Tries `requested`, then `fallback`, then `lastResort` with `lookup(name)`,
// which returns a value convertible to bool (null when the name is unknown).
// An empty request is not a fallback: it means "inherit the default".
template <typename Lookup>
auto chooseMaterial(const std::string& requested, const std::string& fallback,
                    const std::string& lastResort, Lookup&& lookup)
    -> MaterialChoice<decltype(lookup(requested))> {
  MaterialChoice<decltype(lookup(requested))> choice;
  const std::string candidates[] = {requested, fallback, lastResort};
  for (int i = 0; i < 3; ++i) {
    if (candidates[i].empty()) {
      continue;
    }
    auto value = lookup(candidates[i]);
    if (value) {
      choice.value = value;
      choice.name = candidates[i];
      choice.fallback = i > 0 && !requested.empty();
      return choice;
    }
  }
  choice.fallback = !requested.empty();
  return choice;
}

} // namespace trech::sim
