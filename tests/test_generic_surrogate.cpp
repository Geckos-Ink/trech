// Unit test for GenericSurrogate: the scenario-agnostic named-IO surrogate.
// Covers the general feed-forward JSON schema (with hidden layer + activation
// + output destandardisation), named prediction with missing/extra inputs, and
// loading the two committed specialised schemas (ridge_optics_n_v1,
// logistic_stratifier_v1) generically.

#include "trech/ml/GenericSurrogate.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

int failures = 0;

void expect(bool cond, const char* msg) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", msg);
    ++failures;
  }
}

bool approx(double a, double b, double tol = 1e-6) {
  return std::abs(a - b) <= tol;
}

std::string writeTemp(const std::string& contents, const std::string& name) {
  const std::string path = std::string("./") + name;
  std::ofstream out(path);
  out << contents;
  out.close();
  return path;
}

}  // namespace

int main() {
  // 1) General linear model, two inputs -> one output, with input
  //    standardisation and output destandardisation.
  //    Standardised: xs = [(a-1)/2, (b-0)/1]; raw = 2*xs0 + 3*xs1 + 0.5;
  //    out = raw*10 + 100.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["a", "b"],
      "output_features": ["y"],
      "input_mean": [1.0, 0.0],
      "input_std": [2.0, 1.0],
      "output_mean": [100.0],
      "output_std": [10.0],
      "layers": [
        {"weights": [[2.0, 3.0]], "bias": [0.5], "activation": "none"}
      ]
    })";
    const std::string path = writeTemp(json, "test_generic_linear.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "general linear model should load");
    expect(m.loaded(), "loaded() true after general load");
    expect(m.inputNames().size() == 2 && m.outputNames().size() == 1,
           "general model input/output names sized right");

    // a=3,b=2: xs=[(3-1)/2,(2-0)/1]=[1,2]; raw=2*1+3*2+0.5=8.5; out=8.5*10+100
    std::unordered_map<std::string, double> in{{"a", 3.0}, {"b", 2.0},
                                               {"ignored", 9.0}};
    std::unordered_map<std::string, double> out;
    expect(m.predict(in, &out), "general predict should succeed");
    expect(out.count("y") == 1, "general predict emits named output y");
    expect(approx(out["y"], 185.0), "general linear predict == 185.0");

    // Missing input 'b' defaults to 0: xs=[1,0]; raw=2*1+3*0+0.5=2.5;
    // out=2.5*10+100=125.
    std::unordered_map<std::string, double> inMissing{{"a", 3.0}};
    std::unordered_map<std::string, double> outMissing;
    expect(m.predict(inMissing, &outMissing), "predict with missing input ok");
    expect(approx(outMissing["y"], 125.0),
           "missing input defaults to zero (== 125.0)");
    std::remove(path.c_str());
  }

  // 2) Two-layer model with sigmoid output in [0,1].
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["p"],
      "layers": [
        {"weights": [[1.0],[1.0]], "bias": [0.0, 0.0], "activation": "relu"},
        {"weights": [[1.0, 1.0]], "bias": [0.0], "activation": "sigmoid"}
      ]
    })";
    const std::string path = writeTemp(json, "test_generic_mlp.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "two-layer model should load");
    std::unordered_map<std::string, double> out;
    expect(m.predict({{"x", 0.0}}, &out), "mlp predict x=0 ok");
    expect(approx(out["p"], 0.5), "sigmoid(0) == 0.5");
    expect(m.predict({{"x", 10.0}}, &out), "mlp predict x=10 ok");
    // relu(10)=10 twice, sum=20, sigmoid(20) ~ 1.
    expect(out["p"] > 0.999 && out["p"] <= 1.0, "sigmoid(20) ~ 1");
    std::remove(path.c_str());
  }

  // 3) Bad model: final layer width != output_features must fail to load.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["a", "b"],
      "layers": [{"weights": [[1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_bad.json");
    trech::ml::GenericSurrogate m;
    expect(!m.load(path), "mismatched output width should fail to load");
    expect(!m.loaded(), "loaded() false after failed load");
    std::remove(path.c_str());
  }

  // 4) Committed ridge_optics_n_v1 schema loads generically -> refractive_index.
  {
    const char* candidates[] = {
        "data/optics_surrogate_ridge.json",
        "../../data/optics_surrogate_ridge.json",
        "../../../data/optics_surrogate_ridge.json",
        "../../../../data/optics_surrogate_ridge.json",
    };
    std::string path;
    for (const char* c : candidates) {
      std::ifstream f(c);
      if (f.good()) {
        path = c;
        break;
      }
    }
    if (!path.empty()) {
      trech::ml::GenericSurrogate m;
      expect(m.load(path), "committed ridge model should load generically");
      expect(m.modelId() == "ridge_optics_n_v1", "ridge modelId preserved");
      expect(m.outputNames().size() == 1 &&
                 m.outputNames()[0] == "refractive_index",
             "ridge output named refractive_index");
      // Water: H 0.1119, O 0.8881, density 1.0 -> n around 1.3.
      std::unordered_map<std::string, double> out;
      expect(m.predict({{"H", 0.1119}, {"O", 0.8881}, {"density_gcm3", 1.0}},
                       &out),
             "ridge generic predict for water ok");
      expect(out["refractive_index"] > 1.1 && out["refractive_index"] < 1.6,
             "ridge water n in a physical band");
    } else {
      std::fprintf(stderr,
                   "note: skipping committed-ridge check (not found at %s)\n",
                   path.c_str());
    }
  }

  // 5) Coverage with a HEURISTIC domain (model carries no input_domain block):
  //    an input beyond kDefaultStandardizedDomainRadius (3 sigma) is flagged
  //    out-of-domain, domainMeasured is false.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["y"],
      "input_mean": [0.0],
      "input_std": [1.0],
      "layers": [{"weights": [[1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_cov_heur.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "heuristic-domain model should load");
    expect(!m.domainMeasured(), "no input_domain block -> domain not measured");

    const auto in = m.coverage({{"x", 1.0}});  // z=1 < 3 -> in
    expect(in.inDomain, "x=1 (z=1) is in the heuristic domain");
    expect(!in.domainMeasured, "coverage reports heuristic (not measured)");
    expect(approx(in.maxStandardizedDeviation, 1.0), "max |z| == 1");
    expect(approx(in.extrapolation, 0.0), "no extrapolation in-domain");
    expect(in.outOfDomainInputs.empty(), "no out-of-domain inputs");

    const auto out = m.coverage({{"x", 5.0}});  // z=5 > 3 -> out by 2
    expect(!out.inDomain, "x=5 (z=5) is out of the heuristic domain");
    expect(approx(out.extrapolation, 2.0), "extrapolation == |z|-radius == 2");
    expect(out.outOfDomainInputs.size() == 1 &&
               out.outOfDomainInputs[0] == "x",
           "input x recorded out-of-domain");
    std::remove(path.c_str());
  }

  // 6) Coverage with a MEASURED domain (input_domain.standardized_radius): the
  //    per-feature trained hull edge overrides the heuristic; domainMeasured
  //    is true, and the tighter radius flags a point the heuristic would pass.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["y"],
      "input_mean": [0.0],
      "input_std": [1.0],
      "input_domain": {"standardized_radius": [2.0]},
      "layers": [{"weights": [[1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_cov_meas.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "measured-domain model should load");
    expect(m.domainMeasured(), "input_domain block -> domain measured");

    const auto in = m.coverage({{"x", 1.5}});  // z=1.5 < 2 -> in
    expect(in.inDomain && in.domainMeasured,
           "x=1.5 in the measured hull, reported measured");
    const auto out = m.coverage({{"x", 2.5}});  // z=2.5 > 2 -> out by 0.5
    expect(!out.inDomain, "x=2.5 outside the measured hull (heuristic 3 would pass)");
    expect(approx(out.extrapolation, 0.5), "measured extrapolation == 0.5");
    std::remove(path.c_str());
  }

  // 7) A MISSING input the model needs (far from its training mean) is honestly
  //    flagged: it defaults to 0, and 0 is out of that feature's domain.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["a", "b"],
      "output_features": ["y"],
      "input_mean": [0.0, 10.0],
      "input_std": [1.0, 1.0],
      "layers": [{"weights": [[1.0, 1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_cov_missing.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "missing-input coverage model should load");
    // b omitted -> 0; z_b = (0-10)/1 = -10 -> |z|=10 > 3.
    const auto cov = m.coverage({{"a", 0.5}});
    expect(!cov.inDomain, "a missing input far from its mean is out-of-domain");
    expect(cov.outOfDomainInputs.size() == 1 &&
               cov.outOfDomainInputs[0] == "b",
           "the missing input 'b' is the out-of-domain one");
    expect(approx(cov.extrapolation, 7.0), "extrapolation == 10 - 3 == 7");
    std::remove(path.c_str());
  }

  // 8) Carried training provenance + held-out accuracy (workstream 3 b + c):
  //    a model can carry the dimension-scale band(s) it was trained on and its
  //    held-out R2 so the cascade can flag off-band use and grade the gap.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["y"],
      "trained_scale_bands": ["meso"],
      "holdout": {"r2_min": 0.87, "n": 12},
      "layers": [{"weights": [[1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_prov.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "provenance-carrying model should load");
    expect(m.trainedScaleBands().size() == 1 &&
               m.trainedScaleBands()[0] == "meso",
           "trained_scale_bands loaded (meso)");
    expect(m.hasHoldout(), "hasHoldout true when holdout block present");
    expect(approx(m.holdoutR2Min(), 0.87), "holdoutR2Min == 0.87");
    expect(m.holdoutSamples() == 12, "holdoutSamples == 12");
    std::remove(path.c_str());
  }

  // 9) A model without those blocks reports them absent (never a fake 0 == R2):
  //    illustrative hand-authored maps carry no provenance/metrics.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["y"],
      "layers": [{"weights": [[1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_noprov.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "no-provenance model should load");
    expect(m.trainedScaleBands().empty(),
           "trained_scale_bands empty when absent (unknown)");
    expect(!m.hasHoldout(), "hasHoldout false when no holdout block");
    std::remove(path.c_str());
  }

  // 10) Starved-region signal (density INSIDE the hull): a value within the
  //     trained range but in an empty occupancy bin is flagged starved, while
  //     staying in-domain (distinct from the beyond-the-edge extrapolation flag).
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["y"],
      "input_mean": [5.0], "input_std": [3.0],
      "input_domain": {
        "standardized_radius": [2.0],
        "input_min": [0.0], "input_max": [10.0],
        "occupancy": {"bins": 4, "counts": [[5, 0, 0, 3]]}
      },
      "layers": [{"weights": [[1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_starved.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "occupancy model should load");
    expect(m.hasOccupancy(), "hasOccupancy true with an occupancy block");

    const auto dense = m.coverage({{"x", 1.0}});  // bin 0, count 5 -> populated
    expect(dense.inDomain && dense.starvedInputs.empty(),
           "x=1 sits in a populated bin (not starved)");
    const auto hole = m.coverage({{"x", 3.0}});   // bin 1, count 0 -> empty
    expect(hole.inDomain, "x=3 is in-domain (|z|<radius), not an edge extrapolation");
    expect(hole.starvedInputs.size() == 1 && hole.starvedInputs[0] == "x",
           "x=3 in an empty in-range bin is flagged starved");
    const auto dense2 = m.coverage({{"x", 8.0}});  // bin 3, count 3 -> populated
    expect(dense2.starvedInputs.empty(), "x=8 sits in a populated bin");
    std::remove(path.c_str());
  }

  if (failures == 0) {
    std::printf("test_generic_surrogate: all checks passed\n");
    return 0;
  }
  std::fprintf(stderr, "test_generic_surrogate: %d check(s) failed\n", failures);
  return 1;
}
