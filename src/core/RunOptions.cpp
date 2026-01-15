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
  out << "Usage: trech run <experiment.js> [options]\n"
      << "Options:\n"
      << "  --macro <file>    Execute Geant4 macro in batch mode\n"
      << "  --ui              Start interactive UI session\n"
      << "  --output <dir>    Write outputs under directory (default: .)\n"
      << "  --seed <n>        Override RNG seed\n"
      << "  --events <n>      Override event count\n"
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

  if (command != "run") {
    options.valid = false;
    options.error = "Unknown command: " + command;
    return options;
  }

  if (argc < 3) {
    options.valid = false;
    options.error = "Missing experiment path.";
    return options;
  }

  options.experimentPath = argv[2];

  for (int i = 3; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "-h" || arg == "--help") {
      options.showHelp = true;
      return options;
    }
    if (arg == "--macro") {
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --macro.";
        return options;
      }
      options.macroPath = argv[++i];
      continue;
    }
    if (arg == "--ui") {
      options.enableUi = true;
      continue;
    }
    if (arg == "--output" || arg == "-o") {
      if (i + 1 >= argc) {
        options.valid = false;
        options.error = "Missing value for --output.";
        return options;
      }
      options.outputDir = argv[++i];
      continue;
    }
    if (arg == "--seed") {
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
