#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace trech {

struct TrechConfig;

struct RunOptions {
  std::string experimentPath;
  std::string macroPath;
  std::string outputDir = ".";
  bool enableUi = false;
  bool hasSeedOverride = false;
  std::uint64_t seedOverride = 0;
  bool hasEventOverride = false;
  int eventOverride = 0;
  std::string physicsList;
  std::string rngEngine;
  std::vector<std::string> cliArgs;
  bool showHelp = false;
  bool valid = true;
  std::string error;
};

std::string runUsage();
RunOptions parseRunOptions(int argc, char** argv);
void applyRunOverrides(TrechConfig& cfg, const RunOptions& options);

} // namespace trech
