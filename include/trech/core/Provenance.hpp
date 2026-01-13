#pragma once

#include <cstdint>
#include <string>

namespace trech {

struct ProvenanceRecord {
  std::string phase;
  std::string configJson;
  std::string configHash;
  std::string geant4Version;
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
