#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>

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

  fs::path path = fs::temp_directory_path() / "trech_js_runtime_test.js";
  {
    std::ofstream out(path);
    out << "const cfg = { run: { nEvents: 3 } };\\n";
    out << "globalThis.TRECH_CONFIG = JSON.stringify(cfg);\\n";
  }

  try {
    trech::JsRuntime js;
    const std::string json = js.evalExperimentAndGetConfigJson(path.string());
    const trech::TrechConfig cfg = trech::configFromJsonString(json);
    if (expect(cfg.run.nEvents == 3, "Expected nEvents to be 3.")) {
      return 1;
    }
  } catch (const std::exception& ex) {
    std::cerr << "JS runtime error: " << ex.what() << "\n";
    return 1;
  }

  std::error_code ec;
  fs::remove(path, ec);
  return 0;
}
