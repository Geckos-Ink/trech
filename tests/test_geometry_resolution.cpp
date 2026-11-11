// Geant4-free checks of the geometry-resolution report: the material candidate
// chain DetectorConstruction uses, the deterministic overlap-check surface
// sampler, the geometry.overlapCheck config surface and the conditional
// provenance blocks (geometry_resolution, geometry_overlap_check, event-deposit
// shape) written by ProvenanceWriter.
#include "trech/core/Config.hpp"
#include "trech/core/Provenance.hpp"
#include "trech/sim/GeometryResolution.hpp"
#include "trech/sim/OverlapSampling.hpp"

#include <nlohmann/json.hpp>

#include <cmath>
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


void testOverlapSampler() {
  sim::OverlapShape box;
  box.hx = 5.0;
  box.hy = 2.0;
  box.hz = 1.0;
  const auto a = sim::sampleOverlapSurface(box, 4000, sim::overlapSeedFor("slab"));
  const auto b = sim::sampleOverlapSurface(box, 4000, sim::overlapSeedFor("slab"));
  const auto c = sim::sampleOverlapSurface(box, 4000, sim::overlapSeedFor("other"));
  require(a.size() == 4000 && a == b, "sampler is deterministic per seed");
  require(a != c, "different names draw different points");
  int onZFaces = 0;
  for (const auto& p : a) {
    const bool onX = std::abs(std::abs(p[0]) - 5.0) < 1e-12;
    const bool onY = std::abs(std::abs(p[1]) - 2.0) < 1e-12;
    const bool onZ = std::abs(std::abs(p[2]) - 1.0) < 1e-12;
    require(onX || onY || onZ, "box point lies on a face");
    require(std::abs(p[0]) <= 5.0 && std::abs(p[1]) <= 2.0 && std::abs(p[2]) <= 1.0,
            "box point inside the bounds");
    onZFaces += onZ ? 1 : 0;
  }
  // z faces carry 10/(10+2+5) of the area: 2353 of 4000 expected.
  require(std::abs(onZFaces - 4000.0 * 10.0 / 17.0) < 4000.0 * 0.03, "area-weighted face choice");
  require(std::abs(sim::overlapSurfaceArea(box) - 8.0 * 17.0) < 1e-12, "box area");

  sim::OverlapShape tube;
  tube.kind = sim::OverlapShape::Kind::Tube;
  tube.rmin = 1.0;
  tube.rmax = 3.0;
  tube.hz = 4.0;
  for (const auto& p : sim::sampleOverlapSurface(tube, 2000, 7)) {
    const double r = std::hypot(p[0], p[1]);
    const bool wall = std::abs(r - 3.0) < 1e-9 || std::abs(r - 1.0) < 1e-9;
    const bool cap = std::abs(std::abs(p[2]) - 4.0) < 1e-12 && r >= 1.0 - 1e-9 && r <= 3.0 + 1e-9;
    require(wall || cap, "tube point on a wall or an annular cap");
  }

  sim::OverlapShape sphere;
  sphere.kind = sim::OverlapShape::Kind::Sphere;
  sphere.rmax = 2.5;
  double meanZ = 0.0;
  const auto spherePoints = sim::sampleOverlapSurface(sphere, 2000, 11);
  for (const auto& p : spherePoints) {
    require(std::abs(std::sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]) - 2.5) < 1e-9,
            "sphere point on the sphere");
    meanZ += p[2] / spherePoints.size();
  }
  require(std::abs(meanZ) < 0.15, "sphere points are not biased along z");
  require(sim::sampleOverlapSurface(sphere, 0, 1).empty(), "zero samples is empty");
}

