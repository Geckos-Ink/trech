#include "TemporaryDirectory.hpp"

#include "trech/core/Provenance.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/ml/FeaturePipeline.hpp"
#include "trech/ml/Stratifier.hpp"

#include <nlohmann/json.hpp>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace {
void require(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
}

void write(const std::filesystem::path& path, const std::string& bytes) {
  std::ofstream out(path, std::ios::binary);
  out << bytes;
  require(static_cast<bool>(out), "could not write test fixture");
}
}  // namespace

int main() {
  try {
    const trech::test::TemporaryDirectory fixture;
    const auto path = fixture.path() / "classifier.json";
    const auto names = trech::ml::FeaturePipeline().FeatureNames();
    nlohmann::json model = {{"model", "logistic_stratifier_v1"},
        {"feature_schema", "trech_event_features_v1"}, {"feature_names", names},
        {"weights", std::vector<double>(names.size(), 0.0)},
        {"mean", std::vector<double>(names.size(), 0.0)},
        {"std", std::vector<double>(names.size(), 1.0)}, {"bias", 2.0}};
    const auto bytes = model.dump();
    write(path, bytes);
    trech::StratifyConfig cfg;
    cfg.enable = true;
    cfg.modelPath = path.string();
    trech::DeterminismConfig predictive;
    predictive.mode = "predictive";
    const auto captured = trech::ml::captureStratifierModel(cfg, predictive);
    require(captured && captured->status == "loaded" && captured->bytes == bytes &&
            captured->sha256 == trech::sha256Hex(bytes) && captured->sizeBytes == bytes.size() &&
            captured->contentId == "fnv1a64:" + trech::fnv1a64Hex(bytes),
            "capture must identify the bytes supplied to workers");
    model["bias"] = -2.0;
    write(path, model.dump());
    trech::ml::EventFeatures features;
    trech::ml::EventStratifier worker(cfg, predictive, captured);
    trech::ml::EventStratifier fresh(cfg, predictive);
    require(worker.modelLoaded() && worker.Evaluate(features).exceptional &&
            !fresh.Evaluate(features).exceptional,
            "replacement must not change captured worker inference");
    std::filesystem::remove(path);
    trech::ml::EventStratifier laterWorker(cfg, predictive, captured);
    require(laterWorker.Evaluate(features).exceptional,
            "worker must load captured bytes after source deletion");
    const auto failed = trech::ml::captureStratifierModel(cfg, predictive);
    require(failed && failed->status == "failed" && failed->sha256.empty() &&
            failed->bytes.empty() && failed->sizeBytes == 0,
            "failed capture must not publish identities");
    write(path, bytes);
    trech::ml::EventStratifier failedWorker(cfg, predictive, failed);
    require(!failedWorker.modelLoaded() && failedWorker.Evaluate(features).source == "thresholds",
            "failed snapshot must not retry a restored path");
    write(path, bytes + " trailing garbage");
    const auto malformed = trech::ml::captureStratifierModel(cfg, predictive);
    require(malformed->status == "failed" && malformed->bytes.empty() && malformed->contentId.empty(),
            "malformed capture must not retain parsed prefix or identity");
    write(path, bytes);
    trech::ml::EventStratifier malformedWorker(cfg, predictive, malformed);
    require(!malformedWorker.modelLoaded(), "malformed snapshot must not retry a restored path");
    auto corrupt = std::make_shared<trech::ml::StratifierModelSnapshot>(*captured);
    corrupt->sha256.assign(64, '0');
    bool digestRejected = false;
    try { trech::ml::EventStratifier mismatch(cfg, predictive, corrupt); }
    catch (const std::runtime_error&) { digestRejected = true; }
    require(digestRejected, "worker must reject a snapshot with an inconsistent digest");
    trech::DeterminismConfig strict;
    strict.mode = "strict";
    auto disabled = trech::ml::captureStratifierModel(cfg, strict);
    require(disabled->status == "disabled_strict" && disabled->bytes.empty() && disabled->sha256.empty(),
            "strict capture must not load a model");
    trech::ml::EventStratifier strictWorker(cfg, strict, captured);
    require(!strictWorker.modelLoaded() && strictWorker.Evaluate(features).source == "thresholds",
            "strict worker must ignore even an available snapshot");
    cfg.enable = false;
    disabled = trech::ml::captureStratifierModel(cfg, predictive);
    require(disabled->status == "disabled" && disabled->bytes.empty(),
            "disabled stratification must not load a model");
    cfg.enable = true;
    cfg.modelPath = (fixture.path() / "different.json").string();
    bool rejected = false;
    try { trech::ml::EventStratifier mismatch(cfg, predictive, captured); }
    catch (const std::runtime_error&) { rejected = true; }
    require(rejected, "worker must reject a snapshot from another configured path");
    cfg.modelPath.clear();
    require(!trech::ml::captureStratifierModel(cfg, predictive),
            "unconfigured classifier must not invent a snapshot");

    // Experiment-relative artifacts: a relative path missing from the working directory is
    // read beside the experiment, while the snapshot keeps the declared path.
    namespace fs = std::filesystem;
    const auto bundle = fixture.path() / "bundle";
    fs::create_directories(bundle / "scene_deps");
    const auto experiment = (bundle / "scene.js").string();
    model["bias"] = 2.0;
    const auto bundled = model.dump();
    write(bundle / "scene_deps" / "classifier.json", bundled);
    const std::string declared = "scene_deps/classifier.json";
    require(!fs::exists(declared), "test working directory must not contain the bundle path");
    const auto resolved = trech::resolveArtifactPath(declared, experiment);
    require(fs::path(resolved) == (bundle / declared).lexically_normal(),
            "missing working-directory artifact must resolve beside the experiment");
    require(trech::resolveArtifactPath(declared, "") == declared &&
            trech::resolveArtifactPath("scene_deps/absent.json", experiment) == "scene_deps/absent.json" &&
            trech::resolveArtifactPath(resolved, "elsewhere/x.js") == resolved,
            "empty experiment, unresolvable and absolute paths must stay as declared");
    cfg.modelPath = declared;
    const auto relative = trech::ml::captureStratifierModel(cfg, predictive, resolved);
    require(relative && relative->status == "loaded" && relative->path == declared &&
            relative->sha256 == trech::sha256Hex(bundled),
            "snapshot must read the resolved file but record the declared path");
    require(trech::ml::captureStratifierModel(cfg, predictive)->status == "failed",
            "without a resolved read path the working-directory lookup still fails");
    std::cout << "model loader snapshots: all checks passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
