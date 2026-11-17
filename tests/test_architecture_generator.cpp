// Engine-side architecture generation: classic reference family, deterministic
// native trainer, job parsing, the Python worker bridge and the decision rule.
//
//   test_architecture_generator          classic + bridge (fake workers, no torch)
//   test_architecture_generator --live   the real Evolvo worker (TRECH_ML_PYTHON;
//                                        an unavailable worker fails the test)
#include "trech/ml/ArchitectureGenerator.hpp"
#include "trech/ml/GenericSurrogate.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
using nlohmann::json;
using namespace trech::ml;

namespace {

int failures = 0;
void check(bool ok, const std::string& what) {
  if (!ok) {
    ++failures;
    std::cerr << "FAIL: " << what << "\n";
  }
}

// splitmix-free deterministic data: a fixed quasi-random sequence.
double frac(double v) { return v - std::floor(v); }

json rows(int n, int offset, bool linear) {
  json out = json::array();
  for (int i = 0; i < n; ++i) {
    const double a = 2.0 * frac((i + offset) * 0.6180339887) - 1.0;
    const double b = 2.0 * frac((i + offset) * 0.4142135623) - 1.0;
    const double y = linear ? 2.0 * a - b + 0.5 : std::sin(3.0 * a) * b + a * a;
    out.push_back({{"a", a}, {"b", b}, {"y", y}});
  }
  return out;
}

json baseJob(const std::string& name, bool linear, int epochs) {
  return {{"schema", "trech_arch_job_v1"},
          {"name", name},
          {"inputs", {"a", "b"}},
          {"outputs", {"y"}},
          {"data", {{"train", rows(120, 0, linear)}, {"selection", rows(40, 500, linear)},
                    {"test", rows(40, 900, linear)}}},
          {"seed", 11},
          {"budget", {{"max_params", 5000}, {"max_epochs", epochs}, {"generations", 1},
                      {"population", 3}, {"patience", 1}, {"worker_timeout_s", 30}}}};
}

bool throwsWith(const json& job, const std::string& fragment) {
  try {
    parseArchitectureJob(job, ".");
  } catch (const std::invalid_argument& e) {
    if (std::string(e.what()).find(fragment) != std::string::npos) return true;
    std::cerr << "  (got: " << e.what() << ")\n";
    return false;
  }
  return false;
}

fs::path outDir(const std::string& leaf) {
  const fs::path dir = fs::path(TRECH_BINARY_DIR) / "arch_generator" / leaf;
  fs::remove_all(dir);
  return dir;
}

int live() {
  auto job = parseArchitectureJob(baseJob("live", false, 200), ".");
  job.generations = 2;
  job.population = 4;
  job.maxRows = 3;
  const auto outcome = ArchitectureGenerator::generate(job, outDir("live").string());
  const auto& evolvo = outcome.outcome.at("evolvo");
  const std::string status = evolvo.value("status", std::string());
  check(outcome.ok && (status == "accepted" || status == "rejected"),
        "the real worker returns a scorable model (" + status + ": " + evolvo.value("error", std::string()) + ")");
  check(evolvo.value("scored_by", std::string()) == "engine", "the engine re-scores the evolved model");
  check(evolvo.value("report_agrees", false), "the engine's selection loss agrees with the worker's");
  GenericSurrogate model;
  check(model.load(outcome.modelPath), "the chosen model loads");
  std::cout << "live: " << status << " -> " << outcome.generator << " (" << outcome.reason << ")\n";
  return failures ? 1 : 0;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc > 1 && std::string(argv[1]) == "--live") return live();

