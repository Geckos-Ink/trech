#include "trech/core/RunOptions.hpp"
#include "trech/core/Config.hpp"

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
  const char* argv1[] = {
      "trech",
      "run",
      "exp.js",
      "--seed",
      "123",
      "--events",
      "5",
      "--output",
      "out",
      "--macro",
      "run.mac",
      "--ui"};
  int argc1 = static_cast<int>(sizeof(argv1) / sizeof(argv1[0]));
  auto options1 = trech::parseRunOptions(argc1, const_cast<char**>(argv1));
  if (expect(options1.valid, "Expected options to be valid.")) {
    return 1;
  }
  if (expect(options1.experimentPath == "exp.js", "Experiment path mismatch.")) {
    return 1;
  }
  if (expect(options1.macroPath == "run.mac", "Macro path mismatch.")) {
    return 1;
  }
  if (expect(options1.outputDir == "out", "Output dir mismatch.")) {
    return 1;
  }
  if (expect(options1.hasSeedOverride && options1.seedOverride == 123, "Seed override mismatch.")) {
    return 1;
  }
  if (expect(options1.hasEventOverride && options1.eventOverride == 5, "Event override mismatch.")) {
    return 1;
  }
  if (expect(options1.enableUi, "Expected UI flag to be enabled.")) {
    return 1;
  }

  trech::TrechConfig cfg;
  trech::applyRunOverrides(cfg, options1);
  if (expect(cfg.run.seed == 123, "Seed override not applied.")) {
    return 1;
  }
  if (expect(cfg.run.nEvents == 5, "Event override not applied.")) {
    return 1;
  }

  const char* argv2[] = {"trech", "run", "exp.js", "--seed", "nope"};
  int argc2 = static_cast<int>(sizeof(argv2) / sizeof(argv2[0]));
  auto options2 = trech::parseRunOptions(argc2, const_cast<char**>(argv2));
  if (expect(!options2.valid, "Expected invalid options for bad seed.")) {
    return 1;
  }

  return 0;
}
