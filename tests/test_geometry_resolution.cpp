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
#include <utility>
#include <vector>

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

void testVolumeFieldTypes() {
  // Accepted forms parse exactly as before: arrays, {x,y,z}, the halfSizeMm
  // fallback, radius aliases and placement vectors.
  const auto ok = trech::configFromJsonString(R"({"geometry":{"volumes":[
    {"name":"a","shape":{"type":"box","sizeMm":[1,2,3]},
     "placement":{"parent":"world","positionMm":{"x":4,"y":5,"z":6},"rotationDeg":[0,90,0]}},
    {"name":"b","shape":{"sizeMm":5,"halfSizeMm":{"x":1,"y":2,"z":3}}},
    {"name":"c","shape":{"type":"tube","radiusMm":2,"halfLengthMm":4}}]}})");
  const auto& v = ok.geometry.volumes;
  require(v.size() == 3, "three volumes parsed");
  require(v[0].shape.sizeXmm == 1 && v[0].shape.sizeYmm == 2 && v[0].shape.sizeZmm == 3,
          "array box size");
  require(v[0].placement.positionMm.y == 5 && v[0].placement.rotationDeg.y == 90,
          "object position and array rotation");
  require(v[1].shape.type == "box" && v[1].shape.sizeXmm == 2 && v[1].shape.sizeYmm == 4 &&
              v[1].shape.sizeZmm == 6,
          "scalar sizeMm keeps zero extents, so halfSizeMm is used (doubled)");
  require(v[2].shape.outerRadiusMm == 2 && v[2].shape.lengthMm == 8, "tube aliases");

  // Wrong-typed fields are parse errors that name the volume and the field.
  const std::pair<const char*, const char*> bad[] = {
      {R"({"geometry":{"volumes":[{"name":"a","shape":{"type":"box","sizeMm":[1,"2",3]}}]}})",
       "geometry.volumes[0] ('a').shape.sizeMm[1] must be a number"},
      {R"({"geometry":{"volumes":[{},{"name":"t","shape":{"type":"tube","outerRadiusMm":"5"}}]}})",
       "geometry.volumes[1] ('t').shape.outerRadiusMm must be a number"},
      {R"({"geometry":{"volumes":[{"shape":{"halfSizeMm":{"x":1,"y":null,"z":1}}}]}})",
       "geometry.volumes[0].shape.halfSizeMm.y must be a number"},
      {R"({"geometry":{"volumes":[{"name":"p","placement":{"positionMm":[0,0,"1"]}}]}})",
       "geometry.volumes[0] ('p').placement.positionMm[2] must be a number"},
      {R"({"geometry":{"volumes":[{"name":"q","placement":{"parent":7}}]}})",
       "geometry.volumes[0] ('q').placement.parent must be a string"},
      {R"({"geometry":{"volumes":[{"name":"r","shape":{"type":3}}]}})",
       "geometry.volumes[0] ('r').shape.type must be a string"},
  };
  for (const auto& [json, message] : bad) {
    std::string what;
    try {
      trech::configFromJsonString(json);
    } catch (const std::invalid_argument& e) {
      what = e.what();
    }
    require(what == message, std::string("expected '") + message + "', got '" + what + "'");
  }
  std::string what;
  try {
    trech::configFromJsonString(R"({"geometry":{"volumes":[{"name":"m","material":5}]}})");
  } catch (const std::invalid_argument& e) {
    what = e.what();
  }
  require(what.rfind("geometry.volumes[0] ('m'): ", 0) == 0,
          "other wrong-typed volume fields keep the library message behind the location");
}

