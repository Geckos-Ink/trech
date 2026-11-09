// Geant4-free checks of the geometry-resolution report: the material candidate
// chain DetectorConstruction uses, and the conditional provenance blocks
// (geometry_resolution, event-deposit shape) written by ProvenanceWriter.
#include "trech/core/Provenance.hpp"
#include "trech/sim/GeometryResolution.hpp"

#include <nlohmann/json.hpp>

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

namespace sim = trech::sim;

namespace {

void require(bool ok, const std::string& what) {
  if (!ok) {
    throw std::runtime_error(what);
  }
}

// Stand-in for the custom-material map + NIST lookup.
const int* lookupIn(const std::set<std::string>& known, const std::string& name) {
  static const int kFound = 1;
  return known.count(name) ? &kFound : nullptr;
}

void testMaterialChain() {
  const std::set<std::string> known = {"G4_AIR", "G4_WATER", "brine"};
  auto lookup = [&](const std::string& n) { return lookupIn(known, n); };

  auto exact = sim::chooseMaterial("G4_WATER", "G4_AIR", "G4_AIR", lookup);
  require(exact.value && exact.name == "G4_WATER" && !exact.fallback, "known request resolves");

  auto custom = sim::chooseMaterial("brine", "G4_WATER", "G4_AIR", lookup);
  require(custom.name == "brine" && !custom.fallback, "declared material resolves");

  auto inherit = sim::chooseMaterial("", "G4_WATER", "G4_AIR", lookup);
  require(inherit.name == "G4_WATER" && !inherit.fallback, "empty request inherits silently");

  auto unknown = sim::chooseMaterial("air", "G4_WATER", "G4_AIR", lookup);
  require(unknown.name == "G4_WATER" && unknown.fallback, "unknown request falls back");

  auto chain = sim::chooseMaterial("air", "vacuum", "G4_AIR", lookup);
  require(chain.name == "G4_AIR" && chain.fallback, "unknown fallback reaches last resort");

  const std::set<std::string> none;
  auto nothing = sim::chooseMaterial(
      "air", "", "G4_AIR", [&](const std::string& n) { return lookupIn(none, n); });
  require(!nothing.value && nothing.fallback && nothing.name.empty(),
          "nothing resolvable is still a fallback with no value");

  sim::GeometryResolutionReport report;
  report.add({"material_fallback", "world", "", "air", "G4_AIR", "unknown_material"});
  report.add({"volume_skipped", "volume", "slab", "box", "", "invalid_shape"});
  require(report.count("material_fallback") == 1 && report.count("volume_skipped") == 1 &&
              report.count("parent_fallback") == 0 && !report.empty(),
          "report counts by kind");
}

nlohmann::json writeAndRead(const trech::ProvenanceRecord& record, const std::string& path) {
  std::remove(path.c_str());
  trech::ProvenanceWriter(path).write(record);
  std::ifstream in(path);
  std::string line;
  std::getline(in, line);
  std::remove(path.c_str());
  return nlohmann::json::parse(line);
}

void testProvenanceBlocks() {
  const auto path =
      (std::filesystem::temp_directory_path() / "trech_geometry_resolution_test.jsonl").string();

  trech::ProvenanceRecord plain;
  plain.phase = "run_start";
  auto j = writeAndRead(plain, path);
  require(!j.contains("geometry_resolution"), "no issues → no geometry block");
  require(!j.contains("system_event_edep_zero_fraction"), "run_start keeps its shape");

  trech::ProvenanceRecord end;
  end.phase = "run_end";
  end.systemEventShapeRecorded = true;
  end.systemEventEdepZeroFraction = 0.25;
  end.systemEventEdepShapeDefined = false;
  end.geometryIssues.push_back(
      {"material_fallback", "world", "", "air", "G4_AIR", "unknown_material"});
  end.geometryIssues.push_back(
      {"parent_fallback", "volume", "cell", "tank", "world", "unknown_parent"});
  j = writeAndRead(end, path);
  require(j.at("system_event_edep_zero_fraction").get<double>() == 0.25, "shape copied");
  require(j.at("system_event_edep_skewness").is_null() &&
              j.at("system_event_edep_excess_kurtosis").is_null(),
          "undefined shape is null, not zero");
  const auto& g = j.at("geometry_resolution");
  require(g.at("schema") == "trech_geometry_resolution_v1", "schema tag");
  require(g.at("material_fallback_count") == 1 && g.at("parent_fallback_count") == 1 &&
              g.at("volume_skipped_count") == 0,
          "counts by kind");
  require(g.at("issues").size() == 2 && g.at("issues")[1].at("requested") == "tank",
          "issues keep order and fields");

  end.systemEventEdepShapeDefined = true;
  end.systemEventEdepSkewness = 2.6;
  j = writeAndRead(end, path);
  require(j.at("system_event_edep_skewness").get<double>() == 2.6, "defined shape written");
}

} // namespace

int main() {
  try {
    testMaterialChain();
    testProvenanceBlocks();
  } catch (const std::exception& e) {
    std::cerr << "test_geometry_resolution failed: " << e.what() << '\n';
    return 1;
  }
  std::cout << "test_geometry_resolution passed\n";
  return 0;
}
