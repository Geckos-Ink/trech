#include "trech/js/JsRuntime.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <nlohmann/json.hpp>

namespace {
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
}

int main() {
  namespace fs = std::filesystem;
  const auto directory = fs::temp_directory_path() /
      ("trech_bundle_" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  fs::create_directories(directory);
  auto write = [&](const char* name, const char* text) { std::ofstream(directory / name) << text; };
  try {
    write("sample.ui.js", R"JS(
TRECH_PARAMETERS({count: function() {
  return {type:'integer', default: baseline, min:1, max:10, label:'Event count'};
}});
globalThis.TRECH_UI_DESCRIPTOR = function() {
  globalThis.TRECH_STUDIO = {schema:'trech_studio_v1', title:'Sample UI'};
};
)JS");
    write("sample.view.js", "TRECH_VIEWS.sample = {colour: function() { return 'red'; }};");
    write("sample.validation.js", "TRECH_VALIDATIONS.sample = {schema:'trech_scenario_validation_v1', expected:3};");
    write("sample.js", R"JS(
const baseline = 3;
globalThis.TRECH_CONFIG = {run:{nEvents:TRECH_PARAMETER('count')}};
globalThis.TRECH_HOOKS = {onRunStart(ctx) {ctx.emit('colour', TRECH_VIEWS.sample.colour());}};
)JS");
    write("wrapper.ui.js", "globalThis.TRECH_UI_DESCRIPTOR = function() {globalThis.TRECH_STUDIO.title = 'Wrapper UI';};");
    write("wrapper.js", "TRECH_INCLUDE('sample.js');");
    {
      trech::JsRuntime runtime;
      runtime.setScriptParameterOverrides({"count=7"});
      const auto config = nlohmann::json::parse(runtime.evalExperimentAndGetConfigJson((directory / "wrapper.js").string()));
      const auto metadata = nlohmann::json::parse(runtime.authoringMetadataJson());
      require(config.at("run").at("nEvents") == 7, "Nested UI override did not reach physics");
      require(!config.contains("validation") && !config.contains("studio"), "Authoring data leaked into physics config");
      require(metadata.at("sources").size() == 6, "Nested companions missing from source inventory");
      require(metadata.at("studio").at("title") == "Wrapper UI", "Nested UI descriptor replaced the parent descriptor");
      require(metadata.at("validation").at("sample").at("expected") == 3, "Validation metadata missing");
    }
    {
      trech::JsRuntime runtime;
      runtime.setScriptParameterOverrides({"count=11"});
      bool rejected = false;
      try { runtime.evalExperimentAndGetConfigJson((directory / "sample.js").string()); }
      catch (const std::exception& error) { rejected = std::string(error.what()).find("count") != std::string::npos; }
      require(rejected, "UI range was not enforced outside Studio");
    }
    write("sample.view.js", "throw new Error('broken view');");
    {
      trech::JsRuntime runtime;
      bool diagnosed = false;
      try { runtime.evalExperimentAndGetConfigJson((directory / "sample.js").string()); }
      catch (const std::exception& error) {
        const std::string message = error.what();
        diagnosed = message.find("sample.view.js") != std::string::npos && message.find("broken view") != std::string::npos;
      }
      require(diagnosed, "Companion errors lost their source path");
    }
    fs::remove_all(directory);
    std::cout << "Bundle loading, nested sources, UI bounds, metadata and diagnostics pass\n";
  } catch (const std::exception& error) {
    fs::remove_all(directory);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