  // Ladder and classic family.
  const auto ladder = widthLadder(4, 64);
  check(ladder == std::vector<int>({4, 6, 8, 11, 16, 23, 32, 45, 64}), "the width ladder matches GFSL-NN");
  {
    json j = baseJob("family", false, 10);
    auto job = parseArchitectureJob(j, ".");
    job.outputs = {"u", "v"};
    job.inputs = {"a", "b", "c"};
    job.train.y.assign(300, {0.0, 0.0});
    job.maxParams = 20000;
    const auto family = classicStructures(job);
    check(family.size() == 3 && family[0].name == "linear" && family[0].params == 8,
          "the family starts with the linear map");
    check(family[1].widths == std::vector<int>({16}) && family[1].params == 98, "mlp1 width 16 (98 params)");
    check(family[2].widths == std::vector<int>({16, 16}) && family[2].params == 370, "mlp2 16x16 (370 params)");
    check(family[1].genome["rows"][0][0] == "mlp" && family[1].genome["rows"][0][3][1] == 1,
          "classic structures are GFSL-NN genomes");
    job.train.y.assign(10, {0.0, 0.0});
    const auto small = classicStructures(job);
    check(small[2].widths == std::vector<int>({8, 8}) && small[2].params == 122,
          "few training targets shrink the classic width (8 params per target)");
  }

  // Job validation.
  json bad = baseJob("x", false, 10);
  bad["schema"] = "nope";
  check(throwsWith(bad, "schema"), "wrong schema is refused");
  bad = baseJob("x", false, 10);
  bad["inputs"] = {"a", "a"};
  check(throwsWith(bad, "unique"), "duplicate names are refused");
  bad = baseJob("x", false, 10);
  bad["data"]["train"][3].erase("b");
  check(throwsWith(bad, "row 3 lacks numeric 'b'"), "a missing column names its row");
  bad = baseJob("x", false, 10);
  bad["generator"] = "magic";
  check(throwsWith(bad, "generator"), "unknown generators are refused");
  bad = baseJob("x", false, 10);
  bad["generator"] = "auto";
  check(throwsWith(bad, "no automatic fallback"), "the old auto (fallback) generator is refused");
  bad = baseJob("x", false, 10);
  bad["require_engine_native"] = true;
  check(throwsWith(bad, "LibTorch is required"), "require_engine_native is refused");
  bad = baseJob("../x", false, 10);
  check(throwsWith(bad, "file stem"), "names cannot escape the output directory");
  bad = baseJob("x", false, 10);
  bad["data"]["train"] = "same.jsonl";
  bad["data"]["selection"] = "same.jsonl";
  {
    std::ofstream("same.jsonl") << "{\"a\":1,\"b\":2,\"y\":3}\n{\"a\":2,\"b\":1,\"y\":0}\n";
    check(throwsWith(bad, "different tables"), "one table cannot be both train and selection");
    fs::remove("same.jsonl");
  }

  // Native trainer: deterministic, learns, and its export reloads exactly.
  auto job = parseArchitectureJob(baseJob("native", false, 400), ".");
  const auto family = classicStructures(job);
  const auto fitA = trainClassicNative(job, family[1]);
  const auto fitB = trainClassicNative(job, family[1]);
  check(fitA.layers[0].weights == fitB.layers[0].weights && fitA.selectionLoss == fitB.selectionLoss,
        "the native trainer is deterministic");
  {
    // Slow steady progress is not a plateau: gains below relTol per epoch that add up over the
    // patience window keep training (the old per-epoch rule stopped mlp1 at epoch 222, loss 0.155).
    auto longJob = parseArchitectureJob(baseJob("long", false, 1000), ".");
    const auto slow = trainClassicNative(longJob, classicStructures(longJob)[1]);
    check(slow.epochs > 500 && slow.selectionLoss < 0.05,
          "a still-improving classic fit is not stopped as a plateau (" + std::to_string(slow.epochs) +
              " epochs, loss " + std::to_string(slow.selectionLoss) + ")");
  }
  const auto linearFit = trainClassicNative(job, family[0]);
  check(fitA.selectionLoss < 0.5 * linearFit.selectionLoss, "the MLP beats the linear map on a nonlinear target");
  const fs::path nativeDir = outDir("native");
  fs::create_directories(nativeDir);
  const std::string path = (nativeDir / "m.json").string();
  const json exported = nativeModelJson(job, fitA);
  std::ofstream(path) << exported.dump();
  GenericSurrogate model;
  check(model.load(path), "the engine loads the native export: " + model.note());
  double worst = 0.0;
  for (const auto& x : job.test.x) {
    std::vector<double> out;
    model.predictVector(x, &out);
    const auto ref = predictNative(fitA, x);
    worst = std::max(worst, std::fabs(out[0] - ref[0]) / std::max(1.0, std::fabs(ref[0])));
  }
  check(worst < 1e-9, "GenericSurrogate reproduces the native trainer (worst " + std::to_string(worst) + ")");
  check(exported.contains("holdout") && exported["holdout"]["n"] == 40 && exported.contains("input_domain"),
        "the export carries test holdout and input domain");

