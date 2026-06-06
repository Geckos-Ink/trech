// Unit test for the LibTorch-free ridge backend of OpticsSurrogate.
// Verifies the JSON model loads, the standardised ridge evaluation matches a
// hand-computed value, abs/scat carry the "not predicted" sentinel, and the
// element-order / feature-length guards reject malformed models.

#include "trech/ml/OpticsSurrogate.hpp"

#include <array>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace {

int failures = 0;

void expect(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "FAIL: %s\n", message);
    ++failures;
  }
}

bool approx(double a, double b, double tol = 1e-5) {
  return std::abs(a - b) <= tol;
}

// Serialize a ridge model JSON with the canonical element order. weights/mean/
// std must be length kInputFeatureCount (elements + density).
std::string makeRidgeJson(const std::vector<double>& weights,
                          const std::vector<double>& mean,
                          const std::vector<double>& std_, double bias,
                          bool correctElements) {
  std::ostringstream os;
  os << "{\"model\":\"ridge_optics_n_v1\",\"elements\":[";
  const auto& elems = trech::ml::OpticsSurrogate::kCompositionElements;
  for (std::size_t i = 0; i < elems.size(); ++i) {
    // Corrupt the order when asked, to exercise the guard.
    const char* name = (!correctElements && i == 0) ? "Zz" : elems[i];
    os << (i ? "," : "") << "\"" << name << "\"";
  }
  os << "],";
  auto arr = [&](const char* key, const std::vector<double>& v) {
    os << "\"" << key << "\":[";
    for (std::size_t i = 0; i < v.size(); ++i) os << (i ? "," : "") << v[i];
    os << "]";
  };
  arr("weights", weights);
  os << ",";
  arr("mean", mean);
  os << ",";
  arr("std", std_);
  os << ",\"bias\":" << bias << "}";
  return os.str();
}

std::string writeTemp(const std::string& contents, const std::string& name) {
  std::string path = std::string(".") + "/" + name;
  std::ofstream out(path);
  out << contents;
  out.close();
  return path;
}

}  // namespace

int main() {
  const int n = trech::ml::OpticsSurrogate::kInputFeatureCount;
  expect(n == 15, "kInputFeatureCount should be 15 (14 element slots + density)");

  // Ridge: weight only on the first element (H) and on density (last slot).
  std::vector<double> weights(n, 0.0), mean(n, 0.0), std_(n, 1.0);
  weights[0] = 0.10;       // H slot
  weights[n - 1] = 0.02;   // density slot
  mean[0] = 0.0;
  mean[n - 1] = 1.0;       // density standardised around 1.0
  std_[0] = 1.0;
  std_[n - 1] = 2.0;       // density std
  const double bias = 1.40;

  const std::string good = makeRidgeJson(weights, mean, std_, bias, true);
  const std::string goodPath = writeTemp(good, "test_ridge_good.json");

  trech::ml::OpticsSurrogate surrogate;
  expect(surrogate.load(goodPath), "ridge json should load");
  expect(surrogate.loaded(), "loaded() should be true after a good load");

  // Composition: H fraction 0.5, density 3.0 (other slots 0).
  std::vector<float> comp(n, 0.0f);
  comp[0] = 0.5f;
  comp[n - 1] = 3.0f;
  std::array<float, 3> out{};
  expect(surrogate.predict(comp, &out), "predict should succeed");

  // Hand-computed: n = bias + w_H*(0.5-0)/1 + w_rho*(3-1)/2
  //                  = 1.40 + 0.10*0.5 + 0.02*1.0 = 1.47
  expect(approx(out[0], 1.47), "ridge prediction should equal 1.47");
  expect(out[1] < 0.0f && out[2] < 0.0f,
         "abs/scat should be the negative 'not predicted' sentinel");

  // Wrong-length composition is rejected.
  std::vector<float> shortComp(n - 1, 0.0f);
  std::array<float, 3> out2{};
  expect(!surrogate.predict(shortComp, &out2),
         "predict should reject a wrong-length composition");

  // Element-order mismatch must fail to load.
  const std::string bad = makeRidgeJson(weights, mean, std_, bias, false);
  const std::string badPath = writeTemp(bad, "test_ridge_badelems.json");
  trech::ml::OpticsSurrogate surrogate2;
  expect(!surrogate2.load(badPath),
         "ridge json with a wrong element order should fail to load");
  expect(!surrogate2.loaded(), "loaded() should be false after a failed load");

  std::remove(goodPath.c_str());
  std::remove(badPath.c_str());

  if (failures == 0) {
    std::printf("test_optics_surrogate: all checks passed\n");
    return 0;
  }
  std::fprintf(stderr, "test_optics_surrogate: %d check(s) failed\n", failures);
  return 1;
}
