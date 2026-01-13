#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace trech {

struct ProvenanceRecord {
  std::string phase;
  std::string configJson;
  std::string configHash;
  std::string geant4Version;
  std::string physicsList;
  std::string rngEngine;
  std::vector<std::string> cliArgs;
  std::string macroPath;
  std::string outputDir;
  int nEvents = 0;
  std::uint64_t seed = 0;
};

class ProvenanceWriter {
public:
  explicit ProvenanceWriter(const std::string& path);
  void write(const ProvenanceRecord& record) const;

private:
  std::string path_;
};

std::string hashConfigJson(const std::string& json);

} // namespace trech