  // Classic generation.
  auto outcome = ArchitectureGenerator::generate(parseArchitectureJob(
      [] { auto j = baseJob("classic", false, 200); j["generator"] = "classic"; return j; }(), "."),
      outDir("classic").string());
  check(outcome.generator == "classic" && fs::exists(outcome.modelPath) && fs::exists(outcome.outcomePath),
        "the classic generator writes a model and an outcome");
  check(!outcome.outcome["evolvo"]["attempted"].get<bool>(), "classic jobs do not start the worker");

  // Missing interpreter -> an error, never a classic stand-in.
  auto failed = [](const ArchitectureOutcome& o, const std::string& status) {
    return !o.ok && o.generator == "none" && o.modelPath.empty() && o.outcome["evolvo"]["status"] == status &&
           o.outcome["decision"]["ok"] == false && fs::exists(o.outcomePath);
  };
  {
    auto j = baseJob("nopython", false, 50);
    j["python"] = "/nonexistent/python3";
    outcome = ArchitectureGenerator::generate(parseArchitectureJob(j, "."), outDir("nopython").string());
    check(failed(outcome, "not_started"), "a missing interpreter fails the job: " + outcome.reason);
  }

#ifdef TRECH_TEST_PYTHON
  auto fake = [&](const std::string& mode, bool linear, int epochs, double timeout) {
    auto j = baseJob(mode, linear, epochs);
    j["python"] = TRECH_TEST_PYTHON;
    j["worker"] = {{"module", "fake_arch_worker"},
                   {"path", std::string(TRECH_SOURCE_DIR) + "/tests/fixtures/arch_worker_fake"}};
    j["budget"]["worker_timeout_s"] = timeout;
    return ArchitectureGenerator::generate(parseArchitectureJob(j, "."), outDir("fake_" + mode).string());
  };
  outcome = fake("better", true, 3, 30);
  check(outcome.generator == "evolvo" && outcome.outcome["evolvo"]["status"] == "accepted",
        "a better evolved model replaces the classic reference: " + outcome.reason);
  check(outcome.outcome["evolvo"]["selection_loss"].get<double>() < 1e-20, "the engine scores the exact model at zero");
  outcome = fake("worse", false, 200, 30);
  check(outcome.ok && outcome.generator == "classic" && outcome.outcome["evolvo"]["status"] == "rejected",
        "a worse evolved model is rejected and the better reference kept");
  check(!outcome.outcome["evolvo"]["report_agrees"].get<bool>(),
        "the engine catches a worker that misreports its loss");
  outcome = fake("mismatch", true, 3, 30);
  check(failed(outcome, "mismatched_result"), "a result for another request fails the job");
  outcome = fake("unavailable", false, 20, 30);
  check(failed(outcome, "unavailable") && outcome.outcome["evolvo"]["exit_code"] == 3,
        "worker unavailability fails the job");
  outcome = fake("crash", false, 20, 30);
  check(failed(outcome, "no_result"), "a crashing worker fails the job");
  outcome = fake("hang", false, 20, 1.0);
  check(failed(outcome, "timeout"), "a hanging worker is killed at the timeout and fails the job");
#else
#error "TRECH_TEST_PYTHON (TRECH_ML_PYTHON) is required"
#endif

  if (failures) {
    std::cerr << failures << " failure(s)\n";
    return 1;
  }
  std::cout << "test_architecture_generator: all checks passed\n";
  return 0;
}