void testOverlapConfig() {
  const auto plain = trech::configFromJsonString(R"({"geometry":{"volumes":[
    {"name":"a","shape":{"type":"box","sizeMm":[1,1,1]}}]}})");
  require(plain.geometry.overlapCheck.isDefault() && plain.geometry.overlapCheck.enable,
          "overlap check defaults on");
  require(trech::configToJsonString(plain).find("overlapCheck") == std::string::npos,
          "default overlap check is not serialized (config hash unchanged)");

  const auto off = trech::configFromJsonString(R"({"geometry":{"overlapCheck":false}})");
  require(!off.geometry.overlapCheck.enable, "boolean false disables the check");
  const auto custom = trech::configFromJsonString(
      R"({"geometry":{"overlapCheck":{"samplesPerVolume":250,"toleranceMm":0.01}}})");
  require(custom.geometry.overlapCheck.samplesPerVolume == 250 &&
              custom.geometry.overlapCheck.toleranceMm == 0.01,
          "object form parsed");
  const auto again = trech::configFromJsonString(trech::configToJsonString(custom));
  require(again.geometry.overlapCheck.samplesPerVolume == 250 &&
              again.geometry.overlapCheck.toleranceMm == 0.01 && again.geometry.overlapCheck.enable,
          "non-default overlap check round-trips");

  for (const char* bad : {R"({"geometry":{"overlapCheck":{"samplesPerVolume":0}}})",
                          R"({"geometry":{"overlapCheck":{"samplesPerVolume":2.5}}})",
                          R"({"geometry":{"overlapCheck":{"toleranceMm":-1}}})",
                          R"({"geometry":{"overlapCheck":"yes"}})"}) {
    bool threw = false;
    try {
      trech::configFromJsonString(bad);
    } catch (const std::invalid_argument&) {
      threw = true;
    }
    require(threw, std::string("invalid overlapCheck rejected: ") + bad);
  }
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

  require(g.at("overlap_count") == 0 && !g.at("issues")[0].contains("depth_mm"),
          "non-overlap issues carry no depth");
  require(!j.contains("geometry_overlap_check"), "no overlap block when the check did not run");

  trech::ProvenanceRecord audited;
  audited.phase = "run_start";
  audited.geometryOverlapCheckRan = true;
  audited.geometryOverlapSamplesPerVolume = 1000;
  audited.geometryOverlapVolumesChecked = 3;
  audited.geometryOverlapPairsChecked = 2;
  j = writeAndRead(audited, path);
  require(!j.contains("geometry_resolution"), "a clean check adds no resolution block");
  const auto& clean = j.at("geometry_overlap_check");
  require(clean.at("schema") == "trech_geometry_overlap_check_v1" && clean.at("clean") == true &&
              clean.at("overlap_count") == 0 && clean.at("pairs_checked") == 2 &&
              clean.at("volumes_checked") == 3 && clean.at("samples_per_volume") == 1000,
          "clean overlap summary");

  trech::ProvenanceRecord::GeometryIssue overlap{"overlap", "volume", "a", "b", "",
                                                 "overlaps_sibling"};
  overlap.depthMm = 1.5;
  audited.geometryIssues.push_back(overlap);
  j = writeAndRead(audited, path);
  require(j.at("geometry_overlap_check").at("clean") == false &&
              j.at("geometry_overlap_check").at("overlap_count") == 1,
          "overlap summary counts overlaps");
  require(j.at("geometry_resolution").at("overlap_count") == 1 &&
              j.at("geometry_resolution").at("issues")[0].at("depth_mm") == 1.5,
          "overlap issue carries its depth");

  end.systemEventEdepShapeDefined = true;
  end.systemEventEdepSkewness = 2.6;
  j = writeAndRead(end, path);
  require(j.at("system_event_edep_skewness").get<double>() == 2.6, "defined shape written");
  require(!j.contains("system_event_secondaries_mean") && !j.contains("volume_event_edep"),
          "no event-shape JSON → no multiplicity/per-volume keys");

  end.systemEventShapeJson =
      R"({"system_event_secondaries_mean":0.872,"system_event_secondaries_skewness":null,)"
      R"("volume_event_edep":{"phantom":{"mean_mev":0.5,"zero_fraction":0.25}}})";
  j = writeAndRead(end, path);
  require(j.at("system_event_secondaries_mean").get<double>() == 0.872,
          "multiplicity copied flat with its score key");
  require(j.at("system_event_secondaries_skewness").is_null(), "null shape stays null");
  require(j.at("volume_event_edep").at("phantom").at("mean_mev").get<double>() == 0.5,
          "per-volume block copied");
  require(j.at("system_event_edep_skewness").get<double>() == 2.6,
          "existing deposit shape untouched");
}

} // namespace

int main() {
  try {
    testMaterialChain();
    testOverlapSampler();
    testOverlapConfig();
    testProvenanceBlocks();
  } catch (const std::exception& e) {
    std::cerr << "test_geometry_resolution failed: " << e.what() << '\n';
    return 1;
  }
  std::cout << "test_geometry_resolution passed\n";
  return 0;
}
