#include "TemporaryDirectory.hpp"

// Real optional-backend integration, with synthetic numerical modules only.
// Fixtures are authored in C++, so this gate needs no Python torch package.
#include "trech/core/Provenance.hpp"
#include "trech/ml/GenericSurrogate.hpp"
#include "trech/ml/OpticsSurrogate.hpp"
#include "trech/ml/Stratifier.hpp"
#include "trech/ml/TorchScriptStub.hpp"

#include <torch/script.h>

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>

namespace {
void require(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
}

void save(const std::filesystem::path& path, const std::string& definition) {
  torch::jit::Module model("synthetic_fixture");
  model.define(definition);
  model.save(path.string());
}

std::string bytes(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}
} // namespace

int main() {
  namespace fs = std::filesystem;
  const trech::test::TemporaryDirectory fixture;
  const auto& directory = fixture.path();
  try {
    const auto path = directory / "generic.pt";
    save(path, "def forward(self, x):\n    return x * 2.0 + 1.0\n");
    trech::ml::GenericSurrogate generic;
    require(generic.load(path.string()), "TorchScript snapshot load failed");
    const auto snapshot = bytes(path);
    const auto digest = generic.contentSha256();
    require(digest == trech::sha256Hex(snapshot) && generic.contentSizeBytes() == snapshot.size(),
            "TorchScript identity differs from loader bytes");
    std::vector<double> output;
    require(generic.predictVector({3, 4}, &output) && output == std::vector<double>({7, 9}),
            "TorchScript vector inference failed");
    trech::ml::GenericSurrogate::Workspace workspace;
    const double input[] = {3, 4};
    double fixed[] = {-1, -1};
    require(generic.predictInto(input, 2, fixed, 2, workspace) && fixed[0] == 7 && fixed[1] == 9,
            "TorchScript fixed-buffer inference failed");
    fixed[0] = -1;
    require(!generic.predictInto(input, 2, fixed, 1, workspace) && fixed[0] == -1,
            "Wrong TorchScript output width published partial data");
    output = {99};
    require(!generic.predictVector({std::numeric_limits<double>::quiet_NaN()}, &output) &&
            output == std::vector<double>({99}), "Nonfinite TorchScript input was published");
    require(!generic.predictVector({std::numeric_limits<double>::max()}, &output) &&
            output == std::vector<double>({99}), "Overflowing float input was published");
    save(path, "def forward(self, x):\n    return x * 3.0\n");
    require(generic.contentSha256() == digest && generic.predictVector({3, 4}, &output) &&
            output == std::vector<double>({7, 9}), "File replacement relabelled loaded TorchScript weights");
    trech::ml::GenericSurrogate fresh;
    require(fresh.load(path.string()) && fresh.contentSha256() != digest &&
            fresh.predictVector({3, 4}, &output) && output == std::vector<double>({9, 12}),
            "Fresh TorchScript load did not observe replacement");
    save(path, "def forward(self, x):\n    return x / 0.0\n");
    require(fresh.load(path.string()), "Nonfinite-output fixture did not load");
    output = {99};
    require(!fresh.predictVector({1}, &output) && output == std::vector<double>({99}),
            "Nonfinite TorchScript output was published");
    fixed[0] = -1;
    require(!fresh.predictInto(input, 1, fixed, 1, workspace) && fixed[0] == -1,
            "Fixed-buffer TorchScript output validation differs from vector API");
    save(path, "def forward(self, x):\n    return (x, x)\n");
    require(fresh.load(path.string()) && !fresh.predictVector({1}, &output) &&
            output == std::vector<double>({99}), "Unsupported TorchScript output was published");
    save(path, "def forward(self, x):\n    return x[1]\n");
    require(fresh.load(path.string()) && !fresh.predictVector({1}, &output) &&
            output == std::vector<double>({99}), "TorchScript inference exception escaped or changed output");
    fs::remove(path);
    require(!generic.load(path.string()) && !generic.loaded() && generic.contentSha256().empty() &&
            generic.contentId().empty() && generic.contentSizeBytes() == 0,
            "Failed TorchScript reload retained weights or identities");

    const auto classifierPath = directory / "classifier.pt";
    save(classifierPath, "def forward(self, x):\n    return torch.sigmoid(x[:, 0:1])\n");
    trech::ml::TorchScriptStub classifier;
    classifier.SetLabels("cold", "hot");
    require(classifier.Load(classifierPath.string()), "TorchScript classifier did not load");
    const auto classifierBytes = bytes(classifierPath);
    const auto classifierDigest = classifier.contentSha256();
    require(classifierDigest == trech::sha256Hex(classifierBytes) &&
            classifier.contentId() == "fnv1a64:" + trech::fnv1a64Hex(classifierBytes) &&
            classifier.contentSizeBytes() == classifierBytes.size(),
            "Classifier identity differs from loaded TorchScript bytes");
    std::string label;
    float score = -1;
    require(classifier.PredictLabel({2}, &label, &score) && label == "hot" &&
            std::abs(score - 0.880797f) < 1e-5, "TorchScript classifier tensor inference failed");
    trech::ml::TorchScriptStub moved(std::move(classifier));
    trech::ml::TorchScriptStub assigned;
    require(assigned.Load(classifierPath.string()), "Move-assignment destination failed to load");
    assigned = std::move(moved);
    require(assigned.contentSha256() == classifierDigest &&
            assigned.PredictLabel({-2}, &label, &score) && label == "cold",
            "TorchScript classifier move lifecycle lost module or labels");
    trech::StratifyConfig config;
    config.enable = true;
    config.modelPath = classifierPath.string();
    config.labelPredictable = "cold";
    config.labelExceptional = "hot";
    trech::DeterminismConfig mode;
    mode.mode = "strict";
    trech::ml::EventStratifier strict(config, mode);
    trech::ml::EventFeatures event;
    event.totalEdepMeV = 2;
    require(!strict.modelLoaded() && strict.Evaluate(event).source == "thresholds",
            "Strict stratification enabled TorchScript inference");
    mode.mode = "predictive";
    trech::ml::EventStratifier predictive(config, mode);
    require(predictive.modelLoaded() && predictive.Evaluate(event).source == "model" &&
            predictive.Evaluate(event).label == "hot", "Predictive stratification lost TorchScript model");
    save(classifierPath, "def forward(self, x):\n    return 'hot'\n");
    require(assigned.contentSha256() == classifierDigest &&
            assigned.PredictLabel({-2}, &label, &score) && label == "cold",
            "Replacing classifier file relabelled or changed the loaded module");
    require(assigned.Load(classifierPath.string()) && assigned.PredictLabel({1}, &label) && label == "hot",
            "TorchScript string-label output failed");
    require(assigned.contentSha256() == trech::sha256Hex(bytes(classifierPath)) &&
            assigned.contentSha256() != classifierDigest,
            "Classifier reload did not identify replacement bytes");
    save(classifierPath, "def forward(self, x):\n    return torch.tensor([0.25, 0.75])\n");
    require(assigned.Load(classifierPath.string()) && assigned.PredictLabel({1}, &label, &score) &&
            label == "hot" && score == 0.75f, "Two-class TorchScript tensor output failed");
    save(classifierPath, "def forward(self, x):\n    return x[1]\n");
    require(assigned.Load(classifierPath.string()), "Invalid-input classifier fixture failed to load");
    label = "unchanged";
    score = -1;
    require(!assigned.PredictLabel({1}, &label, &score) && label == "unchanged" && score == -1,
            "Classifier interpreter exception escaped or changed output");
    require(!assigned.Load((directory / "missing.pt").string()) && !assigned.loaded() &&
            assigned.contentId().empty() && assigned.contentSha256().empty() && assigned.contentSizeBytes() == 0 &&
            !assigned.PredictLabel({1}, &label),
            "Failed classifier reload retained a module");
    require(assigned.LoadSnapshot((directory / "missing.pt").string(), classifierBytes) &&
            assigned.contentSha256() == classifierDigest && assigned.PredictLabel({-2}, &label) && label == "cold",
            "Supplied TorchScript classifier snapshot reopened its path or lost bytes");

    const auto opticsPath = directory / "optics.pt";
    save(opticsPath, "def forward(self, x):\n    return x[:, 0:3] + 1.0\n");
    trech::ml::OpticsSurrogate optics;
    require(optics.load(opticsPath.string()), "TorchScript optics module did not load");
    const auto opticsBytes = bytes(opticsPath);
    const auto opticsDigest = optics.contentSha256();
    require(opticsDigest == trech::sha256Hex(opticsBytes) &&
            optics.contentId() == "fnv1a64:" + trech::fnv1a64Hex(opticsBytes) &&
            optics.contentSizeBytes() == opticsBytes.size(),
            "Optics identity differs from loaded TorchScript bytes");
    std::vector<float> composition(trech::ml::OpticsSurrogate::kInputFeatureCount, 0);
    composition[0] = 0.25f;
    std::array<float, 3> optical{};
    require(optics.predict(composition, &optical) && optical[0] == 1.25f &&
            optical[1] == 1 && optical[2] == 1, "TorchScript optics tensor inference failed");
    save(opticsPath, "def forward(self, x):\n    return x[1]\n");
    require(optics.contentSha256() == opticsDigest && optics.predict(composition, &optical) && optical[0] == 1.25f,
            "Replacing optics file relabelled or changed the loaded module");
    require(optics.load(opticsPath.string()), "Invalid-input optics fixture failed to load");
    require(optics.contentSha256() == trech::sha256Hex(bytes(opticsPath)) && optics.contentSha256() != opticsDigest,
            "Optics reload did not identify replacement bytes");
    optical = {{-1, -1, -1}};
    require(!optics.predict(composition, &optical) && optical == std::array<float, 3>{{-1, -1, -1}},
            "Optics interpreter exception escaped or published partial output");
    require(!optics.load((directory / "missing.pt").string()) && !optics.loaded() &&
            optics.contentId().empty() && optics.contentSha256().empty() && optics.contentSizeBytes() == 0 &&
            !optics.predict(composition, &optical), "Failed optics reload retained a module");
    std::cout << "TorchScript loaders, lifecycle, strict gates and snapshot inference pass\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
