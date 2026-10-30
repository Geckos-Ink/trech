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

  // Known SHA-256 vectors plus padding boundaries and all byte values. Keep
  // the existing FNV config-hash contract independent of artifact digests.
  const std::vector<std::pair<std::string, std::string>> vectors = {
      {"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
      {"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},
      {std::string(55, 'a'), "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318"},
      {std::string(56, 'a'), "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a"},
      {std::string(63, 'a'), "7d3e74a05d7db15bce4ad9ec0658ea98e3f06eeecf16b4c6fff2da457ddc2f34"},
      {std::string(64, 'a'), "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb"},
      {std::string(65, 'a'), "635361c48bb9eab14198e76ea8ab7f1a41685d6ad62aa9146d301d4f17eb0ae0"},
      {std::string(1000000, 'a'), "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"}};
  for (const auto& vector : vectors)
    if (expect(trech::sha256Hex(vector.first) == vector.second, "SHA-256 vector mismatch.")) return 1;
  std::string binary;
  for (unsigned i = 0; i < 256; ++i) binary.push_back(static_cast<char>(i));
  if (expect(trech::sha256Hex(binary) == "40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880",
             "SHA-256 must preserve embedded NUL and high bytes.")) return 1;
  if (expect(trech::hashConfigJson("hello") == "a430d84680aabd0b", "Config hash changed algorithm.")) return 1;

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
  record.hooksEnabled = true;
  record.hooksRegistered = {"onInit", "onRunStart", "onStep"};
  record.hooksGuardrailMaxStepCallbacks = 1234;
  record.hooksGuardrailMaxEmitsPerCallback = 5;
  record.hooksGuardrailMaxEmitPayloadBytes = 512;
  record.hookOnInitCount = 1;
  record.hookOnRunStartCount = 1;
  record.hookOnEventStartCount = 4;
  record.hookOnStepCount = 1234;
  record.hookOnStepRawCount = 1300;
  record.hookOnStepDroppedCount = 66;
  record.hookOnEventEndCount = 4;
  record.hookOnRunEndCount = 1;
  record.hookUnknownRegisteredCount = 0;
  record.hookPatchCount = 2;
  record.hookEmitCount = 5;
  record.hookEmitDroppedCount = 3;
  record.nuclearEnabled = true;
  record.nuclearCycleCount = 1;
  record.nuclearConsistentCycleCount = 1;
  record.systemEventCount = 10;
  record.systemEventEdepMeanMeV = 1.25;
  record.systemEventEdepVarianceMeV2 = 0.0625;
  record.systemEventEdepStddevMeV = 0.25;

  writer.write(record);
  record.phase = "run_end";
  record.modelArtifactsJson = R"({"schema":"trech_model_artifacts_v1","models":[{"name":"missing","loaded":false,"sha256":null,"size_bytes":null}]})";
  writer.write(record);

  std::ifstream in(path);
  std::string line;
  std::getline(in, line);
  if (expect(!line.empty(), "Provenance output is empty.")) {
    return 1;
  }

  const auto json = nlohmann::json::parse(line);
  if (expect(!json.contains("model_artifacts"), "Legacy provenance invented a manifest.")) return 1;
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
  if (expect(json.at("hooks_enabled") == true, "Hooks enabled mismatch.")) {
    return 1;
  }
  if (expect(json.at("hooks_guardrail_max_step_callbacks") == 1234,
             "Hooks guardrail mismatch.")) {
    return 1;
  }
  if (expect(json.at("hooks_guardrail_max_emits_per_callback") == 5,
             "Hook emit guardrail mismatch.")) {
    return 1;
  }
  if (expect(json.at("hooks_guardrail_max_emit_payload_bytes") == 512,
             "Hook payload guardrail mismatch.")) {
    return 1;
  }
  if (expect(json.at("hook_on_step_dropped_count") == 66,
             "Hook onStep dropped count mismatch.")) {
    return 1;
  }
  if (expect(json.at("hook_patch_count") == 2, "Hook patch count mismatch.")) {
    return 1;
  }
  if (expect(json.at("hook_emit_count") == 5, "Hook emit count mismatch.")) {
    return 1;
  }
  if (expect(json.at("hook_emit_dropped_count") == 3,
             "Hook emit dropped count mismatch.")) {
    return 1;
  }
  if (expect(json.at("nuclear_enabled") == true, "Nuclear enabled mismatch.")) {
    return 1;
  }
  if (expect(json.at("nuclear_cycle_count") == 1, "Nuclear cycle count mismatch.")) {
    return 1;
  }
  if (expect(json.at("nuclear_consistent_cycle_count") == 1,
             "Nuclear consistent cycle count mismatch.")) {
    return 1;
  }
  if (expect(json.at("hooks_registered").is_array() &&
                 json.at("hooks_registered").size() == 3,
             "Hooks registered list mismatch.")) {
    return 1;
  }
  if (expect(json.at("system_event_count") == 10, "System event count mismatch.")) {
    return 1;
  }
  if (expect(json.at("system_event_edep_stddev_mev") == 0.25,
             "System event stddev mismatch.")) {
    return 1;
  }

  std::getline(in, line);
  const auto end = nlohmann::json::parse(line);
  if (expect(end.at("model_artifacts") == nlohmann::json::parse(record.modelArtifactsJson),
             "Provenance lost typed artifact snapshot.")) return 1;
  fs::remove(path, ec);
  return 0;
}
