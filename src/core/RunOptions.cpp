#include "trech/core/RunOptions.hpp"

#include "trech/core/Config.hpp"

#include <exception>
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

std::string runUsage() {
  std::ostringstream out;
  out << "Usage:\n"
      << "  trech run <experiment.js> [options]\n"
      << "  trech inspect <experiment.js> [--param <name>=<json>]\n"
      << "  trech lab [options]\n"
      << "Options:\n"
      << "  --macro <file>    Execute Geant4 macro in batch mode (run only)\n"
      << "  --ui              Start interactive UI session (run only)\n"
      << "  --config <file>   Load initial JSON config (lab mode)\n"
      << "  --commands <file> Read JSON command stream from file (lab mode)\n"
      << "  --output <dir>    Write outputs under directory (default: .)\n"
      << "  --seed <n>        Override RNG seed\n"
      << "  --events <n>      Override event count\n"
      << "  --param <n>=<json> Override a typed TRECH_VALUE (run/inspect; repeatable)\n"
      << "  -h, --help        Show this help\n";
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
  } else {
    options.valid = false;
    options.error = "Unknown command: " + command;
    return options;
  }

  for (int i = argStart; i < argc; ++i) {
    const std::string arg = argv[i];
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
    if (arg == "--param") {
      if (options.command == CliCommand::Lab) {
        options.valid = false;
        options.error = "--param is only supported in run/inspect mode.";
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
    if (arg == "--ui") {
      if (options.command != CliCommand::Run) {
        options.valid = false;
        options.error = "--ui is only supported in run mode.";
        return options;
      }
      options.enableUi = true;
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

  return options;
}

void applyRunOverrides(TrechConfig& cfg, const RunOptions& options) {
  if (options.hasSeedOverride) {
    cfg.run.seed = options.seedOverride;
  }
  if (options.hasEventOverride) {
    cfg.run.nEvents = options.eventOverride;
  }
}

} // namespace trech
