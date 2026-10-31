#include "trech/js/JsRuntime.hpp"
#include <nlohmann/json.hpp>
#include <filesystem>
#include <iostream>
#include <stdexcept>

int main() {
  try {
    trech::JsRuntime runtime;
    runtime.evalExperimentAndGetConfigJson((std::filesystem::path(TRECH_SOURCE_DIR) /
        "tests/fixtures/js/euler3d_accuracy.js").string());
    trech::HookRuntimeContext context;
    context.determinismMode = "strict";
    context.eventId = 0;
    const auto report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto records = runtime.takeEmittedRecords();
    if (report.predictCount || report.emitDroppedCount || records.size() != 1)
      throw std::runtime_error("Verification must emit one complete report without inference");
    const auto result = nlohmann::json::parse(records[0].payloadJson);
    if (result.at("anchors").size() != 3 || result.at("physical_accuracy_verified") != false ||
        result.at("particle_training_data") != false)
      throw std::runtime_error("Exact anchors were mislabelled as physical training/validation");
    for (const auto& anchor : result.at("anchors"))
      std::cout << anchor.at("kind") << " grid orders " << anchor.at("spatial_orders")
                << " timestep orders " << anchor.at("temporal_orders") << '\n';
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
