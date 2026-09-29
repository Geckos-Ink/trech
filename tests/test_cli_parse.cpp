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

  const char* argvInspect[] = {"trech", "inspect", "exp.js", "--param",
                               "temperature_k=310.5", "--param", "quality=\"fast\""};
  const int argcInspect = static_cast<int>(sizeof(argvInspect) / sizeof(argvInspect[0]));
  const auto inspect = trech::parseRunOptions(
      argcInspect, const_cast<char**>(argvInspect));
  if (expect(inspect.valid && inspect.command == trech::CliCommand::Inspect,
             "Expected inspect command mode.")) {
    return 1;
  }
  if (expect(inspect.scriptParameterOverrides.size() == 2,
             "Expected repeatable script parameter overrides.")) {
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

  const char* argv6[] = {"trech", "lab", "--ui"};
  int argc6 = static_cast<int>(sizeof(argv6) / sizeof(argv6[0]));
  auto options6 = trech::parseRunOptions(argc6, const_cast<char**>(argv6));
  if (expect(!options6.valid, "Expected --ui to fail in persistent lab mode.")) {
    return 1;
  }

  const char* argv7[] = {"trech", "lab", "--macro", "run.mac"};
  int argc7 = static_cast<int>(sizeof(argv7) / sizeof(argv7[0]));
  auto options7 = trech::parseRunOptions(argc7, const_cast<char**>(argv7));
  if (expect(!options7.valid, "Expected --macro to fail in persistent lab mode.")) {
    return 1;
  }

  const char* argv8[] = {"trech", "inspect", "exp.js", "--events", "2"};
  const int argc8 = static_cast<int>(sizeof(argv8) / sizeof(argv8[0]));
  if (expect(!trech::parseRunOptions(argc8, const_cast<char**>(argv8)).valid,
             "Expected --events to fail in inspect mode.")) {
    return 1;
  }

  // Observation-only 3D capture: a default run leaves viz untouched, --viz
  // enables the recorder, --viz-all adds non-optical tracks, and the cap is a
  // positive integer. Lab/inspect reject the flags.
  {
    trech::TrechConfig untouched;
    trech::applyRunOverrides(untouched, options1);
    if (expect(!untouched.viz.enable, "Default run must not enable viz capture.")) {
      return 1;
    }
    const char* argvViz[] = {"trech", "run", "exp.js", "--viz-all",
                             "--viz-max-trajectories", "64"};
    const int argcViz = static_cast<int>(sizeof(argvViz) / sizeof(argvViz[0]));
    const auto vizOptions = trech::parseRunOptions(argcViz, const_cast<char**>(argvViz));
    if (expect(vizOptions.valid && vizOptions.captureViz && vizOptions.captureVizNonOptical &&
                   vizOptions.captureVizMaxTrajectories == 64,
               "Expected --viz-all --viz-max-trajectories 64 to parse.")) {
      return 1;
    }
    trech::TrechConfig captured;
    trech::applyRunOverrides(captured, vizOptions);
    if (expect(captured.viz.enable && captured.viz.includeNonOptical &&
                   captured.viz.maxTrajectories == 64,
               "Expected --viz-all capture to enable non-optical recording.")) {
      return 1;
    }
    const char* argvOptical[] = {"trech", "run", "exp.js", "--viz"};
    const auto opticalOptions = trech::parseRunOptions(4, const_cast<char**>(argvOptical));
    trech::TrechConfig optical;
    optical.viz.maxTrajectories = 17;
    trech::applyRunOverrides(optical, opticalOptions);
    if (expect(optical.viz.enable && !optical.viz.includeNonOptical &&
                   optical.viz.maxTrajectories == 17,
               "Expected --viz to keep the scenario's own viz settings.")) {
      return 1;
    }
    const char* argvBadCap[] = {"trech", "run", "exp.js", "--viz-max-trajectories", "0"};
    if (expect(!trech::parseRunOptions(5, const_cast<char**>(argvBadCap)).valid,
               "Expected a non-positive trajectory cap to fail.")) {
      return 1;
    }
    const char* argvLabViz[] = {"trech", "lab", "--viz"};
    if (expect(!trech::parseRunOptions(3, const_cast<char**>(argvLabViz)).valid,
               "Expected --viz to fail in lab mode.")) {
      return 1;
    }
  }

  return 0;
}
