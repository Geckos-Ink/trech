#include "trech/js/JsRuntime.hpp"
#include "trech/core/Config.hpp"
#include <nlohmann/json.hpp>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
using json = nlohmann::json;
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
const auto experiment = std::string(TRECH_SOURCE_DIR) + "/examples/experiments/chemistry_mode.js";
json example() {
  json atom = {{"atoms", {{{"element", "H"}, {"massNumber", 2}, {"position", {1,0,0}}}}}, {"bonds", json::array()}, {"charge", 0}};
  json entities = json::array({{{"id", "a"}, {"structure", atom}, {"rotation_deg", {0,0,90}}},
                               {{"id", "b"}, {"structure", atom}, {"position", {3,0,0}}}});
  json field = {{"id", "shared"}, {"particle", "electron"}, {"owner_ids", {"a", "b"}},
    {"geometry", {{"charge", 0}, {"atoms", {{{"element", "H"}, {"massNumber", 2}, {"position", {0,1,0}}},
                                          {{"element", "H"}, {"massNumber", 2}, {"position", {4,0,0}}}}}}},
    {"length_unit", "angstrom"}, {"density_unit", "electrons/angstrom^3"},
    {"source", {{"kind", "inferred"}, {"method", "test fixture only"}}},
    {"grid", {{"shape", {2,2,2}}, {"origin", {-1,-1,-1}}, {"spacing", 1}, {"values", {0,0,0,0,1,1,1,1}}}}, {"isovalue", .5}};
  json scene = {{"schema", "trech_chemistry_scene_v1"}, {"molecules", entities}, {"time_kind", "physical"},
    {"links", {{{"a", {{"molecule", "a"}, {"atom", 0}}}, {"b", {{"molecule", "b"}, {"atom", 0}}}, {"order", 1}}}},
    {"frames", {{{"time_s", .125}, {"fields", {field}}}, {{"time_s", .25}, {"fields", {field}}}}}};
  return scene;
}
int main() {
  const auto file = std::filesystem::temp_directory_path() / "trech_chemistry_scene_test.json";
  try {
    auto scene = example();
    { std::ofstream f(file); f << scene; }
    trech::JsRuntime reader;
    reader.setScriptParameterOverrides({"scene_file=" + json(file.string()).dump()});
    const auto config = json::parse(reader.evalExperimentAndGetConfigJson(experiment));
    const auto input = config["hooks"]["inputs"];
    trech::JsRuntime restored;
    restored.setScriptParameterOverrides({"scene_json=" + json(input["scene"].dump()).dump()});
    const auto restoredConfig = json::parse(restored.evalExperimentAndGetConfigJson(experiment));
    require(restoredConfig == config, "canonical scenes must re-inspect identically after restore/export");
    require(std::abs(input["structure"]["atoms"][0]["position"][0].get<double>()) < 1e-12 &&
            std::abs(input["structure"]["atoms"][0]["position"][1].get<double>() - 1) < 1e-12, "rigid placement/rotation incorrect");
    require(input["structure"]["atoms"][1]["position"] == json({4,0,0}), "second molecule not placed");
    require(input["structure"]["bonds"] == json::array({{0,1,1}}), "cross-molecule link not retained");
    require(input["scene"]["frames"][1]["physical_time_s"] == .25, "physical density clock lost");
    for (int invalid = 0; invalid < 10; ++invalid) {
      auto bad = scene;
      if (invalid == 0) bad["molecules"][1]["id"] = "a";
      if (invalid == 1) bad["links"][0]["a"]["atom"] = 10;
      if (invalid == 2) bad["frames"][0]["fields"][0]["grid"]["values"][0] = -1;
      if (invalid == 3) bad["frames"][0]["fields"][0]["owner_ids"] = {"unknown"};
      if (invalid == 4) bad["frames"][0]["fields"][0]["grid"]["shape"] = {3,3,3};
      if (invalid == 5) bad["frames"][1]["fields"][0]["length_unit"] = "fm";
      if (invalid == 6) bad["frames"][1]["time_s"] = .125;
      if (invalid == 7) bad["frames"][0]["fields"][0].erase("source");
      if (invalid == 8) bad["time_kind"] = "snapshot";
      if (invalid == 9) bad["frames"][0]["fields"][0]["geometry"]["atoms"][0]["position"][0] = 1;
      trech::JsRuntime js; js.setScriptParameterOverrides({"scene_json=" + json(bad.dump()).dump()});
      bool rejected = false;
      try { js.evalExperimentAndGetConfigJson(experiment); } catch (...) { rejected = true; }
      require(rejected, "invalid scene/field/clock accepted");
    }
    for (int variant = 0; variant < 3; ++variant) {
      const bool strict = variant != 0, comparison = variant == 2;
      auto data = scene;
      if (comparison) for (auto& frame : data["frames"]) frame["fields"][0]["source"]["kind"] = "quantum_reference";
      trech::JsRuntime js;
      js.setScriptParameterOverrides({"scene_json=" + json(data.dump()).dump(), std::string("mode=\"") + (strict ? "strict" : "predictive") + "\""});
      js.evalExperimentAndGetConfigJson(experiment);
      trech::HookRuntimeContext ctx; ctx.eventId = 0; ctx.determinismMode = strict ? "strict" : "predictive";
      ctx.materialsJson = R"([{"name":"molecular_probe","available":true,"elements":[{"symbol":"H","z":1,"atomic_mass_amu":2.014,"natural_isotopic_composition":false,"isotopes":[{"a":2,"z":1}]}]}])";
      auto report = js.dispatchHook("onEventEnd", ctx, nullptr, false);
      auto emits = js.takeEmittedRecords();
      require(report.predictCount == 0 && report.emitDroppedCount == 0 && emits.size() == 3, "unexpected inference or lost density frame");
      auto frame = json::parse(emits.back().payloadJson);
      require(frame["physical_time_s"] == .125, "clock changed at JS boundary");
      require(frame["fields"].size() == (strict && !comparison ? 0u : 1u), "strict must suppress imported inferred fields but retain labelled independent comparisons");
      require(frame["omitted_fields"].size() == (strict && !comparison ? 1u : 0u), "strict omission must be disclosed");
    }
    // Spectrum/field disagreement must fail before any model is run.
    for (int invalid = -1; invalid < 4; ++invalid) {
      auto data = scene;
      for (auto& frame : data["frames"]) {
        auto& field = frame["fields"][0];
        field["density_unit"] = "probability/angstrom^3";
        field["orbital"] = {{"index", 1}, {"energy_hartree", -0.5}, {"occupation", 2}};
        frame["electronic_structure"] = {{"source", field["source"]}, {"geometry", field["geometry"]}, {"electron_count", 2},
          {"total_energy_hartree", -1.0}, {"orbitals", {{{"index", 1}, {"energy_hartree", -0.5}, {"occupation", 2}, {"field_id", "shared"}}}}};
      }
      auto& electronic = data["frames"][0]["electronic_structure"];
      if (invalid == 0) electronic["electron_count"] = 3;
      if (invalid == 1) electronic["orbitals"][0]["field_id"] = "absent";
      if (invalid == 2) electronic["orbitals"][0]["occupation"] = -1;
      if (invalid == 3) electronic["orbitals"][0]["energy_hartree"] = 1;
      trech::JsRuntime js;
      js.setScriptParameterOverrides({"scene_json=" + json(data.dump()).dump()});
      bool rejected = false;
      try { js.evalExperimentAndGetConfigJson(experiment); } catch (...) { rejected = true; }
      require(rejected == (invalid >= 0), "invalid orbital contract or valid spectrum rejected");
      if (invalid == -1) {
        trech::HookRuntimeContext ctx;
        ctx.eventId = 0; ctx.determinismMode = "strict";
        ctx.materialsJson = R"([{"name":"molecular_probe","available":true,"elements":[{"symbol":"H","z":1,"atomic_mass_amu":2.014,"natural_isotopic_composition":false,"isotopes":[{"a":2,"z":1}]}]}])";
        // Source is inferred: strict must suppress both fields and the spectrum.
        trech::JsRuntime strict;
        strict.setScriptParameterOverrides({"scene_json=" + json(data.dump()).dump(), "mode=\"strict\""});
        strict.evalExperimentAndGetConfigJson(experiment);
        const auto report = strict.dispatchHook("onEventEnd", ctx, nullptr, false);
        const auto emitted = strict.takeEmittedRecords();
        const auto frame = json::parse(emitted.back().payloadJson);
        require(frame["electronic_structure"].is_null() && frame["fields"].empty() && report.predictCount == 0,
          "strict leaked an inferred orbital spectrum or field");
      }

    }
    { std::ofstream f(file); f << "globalThis.notJson=true;"; }
    trech::JsRuntime noEval; noEval.setScriptParameterOverrides({"scene_file=" + json(file.string()).dump()});
    bool rejected = false;
    try { noEval.evalExperimentAndGetConfigJson(experiment); } catch (...) { rejected = true; }
    require(rejected, "JSON loader must not evaluate JavaScript");
    std::filesystem::remove(file);
    std::cout << "molecular JSON scenes, shared fields, clocks and strict gating pass\n";
  } catch (const std::exception& e) { std::filesystem::remove(file); std::cerr << e.what() << '\n'; return 1; }
}
