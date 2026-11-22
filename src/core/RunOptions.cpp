#include "trech/core/RunOptions.hpp"

#include "trech/core/Config.hpp"
#include "trech/core/Trace.hpp"

#include <exception>
#include <filesystem>
#include <cmath>
#include <sstream>

namespace trech {
namespace {

bool parseUnsigned(const std::string& text, std::uint64_t& value) {
  std::size_t pos = 0;
  try {
    value = std::stoull(text, &pos, 10);
  } catch (const std::exception&) {
    return false;
  }
  return pos == text.size();
}

bool parseInteger(const std::string& text, int& value) {
  std::size_t pos = 0;
  try {
    value = std::stoi(text, &pos, 10);
  } catch (const std::exception&) {
    return false;
  }
  return pos == text.size();
}

} // namespace

std::string resolveArtifactPath(const std::string& declared, const std::string& experimentPath) {
  namespace fs = std::filesystem;
  const fs::path path(declared);
  if (declared.empty() || path.is_absolute() || experimentPath.empty()) return declared;
  std::error_code ec;
  if (fs::is_regular_file(path, ec)) return declared;
  const fs::path base = fs::path(experimentPath).parent_path();
  if (base.empty()) return declared;
  const fs::path alternative = (base / path).lexically_normal();
  return fs::is_regular_file(alternative, ec) ? alternative.string() : declared;
}

std::string runUsage() {
  std::ostringstream out;
  out << "Usage:\n"
      << "  trech run <experiment.js> [options]\n"
      << "  trech inspect <experiment.js> [--param <name>=<json>]\n"
      << "  trech lab [<experiment.js>] [options]   (live session; a scenario's hooks run)\n"
      << "  trech arch <job.json> [--output <dir>] [--generator evolvo|classic] [--python <exe>]\n"
      << "             [--trace <spec>] [--trace-file <f>] [--trace-stderr]\n"
      << "  trech budget [--features <n>] [--targets <n>]   (compute budget and model capacity, JSON)\n"
      << "Options:\n"
      << "  --macro <file>    Execute Geant4 macro in batch mode (run only)\n"
      << "  --ui              Start interactive UI session (run only)\n"
      << "  --config <file>   Load initial JSON config (lab mode)\n"
      << "  --commands <file> Read JSON command stream from file (lab mode)\n"
      << "  --watch           Re-evaluate a lab scenario before a batch when its files change\n"
      << "  --output <dir>    Write outputs under directory (default: .)\n"
      << "  --seed <n>        Override RNG seed\n"
      << "  --events <n>      Override event count\n"
      << "  --refinement <x>  Continuous scenario precision factor (run/inspect)\n"
      << "  --time-budget <s> Soft simulation wall-time budget (predictive run only)\n"
      << "  --param <n>=<json> Override a typed TRECH_VALUE (run/inspect/lab scenario; repeatable)\n"
      << "  --viz             Capture trajectories + scene manifest for 3D replay (run only)\n"
      << "  --viz-all         As --viz, also recording non-optical particles (run only)\n"
      << "  --viz-max-trajectories <n> Trajectory cap for a --viz capture (run only)\n"
      << "  --strict-config   Refuse a config with keys the engine never reads\n"
      << "  --trace <spec>    Engine trace (observation only): <level>[:<cat>,...]; level off,\n"
      << "                    summary, info, debug or trace (default: $TRECH_TRACE). Writes\n"
      << "                    <output>/trech_trace.jsonl and a run attribution summary\n"
      << "  --trace-file <f>  Trace JSONL path instead of <output>/trech_trace.jsonl\n"
      << "  --trace-stderr    Also print every trace record on stderr\n"
      << "  --formal-audit <f> Lean audit report (scripts/check_lean_laws.py --report) whose identity\n"
      << "                    a run with law checks records in provenance (default: $TRECH_FORMAL_AUDIT)\n"
      << "  --js-engine <e>   JavaScript engine: quickjs or v8 (v8 needs a TRECH_ENABLE_V8 build;\n"
      << "                    default: $TRECH_JS_ENGINE, else the build default)\n"
      << "  -h, --help        Show this help\n"
      << "Config notes:\n"
      << "  The apparatus block may be authored as environment, medium or detector\n"
      << "  (aliases merged in that order; provenance and config hashes use detector).\n"
      << "  inspect reports a config the engine would refuse as config_error.\n";
  return out.str();
}

RunOptions parseRunOptions(int argc, char** argv) {
  RunOptions options;
  if (argc > 0 && argv) {
    options.cliArgs.assign(argv, argv + argc);
  }

  if (argc < 2) {
    options.valid = false;
    options.error = "Missing command.";
    return options;
  }

  const std::string command = argv[1];
  if (command == "-h" || command == "--help") {
    options.showHelp = true;
    return options;
  }

  int argStart = 2;
  if (command == "run") {
    options.command = CliCommand::Run;
    if (argc < 3) {
      options.valid = false;
      options.error = "Missing experiment path.";
      return options;
    }
    options.experimentPath = argv[2];
    argStart = 3;
  } else if (command == "inspect") {
    options.command = CliCommand::Inspect;
    if (argc < 3) {
      options.valid = false;
      options.error = "Missing experiment path.";
      return options;
    }
    options.experimentPath = argv[2];
    argStart = 3;
  } else if (command == "lab") {
    options.command = CliCommand::Lab;
    // Optional scenario: `trech lab <experiment.js>` hosts its hooks live.
    if (argc >= 3 && argv[2][0] != '-') {
      options.experimentPath = argv[2];
      argStart = 3;
    }
  } else if (command == "budget") {
    // Probe the computational context; no scenario runs.
    options.command = CliCommand::Budget;
    for (int i = 2; i < argc; ++i) {
      const std::string arg = argv[i];
      if ((arg == "--features" || arg == "--targets") && i + 1 < argc) {
        int value = 0;
        try { value = std::stoi(argv[++i]); } catch (...) { value = -1; }
        if (value < 1 || value > 4096) {
          options.valid = false;
          options.error = arg + " must be an integer in [1, 4096].";
          return options;
        }
        (arg == "--features" ? options.budgetFeatures : options.budgetTargets) = value;
      } else {
        options.valid = false;
        options.error = "Unknown budget option: " + arg;
        return options;
      }
    }
    return options;
  } else if (command == "arch") {
    // Architecture generation takes its own small option set and runs no scenario.
    options.command = CliCommand::Arch;
    if (argc < 3) {
      options.valid = false;
      options.error = "Missing architecture job path.";
      return options;
    }
    options.experimentPath = argv[2];
    for (int i = 3; i < argc; ++i) {
      const std::string arg = argv[i];
      if (arg == "-h" || arg == "--help") {
        options.showHelp = true;
        return options;
      }
      if (arg == "--output" || arg == "-o" || arg == "--generator" || arg == "--python") {
        if (i + 1 >= argc) {
          options.valid = false;
          options.error = arg + " requires a value.";
          return options;
        }
        const std::string value = argv[++i];
        if (arg == "--generator") {
          if (value != "evolvo" && value != "classic") {
            options.valid = false;
            options.error = "--generator must be evolvo or classic.";
            return options;
          }
          options.archGenerator = value;
        } else if (arg == "--python") {
          options.archPython = value;
        } else {
          options.outputDir = value;
        }
        continue;
      }
      // The engine trace also covers arch: the search's Python worker traces at the same level
      // and its records are copied into <output>/trech_trace.jsonl (origin "python").
      if (arg == "--trace" || arg == "--trace-file") {
        if (i + 1 >= argc) {
          options.valid = false;
          options.error = "Missing value for " + arg + ".";
          return options;
        }
        const std::string value = argv[++i];
        if (arg == "--trace-file") {
          options.traceFile = value;
          continue;
        }
        try {
          (void)trace::parseSpec(value);
        } catch (const std::exception& error) {
          options.valid = false;
          options.error = std::string("Invalid --trace value: ") + error.what() + ".";
          return options;
        }
        options.traceSpec = value;
        continue;
      }
      if (arg == "--trace-stderr") {
        options.traceStderr = true;
        continue;
      }
      options.valid = false;
      options.error = "Unknown option for arch: " + arg;
      return options;
    }
    return options;
  } else {
    options.valid = false;
    options.error = "Unknown command: " + command;
    return options;
  }

  for (int i = argStart; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--refinement" || arg == "--time-budget") {
      if (options.command == CliCommand::Lab ||
          (arg == "--time-budget" && options.command != CliCommand::Run)) {
        options.valid = false;
        options.error = arg + " is only supported in " +
            (arg == "--refinement" ? "run/inspect mode." : "run mode.");
        return options;
      }
      double value = 0.0;
      try {
        if (i + 1 >= argc) throw std::invalid_argument("missing");
        const std::string raw = argv[++i];
        std::size_t end = 0;
        value = std::stod(raw, &end);
        if (end != raw.size() || !std::isfinite(value) || value <= 0.0)
          throw std::invalid_argument("invalid");
      } catch (const std::exception&) {
        options.valid = false;
        options.error = arg + " requires a finite positive number.";
        return options;
      }
      if (arg == "--refinement") options.refinement = value;
      else options.timeBudgetSeconds = value;
      continue;
    }
    if (arg == "-h" || arg == "--help") {
      options.showHelp = true;
      return options;
    }
    if (arg == "--config") {
      if (options.command != CliCommand::Lab) {
        options.valid = false;
        options.error = "--config is only supported in lab mode.";
        return options;
      }
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --config.";
        return options;
      }
      options.configPath = argv[++i];
      continue;
    }
    if (arg == "--commands") {
      if (options.command != CliCommand::Lab) {
        options.valid = false;
        options.error = "--commands is only supported in lab mode.";
        return options;
      }
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --commands.";
        return options;
      }
      options.commandsPath = argv[++i];
      continue;
    }
    if (arg == "--watch") {
      if (options.command != CliCommand::Lab || options.experimentPath.empty()) {
        options.valid = false;
        options.error = "--watch needs a lab scenario: trech lab <experiment.js> --watch";
        return options;
      }
      options.labWatch = true;
      continue;
    }
    if (arg == "--js-engine") {
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --js-engine.";
        return options;
      }
      options.jsEngine = argv[++i];
      if (options.jsEngine != "quickjs" && options.jsEngine != "v8") {
        options.valid = false;
        options.error = "Invalid --js-engine value; expected quickjs or v8.";
        return options;
      }
      continue;
    }
    if (arg == "--param") {
      if (options.command == CliCommand::Lab && options.experimentPath.empty()) {
        options.valid = false;
        options.error = "--param in lab mode needs a scenario: trech lab <experiment.js> --param ...";
        return options;
      }
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --param.";
        return options;
      }
      const std::string value = argv[++i];
      const auto equals = value.find('=');
      if (equals == std::string::npos || equals == 0 || equals + 1 >= value.size()) {
        options.valid = false;
        options.error = "Invalid --param value; expected name=<json>.";
        return options;
      }
      options.scriptParameterOverrides.push_back(value);
      continue;
    }
    if (arg == "--macro") {
      if (options.command != CliCommand::Run) {
        options.valid = false;
        options.error = "--macro is only supported in run mode.";
        return options;
      }
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --macro.";
        return options;
      }
      options.macroPath = argv[++i];
      continue;
    }
    if (arg == "--strict-config") {
      options.strictConfig = true;
      continue;
    }
    if (arg == "--trace" || arg == "--trace-file") {
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for " + arg + ".";
        return options;
      }
      const std::string value = argv[++i];
      if (arg == "--trace-file") {
        options.traceFile = value;
        continue;
      }
      try {
        (void)trace::parseSpec(value);
      } catch (const std::exception& error) {
        options.valid = false;
        options.error = std::string("Invalid --trace value: ") + error.what() + ".";
        return options;
      }
      options.traceSpec = value;
      continue;
    }
    if (arg == "--trace-stderr") {
      options.traceStderr = true;
      continue;
    }
    if (arg == "--formal-audit") {
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --formal-audit.";
        return options;
      }
      options.formalAuditPath = argv[++i];
      continue;
    }
    if (arg == "--ui") {
      if (options.command != CliCommand::Run) {
        options.valid = false;
        options.error = "--ui is only supported in run mode.";
        return options;
      }
      options.enableUi = true;
      continue;
    }
    if (arg == "--viz" || arg == "--viz-all" || arg == "--viz-max-trajectories") {
      if (options.command != CliCommand::Run) {
        options.valid = false;
        options.error = arg + " is only supported in run mode.";
        return options;
      }
      options.captureViz = true;
      if (arg == "--viz-all") {
        options.captureVizNonOptical = true;
      } else if (arg == "--viz-max-trajectories") {
        int value = 0;
        if (i + 1 >= argc || !parseInteger(argv[++i], value) || value <= 0) {
          options.valid = false;
          options.error = "Invalid value for --viz-max-trajectories.";
          return options;
        }
        options.captureVizMaxTrajectories = value;
      }
      continue;
    }
    if (arg == "--output" || arg == "-o") {
      if (options.command == CliCommand::Inspect) {
        options.valid = false;
        options.error = "--output is not supported in inspect mode.";
        return options;
      }
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --output.";
        return options;
      }
      options.outputDir = argv[++i];
      continue;
    }
    if (arg == "--seed") {
      if (options.command == CliCommand::Inspect) {
        options.valid = false;
        options.error = "--seed is not supported in inspect mode.";
        return options;
      }
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --seed.";
        return options;
      }
      std::uint64_t value = 0;
      if (!parseUnsigned(argv[++i], value)) {
        options.valid = false;
        options.error = "Invalid seed value.";
        return options;
      }
      options.hasSeedOverride = true;
      options.seedOverride = value;
      continue;
    }
    if (arg == "--events") {
      if (options.command == CliCommand::Inspect) {
        options.valid = false;
        options.error = "--events is not supported in inspect mode.";
        return options;
      }
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --events.";
        return options;
      }
      int value = 0;
      if (!parseInteger(argv[++i], value) || value <= 0) {
        options.valid = false;
        options.error = "Invalid events value.";
        return options;
      }
      options.hasEventOverride = true;
      options.eventOverride = value;
      continue;
    }

    options.valid = false;
    options.error = "Unknown option: " + arg;
    return options;
  }

  if (options.command != CliCommand::Lab && options.experimentPath.empty()) {
    options.valid = false;
    options.error = "Missing experiment path.";
    return options;
  }
  if (options.command == CliCommand::Lab && !options.experimentPath.empty() &&
      !options.configPath.empty()) {
    options.valid = false;
    options.error = "trech lab takes a scenario or --config, not both.";
    return options;
  }

  return options;
}

