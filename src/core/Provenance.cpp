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

std::string hashFileContents(const std::string& path) {
  if (path.empty()) {
    return {};
  }
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    return {};
  }
  const std::string bytes((std::istreambuf_iterator<char>(in)),
                          std::istreambuf_iterator<char>());
  return hashConfigJson(bytes);
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
  j["determinism_mode"] = record.determinismMode;
  j["predictive_mode"] = record.predictiveMode;
  j["stratify_enabled"] = record.stratifyEnabled;
  j["stratify_model_path"] = record.stratifyModelPath;
  j["stratify_model_hash"] = record.stratifyModelHash;
  j["stratify_model_hash_available"] = record.stratifyModelHashAvailable;
  j["stratify_total_count"] = record.stratifyTotalCount;
  j["stratify_predictable_count"] = record.stratifyPredictableCount;
  j["stratify_exceptional_count"] = record.stratifyExceptionalCount;
  j["stratify_unclassified_count"] = record.stratifyUnclassifiedCount;
  j["stratify_source_thresholds_count"] = record.stratifySourceThresholdsCount;
  j["stratify_source_model_count"] = record.stratifySourceModelCount;
  j["stratify_source_unknown_count"] = record.stratifySourceUnknownCount;
  j["hooks_enabled"] = record.hooksEnabled;
  j["hooks_registered"] = record.hooksRegistered;
  j["hooks_guardrail_max_step_callbacks"] = record.hooksGuardrailMaxStepCallbacks;
  j["hooks_guardrail_max_emits_per_callback"] = record.hooksGuardrailMaxEmitsPerCallback;
  j["hooks_guardrail_max_emit_payload_bytes"] = record.hooksGuardrailMaxEmitPayloadBytes;
  j["hook_on_init_count"] = record.hookOnInitCount;
  j["hook_on_run_start_count"] = record.hookOnRunStartCount;
  j["hook_on_event_start_count"] = record.hookOnEventStartCount;
  j["hook_on_step_count"] = record.hookOnStepCount;
  j["hook_on_step_raw_count"] = record.hookOnStepRawCount;
  j["hook_on_step_dropped_count"] = record.hookOnStepDroppedCount;
  j["hook_on_event_end_count"] = record.hookOnEventEndCount;
  j["hook_on_run_end_count"] = record.hookOnRunEndCount;
  j["hook_unknown_registered_count"] = record.hookUnknownRegisteredCount;
  j["hook_patch_count"] = record.hookPatchCount;
  j["hook_emit_count"] = record.hookEmitCount;
  j["hook_emit_dropped_count"] = record.hookEmitDroppedCount;
  j["system_event_count"] = record.systemEventCount;
  j["system_event_edep_mean_mev"] = record.systemEventEdepMeanMeV;
  j["system_event_edep_variance_mev2"] = record.systemEventEdepVarianceMeV2;
  j["system_event_edep_stddev_mev"] = record.systemEventEdepStddevMeV;

  std::ofstream out(path_, std::ios::app);
  out << j.dump() << '\n';
}

} // namespace trech
