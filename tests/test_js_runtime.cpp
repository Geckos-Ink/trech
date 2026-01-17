#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
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
    out << "globalThis.TRECH_CONFIG = JSON.stringify(cfg);\n";
  }

  try {
    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(path.string());
    const trech::TrechConfig cfg = trech::configFromJsonString(json);
    failures += expect(cfg.run.nEvents == 3, "Expected nEvents to be 3.");
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
    out << "throw new Error(\"include boom\");\n";
  }
  {
    std::ofstream out(mainFile);
    out << "TRECH_INCLUDE(\"helper.js\");\n";
    out << "const cfg = { run: { nEvents: 1 } };\n";
    out << "globalThis.TRECH_CONFIG = JSON.stringify(cfg);\n";
  }

  try {
    trech::JsRuntime js;
    (void)js.evalExperimentAndGetConfigJson(mainFile.string());
    failures += expect(false, "Expected include error to be thrown.");
  } catch (const std::exception& ex) {
    const std::string msg = ex.what();
    failures += expect(msg.find(includeFile.filename().string()) != std::string::npos,
                       "Expected included filename in error.");
  }

  fs::remove_all(includeDir, ec);
  return failures == 0 ? 0 : 1;
}
