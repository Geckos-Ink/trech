#include "trech/core/Provenance.hpp"

#include <fstream>
#include <iomanip>
#include <sstream>

#include <nlohmann/json.hpp>

namespace trech {
namespace {

std::uint64_t fnv1a64(const std::string& input) {
  const std::uint64_t kOffset = 14695981039346656037ull;
  const std::uint64_t kPrime = 1099511628211ull;
  std::uint64_t hash = kOffset;
  for (unsigned char c : input) {
    hash ^= static_cast<std::uint64_t>(c);
    hash *= kPrime;
  }
  return hash;
}

} // namespace

std::string hashConfigJson(const std::string& json) {
  // TODO: replace with SHA-256 once the provenance format is finalized.
  const std::uint64_t hash = fnv1a64(json);
  std::ostringstream out;
  out << std::hex << std::setw(16) << std::setfill('0') << hash;
  return out.str();
}

ProvenanceWriter::ProvenanceWriter(const std::string& path) : path_(path) {}

void ProvenanceWriter::write(const ProvenanceRecord& record) const {
  nlohmann::json j;
  j["phase"] = record.phase;
  j["config_json"] = record.configJson;
  j["config_hash"] = record.configHash;
  j["geant4_version"] = record.geant4Version;
  j["physics_list"] = record.physicsList;
  j["rng_engine"] = record.rngEngine;
  j["cli_args"] = record.cliArgs;
  j["macro_path"] = record.macroPath;
  j["output_dir"] = record.outputDir;
  j["n_events"] = record.nEvents;
  j["seed"] = record.seed;

  std::ofstream out(path_, std::ios::app);
  out << j.dump() << '\n';
}

} // namespace trech
