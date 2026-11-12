#pragma once

// Geant4-free record of how DetectorConstruction resolved the declared
// geometry. Construction substitutes a medium for an unknown material, places a
// volume with an unknown parent in the world and drops a volume whose shape is
// invalid or whose name is a duplicate. Those substitutions used to be silent;
// this report keeps each one so provenance can say what Geant4 actually built.

#include <sstream>
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

// Issue kinds `geometry.refuseOn` may name, in canonical order (Config.cpp
// keeps the same list for parsing; test_geometry_resolution checks they agree).
inline const std::vector<std::string>& geometryIssueKinds() {
  static const std::vector<std::string> kinds = {"material_fallback", "parent_fallback",
                                                 "volume_skipped", "overlap"};
  return kinds;
}

// Issues whose kind the scenario asked the engine to refuse to run on, in
// report order. Empty when `refuseOn` is empty or nothing matched.
inline std::vector<GeometryResolutionIssue> refusedIssues(const GeometryResolutionReport& report,
                                                          const std::vector<std::string>& refuseOn) {
  std::vector<GeometryResolutionIssue> refused;
  for (const auto& issue : report.issues) {
    for (const auto& kind : refuseOn) {
      if (issue.kind == kind) {
        refused.push_back(issue);
        break;
      }
    }
  }
  return refused;
}

// One-line-per-issue explanation for the refusal error and stderr.
inline std::string refusalMessage(const std::vector<GeometryResolutionIssue>& refused) {
  std::string message = "geometry.refuseOn: refusing to run; Geant4 construction made " +
                        std::to_string(refused.size()) + " refused substitution(s):";
  for (const auto& issue : refused) {
    message += "\n  " + issue.kind + " " + issue.role;
    if (!issue.volume.empty()) {
      message += " '" + issue.volume + "'";
    }
    message += " (" + issue.reason;
    if (!issue.requested.empty()) {
      message += ", requested '" + issue.requested + "'";
    }
    if (!issue.resolved.empty()) {
      message += ", used '" + issue.resolved + "'";
    }
    if (issue.kind == "overlap") {
      std::ostringstream depth;
      depth << issue.depthMm;
      message += ", depth >= " + depth.str() + " mm";
    }
    message += ")";
  }
  return message;
}

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
