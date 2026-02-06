#include "trech/core/Provenance.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>

#include <nlohmann/json.hpp>

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
  namespace fs = std::filesystem;

  fs::path path = fs::temp_directory_path() / "trech_provenance_test.jsonl";
  std::error_code ec;
  fs::remove(path, ec);

  trech::ProvenanceWriter writer(path.string());
  trech::ProvenanceRecord record;
  record.phase = "run_start";
  record.configJson = "{\"run\":{\"nEvents\":1}}";
  record.configHash = "deadbeef";
  record.geant4Version = "G4-TEST";
  record.physicsList = "QBBC";
  record.rngEngine = "HepJamesRandom";
  record.cliArgs = {"trech", "run", "exp.js"};
  record.macroPath = "run.mac";
  record.outputDir = "out";
  record.nEvents = 1;
  record.seed = 99;
  record.determinismMode = "predictive";
  record.predictiveMode = true;
  record.stratifyEnabled = true;
  record.stratifyModelPath = "models/stratify.pt";
  record.stratifyModelHash = "cafecafe";
  record.stratifyModelHashAvailable = true;
  record.stratifyTotalCount = 10;
  record.stratifyPredictableCount = 9;
  record.stratifyExceptionalCount = 1;
  record.stratifySourceThresholdsCount = 7;
  record.stratifySourceModelCount = 3;
  record.stratifySourceUnknownCount = 0;

  writer.write(record);

  std::ifstream in(path);
  std::string line;
  std::getline(in, line);
  if (expect(!line.empty(), "Provenance output is empty.")) {
    return 1;
  }

  const auto json = nlohmann::json::parse(line);
  if (expect(json.at("phase") == "run_start", "Phase mismatch.")) {
    return 1;
  }
  if (expect(json.at("config_hash") == "deadbeef", "Config hash mismatch.")) {
    return 1;
  }
  if (expect(json.at("geant4_version") == "G4-TEST", "Geant4 version mismatch.")) {
    return 1;
  }
  if (expect(json.at("physics_list") == "QBBC", "Physics list mismatch.")) {
    return 1;
  }
  if (expect(json.at("rng_engine") == "HepJamesRandom", "RNG engine mismatch.")) {
    return 1;
  }
  if (expect(json.at("n_events") == 1, "n_events mismatch.")) {
    return 1;
  }
  if (expect(json.at("seed") == 99, "Seed mismatch.")) {
    return 1;
  }
  if (expect(json.at("determinism_mode") == "predictive", "Determinism mode mismatch.")) {
    return 1;
  }
  if (expect(json.at("predictive_mode") == true, "Predictive mode mismatch.")) {
    return 1;
  }
  if (expect(json.at("stratify_model_hash") == "cafecafe",
             "Stratify model hash mismatch.")) {
    return 1;
  }
  if (expect(json.at("stratify_source_model_count") == 3,
             "Stratify source model count mismatch.")) {
    return 1;
  }

  fs::remove(path, ec);
  return 0;
}
