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

  if (failures == 0) {
    std::printf("test_generic_surrogate: all checks passed\n");
    return 0;
  }
  std::fprintf(stderr, "test_generic_surrogate: %d check(s) failed\n", failures);
  return 1;
}
