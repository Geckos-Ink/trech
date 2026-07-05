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
      out << "      stages: c ? c.__cascade.stagesRun : -1\n";
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

    // Strict mode disables the cascade: returns null.
    trech::HookRuntimeContext strictC = cCtx;
    strictC.determinismMode = "strict";
    const auto strictCReport = js.dispatchHook("onEventEnd", strictC, nullptr, false);
    failures += expect(strictCReport.predictCount == 0,
                       "Expected strict mode to disable ctx.cascade.");
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

  fs::remove(flowFile, ec);
  fs::remove(flowDslFile, ec);
  fs::remove(flowRequireFile, ec);
  fs::remove(hookRuntimeFile, ec);
  fs::remove(predictModel, ec);
  fs::remove(predictExp, ec);
  fs::remove(cascadeNano, ec);
  fs::remove(cascadeMeso, ec);
  fs::remove(cascadeExp, ec);
  fs::remove(pubchemFile, ec);
  fs::remove(pubchemDir / "water.json", ec);
  fs::remove(pubchemDir, ec);
  unsetenv("TRECH_PUBCHEM_CACHE_DIR");
  return failures == 0 ? 0 : 1;
}
