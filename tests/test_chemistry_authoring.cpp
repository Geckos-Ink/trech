#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <nlohmann/json.hpp>

using json = nlohmann::json;
void require(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }
const auto scenario = std::string(TRECH_SOURCE_DIR) + "/examples/experiments/chemistry_mode.js";
json structure(const char* element = "H", int a = 0) {
  json atom = {{"element", element}, {"position", {0, 0, 0}}};
  if (a) atom["massNumber"] = a;
  return {{"atoms", json::array({atom})}, {"bonds", json::array()}, {"charge", 0}};
}
void overrideJson(trech::JsRuntime& js, const json& s, const json& plan, bool strict = false) {
  js.setScriptParameterOverrides({"structure_json=" + json(s.dump()).dump(),
    "reaction_json=" + json(plan.is_null() ? "" : plan.dump()).dump(),
    std::string("mode=\"") + (strict ? "strict" : "predictive") + "\""});
}
int main() {
  const auto model = std::filesystem::temp_directory_path() / "trech_chemistry_test_hazard.json";
  try {
    const auto legacy = json::parse(trech::configToJsonString(trech::TrechConfig{}));
    require(!legacy.contains("materialProbe"), "default probe changed config bytes");
    require(!legacy.contains("hooks"), "default hooks changed config bytes");
    trech::JsRuntime scaffold;
    const auto defaultInputs = json::parse(scaffold.evalExperimentAndGetConfigJson(scenario))["hooks"]["inputs"];
    for (const auto& bond : defaultInputs["structure"]["bonds"])
      require(bond.size() == 2, "unrecorded scaffold bond order must stay unknown");
    const auto cfg = trech::configFromJsonString(R"({"materials":[{"name":"HD","densityGcm3":1,"components":[{"element":"H","atoms":1,"massNumber":1},{"element":"H","atoms":1,"massNumber":2}]}],"materialProbe":{"enable":true,"includeIsotopes":true},"hooks":{"inputs":{"positions":[[1,2,3]]}}})");
    const auto serialized = trech::configToJsonString(cfg);
    require(trech::configToJsonString(trech::configFromJsonString(serialized)) == serialized,
            "new material/probe/input config must round trip byte-identically");
    const auto encoded = json::parse(serialized);
    require(!encoded["materials"][0]["components"][0].contains("fraction"), "stoichiometry must not emit fraction");
    for (const auto* invalid : {
      R"({"materials":{"components":[{"element":"H","atoms":1.5}]}})",
      R"({"materials":{"components":[{"element":"H","atoms":0}]}})",
      R"({"materials":{"components":[{"element":"H","massNumber":-1,"fraction":1}]}})",
      R"({"materials":{"components":[{"material":"G4_WATER","massNumber":2,"fraction":1}]}})",
      R"({"materials":{"components":[{"element":"H","atoms":2,"fraction":1}]}})",
      R"({"materials":{"components":[{"element":"H","atoms":2},{"element":"O","fraction":1}]}})",
      R"({"hooks":{"inputs":[]}})"}) {
      bool rejected = false;
      try { (void)trech::configFromJsonString(invalid); } catch (...) { rejected = true; }
      require(rejected, "malformed isotope/stoichiometry/input accepted");
    }
    auto h = structure(), d = structure("H", 2);
    auto h2 = h; h2["atoms"].push_back(h2["atoms"][0]); h2["bonds"] = {{0, 1, 1}};
    json plan;
    plan["species"] = json::array({{{"name", "H"}, {"count", 2}, {"structure", h}},
                                   {{"name", "H2"}, {"count", 0}, {"structure", h2}}});
    json channel = {{"name", "join"}, {"delta", {{"H", -2}, {"H2", 1}}}};
    plan["channels"] = json::array({channel});
    auto changed = h; changed["atoms"][0]["position"][0] = 1;
    trech::JsRuntime first, second;
    overrideJson(first, h, nullptr); overrideJson(second, changed, nullptr);
    const auto a = trech::configToJsonString(trech::configFromJsonString(first.evalExperimentAndGetConfigJson(scenario)));
    const auto b = trech::configToJsonString(trech::configFromJsonString(second.evalExperimentAndGetConfigJson(scenario)));
    require(a != b, "authored coordinates must affect the config hash input");
    for (int invalid = 0; invalid < 4; ++invalid) {
      auto bad = plan;
      if (invalid == 0) bad["channels"][0]["delta"]["H"] = -1;
      if (invalid == 1) bad["species"][0]["structure"] = d;
      if (invalid == 2) bad["species"][1]["structure"]["charge"] = 1;
      if (invalid == 3) bad["channels"][0]["delta"]["typo"] = 1;
      trech::JsRuntime js; overrideJson(js, h, bad);
      bool rejected = false;
      try { js.evalExperimentAndGetConfigJson(scenario); } catch (...) { rejected = true; }
      require(rejected, "unbalanced atom/isotope/charge or unknown species accepted");
    }
    {
      std::ofstream f(model);
      // Deterministic test fixture only; never a deployed chemistry model.
      f << R"({"model":"generic_surrogate_v1","input_features":["edep_mev","material.molecular_probe.isotope.Z1.A2.neutrons"],"output_features":["hazard_join"],"layers":[{"weights":[[0,0]],"bias":[1],"activation":"none"}]})";
    }
    plan["modelPath"] = model.string();
    for (int variant = 0; variant < 4; ++variant) {
      const bool strict = variant == 1, missing = variant == 2, noModel = variant == 3;
      trech::JsRuntime js;
      // Explicit isotope disables the unrelated natural-composition photon model.
      auto selectedPlan = plan;
      if (noModel) selectedPlan.erase("modelPath");
      overrideJson(js, d, selectedPlan, strict);
      js.evalExperimentAndGetConfigJson(scenario);
      trech::HookRuntimeContext ctx;
      ctx.determinismMode = strict ? "strict" : "predictive"; ctx.seed = 42; ctx.eventId = 0;
      auto row = json{{"symbol", "H"}, {"z", 1}, {"atomic_mass_amu", 2.014}, {"natural_isotopic_composition", false},
                      {"isotopes", {{{"a", 2}, {"z", 1}, {"abundance", 1}, {"neutrons", 1}}}}};
      if (missing) row["isotopes"][0].erase("neutrons");
      auto natural = row; natural["isotopes"][0]["a"] = 1; natural["natural_isotopic_composition"] = true;
      ctx.materialsJson = json::array({{{"name", "molecular_probe"}, {"available", true}, {"elements", {row}}},
        {{"name", "chem_species_H"}, {"available", true}, {"elements", {natural}}},
        {{"name", "chem_species_H2"}, {"available", true}, {"elements", {natural}}}}).dump();
      auto report = js.dispatchHook("onEventEnd", ctx, nullptr, false);
      const auto emits = js.takeEmittedRecords();
      require(emits.size() == 3 && report.emitDroppedCount == 0, "chemistry emits missing");
      const auto result = json::parse(emits.back().payloadJson);
      require(result["inventory"]["H"][0] == (strict || missing || noModel ? 2 : 0), "strict/inferred inventory changed incorrectly");
      require(result["inventory"]["H2"][0] == (strict || missing || noModel ? 0 : 1), "conserved product inventory incorrect");
      require(report.predictCount == (strict || missing || noModel ? 0u : 1u), "strict/inference counters incorrect");
      require(strict || noModel ? result["result"].is_null() : result["result"]["drawCount"] == (missing ? 0 : 1),
              "reaction draws not gated by strict mode");
      require(!json::parse(emits.front().payloadJson)["capabilities"]["particle_response"]["available"].get<bool>(),
              "isotope model coverage must not be invented");
    }
    std::filesystem::remove(model);
    std::cout << "chemistry authoring contracts pass\n";
  } catch (const std::exception& e) {
    std::filesystem::remove(model);
    std::cerr << e.what() << '\n'; return 1;
  }
}
