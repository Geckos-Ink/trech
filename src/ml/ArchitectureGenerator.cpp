#include "trech/ml/ArchitectureGenerator.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <unordered_set>

#include "trech/core/Provenance.hpp"
#include "trech/core/Trace.hpp"
#include "trech/js/DeterministicMath.h"
#include "trech/ml/GenericSurrogate.hpp"

#ifndef _WIN32
#include <fcntl.h>
#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
extern char** environ;
#endif

#ifndef TRECH_DEFAULT_PYTHON
#define TRECH_DEFAULT_PYTHON "python3"
#endif
#ifndef TRECH_REPOSITORY_ROOT
#define TRECH_REPOSITORY_ROOT "."
#endif

namespace fs = std::filesystem;

using nlohmann::json;

namespace trech::ml {
namespace {

constexpr const char* kJobSchema = "trech_arch_job_v1";
constexpr const char* kRequestSchema = "trech_arch_request_v1";
constexpr const char* kResultSchema = "trech_arch_result_v1";
constexpr const char* kOutcomeSchema = "trech_arch_outcome_v1";

[[noreturn]] void fail(const std::string& what) { throw std::invalid_argument("architecture job: " + what); }

std::string readFile(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::runtime_error("cannot read " + path);
  return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}

void writeFile(const std::string& path, const std::string& bytes) {
  const std::string tmp = path + ".tmp";
  {
    std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot write " + tmp);
    out << bytes;
    if (!out) throw std::runtime_error("cannot write " + tmp);
  }
  fs::rename(tmp, path);
}

ArchTable parseTable(const json& spec, const std::vector<std::string>& inputs,
                     const std::vector<std::string>& outputs, const std::string& baseDir,
                     const std::string& label) {
  ArchTable table;
  std::vector<json> rows;
  if (spec.is_string()) {
    fs::path path(spec.get<std::string>());
    if (path.is_relative()) path = fs::path(baseDir) / path;
    table.source = path.lexically_normal().string();
    std::istringstream lines(readFile(table.source));
    std::string line;
    while (std::getline(lines, line)) {
      if (line.find_first_not_of(" \t\r") == std::string::npos) continue;
      rows.push_back(json::parse(line));
    }
  } else if (spec.is_array()) {
    table.source = "inline";
    rows.assign(spec.begin(), spec.end());
  } else {
    fail(label + " must be a JSON-lines path or an array of row objects");
  }
  auto column = [&](const json& row, const std::string& name, std::size_t index) {
    if (!row.is_object() || !row.contains(name) || !row.at(name).is_number())
      fail(label + " row " + std::to_string(index) + " lacks numeric '" + name + "'");
    const double v = row.at(name).get<double>();
    if (!std::isfinite(v)) fail(label + " row " + std::to_string(index) + " has non-finite '" + name + "'");
    return v;
  };
  for (std::size_t r = 0; r < rows.size(); ++r) {
    std::vector<double> x, y;
    for (const auto& name : inputs) x.push_back(column(rows[r], name, r));
    for (const auto& name : outputs) y.push_back(column(rows[r], name, r));
    table.x.push_back(std::move(x));
    table.y.push_back(std::move(y));
  }
  return table;
}

std::vector<std::string> names(const json& j, const char* key) {
  if (!j.contains(key) || !j.at(key).is_array() || j.at(key).empty())
    fail(std::string(key) + " must be a non-empty list of names");
  std::vector<std::string> out;
  std::unordered_set<std::string> seen;
  for (const auto& n : j.at(key)) {
    if (!n.is_string() || n.get<std::string>().empty() || !seen.insert(n.get<std::string>()).second)
      fail(std::string(key) + " must hold unique non-empty strings");
    out.push_back(n.get<std::string>());
  }
  return out;
}

// splitmix64: a portable, specified generator (std:: distributions are not).
struct SplitMix {
  std::uint64_t state;
  std::uint64_t next() {
    std::uint64_t z = (state += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
  }
  double uniform() { return static_cast<double>(next() >> 11) * (1.0 / 9007199254740992.0); }
};

std::uint64_t fnv1a(const std::string& text) {
  std::uint64_t h = 1469598103934665603ull;
  for (unsigned char c : text) {
    h ^= c;
    h *= 1099511628211ull;
  }
  return h;
}

void standardize(const std::vector<std::vector<double>>& a, std::vector<double>* mean,
                 std::vector<double>* stdv) {
  const std::size_t n = a.size(), d = a.empty() ? 0 : a[0].size();
  mean->assign(d, 0.0);
  stdv->assign(d, 0.0);
  for (const auto& row : a)
    for (std::size_t j = 0; j < d; ++j) (*mean)[j] += row[j];
  for (std::size_t j = 0; j < d; ++j) (*mean)[j] /= static_cast<double>(n);
  for (const auto& row : a)
    for (std::size_t j = 0; j < d; ++j) (*stdv)[j] += (row[j] - (*mean)[j]) * (row[j] - (*mean)[j]);
  for (std::size_t j = 0; j < d; ++j) {
    const double s = std::sqrt((*stdv)[j] / static_cast<double>(n));
    (*stdv)[j] = s < 1e-9 ? 1.0 : s;  // the Python trainers' rule
  }
}

double activate(const std::string& fn, double z) {
  if (fn == "silu") return z / (1.0 + trech_dmath_exp(-z));
  if (fn == "tanh") return trech_dmath_tanh(z);
  return z;
}

double activateGrad(const std::string& fn, double z, double a) {
  if (fn == "silu") {
    const double s = 1.0 / (1.0 + trech_dmath_exp(-z));
    return s * (1.0 + z * (1.0 - s));
  }
  if (fn == "tanh") return 1.0 - a * a;
  return 1.0;
}

long long denseParams(int nIn, const std::vector<int>& widths, int nOut) {
  long long p = 0;
  int prev = nIn;
  for (int w : widths) {
    p += static_cast<long long>(prev + 1) * w;
    prev = w;
  }
  return p + static_cast<long long>(prev + 1) * nOut;
}

// Forward pass on a standardized row; keeps pre-activations/activations when asked.
void forward(const std::vector<DenseLayer>& layers, const std::vector<double>& x,
             std::vector<std::vector<double>>* zs, std::vector<std::vector<double>>* as) {
  as->assign(layers.size() + 1, {});
  zs->assign(layers.size(), {});
  (*as)[0] = x;
  for (std::size_t l = 0; l < layers.size(); ++l) {
    const auto& layer = layers[l];
    const auto& in = (*as)[l];
    auto& z = (*zs)[l];
    auto& a = (*as)[l + 1];
    z.assign(layer.bias.size(), 0.0);
    a.assign(layer.bias.size(), 0.0);
    for (std::size_t o = 0; o < layer.bias.size(); ++o) {
      double sum = layer.bias[o];
      for (std::size_t i = 0; i < in.size(); ++i) sum += layer.weights[o][i] * in[i];
      z[o] = sum;
      a[o] = activate(layer.activation, sum);
    }
  }
}

double tableLoss(const std::vector<DenseLayer>& layers, const std::vector<std::vector<double>>& xs,
                 const std::vector<std::vector<double>>& ys) {
  std::vector<std::vector<double>> zs, as;
  double sum = 0.0;
  std::size_t count = 0;
  for (std::size_t r = 0; r < xs.size(); ++r) {
    forward(layers, xs[r], &zs, &as);
    for (std::size_t o = 0; o < ys[r].size(); ++o) {
      const double d = as.back()[o] - ys[r][o];
      sum += d * d;
      ++count;
    }
  }
  return count ? sum / static_cast<double>(count) : std::numeric_limits<double>::infinity();
}

std::vector<std::vector<double>> standardized(const std::vector<std::vector<double>>& a,
                                              const std::vector<double>& mean,
                                              const std::vector<double>& stdv) {
  auto out = a;
  for (auto& row : out)
    for (std::size_t j = 0; j < row.size(); ++j) row[j] = (row[j] - mean[j]) / stdv[j];
  return out;
}

double selectionScore(double loss, long long params, double sizeCost) {
  if (!std::isfinite(loss)) return std::numeric_limits<double>::infinity();
  return std::log(std::max(loss, 1e-12)) + sizeCost * std::log(static_cast<double>(std::max(1LL, params)));
}

json metricsJson(const std::vector<std::string>& outputs, const std::vector<std::vector<double>>& truth,
                 const std::vector<std::vector<double>>& pred) {
  json r2 = json::object(), mae = json::object(), rmse = json::object();
  double r2min = std::numeric_limits<double>::infinity();
  const std::size_t n = truth.size();
  for (std::size_t o = 0; o < outputs.size(); ++o) {
    double mean = 0.0;
    for (std::size_t r = 0; r < n; ++r) mean += truth[r][o];
    mean /= static_cast<double>(n);
    double ssRes = 0.0, ssTot = 0.0, abs = 0.0;
    for (std::size_t r = 0; r < n; ++r) {
      const double d = pred[r][o] - truth[r][o];
      ssRes += d * d;
      abs += std::fabs(d);
      ssTot += (truth[r][o] - mean) * (truth[r][o] - mean);
    }
    const double value = ssTot > 0 ? 1.0 - ssRes / ssTot : 0.0;
    r2[outputs[o]] = value;
    mae[outputs[o]] = abs / static_cast<double>(n);
    rmse[outputs[o]] = std::sqrt(ssRes / static_cast<double>(n));
    r2min = std::min(r2min, value);
  }
  return {{"r2_min", r2min}, {"n", n}, {"r2", r2}, {"mae", mae}, {"rmse", rmse}};
}

json inputDomain(const ArchitectureJob& job, const std::vector<double>& xMean,
                 const std::vector<double>& xStd) {
  const int bins = 8;
  const std::size_t d = job.inputs.size();
  std::vector<double> radius(d, 0.0), lo(d, std::numeric_limits<double>::infinity()),
      hi(d, -std::numeric_limits<double>::infinity());
  for (const auto& row : job.train.x)
    for (std::size_t j = 0; j < d; ++j) {
      radius[j] = std::max(radius[j], std::fabs((row[j] - xMean[j]) / xStd[j]));
      lo[j] = std::min(lo[j], row[j]);
      hi[j] = std::max(hi[j], row[j]);
    }
  json counts = json::array();
  for (std::size_t j = 0; j < d; ++j) {
    std::vector<long long> c(bins, 0);
    for (const auto& row : job.train.x) {
      int b = 0;
      if (hi[j] > lo[j]) {
        b = row[j] >= hi[j] ? bins - 1
                            : static_cast<int>(std::floor((row[j] - lo[j]) / (hi[j] - lo[j]) * bins));
        b = std::min(bins - 1, std::max(0, b));
      }
      ++c[b];
    }
    counts.push_back(c);
  }
  return {{"standardized_radius", radius}, {"input_min", lo}, {"input_max", hi},
          {"n_train_rows", job.train.rows()}, {"occupancy", {{"bins", bins}, {"counts", counts}}}};
}

// Re-score any loadable model on the selection split, in training-standardized units.
bool rescore(const GenericSurrogate& model, const ArchitectureJob& job, const std::vector<double>& yMean,
             const std::vector<double>& yStd, double* loss, std::vector<std::vector<double>>* testPred) {
  double sum = 0.0;
  std::size_t count = 0;
  std::vector<double> out;
  for (std::size_t r = 0; r < job.selection.rows(); ++r) {
    if (!model.predictVector(job.selection.x[r], &out) || out.size() != job.outputs.size()) return false;
    for (std::size_t o = 0; o < out.size(); ++o) {
      const double d = (out[o] - job.selection.y[r][o]) / yStd[o];
      sum += d * d;
      ++count;
    }
  }
  *loss = sum / static_cast<double>(count);
  testPred->clear();
  for (std::size_t r = 0; r < job.test.rows(); ++r) {
    if (!model.predictVector(job.test.x[r], &out)) return false;
    testPred->push_back(out);
  }
  (void)yMean;
  return std::isfinite(*loss);
}

bool sameNames(const GenericSurrogate& model, const ArchitectureJob& job) {
  return model.inputNames() == job.inputs && model.outputNames() == job.outputs;
}

}  // namespace

// ----------------------------------------------------------------------------- job
ArchitectureJob parseArchitectureJob(const json& j, const std::string& baseDir) {
  if (!j.is_object() || j.value("schema", std::string()) != kJobSchema)
    fail(std::string("schema must be ") + kJobSchema);
  ArchitectureJob job;
  job.name = j.value("name", std::string());
  if (job.name.empty() || job.name.find_first_of("/\\") != std::string::npos || job.name[0] == '.')
    fail("name must be a plain non-empty file stem");
  job.inputs = names(j, "inputs");
  job.outputs = names(j, "outputs");
  for (const auto& n : job.outputs)
    if (std::find(job.inputs.begin(), job.inputs.end(), n) != job.inputs.end())
      fail("'" + n + "' is both an input and an output");
  if (!j.contains("data") || !j.at("data").is_object()) fail("data must name train/selection tables");
  const auto& data = j.at("data");
  if (!data.contains("train") || !data.contains("selection")) fail("data needs train and selection");
  job.train = parseTable(data.at("train"), job.inputs, job.outputs, baseDir, "train");
  job.selection = parseTable(data.at("selection"), job.inputs, job.outputs, baseDir, "selection");
  if (data.contains("test")) job.test = parseTable(data.at("test"), job.inputs, job.outputs, baseDir, "test");
  if (job.train.rows() < 2 || job.selection.rows() < 2) fail("train and selection need two or more rows each");
  if (!job.train.source.empty() && job.train.source != "inline" &&
      (job.train.source == job.selection.source || job.train.source == job.test.source ||
       (!job.test.source.empty() && job.selection.source == job.test.source)))
    fail("train, selection and test must come from different tables");
  job.generator = j.value("generator", std::string("evolvo"));
  if (job.generator != "evolvo" && job.generator != "classic")
    fail("generator must be evolvo or classic (there is no automatic fallback)");
  job.seed = j.value("seed", static_cast<std::uint64_t>(0));
  const json budget = j.value("budget", json::object());
  auto positive = [&](const char* key, int fallback) {
    const int v = budget.value(key, fallback);
    if (v < 1) fail(std::string("budget.") + key + " must be positive");
    return v;
  };
  job.maxParams = positive("max_params", job.maxParams);
  job.maxRows = positive("max_rows", job.maxRows);
  job.maxEpochs = positive("max_epochs", job.maxEpochs);
  job.generations = positive("generations", job.generations);
  job.population = positive("population", job.population);
  job.patience = positive("patience", job.patience);
  job.maxEvaluations = budget.value("max_evaluations", 0);
  job.timeBudgetSeconds = budget.value("time_budget_s", 0.0);
  job.workerTimeoutSeconds = budget.value("worker_timeout_s", job.workerTimeoutSeconds);
  if (job.population < 2) fail("budget.population must be at least 2");
  if (job.maxEvaluations < 0 || !(job.timeBudgetSeconds >= 0) || !(job.workerTimeoutSeconds > 0))
    fail("budget limits must be non-negative (worker timeout positive)");
  job.sizeCost = j.value("size_cost", job.sizeCost);
  job.learningRate = j.value("lr", job.learningRate);
  if (!(job.sizeCost >= 0) || !std::isfinite(job.sizeCost) || !(job.learningRate > 0))
    fail("size_cost must be finite and non-negative, lr positive");
  if (j.contains("ops")) job.ops = names(j, "ops");
  job.knowledgePath = j.value("knowledge", std::string());
  if (!job.knowledgePath.empty() && fs::path(job.knowledgePath).is_relative())
    job.knowledgePath = (fs::path(baseDir) / job.knowledgePath).lexically_normal().string();
  job.python = j.value("python", std::string());
  if (j.contains("require_engine_native"))
    fail("require_engine_native was removed: LibTorch is required, so every evolved model loads");
  if (j.contains("worker")) {
    const auto& w = j.at("worker");
    job.workerModule = w.value("module", job.workerModule);
    job.workerPath = w.value("path", std::string());
    if (!job.workerPath.empty() && fs::path(job.workerPath).is_relative())
      job.workerPath = (fs::path(baseDir) / job.workerPath).lexically_normal().string();
  }
  return job;
}

ArchitectureJob loadArchitectureJob(const std::string& path) {
  json j;
  try {
    j = json::parse(readFile(path));
  } catch (const json::exception& e) {
    fail(path + ": " + e.what());
  }
  auto job = parseArchitectureJob(j, fs::path(path).parent_path().string());
  job.jobPath = path;
  return job;
}

// ----------------------------------------------------------------------------- classic family
std::vector<int> widthLadder(int lo, int hi) {
  std::vector<int> out;
  for (int k = 0;; ++k) {
    const int w = static_cast<int>(std::lround(std::pow(2.0, k / 2.0)));
    if (w > hi) break;
    if (w >= lo && (out.empty() || out.back() != w)) out.push_back(w);
  }
  return out;
}

std::vector<ClassicStructure> classicStructures(const ArchitectureJob& job) {
  const int nIn = static_cast<int>(job.inputs.size());
  const int nOut = static_cast<int>(job.outputs.size());
  const auto ladder = widthLadder(4, 1024);
  // Width: the rung nearest 4 x the widest side (GFSL-NN's window centre).
  const int target = 4 * std::max({nIn, nOut, 4});
  std::size_t centre = 0;
  for (std::size_t i = 1; i < ladder.size(); ++i)
    if (std::abs(ladder[i] - target) < std::abs(ladder[centre] - target)) centre = i;
  // Capacity: at most 8 parameters per training target, within the budget.
  const long long cap = std::min<long long>(
      job.maxParams, std::max<long long>(64, 8LL * static_cast<long long>(job.train.rows()) * nOut));
  std::vector<ClassicStructure> out;
  ClassicStructure linear{"linear", {}, "none", denseParams(nIn, {}, nOut),
                          json{{"schema", "evolvo_arch_genome_v1"}, {"rows", json::array()}}};
  if (linear.params <= job.maxParams) out.push_back(linear);
  for (int depth : {1, 2}) {
    std::size_t k = centre;
    while (k > 0 && denseParams(nIn, std::vector<int>(depth, ladder[k]), nOut) > cap) --k;
    const std::vector<int> widths(depth, ladder[k]);
    const long long params = denseParams(nIn, widths, nOut);
    if (params > job.maxParams) continue;
    out.push_back({"mlp" + std::to_string(depth), widths, "silu", params,
                   json{{"schema", "evolvo_arch_genome_v1"},
                        {"rows", json::array({json::array({"mlp", 0, -1, json::array({ladder[k], depth, "silu"})})})}}});
  }
  if (out.empty()) fail("max_params is too small for even a linear model");
  return out;
}

// ----------------------------------------------------------------------------- native trainer
NativeFit trainClassicNative(const ArchitectureJob& job, const ClassicStructure& structure) {
  NativeFit fit;
  fit.structure = structure;
  standardize(job.train.x, &fit.xMean, &fit.xStd);
  standardize(job.train.y, &fit.yMean, &fit.yStd);
  const auto xs = standardized(job.train.x, fit.xMean, fit.xStd);
  const auto ys = standardized(job.train.y, fit.yMean, fit.yStd);
  const auto xv = standardized(job.selection.x, fit.xMean, fit.xStd);
  const auto yv = standardized(job.selection.y, fit.yMean, fit.yStd);
  const std::size_t nIn = job.inputs.size(), nOut = job.outputs.size(), n = xs.size();

  SplitMix rng{job.seed ^ fnv1a(structure.name)};
  std::vector<int> sizes{static_cast<int>(nIn)};
  for (int w : structure.widths) sizes.push_back(w);
  sizes.push_back(static_cast<int>(nOut));
  auto& layers = fit.layers;
  for (std::size_t l = 0; l + 1 < sizes.size(); ++l) {
    DenseLayer layer;
    const double bound = std::sqrt(6.0 / (sizes[l] + sizes[l + 1]));
    layer.weights.assign(sizes[l + 1], std::vector<double>(sizes[l], 0.0));
    for (auto& row : layer.weights)
      for (auto& w : row) w = (2.0 * rng.uniform() - 1.0) * bound;
    layer.bias.assign(sizes[l + 1], 0.0);
    layer.activation = l + 2 < sizes.size() ? structure.activation : "none";
    layers.push_back(std::move(layer));
  }
  // Adam state mirrors the parameter shapes.
  auto zeroLike = [&]() {
    std::vector<DenseLayer> z = layers;
    for (auto& layer : z) {
      for (auto& row : layer.weights) std::fill(row.begin(), row.end(), 0.0);
      std::fill(layer.bias.begin(), layer.bias.end(), 0.0);
    }
    return z;
  };
  auto m = zeroLike(), v = zeroLike(), g = zeroLike();
  const double beta1 = 0.9, beta2 = 0.999, eps = 1e-8, lr = job.learningRate;
  const int minEpochs = 5, patience = 25;
  const double relTol = 1e-3;
  double best = std::numeric_limits<double>::infinity();
  // Progress is measured from the best loss when the last improvement was counted (Evolvo's
  // PlateauStopper rule), so slow steady gains below relTol per epoch still add up.
  double anchor = std::numeric_limits<double>::infinity();
  int lastImprovement = -1;
  std::vector<DenseLayer> bestLayers = layers;
  std::vector<std::vector<double>> zs, as;
  std::vector<std::vector<double>> deltas(layers.size());
  for (int epoch = 0;; ++epoch) {
    g = zeroLike();
    const double scale = 2.0 / static_cast<double>(n * nOut);
    for (std::size_t r = 0; r < n; ++r) {
      forward(layers, xs[r], &zs, &as);
      for (std::size_t l = layers.size(); l-- > 0;) {
        auto& delta = deltas[l];
        delta.assign(layers[l].bias.size(), 0.0);
        for (std::size_t o = 0; o < delta.size(); ++o) {
          double upstream;
          if (l + 1 == layers.size()) {
            upstream = scale * (as[l + 1][o] - ys[r][o]);
          } else {
            upstream = 0.0;
            for (std::size_t k = 0; k < deltas[l + 1].size(); ++k)
              upstream += deltas[l + 1][k] * layers[l + 1].weights[k][o];
          }
          delta[o] = upstream * activateGrad(layers[l].activation, zs[l][o], as[l + 1][o]);
        }
      }
      for (std::size_t l = 0; l < layers.size(); ++l)
        for (std::size_t o = 0; o < deltas[l].size(); ++o) {
          g[l].bias[o] += deltas[l][o];
          for (std::size_t i = 0; i < as[l].size(); ++i) g[l].weights[o][i] += deltas[l][o] * as[l][i];
        }
    }
    const double t = epoch + 1.0;
    const double c1 = 1.0 - trech_dmath_pow(beta1, t), c2 = 1.0 - trech_dmath_pow(beta2, t);
    auto step = [&](double& p, double& mm, double& vv, double grad) {
      mm = beta1 * mm + (1.0 - beta1) * grad;
      vv = beta2 * vv + (1.0 - beta2) * grad * grad;
      p -= lr * (mm / c1) / (std::sqrt(vv / c2) + eps);
    };
    for (std::size_t l = 0; l < layers.size(); ++l)
      for (std::size_t o = 0; o < layers[l].bias.size(); ++o) {
        step(layers[l].bias[o], m[l].bias[o], v[l].bias[o], g[l].bias[o]);
        for (std::size_t i = 0; i < layers[l].weights[o].size(); ++i)
          step(layers[l].weights[o][i], m[l].weights[o][i], v[l].weights[o][i], g[l].weights[o][i]);
      }
    const double loss = tableLoss(layers, xv, yv);
    fit.epochs = epoch + 1;
    if (!std::isfinite(loss)) {
      fit.stopReason = "diverged";
      break;
    }
    if (!std::isfinite(anchor) || loss < anchor - relTol * std::fabs(anchor)) {
      lastImprovement = epoch;
      anchor = loss;
    }
    if (loss < best) {
      best = loss;
      fit.bestEpoch = epoch;
      bestLayers = layers;
    }
    if (epoch + 1 >= job.maxEpochs) {
      fit.stopReason = "max_epochs";
      break;
    }
    const int wait = std::max(patience, static_cast<int>(std::ceil(0.1 * (epoch + 1))));
    if (epoch + 1 >= minEpochs && epoch - lastImprovement >= wait) {
      fit.stopReason = "plateau";
      break;
    }
  }
  layers = bestLayers;
  fit.selectionLoss = best;
  fit.score = selectionScore(best, structure.params, job.sizeCost);
  return fit;
}

std::vector<double> predictNative(const NativeFit& fit, const std::vector<double>& x) {
  std::vector<double> z(x.size());
  for (std::size_t j = 0; j < x.size(); ++j) z[j] = (x[j] - fit.xMean[j]) / fit.xStd[j];
  std::vector<std::vector<double>> zs, as;
  forward(fit.layers, z, &zs, &as);
  std::vector<double> out = as.back();
  for (std::size_t o = 0; o < out.size(); ++o) out[o] = out[o] * fit.yStd[o] + fit.yMean[o];
  return out;
}

json nativeModelJson(const ArchitectureJob& job, const NativeFit& fit) {
  json layers = json::array();
  for (const auto& layer : fit.layers)
    layers.push_back({{"weights", layer.weights}, {"bias", layer.bias}, {"activation", layer.activation}});
  json model = {
      {"model", "generic_surrogate_v1"},
      {"input_features", job.inputs},
      {"output_features", job.outputs},
      {"input_mean", fit.xMean},
      {"input_std", fit.xStd},
      {"output_mean", fit.yMean},
      {"output_std", fit.yStd},
      {"layers", layers},
      {"trained_from",
       {{"generator", "classic_native"},
        {"structure", fit.structure.name},
        {"genome", fit.structure.genome},
        {"parameter_count", fit.structure.params},
        {"selection_loss", fit.selectionLoss},
        {"selection_objective", "mean_squared_error_in_training_standardized_outputs"},
        {"epochs", fit.epochs},
        {"best_epoch", fit.bestEpoch},
        {"stop_reason", fit.stopReason},
        {"seed", job.seed},
        {"train", job.train.source},
        {"selection", job.selection.source},
        {"test", job.test.source},
        {"math", trech_dmath_id()}}},
      {"input_domain", inputDomain(job, fit.xMean, fit.xStd)},
      {"note",
       {{"description",
         "classic reference architecture trained natively by the TRECH engine; a learned "
         "prediction selected on the selection table, not a Geant4 tally"}}},
  };
  if (job.test.rows() > 0) {
    std::vector<std::vector<double>> pred;
    for (const auto& x : job.test.x) pred.push_back(predictNative(fit, x));
    model["holdout"] = metricsJson(job.outputs, job.test.y, pred);
  }
  return model;
}

// ----------------------------------------------------------------------------- Python bridge
std::string resolvePython(const ArchitectureJob& job) {
  if (!job.python.empty()) return job.python;
  if (const char* env = std::getenv("TRECH_PYTHON"); env && *env) return env;
  return TRECH_DEFAULT_PYTHON;
}

std::string resolveRepositoryRoot() {
  if (const char* env = std::getenv("TRECH_ROOT"); env && *env) return env;
  return TRECH_REPOSITORY_ROOT;
}

WorkerRun runPythonModule(const std::string& python, const std::string& module,
                          const std::vector<std::string>& args,
                          const std::vector<std::string>& pythonPath, const std::string& logPath,
                          double timeoutSeconds) {
  WorkerRun run;
  run.logPath = logPath;
#ifdef _WIN32
  (void)python;
  (void)module;
  (void)args;
  (void)pythonPath;
  (void)timeoutSeconds;
  run.error = "the Python worker bridge is POSIX-only";
  return run;
#else
  std::vector<std::string> argvStrings{python, "-m", module};
  argvStrings.insert(argvStrings.end(), args.begin(), args.end());
  std::vector<char*> argv;
  for (auto& s : argvStrings) argv.push_back(s.data());
  argv.push_back(nullptr);

  std::string joined;
  for (const auto& p : pythonPath) {
    if (p.empty()) continue;
    if (!joined.empty()) joined += ':';
    joined += p;
  }
  std::vector<std::string> envStrings;
  std::string previous;
  for (char** e = environ; e && *e; ++e) {
    const std::string entry(*e);
    if (entry.rfind("PYTHONPATH=", 0) == 0) {
      previous = entry.substr(11);
      continue;
    }
    envStrings.push_back(entry);
  }
  envStrings.push_back("PYTHONPATH=" + joined + (previous.empty() ? "" : ":" + previous));
  // While the engine traces, the worker traces at the same level into its own file (it never
  // inherits the engine's file), which is imported below with origin "python".
  const std::string childTrace = logPath + ".trace.jsonl";
  if (trace::active()) {
    envStrings.erase(std::remove_if(envStrings.begin(), envStrings.end(),
                                    [](const std::string& e) { return e.rfind("TRECH_TRACE", 0) == 0; }),
                     envStrings.end());
    for (auto& e : trace::childEnvironment(childTrace)) envStrings.push_back(std::move(e));
    std::error_code ignored;
    std::filesystem::remove(childTrace, ignored);
    trace::record(trace::Level::Info, "python", "worker start",
                  {{"python", python}, {"module", module}, {"args", args}, {"trace_file", childTrace}});
  }
  envStrings.push_back("PYTHONDONTWRITEBYTECODE=1");
  std::vector<char*> envp;
  for (auto& s : envStrings) envp.push_back(s.data());
  envp.push_back(nullptr);

  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0);
  posix_spawn_file_actions_addopen(&actions, 1, logPath.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
  posix_spawn_file_actions_adddup2(&actions, 1, 2);
  pid_t pid = 0;
  const auto started = std::chrono::steady_clock::now();
  const int rc = python.find('/') == std::string::npos
                     ? posix_spawnp(&pid, python.c_str(), &actions, nullptr, argv.data(), envp.data())
                     : posix_spawn(&pid, python.c_str(), &actions, nullptr, argv.data(), envp.data());
  posix_spawn_file_actions_destroy(&actions);
  if (rc != 0) {
    run.error = "cannot start '" + python + "': " + std::strerror(rc);
    return run;
  }
  run.started = true;
  int status = 0;
  for (;;) {
    const pid_t done = waitpid(pid, &status, WNOHANG);
    if (done == pid) break;
    const double elapsed =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    if (done < 0 || elapsed > timeoutSeconds) {
      if (done >= 0) {
        run.timedOut = true;
        kill(pid, SIGTERM);
        for (int i = 0; i < 100 && waitpid(pid, &status, WNOHANG) == 0; ++i)
          std::this_thread::sleep_for(std::chrono::milliseconds(20));
        if (waitpid(pid, &status, WNOHANG) == 0) {
          kill(pid, SIGKILL);
          waitpid(pid, &status, 0);
        }
      }
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  run.seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
  if (WIFEXITED(status)) run.exitCode = WEXITSTATUS(status);
  else if (WIFSIGNALED(status)) run.exitCode = 128 + WTERMSIG(status);
  if (run.timedOut) run.error = "worker exceeded " + std::to_string(timeoutSeconds) + " s";
  if (trace::active()) {
    const std::size_t imported = trace::importRecords(childTrace, "python");
    trace::record(trace::Level::Info, "python", "worker end",
                  {{"module", module}, {"exit_code", run.exitCode}, {"timed_out", run.timedOut},
                   {"seconds", run.seconds}, {"records_imported", imported}});
  }
  return run;
#endif
}

// ----------------------------------------------------------------------------- generator
ArchitectureOutcome ArchitectureGenerator::generate(const ArchitectureJob& job, const std::string& outputDir) {
  ArchitectureOutcome result;
  fs::create_directories(outputDir);
  const fs::path out(outputDir);
  json record = {{"schema", kOutcomeSchema},
                 {"name", job.name},
                 {"inputs", job.inputs},
                 {"outputs", job.outputs},
                 {"generator_requested", job.generator},
                 {"seed", job.seed},
                 {"size_cost", job.sizeCost},
                 {"score", "ln(selection_loss) + size_cost * ln(params)"},
                 {"rows", {{"train", job.train.rows()}, {"selection", job.selection.rows()}, {"test", job.test.rows()}}}};
  if (!job.jobPath.empty()) record["job"] = job.jobPath;

  // 1. Classic reference family (always): the fallback and the bar to beat.
  json classic = json::array();
  const NativeFit* best = nullptr;
  std::vector<NativeFit> fits;
  for (const auto& structure : classicStructures(job)) fits.push_back(trainClassicNative(job, structure));
  for (const auto& fit : fits) {
    if (trace::active()) {
      // Native C++ Adam (no LibTorch): the classic reference family the search must beat.
      trace::tally("torch.train_steps_by_learner", "arch.classic_native", fit.epochs);
      trace::record(trace::Level::Debug, "arch", "classic reference trained",
                    {{"structure", fit.structure.name}, {"widths", fit.structure.widths},
                     {"activation", fit.structure.activation}, {"params", fit.structure.params},
                     {"epochs", fit.epochs}, {"best_epoch", fit.bestEpoch}, {"stop_reason", fit.stopReason},
                     {"selection_loss", fit.selectionLoss}, {"score", fit.score},
                     {"optimizer", "adam (native C++)"}});
    }
    classic.push_back({{"structure", fit.structure.name}, {"params", fit.structure.params},
                       {"selection_loss", fit.selectionLoss}, {"score", fit.score}, {"epochs", fit.epochs},
                       {"best_epoch", fit.bestEpoch}, {"stop_reason", fit.stopReason},
                       {"genome", fit.structure.genome}});
    if (std::isfinite(fit.score) &&
        (!best || fit.score < best->score ||
         (fit.score == best->score && fit.structure.params < best->structure.params)))
      best = &fit;
  }
  if (!best) throw std::runtime_error("no classic structure trained to a finite selection loss");
  const std::string classicPath = (out / (job.name + ".classic.json")).string();
  writeFile(classicPath, nativeModelJson(job, *best).dump(2) + "\n");
  {
    GenericSurrogate check;
    double loss = 0.0;
    std::vector<std::vector<double>> pred;
    if (!check.load(classicPath) || !rescore(check, job, best->yMean, best->yStd, &loss, &pred))
      throw std::runtime_error("the engine cannot reload its own classic model: " + check.note());
    record["classic"] = {{"candidates", classic}, {"reference", best->structure.name},
                         {"model", classicPath}, {"selection_loss", loss},
                         {"params", best->structure.params}, {"score", best->score}};
  }
  const double classicScore = best->score;
  std::string generator = "classic";
  std::string modelPath = classicPath;
  std::string reason = "classic generator requested";
  bool ok = true;

  // 2. Evolvo through the Python worker, seeded with the classic family.
  json evolvo = {{"attempted", job.generator != "classic"}};
  if (job.generator != "classic") {
    const std::string root = resolveRepositoryRoot();
    const std::string python = resolvePython(job);
    const std::string requestPath = (out / (job.name + ".worker_request.json")).string();
    const std::string resultPath = (out / (job.name + ".worker_result.json")).string();
    const std::string logPath = (out / (job.name + ".worker.log")).string();
    auto rowsJson = [](const ArchTable& t) { return json{{"x", t.x}, {"y", t.y}, {"source", t.source}}; };
    json seeds = json::array();
    for (const auto& fit : fits) seeds.push_back(fit.structure.genome);
    json request = {
        {"schema", kRequestSchema},
        {"name", job.name},
        {"inputs", job.inputs},
        {"outputs", job.outputs},
        {"train", rowsJson(job.train)},
        {"selection", rowsJson(job.selection)},
        {"test", rowsJson(job.test)},
        {"seed", job.seed},
        {"budget", {{"max_params", job.maxParams}, {"max_rows", job.maxRows}, {"max_epochs", job.maxEpochs},
                    {"generations", job.generations}, {"population", job.population},
                    {"patience", job.patience}, {"max_evaluations", job.maxEvaluations},
                    {"time_budget_s", job.timeBudgetSeconds}}},
        {"size_cost", job.sizeCost},
        {"lr", job.learningRate},
        {"ops", job.ops},
        {"seeds", seeds},
        {"classic_reference", {{"structure", best->structure.name}, {"selection_loss", best->selectionLoss},
                               {"params", best->structure.params}, {"score", classicScore}}},
        {"knowledge", job.knowledgePath},
        {"out_prefix", (out / (job.name + "_evolvo")).string()},
    };
    const std::string requestBytes = request.dump() + "\n";
    writeFile(requestPath, requestBytes);
    const std::string requestSha = sha256Hex(requestBytes);
    std::error_code ignored;
    fs::remove(resultPath, ignored);
    std::vector<std::string> path{(fs::path(root) / "tools" / "torch").string(),
                                  (fs::path(root) / "thirds" / "evolvo" / "src").string()};
    if (!job.workerPath.empty()) path.insert(path.begin(), job.workerPath);
    const WorkerRun run = runPythonModule(python, job.workerModule, {"--request", requestPath, "--result", resultPath},
                                          path, logPath, job.workerTimeoutSeconds);
    evolvo.update({{"python", python}, {"module", job.workerModule}, {"request", requestPath},
                   {"request_sha256", requestSha}, {"log", logPath}, {"started", run.started},
                   {"exit_code", run.exitCode}, {"seconds", run.seconds}});
    std::string status;
    std::string error;
    json worker;
    if (!run.started) {
      status = "not_started";
      error = run.error;
    } else if (run.timedOut) {
      status = "timeout";
      error = run.error;
    } else if (!fs::exists(resultPath)) {
      status = "no_result";
      error = "worker exited " + std::to_string(run.exitCode) + " without a result (see log)";
    } else {
      try {
        worker = json::parse(readFile(resultPath));
      } catch (const std::exception& e) {
        status = "no_result";
        error = std::string("unparseable result: ") + e.what();
      }
    }
    if (status.empty()) {
      if (worker.value("schema", std::string()) != kResultSchema ||
          worker.value("request_sha256", std::string()) != requestSha) {
        status = "mismatched_result";
        error = "result schema or request_sha256 does not match this request";
      } else if (worker.value("status", std::string()) != "ok") {
        status = worker.value("status", std::string("error"));
        error = worker.value("error", std::string("worker reported failure"));
      }
    }
    if (status.empty()) {
      const json best_ = worker.value("best", json::object());
      const json exports = best_.value("exports", json::object());
      std::string candidate = exports.value("json", std::string());
      const bool native = !candidate.empty();
      if (!native) candidate = exports.value("torchscript", std::string());
      evolvo["result"] = resultPath;
      evolvo["genome"] = best_.value("genome", json());
      evolvo["describe"] = best_.value("describe", json());
      evolvo["reported_selection_loss"] = best_.value("selection_loss", json());
      evolvo["params"] = best_.value("params", json());
      evolvo["model"] = candidate;
      evolvo["engine_native"] = native;
      evolvo["search"] = worker.value("search", json());
      evolvo["overall_best"] = worker.value("overall_best", json());
      const long long params = best_.value("params", 0LL);
      GenericSurrogate model;
      double loss = 0.0;
      std::vector<std::vector<double>> pred;
      if (candidate.empty() || !fs::exists(candidate) || params < 1) {
        status = "no_model";
        error = "the result names no exported model";
      } else if (model.load(candidate) && sameNames(model, job) &&
                 rescore(model, job, best->yMean, best->yStd, &loss, &pred)) {
        // Re-scored by the engine on the same selection rows, never taken on trust.
        const double reported = best_.value("selection_loss", std::numeric_limits<double>::quiet_NaN());
        evolvo["selection_loss"] = loss;
        evolvo["scored_by"] = "engine";
        evolvo["report_agrees"] = std::fabs(loss - reported) <= 1e-3 * std::max(1.0, std::fabs(reported)) + 1e-6;
        const double score = selectionScore(loss, params, job.sizeCost);
        evolvo["score"] = score;
        if (job.test.rows() > 0) evolvo["holdout_engine"] = metricsJson(job.outputs, job.test.y, pred);
        if (score < classicScore) {
          status = "accepted";
          generator = "evolvo";
          modelPath = candidate;
          reason = "the evolved architecture beat the classic reference on the selection score";
        } else {
          // Not a fallback: Evolvo ran and its best model lost on the same rows, so the better
          // model (the reference) is the honest choice.
          status = "rejected";
          reason = "the classic reference kept: the evolved architecture did not beat it on the "
                   "selection score";
        }
      } else {
        status = "unloadable";
        error = "the engine cannot load the evolved model (" + model.note() + ")";
      }
    }
    evolvo["status"] = status;
    if (!error.empty()) evolvo["error"] = error;
    if (status != "accepted" && status != "rejected") {
      // Every Evolvo failure is an error: no silent classic model stands in for a search that
      // did not run or did not deliver.
      ok = false;
      generator = "none";
      modelPath.clear();
      reason = "evolvo " + status + (error.empty() ? "" : ": " + error);
    }
  }
  record["evolvo"] = evolvo;
  record["decision"] = {{"ok", ok}, {"generator", generator}, {"model", modelPath}, {"reason", reason}};
  result.ok = ok;
  result.generator = generator;
  result.modelPath = modelPath;
  result.reason = reason;
  result.outcomePath = (out / (job.name + ".outcome.json")).string();
  writeFile(result.outcomePath, record.dump(2) + "\n");
  result.outcome = std::move(record);
  return result;
}

}  // namespace trech::ml
