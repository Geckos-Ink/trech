// DomainLearner: response-driven domain emergence, prequential grading,
// tendencies, merges, export/frozen replay and determinism.
#include "trech/ml/ComputeBudget.hpp"
#include "trech/ml/DomainDiscovery.hpp"
#include "trech/ml/DomainLearner.hpp"

#include <cmath>
#include <cstdlib>
#include <fstream>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>

using namespace trech::ml;

namespace {

int failures = 0;

void check(bool ok, const std::string& what) {
  if (!ok) {
    ++failures;
    std::cerr << "FAIL: " << what << "\n";
  } else {
    std::cout << "ok: " << what << "\n";
  }
}

struct Rng {
  std::uint64_t s;
  double uniform() {
    s = s * 6364136223846793005ULL + 1442695040888963407ULL;
    return static_cast<double>(s >> 11) * 0x1.0p-53;
  }
};

DomainLearnerOptions baseOptions() {
  DomainLearnerOptions o;
  o.features = {"a", "b"};
  o.targets = {"y"};
  o.seed = 7;
  o.capacity.maxDomains = 12;
  o.capacity.bufferRows = 2048;
  o.capacity.splitCandidates = 32;
  o.capacity.basisDegree = 1;
  o.minElements = 24;
  return o;
}

// Three affine regimes on a uniform square: no feature gap separates them.
int regimeOf(double a, double b) {
  if (a < 0.4) return 0;
  return b < 0.5 ? 1 : 2;
}

double law(int regime, double a, double b, double shift = 0.0) {
  switch (regime) {
    case 0: return 1.0 + 2.0 * a - b;
    case 1: return -3.0 + 0.5 * a + 4.0 * b + shift;
    default: return 2.0 - 1.5 * a + 0.2 * b;
  }
}

DomainLearnerBatch makeBatch(Rng& rng, std::size_t n, double time, double shift = 0.0,
                             bool sameLaw = false, std::vector<int>* regimes = nullptr) {
  DomainLearnerBatch batch;
  batch.time = time;
  batch.count = n;
  for (std::size_t i = 0; i < n; ++i) {
    const double a = rng.uniform(), b = rng.uniform();
    const int r = regimeOf(a, b);
    batch.features.push_back(a);
    batch.features.push_back(b);
    batch.targets.push_back(sameLaw ? law(0, a, b) : law(r, a, b, shift));
    if (regimes) regimes->push_back(r);
  }
  return batch;
}

// Fraction of elements whose domain's majority regime is their own regime.
double purity(const std::vector<int>& domains, const std::vector<int>& regimes) {
  std::map<int, std::map<int, int>> counts;
  for (std::size_t i = 0; i < domains.size(); ++i) ++counts[domains[i]][regimes[i]];
  int agree = 0;
  for (const auto& [domain, byRegime] : counts) {
    int best = 0;
    for (const auto& [r, c] : byRegime) best = std::max(best, c);
    agree += best;
  }
  return static_cast<double>(agree) / static_cast<double>(domains.size());
}

void regimesEmerge() {
  DomainLearner learner(baseOptions());
  Rng rng{11};
  DomainLearnerResult last;
  std::vector<int> regimes;
  std::size_t splits = 0;
  for (int c = 0; c < 30; ++c) {
    regimes.clear();
    last = learner.update(makeBatch(rng, 400, c, 0.0, false, &regimes));
    for (const auto& e : last.events) splits += e.type == "split";
  }
  check(last.domains.size() >= 3, "three unlabelled affine regimes emerge as >= 3 domains (got " +
                                       std::to_string(last.domains.size()) + ")");
  check(splits >= 2, "subdivision events recorded");
  const double p = purity(last.elementDomains, regimes);
  check(p > 0.97, "domain membership matches the hidden regimes (purity " + std::to_string(p) + ")");
  check(last.scored == 400, "every finite row is graded prequentially");
  check(last.routedRmse[0] < 0.05 * last.pooledRmse[0],
        "routed prequential RMSE " + std::to_string(last.routedRmse[0]) + " << pooled " +
            std::to_string(last.pooledRmse[0]));
  bool tendencies = false;
  for (const auto& d : last.domains) {
    for (const auto& e : d.tendencies) tendencies |= e.series == "sensitivity:y/a";
  }
  check(tendencies, "per-domain model-parameter tendencies are tracked");

  // Export, reload frozen, and replay a new batch bit for bit.
  const auto state = learner.exportState();
  DomainLearner frozen = DomainLearner::fromState(state, true);
  Rng fresh{99};
  auto probe = makeBatch(fresh, 300, 30.0);
  DomainLearner live = DomainLearner::fromState(state, true);
  const auto a = frozen.update(probe);
  probe.targets.clear();  // a frozen learner predicts without targets
  const auto b = live.update(probe);
  bool same = a.predictions.size() == b.predictions.size();
  for (std::size_t i = 0; same && i < a.predictions.size(); ++i) same = a.predictions[i] == b.predictions[i];
  check(same && a.elementDomains == b.elementDomains, "frozen replay is identical with or without targets");
  // Grading with targets over many calls must not move a frozen learner.
  for (int c = 0; c < 12; ++c) frozen.update(makeBatch(fresh, 300, 31.0 + c));
  check(frozen.exportState().at("leaves") == state.at("leaves"),
        "a frozen learner graded with targets never changes its models or predictor choices");
  double sq = 0.0;
  std::size_t wrong = 0;
  Rng again{99};
  const auto truth = makeBatch(again, 300, 30.0);
  for (std::size_t i = 0; i < truth.count; ++i) {
    const double e = a.predictions[i] - truth.targets[i];
    sq += e * e;
    wrong += std::abs(e) > 0.1;
  }
  const double rmse = std::sqrt(sq / static_cast<double>(truth.count));
  check(rmse < 0.1 && wrong <= 6, "held-out frozen predictions follow the laws (RMSE " + std::to_string(rmse) +
                                      ", " + std::to_string(wrong) + "/300 rows off by > 0.1)");
  // Trust gate: rows far outside every domain are flagged extrapolating and withheld; the rest
  // keep their predictions bit for bit.
  {
    DomainLearner gate = DomainLearner::fromState(state, true);
    auto far = probe;
    for (std::size_t i = 0; i < far.count; i += 3) far.features[i * 2] += 1e3;
    auto gated = gate.update(far);
    DomainLearner plain = DomainLearner::fromState(state, true);
    const auto open = plain.update(far);
    const std::size_t withheld = trech::ml::withholdExtrapolated(gated, 1);
    bool keptSame = true, blanked = true;
    for (std::size_t i = 0; i < far.count; ++i) {
      if (gated.extrapolated[i]) blanked = blanked && std::isnan(gated.predictions[i]) && std::isnan(gated.predictionStd[i]);
      else keptSame = keptSame && gated.predictions[i] == open.predictions[i];
    }
    check(withheld == open.extrapolatedCount && withheld >= far.count / 3 && gated.withheldCount == withheld,
          "withholdExtrapolated blanks exactly the extrapolating rows (" + std::to_string(withheld) + ")");
    check(blanked && keptSame, "withheld rows are NaN, covered rows are unchanged");
    check(gate.exportState().at("leaves") == plain.exportState().at("leaves"),
          "withholding predictions changes nothing in the learner");
  }
  check(last.domains.size() <= 5, "exact regimes are not over-split (" + std::to_string(last.domains.size()) + " domains)");
}

void singleLawStaysWhole() {
  auto o = baseOptions();
  o.capacity.basisDegree = 2;
  DomainLearner learner(o);
  Rng rng{5};
  DomainLearnerResult last;
  for (int c = 0; c < 20; ++c) {
    DomainLearnerBatch batch;
    batch.time = c;
    batch.count = 300;
    for (int i = 0; i < 300; ++i) {
      const double a = rng.uniform() * 4.0 - 2.0, b = rng.uniform();
      batch.features.insert(batch.features.end(), {a, b});
      // One quadratic law plus small noise: no response domain to find.
      batch.targets.push_back(0.5 * a * a - a * b + 0.01 * (rng.uniform() - 0.5));
    }
    last = learner.update(batch);
  }
  check(last.domains.size() == 1, "a single quadratic law with noise stays one domain (got " +
                                       std::to_string(last.domains.size()) + ")");
}

void driftAndMerge() {
  auto o = baseOptions();
  o.mergeCooldown = 3;
  DomainLearner learner(o);
  Rng rng{21};
  DomainLearnerResult last;
  bool merged = false;
  for (int c = 0; c < 25; ++c) last = learner.update(makeBatch(rng, 400, c));
  const std::size_t before = last.domains.size();
  // Every regime now follows regime 0's law: the subdivision is obsolete.
  for (int c = 25; c < 110; ++c) {
    last = learner.update(makeBatch(rng, 400, c, 0.0, true));
    for (const auto& e : last.events) merged |= e.type == "merge";
    if (std::getenv("TRECH_DEBUG_LEARNER")) {
      std::cout << c << " domains=" << last.domains.size();
      for (const auto& e : last.events) std::cout << " [" << e.type << " " << e.domain << " " << e.detail << "]";
      std::cout << "\n";
    }
  }
  check(merged, "domains whose laws coincide merge back");
  check(last.domains.size() <= before + 2, "the subdivision stays bounded after the change (" +
                                              std::to_string(before) + " -> " + std::to_string(last.domains.size()) + ")");
  check(last.routedRmse[0] < 0.02, "prequential accuracy recovers after the law change (RMSE " +
                                       std::to_string(last.routedRmse[0]) + ")");

  // A drifting coefficient: the regime-1 law shifts steadily with time.
  // Ablation on identical data (three seeds): with and without the tendency predictor.
  auto driftRun = [&](bool tendency, std::uint64_t seed, bool* selected) {
    auto o = baseOptions();
    o.tendencyPredictor = tendency;
    DomainLearner learner(o);
    Rng r{seed};
    double sq = 0.0;
    for (int c = 0; c < 80; ++c) {
      last = learner.update(makeBatch(r, 400, c, 0.05 * c));
      for (const auto& e : last.events) *selected |= e.type == "model" && e.detail.find("ridge+trend") != std::string::npos;
      if (c >= 20) sq += last.routedRmse[0] * last.routedRmse[0];
    }
    return std::sqrt(sq / 60.0);
  };
  bool withSelected = false, withoutSelected = false;
  double with = 0.0, without = 0.0;
  for (std::uint64_t seed : {31u, 32u, 33u}) {
    without += driftRun(false, seed, &withoutSelected) / 3.0;
    with += driftRun(true, seed, &withSelected) / 3.0;
  }
  check(withSelected && !withoutSelected, "a steadily drifting law selects the ridge+trend predictor (bias tendency)");
  check(with < 0.95 * without, "the tendency predictor lowers prequential error under drift (" +
                                   std::to_string(without) + " -> " + std::to_string(with) + ", 3 seeds)");
  bool trend = false;
  for (const auto& d : last.domains) {
    for (const auto& e : d.tendencies) {
      if (e.series == "target:y" && e.significant && e.slope > 0.0 && d.featureMin.size() == 2 &&
          d.featureMin[0] >= 0.35 && d.featureMax[1] <= 0.55) {
        trend = true;
      }
    }
  }
  check(trend, "the drifting regime reports a significant positive target tendency");
}

void deterministic() {
  DomainLearner a(baseOptions()), b(baseOptions());
  Rng ra{3}, rb{3};
  DomainLearnerResult x, y;
  for (int c = 0; c < 12; ++c) {
    x = a.update(makeBatch(ra, 200, c));
    y = b.update(makeBatch(rb, 200, c));
  }
  check(x.elementDomains == y.elementDomains && a.exportState() == b.exportState(),
        "identical inputs and seed give identical learners");
}

void residualNetwork() {
  auto o = baseOptions();
  o.capacity.basisDegree = 1;
  o.capacity.residualHidden = 16;
  o.capacity.residualSteps = 40;
  o.capacity.maxDomains = 1;  // one domain: the network must model the curvature
  DomainLearner learner(o);
  Rng rng{17};
  DomainLearnerResult last;
  bool switched = false;
  for (int c = 0; c < 40; ++c) {
    DomainLearnerBatch batch;
    batch.time = c;
    batch.count = 300;
    for (int i = 0; i < 300; ++i) {
      const double a = rng.uniform() * 2.0 - 1.0, b = rng.uniform() * 2.0 - 1.0;
      batch.features.insert(batch.features.end(), {a, b});
      batch.targets.push_back(std::sin(3.0 * a) + b * b);
    }
    last = learner.update(batch);
    for (const auto& e : last.events) switched |= e.type == "model" && e.detail == "inside:ridge+mlp";
  }
  check(switched && last.domains.at(0).model.rfind("ridge+mlp", 0) == 0,
        "the online LibTorch residual network is selected when it predicts better");
  check(last.routedRmse[0] < 0.7 * last.pooledRmse[0],
        "residual network beats the affine pooled baseline prequentially (" +
            std::to_string(last.routedRmse[0]) + " vs " + std::to_string(last.pooledRmse[0]) + ")");
  const auto reloaded = DomainLearner::fromState(learner.exportState(), true).exportState();
  check(reloaded.at("leaves") == learner.exportState().at("leaves"), "residual networks round-trip");
}

void stationaryReservoir() {
  auto sample = [](double forgetting) {
    auto o = baseOptions();
    o.forgetting = forgetting;
    o.capacity.bufferRows = 512;
    DomainLearner learner(o);
    Rng rng{41};
    for (int c = 0; c < 50; ++c) learner.update(makeBatch(rng, 200, c, 0.0, true));
    const auto state = learner.exportState(true);
    long lo = 1 << 30, hi = 0;
    std::size_t rows = 0;
    for (const auto& leaf : state.at("leaves")) {
      for (long call : leaf.at("rows").at("call").get<std::vector<long>>()) {
        lo = std::min(lo, call);
        hi = std::max(hi, call);
        ++rows;
      }
    }
    // Continue from the exported rows: the reservoir keeps its sampling rate.
    auto resumed = DomainLearner::fromState(state, false);
    Rng more{43};
    resumed.update(makeBatch(more, 200, 50.0, 0.0, true));
    return std::make_pair(lo, rows);
  };
  const auto stationary = sample(1.0);
  const auto forgetting = sample(0.97);
  check(stationary.first <= 5 && stationary.second == 512,
        "a stationary learner keeps a uniform reservoir of all calls (oldest call " +
            std::to_string(stationary.first) + ")");
  check(forgetting.first >= 40, "a forgetting learner keeps recent rows (oldest call " +
                                    std::to_string(forgetting.first) + ")");
}

void capacity() {
  ComputeBudget small;
  small.hardwareThreads = 2;
  small.gflops = 0.2;
  small.memoryBytes = 2e9;
  ComputeBudget large;
  large.hardwareThreads = 16;
  large.gflops = 80.0;
  large.memoryBytes = 64e9;
  const auto a = learnerCapacity(small, 4, 2);
  const auto b = learnerCapacity(large, 4, 2);
  check(a.basisDegree == 1 && b.basisDegree == 2, "basis degree follows throughput");
  check(b.maxDomains * b.bufferRows > a.maxDomains * a.bufferRows, "capacity grows with the machine");
  check(a.residualHidden == 0 && b.residualHidden > 0, "residual networks only with spare throughput");
  const auto round = ComputeBudget::fromJson(large.toJson());
  check(round.gflops == large.gflops && round.hardwareThreads == 16, "budget round-trips through JSON");
  const auto& host = hostComputeBudget();
  check(host.hardwareThreads >= 1 && host.gflops >= 0.0, "host budget probed (" +
                                                              host.toJson().dump() + ")");
}

// Block-wise density discovery beyond the former 2,048-row cap.
void largeDensityPopulation() {
  DomainDiscoveryRequest request;
  request.featureCount = 2;
  request.method = DomainDiscoveryMethod::Density;
  request.minElements = 16;
  Rng rng{91};
  const std::size_t perBlob = 3000;
  for (int blob = 0; blob < 2; ++blob) {
    for (std::size_t i = 0; i < perBlob; ++i) {
      const double angle = 6.283185307179586 * rng.uniform();
      const double radius = std::sqrt(rng.uniform());
      request.values.push_back(blob * 4.0 + radius * std::cos(angle));
      request.values.push_back(radius * std::sin(angle));
    }
  }
  const auto result = discoverDomains(request);
  if (std::getenv("TRECH_DEBUG_LEARNER")) {
    for (const auto& g : result.groups) std::cout << "group " << g.path << " " << g.elements << "\n";
  }
  std::size_t substantial = 0;
  for (const auto& group : result.groups) substantial += group.path != "u" && group.elements >= 1000;
  // Residual rows ("u") are allowed; no substantial group may mix the blobs.
  std::map<int, std::set<int>> blobsOf;
  for (std::size_t i = 0; i < 2 * perBlob; ++i) {
    const int g = result.elementGroups[i];
    if (result.groups[static_cast<std::size_t>(g)].path != "u") blobsOf[g].insert(i < perBlob ? 0 : 1);
  }
  bool separated = blobsOf.size() == 2;
  for (const auto& [g, blobs] : blobsOf) separated = separated && blobs.size() == 1;
  check(substantial == 2 && separated,
        "density discovery separates two 3,000-row populations block-wise");
}

void invalid() {
  bool threw = false;
  try {
    DomainLearner learner(baseOptions());
    DomainLearnerBatch bad;
    bad.count = 2;
    bad.features = {1.0};
    learner.update(bad);
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  check(threw, "mismatched batches are refused");
  threw = false;
  try {
    auto state = DomainLearner(baseOptions()).exportState();
    state["nodes"] = nlohmann::json::array({{{"leaf", 5}}});
    DomainLearner::fromState(state, true);
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  check(threw, "malformed states fail closed");
}

}  // namespace

// Export a learned state (with a residual network and pooled law) and the
// engine's predictions on fresh rows for the NumPy twin (test_domain_learner.py).
int exportParity(const std::string& path) {
  auto o = baseOptions();
  o.capacity.basisDegree = 2;
  o.capacity.residualHidden = 8;
  o.capacity.residualSteps = 20;
  DomainLearner learner(o);
  Rng rng{77};
  for (int c = 0; c < 25; ++c) {
    auto batch = makeBatch(rng, 300, c);
    for (std::size_t i = 0; i < batch.count; ++i) batch.targets[i] += 0.3 * std::sin(4.0 * batch.features[2 * i]);
    learner.update(batch);
  }
  const auto state = learner.exportState();
  DomainLearner frozen = DomainLearner::fromState(state, true);
  Rng probe{78};
  DomainLearnerBatch batch;
  batch.count = 400;
  for (std::size_t i = 0; i < batch.count; ++i) {
    // Include rows beyond the unit square: extrapolation paths and clamps.
    batch.features.push_back(rng.uniform() * 1.6 - 0.3);
    batch.features.push_back(probe.uniform() * 1.6 - 0.3);
  }
  const auto result = frozen.update(batch);
  nlohmann::json out = {{"state", state}, {"features", batch.features}, {"predictions", result.predictions},
                        {"domains", result.predictionDomains}};
  std::ofstream(path) << out.dump();
  std::cout << "exported " << path << "\n";
  return 0;
}

int main(int argc, char** argv) {
  if (argc == 3 && std::string(argv[1]) == "--export") return exportParity(argv[2]);
  regimesEmerge();
  singleLawStaysWhole();
  driftAndMerge();
  deterministic();
  residualNetwork();
  stationaryReservoir();
  largeDensityPopulation();
  capacity();
  invalid();
  if (failures) {
    std::cerr << failures << " failure(s)\n";
    return 1;
  }
  std::cout << "all domain learner checks passed\n";
  return 0;
}