void applyRunOverrides(TrechConfig& cfg, const RunOptions& options) {
  if (options.timeBudgetSeconds > 0.0) {
    cfg.run.timeBudgetSeconds = options.timeBudgetSeconds;
  }
  if (options.hasSeedOverride) {
    cfg.run.seed = options.seedOverride;
  }
  if (options.hasEventOverride) {
    cfg.run.nEvents = options.eventOverride;
  }
  if (cfg.run.timeBudgetSeconds > 0.0) {
    if (cfg.determinism.mode != "predictive") {
      throw std::runtime_error("Time budgets require predictive mode; strict runs use fixed work.");
    }
    cfg.run.threads = 1;
  }
  if (options.captureViz) {
    cfg.viz.enable = true;
    if (options.captureVizNonOptical) {
      cfg.viz.includeNonOptical = true;
    }
    if (options.captureVizMaxTrajectories > 0) {
      cfg.viz.maxTrajectories = options.captureVizMaxTrajectories;
    }
  }
}

bool configureTraceFromOptions(const RunOptions& options) {
  trace::Options resolved = trace::optionsFromEnvironment();
  if (!options.traceSpec.empty()) {
    const auto fromCli = trace::parseSpec(options.traceSpec);
    resolved.level = fromCli.level;
    resolved.categories = fromCli.categories;
  }
  if (!options.traceFile.empty()) resolved.path = options.traceFile;
  if (options.traceStderr) resolved.toStderr = true;
  if (resolved.level != trace::Level::Off && resolved.path.empty()) {
    std::error_code ignored;
    std::filesystem::create_directories(options.outputDir, ignored);
    resolved.path = (std::filesystem::path(options.outputDir) / "trech_trace.jsonl").string();
  }
  trace::configure(resolved);
  return trace::active();
}

} // namespace trech
