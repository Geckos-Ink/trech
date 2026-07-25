#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <cstdlib>
#include <iostream>
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

  fs::path valueFile =
      fs::temp_directory_path() / ("trech_js_runtime_value_" + stamp + ".js");
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
      fs::temp_directory_path() / ("trech_js_runtime_hook_dispatch_" + stamp + ".js");
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
    out << "        run: { nEvents: 5 },\n";
    out << "        beam: { energyMeV: 2.0 + delta },\n";
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
      fs::temp_directory_path() / ("trech_js_runtime_pubchem_" + stamp);
  fs::create_directories(pubchemDir, ec);
  {
    std::ofstream out(pubchemDir / "water.json");
    out << R"({"name":"water","cid":962,"molecular_formula":"H2O","molecular_weight":18.015,"smiles":"O"})";
  }
  setenv("TRECH_PUBCHEM_CACHE_DIR", pubchemDir.string().c_str(), 1);

  fs::path pubchemFile =
      fs::temp_directory_path() / ("trech_js_runtime_pubchem_exp_" + stamp + ".js");
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
    failures += expect(cfg.system.ensemble == "patched",
                       "Expected onInit patch to override system ensemble.");
    failures += expect(cfg.beam.energyMeV >= 3.0 && cfg.beam.energyMeV <= 5.0,
                       "Expected deterministic rng patch energy in expected range.");

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

  // ctx.predict: a scenario declares a generic model and a hook calls it.
  // Verifies model loading from models[], named IO, predictive-mode gating,
  // predict counting, and graceful null for undeclared models / strict mode.
  fs::path predictModel =
      fs::temp_directory_path() / ("trech_js_predict_model_" + stamp + ".json");
  fs::path predictExp =
      fs::temp_directory_path() / ("trech_js_predict_exp_" + stamp + ".js");
  try {
    {
      // General linear model: rate = 1.0 + 2*edep + 0.5*activation (no scaling).
      std::ofstream m(predictModel);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep\",\"activation\"],"
        << "\"output_features\":[\"rate\"],"
        << "\"layers\":[{\"weights\":[[2.0,0.5]],\"bias\":[1.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      std::ofstream out(predictExp);
      out << "const cfg = {\n";
      out << "  run: { nEvents: 2, seed: 7 },\n";
      out << "  determinism: { mode: \"predictive\" },\n";
      out << "  models: [{ name: \"rate\", path: \""
          << predictModel.generic_string() << "\" }]\n";
      out << "};\n";
      out << "globalThis.TRECH_CONFIG = cfg;\n";
      out << "globalThis.TRECH_HOOKS = {\n";
      out << "  onEventEnd(ctx) {\n";
      out << "    const p = ctx.predict(\"rate\", { edep: ctx.event.edepMeV,"
          << " activation: 2.0 });\n";
      out << "    const miss = ctx.predict(\"nope\", {});\n";
      out << "    ctx.emit(\"pred\", { rate: p ? p.rate : null,"
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
    failures += expect(predEmits[0].payloadJson.find("\"rate\":8") != std::string::npos,
                       "Expected ctx.predict to return rate=8.");
    failures += expect(predEmits[0].payloadJson.find("\"missing\":null") != std::string::npos,
                       "Expected undeclared model to yield null.");

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
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.predict runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.cascade: two scale-tagged models chained in ONE pass. The nano stage
  // maps a Geant4-derived fact (edep) to a nano_signal; the meso stage consumes
  // that nano_signal -- without the scenario hand-wiring the chain. Verifies
  // multi-scale chaining, flat context return, stage counting, and strict-mode
  // gating through the JS boundary.
  fs::path cascadeNano =
      fs::temp_directory_path() / ("trech_js_casc_nano_" + stamp + ".json");
  fs::path cascadeMeso =
      fs::temp_directory_path() / ("trech_js_casc_meso_" + stamp + ".json");
  fs::path cascadeExp =
      fs::temp_directory_path() / ("trech_js_casc_exp_" + stamp + ".js");
  try {
    {
      // nano_signal = 2*edep
      std::ofstream m(cascadeNano);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep\"],"
        << "\"output_features\":[\"nano_signal\"],"
        << "\"layers\":[{\"weights\":[[2.0]],\"bias\":[0.0],"
        << "\"activation\":\"none\"}]}";
    }
    {
      // observed = 3*nano_signal + 1
      std::ofstream m(cascadeMeso);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"nano_signal\"],"
        << "\"output_features\":[\"observed\"],"
        << "\"layers\":[{\"weights\":[[3.0]],\"bias\":[1.0],"
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
      out << "    ctx.emit(\"casc\", {\n";
      out << "      observed: c ? c.observed : null,\n";
      out << "      nano_signal: c ? c.nano_signal : null,\n";
      out << "      stages: c ? c.__cascade.stagesRun : -1,\n";
      // Coverage surface (workstream 3): nano_signal=6 lands outside meso's
      // heuristic 3-sigma hull, so the meso stage is flagged extrapolating.
      out << "      extrapolating: c ? c.__cascade.stagesExtrapolating : -1,\n";
      out << "      nanoInDomain: c ? c.__cascade.trace[0].inDomain : null,\n";
      out << "      mesoInDomain: c ? c.__cascade.trace[1].inDomain : null,\n";
      out << "      mesoMeasured: c ? c.__cascade.trace[1].domainMeasured : null,\n";
      out << "      mesoOOD: c ? c.__cascade.trace[1].outOfDomainInputs.join(\",\") : null,\n";
      // Provenance/quality fields (workstream 3 b + c): the demo models carry no
      // trained bands or held-out metrics, so off-band is false and R2 is null.
      out << "      scaleMismatched: c ? c.__cascade.stagesScaleMismatched : -1,\n";
      out << "      mesoScaleMismatch: c ? c.__cascade.trace[1].scaleMismatch : null,\n";
      out << "      mesoHoldout: c ? c.__cascade.trace[1].holdoutR2 : \"absent\"\n";
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
    // Two stages ran -> two counted inferences.
    failures += expect(cReport.predictCount == 2,
                       "Expected a 2-stage cascade to count as 2 inferences.");
    // Run-level out-of-domain accountability (workstream 3a): the meso stage
    // extrapolated, so exactly one of the two inferences is out-of-domain.
    failures += expect(cReport.outOfDomainCount == 1,
                       "Expected report.outOfDomainCount == 1 (meso stage).");
    const auto cEmits = js.takeEmittedRecords();
    failures += expect(cEmits.size() == 1, "Expected one cascade emit.");
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
  } catch (const std::exception& ex) {
    std::cerr << "JS ctx.cascade runtime error: " << ex.what() << "\n";
    failures += 1;
  }

  // ctx.cascade() with NO argument auto-seeds from the ambient Geant4 base
  // (workstream 1): the nano stage declares the ambient key `edep_mev` and must
  // consume the per-event tally with the scenario copying nothing by hand. Also
  // verifies material probes reach the seed and an explicit arg still overrides.
  fs::path ambientNano =
      fs::temp_directory_path() / ("trech_js_amb_nano_" + stamp + ".json");
  fs::path ambientExp =
      fs::temp_directory_path() / ("trech_js_amb_exp_" + stamp + ".js");
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
      out << "    ctx.emit(\"amb\", {\n";
      out << "      nano_signal: c ? c.nano_signal : null,\n";
      out << "      edep_seed: c ? c.edep_mev : null,\n";
      out << "      optics_n: c ? c['optics.water.mean_refractive_index'] : null,\n";
      out << "      optics_direct: ctx.optics ? ctx.optics.water.mean_refractive_index : null,\n";
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
    failures += expect(aReport.predictCount == 1,
                       "Expected the ambient-seeded nano stage to run once.");
    const auto aEmits = js.takeEmittedRecords();
    failures += expect(aEmits.size() == 1, "Expected one ambient-seed emit.");
    if (!aEmits.empty()) {
      const std::string& p = aEmits[0].payloadJson;
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
      fs::temp_directory_path() / ("trech_js_evo_nano_" + stamp + ".json");
  fs::path evolveMacro =
      fs::temp_directory_path() / ("trech_js_evo_macro_" + stamp + ".json");
  fs::path evolveExp =
      fs::temp_directory_path() / ("trech_js_evo_exp_" + stamp + ".js");
  try {
    {
      // nano stage: drive = 0.5*edep_mev (an AMBIENT Geant4 fact) + 1.0*catalyst
      // (a per-element aux fact). It emits an intermediate, not a field update.
      std::ofstream m(evolveNano);
      m << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"edep_mev\",\"catalyst\"],"
        << "\"output_features\":[\"drive\"],"
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
      out << "    { name: \"macro_op\", scale: \"macro\", path: \""
          << evolveMacro.generic_string() << "\" },\n";
      out << "    { name: \"nano_op\", scale: \"nano\", path: \""
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
      out << "      context: { rate_coefficient: 0.25 }\n";
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
    failures += expect(js.loadedModelNames().size() == 2,
                       "Expected both evolve operator models to load.");

    trech::HookRuntimeContext eCtx{};
    eCtx.determinismMode = "predictive";
    eCtx.eventId = 0;
    eCtx.eventEdepMeV = 2.0;  // ambient edep_mev -> drive = 1.0 + catalyst
    const auto eReport = js.dispatchHook("onEventEnd", eCtx, nullptr, false);
    failures += expect(eReport.invoked, "Expected evolve onEventEnd invocation.");
    // Honest accounting: 2 stages over 3 elements = 6 model evaluations, NOT 2.
    failures += expect(eReport.predictCount == 6,
                       "Expected 2 stages x 3 elements = 6 counted inferences.");
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
  fs::remove(pubchemFile, ec);
  fs::remove(pubchemDir / "water.json", ec);
  fs::remove(pubchemDir, ec);
  unsetenv("TRECH_PUBCHEM_CACHE_DIR");
  return failures == 0 ? 0 : 1;
}
