#include "trech/js/JsRuntime.hpp"
#include <nlohmann/json.hpp>
#include <filesystem>
#include <iostream>
#include <stdexcept>

// Lattice Boltzmann development track: exact/benchmark anchors must hold before any
// scenario companion comparison is trusted (AGENTS/engine/lattice/AGENTS.md).
int main() {
  try {
    trech::JsRuntime runtime;
    runtime.evalExperimentAndGetConfigJson((std::filesystem::path(TRECH_SOURCE_DIR) /
        "tests/fixtures/js/lbm_accuracy.js").string());
    trech::HookRuntimeContext context;
    context.determinismMode = "strict";
    context.eventId = 0;
    const auto report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto records = runtime.takeEmittedRecords();
    if (report.predictCount || report.emitDroppedCount || records.size() != 1)
      throw std::runtime_error("Verification must emit one complete report without inference");
    const auto result = nlohmann::json::parse(records[0].payloadJson);
    if (result.at("schema") != "trech_lbm_verification_v1" || result.at("anchors").size() != 11 ||
        result.at("physical_accuracy_verified") != false || result.at("particle_training_data") != false)
      throw std::runtime_error("LBM anchors missing or mislabelled as physical training/validation");
    const auto& parity = result.at("anchors").at(8);
    if (parity.at("kind") != "native_parity" || parity.at("native_available") != true ||
        parity.at("bit_identical") != true)
      throw std::runtime_error("Native lattice advance missing or not bit-identical to the JS reference");
    for (const auto& anchor : result.at("anchors")) std::cout << anchor.dump() << '\n';
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
