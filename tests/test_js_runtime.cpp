#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <cctype>
#include <chrono>
#include <string>

namespace {

int expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << "\n";
    return 1;
  }
  return 0;
}

int extractLineNumber(const std::string& message, const std::string& path) {
  std::string needle = path;
  std::size_t pos = message.find(needle);
  if (pos == std::string::npos) {
    needle = std::filesystem::path(path).filename().string();
    pos = message.find(needle);
  }
  if (pos == std::string::npos) {
    return -1;
  }
  pos = message.find(':', pos + needle.size());
  if (pos == std::string::npos) {
    return -1;
  }
  int line = 0;
  bool found = false;
  for (std::size_t i = pos + 1; i < message.size(); ++i) {
    const unsigned char ch = static_cast<unsigned char>(message[i]);
    if (!std::isdigit(ch)) {
      break;
    }
    found = true;
    line = (line * 10) + (ch - '0');
  }
  return found ? line : -1;
}

} // namespace

int main() {
  namespace fs = std::filesystem;
  int failures = 0;
  const auto stamp =
      std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());

  fs::path path = fs::temp_directory_path() / ("trech_js_runtime_test_" + stamp + ".js");
  {
    std::ofstream out(path);
    out << "const cfg = { run: { nEvents: 3 } };\n";
    out << "globalThis.TRECH_CONFIG = cfg;\n";
    out << "globalThis.TRECH_HOOKS = { onInit() {} };\n";
  }

  try {
    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(path.string());
    const trech::TrechConfig cfg = trech::configFromJsonString(json);
    failures += expect(cfg.run.nEvents == 3, "Expected nEvents to be 3.");
    failures += expect(!cfg.hooks.registered.empty() &&
                           cfg.hooks.registered.front() == "onInit",
                       "Expected hooks to capture onInit.");
  } catch (const std::exception& ex) {
    std::cerr << "JS runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  std::error_code ec;
  fs::remove(path, ec);

  fs::path includeDir = fs::temp_directory_path() / ("trech_js_runtime_inc_" + stamp);
  fs::path includeFile = includeDir / "helper.js";
  fs::path mainFile = includeDir / "main.js";
  fs::create_directories(includeDir, ec);

  {
    std::ofstream out(includeFile);
    out << "\n";
    out << "\n";
    out << "throw new Error(\"include boom\");\n";
  }
  {
    std::ofstream out(mainFile);
    out << "TRECH_INCLUDE(\"helper.js\");\n";
    out << "const cfg = { run: { nEvents: 1 } };\n";
    out << "globalThis.TRECH_CONFIG = cfg;\n";
  }

  try {
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(mainFile.string());
    failures += expect(false, "Expected include error to be thrown.");
  } catch (const std::exception& ex) {
    const std::string msg = ex.what();
    failures += expect(msg.find(includeFile.filename().string()) != std::string::npos,
                       "Expected included filename in error.");
    const int line = extractLineNumber(msg, includeFile.string());
    failures += expect(line == 3, "Expected include error line number 3.");
  }

  fs::remove_all(includeDir, ec);

  fs::path flowFile = fs::temp_directory_path() / ("trech_js_runtime_flow_" + stamp + ".js");
  {
    std::ofstream out(flowFile);
    out << "globalThis.TRECH_CONFIG = (flow) => flow({ run: { nEvents: 1 }, materials: [] })\n";
    out << "  .set(\"run.nEvents\", 7)\n";
    out << "  .merge({ detector: { worldMaterial: \"G4_AIR\" } })\n";
    out << "  .push(\"materials\", {\n";
    out << "    name: \"water_custom\",\n";
    out << "    densityGcm3: 1.0,\n";
    out << "    components: [{ material: \"G4_WATER\", fraction: 1.0 }]\n";
    out << "  })\n";
    out << "  .when(true, (f) => f.set(\"beam.energyMeV\", 2.5))\n";
    out << "  .build();\n";
  }

  try {
    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(flowFile.string());
    const trech::TrechConfig cfg = trech::configFromJsonString(json);
    failures += expect(cfg.run.nEvents == 7, "Expected flow nEvents to be 7.");
    failures += expect(cfg.detector.worldMaterial == "G4_AIR",
                       "Expected flow merge to set detector world material.");
    failures += expect(std::fabs(cfg.beam.energyMeV - 2.5) < 1e-9,
                       "Expected flow when branch to set beam energy.");
    failures += expect(cfg.materials.size() == 1,
                       "Expected flow push to append one material.");
    failures += expect(!cfg.materials.front().components.empty() &&
                           cfg.materials.front().components.front().material == "G4_WATER",
                       "Expected flow material component to be preserved.");
  } catch (const std::exception& ex) {
    std::cerr << "JS flow runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  fs::path flowDslFile =
      fs::temp_directory_path() / ("trech_js_runtime_flow_dsl_" + stamp + ".js");
  {
    std::ofstream out(flowDslFile);
    out << "globalThis.TRECH_CONFIG = (flow) => flow({\n";
    out << "  environment: { worldSizeMm: 123.0, worldMaterial: \"G4_AIR\" },\n";
    out << "  medium: { mediumBoxMm: 80.0, mediumMaterial: \"G4_WATER\" },\n";
    out << "  beams: {\n";
    out << "    name: \"probe\",\n";
    out << "    particle: \"e-\",\n";
    out << "    energyMeV: 3.0,\n";
    out << "    direction: [0.0, 0.0, 1.0],\n";
    out << "    active: true\n";
    out << "  },\n";
    out << "  hooks: { registered: \"onStep\" }\n";
    out << "})\n";
    out << "  .defaults({ run: { nEvents: 4, seed: 10 }, determinism: { mode: \"strict\" } })\n";
    out << "  .derive(\"run.seed\", (seed) => seed + 5)\n";
    out << "  .normalizeDetectorAliases()\n";
    out << "  .finalize({ selectBeam: true })\n";
    out << "  .require(\"detector.mediumMaterial\", \"string\")\n";
    out << "  .require(\"beams\", \"array\")\n";
    out << "  .build();\n";
  }

  try {
    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(flowDslFile.string());
    const trech::TrechConfig cfg = trech::configFromJsonString(json);
    failures += expect(cfg.run.nEvents == 4,
                       "Expected flow defaults to set nEvents.");
    failures += expect(cfg.run.seed == 15,
                       "Expected flow derive to update seed.");
    failures += expect(cfg.detector.worldMaterial == "G4_AIR" &&
                           cfg.detector.mediumMaterial == "G4_WATER",
                       "Expected detector alias normalization to preserve materials.");
    failures += expect(cfg.beams.size() == 1 &&
                           std::fabs(cfg.beam.energyMeV - 3.0) < 1e-9,
                       "Expected flow finalize/selectBeam to normalize beams.");
    failures += expect(cfg.hooks.registered.size() == 1 &&
                           cfg.hooks.registered.front() == "onStep",
                       "Expected hook registrations to survive flow finalize.");
  } catch (const std::exception& ex) {
    std::cerr << "JS flow DSL runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  fs::path flowRequireFile =
      fs::temp_directory_path() / ("trech_js_runtime_flow_require_" + stamp + ".js");
  {
    std::ofstream out(flowRequireFile);
    out << "globalThis.TRECH_CONFIG = (flow) => flow({ run: { nEvents: 1 } })\n";
    out << "  .require(\"beam\", \"object\", \"beam must exist\")\n";
    out << "  .build();\n";
  }

  try {
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(flowRequireFile.string());
    failures += expect(false, "Expected flow require error to be thrown.");
  } catch (const std::exception& ex) {
    const std::string msg = ex.what();
    failures += expect(msg.find("TRECH_FLOW require failed at 'beam'") != std::string::npos,
                       "Expected flow require failure message to include path.");
  }

  fs::remove(flowFile, ec);
  fs::remove(flowDslFile, ec);
  fs::remove(flowRequireFile, ec);
  return failures == 0 ? 0 : 1;
}
