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

  // 10b) JOINT starved region: the hole the per-feature checks cannot see.
  //      Training covered (cold, slow) and (hot, fast) only. The point
  //      (cold, fast) is inside BOTH features' ranges and inside every occupancy
  //      bin that matters, yet no training point sits anywhere near it.
  {
    // Two clusters in standardized space: around (-1,-1) and (+1,+1).
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["temperature", "rate"],
      "output_features": ["y"],
      "input_mean": [0.0, 0.0],
      "input_std": [1.0, 1.0],
      "input_domain": {
        "standardized_radius": [1.5, 1.5],
        "joint": {
          "metric": "euclidean_standardized",
          "centers": [[-1.0, -1.0], [1.0, 1.0]],
          "radius": 0.5,
          "quantile": 0.99
        }
      },
      "layers": [{"weights": [[1.0, 1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_joint.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "joint-domain model should load");
    expect(m.hasJointDomain(), "hasJointDomain true with a joint block");

    // On a training cluster: covered.
    const auto near = m.coverage({{"temperature", -1.0}, {"rate", -1.0}});
    expect(near.jointMeasured, "coverage reports the joint check was performed");
    expect(!near.jointStarved, "a point on a training cluster is not joint-starved");
    expect(approx(near.jointDistance, 0.0), "distance to its own center is 0");

    // The hole BETWEEN the clusters: every per-feature check passes.
    const auto hole = m.coverage({{"temperature", -1.0}, {"rate", 1.0}});
    expect(hole.inDomain,
           "the off-diagonal point passes every per-feature domain check");
    expect(hole.outOfDomainInputs.empty(),
           "no single input is out of range at the joint hole");
    expect(hole.starvedInputs.empty(),
           "per-feature occupancy cannot see the joint hole either");
    expect(hole.jointStarved,
           "the joint check flags a point far from every training cluster");
    expect(approx(hole.jointDistance, 2.0),
           "joint distance is the standardized distance to the nearest cluster");
    expect(approx(hole.jointRadius, 0.5), "the trained covering radius is reported");

    // Just inside the covering radius stays clean (no false alarm next to data).
    const auto close = m.coverage({{"temperature", -1.0}, {"rate", -0.6}});
    expect(!close.jointStarved, "a point within the covering radius is not starved");
    std::remove(path.c_str());
  }

  // 10c) A model with no joint reference reports the check as NOT PERFORMED —
  //      unknown must never read as "checked and fine".
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["y"],
      "input_domain": {"standardized_radius": [2.0]},
      "layers": [{"weights": [[1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_nojoint.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "no-joint model should load");
    expect(!m.hasJointDomain(), "hasJointDomain false with no joint block");
    const auto cov = m.coverage({{"x", 0.5}});
    expect(!cov.jointMeasured, "joint check reported as not performed");
    expect(!cov.jointStarved && approx(cov.jointDistance, 0.0),
           "the unperformed joint check reports neutral values");
    std::remove(path.c_str());
  }

  // 10d) A malformed joint block (a center of the wrong width) is ignored
  //      entirely rather than half-applied.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["a", "b"],
      "output_features": ["y"],
      "input_domain": {
        "standardized_radius": [2.0, 2.0],
        "joint": {"centers": [[0.0, 0.0], [1.0]], "radius": 0.5}
      },
      "layers": [{"weights": [[1.0, 1.0]], "bias": [0.0], "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_badjoint.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "model with a malformed joint block still loads");
    expect(!m.hasJointDomain(), "a malformed joint reference is ignored, not partial");
    expect(!m.coverage({{"a", 9.0}, {"b", 9.0}}).jointMeasured,
           "no joint verdict is reported from a malformed reference");
    std::remove(path.c_str());
  }

  // 11b) Per-OUTPUT held-out accuracy: each metric block is read independently,
  //      so a model carrying r2+mae but no rmse reports exactly that, and an
  //      output missing from a block is reported absent rather than as 0.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["a", "b"],
      "holdout": {
        "r2_min": 0.5, "n": 400,
        "r2": {"a": 0.99, "b": 0.5},
        "mae": {"a": 0.01},
        "rmse": {"b": 3.5}
      },
      "layers": [{"weights": [[1.0],[1.0]], "bias": [0.0, 0.0],
                  "activation": "none"}]
    })";
    const std::string path = writeTemp(json, "test_generic_outacc.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "per-output accuracy model should load");
    expect(m.hasOutputAccuracy(), "hasOutputAccuracy true with a per-output block");

    const auto a = m.outputAccuracy(0);
    expect(a.hasR2 && approx(a.r2, 0.99), "output a carries its own R2");
    expect(a.hasMeanAbsoluteError && approx(a.meanAbsoluteError, 0.01),
           "output a carries its MAE");
    expect(!a.hasRootMeanSquaredError,
           "output a has no rmse entry -> absent, not 0");
    const auto b = m.outputAccuracy(1);
    expect(b.hasRootMeanSquaredError && approx(b.rootMeanSquaredError, 3.5),
           "output b carries its measured 1-sigma residual");
    expect(!b.hasMeanAbsoluteError, "output b has no mae entry -> absent");
    expect(!m.outputAccuracy(9).measured(),
           "an out-of-range output index reports nothing measured");
    // The model-wide summary is unchanged by the per-output split.
    expect(m.hasHoldout() && approx(m.holdoutR2Min(), 0.5),
           "model-wide r2_min stays the worst output");
    std::remove(path.c_str());
  }

  // 11c) A committed trained operator really carries the metrics (this is the
  //      data the engine hands back as a measured uncertainty, so a regression
  //      that silently drops it must fail here, not in a scenario).
  {
    const char* candidates[] = {
        "data/polyurethane_cascade/meso_reaction_operator.json",
        "../../data/polyurethane_cascade/meso_reaction_operator.json",
        "../../../data/polyurethane_cascade/meso_reaction_operator.json",
        "../../../../data/polyurethane_cascade/meso_reaction_operator.json",
    };
    std::string path;
    for (const char* c : candidates) {
      std::ifstream f(c);
      if (f.good()) { path = c; break; }
    }
    if (!path.empty()) {
      trech::ml::GenericSurrogate m;
      expect(m.load(path), "committed meso operator should load");
      expect(m.hasOutputAccuracy(),
             "committed trained operator carries per-output held-out metrics");
      bool everyOutputMeasured = true;
      bool everyOutputHasSigma = true;
      for (std::size_t o = 0; o < m.outputNames().size(); ++o) {
        const auto acc = m.outputAccuracy(o);
        if (!acc.measured()) everyOutputMeasured = false;
        if (!acc.hasRootMeanSquaredError) everyOutputHasSigma = false;
      }
      expect(everyOutputMeasured, "every trained output carries a metric");
      expect(everyOutputHasSigma,
             "every trained output carries a measured 1-sigma residual (rmse)");
    } else {
      std::fprintf(stderr,
                   "note: skipping committed-operator accuracy check "
                   "(model not found)\n");
    }
  }

  // 11) The batched inference path (predictInto + a REUSED workspace) must
  //     agree BIT-FOR-BIT with the convenience predictVector form, and a reused
  //     workspace must carry no state between calls -- an operator evaluating
  //     thousands of elements per step relies on both, and a drift here would
  //     silently change physics that the determinism contract calls reproducible.
  {
    const std::string json = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["a", "b", "c"],
      "output_features": ["y0", "y1"],
      "input_mean": [0.5, -1.0, 2.0],
      "input_std": [1.5, 0.25, 3.0],
      "output_mean": [10.0, -4.0],
      "output_std": [2.5, 0.5],
      "layers": [
        {"weights": [[0.3, -0.7, 1.1], [2.0, 0.5, -0.25], [-1.3, 0.9, 0.4],
                     [0.6, -0.2, 0.8]],
         "bias": [0.1, -0.4, 0.7, 0.2], "activation": "tanh"},
        {"weights": [[0.9, -0.5, 0.25, 1.4], [-0.75, 1.1, 0.6, -0.3]],
         "bias": [0.05, -0.15], "activation": "none"}
      ]
    })";
    const std::string path = writeTemp(json, "test_generic_batched.json");
    trech::ml::GenericSurrogate m;
    expect(m.load(path), "batched-path model should load");

    trech::ml::GenericSurrogate::Workspace shared;
    bool identical = true;
    bool sized = true;
    for (int step = 0; step < 64; ++step) {
      const double t = 0.125 * static_cast<double>(step) - 4.0;
      const std::vector<double> x{t, 0.5 * t - 1.0, 2.0 - 0.25 * t};

      std::vector<double> viaVector;
      std::vector<double> viaWorkspace(m.outputNames().size(), 0.0);
      trech::ml::GenericSurrogate::Workspace fresh;
      std::vector<double> viaFresh(m.outputNames().size(), 0.0);
      if (!m.predictVector(x, &viaVector) ||
          !m.predictInto(x.data(), x.size(), viaWorkspace.data(),
                         viaWorkspace.size(), shared) ||
          !m.predictInto(x.data(), x.size(), viaFresh.data(), viaFresh.size(),
                         fresh)) {
        sized = false;
        break;
      }
      for (std::size_t o = 0; o < viaVector.size(); ++o) {
        // Exact equality on purpose: "close enough" is not the contract.
        if (viaVector[o] != viaWorkspace[o] || viaVector[o] != viaFresh[o]) {
          identical = false;
        }
      }
    }
    expect(sized, "batched predictInto succeeds for every step");
    expect(identical,
           "predictInto (reused AND fresh workspace) == predictVector bitwise");

    // Wrong output width is refused rather than writing past the caller's
    // buffer (the batched callers size `out` from their own plan).
    std::vector<double> tooSmall(1, 0.0);
    const std::vector<double> x{0.0, 0.0, 0.0};
    expect(!m.predictInto(x.data(), x.size(), tooSmall.data(), tooSmall.size(),
                          shared),
           "predictInto refuses a mismatched output width");
    expect(!m.predictInto(x.data(), x.size() - 1, tooSmall.data(),
                          m.outputNames().size(), shared),
           "predictInto refuses a mismatched input width");

    // A workspace is shape-agnostic: reusing the one just driven by a 3->2
    // model on a different model must not leak the previous shape.
    const std::string other = R"({
      "model": "generic_surrogate_v1",
      "input_features": ["x"],
      "output_features": ["y"],
      "layers": [{"weights": [[2.0]], "bias": [1.0], "activation": "none"}]
    })";
    const std::string otherPath = writeTemp(other, "test_generic_batched2.json");
    trech::ml::GenericSurrogate small;
    expect(small.load(otherPath), "second batched model should load");
    std::vector<double> reused(1, 0.0);
    const std::vector<double> sx{3.0};
    expect(small.predictInto(sx.data(), sx.size(), reused.data(), reused.size(),
                             shared),
           "a workspace from another model shape is reusable");
    expect(approx(reused[0], 7.0), "reused workspace gives the right value");
    std::remove(path.c_str());
    std::remove(otherPath.c_str());
  }

  if (failures == 0) {
    std::printf("test_generic_surrogate: all checks passed\n");
    return 0;
  }
  std::fprintf(stderr, "test_generic_surrogate: %d check(s) failed\n", failures);
  return 1;
}
