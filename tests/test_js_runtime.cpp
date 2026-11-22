#include "trech/core/Config.hpp"
#include "trech/js/DeterministicMath.h"
#include "trech/js/JsRuntime.hpp"
#include "TemporaryDirectory.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <cstdlib>
#include <iostream>
#include <iterator>
#include <cctype>
#include <chrono>
#include <string>

#include <nlohmann/json.hpp>

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
  const trech::test::TemporaryDirectory fixture("trech_js_runtime");
  int failures = 0;
  const auto stamp =
      std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());

  fs::path path = fixture.path() / ("trech_js_runtime_test_" + stamp + ".js");
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

  fs::path includeDir = fixture.path() / ("trech_js_runtime_inc_" + stamp);
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

  fs::path flowFile = fixture.path() / ("trech_js_runtime_flow_" + stamp + ".js");
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
      fixture.path() / ("trech_js_runtime_flow_dsl_" + stamp + ".js");
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
      fixture.path() / ("trech_js_runtime_flow_require_" + stamp + ".js");
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

  // Reusable validation presets: a clean config passes every built-in preset,
  // and check() reports each issue (not just the first) with its preset tag.
  fs::path flowPresetFile =
      fixture.path() / ("trech_js_runtime_flow_presets_" + stamp + ".js");
  {
    std::ofstream out(flowPresetFile);
    out << "globalThis.TRECH_HOOKS = { onInit(ctx) {} };\n";
    out << "const good = { run: { nEvents: 2, seed: 3 }, determinism: { mode: 'strict' },\n";
    out << "  detector: { worldMaterial: 'G4_AIR', mediumMaterial: 'My_Water' },\n";
    out << "  environment: { worldMaterial: 'G4_AIR' },\n";
    out << "  materials: [{ name: 'my_water', components: [] }],\n";
    out << "  hooks: { registered: ['onInit'], maxStepCallbacks: 10 },\n";
    out << "  geometry: { volumes: [{ name: 'box', placement: { parent: 'medium' },\n";
    out << "    material: 'G4_WATER', shape: { type: 'box', sizeMm: [1, 2, 3] } },\n";
    out << "    { name: 'inner', placement: { parent: 'box' }, material: 'my_water',\n";
    out << "      shape: { type: 'sphere', radiusMm: 0.2 } }] },\n";
    out << "  beams: [{ name: 'b', particle: 'gamma', energyMeV: 1, direction: [0, 0, 1] }],\n";
    out << "  models: [{ name: 'm', path: 'm.json', scale: 'nano' }] };\n";
    out << "const flow = TRECH_FLOW(good).validate('all');\n";
    out << "const bad = { run: { nEvents: 1.5 }, determinism: { mode: 'fast' },\n";
    out << "  environment: { mediumMaterial: 'watr' }, medium: 'water',\n";
    out << "  detector: { mediumMaterial: 'G4_WATER' },\n";
    out << "  materials: [{ name: 'x' }, { name: 'X' }],\n";
    out << "  hooks: { registered: ['onStpe'], maxEmits: 1.5 },\n";
    out << "  geometry: { volumes: [{ name: 'a', placement: { parent: 'ghost' }, parent: 'x',\n";
    out << "    material: 'G4_AIR', shape: { type: 'box', sizeMm: [1, -2, 3] } }],\n";
    out << "    overlapCheck: { samplesPerVolume: 0, toleranceMm: -1 }, refuseOn: ['overlaps'] },\n";
    out << "  beam: { particle: 'e-', energyMeV: -1, direction: [0, 0, 0] },\n";
    out << "  models: [{ name: 'm' }, { name: 'm', path: 'p', scale: '' }] };\n";
    out << "const issues = TRECH_FLOW.check(bad);\n";
    out << "TRECH_FLOW.definePreset('needs_ensemble', [{ path: 'system.ensemble',\n";
    out << "  check: 'string', message: 'ensemble required' }]);\n";
    out << "const custom = TRECH_FLOW({}).check(['needs_ensemble']);\n";
    out << "const refuseConflict = TRECH_FLOW({ geometry: { overlapCheck: false,\n";
    out << "  refuseOn: 'any' } }).check(['geometry']);\n";
    out << "const refuseFine = TRECH_FLOW({ geometry: { overlapCheck: false,\n";
    out << "  refuseOn: ['material_fallback', 'volume_skipped'] } }).check(['geometry']);\n";
    // Engine shape fallbacks: a scalar sizeMm with a valid halfSizeMm, and a
    // shape without type (the engine builds a box), pass; a bare scalar fails.
    out << "const shapeFallbacks = TRECH_FLOW({ geometry: { volumes: [\n";
    out << "  { name: 'h', shape: { type: 'box', sizeMm: 5, halfSizeMm: [1, 2, 3] } },\n";
    out << "  { name: 'o', shape: { halfSizeMm: { x: 1, y: 1, z: 1 } } }] } }).check(['geometry']);\n";
    out << "const scalarBox = TRECH_FLOW({ geometry: { volumes: [\n";
    out << "  { name: 's', shape: { type: 'box', sizeMm: 60 } }] } }).check(['geometry']);\n";
    out << "let redefineBlocked = false;\n";
    out << "try { TRECH_FLOW.definePreset('beam', () => []); } catch (e) { redefineBlocked = true; }\n";
    out << "let threw = '';\n";
    out << "try { TRECH_FLOW(bad).validate(['run', 'materials']); } catch (e) { threw = String(e.message); }\n";
    out << "globalThis.TRECH_CONFIG = flow.merge({ system: { ensemble: JSON.stringify({\n";
    out << "  issues, custom, refuseConflict, refuseFine, shapeFallbacks, scalarBox,\n";
    out << "  redefineBlocked, threw,\n";
    out << "  presets: TRECH_FLOW.presets() }) } }).build();\n";
  }
  try {
    trech::JsRuntime js;
    const auto cfg = trech::configFromJsonString(
        js.evalExperimentAndGetConfigJson(flowPresetFile.string()));
    const auto report = nlohmann::json::parse(cfg.system.ensemble);
    std::string joined;
    for (const auto& issue : report.at("issues")) {
      joined += issue.get<std::string>() + "\n";
    }
    const char* expected[] = {
        "[run] run.nEvents", "[determinism] determinism.mode", "[beam] beam.energyMeV",
        "[beam] beam.direction", "[materials] materials[1].name: duplicates",
        "[materials] environment.mediumMaterial: 'watr'",
        "[geometry] geometry.volumes[0].parent: ignored by the engine",
        "[geometry] geometry.volumes[0].placement.parent: unknown volume 'ghost'",
        "[geometry] geometry.volumes[0].shape.sizeMm",
        "[geometry] geometry.overlapCheck.samplesPerVolume",
        "[geometry] geometry.overlapCheck.toleranceMm", "[geometry] geometry.refuseOn[0]: must be any",
        "[hooks] hooks.registered[0]: 'onStpe'",
        "[hooks] hooks.maxEmits", "[models] models[0].path",
        "[models] models[1].name: duplicates", "[models] models[1].scale",
        "[environment] medium: must be an object",
        "[environment] detector.mediumMaterial: overrides environment.mediumMaterial"};
    for (const char* needle : expected) {
      failures += expect(joined.find(needle) != std::string::npos,
                         (std::string("Expected preset issue: ") + needle).c_str());
    }
    failures += expect(report.at("issues").size() == std::size(expected),
                       "Expected exactly one issue per seeded defect.");
    failures += expect(report.at("custom").size() == 1 &&
                           report.at("custom")[0].get<std::string>() ==
                               "[needs_ensemble] system.ensemble: ensemble required",
                       "Expected custom rule preset to report its message.");
    failures += expect(report.at("refuseConflict").size() == 1 &&
                           report.at("refuseConflict")[0].get<std::string>().find(
                               "refuses overlaps but geometry.overlapCheck is disabled") !=
                               std::string::npos,
                       "Expected refuseOn overlap with the check disabled to be flagged.");
    failures += expect(report.at("refuseFine").empty(),
                       "Expected non-overlap refusal kinds to pass with the check disabled.");
    failures += expect(report.at("shapeFallbacks").empty(),
                       "Expected halfSizeMm fallback and an untyped box to pass the preset.");
    failures += expect(report.at("scalarBox").size() == 1 &&
                           report.at("scalarBox")[0].get<std::string>().find(
                               "a single number is not expanded by the engine") !=
                               std::string::npos,
                       "Expected a scalar box sizeMm to be flagged with the expansion hint.");
    failures += expect(report.at("redefineBlocked").get<bool>(),
                       "Expected built-in presets to be protected.");
    const auto threw = report.at("threw").get<std::string>();
    failures += expect(threw.find("TRECH_FLOW validate failed (3 issues)") != std::string::npos,
                       "Expected validate() to aggregate issues of the selected presets.");
    failures += expect(report.at("presets").size() == 9,
                       "Expected eight built-in presets plus the custom one.");
  } catch (const std::exception& ex) {
    std::cerr << "JS flow preset runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  fs::path valueFile =
      fixture.path() / ("trech_js_runtime_value_" + stamp + ".js");
  {
    std::ofstream out(valueFile);
    out << "const temperature = TRECH_VALUE.number('temperature_k', {\n";
    out << "  label: 'Temperature', group: 'Environment', unit: 'K',\n";
    out << "  default: 293.15, min: 250, max: 350, step: 0.5\n";
    out << "});\n";
    out << "const events = TRECH_VALUE.integer('event_level', {\n";
    out << "  label: 'Event level', default: 10, min: 1, max: 100, step: 1\n";
    out << "});\n";
    out << "const mode = TRECH_VALUE.choice('quality', {\n";
    out << "  default: 'balanced', choices: ['fast', 'balanced', 'fine']\n";
    out << "});\n";
    out << "globalThis.TRECH_CONFIG = { detector: { temperatureK: temperature },\n";
    out << "  run: { nEvents: events }, system: { ensemble: mode } };\n";
  }
  try {
    trech::JsRuntime defaults;
    const auto defaultCfg = trech::configFromJsonString(
        defaults.evalExperimentAndGetConfigJson(valueFile.string()));
    failures += expect(std::fabs(defaultCfg.detector.temperatureK - 293.15) < 1e-9 &&
                           defaultCfg.run.nEvents == 10,
                       "Expected ordinary TRECH_VALUE calls to return defaults.");
    const auto declarations = nlohmann::json::parse(defaults.scriptParametersJson());
    failures += expect(declarations.size() == 3 &&
                           declarations.at(0).at("id") == "temperature_k" &&
                           !declarations.at(0).at("overridden").get<bool>(),
                       "Expected typed TRECH_VALUE metadata in source order.");

    trech::JsRuntime overridden;
    overridden.setScriptParameterOverrides(
        {"temperature_k=310.5", "event_level=25", "quality=\"fine\""});
    const auto overrideCfg = trech::configFromJsonString(
        overridden.evalExperimentAndGetConfigJson(valueFile.string()));
    failures += expect(std::fabs(overrideCfg.detector.temperatureK - 310.5) < 1e-9 &&
                           overrideCfg.run.nEvents == 25 &&
                           overrideCfg.system.ensemble == "fine",
                       "Expected validated TRECH_VALUE overrides in config.");
    const auto selected = nlohmann::json::parse(overridden.scriptParametersJson());
    failures += expect(selected.at(0).at("value") == 310.5 &&
                           selected.at(0).at("overridden").get<bool>(),
                       "Expected resolved TRECH_VALUE metadata.");

    try {
      trech::JsRuntime invalid;
      invalid.setScriptParameterOverrides({"temperature_k=999"});
      (void)invalid.evalExperimentAndGetConfigJson(valueFile.string());
      failures += expect(false, "Expected out-of-range TRECH_VALUE override to fail.");
    } catch (const std::exception& ex) {
      failures += expect(std::string(ex.what()).find("above max") != std::string::npos,
                         "Expected TRECH_VALUE range error context.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS TRECH_VALUE runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  fs::path hookRuntimeFile =
      fixture.path() / ("trech_js_runtime_hook_dispatch_" + stamp + ".js");
  {
    std::ofstream out(hookRuntimeFile);
    out << "globalThis.TRECH_CONFIG = {\n";
    out << "  run: { nEvents: 2, seed: 99 },\n";
    out << "  beam: { particle: \"e-\", energyMeV: 1.0, direction: [0.0, 0.0, 1.0] },\n";
    out << "  system: { enable: true, mode: \"steady_state\", frame: \"point_agnostic\", ensemble: \"base\" },\n";
    out << "  hooks: { maxEmitsPerCallback: 1, maxEmitPayloadBytes: 48 }\n";
    out << "};\n";
    out << "globalThis.TRECH_HOOKS = {\n";
    out << "  onInit(ctx) {\n";
    out << "    ctx.emit(\"init\", { seed: ctx.runtime.seed, mode: ctx.runtime.mode });\n";
    out << "    const delta = ctx.rng.int(1, 3);\n";
    out << "    return {\n";
    out << "      override: {\n";
    out << "        run: { nEvents: 5, nEvent: 9, threads: 1 },\n";
    out << "        geometry: { volumes: [] },\n";
    out << "        beam: { energyMeV: 2.0 + delta, originMm: [1, -2, 3], 'originMm.x': 9,\n";
    out << "                direction: { x: 0.5, y: false, typo: 2 } },\n";
    out << "        system: { ensemble: \"patched\" }\n";
    out << "      }\n";
    out << "    };\n";
    out << "  },\n";
    out << "  onEventStart(ctx) {\n";
    out << "    if (ctx.event && ctx.event.id === 7) {\n";
    out << "      ctx.emit(\"event_start\", { id: ctx.event.id });\n";
    out << "      ctx.emit(\"event_start_extra\", { id: ctx.event.id + 1 });\n";
    out << "    }\n";
    out << "  },\n";
    out << "  onStep(ctx) {\n";
    out << "    if (ctx.step && ctx.step.index === 3) {\n";
    out << "      ctx.emit(\"step_big\", { blob: \"0123456789012345678901234567890123456789\" });\n";
    out << "      ctx.emit(\"step_ok\", { edep: ctx.step.edepMeV, len: ctx.step.stepLengthMm });\n";
    out << "    }\n";
    out << "  },\n";
    out << "  onEventEnd(ctx) {\n";
    out << "    if (ctx.event && ctx.event.id === 9) {\n";
    out << "      ctx.emit(\"event_end\", { edep: ctx.event.edepMeV, steps: ctx.event.totalStepCount });\n";
    out << "    }\n";
    out << "  }\n";
    out << "};\n";
  }

  fs::path pubchemDir =
      fixture.path() / ("trech_js_runtime_pubchem_" + stamp);
  fs::create_directories(pubchemDir, ec);
  {
    std::ofstream out(pubchemDir / "water.json");
    out << R"({"name":"water","cid":962,"molecular_formula":"H2O","molecular_weight":18.015,"smiles":"O"})";
  }
  setenv("TRECH_PUBCHEM_CACHE_DIR", pubchemDir.string().c_str(), 1);

  fs::path pubchemFile =
      fixture.path() / ("trech_js_runtime_pubchem_exp_" + stamp + ".js");
  {
    std::ofstream out(pubchemFile);
    out << "const w = TRECH_PUBCHEM(\"water\");\n";
    out << "globalThis.TRECH_CONFIG = { run: { nEvents: 1 }, system: { ensemble: w.molecular_formula } };\n";
  }

  try {
    {
      trech::JsRuntime js;
      const std::string json = js.evalExperimentAndGetConfigJson(pubchemFile.string());
      trech::TrechConfig cfg = trech::configFromJsonString(json);
      failures += expect(cfg.system.ensemble == "H2O",
                         "Expected TRECH_PUBCHEM to load cache JSON.");
    }

    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(hookRuntimeFile.string());
    trech::TrechConfig cfg = trech::configFromJsonString(json);
    const auto initReport = js.dispatchHook(
        "onInit",
        trech::HookRuntimeContext{
            cfg.run.seed,
            cfg.run.nEvents,
            cfg.determinism.mode,
            -1,
            -1,
            0.0,
            0.0,
            cfg.hooks.maxEmitsPerCallback,
            cfg.hooks.maxEmitPayloadBytes,
        },
        &cfg,
        true);
    failures += expect(initReport.invoked, "Expected onInit hook invocation.");
    failures += expect(initReport.patchApplied, "Expected onInit hook patch to apply.");
    failures += expect(initReport.emitCount == 1,
                       "Expected onInit to emit one record.");
    failures += expect(initReport.emitDroppedCount == 0,
                       "Expected onInit not to drop emits.");
    failures += expect(cfg.run.nEvents == 5, "Expected onInit patch to override nEvents.");
    failures += expect(cfg.run.threads == 1, "Expected onInit patch to override threads.");
    failures += expect(initReport.ignoredPatchPaths ==
                           std::vector<std::string>{"beam.direction.typo", "beam.direction.y",
                                                    "beam[\"originMm.x\"]", "geometry.volumes", "run.nEvent"},
                       "Expected the unapplied override leaves to be reported.");
    failures += expect(cfg.beam.originXMm == 1 && cfg.beam.originYMm == -2 && cfg.beam.originZMm == 3,
                       "Expected onInit to override the beam origin array.");
    failures += expect(cfg.beam.directionX == 0.5 && cfg.beam.directionY == 0 && cfg.beam.directionZ == 1,
                       "Expected only valid direction object members to apply.");
    failures += expect(cfg.system.ensemble == "patched",
                       "Expected onInit patch to override system ensemble.");
    failures += expect(cfg.beam.energyMeV >= 3.0 && cfg.beam.energyMeV <= 5.0,
                       "Expected deterministic rng patch energy in expected range.");

    const auto mixedPatchPath = fixture.path() / "mixed_hook_patch.js";
    {
      std::ofstream out(mixedPatchPath);
      out << R"JS(
globalThis.TRECH_CONFIG = {run: {nEvents: 2, threads: 3}, beam: {originMm: [1, 2, 3]}};
globalThis.TRECH_HOOKS = {onInit() { return {override: {
  beam: {direction: [0.5, "bad", 1], originMm: {z: -4}},
  run: {nEvents: 4294967301, threads: -1}, system: {ensemble: "valid"}
}}; }};
)JS";
    }
    trech::JsRuntime mixedJs;
    auto mixed = trech::configFromJsonString(mixedJs.evalExperimentAndGetConfigJson(mixedPatchPath.string()));
    const auto mixedReport = mixedJs.dispatchHook("onInit", {}, &mixed, true);
    failures += expect(mixedReport.patchApplied &&
                           mixedReport.ignoredPatchPaths == std::vector<std::string>{
                               "beam.direction", "run.nEvents", "run.threads"},
                       "Expected malformed vectors and out-of-range integers to be reported.");
    failures += expect(mixed.beam.directionX == 0 && mixed.beam.directionY == 0 && mixed.beam.directionZ == 1 &&
                           mixed.run.nEvents == 2 && mixed.run.threads == 3,
                       "Expected rejected override fields to retain their authored values.");
    failures += expect(mixed.beam.originXMm == 1 && mixed.beam.originYMm == 2 && mixed.beam.originZMm == -4 &&
                           mixed.system.ensemble == "valid",
                       "Expected valid fields to apply alongside rejected fields.");

    const auto eventReport = js.dispatchHook(
        "onEventStart",
        trech::HookRuntimeContext{
            cfg.run.seed,
            cfg.run.nEvents,
            cfg.determinism.mode,
            7,
            -1,
            0.0,
            0.0,
            cfg.hooks.maxEmitsPerCallback,
            cfg.hooks.maxEmitPayloadBytes,
        },
        nullptr,
        false);
    failures += expect(eventReport.invoked, "Expected onEventStart hook invocation.");
    failures += expect(eventReport.emitCount == 1, "Expected onEventStart to emit one record.");
    failures += expect(eventReport.emitDroppedCount == 1,
                       "Expected onEventStart to drop one record due to maxEmitsPerCallback.");

    const auto stepReport = js.dispatchHook(
        "onStep",
        trech::HookRuntimeContext{
            cfg.run.seed,
            cfg.run.nEvents,
            cfg.determinism.mode,
            7,
            3,
            0.25,
            1.5,
            cfg.hooks.maxEmitsPerCallback,
            cfg.hooks.maxEmitPayloadBytes,
        },
        nullptr,
        false);
    failures += expect(stepReport.invoked, "Expected onStep hook invocation.");
    failures += expect(stepReport.emitCount == 1, "Expected onStep to emit one record.");
    failures += expect(stepReport.emitDroppedCount == 1,
                       "Expected onStep to drop one oversize payload emit.");

    const auto eventEndReport = js.dispatchHook(
        "onEventEnd",
        trech::HookRuntimeContext{
            cfg.run.seed,
            cfg.run.nEvents,
            cfg.determinism.mode,
            9,
            -1,
            0.0,
            0.0,
            cfg.hooks.maxEmitsPerCallback,
            cfg.hooks.maxEmitPayloadBytes,
            0.75,
            12.5,
            4,
            2,
            0,
            0,
            0.0,
        },
        nullptr,
        false);
    failures += expect(eventEndReport.invoked, "Expected onEventEnd hook invocation.");
    failures += expect(eventEndReport.emitCount == 1,
                       "Expected onEventEnd to emit one record.");

    const auto missingReport = js.dispatchHook(
        "onRunEnd",
        trech::HookRuntimeContext{
            cfg.run.seed,
            cfg.run.nEvents,
            cfg.determinism.mode,
            -1,
            -1,
            0.0,
            0.0,
            cfg.hooks.maxEmitsPerCallback,
            cfg.hooks.maxEmitPayloadBytes,
        },
        nullptr,
        false);
    failures += expect(!missingReport.invoked,
                       "Expected missing hook callback to be skipped.");

    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 4, "Expected four emitted hook records.");
    failures += expect(emits[0].tag == "init", "Expected first emit tag to be init.");
    failures += expect(emits[1].tag == "event_start",
                       "Expected second emit tag to be event_start.");
    failures += expect(emits[2].tag == "step_ok", "Expected third emit tag to be step_ok.");
    failures += expect(emits[3].payloadJson.find("\"edep\":0.75") != std::string::npos,
                       "Expected onEventEnd emit to include event edep.");
  } catch (const std::exception& ex) {
    std::cerr << "JS hook runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.step detail (track identity, pre/post points, times, energies) and
  // ctx.runtime.runId. The detail must not change the hook RNG stream.
  fs::path stepDetailFile =
      fixture.path() / ("trech_js_runtime_step_detail_" + stamp + ".js");
  {
    std::ofstream out(stepDetailFile);
    out << "globalThis.TRECH_CONFIG = { run: { nEvents: 1, seed: 7 },\n";
    out << "  hooks: { maxEmitsPerCallback: 4, maxEmitPayloadBytes: 4096 } };\n";
    out << "globalThis.TRECH_HOOKS = {\n";
    out << "  onStep(ctx) {\n";
    out << "    const s = ctx.step;\n";
    out << "    ctx.emit(\"detail\", { has: s.trackId !== undefined, run: ctx.runtime.runId,\n";
    out << "      track: s.trackId === undefined ? null : s.trackId,\n";
    out << "      parent: s.parentTrackId === undefined ? null : s.parentTrackId,\n";
    out << "      particle: s.particle === undefined ? \"absent\" : s.particle,\n";
    out << "      volume: s.volume === undefined ? \"absent\" : s.volume,\n";
    out << "      process: s.process === undefined ? \"absent\" : s.process,\n";
    out << "      pre: s.prePositionMm || null, post: s.postPositionMm || null,\n";
    out << "      dt: s.postTimeNs === undefined ? null : s.postTimeNs - s.preTimeNs,\n";
    out << "      dke: s.preKineticEnergyMeV === undefined ? null\n";
    out << "        : s.preKineticEnergyMeV - s.postKineticEnergyMeV,\n";
    out << "      u: ctx.rng.uniform() });\n";
    out << "  }\n";
    out << "};\n";
  }
  try {
    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(stepDetailFile.string());
    trech::TrechConfig cfg = trech::configFromJsonString(json);
    trech::HookRuntimeContext plain{cfg.run.seed, cfg.run.nEvents, cfg.determinism.mode,
                                    0, 2, 0.5, 1.25,
                                    cfg.hooks.maxEmitsPerCallback,
                                    cfg.hooks.maxEmitPayloadBytes};
    trech::HookRuntimeContext detailed = plain;
    detailed.runId = 3;
    detailed.hasStepDetail = true;
    detailed.trackId = 4;
    detailed.parentTrackId = 1;
    detailed.particleName = "e-";
    detailed.volumeName = "water_box";
    detailed.processName = "";  // e.g. no defining process => null
    detailed.prePositionMm = {1.0, -2.0, 3.0};
    detailed.postPositionMm = {1.5, -2.0, 4.25};
    detailed.preGlobalTimeNs = 0.25;
    detailed.postGlobalTimeNs = 0.75;
    detailed.preKineticEnergyMeV = 1.0;
    detailed.postKineticEnergyMeV = 0.875;
    (void)js.dispatchHook("onStep", plain, nullptr, false);
    (void)js.dispatchHook("onStep", detailed, nullptr, false);
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 2, "Expected two step-detail emits.");
    if (emits.size() == 2) {
      const auto a = nlohmann::json::parse(emits[0].payloadJson);
      const auto b = nlohmann::json::parse(emits[1].payloadJson);
      failures += expect(a.at("has") == false && a.at("run").is_null() &&
                             a.at("particle") == "absent" && a.at("pre").is_null(),
                         "Expected plain onStep ctx to omit step detail and runId.");
      failures += expect(b.at("has") == true && b.at("run") == 3 && b.at("track") == 4 &&
                             b.at("parent") == 1 && b.at("particle") == "e-" &&
                             b.at("volume") == "water_box" && b.at("process").is_null(),
                         "Expected detailed onStep ctx identity fields.");
      failures += expect(b.at("pre") == nlohmann::json::array({1.0, -2.0, 3.0}) &&
                             b.at("post") == nlohmann::json::array({1.5, -2.0, 4.25}),
                         "Expected pre/post step positions in mm.");
      failures += expect(b.at("dt") == 0.5 && b.at("dke") == 0.125,
                         "Expected step global-time and kinetic-energy deltas.");
      failures += expect(a.at("u") == b.at("u"),
                         "Expected step detail/runId to leave the hook RNG stream unchanged.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS step-detail runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.track for onTrackStart/onTrackEnd: identity, point, length and step
  // count are serialized; ctx.track is null elsewhere; trackId (and only for
  // track hooks) enters the hook RNG seed, so the onStep stream is unchanged.
  fs::path trackDetailFile =
      fixture.path() / ("trech_js_runtime_track_detail_" + stamp + ".js");
  {
    std::ofstream out(trackDetailFile);
    out << "globalThis.TRECH_CONFIG = { run: { nEvents: 1, seed: 7 },\n";
    out << "  hooks: { maxEmitsPerCallback: 4, maxEmitPayloadBytes: 4096 } };\n";
    out << "const record = (ctx) => ({ t: ctx.track, step: ctx.step,\n";
    out << "  event: ctx.event ? ctx.event.id : null, u: ctx.rng.uniform() });\n";
    out << "globalThis.TRECH_HOOKS = {\n";
    out << "  onTrackStart(ctx) { ctx.emit(\"start\", record(ctx)); },\n";
    out << "  onTrackEnd(ctx) { ctx.emit(\"end\", record(ctx)); },\n";
    out << "  onStep(ctx) { ctx.emit(\"step\", { track: ctx.track, u: ctx.rng.uniform() }); }\n";
    out << "};\n";
  }
  try {
    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(trackDetailFile.string());
    trech::TrechConfig cfg = trech::configFromJsonString(json);
    failures += expect(cfg.hooks.registered.size() == 3,
                       "Expected onTrackStart/onTrackEnd/onStep auto-registration.");
    trech::HookRuntimeContext base{cfg.run.seed, cfg.run.nEvents, cfg.determinism.mode,
                                   0, -1, 0.0, 0.0,
                                   cfg.hooks.maxEmitsPerCallback,
                                   cfg.hooks.maxEmitPayloadBytes};
    trech::HookRuntimeContext start = base;
    start.hasTrackDetail = true;
    start.trackId = 2;
    start.parentTrackId = 1;
    start.particleName = "e-";
    start.volumeName = "water_box";
    start.processName = "compt";
    start.trackPositionMm = {1.0, -2.0, 3.0};
    start.trackGlobalTimeNs = 0.5;
    start.trackKineticEnergyMeV = 0.25;
    trech::HookRuntimeContext primary = start;
    primary.trackId = 1;
    primary.parentTrackId = 0;
    primary.processName = "";  // primaries have no creator process => null
    trech::HookRuntimeContext end = start;
    end.trackLengthMm = 0.125;
    end.trackStepCount = 7;
    end.trackKineticEnergyMeV = 0.0;
    end.processName = "eIoni";
    trech::HookRuntimeContext stepPlain = base;
    stepPlain.stepIndex = 2;
    trech::HookRuntimeContext stepWithTrackId = stepPlain;
    stepWithTrackId.trackId = 9;  // no track detail: must not reach the seed
    (void)js.dispatchHook("onTrackStart", start, nullptr, false);
    (void)js.dispatchHook("onTrackStart", primary, nullptr, false);
    (void)js.dispatchHook("onTrackEnd", end, nullptr, false);
    (void)js.dispatchHook("onTrackStart", start, nullptr, false);
    (void)js.dispatchHook("onStep", stepPlain, nullptr, false);
    (void)js.dispatchHook("onStep", stepWithTrackId, nullptr, false);
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 6, "Expected six track/step emits.");
    if (emits.size() == 6) {
      std::vector<nlohmann::json> p;
      for (const auto& e : emits) p.push_back(nlohmann::json::parse(e.payloadJson));
      const auto& t = p[0].at("t");
      failures += expect(t.at("id") == 2 && t.at("parentId") == 1 && t.at("primary") == false &&
                             t.at("particle") == "e-" && t.at("volume") == "water_box" &&
                             t.at("process") == "compt" &&
                             t.at("positionMm") == nlohmann::json::array({1.0, -2.0, 3.0}) &&
                             t.at("timeNs") == 0.5 && t.at("kineticEnergyMeV") == 0.25 &&
                             t.at("lengthMm") == 0.0 && t.at("stepCount") == 0,
                         "Expected onTrackStart ctx.track fields.");
      failures += expect(p[0].at("step").is_null() && p[0].at("event") == 0,
                         "Expected ctx.step null and ctx.event set for track hooks.");
      failures += expect(p[1].at("t").at("primary") == true &&
                             p[1].at("t").at("process").is_null(),
                         "Expected a primary track with a null creator process.");
      failures += expect(p[2].at("t").at("lengthMm") == 0.125 &&
                             p[2].at("t").at("stepCount") == 7 &&
                             p[2].at("t").at("process") == "eIoni",
                         "Expected onTrackEnd length, step count and ending process.");
      failures += expect(p[0].at("u") == p[3].at("u"),
                         "Expected an identical track dispatch to replay its ctx.rng draw.");
      failures += expect(p[0].at("u") != p[1].at("u"),
                         "Expected different tracks of one event to get different streams.");
      failures += expect(p[4].at("track").is_null() && p[4].at("u") == p[5].at("u"),
                         "Expected ctx.track null in onStep and its seed independent of trackId.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS track-detail runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.predict: a scenario declares a generic model and a hook calls it.
  // Verifies model loading from models[], named IO, predictive-mode gating,
  // predict counting, and graceful null for undeclared models / strict mode.
  fs::path predictModel =
      fixture.path() / ("trech_js_predict_model_" + stamp + ".json");
  fs::path predictExp =
      fixture.path() / ("trech_js_predict_exp_" + stamp + ".js");
  try {
    {
      // General linear model: rate = 1.0 + 2*edep + 0.5*activation (no scaling).
      std::ofstream m(predictModel);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep\",\"activation\"],"
        << "\"output_features\":[\"rate\"],"
        // Measured per-output held-out metrics: the engine hands these back as
        // `__accuracy`, so a scenario reports the model's own uncertainty
        // instead of typing a sigma of its own.
        << "\"holdout\":{\"r2_min\":0.93,\"n\":128,"
        << "\"r2\":{\"rate\":0.93},\"mae\":{\"rate\":0.1},"
        << "\"rmse\":{\"rate\":0.25}},"
        << "\"layers\":[{\"weights\":[[2.0,0.5]],\"bias\":[1.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      std::ofstream out(predictExp);
      out << "const cfg = {\n";
      out << "  run: { nEvents: 2, seed: 7 },\n";
      out << "  determinism: { mode: \"predictive\" },\n";
      out << "  models: [{ name: \"rate\", scale: \"nano\", path: \""
          << predictModel.generic_string() << "\" }]\n";
      out << "};\n";
      out << "globalThis.TRECH_CONFIG = cfg;\n";
      out << "globalThis.TRECH_HOOKS = {\n";
      out << "  onEventEnd(ctx) {\n";
      out << "    const p = ctx.predict(\"rate\", { edep: ctx.event.edepMeV,"
          << " activation: 2.0 });\n";
      out << "    const miss = ctx.predict(\"nope\", {});\n";
      out << "    ctx.emit(\"pred\", { rate: p ? p.rate : null,"
          << " sigma: p && p.__accuracy ? p.__accuracy.rate.rmse : null,"
          << " r2: p && p.__accuracy ? p.__accuracy.rate.r2 : null,"
          << " missing: miss });\n";
      out << "  }\n";
      out << "};\n";
    }
    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(predictExp.string());
    trech::TrechConfig cfg = trech::configFromJsonString(json);
    failures += expect(cfg.models.size() == 1 && cfg.models.front().name == "rate",
                       "Expected models[] parsed from the experiment.");
    const auto names = js.loadedModelNames();
    failures += expect(names.size() == 1 && names.front() == "rate",
                       "Expected the declared model to load.");

    trech::HookRuntimeContext predCtx{};
    predCtx.seed = cfg.run.seed;
    predCtx.nEvents = cfg.run.nEvents;
    predCtx.determinismMode = "predictive";
    predCtx.eventId = 0;
    predCtx.eventEdepMeV = 3.0;  // rate = 1 + 2*3 + 0.5*2 = 8.0
    const auto predReport = js.dispatchHook("onEventEnd", predCtx, nullptr, false);
    failures += expect(predReport.invoked, "Expected predictive onEventEnd invocation.");
    failures += expect(predReport.predictCount == 1,
                       "Expected exactly one counted ctx.predict call "
                       "(undeclared model returns null, uncounted).");
    const auto predEmits = js.takeEmittedRecords();
    failures += expect(predEmits.size() == 1, "Expected one predict emit.");
    // The measured uncertainty travels with the prediction (reserved
    // `__accuracy`), so the scenario emits the model's own held-out residual.
    failures += expect(
        predEmits[0].payloadJson.find("\"sigma\":0.25") != std::string::npos &&
            predEmits[0].payloadJson.find("\"r2\":0.93") != std::string::npos,
        "Expected ctx.predict to report the model's measured per-output "
        "held-out accuracy (rmse + r2) as __accuracy.");
    failures += expect(predEmits[0].payloadJson.find("\"rate\":8") != std::string::npos,
                       "Expected ctx.predict to return rate=8.");
    failures += expect(predEmits[0].payloadJson.find("\"missing\":null") != std::string::npos,
                       "Expected undeclared model to yield null.");
    failures += expect(predReport.starvedCount == 0 && predReport.scaleMismatchCount == 0 &&
                           predEmits[0].payloadJson.find("scaleMismatch") == std::string::npos,
                       "Expected unknown training-band coverage to remain unchecked and absent.");

    // Strict mode disables the learned-inference path: predict returns null.
    trech::HookRuntimeContext strictCtx = predCtx;
    strictCtx.determinismMode = "strict";
    const auto strictReport = js.dispatchHook("onEventEnd", strictCtx, nullptr, false);
    failures += expect(strictReport.predictCount == 0,
                       "Expected strict mode to disable ctx.predict.");
    const auto strictEmits = js.takeEmittedRecords();
    failures += expect(!strictEmits.empty() &&
                           strictEmits[0].payloadJson.find("\"rate\":null") != std::string::npos,
                       "Expected strict-mode ctx.predict to return null.");

    // Density and scale evidence are independent of hull coverage. The first
    // point is flagged by BOTH density checks but counts as one prediction;
    // the second is well populated and only off-band. Dispatches reset counts.
    {
      std::ofstream model(predictModel);
      model << R"({"model":"generic_surrogate_v1",
        "input_features":["edep","activation"],"output_features":["rate"],
        "trained_scale_bands":["atomic"],
        "input_mean":[5,2],"input_std":[3,1],
        "input_domain":{"standardized_radius":[2,3],
          "input_min":[0,0],"input_max":[10,4],
          "occupancy":{"bins":4,"counts":[[5,0,0,3],[1,1,1,1]]},
          "joint":{"centers":[[-1.6666666666666667,0]],"radius":0.1}},
        "layers":[{"weights":[[0,0]],"bias":[1],"activation":"none"}]})";
    }
    trech::JsRuntime trust;
    (void)trust.evalExperimentAndGetConfigJson(predictExp.string());
    const auto starved = trust.dispatchHook("onEventEnd", predCtx, nullptr, false);
    failures += expect(starved.predictCount == 1 && starved.outOfDomainCount == 0 &&
                           starved.starvedCount == 1 && starved.scaleMismatchCount == 1,
                       "Expected point trust causes counted once and separately from OOD.");
    (void)trust.takeEmittedRecords();
    auto populatedCtx = predCtx;
    populatedCtx.eventEdepMeV = 0;
    const auto populated = trust.dispatchHook("onEventEnd", populatedCtx, nullptr, false);
    failures += expect(populated.predictCount == 1 && populated.outOfDomainCount == 0 &&
                           populated.starvedCount == 0 && populated.scaleMismatchCount == 1,
                       "Expected populated point to reset starvation while retaining off-band evidence.");
    (void)trust.takeEmittedRecords();
    const auto strictTrust = trust.dispatchHook("onEventEnd", strictCtx, nullptr, false);
    failures += expect(strictTrust.predictCount == 0 && strictTrust.outOfDomainCount == 0 &&
                           strictTrust.starvedCount == 0 && strictTrust.scaleMismatchCount == 0,
                       "Expected strict point dispatch to reset every trust cause.");
    (void)trust.takeEmittedRecords();
    const auto noHook = trust.dispatchHook("onRunEnd", predCtx, nullptr, false);
    failures += expect(!noHook.invoked && noHook.starvedCount == 0 && noHook.scaleMismatchCount == 0,
                       "Expected absent callback to return no stale trust counts.");
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.predict runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.cascade: two scale-tagged models chained in ONE pass. The nano stage
  // maps a Geant4-derived fact (edep) to a nano_signal; the meso stage consumes
  // that nano_signal -- without the scenario hand-wiring the chain. Verifies
  // multi-scale chaining, flat context return, optional named-stage filtering,
  // stage counting, and strict-mode gating through the JS boundary.
  fs::path cascadeNano =
      fixture.path() / ("trech_js_casc_nano_" + stamp + ".json");
  fs::path cascadeMeso =
      fixture.path() / ("trech_js_casc_meso_" + stamp + ".json");
  fs::path cascadeExp =
      fixture.path() / ("trech_js_casc_exp_" + stamp + ".js");
  try {
    {
      // nano_signal = 2*edep, with measured per-output held-out metrics so the
      // stage can report the uncertainty of the quantity it produced.
      std::ofstream m(cascadeNano);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep\"],"
        << "\"output_features\":[\"nano_signal\",\"nano_interval\"],"
        << "\"holdout\":{\"r2_min\":0.88,\"n\":64,"
        << "\"r2\":{\"nano_signal\":0.88},"
        << "\"rmse\":{\"nano_signal\":0.4}},"
        << "\"prediction_interval\":{\"nominal_coverage\":0.9,\"half_width\":{\"nano_interval\":0.25}},"
        // A joint training reference covering edep ~ 3: the multivariate
        // density check the per-feature hull cannot make.
        << "\"input_domain\":{\"standardized_radius\":[5.0],"
        << "\"joint\":{\"centers\":[[3.0]],\"radius\":0.5}},"
        << "\"layers\":[{\"weights\":[[2.0],[1.0]],\"bias\":[0.0,0.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      // observed = 3*nano_signal + 1
      std::ofstream m(cascadeMeso);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"nano_signal\"],"
        << "\"output_features\":[\"observed\",\"nano_signal\"],"
        << "\"layers\":[{\"weights\":[[3.0],[1.0]],\"bias\":[1.0,0.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      std::ofstream out(cascadeExp);
      out << "const cfg = {\n";
      out << "  run: { nEvents: 2, seed: 7 },\n";
      out << "  determinism: { mode: \"predictive\" },\n";
      // meso declared FIRST to prove the engine orders by scale, not listing.
      out << "  models: [\n";
      out << "    { name: \"meso\", scale: \"meso\", path: \""
          << cascadeMeso.generic_string() << "\" },\n";
      out << "    { name: \"nano\", scale: \"nano\", path: \""
          << cascadeNano.generic_string() << "\" }\n";
      out << "  ]\n";
      out << "};\n";
      out << "globalThis.TRECH_CONFIG = cfg;\n";
      out << "globalThis.TRECH_HOOKS = {\n";
      out << "  onEventEnd(ctx) {\n";
      out << "    const c = ctx.cascade({ edep: ctx.event.edepMeV });\n";
      out << "    const selected = ctx.cascade("
             "{ edep: ctx.event.edepMeV }, [\"nano\"]);\n";
      out << "    ctx.emit(\"casc\", {\n";
      out << "      observed: c ? c.observed : null,\n";
      out << "      nano_signal: c ? c.nano_signal : null,\n";
      out << "      stages: c ? c.__cascade.stagesRun : -1,\n";
      // Coverage surface (workstream 3): nano_signal=6 lands outside meso's
      // heuristic 3-sigma hull, so the meso stage is flagged extrapolating.
      out << "      extrapolating: c ? c.__cascade.stagesExtrapolating : -1,\n";
      out << "      nanoInDomain: c ? c.__cascade.trace[0].inDomain : null,\n";
      out << "      mesoInDomain: c ? c.__cascade.trace[1].inDomain : null,\n";
      out << "      mesoLocalInDomain: c ? c.__cascade.trace[1].localInDomain : null,\n";
      out << "      mesoUpstreamOOD: c ? c.__cascade.trace[1].upstreamOutOfDomainInputs.join(\",\") : null,\n";
      out << "      mesoMeasured: c ? c.__cascade.trace[1].domainMeasured : null,\n";
      out << "      mesoOOD: c ? c.__cascade.trace[1].outOfDomainInputs.join(\",\") : null,\n";
      // Provenance/quality fields (workstream 3 b + c): the demo models carry no
      // trained bands or held-out metrics, so off-band is false and R2 is null.
      out << "      scaleMismatched: c ? c.__cascade.stagesScaleMismatched : -1,\n";
      out << "      starved: c ? c.__cascade.stagesStarved : -1,\n";
      out << "      trustTrace: c ? c.__cascade.trace : null,\n";
      out << "      mesoScaleMismatch: c ? c.__cascade.trace[1].scaleMismatch : null,\n";
      out << "      mesoHoldout: c ? c.__cascade.trace[1].holdoutR2 : \"absent\",\n";
      // Per-output measured accuracy: present for the nano stage (its model
      // carries metrics), an empty object for the illustrative meso map --
      // absent must read as absent, never as a zero residual.
      // Joint starvation crosses the boundary as a value for a model that
      // carries a reference and as NULL for one that does not -- "not checked"
      // must not read as "checked and fine".
      out << "      nanoJointMeasured: c ? c.__cascade.trace[0].jointMeasured "
             ": null,\n";
      out << "      nanoJointStarved: c ? c.__cascade.trace[0].jointStarved "
             ": \"absent\",\n";
      out << "      mesoJointMeasured: c ? c.__cascade.trace[1].jointMeasured "
             ": null,\n";
      out << "      mesoJointStarved: c ? c.__cascade.trace[1].jointStarved "
             ": \"absent\",\n";
      out << "      nanoAccuracy: c ? "
             "JSON.stringify(c.__cascade.trace[0].outputAccuracy) : null,\n";
      out << "      mesoAccuracy: c ? "
             "JSON.stringify(c.__cascade.trace[1].outputAccuracy) : null,\n";
      out << "      finalUncertainty: c ? c.__cascade.outputUncertainty : null,\n";
      out << "      finalMeasuredFraction: c ? c.__cascade.measuredUncertaintyFraction : null,\n";
      out << "      selectedUncertainty: selected ? selected.__cascade.outputUncertainty : null,\n";
      out << "      selectedMeasuredFraction: selected ? selected.__cascade.measuredUncertaintyFraction : null,\n";
      out << "      selectedStages: selected ? selected.__cascade.stagesRun : -1,\n";
      out << "      selectedModel: selected ? selected.__cascade.trace[0].model : null,\n";
      out << "      selectedNano: selected ? selected.nano_signal : null,\n";
      out << "      selectedObserved: selected && selected.observed !== undefined ? "
             "selected.observed : null\n";
      out << "    });\n";
      out << "  }\n";
      out << "};\n";
    }
    trech::JsRuntime js;
    const std::string json =
        js.evalExperimentAndGetConfigJson(cascadeExp.string());
    trech::TrechConfig cfg = trech::configFromJsonString(json);
    failures += expect(cfg.models.size() == 2,
                       "Expected two cascade models parsed.");
    const auto names = js.loadedModelNames();
    failures += expect(names.size() == 2,
                       "Expected both cascade models to load.");

    trech::HookRuntimeContext cCtx{};
    cCtx.seed = cfg.run.seed;
    cCtx.nEvents = cfg.run.nEvents;
    cCtx.determinismMode = "predictive";
    cCtx.eventId = 0;
    cCtx.eventEdepMeV = 3.0;  // nano_signal = 6 ; observed = 3*6+1 = 19
    const auto cReport = js.dispatchHook("onEventEnd", cCtx, nullptr, false);
    failures += expect(cReport.invoked, "Expected cascade onEventEnd invocation.");
    // Two stages in the full pass + one explicitly selected stage.
    failures += expect(cReport.predictCount == 3,
                       "Expected 2 full-cascade + 1 selected-stage inference.");
    // Run-level out-of-domain accountability (workstream 3a): the meso stage
    // extrapolated, so exactly one of the three inferences is out-of-domain.
    failures += expect(cReport.outOfDomainCount == 1,
                       "Expected report.outOfDomainCount == 1 (meso stage).");
    const auto cEmits = js.takeEmittedRecords();
    failures += expect(cEmits.size() == 1, "Expected one cascade emit.");
    const auto uncertaintyEmit = nlohmann::json::parse(cEmits[0].payloadJson);
    const auto& final = uncertaintyEmit.at("finalUncertainty");
    failures += expect(final.size() == 3 && final.at("nano_signal").is_null() &&
                           final.at("observed").is_null() &&
                           final.at("nano_interval").at("interval_half_width") == 0.25 &&
                           final.at("nano_interval").at("interval_coverage") == 0.9 &&
                           uncertaintyEmit.at("finalMeasuredFraction") == 1.0 / 3.0,
                       "Final uncertainty excludes seeds and follows the last producer.");
    failures += expect(uncertaintyEmit.at("selectedUncertainty").at("nano_signal").at("rmse") == 0.4 &&
                           uncertaintyEmit.at("selectedMeasuredFraction") == 1.0,
                       "A selected-stage cascade retains its RMSE and interval output coverage.");
    failures += expect(
        cEmits[0].payloadJson.find("\"observed\":19") != std::string::npos,
        "Expected cascade to chain nano->meso (observed=19).");
    failures += expect(
        cEmits[0].payloadJson.find("\"nano_signal\":6") != std::string::npos,
        "Expected the nano stage output present in the flat context.");
    failures += expect(
        cEmits[0].payloadJson.find("\"stages\":2") != std::string::npos,
        "Expected __cascade.stagesRun == 2.");
    // Per-stage training-domain coverage is surfaced through the JS boundary.
    failures += expect(
        cEmits[0].payloadJson.find("\"extrapolating\":1") != std::string::npos,
        "Expected __cascade.stagesExtrapolating == 1 (meso out-of-domain).");
    failures += expect(
        cEmits[0].payloadJson.find("\"nanoInDomain\":true") != std::string::npos,
        "Expected the nano stage flagged in-domain.");
    failures += expect(
        cEmits[0].payloadJson.find("\"mesoInDomain\":false") != std::string::npos,
        "Expected the meso stage flagged extrapolating (out-of-domain).");
    failures += expect(
        cEmits[0].payloadJson.find("\"mesoMeasured\":false") != std::string::npos,
        "Expected the meso stage domain reported heuristic (not measured).");
    failures += expect(
        cEmits[0].payloadJson.find("\"mesoOOD\":\"nano_signal\"") !=
            std::string::npos,
        "Expected meso to record nano_signal as its out-of-domain input.");
    // Provenance/quality cross the JS boundary: demo models carry no trained
    // bands (never off-band) and no held-out metrics (R2 reported null).
    failures += expect(
        cEmits[0].payloadJson.find("\"scaleMismatched\":0") != std::string::npos,
        "Expected no off-band stages for untrained demo maps.");
    failures += expect(
        cEmits[0].payloadJson.find("\"mesoScaleMismatch\":false") !=
            std::string::npos,
        "Expected meso stage not flagged off-band (no trained bands).");
    failures += expect(
        cEmits[0].payloadJson.find("\"mesoHoldout\":null") != std::string::npos,
        "Expected held-out R2 reported null (no metrics), never 0.");
    failures += expect(
        cEmits[0].payloadJson.find("nano_signal") != std::string::npos &&
            cEmits[0].payloadJson.find("rmse") != std::string::npos,
        "Expected the nano stage to surface its measured per-output accuracy.");
    failures += expect(
        cEmits[0].payloadJson.find("\"mesoAccuracy\":\"{}\"") !=
            std::string::npos,
        "Expected the metric-less meso map to report accuracy as absent ({}).");
    failures += expect(
        cEmits[0].payloadJson.find("\"nanoJointMeasured\":true") !=
                std::string::npos &&
            cEmits[0].payloadJson.find("\"nanoJointStarved\":false") !=
                std::string::npos,
        "Expected the nano stage's joint check to run and pass (edep is inside "
        "the carried training region).");
    failures += expect(
        cEmits[0].payloadJson.find("\"mesoJointMeasured\":false") !=
                std::string::npos &&
            cEmits[0].payloadJson.find("\"mesoJointStarved\":null") !=
                std::string::npos,
        "Expected a model with no joint reference to report the check as not "
        "performed (null), never as a pass.");
    failures += expect(
        cEmits[0].payloadJson.find("\"selectedStages\":1") != std::string::npos &&
            cEmits[0].payloadJson.find("\"selectedModel\":\"nano\"") !=
                std::string::npos &&
            cEmits[0].payloadJson.find("\"selectedNano\":6") !=
                std::string::npos &&
            cEmits[0].payloadJson.find("\"selectedObserved\":null") !=
                std::string::npos,
        "Expected ctx.cascade(seed, modelNames) to run only the selected stage.");

    // Strict mode disables the cascade: returns null.
    trech::HookRuntimeContext strictC = cCtx;
    strictC.determinismMode = "strict";
    const auto strictCReport = js.dispatchHook("onEventEnd", strictC, nullptr, false);
    failures += expect(strictCReport.predictCount == 0,
                       "Expected strict mode to disable ctx.cascade.");
    failures += expect(strictCReport.outOfDomainCount == 0,
                       "Expected strict mode to zero the out-of-domain count.");
    const auto strictCEmits = js.takeEmittedRecords();
    failures += expect(
        !strictCEmits.empty() &&
            strictCEmits[0].payloadJson.find("\"observed\":null") !=
                std::string::npos,
        "Expected strict-mode ctx.cascade to return null.");

    // An extrapolated lower-stage output can fit the upper-stage hull. Keep
    // that ancestry visible and counted even though local coverage passes.
    {
      std::ofstream m(cascadeNano);
      m << R"({"model":"generic_surrogate_v1",
        "input_features":["edep"], "output_features":["nano_signal"],
        "input_domain":{"standardized_radius":[2.0]},
        "layers":[{"weights":[[0.1]],"bias":[0.0],"activation":"none"}]})";
    }
    {
      std::ofstream m(cascadeMeso);
      m << R"({"model":"generic_surrogate_v1",
        "input_features":["nano_signal"], "output_features":["observed"],
        "input_domain":{"standardized_radius":[2.0]},
        "layers":[{"weights":[[3.0]],"bias":[1.0],"activation":"none"}]})";
    }
    trech::JsRuntime inherited;
    (void)inherited.evalExperimentAndGetConfigJson(cascadeExp.string());
    cCtx.eventEdepMeV = 5.0;  // lower OOD -> 0.5, inside the upper hull
    const auto inheritedReport = inherited.dispatchHook("onEventEnd", cCtx, nullptr, false);
    failures += expect(inheritedReport.predictCount == 3 &&
                           inheritedReport.outOfDomainCount == 3,
                       "Expected inherited cascade OOD in hook accounting.");
    const auto inheritedEmits = inherited.takeEmittedRecords();
    failures += expect(inheritedEmits.size() == 1, "Expected inherited trust emit.");
    if (!inheritedEmits.empty()) {
      const auto payload = nlohmann::json::parse(inheritedEmits[0].payloadJson);
      failures += expect(payload.at("extrapolating") == 2 &&
                             payload.at("mesoInDomain") == false &&
                             payload.at("mesoLocalInDomain") == true &&
                             payload.at("mesoUpstreamOOD") == "nano_signal" &&
                             payload.at("mesoOOD") == "",
                         "Expected effective and local domain trust with input lineage.");
    }

    // Locally in-range starvation and off-band use remain separate from OOD,
    // while each is inherited by consumers even without local density/band data.
    {
      std::ofstream m(cascadeNano);
      m << R"({"model":"generic_surrogate_v1",
        "input_features":["edep"], "output_features":["nano_signal"],
        "trained_scale_bands":["atomic"],
        "input_mean":[5],"input_std":[3],
        "input_domain":{"standardized_radius":[2],"input_min":[0],"input_max":[10],
          "occupancy":{"bins":4,"counts":[[5,0,0,3]]}},
        "layers":[{"weights":[[0]],"bias":[0.25],"activation":"none"}]})";
    }
    trech::JsRuntime densityScale;
    (void)densityScale.evalExperimentAndGetConfigJson(cascadeExp.string());
    cCtx.eventEdepMeV = 3;
    const auto trustReport = densityScale.dispatchHook("onEventEnd", cCtx, nullptr, false);
    failures += expect(trustReport.predictCount == 3 && trustReport.outOfDomainCount == 0,
                       "Expected density/scale evidence to preserve hull-only OOD accounting.");
    failures += expect(trustReport.starvedCount == 3 && trustReport.scaleMismatchCount == 3,
                       "Expected inherited density/scale causes in full plus selected cascade accounting.");
    const auto trustEmits = densityScale.takeEmittedRecords();
    failures += expect(trustEmits.size() == 1, "Expected density/scale trust emit.");
    if (!trustEmits.empty()) {
      const auto payload = nlohmann::json::parse(trustEmits[0].payloadJson);
      const auto& lower = payload.at("trustTrace").at(0);
      const auto& upper = payload.at("trustTrace").at(1);
      failures += expect(payload.at("starved") == 2 && payload.at("scaleMismatched") == 2 &&
                             payload.at("extrapolating") == 0 &&
                             lower.at("starved") == true && lower.at("localStarved") == true &&
                             lower.at("localScaleMismatch") == true &&
                             lower.at("upstreamStarvedInputs").empty() &&
                             lower.at("upstreamScaleMismatchedInputs").empty(),
                         "Expected local density/scale evidence and effective cascade totals.");
      const auto inputNames = nlohmann::json::array({"nano_signal"});
      failures += expect(upper.at("inDomain") == true &&
                             upper.at("starved") == true && upper.at("localStarved") == false &&
                             upper.at("upstreamStarvedInputs") == inputNames &&
                             upper.at("starvedInputs").empty() && upper.at("jointStarved").is_null() &&
                             upper.at("scaleMismatch") == true && upper.at("localScaleMismatch") == false &&
                             upper.at("upstreamScaleMismatchedInputs") == inputNames &&
                             upper.at("trainedScale") == "",
                         "Expected inherited causes without fabricated local checks/bands.");
    }
    const auto strictTrustReport = densityScale.dispatchHook("onEventEnd", strictC, nullptr, false);
    failures += expect(strictTrustReport.predictCount == 0 && strictTrustReport.outOfDomainCount == 0 &&
                           strictTrustReport.starvedCount == 0 && strictTrustReport.scaleMismatchCount == 0,
                       "Expected strict mode to disable density/scale cascade inference.");
    (void)densityScale.takeEmittedRecords();
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.cascade runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.cascade() with NO argument auto-seeds from the ambient Geant4 base
  // (workstream 1): the nano stage declares the ambient key `edep_mev` and must
  // consume the per-event tally with the scenario copying nothing by hand. Also
  // verifies material probes reach the seed and an explicit arg still overrides.
  fs::path ambientNano =
      fixture.path() / ("trech_js_amb_nano_" + stamp + ".json");
  fs::path ambientExp =
      fixture.path() / ("trech_js_amb_exp_" + stamp + ".js");
  try {
    {
      // nano_signal = 2*edep_mev (edep_mev is an AMBIENT seed key)
      std::ofstream m(ambientNano);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep_mev\"],"
        << "\"output_features\":[\"nano_signal\"],"
        << "\"layers\":[{\"weights\":[[2.0]],\"bias\":[0.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      std::ofstream out(ambientExp);
      out << "const cfg = {\n";
      out << "  run: { nEvents: 2, seed: 7 },\n";
      out << "  determinism: { mode: \"predictive\" },\n";
      out << "  models: [\n";
      out << "    { name: \"nano\", scale: \"nano\", path: \""
          << ambientNano.generic_string() << "\" }\n";
      out << "  ]\n";
      out << "};\n";
      out << "globalThis.TRECH_CONFIG = cfg;\n";
      out << "globalThis.TRECH_HOOKS = {\n";
      out << "  onEventEnd(ctx) {\n";
      // No argument: the cascade seeds itself from ctx.event + ctx.materials.
      out << "    const c = ctx.cascade();\n";
      out << "    const p = ctx.predict(\"nano\");\n";
      out << "    const q = ctx.predict(\"nano\", {edep_mev: 6});\n";
      out << "    const override = ctx.cascade({edep_mev: 9, caller_only: 1});\n";
      out << "    const after = ctx.cascade();\n";
      out << "    const pointAfter = ctx.predict(\"nano\");\n";
      out << "    ctx.emit(\"amb\", {\n";
      out << "      point_signal: p ? p.nano_signal : null,\n";
      out << "      override_signal: q ? q.nano_signal : null,\n";
      out << "      cascade_override: override ? override.nano_signal : null,\n";
      out << "      after_override: after ? after.nano_signal : null,\n";
      out << "      point_after_override: pointAfter ? pointAfter.nano_signal : null,\n";
      out << "      caller_leaked: after ? after.__cascade.seedKeys.includes('caller_only') : false,\n";
      out << "      output_leaked: after ? after.__cascade.seedKeys.includes('nano_signal') : false,\n";
      out << "      nano_signal: c ? c.nano_signal : null,\n";
      out << "      edep_seed: c ? c.edep_mev : null,\n";
      out << "      optics_n: c ? c['optics.water.mean_refractive_index'] : null,\n";
      out << "      optics_direct: ctx.optics && ctx.optics.water ? ctx.optics.water.mean_refractive_index : null,\n";
      out << "      seedKeys: c ? c.__cascade.seedKeys : []\n";
      out << "    });\n";
      out << "  }\n";
      out << "};\n";
    }
    trech::JsRuntime js;
    const std::string json =
        js.evalExperimentAndGetConfigJson(ambientExp.string());
    (void)json;
    const auto names = js.loadedModelNames();
    failures += expect(names.size() == 1,
                       "Expected the ambient-seed nano model to load.");

    trech::HookRuntimeContext aCtx{};
    aCtx.determinismMode = "predictive";
    aCtx.eventId = 0;
    aCtx.eventEdepMeV = 4.0;  // ambient edep_mev -> nano_signal = 8
    aCtx.materialsJson =
        "[{\"name\":\"G4_WATER\",\"density_g_per_cm3\":1.0,"
        "\"electron_density_per_cm3\":3.3e23,"
        "\"numberDensityPerCm3\":{\"H\":6.7e22}}]";
    aCtx.opticsJson =
        "[{\"material_name\":\"G4_WATER\",\"config_material_key\":\"water\","
        "\"mean_refractive_index\":1.333,\"mean_absorption_length_mm\":12000,"
        "\"mean_scatter_length_mm\":15000,\"display_rgb\":[0.98,0.99,1.0]}]";
    const auto aReport = js.dispatchHook("onEventEnd", aCtx, nullptr, false);
    failures += expect(aReport.invoked,
                       "Expected ambient-seed onEventEnd invocation.");
    failures += expect(aReport.predictCount == 6,
                       "Expected all ambient and explicit override predictions.");
    const auto aEmits = js.takeEmittedRecords();
    failures += expect(aEmits.size() == 1, "Expected one ambient-seed emit.");
    if (!aEmits.empty()) {
      const std::string& p = aEmits[0].payloadJson;
      const auto payload = nlohmann::json::parse(p);
      failures += expect(payload.at("cascade_override") == 18 &&
                             payload.at("after_override") == 8 &&
                             payload.at("point_after_override") == 8 &&
                             payload.at("caller_leaked") == false &&
                             payload.at("output_leaked") == false,
                         "caller overrides and model outputs never contaminate ambient facts");
      failures += expect(p.find("\"point_signal\":8") != std::string::npos &&
                             p.find("\"override_signal\":12") != std::string::npos,
                         "ctx.predict consumes ambient Geant4 facts and explicit overrides");
      failures += expect(
          p.find("\"nano_signal\":8") != std::string::npos,
          "Expected argument-free ctx.cascade to consume ambient edep_mev.");
      failures += expect(
          p.find("\"edep_seed\":4") != std::string::npos,
          "Expected the ambient edep_mev fact present in the flat context.");
      failures += expect(
          p.find("\"edep_mev\"") != std::string::npos,
          "Expected seedKeys to list the ambient event fact edep_mev.");
      failures += expect(
          p.find("material.G4_WATER.density_g_per_cm3") != std::string::npos,
          "Expected seedKeys to list a Geant4 material probe fact.");
      failures += expect(
          p.find("material.G4_WATER.number_density.H") != std::string::npos,
          "Expected seedKeys to list a per-element number density.");
      failures += expect(
          p.find("\"optics_n\":1.333") != std::string::npos &&
              p.find("\"optics_direct\":1.333") != std::string::npos,
          "Expected ctx.optics and the ambient cascade to share derived optics.");
    }

    aCtx.eventId = 1;
    aCtx.eventEdepMeV = 2.0;
    aCtx.materialsJson = "[]";
    aCtx.opticsJson = "[]";
    const auto changedReport = js.dispatchHook("onEventEnd", aCtx, nullptr, false);
    const auto changedEmits = js.takeEmittedRecords();
    failures += expect(changedReport.predictCount == 6 && changedEmits.size() == 1,
                       "changed hook context still runs all predictions");
    if (!changedEmits.empty()) {
      const auto payload = nlohmann::json::parse(changedEmits[0].payloadJson);
      failures += expect(payload.at("nano_signal") == 4 &&
                             payload.at("point_signal") == 4 &&
                             payload.at("after_override") == 4 &&
                             payload.at("point_after_override") == 4 &&
                             payload.at("seedKeys").size() == 7 &&
                             !payload.contains("optics_n"),
                         "each dispatch refreshes event facts and removes obsolete probe facts");
    }
    aCtx.eventId = -1;  // no per-event tally is available at run scope
    const auto absentReport = js.dispatchHook("onEventEnd", aCtx, nullptr, false);
    const auto absentEmits = js.takeEmittedRecords();
    failures += expect(absentReport.predictCount == 2 && !absentEmits.empty() &&
                           absentEmits[0].payloadJson.find("\"point_signal\":null") != std::string::npos,
                       "absent Geant4 facts skip cascade/point inference; explicit override still runs");
  } catch (const std::exception& ex) {
    std::cerr << "JS ambient-cascade runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.evolve: the per-element inference OPERATOR crossing the JS boundary.
  // A scenario declares named state over N elements and the engine chains
  // scale-tagged models over every element, integrating the rates they predict
  // -- replacing the hand-written per-element rate loop the scenario used to
  // carry. Verifies in-place mutation of the caller's arrays, the ambient
  // Geant4 shared context, aux/context inputs, intermediate chaining by scale,
  // declared bounds, honest N*stages inference counting, and strict-mode
  // gating.
  fs::path evolveNano =
      fixture.path() / ("trech_js_evo_nano_" + stamp + ".json");
  fs::path evolveMacro =
      fixture.path() / ("trech_js_evo_macro_" + stamp + ".json");
  fs::path evolveExp =
      fixture.path() / ("trech_js_evo_exp_" + stamp + ".js");
  fs::path reactModel =
      fixture.path() / ("trech_js_react_model_" + stamp + ".json");
  fs::path reactExp =
      fixture.path() / ("trech_js_react_exp_" + stamp + ".js");
  try {
    {
      // nano stage: drive = 0.5*edep_mev (an AMBIENT Geant4 fact) + 1.0*catalyst
      // (a per-element aux fact). It emits an intermediate, not a field update.
      std::ofstream m(evolveNano);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep_mev\",\"catalyst\"],"
        << "\"output_features\":[\"drive\"],"
        << "\"trained_scale_bands\":[\"atomic\"],"
        << "\"input_domain\":{\"standardized_radius\":[5,5],"
        << "\"input_min\":[0,0],\"input_max\":[4,4],"
        << "\"occupancy\":{\"bins\":4,\"counts\":[[2,2,0,2],[2,2,2,2]]},"
        << "\"joint\":{\"centers\":[[2,0]],\"radius\":0.1}},"
        << "\"layers\":[{\"weights\":[[0.5,1.0]],\"bias\":[0.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      // macro stage: consumes the nano intermediate + the live state + a
      // scenario-supplied coefficient.
      //   d_conversion_dt = drive * (1 - conversion) ... expressed linearly as
      //   0.5*drive - 0.5*conversion is enough to prove chaining + integration.
      //   d_heat_dt       = 10*rate_coefficient
      std::ofstream m(evolveMacro);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"drive\",\"conversion\",\"rate_coefficient\"],"
        << "\"output_features\":[\"d_conversion_dt\",\"d_heat_dt\"],"
        << "\"layers\":[{\"weights\":[[0.5,-0.5,0.0],[0.0,0.0,10.0]],"
        << "\"bias\":[0.0,0.0],\"activation\":\"none\"}]}";
    }
    {
      std::ofstream out(evolveExp);
      out << "const cfg = {\n";
      out << "  run: { nEvents: 2, seed: 7 },\n";
      out << "  determinism: { mode: \"predictive\" },\n";
      // macro declared FIRST to prove the operator orders by scale, not listing.
      out << "  models: [\n";
      out << "    { name: \"macro_op\", scale: \"macro\", "
             "operator_role: \"reaction_state\", element_kind: \"parcel\", "
             "required_context_keys: [\"rate_coefficient\"], path: \""
          << evolveMacro.generic_string() << "\" },\n";
      out << "    { name: \"nano_op\", scale: \"nano\", "
             "operator_role: \"reaction_state\", element_kind: \"parcel\", "
             "required_context_keys: [\"edep_mev\"], path: \""
          << evolveNano.generic_string() << "\" },\n";
      out << "    { name: \"voxel_op\", scale: \"nano\", "
             "operator_role: \"transport_state\", element_kind: \"voxel\", "
             "required_context_keys: [\"edep_mev\"], path: \""
          << evolveNano.generic_string() << "\" },\n";
      out << "    { name: \"missing_context_op\", scale: \"nano\", "
             "operator_role: \"unavailable_context\", element_kind: \"parcel\", "
             "required_context_keys: [\"never_present\"], path: \""
          << evolveNano.generic_string() << "\" }\n";
      out << "  ]\n";
      out << "};\n";
      out << "globalThis.TRECH_CONFIG = cfg;\n";
      out << "globalThis.TRECH_HOOKS = {\n";
      out << "  onEventEnd(ctx) {\n";
      // Three elements the scenario owns; the engine mutates them in place.
      out << "    const conversion = [0.0, 0.4, 0.9];\n";
      out << "    const heat = [300.0, 300.0, 300.0];\n";
      out << "    const catalyst = [0.0, 1.0, 2.0];\n";
      out << "    const r = ctx.evolve({\n";
      out << "      dt: 2.0,\n";
      // `conversion` is bounded 0..1 so the third element must clamp.
      out << "      fields: [{ name: \"conversion\", min: 0, max: 1 }, \"heat\"],\n";
      out << "      state: { conversion: conversion, heat: heat },\n";
      out << "      aux: { catalyst: catalyst },\n";
      out << "      context: { rate_coefficient: 0.25 },\n";
      out << "      operator_role: \"reaction_state\",\n";
      out << "      element_kind: \"parcel\"\n";
      out << "    });\n";
      out << "    const ambiguousState = [0.25];\n";
      out << "    const ambiguous = ctx.evolve({\n";
      out << "      dt: 1, fields: [{name:\"conversion\",min:0,max:1}],\n";
      out << "      state: {conversion: ambiguousState},\n";
      out << "      aux: {catalyst:[0]}, context:{rate_coefficient:0.25}\n";
      out << "    });\n";
      out << "    const absentState = [0.5];\n";
      out << "    const absent = ctx.evolve({\n";
      out << "      dt: 1, fields: [{name:\"conversion\",min:0,max:1}],\n";
      out << "      state: {conversion: absentState},\n";
      out << "      aux: {catalyst:[0]}, context:{rate_coefficient:0.25},\n";
      out << "      operator_role:\"unavailable_context\", element_kind:\"parcel\"\n";
      out << "    });\n";
      out << "    ctx.emit(\"evo\", {\n";
      out << "      ran: r ? r.ran : null,\n";
      out << "      stages: r ? r.stagesRun : -1,\n";
      out << "      elements: r ? r.elementsEvolved : -1,\n";
      out << "      inferences: r ? r.inferenceCount : -1,\n";
      out << "      firstStage: r ? r.trace[0].model : null,\n";
      out << "      intermediate: r ? r.trace[0].intermediateOutputs.join(\",\") : null,\n";
      out << "      integrated: r ? r.trace[1].integratedFields.join(\",\") : null,\n";
      out << "      auxKeys: r ? r.auxKeys.join(\",\") : null,\n";
      out << "      holdout: r ? r.trace[1].holdoutR2 : \"absent\",\n";
      out << "      selectionMode: r ? r.selection.mode : null,\n";
      out << "      selectionStatus: r ? r.selection.status : null,\n";
      out << "      selectedModels: r ? r.selection.selectedModels.join(\",\") : null,\n";
      out << "      ambiguousStatus: ambiguous ? ambiguous.selection.status : null,\n";
      out << "      ambiguousRan: ambiguous ? ambiguous.ran : null,\n";
      out << "      ambiguousState: ambiguousState,\n";
      out << "      absentStatus: absent ? absent.selection.status : null,\n";
      out << "      absentRan: absent ? absent.ran : null,\n";
      out << "      absentReason: absent ? absent.selection.trace[1].reason : null,\n";
      out << "      absentState: absentState,\n";
      out << "      conversion: conversion,\n";
      out << "      heat: heat,\n";
      out << "      catalyst: catalyst\n";
      out << "    });\n";
      out << "  }\n";
      out << "};\n";
    }
    trech::JsRuntime js;
    const std::string json =
        js.evalExperimentAndGetConfigJson(evolveExp.string());
    (void)json;
    failures += expect(js.loadedModelNames().size() == 4,
                       "Expected all contextual-selection models to load.");

    trech::HookRuntimeContext eCtx{};
    eCtx.determinismMode = "predictive";
    eCtx.eventId = 0;
    eCtx.eventEdepMeV = 2.0;  // ambient edep_mev -> drive = 1.0 + catalyst
    const auto eReport = js.dispatchHook("onEventEnd", eCtx, nullptr, false);
    failures += expect(eReport.invoked, "Expected evolve onEventEnd invocation.");
    // Honest accounting: 2 stages over 3 elements = 6 model evaluations, NOT 2.
    failures += expect(eReport.predictCount == 6,
                       "Expected 2 stages x 3 elements = 6 counted inferences.");
    failures += expect(eReport.starvedCount == 3 && eReport.scaleMismatchCount == 3,
                       "Expected evolve to count density unions and off-band evaluations per element.");
    const auto eEmits = js.takeEmittedRecords();
    failures += expect(eEmits.size() == 1, "Expected one evolve emit.");
    if (!eEmits.empty()) {
      const std::string& p = eEmits[0].payloadJson;
      failures += expect(p.find("\"ran\":true") != std::string::npos,
                         "Expected the operator to report it ran.");
      failures += expect(p.find("\"stages\":2") != std::string::npos,
                         "Expected both operator stages to run.");
      failures += expect(p.find("\"elements\":3") != std::string::npos,
                         "Expected all three elements evolved.");
      failures += expect(p.find("\"inferences\":6") != std::string::npos,
                         "Expected inferenceCount == stages * elements.");
      failures += expect(
          p.find("\"firstStage\":\"nano_op\"") != std::string::npos,
          "Expected the operator to execute in ascending scale order.");
      failures += expect(
          p.find("\"intermediate\":\"drive\"") != std::string::npos,
          "Expected the nano stage's output recorded as an intermediate.");
      failures += expect(
          p.find("\"integrated\":\"conversion,heat\"") != std::string::npos,
          "Expected the macro stage to report both integrated fields.");
      failures += expect(p.find("\"auxKeys\":\"catalyst\"") != std::string::npos,
                         "Expected the per-element aux fact to be bound.");
      failures += expect(p.find("\"holdout\":null") != std::string::npos,
                         "Expected held-out R2 reported null, never 0.");
      failures += expect(
          p.find("\"selectionMode\":\"contextual\"") != std::string::npos &&
              p.find("\"selectionStatus\":\"selected\"") != std::string::npos &&
              p.find("\"selectedModels\":\"macro_op,nano_op\"") !=
                  std::string::npos,
          "Expected role + element kind to select the compatible operator stages.");
      failures += expect(
          p.find("\"ambiguousStatus\":\"ambiguous\"") != std::string::npos &&
              p.find("\"ambiguousRan\":false") != std::string::npos &&
              p.find("\"ambiguousState\":[0.25]") != std::string::npos,
          "Expected ambiguous contextual selection to report and not mutate.");
      failures += expect(
          p.find("\"absentStatus\":\"no_compatible\"") != std::string::npos &&
              p.find("\"absentRan\":false") != std::string::npos &&
              p.find("\"absentReason\":\"missing_context\"") !=
                  std::string::npos &&
              p.find("\"absentState\":[0.5]") != std::string::npos,
          "Expected missing required context to report no-compatible and not mutate.");
      // The engine mutated the scenario's OWN arrays in place.
      //   drive_e = 0.5*edep_mev + catalyst = 1 + catalyst
      //   d_conversion_dt = 0.5*drive - 0.5*conversion ; dt = 2
      //   e0: drive 1.0 -> 0.0 + (0.5*1.0 - 0.5*0.0)*2 = 1.0
      //   e1: drive 2.0 -> 0.4 + (0.5*2.0 - 0.5*0.4)*2 = 2.0 -> clamped to 1.0
      //   e2: drive 3.0 -> 0.9 + (0.5*3.0 - 0.5*0.9)*2 = 3.0 -> clamped to 1.0
      failures += expect(
          p.find("\"conversion\":[1.0,1.0,1.0]") != std::string::npos ||
              p.find("\"conversion\":[1,1,1]") != std::string::npos,
          "Expected conversion integrated in place and held at its declared max.");
      //   d_heat_dt = 10*0.25 = 2.5 -> heat = 300 + 2.5*2 = 305 for every element
      failures += expect(
          p.find("\"heat\":[305.0,305.0,305.0]") != std::string::npos ||
              p.find("\"heat\":[305,305,305]") != std::string::npos,
          "Expected the scenario-supplied coefficient to drive the heat field.");
      // Aux arrays are read-only: the engine must not write back through them.
      failures += expect(
          p.find("\"catalyst\":[0.0,1.0,2.0]") != std::string::npos ||
              p.find("\"catalyst\":[0,1,2]") != std::string::npos,
          "Expected aux arrays left untouched.");
    }

    // Strict mode disables the operator: it returns null AND leaves the state
    // untouched, so a strict run can never silently pick up inferred physics.
    trech::HookRuntimeContext strictE = eCtx;
    strictE.determinismMode = "strict";
    const auto strictEReport =
        js.dispatchHook("onEventEnd", strictE, nullptr, false);
    failures += expect(strictEReport.predictCount == 0,
                       "Expected strict mode to disable ctx.evolve.");
    failures += expect(strictEReport.starvedCount == 0 && strictEReport.scaleMismatchCount == 0,
                       "Expected strict evolve dispatch to reset density/band counts.");
    const auto strictEEmits = js.takeEmittedRecords();
    failures += expect(
        !strictEEmits.empty() &&
            strictEEmits[0].payloadJson.find("\"ran\":null") != std::string::npos,
        "Expected strict-mode ctx.evolve to return null.");
    failures += expect(
        !strictEEmits.empty() &&
            (strictEEmits[0].payloadJson.find("\"conversion\":[0.0,0.4,0.9]") !=
                 std::string::npos ||
             strictEEmits[0].payloadJson.find("\"conversion\":[0,0.4,0.9]") !=
                 std::string::npos),
        "Expected strict-mode ctx.evolve to leave the state untouched.");
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.evolve runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.evolve domain routing: an undeclared population over several operator
  // kinds of ONE role is grouped by trained domain instead of being declined
  // as ambiguous; `group_by: "declared"` keeps the label-only contract.
  fs::path routeWax = fixture.path() / ("trech_js_route_wax_" + stamp + ".json");
  fs::path routeCarrier = fixture.path() / ("trech_js_route_carrier_" + stamp + ".json");
  fs::path routeLoose = fixture.path() / ("trech_js_route_loose_" + stamp + ".json");
  fs::path routeExp = fixture.path() / ("trech_js_route_exp_" + stamp + ".js");
  try {
    auto writeModel = [](const fs::path& path, double mean, double bias) {
      std::ofstream m(path);
      m << "{\"model\":\"generic_surrogate_v1\",\"input_features\":[\"comp\"],"
        << "\"output_features\":[\"d_temp_dt\"],\"input_mean\":[" << mean
        << "],\"input_std\":[1],\"input_domain\":{\"standardized_radius\":[1]},"
        << "\"layers\":[{\"weights\":[[0.0]],\"bias\":[" << bias
        << "],\"activation\":\"none\"}]}";
    };
    writeModel(routeWax, -5.0, 1.0);
    writeModel(routeCarrier, 5.0, 2.0);
    writeModel(routeLoose, 0.0, 3.0);
    {
      std::ofstream out(routeExp);
      out << "globalThis.TRECH_CONFIG={run:{nEvents:1,seed:3},determinism:{mode:\"predictive\"},\n";
      out << " models:[\n";
      out << "  {name:\"wax_op\",scale:\"meso\",operator_role:\"thermal\",element_kind:\"wax\",path:\""
          << routeWax.generic_string() << "\"},\n";
      out << "  {name:\"carrier_op\",scale:\"meso\",operator_role:\"thermal\",element_kind:\"carrier\",path:\""
          << routeCarrier.generic_string() << "\"},\n";
      out << "  {name:\"loose_op\",scale:\"meso\",operator_role:\"unlabelled\",path:\""
          << routeLoose.generic_string() << "\"}]};\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      out << " const temp=[0,0,0];\n";
      out << " const r=ctx.evolve({dt:1,fields:[\"temp\"],state:{temp},aux:{comp:[-5,5,50]},operator_role:\"thermal\"});\n";
      out << " const declaredTemp=[0];\n";
      out << " const d=ctx.evolve({dt:1,fields:[\"temp\"],state:{temp:declaredTemp},aux:{comp:[-5]},"
             "operator_role:\"thermal\",group_by:\"declared\"});\n";
      out << " const looseTemp=[0];\n";
      out << " const l=ctx.evolve({dt:1,fields:[\"temp\"],state:{temp:looseTemp},aux:{comp:[0]},operator_role:\"unlabelled\"});\n";
      out << " let bad=null; try{ctx.evolve({dt:1,fields:[\"temp\"],state:{temp:[0]},aux:{comp:[0]},"
             "operator_role:\"thermal\",group_by:\"kind\"});}catch(e){bad=String(e.message);}\n";
      out << " ctx.emit(\"route\",{temp,status:r.selection.status,grouping:r.selection.grouping,\n";
      out << "  reason:r.selection.trace[0].reason,sets:r.routing.sets.length,\n";
      out << "  covered:r.routing.sets[0].elementsCovered,uncovered:r.routing.sets[0].elementsUncovered,\n";
      out << "  groups:r.routing.groups.length,elementGroups:r.routing.elementGroups,\n";
      out << "  paths:r.routing.groups.map(g=>g.path.join(\"+\")).sort().join(\"|\"),\n";
      out << "  declaredStatus:d.selection.status,declaredGrouping:d.selection.grouping===undefined,declaredTemp,\n";
      out << "  looseStatus:l.selection.status,looseGrouping:l.selection.grouping,looseRouting:l.routing===undefined,looseTemp,bad});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(routeExp.string());
    trech::HookRuntimeContext rCtx{};
    rCtx.determinismMode = "predictive";
    rCtx.eventId = 0;
    (void)js.dispatchHook("onEventEnd", rCtx, nullptr, false);
    const auto rEmits = js.takeEmittedRecords();
    failures += expect(rEmits.size() == 1, "Expected one domain-routing emit.");
    if (!rEmits.empty()) {
      const std::string& p = rEmits[0].payloadJson;
      failures += expect((p.find("\"temp\":[1,2,0]") != std::string::npos ||
                          p.find("\"temp\":[1.0,2.0,0.0]") != std::string::npos),
                         "Expected each element advanced by the law whose domain covers it, "
                         "and the uncovered one untouched.");
      failures += expect(p.find("\"status\":\"selected\"") != std::string::npos &&
                             p.find("\"grouping\":\"domain\"") != std::string::npos &&
                             p.find("\"reason\":\"domain_routed\"") != std::string::npos,
                         "Expected an undeclared same-role pool to be selected for domain routing.");
      failures += expect(p.find("\"sets\":1") != std::string::npos &&
                             p.find("\"uncovered\":1") != std::string::npos &&
                             p.find("\"groups\":3") != std::string::npos &&
                             p.find("\"paths\":\"|carrier_op|wax_op\"") != std::string::npos,
                         "Expected one rival set and three unnamed groups (wax, carrier, none).");
      failures += expect(p.find("\"declaredStatus\":\"ambiguous\"") != std::string::npos &&
                             p.find("\"declaredGrouping\":true") != std::string::npos &&
                             (p.find("\"declaredTemp\":[0]") != std::string::npos ||
                              p.find("\"declaredTemp\":[0.0]") != std::string::npos),
                         "Expected group_by declared to keep the ambiguous verdict and no field.");
      failures += expect(p.find("\"looseStatus\":\"selected\"") != std::string::npos &&
                             p.find("\"looseGrouping\":\"domain\"") != std::string::npos &&
                             p.find("\"looseRouting\":true") != std::string::npos &&
                             (p.find("\"looseTemp\":[3]") != std::string::npos ||
                              p.find("\"looseTemp\":[3.0]") != std::string::npos),
                         "Expected an unlabelled model to be selectable without rivals.");
      failures += expect(p.find("group_by must be") != std::string::npos,
                         "Expected an invalid group_by to throw.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS domain-routing runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.react: learned hazards + engine-owned seeded discrete transitions.
  // The scenario declares integer inventories, stoichiometry and conserved
  // atoms; the model never writes counts directly.
  try {
    {
      std::ofstream model(reactModel);
      model << "{\"model\":\"generic_surrogate_v1\","
            << "\"input_features\":[\"drive\"],"
            << "\"output_features\":[\"hazard_electrolysis\","
               "\"hazard_combustion\"],"
            << "\"trained_scale_bands\":[\"nano\"],"
            << "\"input_domain\":{\"standardized_radius\":[5],"
            << "\"input_min\":[0],\"input_max\":[4],"
            << "\"occupancy\":{\"bins\":4,\"counts\":[[2,0,2,2]]},"
            << "\"joint\":{\"centers\":[[0]],\"radius\":0.1}},"
            << "\"layers\":[{\"weights\":[[0.0],[0.0]],"
            << "\"bias\":[1.0,0.0],\"activation\":\"none\"}]}";
    }
    {
      std::ofstream out(reactExp);
      out << "globalThis.TRECH_CONFIG={\n";
      out << " run:{nEvents:1,seed:99},determinism:{mode:\"predictive\"},\n";
      out << " models:[{name:\"reaction_op\",scale:\"meso\","
             "operator_role:\"discrete_reaction\","
             "element_kind:\"reaction_site\","
             "required_context_keys:[\"drive\"],path:\""
          << reactModel.generic_string() << "\"}]\n";
      out << "};\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      out << " const water=[2,1],hydrogen=[0,0],oxygen=[0,0];\n";
      out << " const r=ctx.react({dt:1,species:[\"water\",\"hydrogen\",\"oxygen\"],\n";
      out << "  state:{water,hydrogen,oxygen},context:{drive:1},\n";
      out << "  operator_role:\"discrete_reaction\",element_kind:\"reaction_site\",\n";
      out << "  channels:[\n";
      out << "   {name:\"electrolysis\",delta:{water:-2,hydrogen:2,oxygen:1}},\n";
      out << "   {name:\"combustion\",delta:{water:2,hydrogen:-2,oxygen:-1}}],\n";
      out << "  conservation:[\n";
      out << "   {name:\"H_atoms\",coefficients:{water:2,hydrogen:2}},\n";
      out << "   {name:\"O_atoms\",coefficients:{water:1,oxygen:2}}]\n";
      out << " });\n";
      // Invalid atom balance: must be rejected before inference/RNG/mutation.
      out << " const badWater=[2],badHydrogen=[0],badOxygen=[0];\n";
      out << " const bad=ctx.react({dt:1,species:[\"water\",\"hydrogen\",\"oxygen\"],\n";
      out << "  state:{water:badWater,hydrogen:badHydrogen,oxygen:badOxygen},"
             "context:{drive:1},models:[\"reaction_op\"],\n";
      out << "  channels:[{name:\"bad\",delta:{water:-2,hydrogen:1,oxygen:1}}],\n";
      out << "  conservation:[{name:\"H_atoms\",coefficients:{water:2,hydrogen:2}}]\n";
      out << " });\n";
      out << " ctx.emit(\"react\",{ran:r?r.ran:null,mode:r?r.hazardMode:null,"
             "selection:r?r.selection.status:null,inferences:r?r.inferenceCount:-1,"
             "draws:r?r.drawCount:-1,attempts:r?r.transitionAttempts:-1,"
             "accepted:r?r.transitionsAccepted:-1,rejected:r?r.rejectedAvailability:-1,"
             "water,hydrogen,oxygen,badValid:bad?bad.transitionSchemaValid:null,"
             "badInferences:bad?bad.inferenceCount:-1,badDraws:bad?bad.drawCount:-1,"
             "badWater});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(reactExp.string());
    trech::HookRuntimeContext reactCtx{};
    reactCtx.determinismMode = "predictive";
    reactCtx.seed = 99;
    reactCtx.eventId = 0;
    const auto report =
        js.dispatchHook("onEventEnd", reactCtx, nullptr, false);
    failures += expect(report.predictCount == 2,
                       "Expected ctx.react to count one inference per element.");
    failures += expect(report.starvedCount == 2 && report.scaleMismatchCount == 2 &&
                           report.outOfDomainCount == 0,
                       "Expected react density unions/off-band counts without OOD or invalid-call counts.");
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 1, "Expected one ctx.react emit.");
    if (!emits.empty()) {
      const std::string& payload = emits[0].payloadJson;
      failures += expect(
          payload.find("\"ran\":true") != std::string::npos &&
              payload.find("\"mode\":\"direct\"") != std::string::npos &&
              payload.find("\"selection\":\"selected\"") != std::string::npos,
          "Expected contextual discrete operator selection and direct hazards.");
      failures += expect(
          payload.find("\"inferences\":2") != std::string::npos &&
              payload.find("\"draws\":2") != std::string::npos &&
              payload.find("\"attempts\":2") != std::string::npos &&
              payload.find("\"accepted\":1") != std::string::npos &&
              payload.find("\"rejected\":1") != std::string::npos,
          "Expected honest discrete inference/draw/attempt/accept accounting.");
      failures += expect(
          (payload.find("\"water\":[0,1]") != std::string::npos ||
           payload.find("\"water\":[0.0,1.0]") != std::string::npos) &&
              (payload.find("\"hydrogen\":[2,0]") != std::string::npos ||
               payload.find("\"hydrogen\":[2.0,0.0]") != std::string::npos) &&
              (payload.find("\"oxygen\":[1,0]") != std::string::npos ||
               payload.find("\"oxygen\":[1.0,0.0]") != std::string::npos),
          "Expected atomic stoichiometry and non-negative availability.");
      failures += expect(
          payload.find("\"badValid\":false") != std::string::npos &&
              payload.find("\"badInferences\":0") != std::string::npos &&
              payload.find("\"badDraws\":0") != std::string::npos &&
              (payload.find("\"badWater\":[2]") != std::string::npos ||
               payload.find("\"badWater\":[2.0]") != std::string::npos),
          "Expected non-conserving topology rejected before infer/draw/mutate.");
    }

    const auto replayReport =
        js.dispatchHook("onEventEnd", reactCtx, nullptr, false);
    const auto replayEmits = js.takeEmittedRecords();
    failures += expect(
        replayReport.predictCount == 2 && !emits.empty() &&
            replayEmits.size() == 1 &&
            replayEmits[0].payloadJson == emits[0].payloadJson,
        "Expected identical hook identity/seed to replay ctx.react byte-for-byte.");

    trech::HookRuntimeContext strictReact = reactCtx;
    strictReact.determinismMode = "strict";
    const auto strictReport =
        js.dispatchHook("onEventEnd", strictReact, nullptr, false);
    failures += expect(strictReport.predictCount == 0,
                       "Expected strict mode to disable ctx.react.");
    failures += expect(strictReport.starvedCount == 0 && strictReport.scaleMismatchCount == 0,
                       "Expected strict react dispatch to reset density/band counts.");
    const auto strictEmits = js.takeEmittedRecords();
    failures += expect(
        !strictEmits.empty() &&
            strictEmits[0].payloadJson.find("\"ran\":null") !=
                std::string::npos &&
            (strictEmits[0].payloadJson.find("\"water\":[2,1]") !=
                 std::string::npos ||
             strictEmits[0].payloadJson.find("\"water\":[2.0,1.0]") !=
                 std::string::npos),
        "Expected strict ctx.react to return null and leave state untouched.");
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.react runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.react rival arbitration: two hazard laws of one role cover the same
  // cells. `reference_hazards` (per-cell transition probability this step) is
  // evidence; the engine learns per context domain which law to draw from and
  // keeps applying it on a later call without evidence.
  fs::path rivalUp = fixture.path() / ("trech_js_react_rival_up_" + stamp + ".json");
  fs::path rivalDown = fixture.path() / ("trech_js_react_rival_down_" + stamp + ".json");
  fs::path rivalExp = fixture.path() / ("trech_js_react_rival_" + stamp + ".js");
  try {
    auto writeHazard = [](const fs::path& path, double weight, double bias) {
      std::ofstream m(path);
      m << "{\"model\":\"generic_surrogate_v1\",\"input_features\":[\"x\"],"
        << "\"output_features\":[\"hazard_electrolysis\"],\"input_mean\":[0],"
        << "\"input_std\":[1],\"input_domain\":{\"standardized_radius\":[10]},"
        << "\"layers\":[{\"weights\":[[" << weight << "]],\"bias\":[" << bias
        << "],\"activation\":\"none\"}]}";
    };
    writeHazard(rivalUp, 0.4, 0.0);
    writeHazard(rivalDown, -0.4, 0.4);
    {
      std::ofstream out(rivalExp);
      out << "globalThis.TRECH_CONFIG={run:{nEvents:1,seed:5},determinism:{mode:\"predictive\"},\n";
      out << " models:[\n";
      out << "  {name:\"law_up\",scale:\"meso\",operator_role:\"split\",element_kind:\"a\",path:\""
          << rivalUp.generic_string() << "\"},\n";
      out << "  {name:\"law_down\",scale:\"meso\",operator_role:\"split\",element_kind:\"b\",path:\""
          << rivalDown.generic_string() << "\"}]};\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      out << " const N=64; const spec=(call,ref)=>{\n";
      out << "  const x=[],water=[],hydrogen=[],oxygen=[];\n";
      out << "  for(let e=0;e<N;e++){x.push(((e*37+call*11)%N)/63);water.push(4);hydrogen.push(0);oxygen.push(0);}\n";
      out << "  const s={dt:1,species:[\"water\",\"hydrogen\",\"oxygen\"],state:{water,hydrogen,oxygen},aux:{x},\n";
      out << "   operator_role:\"split\",channels:[{name:\"electrolysis\",delta:{water:-2,hydrogen:2,oxygen:1}}],\n";
      out << "   conservation:[{name:\"H\",coefficients:{water:2,hydrogen:2}},{name:\"O\",coefficients:{water:1,oxygen:2}}]};\n";
      out << "  if(ref) s.reference_hazards={electrolysis:x.map(v=>v<0.5?0.4*v:0.4*(1-v))};\n";
      out << "  return s; };\n";
      out << " let late=null;\n";
      out << " for(let call=0;call<40;call++){const r=ctx.react(spec(call,true)); if(call===39) late=r.rival_arbitration.sets[0];}\n";
      out << " const d=spec(40,false); d.report_arbitration=true; const dep=ctx.react(d);\n";
      out << " let bad=null; try{const b=spec(41,false); b.reference_hazards={nope:[0]}; ctx.react(b);}catch(e){bad=String(e.message);}\n";
      out << " const set=dep.rival_arbitration.sets[0];\n";
      out << " ctx.emit(\"react_rivals\",{lateRmse:late.arbitrated_rmse,lateApplied:late.applied,lateGraded:late.graded,\n";
      out << "  depApplied:set.applied,depGraded:set.graded,up:set.selected.law_up,down:set.selected.law_down,\n";
      out << "  combined:set.selected.cooperating_sum,summaryKeys:Object.keys(dep.rival_arbitration.summary).length,bad});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(rivalExp.string());
    trech::HookRuntimeContext rvCtx{};
    rvCtx.determinismMode = "predictive";
    rvCtx.seed = 5;
    rvCtx.eventId = 0;
    (void)js.dispatchHook("onEventEnd", rvCtx, nullptr, false);
    const auto rvEmits = js.takeEmittedRecords();
    failures += expect(rvEmits.size() == 1, "Expected one ctx.react rival-arbitration emit.");
    if (!rvEmits.empty()) {
      const auto j = nlohmann::json::parse(rvEmits[0].payloadJson);
      std::cout << "ctx.react rival arbitration: " << rvEmits[0].payloadJson << "\n";
      failures += expect(j.at("lateGraded").get<bool>() && j.at("lateApplied").get<bool>() &&
                             j.at("lateRmse").get<double>() < 0.02,
                         "Expected graded react rivals to converge on the right law per context domain.");
      failures += expect(!j.at("depGraded").get<bool>() && j.at("depApplied").get<bool>() &&
                             j.at("up").get<int>() + j.at("down").get<int>() == 64 &&
                             j.at("up").get<int>() > 0 && j.at("down").get<int>() > 0 &&
                             j.at("combined").get<int>() == 0 && j.at("summaryKeys").get<int>() == 1,
                         "Expected an ungraded react call to deploy the learned per-domain choice.");
      failures += expect(j.at("bad").is_string() &&
                             j.at("bad").get<std::string>().find("reference_hazards.nope") != std::string::npos,
                         "Expected reference_hazards to name declared channels only.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.react rival arbitration error: " << ex.what() << "\n";
    failures += 1;
  }
  fs::remove(rivalUp);
  fs::remove(rivalDown);
  fs::remove(rivalExp);

  // ctx.cascade rival arbitration: two nano models declare the same output.
  // `reference` evidence in the options teaches the per-context choice; an
  // ungraded call then applies it before the macro stage reads the fact.
  fs::path cascUp = fixture.path() / ("trech_js_casc_rival_up_" + stamp + ".json");
  fs::path cascDown = fixture.path() / ("trech_js_casc_rival_down_" + stamp + ".json");
  fs::path cascObs = fixture.path() / ("trech_js_casc_rival_obs_" + stamp + ".json");
  fs::path cascExp = fixture.path() / ("trech_js_casc_rival_" + stamp + ".js");
  try {
    auto writeLinear = [](const fs::path& path, const char* in, const char* out, double weight, double bias) {
      std::ofstream m(path);
      m << "{\"model\":\"generic_surrogate_v1\",\"input_features\":[\"" << in << "\"],"
        << "\"output_features\":[\"" << out << "\"],\"input_mean\":[0],\"input_std\":[1],"
        << "\"input_domain\":{\"standardized_radius\":[10]},"
        << "\"layers\":[{\"weights\":[[" << weight << "]],\"bias\":[" << bias
        << "],\"activation\":\"none\"}]}";
    };
    writeLinear(cascUp, "x", "y", 1.0, 0.0);
    writeLinear(cascDown, "x", "y", -1.0, 1.0);
    writeLinear(cascObs, "y", "obs", 2.0, 0.0);
    {
      std::ofstream out(cascExp);
      out << "globalThis.TRECH_CONFIG={run:{nEvents:1,seed:5},determinism:{mode:\"predictive\"},\n";
      out << " models:[{name:\"up\",scale:\"nano\",path:\"" << cascUp.generic_string() << "\"},\n";
      out << "  {name:\"down\",scale:\"nano\",path:\"" << cascDown.generic_string() << "\"},\n";
      out << "  {name:\"obs\",scale:\"macro\",path:\"" << cascObs.generic_string() << "\"}]};\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      out << " const names=[\"up\",\"down\",\"obs\"]; const truth=x=>x<0.5?x:1-x;\n";
      out << " const before=ctx.cascade({x:0.9},names);\n";
      out << " for(let call=0;call<80;call++){const x=((call*37)%64)/63; ctx.cascade({x},names,{reference:{y:truth(x)}});}\n";
      out << " const dep=ctx.cascade({x:0.9},names,{report_arbitration:true});\n";
      out << " let bad=null; try{ctx.cascade({x:0.1},names,{reference:{y:\"high\"}});}catch(e){bad=String(e.message);}\n";
      out << " const set=dep.__cascade.rival_arbitration.sets[0];\n";
      out << " ctx.emit(\"cascade_rivals\",{beforeY:before.y,beforeArb:before.__cascade.rival_arbitration===undefined,\n";
      out << "  y:dep.y,obs:dep.obs,graded:set.graded,applied:set.applied,models:set.models,fields:set.fields,\n";
      out << "  summaryKeys:Object.keys(dep.__cascade.rival_arbitration.summary).length,bad});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(cascExp.string());
    trech::HookRuntimeContext cCtx{};
    cCtx.determinismMode = "predictive";
    cCtx.seed = 5;
    cCtx.eventId = 0;
    (void)js.dispatchHook("onEventEnd", cCtx, nullptr, false);
    const auto cEmits = js.takeEmittedRecords();
    failures += expect(cEmits.size() == 1, "Expected one ctx.cascade rival-arbitration emit.");
    if (!cEmits.empty()) {
      const auto j = nlohmann::json::parse(cEmits[0].payloadJson);
      std::cout << "ctx.cascade rival arbitration: " << cEmits[0].payloadJson << "\n";
      failures += expect(std::abs(j.at("beforeY").get<double>() - 0.9) < 1e-9 && j.at("beforeArb").get<bool>(),
                         "Expected an unarbitrated cascade to keep the last rival's (up) output and report nothing.");
      failures += expect(!j.at("graded").get<bool>() && j.at("applied").get<bool>() &&
                             std::abs(j.at("y").get<double>() - 0.1) < 1e-9 &&
                             std::abs(j.at("obs").get<double>() - 0.2) < 1e-9 &&
                             j.at("fields") == nlohmann::json::array({"y"}) &&
                             j.at("summaryKeys").get<int>() == 1,
                         "Expected the learned rival choice to set the fact the macro stage reads.");
      failures += expect(j.at("bad").is_string() &&
                             j.at("bad").get<std::string>().find("reference.y") != std::string::npos,
                         "Expected a non-numeric cascade reference to be rejected.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.cascade rival arbitration error: " << ex.what() << "\n";
    failures += 1;
  }
  fs::remove(cascUp);
  fs::remove(cascDown);
  fs::remove(cascObs);
  fs::remove(cascExp);

  // ctx.interact domain routing + rival arbitration: two heat-exchange pair
  // laws of one role and different kinds. An undeclared call routes pairs by
  // trained domain; `reference_pairs` evidence (per declared link) teaches the
  // per-context choice, and a later ungraded call applies it.
  fs::path pairUp = fixture.path() / ("trech_js_pair_rival_up_" + stamp + ".json");
  fs::path pairDown = fixture.path() / ("trech_js_pair_rival_down_" + stamp + ".json");
  fs::path pairExp = fixture.path() / ("trech_js_pair_rival_" + stamp + ".js");
  try {
    auto writePair = [](const fs::path& path, double weight, double bias) {
      std::ofstream m(path);
      m << "{\"model\":\"generic_surrogate_v1\",\"input_features\":[\"a_x\"],"
        << "\"output_features\":[\"d_heat_dt\"],\"input_mean\":[0],\"input_std\":[1],"
        << "\"input_domain\":{\"standardized_radius\":[10]},"
        << "\"layers\":[{\"weights\":[[" << weight << "]],\"bias\":[" << bias
        << "],\"activation\":\"none\"}]}";
    };
    writePair(pairUp, 1.0, 0.0);
    writePair(pairDown, -1.0, 1.0);
    {
      std::ofstream out(pairExp);
      out << "globalThis.TRECH_CONFIG={run:{nEvents:1,seed:5},determinism:{mode:\"predictive\"},\n";
      out << " models:[{name:\"law_up\",scale:\"meso\",operator_role:\"exchange\",element_kind:\"a\",path:\""
          << pairUp.generic_string() << "\"},\n";
      out << "  {name:\"law_down\",scale:\"meso\",operator_role:\"exchange\",element_kind:\"b\",path:\""
          << pairDown.generic_string() << "\"}]};\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      out << " const N=64; const truth=x=>x<0.5?x:1-x;\n";
      out << " const spec=(call,ref)=>{const x=[],a=[],b=[];\n";
      out << "  for(let i=0;i<N;i++){const v=((i*37+call*11)%N)/63; x.push(v,v); a.push(2*i); b.push(2*i+1);}\n";
      out << "  const s={dt:1,fields:[{name:\"heat\",symmetry:\"antisymmetric\"}],state:{heat:new Array(2*N).fill(0)},\n";
      out << "   aux:{x},links:{a,b},operator_role:\"exchange\"};\n";
      out << "  if(ref) s.reference_pairs={values:{d_heat_dt:a.map((_,i)=>truth(x[2*i]))}};\n";
      out << "  return s;};\n";
      out << " const plain=ctx.interact(spec(0,false));\n";
      out << " let late=null; for(let call=0;call<40;call++){const r=ctx.interact(spec(call,true)); if(call===39) late=r.rival_arbitration.sets[0];}\n";
      out << " const d=spec(40,false); d.report_arbitration=true; const dep=ctx.interact(d);\n";
      out << " let err=0; for(let i=0;i<N;i++){const e=d.state.heat[2*i]-truth(d.aux.x[2*i]); err+=e*e;}\n";
      out << " let bad=null; try{const b=spec(41,false); b.reference_pairs={values:{nope:[]}}; ctx.interact(b);}catch(e){bad=String(e.message);}\n";
      out << " const declared=spec(0,false); declared.group_by=\"declared\"; const dec=ctx.interact(declared);\n";
      out << " ctx.emit(\"pair_rivals\",{grouping:plain.selection.grouping,\n";
      out << "  routed:!!plain.routing,pairs:plain.pairs.length,firstPair:plain.pairs[0],groups:plain.routing.groups.length,\n";
      out << "  plainArb:plain.rival_arbitration===undefined,lateApplied:late.applied,lateRmse:late.arbitrated_rmse,\n";
      out << "  depApplied:dep.rival_arbitration.sets[0].applied,depGraded:dep.rival_arbitration.sets[0].graded,\n";
      out << "  depRmse:Math.sqrt(err/N),fields:dep.rival_arbitration.sets[0].fields,\n";
      out << "  declaredStatus:dec.selection.status,bad});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(pairExp.string());
    trech::HookRuntimeContext pCtx{};
    pCtx.determinismMode = "predictive";
    pCtx.seed = 5;
    pCtx.eventId = 0;
    (void)js.dispatchHook("onEventEnd", pCtx, nullptr, false);
    const auto pEmits = js.takeEmittedRecords();
    failures += expect(pEmits.size() == 1, "Expected one ctx.interact rival-arbitration emit.");
    if (!pEmits.empty()) {
      const auto j = nlohmann::json::parse(pEmits[0].payloadJson);
      std::cout << "ctx.interact rival arbitration: " << pEmits[0].payloadJson << "\n";
      failures += expect(j.at("grouping") == "domain" && j.at("routed").get<bool>() &&
                             j.at("pairs").get<int>() == 64 && j.at("firstPair") == nlohmann::json::array({0, 1}) &&
                             j.at("plainArb").get<bool>(),
                         "Expected an undeclared same-role ctx.interact pool to route pairs by domain.");
      failures += expect(j.at("lateApplied").get<bool>() && j.at("lateRmse").get<double>() < 0.02 &&
                             j.at("depApplied").get<bool>() && !j.at("depGraded").get<bool>() &&
                             j.at("depRmse").get<double>() < 0.02 &&
                             j.at("fields") == nlohmann::json::array({"d_heat_dt"}),
                         "Expected pair evidence to teach a per-context choice that an ungraded call applies.");
      failures += expect(j.at("declaredStatus") == "ambiguous",
                         "Expected group_by declared to keep the ambiguous verdict for ctx.interact.");
      failures += expect(j.at("bad").is_string() &&
                             j.at("bad").get<std::string>().find("reference_pairs.values.nope") != std::string::npos,
                         "Expected reference_pairs to name outputs of the selected models only.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.interact rival arbitration error: " << ex.what() << "\n";
    failures += 1;
  }
  fs::remove(pairUp);
  fs::remove(pairDown);
  fs::remove(pairExp);

  // Rival arbiters across runs: run 1 learns ctx.react rivals from evidence and
  // exports every pool; run 2 (a new runtime) restores the export frozen and
  // deploys the learned choice without evidence, learning nothing more.
  fs::path carryUp = fixture.path() / ("trech_js_carry_up_" + stamp + ".json");
  fs::path carryDown = fixture.path() / ("trech_js_carry_down_" + stamp + ".json");
  fs::path carryState = fixture.path() / ("trech_js_carry_state_" + stamp + ".json");
  fs::path carryTrain = fixture.path() / ("trech_js_carry_train_" + stamp + ".js");
  fs::path carryDeploy = fixture.path() / ("trech_js_carry_deploy_" + stamp + ".js");
  try {
    auto writeHazard = [](const fs::path& path, double weight, double bias) {
      std::ofstream m(path);
      m << "{\"model\":\"generic_surrogate_v1\",\"input_features\":[\"x\"],"
        << "\"output_features\":[\"hazard_electrolysis\"],\"input_mean\":[0],"
        << "\"input_std\":[1],\"input_domain\":{\"standardized_radius\":[10]},"
        << "\"layers\":[{\"weights\":[[" << weight << "]],\"bias\":[" << bias
        << "],\"activation\":\"none\"}]}";
    };
    writeHazard(carryUp, 0.4, 0.0);
    writeHazard(carryDown, -0.4, 0.4);
    auto writeScenario = [&](const fs::path& path, const std::string& body) {
      std::ofstream out(path);
      out << "globalThis.TRECH_CONFIG={run:{nEvents:1,seed:5},determinism:{mode:\"predictive\"},\n";
      out << " models:[{name:\"law_up\",scale:\"meso\",operator_role:\"split\",element_kind:\"a\",path:\""
          << carryUp.generic_string() << "\"},\n";
      out << "  {name:\"law_down\",scale:\"meso\",operator_role:\"split\",element_kind:\"b\",path:\""
          << carryDown.generic_string() << "\"}]};\n";
      out << "const N=64; const spec=(call,ref)=>{const x=[],water=[],hydrogen=[],oxygen=[];\n";
      out << " for(let e=0;e<N;e++){x.push(((e*37+call*11)%N)/63);water.push(4);hydrogen.push(0);oxygen.push(0);}\n";
      out << " const s={dt:1,species:[\"water\",\"hydrogen\",\"oxygen\"],state:{water,hydrogen,oxygen},aux:{x},\n";
      out << "  operator_role:\"split\",channels:[{name:\"electrolysis\",delta:{water:-2,hydrogen:2,oxygen:1}}],\n";
      out << "  conservation:[{name:\"H\",coefficients:{water:2,hydrogen:2}},{name:\"O\",coefficients:{water:1,oxygen:2}}]};\n";
      out << " if(ref) s.reference_hazards={electrolysis:x.map(v=>v<0.5?0.4*v:0.4*(1-v))};\n";
      out << " return s;};\n";
      out << body;
    };
    writeScenario(carryTrain,
        "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n"
        " for(let call=0;call<40;call++) ctx.react(spec(call,true));\n"
        " const st=ctx.arbitrationState();\n"
        " ctx.emit(\"arbitration_state\",{state:st,reactSets:Object.keys(st.pools.react.sets).length,\n"
        "  evolveSets:Object.keys(st.pools.evolve.sets).length});\n"
        "}};\n");
    writeScenario(carryDeploy,
        "const STATE=TRECH_READ_JSON(\"" + carryState.generic_string() + "\");\n"
        "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n"
        " const restored=ctx.restoreArbitration(STATE,{frozen:true});\n"
        " const d=spec(40,false); d.report_arbitration=true; const dep=ctx.react(d);\n"
        " const g=spec(41,true); g.report_arbitration=true; const graded=ctx.react(g);\n"
        " const after=ctx.arbitrationState();\n"
        " let bad=null; try{ctx.restoreArbitration({format:\"nope\"});}catch(e){bad=String(e.message);}\n"
        " const set=dep.rival_arbitration.sets[0], key=Object.keys(graded.rival_arbitration.summary)[0];\n"
        " ctx.emit(\"deploy\",{restored,applied:set.applied,up:set.selected.law_up,down:set.selected.law_down,\n"
        "  combined:set.selected.cooperating_sum,frozen:graded.rival_arbitration.summary[key].frozen===true,\n"
        "  gradedRmse:graded.rival_arbitration.sets[0].arbitrated_rmse,\n"
        "  unchanged:JSON.stringify(after.pools.react.sets[key].arbiter)===JSON.stringify(STATE.pools.react.sets[key].arbiter),bad});\n"
        "}};\n");
    {
      trech::JsRuntime js;
      (void)js.evalExperimentAndGetConfigJson(carryTrain.string());
      trech::HookRuntimeContext tCtx{};
      tCtx.determinismMode = "predictive";
      tCtx.seed = 5;
      (void)js.dispatchHook("onEventEnd", tCtx, nullptr, false);
      const auto emits = js.takeEmittedRecords();
      failures += expect(emits.size() == 1, "Expected one arbitration-state emit.");
      if (!emits.empty()) {
        const auto j = nlohmann::json::parse(emits[0].payloadJson);
        failures += expect(j.at("reactSets").get<int>() == 1 && j.at("evolveSets").get<int>() == 0,
                           "Expected the export to hold the learned react set and empty other pools.");
        std::ofstream(carryState) << j.at("state").dump();
      }
    }
    {
      trech::JsRuntime js;
      (void)js.evalExperimentAndGetConfigJson(carryDeploy.string());
      trech::HookRuntimeContext dCtx{};
      dCtx.determinismMode = "predictive";
      dCtx.seed = 6;
      (void)js.dispatchHook("onEventEnd", dCtx, nullptr, false);
      const auto emits = js.takeEmittedRecords();
      failures += expect(emits.size() == 1, "Expected one frozen-deployment emit.");
      if (!emits.empty()) {
        const auto j = nlohmann::json::parse(emits[0].payloadJson);
        std::cout << "restored rival arbitration: " << emits[0].payloadJson << "\n";
        failures += expect(j.at("restored").at("frozen").get<bool>() &&
                               j.at("restored").at("pools").at("react").get<int>() == 1 &&
                               j.at("applied").get<bool>() && j.at("up").get<int>() == 32 &&
                               j.at("down").get<int>() == 32 && j.at("combined").get<int>() == 0,
                           "Expected a new run to deploy the restored per-domain choice without evidence.");
        failures += expect(j.at("frozen").get<bool>() && j.at("gradedRmse").get<double>() < 0.02 &&
                               j.at("unchanged").get<bool>(),
                           "Expected a frozen restored pool to grade a held-out call and learn nothing.");
        failures += expect(j.at("bad").is_string() &&
                               j.at("bad").get<std::string>().find("trech_rival_arbitration_pools_v1") != std::string::npos,
                           "Expected an unknown arbitration state to be rejected.");
      }
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS rival arbitration export/restore error: " << ex.what() << "\n";
    failures += 1;
  }
  fs::remove(carryUp);
  fs::remove(carryDown);
  fs::remove(carryState);
  fs::remove(carryTrain);
  fs::remove(carryDeploy);

  // ctx.evolveField across runs: export_state returns the field arbiter and its methods'
  // learned state; options.warm_start restores it (frozen: deploy, learn nothing). A warm
  // start that does not fit the declared system throws and leaves no evolution behind.
  fs::path fieldExp = fixture.path() / ("trech_js_field_carry_" + stamp + ".js");
  try {
    {
      std::ofstream out(fieldExp);
      out << "globalThis.TRECH_CONFIG={run:{nEvents:1,seed:3},determinism:{mode:\"predictive\"}};\n";
      out << "const cells=(n)=>{const lo=[],hi=[];for(let c=0;c<n;c++){lo.push([0,0,c*20]);hi.push([20,20,(c+1)*20]);}return {min_mm:lo,max_mm:hi};};\n";
      out << "const decl=(name,n,extra)=>Object.assign({name,region:{shape:\"box\",size_mm:[20,20,20*n]},cells:cells(n),\n";
      out << " values:new Array(n).fill(0),properties:{diffusivity_m2_s:1e-5},options:{cell_mm:5,min_elements:8}},extra);\n";
      out << "const ex=(n)=>({rate_per_s:[0.3].concat(new Array(n-1).fill(0)),target:[5].concat(new Array(n-1).fill(0))});\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      out << " let ref=[0,0,0,0], last=null;\n";
      out << " for(let k=0;k<=20;k++){ if(k>0){ref=ref.map((v,c)=>c===0?v+0.3*(5-v)*0.5:v+0.2*(ref[c-1]-v));}\n";
      out << "  last=ctx.evolveField(decl(\"train\",4,{time_s:2*k,exchanges:ex(4),reference:ref,export_state:k===20}));}\n";
      out << " const st=last.state;\n";
      out << " const opts={cell_mm:5,min_elements:8,warm_start:st,frozen:true};\n";
      out << " const dep=ctx.evolveField(decl(\"deploy\",4,{options:opts,time_s:0,exchanges:ex(4),reference:[0,0,0,0],report:\"summary\",export_state:true}));\n";
      out << " let bad=null; try{ctx.evolveField(decl(\"wrong\",3,{options:{cell_mm:5,min_elements:8,warm_start:st,frozen:true},time_s:0,exchanges:ex(3)}));}catch(e){bad=String(e.message);}\n";
      out << " const after=ctx.evolveField(decl(\"wrong\",3,{time_s:0,exchanges:ex(3)}));\n";
      out << " ctx.emit(\"field_carry\",{format:st.format,methods:st.methods,restored:dep.summary.restored,frozen:dep.summary.frozen===true,\n";
      out << "  unchanged:JSON.stringify(dep.state.arbiter.ew_log)===JSON.stringify(st.arbiter.ew_log),bad,afterName:after.name});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(fieldExp.string());
    trech::HookRuntimeContext fCtx{};
    fCtx.determinismMode = "predictive";
    fCtx.seed = 3;
    (void)js.dispatchHook("onEventEnd", fCtx, nullptr, false);
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 1, "Expected one evolveField carry emit.");
    if (!emits.empty()) {
      const auto j = nlohmann::json::parse(emits[0].payloadJson);
      std::cout << "ctx.evolveField across runs: " << j.dump() << "\n";
      failures += expect(j.at("format") == "trech_field_evolution_v1" && j.at("methods").size() >= 2 &&
                             j.at("restored") == "frozen" && j.at("frozen").get<bool>() && j.at("unchanged").get<bool>(),
                         "Expected an exported field state to restore frozen and stay unchanged.");
      failures += expect(j.at("bad").is_string() &&
                             j.at("bad").get<std::string>().find("restored field state") != std::string::npos &&
                             j.at("afterName") == "wrong",
                         "Expected a mismatched field warm start to throw and leave no evolution behind.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.evolveField export/restore error: " << ex.what() << "\n";
    failures += 1;
  }
  fs::remove(fieldExp);

  // ctx.evolve with PER-ELEMENT material kinds: one call, several materials,
  // each advanced by the operator its own context selected. This is the
  // "inference level is not fixed for the run" contract -- a scenario holding
  // two materials in one state array no longer has to pick one operator for
  // both, and a material with no compatible operator is reported and left
  // untouched instead of inheriting another material's law.
  fs::path multiWax =
      fixture.path() / ("trech_js_multi_wax_" + stamp + ".json");
  fs::path multiCarrier =
      fixture.path() / ("trech_js_multi_carrier_" + stamp + ".json");
  fs::path multiExp =
      fixture.path() / ("trech_js_multi_exp_" + stamp + ".js");
  try {
    {
      std::ofstream m(multiWax);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep_mev\"],"
        << "\"output_features\":[\"d_temperature_k_dt\"],"
        << "\"layers\":[{\"weights\":[[1.0]],\"bias\":[0.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      std::ofstream m(multiCarrier);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep_mev\"],"
        << "\"output_features\":[\"d_temperature_k_dt\"],"
        << "\"layers\":[{\"weights\":[[0.1]],\"bias\":[0.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      std::ofstream out(multiExp);
      out << "globalThis.TRECH_CONFIG={\n";
      out << " run:{nEvents:1,seed:11},determinism:{mode:\"predictive\"},\n";
      out << " models:[\n";
      out << "  {name:\"wax_op\",scale:\"meso\",operator_role:\"thermal_state\","
             "element_kind:\"wax_parcel\",required_context_keys:[\"edep_mev\"],"
             "path:\"" << multiWax.generic_string() << "\"},\n";
      out << "  {name:\"carrier_op\",scale:\"meso\",operator_role:\"thermal_state\","
             "element_kind:\"carrier_cell\",required_context_keys:[\"edep_mev\"],"
             "path:\"" << multiCarrier.generic_string() << "\"}\n";
      out << " ]\n};\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      // Three elements of three materials in ONE state array; the third has no
      // operator at all.
      out << " const temperature_k=[300,300,300];\n";
      out << " const r=ctx.evolve({dt:2,\n";
      out << "  fields:[{name:\"temperature_k\",min:0,max:1000}],\n";
      out << "  state:{temperature_k},\n";
      out << "  operator_role:\"thermal_state\",\n";
      out << "  element_kind:[\"wax_parcel\",\"carrier_cell\",\"glass_wall\"]\n";
      out << " });\n";
      out << " ctx.emit(\"multi\",{status:r?r.selection.status:null,\n";
      out << "  groups:r?r.selection.groups.map(g=>g.elementKind+\":\"+g.status+"
             "\":\"+g.elements+\":\"+g.selectedModels.join(\"|\")).join(\",\"):null,\n";
      out << "  stages:r?r.stagesRun:-1, evolved:r?r.elementsEvolved:-1,\n";
      out << "  inferences:r?r.inferenceCount:-1,\n";
      out << "  matched:r?r.trace.map(t=>t.elementKind+\"=\"+t.elementsMatched)"
             ".join(\",\"):null,\n";
      out << "  temperature_k});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(multiExp.string());
    trech::HookRuntimeContext multiCtx{};
    multiCtx.determinismMode = "predictive";
    multiCtx.seed = 11;
    multiCtx.eventId = 0;
    multiCtx.eventEdepMeV = 3.0;  // ambient Geant4 fact both operators consume
    const auto report = js.dispatchHook("onEventEnd", multiCtx, nullptr, false);
    // Two operators, one matched element each: 2 inferences, not 2 stages x 3.
    failures += expect(report.predictCount == 2,
                       "Expected one inference per matched element kind.");
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 1, "Expected one multi-material emit.");
    if (!emits.empty()) {
      const std::string& p = emits[0].payloadJson;
      failures += expect(
          p.find("\"status\":\"partial\"") != std::string::npos,
          "Expected a partial selection when one material has no operator.");
      failures += expect(
          p.find("carrier_cell:selected:1:carrier_op") != std::string::npos &&
              p.find("wax_parcel:selected:1:wax_op") != std::string::npos &&
              p.find("glass_wall:no_compatible:1:") != std::string::npos,
          "Expected one selection group per material with its element count.");
      failures += expect(
          p.find("\"stages\":2") != std::string::npos &&
              p.find("\"evolved\":2") != std::string::npos &&
              p.find("\"inferences\":2") != std::string::npos,
          "Expected both operators to run on their own elements only.");
      failures += expect(
          p.find("carrier_cell=1") != std::string::npos &&
              p.find("wax_parcel=1") != std::string::npos,
          "Expected each stage to report the elements it evaluated.");
      // wax: d_T/dt = 1.0*edep(3) -> +6 over dt 2; carrier: 0.1*3 -> +0.6;
      // the unclaimed glass wall keeps its value exactly.
      failures += expect(
          p.find("\"temperature_k\":[306.0,300.6,300.0]") != std::string::npos ||
              p.find("\"temperature_k\":[306,300.6,300]") != std::string::npos,
          "Expected each material to evolve through its own operator only.");
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS multi-material ctx.evolve runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // Projections across the two diagonal bands separate them, while each
  // feature on its own is densely occupied. Parents remain independent.
  try {
    const auto path = fixture.path() / "domain_discovery.js";
    {
      std::ofstream out(path);
      out << R"JS(
        globalThis.TRECH_CONFIG = {run: {nEvents: 1}};
        globalThis.TRECH_HOOKS = { onEventEnd(ctx) {
          const x = [], y = [], parents = [];
          for (let i = 0; i < 100; ++i) {
            x.push(i, i, i % 5);
            y.push(i - 2, i + 2, 0);
            parents.push("bands", "bands", "grid");
          }
          x.push(NaN); y.push(0); parents.push("bands");
          const detect = () => ctx.detectDomains({
            features: {y, x: new Float64Array(x)}, parent_groups: parents
          });
          const result = detect();
          if (result === null) { ctx.emit("strict", {}); return; }
          x.reverse(); y.reverse(); parents.reverse();
          const reversed = detect();
          reversed.elementGroups.reverse();
          let rejected = 0;
          for (const invalid of [
            {features:{x:[1], y:[]}}, {features:{x:[null]}},
            {features:{x:[1]}, parent_groups:["a", "b"]}, {features:{x:{}}},
            {features:{x:[]}, min_elements:1}, {features:{x:[]}, max_depth:1.5},
            {features:{x:[]}, method:"other"}
          ]) {
            try { ctx.detectDomains(invalid); } catch (_) { ++rejected; }
          }
          const rings = {x: [], y: []};
          for (let i = 0; i < 120; ++i) {
            const angle = i * 2 * Math.PI / 120;
            for (const radius of [1, 2.4]) {
              rings.x.push(radius * Math.cos(angle));
              rings.y.push(radius * Math.sin(angle));
            }
          }
          const projected = ctx.detectDomains({features:rings});
          const density = ctx.detectDomains({features:rings, method:"density"});
          rings.x.reverse(); rings.y.reverse();
          const densityReversed = ctx.detectDomains({features:rings, method:"density"});
          densityReversed.elementGroups.reverse();
          ctx.emit("domains", {result, reversed, rejected, projected, density, densityReversed,
            empty:ctx.detectDomains({features:{x:[]}})});
        }};
      )JS";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(path.string());
    trech::HookRuntimeContext context{};
    context.determinismMode = "predictive";
    const auto report = js.dispatchHook("onEventEnd", context, nullptr, false);
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 1 && report.predictCount == 0,
                       "Domain discovery emits without model predictions.");
    if (emits.size() == 1) {
      const auto payload = nlohmann::json::parse(emits.front().payloadJson);
      const auto& result = payload.at("result");
      const auto& groups = result.at("groups");
      const auto& assignment = result.at("elementGroups");
      failures += expect(result == payload.at("reversed"), "Domain discovery is row-order invariant.");
      failures += expect(groups.size() == 3 && groups.at(0).at("elements") == 100 &&
                             groups.at(1).at("elements") == 100 && groups.at(2).at("parent") == "grid" &&
                             groups.at(2).at("path") == "",
                         "Two oblique bands split and the uniformly spaced grid stays intact.");
      bool recovered = assignment.size() == 301 && assignment.back().is_null() &&
                       assignment.at(0) != assignment.at(1);
      for (std::size_t i = 0; i < 300 && recovered; ++i) {
        recovered = assignment.at(i) == assignment.at(i % 3);
      }
      failures += expect(recovered, "Membership recovers every band and excludes the NaN row.");
      const auto& density = payload.at("density");
      const auto& ringIds = density.at("elementGroups");
      bool ringsRecovered = density.at("groups").size() == 2 && ringIds.size() == 240 &&
                            ringIds.at(0) != ringIds.at(1);
      for (std::size_t i = 0; i < ringIds.size() && ringsRecovered; ++i) {
        ringsRecovered = ringIds.at(i) == ringIds.at(i % 2);
      }
      failures += expect(payload.at("projected").at("groups").size() == 1 &&
                             density == payload.at("densityReversed") && ringsRecovered,
                         "Density separates concentric rings with overlapping projections.");
      failures += expect(payload.at("rejected") == 7 && payload.at("empty").at("groups").empty(),
                         "Empty batches return empty groups and malformed specs fail.");
    }
    context.determinismMode = "strict";
    (void)js.dispatchHook("onEventEnd", context, nullptr, false);
    const auto strict = js.takeEmittedRecords();
    failures += expect(strict.size() == 1 && strict.front().tag == "strict",
                       "Strict mode disables domain discovery.");
  } catch (const std::exception& ex) {
    std::cerr << "JS domain discovery runtime error: " << ex.what() << "\n";
    ++failures;
  }

  // ctx.learnDomains: a learner persists across hook calls of one runtime,
  // grows domains of a piecewise law, round-trips its state into a frozen
  // learner, refuses malformed specs and is disabled in strict mode.
  try {
    const auto path = fixture.path() / "domain_learning.js";
    {
      std::ofstream out(path);
      out << R"JS(
        globalThis.TRECH_CONFIG = {run: {nEvents: 1}};
        let call = 0;
        globalThis.TRECH_HOOKS = { onEventEnd(ctx) {
          const a = [], b = [], y = [];
          for (let i = 0; i < 240; ++i) {
            const u = ((i * 37 + call * 11) % 240) / 240, v = ((i * 91 + call * 7) % 240) / 240;
            a.push(u); b.push(v);
            y.push(u < 0.5 ? 1 + 2 * u - v : -2 + 0.5 * u + 3 * v);
          }
          call += 1;
          const spec = {name: "piecewise", features: {b, a: new Float64Array(a)}, targets: {y},
                        time: call, options: {min_elements: 16, capacity: {basis_degree: 1}},
                        report: call === 12 ? "full" : "summary"};
          const report = ctx.learnDomains(spec);
          if (report === null) { ctx.emit("strict", {}); return; }
          if (call < 12) return;
          const frozen = ctx.learnDomains({name: "frozen", features: {a, b},
                                           options: {warm_start: report.state, frozen: true}});
          let rejected = 0;
          for (const invalid of [
            {features: {a}}, {name: "", features: {a}}, {name: "x", features: {a: [1], b: []}},
            {name: "piecewise", features: {a, c: b}, targets: {y}},
            {name: "x", features: {a}, report: "everything"},
            {name: "bad", features: {a}, options: {warm_start: {schema: "nope"}}},
            {name: "piecewise", features: {b, a}, targets: {y}, options: [1]}
          ]) {
            try { ctx.learnDomains(invalid); } catch (_) { ++rejected; }
          }
          ctx.emit("learning", {report, frozen, rejected});
        }};
      )JS";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(path.string());
    trech::HookRuntimeContext context{};
    context.determinismMode = "predictive";
    for (int c = 0; c < 12; ++c) (void)js.dispatchHook("onEventEnd", context, nullptr, false);
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 1, "Domain learning emits once after twelve calls.");
    if (emits.size() == 1) {
      const auto payload = nlohmann::json::parse(emits.front().payloadJson);
      const auto& report = payload.at("report");
      const auto& frozen = payload.at("frozen");
      failures += expect(report.at("call") == 12 && report.at("features") == nlohmann::json({"a", "b"}),
                         "The learner persists across calls with sorted feature names.");
      failures += expect(report.at("domains").size() >= 2, "A piecewise law grows several domains.");
      const double routed = report.at("metrics").at("routed_rmse").at("y").get<double>();
      const double pooled = report.at("metrics").at("pooled_rmse").at("y").get<double>();
      failures += expect(routed < 0.1 * pooled, "Routed prequential error beats the pooled law.");
      failures += expect(report.contains("state") && report.contains("budget") && report.contains("capacity"),
                         "Full reports carry the state, budget and capacity.");
      failures += expect(frozen.at("frozen") == true && frozen.at("scored") == 0 &&
                             frozen.at("elementDomains").size() == 240,
                         "A frozen warm start routes and predicts without targets.");
      failures += expect(payload.at("rejected") == 7, "Malformed learnDomains specs fail.");
    }
    context.determinismMode = "strict";
    (void)js.dispatchHook("onEventEnd", context, nullptr, false);
    const auto strict = js.takeEmittedRecords();
    failures += expect(strict.size() == 1 && strict.front().tag == "strict",
                       "Strict mode disables domain learning.");
  } catch (const std::exception& ex) {
    std::cerr << "JS domain learning runtime error: " << ex.what() << "\n";
    ++failures;
  }

  // ctx.lift: recursive group lifting crossing the JS boundary. Three trained
  // group_lift fixtures (cell -> block -> system) are declared with
  // operator_role "group_lift"; the call names no levels, so the engine plans
  // the hierarchy itself (ascending scale, each level's carried lattice edge /
  // length) and must reproduce the trainer's NumPy observer value.
  fs::path liftExp = fixture.path() / ("trech_js_lift_" + stamp + ".js");
  try {
    const std::string dir = std::string(TRECH_SOURCE_DIR) + "/tests/fixtures/ml_group_hierarchy/";
    std::ifstream expectedIn(dir + "expected.json");
    const auto expected = nlohmann::json::parse(expectedIn);
    const auto& c0 = expected.at("cases").at(0);
    const double topRef = c0.at("levels").at(2).at("features").at(0).at(0).get<double>();
    {
      std::ofstream out(liftExp);
      out << "globalThis.TRECH_CONFIG={\n";
      out << " run:{nEvents:1,seed:5},determinism:{mode:\"predictive\"},\n";
      out << " models:[\n";
      out << "  {name:\"system_lift\",scale:\"meso\",operator_role:\"group_lift\",path:\""
          << dir << "system.json\"},\n";
      out << "  {name:\"cell_lift\",scale:\"nano\",operator_role:\"group_lift\",path:\""
          << dir << "cell.json\"},\n";
      out << "  {name:\"block_lift\",scale:\"micro\",operator_role:\"group_lift\",path:\""
          << dir << "block.json\"}\n";
      out << " ]\n};\n";
      out << "const CASE=" << c0.dump() << ";\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      out << " const r=ctx.lift({features:CASE.features,positions:CASE.positions,context:CASE.context});\n";
      out << " if(r===null){ctx.emit(\"lift_strict\",{nullResult:true});return;}\n";
      out << " const none=ctx.lift({features:CASE.features,positions:CASE.positions});\n";
      out << " ctx.emit(\"lift\",{planned:r.planned,levels:r.levels.map(l=>l.model+\":\"+l.grouping+\":\"+l.groups),\n";
      out << "  top:r.top?r.top.energy:null,inferences:r.inferenceCount,\n";
      out << "  latent:r.levels.map(l=>l.latentOutputs),parentLen:r.levels[0].parent.length,\n";
      out << "  missing:none.levels[2].skipReason,missingTop:none.top});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(liftExp.string());
    trech::HookRuntimeContext liftCtx{};
    liftCtx.determinismMode = "predictive";
    liftCtx.seed = 5;
    const auto report = js.dispatchHook("onEventEnd", liftCtx, nullptr, false);
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 1, "Expected one ctx.lift emit.");
    if (!emits.empty()) {
      const auto p = nlohmann::json::parse(emits[0].payloadJson);
      const auto levels = p.at("levels").get<std::vector<std::string>>();
      failures += expect(p.at("planned").get<bool>() && levels.size() == 3 &&
                             levels[0].rfind("cell_lift:cell:", 0) == 0 &&
                             levels[1].rfind("block_lift:cell:8", 0) == 0 &&
                             levels[2] == "system_lift:all:1",
                         "Expected the engine to plan cell -> block -> system by scale.");
      failures += expect(p.at("top").is_number() &&
                             std::abs(p.at("top").get<double>() - topRef) <=
                                 1e-9 * std::max(1.0, std::abs(topRef)),
                         "Expected ctx.lift's observer to match the trainer's reference.");
      failures += expect(p.at("latent") == nlohmann::json::array({true, true, false}),
                         "Expected latent levels to be flagged.");
      failures += expect(p.at("parentLen").get<std::size_t>() ==
                             c0.at("features").at("q").size(),
                         "Expected one parent index per base element.");
      failures += expect(p.at("missing") == "missing_context" && p.at("missingTop").is_null(),
                         "Expected a missing context input to leave the observer null.");
      const long long inferences = p.at("inferences").get<long long>();
      // Both calls count their group evaluations (the second stops below the top).
      failures += expect(report.predictCount == static_cast<std::size_t>(2 * inferences - 1),
                         "Expected every group evaluation to count as an inference.");
    }
    trech::HookRuntimeContext strictCtx{};
    strictCtx.determinismMode = "strict";
    const auto strictReport = js.dispatchHook("onEventEnd", strictCtx, nullptr, false);
    const auto strictEmits = js.takeEmittedRecords();
    failures += expect(strictEmits.size() == 1 && strictEmits[0].tag == "lift_strict" &&
                           strictReport.predictCount == 0,
                       "Expected strict mode to disable ctx.lift (null, no inference).");
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.lift runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.interact: learned PAIR/NEIGHBOUR interaction crossing the JS boundary.
  // The scenario declares positions, per-element fields that receive pair
  // contributions (with their symmetry), a cutoff and a persistent bond with
  // its own state -- the shape of the hand-written force/bond/neighbour loops
  // scenarios carry today. Verifies the deterministic neighbour search, the
  // equal-and-opposite vs shared invariants, in-place mutation of the caller's
  // element AND pair arrays, pairs x stages accounting, and strict-mode gating.
  fs::path interactModel =
      fixture.path() / ("trech_js_interact_model_" + stamp + ".json");
  fs::path interactExp =
      fixture.path() / ("trech_js_interact_exp_" + stamp + ".js");
  try {
    {
      // One micro stage over the pair geometry and the two members' own heat:
      //   d_heat_dt = 0.5*(b_heat - a_heat)   (antisymmetric exchange)
      //   add_contacts = 1                    (shared neighbourhood count)
      //   d_stretch_dt = r                    (the pair's own state)
      std::ofstream model(interactModel);
      model << "{\"model\":\"generic_surrogate_v1\","
            << "\"input_features\":[\"a_heat\",\"b_heat\",\"r\"],"
            << "\"output_features\":[\"d_heat_dt\",\"add_contacts\","
               "\"d_stretch_dt\"],"
            << "\"trained_scale_bands\":[\"atomic\"],"
            << "\"input_domain\":{\"standardized_radius\":[200,200,10],"
            << "\"input_min\":[0,0,0],\"input_max\":[200,200,10],"
            << "\"occupancy\":{\"bins\":2,\"counts\":[[0,2],[2,2],[2,2]]},"
            << "\"joint\":{\"centers\":[[10,4,1]],\"radius\":0.1}},"
            << "\"layers\":[{\"weights\":[[-0.5,0.5,0.0],[0.0,0.0,0.0],"
               "[0.0,0.0,1.0]],\"bias\":[0.0,1.0,0.0],\"activation\":\"none\"}]}";
    }
    {
      std::ofstream out(interactExp);
      out << "globalThis.TRECH_CONFIG={\n";
      out << " run:{nEvents:1,seed:5},determinism:{mode:\"predictive\"},\n";
      out << " models:[{name:\"pair_op\",scale:\"micro\","
             "operator_role:\"pair_interaction\",element_kind:\"parcel\","
             "required_context_keys:[\"edep_mev\"],path:\""
          << interactModel.generic_string() << "\"}]\n";
      out << "};\n";
      out << "globalThis.TRECH_HOOKS={onEventEnd(ctx){\n";
      // Elements 0 and 1 are one unit apart (inside the cutoff); element 2 sits
      // far away and is reachable only through the declared bond to element 0.
      out << " const heat=[10,4,100],contacts=[0,0,0],stretch=[1];\n";
      out << " const r=ctx.interact({dt:0.1,cutoff:2,\n";
      out << "  fields:[{name:\"heat\",symmetry:\"antisymmetric\"},\n";
      out << "          {name:\"contacts\",symmetry:\"symmetric\"}],\n";
      out << "  state:{heat,contacts},\n";
      out << "  positions:{x:[0,1,5],y:[0,0,0],z:[0,0,0]},\n";
      out << "  links:{a:[0],b:[2]},\n";
      out << "  pair_fields:[{name:\"stretch\",min:0,max:4}],\n";
      out << "  pair_state:{stretch},\n";
      out << "  operator_role:\"pair_interaction\",element_kind:\"parcel\"\n";
      out << " });\n";
      out << " ctx.emit(\"interact\",{ran:r?r.ran:null,\n";
      out << "  pairs:r?r.pairCount:-1,links:r?r.linkPairs:-1,\n";
      out << "  neighbors:r?r.neighborPairs:-1,\n";
      out << "  inferences:r?r.inferenceCount:-1,\n";
      out << "  selection:r?r.selection.status:null,\n";
      out << "  rated:r?r.trace[0].ratedElementFields.join(\",\"):null,\n";
      out << "  incremented:r?r.trace[0].incrementedElementFields.join(\",\"):null,\n";
      out << "  pairFields:r?r.trace[0].ratedPairFields.join(\",\"):null,\n";
      out << "  heat,contacts,stretch});\n";
      out << "}};\n";
    }
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(interactExp.string());
    trech::HookRuntimeContext pairCtx{};
    pairCtx.determinismMode = "predictive";
    pairCtx.seed = 5;
    pairCtx.eventId = 0;
    pairCtx.eventEdepMeV = 1.0;  // ambient fact the operator's role requires
    const auto report = js.dispatchHook("onEventEnd", pairCtx, nullptr, false);
    // Honest accounting: 2 pairs x 1 stage = 2 inferences, not 1 per call.
    failures += expect(report.predictCount == 2,
                       "Expected ctx.interact to count one inference per pair.");
    failures += expect(report.starvedCount == 2 && report.scaleMismatchCount == 2 &&
                           report.outOfDomainCount == 0,
                       "Expected pair density unions/off-band counts per evaluated pair, separate from OOD.");
    const auto emits = js.takeEmittedRecords();
    failures += expect(emits.size() == 1, "Expected one ctx.interact emit.");
    if (!emits.empty()) {
      const std::string& payload = emits[0].payloadJson;
      failures += expect(
          payload.find("\"ran\":true") != std::string::npos &&
              payload.find("\"pairs\":2") != std::string::npos &&
              payload.find("\"links\":1") != std::string::npos &&
              payload.find("\"neighbors\":1") != std::string::npos,
          "Expected one cutoff pair plus the declared out-of-range bond.");
      failures += expect(
          payload.find("\"inferences\":2") != std::string::npos &&
              payload.find("\"selection\":\"selected\"") != std::string::npos,
          "Expected contextual pair-operator selection and pairs x stages count.");
      failures += expect(
          payload.find("\"rated\":\"heat\"") != std::string::npos &&
              payload.find("\"incremented\":\"contacts\"") != std::string::npos &&
              payload.find("\"pairFields\":\"stretch\"") != std::string::npos,
          "Expected the trace to name what each output actually did.");
      // heat: pair (0,1) exchanges 0.5*(4-10)*0.1 = -0.3 ; pair (0,2) exchanges
      // 0.5*(100-10)*0.1 = +4.5 -> e0 10-0.3+4.5 = 14.2, e1 4.3, e2 95.5.
      failures += expect(
          payload.find("\"heat\":[14.2,4.3,95.5]") != std::string::npos,
          "Expected equal-and-opposite exchange over both pairs.");
      // contacts: shared +1 per pair, no dt scaling.
      failures += expect(
          (payload.find("\"contacts\":[2,1,1]") != std::string::npos ||
           payload.find("\"contacts\":[2.0,1.0,1.0]") != std::string::npos),
          "Expected the symmetric neighbourhood sum on both members.");
      // stretch: d_stretch_dt = r = 5 over dt 0.1 -> 1 + 0.5 = 1.5
      failures += expect(
          (payload.find("\"stretch\":[1.5]") != std::string::npos),
          "Expected the persistent bond's own state integrated in place.");
    }

    trech::HookRuntimeContext strictPair = pairCtx;
    strictPair.determinismMode = "strict";
    const auto strictReport =
        js.dispatchHook("onEventEnd", strictPair, nullptr, false);
    failures += expect(strictReport.predictCount == 0,
                       "Expected strict mode to disable ctx.interact.");
    failures += expect(strictReport.starvedCount == 0 && strictReport.scaleMismatchCount == 0,
                       "Expected strict pair dispatch to reset density/band counts.");
    const auto strictEmits = js.takeEmittedRecords();
    failures += expect(
        !strictEmits.empty() &&
            strictEmits[0].payloadJson.find("\"ran\":null") !=
                std::string::npos &&
            (strictEmits[0].payloadJson.find("\"heat\":[10,4,100]") !=
                 std::string::npos ||
             strictEmits[0].payloadJson.find("\"heat\":[10.0,4.0,100.0]") !=
                 std::string::npos),
        "Expected strict ctx.interact to return null and leave state untouched.");
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.interact runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  const auto normalFile = fixture.path() / "normal_rng.js";
  {
    std::ofstream out(normalFile);
    out << R"JS(
globalThis.TRECH_CONFIG = {run: {seed: 91827, nEvents: 1}};
globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    const phase = ctx.state.phase || 0;
    ctx.state.phase = phase + 1;
    if (phase === 2) {
      const a = ctx.rng.uniform(), b = ctx.rng.uniform();
      ctx.emit('raw', {a, b, next: ctx.rng.uniform()});
      return;
    }
    if (phase === 3) {
      let rejected = 0;
      for (const args of [[NaN], [Infinity], [-Infinity], [0, NaN], [0, Infinity],
                           [0, -1], ['1'], [null], [0, '1'], [0, null], [{}]]) {
        try { ctx.rng.normal(...args); }
        catch (error) {
          if (!(error instanceof TypeError || error instanceof RangeError)) throw error;
          ++rejected;
        }
      }
      ctx.emit('validation', {rejected, constant: ctx.rng.normal(7, 0),
                              first: ctx.rng.normal(undefined, undefined)});
      return;
    }
    if (phase === 4) {
      ctx.emit('scaled', {first: ctx.rng.normal(4, 2)});
      return;
    }
    if (phase === 5) {
      let overflow = false;
      try {
        ctx.rng.normal(ctx.state.first < 0 ? -Number.MAX_VALUE : Number.MAX_VALUE, Number.MAX_VALUE);
      } catch (error) {
        if (!(error instanceof RangeError)) throw error;
        overflow = true;
      }
      ctx.emit('overflow', {overflow, next: ctx.rng.uniform()});
      return;
    }
    const first = ctx.rng.normal(), next = ctx.rng.uniform();
    ctx.state.first = first;
    const integer = ctx.rng.int(1, 9), shifted = ctx.rng.normal(4, 2);
    let sum = 0, sum2 = 0, tails = 0;
    const count = 16384;
    for (let i = 0; i < count; ++i) {
      const sample = ctx.rng.normal();
      if (!Number.isFinite(sample)) throw new Error('Nonfinite normal draw');
      sum += sample;
      sum2 += sample * sample;
      if (Math.abs(sample) > 2) ++tails;
    }
    ctx.emit('samples', {first, next, integer, shifted,
                         mean: sum / count, secondMoment: sum2 / count, tails});
  }
};
)JS";
  }
  try {
    trech::JsRuntime js;
    js.evalExperimentAndGetConfigJson(normalFile.string());
    trech::HookRuntimeContext context;
    context.seed = 91827;
    context.nEvents = 1;
    context.eventId = 0;
    context.determinismMode = "strict";
    std::string payload;
    const auto dispatch = [&]() {
      const auto report = js.dispatchHook("onEventEnd", context, nullptr, false);
      const auto emits = js.takeEmittedRecords();
      if (!report.invoked || emits.size() != 1 || report.predictCount != 0) {
        throw std::runtime_error("Expected one RNG emit and no inference");
      }
      payload = emits.front().payloadJson;
      return nlohmann::json::parse(payload);
    };
    const auto first = dispatch();
    const auto firstBytes = payload;
    dispatch();
    failures += expect(firstBytes == payload, "Expected byte-identical mixed RNG replay per hook identity.");
    const auto raw = dispatch();
    // Host math is deterministic (trech_dmath), so the sample is reproduced bit for bit.
    const double reference =
        std::sqrt(-2.0 * trech_dmath_log(1.0 - raw.at("a").get<double>())) *
        trech_dmath_cos(6.2831853071795864769 * raw.at("b").get<double>());
    failures += expect(first.at("first").get<double>() == reference &&
                           first.at("next") == raw.at("next"),
                       "Expected normal to consume exactly two existing uniform draws, "
                       "evaluated bit for bit with the deterministic host math.");
    const auto validation = dispatch();
    failures += expect(validation.at("rejected") == 11 && validation.at("constant") == 7 &&
                           validation.at("first") == first.at("first"),
                       "Invalid parameters and zero sigma must consume no RNG draws.");
    failures += expect(dispatch().at("first").get<double>() ==
                           4.0 + 2.0 * first.at("first").get<double>(),
                       "Expected exact normal mean/sigma transformation (no fused multiply-add).");
    const auto overflow = dispatch();
    failures += expect(overflow.at("overflow") == true && overflow.at("next") == raw.at("next"),
                       "Expected overflow to throw after consuming exactly two draws.");
    failures += expect(std::abs(first.at("mean").get<double>()) < 0.04 &&
                           std::abs(first.at("secondMoment").get<double>() - 1.0) < 0.06 &&
                           first.at("tails").get<int>() > 550 && first.at("tails").get<int>() < 950,
                       "Expected standard-normal moments and two-sided tails.");
    context.seed += 1;
    failures += expect(dispatch().at("first") != first.at("first"),
                       "Expected a different run seed to change normal draws.");
    context.seed -= 1;
    context.eventId = 1;
    failures += expect(dispatch().at("first") != first.at("first"),
                       "Expected a different event identity to change normal draws.");
    context.eventId = 0;
    trech::JsRuntime fresh;
    fresh.evalExperimentAndGetConfigJson(normalFile.string());
    fresh.dispatchHook("onEventEnd", context, nullptr, false);
    const auto replay = fresh.takeEmittedRecords();
    failures += expect(replay.size() == 1 && replay.front().payloadJson == firstBytes,
                       "Expected normal replay in a fresh runtime.");
  } catch (const std::exception& ex) {
    std::cerr << "JS normal RNG error: " << ex.what() << "\n";
    failures += 1;
  }

  fs::remove(flowFile, ec);
  fs::remove(flowDslFile, ec);
  fs::remove(flowRequireFile, ec);
  fs::remove(valueFile, ec);
  fs::remove(hookRuntimeFile, ec);
  fs::remove(predictModel, ec);
  fs::remove(predictExp, ec);
  fs::remove(cascadeNano, ec);
  fs::remove(cascadeMeso, ec);
  fs::remove(cascadeExp, ec);
  fs::remove(ambientNano, ec);
  fs::remove(ambientExp, ec);
  fs::remove(evolveNano, ec);
  fs::remove(evolveMacro, ec);
  fs::remove(evolveExp, ec);
  fs::remove(reactModel, ec);
  fs::remove(reactExp, ec);
  fs::remove(interactModel, ec);
  fs::remove(interactExp, ec);
  fs::remove(multiWax, ec);
  fs::remove(multiCarrier, ec);
  fs::remove(multiExp, ec);
  fs::remove(pubchemFile, ec);
  fs::remove(pubchemDir / "water.json", ec);
  fs::remove(pubchemDir, ec);
  unsetenv("TRECH_PUBCHEM_CACHE_DIR");
  return failures == 0 ? 0 : 1;
}