void testRefuseOn() {
  const auto plain = trech::configFromJsonString(R"({"geometry":{"volumes":[]}})");
  require(plain.geometry.refuseOn.empty(), "refusal is off by default");
  require(trech::configToJsonString(plain).find("refuseOn") == std::string::npos,
          "default refusal is not serialized (config hash unchanged)");

  const auto any = trech::configFromJsonString(R"({"geometry":{"refuseOn":"any"}})");
  require(any.geometry.refuseOn == sim::geometryIssueKinds(),
          "'any' expands to every kind in the shared canonical order");
  const auto some = trech::configFromJsonString(
      R"({"geometry":{"refuseOn":["overlap","material_fallback","overlap"]}})");
  require(some.geometry.refuseOn == std::vector<std::string>{"material_fallback", "overlap"},
          "kinds are deduplicated into canonical order");
  const auto again = trech::configFromJsonString(trech::configToJsonString(some));
  require(again.geometry.refuseOn == some.geometry.refuseOn, "refuseOn round-trips");
  const auto parentOnly = trech::configFromJsonString(
      R"({"geometry":{"overlapCheck":false,"refuseOn":["parent_fallback"]}})");
  require(parentOnly.geometry.refuseOn == std::vector<std::string>{"parent_fallback"},
          "non-overlap refusal is valid with the overlap check off");

  for (const char* bad : {R"({"geometry":{"refuseOn":"overlaps"}})",
                          R"({"geometry":{"refuseOn":[1]}})",
                          R"({"geometry":{"refuseOn":true}})",
                          R"({"geometry":{"overlapCheck":false,"refuseOn":"any"}})",
                          R"({"geometry":{"overlapCheck":{"enable":false},"refuseOn":["overlap"]}})"}) {
    bool threw = false;
    try {
      trech::configFromJsonString(bad);
    } catch (const std::invalid_argument&) {
      threw = true;
    }
    require(threw, std::string("invalid refuseOn rejected: ") + bad);
  }

  sim::GeometryResolutionReport report;
  require(sim::refusedIssues(report, any.geometry.refuseOn).empty(), "clean report is not refused");
  report.add({"material_fallback", "world", "", "air", "G4_AIR", "unknown_material"});
  sim::GeometryResolutionIssue overlap{"overlap", "volume", "a", "b", "", "overlaps_sibling"};
  overlap.depthMm = 1.5;
  report.add(overlap);
  report.add({"volume_skipped", "volume", "c", "", "", "invalid_shape"});
  require(sim::refusedIssues(report, {}).empty(), "empty refuseOn never refuses");
  require(sim::refusedIssues(report, {"parent_fallback"}).empty(),
          "unmatched kinds are not refused");
  const auto refused = sim::refusedIssues(report, some.geometry.refuseOn);
  require(refused.size() == 2 && refused[0].kind == "material_fallback" &&
              refused[1].kind == "overlap",
          "matching issues are refused in report order");
  const auto message = sim::refusalMessage(refused);
  require(message.find("2 refused") != std::string::npos &&
              message.find("requested 'air', used 'G4_AIR'") != std::string::npos &&
              message.find("'a' (overlaps_sibling, requested 'b', depth >= 1.5") !=
                  std::string::npos &&
              message.find("invalid_shape") == std::string::npos,
          "refusal message names each refused issue only");
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
  require(!j.contains("geometry_refusal"), "no refusal block unless refused");

  trech::ProvenanceRecord refused;
  refused.phase = "geometry_refused";
  refused.geometryIssues.push_back(overlap);
  refused.geometryRefused = true;
  refused.geometryRefuseOn = {"overlap"};
  refused.geometryRefusedCount = 1;
  j = writeAndRead(refused, path);
  require(j.at("phase") == "geometry_refused", "refusal phase");
  const auto& refusal = j.at("geometry_refusal");
  require(refusal.at("schema") == "trech_geometry_refusal_v1" &&
              refusal.at("refuse_on") == nlohmann::json::array({"overlap"}) &&
              refusal.at("refused_count") == 1,
          "refusal block fields");
  require(j.at("geometry_resolution").at("overlap_count") == 1,
          "refused record keeps the full resolution block");
}

} // namespace

int main() {
  try {
    testMaterialChain();
    testOverlapSampler();
    testOverlapConfig();
    testVolumeFieldTypes();
    testRefuseOn();
    testProvenanceBlocks();
  } catch (const std::exception& e) {
    std::cerr << "test_geometry_resolution failed: " << e.what() << '\n';
    return 1;
  }
  std::cout << "test_geometry_resolution passed\n";
  return 0;
}
