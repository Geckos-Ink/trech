#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/js/JsRuntime.hpp"

#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech {

// A scenario evaluated beside the active one, ready to replace it.
struct LabScriptCandidate {
  std::unique_ptr<JsRuntime> runtime;
  TrechConfig config;            // the scenario config after onInit
  HookInitTallies init;          // what that onInit did
  nlohmann::json parameters;     // the full TRECH_VALUE override map it was evaluated with
};

// The JavaScript side of a scenario-backed live lab (`trech lab <experiment.js>`).
//
// One JsRuntime address stays valid for the whole session: the Geant4 actions built with the
// first batch hold it. `reload` and `params` evaluate the scenario again, from disk, in a
// separate runtime (prepare); only when that evaluation, its onInit and the caller's checks
// succeed is the new runtime swapped in (commit). A failed or refused re-evaluation leaves
// the active hooks, models and JavaScript state untouched. Hook state persists across
// batches until a commit replaces it.
class LabScriptHost {
 public:
  LabScriptHost(std::string experimentPath, const std::vector<std::string>& cliOverrides,
                bool strictConfig);
  ~LabScriptHost();

  // Evaluate the scenario with the current overrides changed by `changes` (name -> JSON
  // value; null restores the authored default) and dispatch its onInit. Throws on any script,
  // TRECH_VALUE, config or (strict) override error. Never touches the active runtime.
  LabScriptCandidate prepare(const nlohmann::json& changes = nlohmann::json::object()) const;
  // Swap `candidate` into the stable runtime, advance the generation and keep its onInit
  // tallies for the next batch. `trigger` records why this generation exists: "start",
  // "params", "reload" or "watch".
  void commit(LabScriptCandidate candidate, const std::string& trigger = "start");

  // Watch mode (`trech lab <experiment.js> --watch`). When any file the active generation read
  // (script sources and TRECH_READ_JSON data) now has other bytes on disk, or is gone, returns a
  // digest of that on-disk state; otherwise, or when that exact state was already refused,
  // returns "". A modification time or size change triggers a re-read; equal bytes are no edit.
  std::string changedSourceFingerprint();
  // Remember a refused on-disk state so it is reported once, not before every batch.
  void refuseWatchedEdit(const std::string& fingerprint);

  JsRuntime* runtime() { return active_.get(); }
  int generation() const { return generation_; }
  const nlohmann::json& parameters() const { return parameters_; }
  // {generation, trigger, entry, sources_sha256, sources:[{path, sha256}], data (when the
  // scenario read TRECH_READ_JSON files), parameter_overrides}:
  // the identity recorded with every batch as provenance/scores `lab_script`.
  const nlohmann::json& identity() const { return identity_; }
  // identity plus phase "lab_script", the resolved TRECH_VALUE declarations, the registered
  // hooks and the last onInit tallies: the line the CLI prints after a (re)load.
  nlohmann::json status() const;

  // Fill a batch's metadata: the pending onInit tallies once after each commit (zero
  // afterwards) and the identity. batchCompleted() marks the pending tallies reported.
  void prepareBatch(RuntimeRunMetadata& metadata) const;
  void batchCompleted();

 private:
  std::string experimentPath_;
  bool strictConfig_ = false;
  std::unique_ptr<JsRuntime> active_;
  nlohmann::json parameters_ = nlohmann::json::object();
  nlohmann::json identity_ = nlohmann::json::object();
  std::vector<std::string> registeredHooks_;
  HookInitTallies init_;
  bool initPending_ = false;
  int generation_ = 0;
  struct WatchedFile {
    std::string path;
    std::string sha256;  // the bytes the active generation evaluated
    std::filesystem::file_time_type stamp;
    std::intmax_t size = -1;
  };
  std::vector<WatchedFile> watched_;
  std::string refusedFingerprint_;
};

}  // namespace trech
