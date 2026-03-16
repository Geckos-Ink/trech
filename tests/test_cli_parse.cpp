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
  if (expect(options1.command == trech::CliCommand::Run, "Expected run command mode.")) {
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

  const char* argv3[] = {"trech", "lab", "--config", "lab_config.json",
                         "--commands", "commands.jsonl", "--events", "9",
                         "--seed", "77", "--output", "lab_out"};
  int argc3 = static_cast<int>(sizeof(argv3) / sizeof(argv3[0]));
  auto options3 = trech::parseRunOptions(argc3, const_cast<char**>(argv3));
  if (expect(options3.valid, "Expected lab options to be valid.")) {
    return 1;
  }
  if (expect(options3.command == trech::CliCommand::Lab, "Expected lab command mode.")) {
    return 1;
  }
  if (expect(options3.configPath == "lab_config.json", "Lab config path mismatch.")) {
    return 1;
  }
  if (expect(options3.commandsPath == "commands.jsonl", "Lab commands path mismatch.")) {
    return 1;
  }
  if (expect(options3.outputDir == "lab_out", "Lab output dir mismatch.")) {
    return 1;
  }
  if (expect(options3.hasEventOverride && options3.eventOverride == 9,
             "Lab events override mismatch.")) {
    return 1;
  }
  if (expect(options3.hasSeedOverride && options3.seedOverride == 77,
             "Lab seed override mismatch.")) {
    return 1;
  }

  const char* argv4[] = {"trech", "run", "exp.js", "--config", "lab.json"};
  int argc4 = static_cast<int>(sizeof(argv4) / sizeof(argv4[0]));
  auto options4 = trech::parseRunOptions(argc4, const_cast<char**>(argv4));
  if (expect(!options4.valid, "Expected --config to fail in run mode.")) {
    return 1;
  }

  const char* argv5[] = {"trech", "lab", "--commands"};
  int argc5 = static_cast<int>(sizeof(argv5) / sizeof(argv5[0]));
  auto options5 = trech::parseRunOptions(argc5, const_cast<char**>(argv5));
  if (expect(!options5.valid, "Expected missing --commands value to fail.")) {
    return 1;
  }

  return 0;
}
