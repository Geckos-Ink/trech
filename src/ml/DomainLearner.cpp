#include "trech/ml/DomainLearner.hpp"

#include <torch/torch.h>

#include "trech/core/Trace.hpp"
#include "trech/ml/LeastSquaresStatistics.hpp"
#include "trech/ml/MlTrace.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <chrono>
#include <cmath>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <stdexcept>
#include <utility>

namespace trech::ml {
namespace {

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

std::uint64_t splitmix(std::uint64_t& state) {
  std::uint64_t z = (state += 0x9e3779b97f4a7c15ULL);
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}

double normal(std::uint64_t& state) {
  const double u1 = (static_cast<double>(splitmix(state) >> 11) + 0.5) * 0x1.0p-53;
  const double u2 = (static_cast<double>(splitmix(state) >> 11) + 0.5) * 0x1.0p-53;
  return std::sqrt(-2.0 * std::log(u1)) * std::cos(6.283185307179586 * u2);
}

std::size_t basisSize(std::size_t d, int degree) {
  return degree >= 2 ? 1 + d + d * (d + 1) / 2 : 1 + d;
}

void basis(const double* z, std::size_t d, int degree, double* out) {
  std::size_t k = 0;
  out[k++] = 1.0;
  for (std::size_t i = 0; i < d; ++i) out[k++] = z[i];
  if (degree >= 2) {
    for (std::size_t i = 0; i < d; ++i) {
      for (std::size_t j = i; j < d; ++j) out[k++] = z[i] * z[j];
    }
  }
}

// d(basis)/dz_f
void basisGradient(const double* z, std::size_t d, int degree, std::size_t f, double* out) {
  std::size_t k = 0;
  out[k++] = 0.0;
  for (std::size_t i = 0; i < d; ++i) out[k++] = i == f ? 1.0 : 0.0;
  if (degree >= 2) {
    for (std::size_t i = 0; i < d; ++i) {
      for (std::size_t j = i; j < d; ++j) {
        double g = 0.0;
        if (i == f) g += z[j];
        if (j == f) g += z[i];
        out[k++] = g;
      }
    }
  }
}

at::Tensor doubles(const std::vector<double>& values, std::vector<int64_t> shape) {
  return at::from_blob(const_cast<double*>(values.data()), shape, at::kDouble).clone();
}

std::vector<double> toVector(const at::Tensor& tensor) {
  const auto t = tensor.contiguous().to(at::kDouble);
  return std::vector<double>(t.data_ptr<double>(), t.data_ptr<double>() + t.numel());
}

// Exponentially weighted linear trend of one series against time.
struct Trend {
  double s0 = 0, s1 = 0, s2 = 0, sv = 0, stv = 0, svv = 0;
  double t0 = kNaN, lastT = 0, lastV = 0, lastZ = 0;
  std::size_t updates = 0;

  struct Fit { double mean_t, mean_v, stt, slope, var; };
  Fit fit() const {
    Fit f{};
    if (s0 <= 0) return f;
    f.mean_t = s1 / s0;
    f.mean_v = sv / s0;
    f.stt = s2 - s0 * f.mean_t * f.mean_t;
    const double stv0 = stv - s0 * f.mean_t * f.mean_v;
    const double svv0 = svv - s0 * f.mean_v * f.mean_v;
    f.slope = f.stt > 1e-300 ? stv0 / f.stt : 0.0;
    const double resid = std::max(0.0, svv0 - f.slope * stv0);
    f.var = updates > 2 ? resid / std::max(s0 - 2.0, 0.5) : 0.0;
    return f;
  }
  double forecastAt(double t, double* sd) const {
    const Fit f = fit();
    const double rel = t - t0;
    const double level = f.mean_v + f.slope * (rel - f.mean_t);
    if (sd) {
      const double lever = f.stt > 1e-300 ? (rel - f.mean_t) * (rel - f.mean_t) / f.stt : 0.0;
      *sd = std::sqrt(std::max(0.0, f.var * (1.0 + 1.0 / std::max(s0, 1e-12) + lever)));
    }
    return level;
  }
  void update(double t, double v, double decay) {
    if (!std::isfinite(v)) return;
    if (!std::isfinite(t0)) t0 = t;
    lastZ = 0.0;
    if (updates >= 3) {
      double sd = 0.0;
      const double predicted = forecastAt(t, &sd);
      const double scale = std::max(sd, 1e-12 * std::max(std::abs(predicted), 1.0));
      lastZ = (v - predicted) / scale;
    }
    s0 *= decay; s1 *= decay; s2 *= decay; sv *= decay; stv *= decay; svv *= decay;
    const double rel = t - t0;
    s0 += 1; s1 += rel; s2 += rel * rel; sv += v; stv += rel * v; svv += v * v;
    lastT = t;
    lastV = v;
    ++updates;
  }
  TendencyEstimate estimate(const std::string& name, double horizon) const {
    TendencyEstimate e;
    e.series = name;
    e.value = lastV;
    e.updates = updates;
    e.z = lastZ;
    const Fit f = fit();
    e.level = forecastAt(lastT, nullptr);
    e.slope = updates >= 2 ? f.slope : 0.0;
    e.slopeStdErr = f.stt > 1e-300 ? std::sqrt(f.var / f.stt) : 0.0;
    e.forecast = forecastAt(lastT + horizon, &e.forecastStd);
    e.significant = updates >= 4 && std::abs(e.slope) > 3.0 * e.slopeStdErr &&
                    std::abs(e.slope) > 0.0;
    return e;
  }
};

// Residual network trained online with LibTorch autograd.
struct Mlp {
  std::vector<at::Tensor> params;  // w1 b1 w2 b2 w3 b3
  std::unique_ptr<torch::optim::Adam> optimizer;

  Mlp(std::size_t in, std::size_t hidden, std::size_t out, std::uint64_t seed) {
    std::uint64_t state = seed;
    auto make = [&](int64_t rows, int64_t cols, double scale) {
      std::vector<double> values(static_cast<std::size_t>(rows * cols));
      for (double& v : values) v = scale * normal(state);
      return doubles(values, {rows, cols}).requires_grad_(true);
    };
    const auto h = static_cast<int64_t>(hidden);
    params.push_back(make(h, static_cast<int64_t>(in), 1.0 / std::sqrt(static_cast<double>(in))));
    params.push_back(at::zeros({h}, at::kDouble).requires_grad_(true));
    params.push_back(make(h, h, 1.0 / std::sqrt(static_cast<double>(hidden))));
    params.push_back(at::zeros({h}, at::kDouble).requires_grad_(true));
    // A zero output layer starts as the ridge model exactly.
    params.push_back(at::zeros({static_cast<int64_t>(out), h}, at::kDouble).requires_grad_(true));
    params.push_back(at::zeros({static_cast<int64_t>(out)}, at::kDouble).requires_grad_(true));
    resetOptimizer();
  }
  void resetOptimizer() {
    optimizer = std::make_unique<torch::optim::Adam>(params, torch::optim::AdamOptions(5e-3));
  }
  at::Tensor forward(const at::Tensor& z) const {
    auto h = at::tanh(at::addmm(params[1], z, params[0].t()));
    h = at::tanh(at::addmm(params[3], h, params[2].t()));
    return at::addmm(params[5], h, params[4].t());
  }
  // Returns the weighted loss before the first and after the last step when `losses` is given
  // (the engine trace asks for it; reading a loss never changes the optimisation).
  void train(const at::Tensor& z, const at::Tensor& residual, const at::Tensor& w, std::size_t steps,
             std::pair<double, double>* losses = nullptr) {
    const auto total = w.sum();
    for (std::size_t s = 0; s < steps; ++s) {
      optimizer->zero_grad();
      const auto loss = ((forward(z) - residual).square().sum(1) * w).sum() / total;
      if (losses && s == 0) losses->first = loss.item<double>();
      loss.backward();
      optimizer->step();
    }
    if (losses) {
      at::NoGradGuard guard;
      losses->second = (((forward(z) - residual).square().sum(1) * w).sum() / total).item<double>();
    }
  }
  std::int64_t parameterCount() const {
    std::int64_t n = 0;
    for (const auto& p : params) n += p.numel();
    return n;
  }
  nlohmann::json toJson() const {
    nlohmann::json out = nlohmann::json::array();
    for (const auto& p : params) {
      out.push_back({{"shape", p.sizes().vec()}, {"values", toVector(p.detach())}});
    }
    return out;
  }
  static std::unique_ptr<Mlp> fromJson(const nlohmann::json& value, std::size_t in,
                                       std::size_t out) {
    if (!value.is_array() || value.size() != 6) throw std::invalid_argument("residual network needs six tensors");
    const auto hidden = value.at(0).at("shape").at(0).get<std::size_t>();
    auto mlp = std::make_unique<Mlp>(in, hidden, out, 0);
    for (std::size_t i = 0; i < 6; ++i) {
      const auto shape = value.at(i).at("shape").get<std::vector<int64_t>>();
      const auto values = value.at(i).at("values").get<std::vector<double>>();
      if (shape != mlp->params[i].sizes().vec() ||
          static_cast<int64_t>(values.size()) != mlp->params[i].numel()) {
        throw std::invalid_argument("residual network tensor shape mismatch");
      }
      at::NoGradGuard guard;
      mlp->params[i].copy_(doubles(values, shape));
    }
    mlp->resetOptimizer();
    return mlp;
  }
};

struct Leaf {
  int id = -1;
  std::size_t depth = 0;
  long born = 0;
  long cooldownUntil = 0;
  std::vector<int> predecessors;
  // Buffered rows (raw units).
  std::vector<double> xs, ys;
  std::vector<long> calls;
  std::vector<std::uint64_t> seqs;
  std::uint64_t seen = 0;  // rows offered to the reservoir (stationary mode)
  std::size_t rowsSinceTraining = 0;  // new rows since the residual network trained
  std::size_t rowsSinceFit = 0;       // new rows since the law was refit
  bool refitNow = false;              // refit during this call
  double debugOutsideSq = 0.0;        // TRECH_DEBUG_LEARNER only
  double effectiveRows = 0.0;         // cached at the last refit
  // Frozen standardisation and envelope (z units).
  bool scaled = false;
  std::vector<double> xMean, xScale, yMean, yScale, zLo, zHi;
  std::vector<double> yLo, yHi;  // observed targets (standardized)
  // Joint support: farthest-point centres of the buffered rows (z units,
  // K x d) and the radius that covers every buffered row.
  std::vector<double> centers;
  double supportRadius = 0.0;
  bool fitted = false;
  std::vector<double> beta;  // p x T, standardized
  std::vector<double> residualStd;
  // Prequential grading (raw units).
  std::vector<double> errSq;
  double errW = 0.0;
  // Predictor choice per context (0 inside the envelope, 1 extrapolating):
  // 0 the domain's ridge law, 1 ridge + residual network, 2 the pooled law,
  // 3 the ridge law shifted by the forecast of its own residual bias.
  // Chosen by exponentially weighted prequential error on the domain's rows.
  std::array<std::array<double, 4>, 2> selSse{}, selCount{}, selNow{}, selNowCount{};
  // Tendency of the own law's residual bias per target ("bias:<target>"
  // trends): the ridge+trend predictor adds its forecast at the call's time.
  std::vector<double> biasNow;
  std::size_t biasRows = 0;
  // Own-law error over the last few calls (decay 1/2): lets a domain fed a
  // few rows per call still detect a change point.
  double fastSse = 0.0, fastCount = 0.0;
  // Extrapolating rows start on the pooled law: a young domain must earn
  // the right to extend its own law beyond the rows it has seen.
  std::array<int, 2> choice{0, 2};
  std::unique_ptr<Mlp> mlp;
  std::map<std::string, Trend> trends;
  // Per-call scratch.
  std::size_t elementsNow = 0;
  std::vector<double> featureSum, targetSum, sqErrNow;
  std::size_t scoredNow = 0, extrapolatedNow = 0;
  bool drift = false;
  bool changePoint = false;  // the law changed: its history is stale

  std::size_t rows() const { return calls.size(); }
};

struct Node {
  bool leaf = true;
  int leafId = -1;
  std::vector<double> direction;  // raw units
  double threshold = 0.0;
  int left = -1, right = -1;
  bool alive = true;
};

struct LineageEntry {
  std::vector<int> predecessors;
  long born = 0;
  long retired = -1;
  std::size_t depth = 0;
};

struct Candidate {
  double score = 0.0;
  std::vector<double> v;  // z-space direction
  double cut = 0.0;       // z-space threshold
};

}  // namespace

struct DomainLearner::Impl {
  DomainLearnerOptions o;
  std::size_t d = 0, t = 0, p = 0;
  long call = 0;
  int nextId = 0;
  std::uint64_t seq = 0;
  double lastTime = kNaN, horizon = 1.0;
  std::vector<Node> nodes;
  std::map<int, Leaf> leaves;
  Leaf pooled;
  std::map<int, LineageEntry> lineage;
  std::map<std::string, Trend> globalTrends;
  std::vector<DomainEvent> events;

  explicit Impl(DomainLearnerOptions options) : o(std::move(options)) {
    d = o.features.size();
    t = o.targets.size();
    if (!d) throw std::invalid_argument("domain learner needs at least one feature");
    if (o.minElements < 4 || o.maxDepth > 24 || !(o.forgetting > 0.0 && o.forgetting <= 1.0) ||
        !(o.tendencyDecay > 0.0 && o.tendencyDecay <= 1.0) || o.ridge < 0.0 ||
        o.capacity.maxDomains < 1 || o.capacity.bufferRows < 16 ||
        o.capacity.basisDegree < 1 || o.capacity.basisDegree > 2 || o.refineEvery < 1) {
      throw std::invalid_argument("invalid domain learner options");
    }
    p = basisSize(d, o.capacity.basisDegree);
    nodes.push_back(Node{});
    nodes[0].leafId = newLeaf({}, 0);
    pooled.id = -1;
  }

  int newLeaf(std::vector<int> predecessors, std::size_t depth) {
    const int id = nextId++;
    Leaf& leaf = leaves[id];
    leaf.id = id;
    leaf.depth = depth;
    leaf.born = call;
    leaf.cooldownUntil = call + static_cast<long>(o.mergeCooldown);
    leaf.predecessors = predecessors;
    lineage[id] = {predecessors, call, -1, depth};
    return id;
  }

  std::size_t minSide() const { return std::max(o.minElements, p + 2); }

  int route(const double* x) const {
    int n = 0;
    while (!nodes[n].leaf) {
      const auto& node = nodes[n];
      double s = 0.0;
      for (std::size_t f = 0; f < d; ++f) s += node.direction[f] * x[f];
      n = s <= node.threshold ? node.left : node.right;
    }
    return nodes[n].leafId;
  }

  int nodeOfLeaf(int id) const {
    for (std::size_t n = 0; n < nodes.size(); ++n) {
      if (nodes[n].alive && nodes[n].leaf && nodes[n].leafId == id) return static_cast<int>(n);
    }
    return -1;
  }

  // ---- standardisation, fitting -------------------------------------------

  std::vector<double> weights(const Leaf& leaf) const {
    std::vector<double> w(leaf.rows());
    for (std::size_t i = 0; i < w.size(); ++i) {
      w[i] = std::pow(o.forgetting, static_cast<double>(call - leaf.calls[i]));
    }
    return w;
  }

  static void moments(const std::vector<double>& values, std::size_t width, const std::vector<double>& w,
                      std::vector<double>& mean, std::vector<double>& sd) {
    mean.assign(width, 0.0);
    sd.assign(width, 0.0);
    double total = 0.0;
    for (std::size_t i = 0; i < w.size(); ++i) {
      total += w[i];
      for (std::size_t f = 0; f < width; ++f) mean[f] += w[i] * values[i * width + f];
    }
    for (double& m : mean) m /= std::max(total, 1e-300);
    for (std::size_t i = 0; i < w.size(); ++i) {
      for (std::size_t f = 0; f < width; ++f) {
        const double r = values[i * width + f] - mean[f];
        sd[f] += w[i] * r * r;
      }
    }
    for (double& s : sd) s = std::sqrt(s / std::max(total, 1e-300));
  }

  static double scaleOf(double sd, double mean) {
    if (sd > 1e-12 * std::max(std::abs(mean), 1e-300) && sd > 0.0) return sd;
    return std::abs(mean) > 0.0 ? std::abs(mean) : 1.0;
  }

  void standardize(const Leaf& leaf, const double* x, double* z) const {
    for (std::size_t f = 0; f < d; ++f) z[f] = (x[f] - leaf.xMean[f]) / leaf.xScale[f];
  }

  // Distance from a row to the nearest support centre, in units of the
  // support radius (0 when the law carries no support set).
  double jointRatio(const Leaf& leaf, const double* x) const {
    if (leaf.centers.empty() || !(leaf.supportRadius > 0.0)) return 0.0;
    std::vector<double> z(d);
    standardize(leaf, x, z.data());
    double best = std::numeric_limits<double>::infinity();
    for (std::size_t c = 0; c * d < leaf.centers.size(); ++c) {
      double sq = 0.0;
      for (std::size_t f = 0; f < d; ++f) {
        const double r = z[f] - leaf.centers[c * d + f];
        sq += r * r;
      }
      best = std::min(best, sq);
    }
    return std::sqrt(best) / leaf.supportRadius;
  }

  void computeSupport(Leaf& leaf, const at::Tensor& z) {
    const auto n = static_cast<std::size_t>(z.size(0));
    leaf.centers.clear();
    leaf.supportRadius = 0.0;
    if (!n) return;
    const auto values = toVector(z.contiguous());
    auto dist2 = [&](std::size_t i, const double* c) {
      double sq = 0.0;
      for (std::size_t f = 0; f < d; ++f) {
        const double r = values[i * d + f] - c[f];
        sq += r * r;
      }
      return sq;
    };
    // Start at the row nearest the mean; then repeatedly add the row farthest
    // from every chosen centre (deterministic farthest-point sampling).
    std::vector<double> mean(d, 0.0);
    for (std::size_t i = 0; i < n; ++i)
      for (std::size_t f = 0; f < d; ++f) mean[f] += values[i * d + f] / static_cast<double>(n);
    std::size_t first = 0;
    double bestStart = std::numeric_limits<double>::infinity();
    for (std::size_t i = 0; i < n; ++i) {
      const double sq = dist2(i, mean.data());
      if (sq < bestStart) { bestStart = sq; first = i; }
    }
    std::vector<double> nearest(n, std::numeric_limits<double>::infinity());
    std::size_t next = first;
    const std::size_t k = std::min<std::size_t>(32, n);
    for (std::size_t c = 0; c < k; ++c) {
      leaf.centers.insert(leaf.centers.end(), values.begin() + static_cast<long>(next * d),
                          values.begin() + static_cast<long>((next + 1) * d));
      const double* centre = &leaf.centers[c * d];
      double far = -1.0;
      for (std::size_t i = 0; i < n; ++i) {
        nearest[i] = std::min(nearest[i], dist2(i, centre));
        if (nearest[i] > far) { far = nearest[i]; next = i; }
      }
      leaf.supportRadius = std::sqrt(std::max(far, 0.0));
    }
    // Rows that coincide with centres leave a zero radius: keep a floor so a
    // degenerate support still admits its own rows.
    leaf.supportRadius = std::max(leaf.supportRadius, 1e-6);
  }

  // Clamp to the envelope widened by half a span. Returns true outside it.
  bool clampToEnvelope(const Leaf& leaf, double* z) const {
    bool outside = false;
    for (std::size_t f = 0; f < d; ++f) {
      const double span = leaf.zHi[f] - leaf.zLo[f];
      const double tolerance = std::max(0.05 * span, 1e-9);
      if (z[f] < leaf.zLo[f] - tolerance || z[f] > leaf.zHi[f] + tolerance) outside = true;
      z[f] = std::clamp(z[f], leaf.zLo[f] - 0.5 * span, leaf.zHi[f] + 0.5 * span);
    }
    return outside;
  }

  // Basis for prediction: affine terms extrapolate linearly from the raw
  // standardized point; curvature terms use the clamped point, so a domain
  // extends its law along its gradient but never extrapolates curvature.
  // Features constant across the domain stay at their single value.
  bool predictionBasis(const Leaf& leaf, const double* x, double* zOut, double* phi) const {
    std::vector<double> z(d), clamped(d);
    standardize(leaf, x, z.data());
    clamped = z;
    // Outside the per-feature box, or far (1.5 radii) from the joint support.
    const bool outside = clampToEnvelope(leaf, clamped.data()) | (jointRatio(leaf, x) > 1.5);
    for (std::size_t f = 0; f < d; ++f) {
      // Linear extrapolation, but at most two spans past the envelope.
      const double span = leaf.zHi[f] - leaf.zLo[f];
      z[f] = span > 0.0 ? std::clamp(z[f], leaf.zLo[f] - 2.0 * span, leaf.zHi[f] + 2.0 * span) : clamped[f];
    }
    basis(clamped.data(), d, o.capacity.basisDegree, phi);
    for (std::size_t f = 0; f < d; ++f) phi[1 + f] = z[f];
    if (zOut) std::copy(clamped.begin(), clamped.end(), zOut);
    return outside;
  }

  struct Design {
    at::Tensor z, phi, y, w;
  };

  Design design(const Leaf& leaf, const std::vector<double>& w) const {
    const auto n = static_cast<int64_t>(leaf.rows());
    std::vector<double> z(leaf.rows() * d), phi(leaf.rows() * p), y(leaf.rows() * std::max<std::size_t>(t, 1));
    for (std::size_t i = 0; i < leaf.rows(); ++i) {
      standardize(leaf, &leaf.xs[i * d], &z[i * d]);
      basis(&z[i * d], d, o.capacity.basisDegree, &phi[i * p]);
      for (std::size_t k = 0; k < t; ++k) {
        y[i * t + k] = (leaf.ys[i * t + k] - leaf.yMean[k]) / leaf.yScale[k];
      }
    }
    return {doubles(z, {n, static_cast<int64_t>(d)}), doubles(phi, {n, static_cast<int64_t>(p)}),
            doubles(y, {n, static_cast<int64_t>(t)}), doubles(w, {n})};
  }

  at::Tensor regularized(const at::Tensor& a) const {
    // Batched or single p x p systems.
    const auto diagonal = a.diagonal(0, -2, -1);
    const auto scale = diagonal.mean(-1, true).clamp_min(1e-300) * o.ridge + 1e-12;
    return a + at::diag_embed(scale.expand_as(diagonal));
  }

  // Weighted ridge fit; returns beta (p x T) and per-target SSE (std units).
  // Fewer than four rows per quadratic coefficient fit the affine part only,
  // so a young domain cannot extrapolate a poorly supported curvature.
  std::pair<at::Tensor, at::Tensor> fit(const at::Tensor& phi, const at::Tensor& y, const at::Tensor& w) const {
    const int64_t affine = static_cast<int64_t>(1 + d);
    const bool reduced = static_cast<std::size_t>(phi.size(0)) < 4 * p && phi.size(1) > affine;
    const auto used = reduced ? phi.slice(1, 0, affine) : phi;
    const auto pw = used * w.unsqueeze(1);
    const auto a = pw.t().mm(used);
    const auto b = pw.t().mm(y);
    auto beta = at::linalg_solve(regularized(a), b);
    if (reduced) beta = at::cat({beta, at::zeros({phi.size(1) - affine, y.size(1)}, at::kDouble)}, 0);
    const auto residual = y - phi.mm(beta);
    const auto sse = (residual.square() * w.unsqueeze(1)).sum(0);
    return {beta, sse};
  }

  void rescale(Leaf& leaf, const std::vector<double>& w, bool announce) {
    std::vector<double> xm, xs, ym, ysd;
    moments(leaf.xs, d, w, xm, xs);
    moments(leaf.ys, t, w, ym, ysd);
    leaf.xMean = xm;
    leaf.yMean = ym;
    leaf.xScale.resize(d);
    leaf.yScale.resize(t);
    for (std::size_t f = 0; f < d; ++f) leaf.xScale[f] = scaleOf(xs[f], xm[f]);
    for (std::size_t k = 0; k < t; ++k) leaf.yScale[k] = scaleOf(ysd[k], ym[k]);
    if (leaf.scaled && announce) events.push_back({"rescale", leaf.id, {}, "standardisation refreshed"});
    leaf.scaled = true;
    if (leaf.mlp) {
      leaf.mlp.reset();
      for (int c = 0; c < 2; ++c) {
        leaf.selSse[c][1] = leaf.selCount[c][1] = 0.0;
        if (leaf.choice[c] == 1) leaf.choice[c] = 0;
      }
    }
  }

  bool needsRescale(const Leaf& leaf, const std::vector<double>& w) const {
    if (!leaf.scaled) return true;
    std::vector<double> xm, xs, ym, ysd;
    moments(leaf.xs, d, w, xm, xs);
    moments(leaf.ys, t, w, ym, ysd);
    auto drifted = [](double mean, double sd, double m0, double s0) {
      const double fresh = scaleOf(sd, mean);
      return fresh > 3.0 * s0 || fresh < s0 / 3.0 || std::abs(mean - m0) > 3.0 * s0;
    };
    for (std::size_t f = 0; f < d; ++f) {
      if (drifted(xm[f], xs[f], leaf.xMean[f], leaf.xScale[f])) return true;
    }
    for (std::size_t k = 0; k < t; ++k) {
      if (drifted(ym[k], ysd[k], leaf.yMean[k], leaf.yScale[k])) return true;
    }
    return false;
  }

  void refresh(Leaf& leaf, bool allowNetwork = true, bool force = false) {
    if (!leaf.rows() || !t) return;
    // Uniformly decayed weights leave a weighted least-squares fit unchanged,
    // so only new rows can move a law: refit once a 32nd of the buffer (or 8
    // rows) is new, and always while the domain is young.
    if (!force && leaf.fitted && leaf.rows() >= 4 * p &&
        leaf.rowsSinceFit < std::max<std::size_t>(8, leaf.rows() / 32)) {
      return;
    }
    leaf.rowsSinceFit = 0;
    leaf.refitNow = true;
    const auto w = weights(leaf);
    {
      double total = 0.0, sq = 0.0;
      for (double v : w) { total += v; sq += v * v; }
      leaf.effectiveRows = total * total / std::max(sq, 1e-300);
    }
    if (needsRescale(leaf, w)) rescale(leaf, w, true);
    const Design x = design(leaf, w);
    leaf.zLo = toVector(std::get<0>(x.z.min(0)));
    leaf.zHi = toVector(std::get<0>(x.z.max(0)));
    leaf.yLo = toVector(std::get<0>(x.y.min(0)));
    leaf.yHi = toVector(std::get<0>(x.y.max(0)));
    computeSupport(leaf, x.z);
    if (leaf.rows() < p + 2) return;  // keep any previous model
    const auto [beta, sse] = fit(x.phi, x.y, x.w);
    leaf.beta = toVector(beta);
    leaf.fitted = true;
    const double total = x.w.sum().item<double>();
    const auto sseValues = toVector(sse);
    leaf.residualStd.resize(t);
    for (std::size_t k = 0; k < t; ++k) {
      leaf.residualStd[k] = std::sqrt(sseValues[k] / std::max(total, 1e-300)) * leaf.yScale[k];
    }
    // Train the residual network once an eighth of the buffer (or 32 rows)
    // is new since it last trained: cost follows information, not calls.
    const bool fresh = !leaf.mlp || leaf.rowsSinceTraining >= std::max<std::size_t>(32, leaf.rows() / 8);
    if (allowNetwork && fresh && o.capacity.residualHidden && leaf.rows() >= 4 * minSide()) {
      leaf.rowsSinceTraining = 0;
      if (!leaf.mlp) {
        leaf.mlp = std::make_unique<Mlp>(d, o.capacity.residualHidden, t,
                                         o.seed ^ (0x5bd1e995ULL * static_cast<std::uint64_t>(leaf.id + 1)));
      }
      // Bounded optimisation set: a deterministic stride through the buffer.
      const auto n = static_cast<int64_t>(leaf.rows());
      const int64_t limit = 4096;
      at::Tensor index = n > limit ? at::arange(0, n, (n + limit - 1) / limit, at::kLong) : at::arange(n, at::kLong);
      const auto z = x.z.index_select(0, index);
      const auto residual = (x.y - x.phi.mm(beta)).index_select(0, index);
      if (trace::active()) {
        std::pair<double, double> losses{0.0, 0.0};
        leaf.mlp->train(z, residual, x.w.index_select(0, index), o.capacity.residualSteps, &losses);
        mltrace::trainBurst("domain_learner.residual_mlp", o.capacity.residualSteps,
                            {{"domain", leaf.id},
                             {"rows", static_cast<std::int64_t>(leaf.rows())},
                             {"rows_used", index.size(0)},
                             {"features", d},
                             {"targets", t},
                             {"hidden", o.capacity.residualHidden},
                             {"parameters", leaf.mlp->parameterCount()},
                             {"optimizer", "adam"},
                             {"learning_rate", 5e-3},
                             {"loss_before", losses.first},
                             {"loss_after", losses.second}});
      } else {
        leaf.mlp->train(z, residual, x.w.index_select(0, index), o.capacity.residualSteps);
      }
    }
  }

  // ---- prediction ------------------------------------------------------------

  // How far a row lies outside a law's envelope: the largest excess over the
  // raw envelope, in units of max(that law's span, the pooled law's scale).
  double excess(const Leaf& leaf, const double* x) const {
    double worst = 0.0;
    for (std::size_t f = 0; f < d; ++f) {
      const double lo = leaf.zLo[f] * leaf.xScale[f] + leaf.xMean[f];
      const double hi = leaf.zHi[f] * leaf.xScale[f] + leaf.xMean[f];
      const double unit = std::max(hi - lo, pooled.scaled ? pooled.xScale[f] : leaf.xScale[f]);
      if (!(unit > 0.0)) continue;
      worst = std::max(worst, std::max(lo - x[f], x[f] - hi) / unit);
    }
    return worst;
  }

  // The domain's own law at one row: ridge and (when it exists) ridge plus
  // residual network, raw units. Returns false without a fitted law.
  bool lawPredict(const Leaf& leaf, const double* x, double* ridge, double* network, bool* outside) const {
    if (!leaf.fitted) return false;
    std::vector<double> z(d), phi(p);
    *outside = predictionBasis(leaf, x, z.data(), phi.data());
    std::vector<double> correction(t, 0.0);
    if (leaf.mlp) {
      at::NoGradGuard guard;
      correction = toVector(leaf.mlp->forward(doubles(z, {1, static_cast<int64_t>(d)})));
    }
    for (std::size_t k = 0; k < t; ++k) {
      double s = 0.0;
      for (std::size_t j = 0; j < p; ++j) s += phi[j] * leaf.beta[j * t + k];
      // A residual network refines a law; it may move it by at most three of
      // the law's own residual standard deviations (standardized units).
      double c = correction[k];
      if (!leaf.residualStd.empty()) {
        const double bound = 3.0 * leaf.residualStd[k] / leaf.yScale[k];
        c = std::clamp(c, -bound, bound);
      }
      double n = s + c;
      if (!leaf.yLo.empty()) {
        // A law never predicts far beyond the responses its domain produced.
        const double span = leaf.yHi[k] - leaf.yLo[k];
        s = std::clamp(s, leaf.yLo[k] - span, leaf.yHi[k] + span);
        n = std::clamp(n, leaf.yLo[k] - span, leaf.yHi[k] + span);
      }
      ridge[k] = s * leaf.yScale[k] + leaf.yMean[k];
      network[k] = n * leaf.yScale[k] + leaf.yMean[k];
    }
    return true;
  }

  // Forecast of the own law's residual bias at `time`, per target. Needs a
  // trend history; a frozen learner restored from a state has none.
  bool biasForecast(const Leaf& leaf, double time, double* shift) const {
    for (std::size_t k = 0; k < t; ++k) {
      const auto it = leaf.trends.find("bias:" + o.targets[k]);
      if (it == leaf.trends.end() || it->second.updates < 4) return false;
      shift[k] = it->second.forecastAt(time, nullptr);
    }
    return true;
  }

  // Selected prediction of a domain for one row. `alternatives` receives the
  // candidates (ridge, network, pooled, ridge+trend; t values each) and
  // `available` which of them exist. Returns false when no candidate exists.
  bool predict(const Leaf& leaf, const double* x, double time, double* out, double* alternatives,
               std::array<bool, 4>* available, bool* outside) const {
    available->fill(false);
    (*available)[0] = lawPredict(leaf, x, alternatives, alternatives + t, outside);
    (*available)[1] = (*available)[0] && leaf.mlp != nullptr;
    bool pooledOutside = false;
    std::vector<double> unused(t), shift(t);
    (*available)[2] = &leaf != &pooled && lawPredict(pooled, x, alternatives + 2 * t, unused.data(), &pooledOutside);
    // Far outside its envelope a domain's own law is not trusted while the
    // pooled law is less far out. Distances are in raw units against the
    // larger of the domain's span and the pooled law's scale, so a feature the
    // domain never saw vary (run context) is judged on the population's scale.
    // Remoteness: half a span past the box, or three support radii from the
    // joint support, counts as 1.
    auto remoteness = [&](const Leaf& law) {
      return std::max(excess(law, x) / 0.5, jointRatio(law, x) / 3.0);
    };
    bool far = false;
    if ((*available)[0] && *outside && (*available)[2]) {
      const double own = remoteness(leaf);
      far = own > 1.0 && remoteness(pooled) < own;
    }
    if ((*available)[0] && o.tendencyPredictor && biasForecast(leaf, time, shift.data())) {
      (*available)[3] = true;
      for (std::size_t k = 0; k < t; ++k) alternatives[3 * t + k] = alternatives[k] + shift[k];
    }
    if (!(*available)[0]) {
      *outside = true;
      if (!(*available)[2]) return false;
      std::copy(alternatives + 2 * t, alternatives + 3 * t, out);
      return true;
    }
    int c = leaf.choice[*outside ? 1 : 0];
    if (far && (*available)[2] && !pooledOutside) c = 2;
    if (!(*available)[static_cast<std::size_t>(c)]) c = 0;
    std::copy(alternatives + c * t, alternatives + (c + 1) * t, out);
    return true;
  }

  // ---- buffers -----------------------------------------------------------------

  void addRows(Leaf& leaf, const std::vector<std::size_t>& rows, const DomainLearnerBatch& batch,
               std::size_t capacity) {
    if (rows.empty()) return;
    leaf.rowsSinceTraining += rows.size();
    leaf.rowsSinceFit += rows.size();
    if (o.forgetting >= 1.0) {
      // Stationary laws: a reservoir keeps a uniform sample of every row the
      // domain has seen, across calls and runs (Algorithm R, deterministic).
      std::uint64_t state = o.seed ^ (seq * 0x9E3779B97F4A7C15ULL) ^ static_cast<std::uint64_t>(leaf.id + 13);
      for (std::size_t r : rows) {
        ++leaf.seen;
        std::size_t slot = leaf.rows();
        if (slot >= capacity) {
          const std::uint64_t j = splitmix(state) % leaf.seen;
          if (j >= capacity) continue;
          slot = static_cast<std::size_t>(j);
        } else {
          leaf.xs.resize(leaf.xs.size() + d);
          leaf.ys.resize(leaf.ys.size() + t);
          leaf.calls.push_back(0);
          leaf.seqs.push_back(0);
        }
        std::copy(&batch.features[r * d], &batch.features[r * d] + d, leaf.xs.begin() + static_cast<long>(slot * d));
        std::copy(&batch.targets[r * t], &batch.targets[r * t] + t, leaf.ys.begin() + static_cast<long>(slot * t));
        leaf.calls[slot] = call;
        leaf.seqs[slot] = seq++;
      }
      return;
    }
    const std::size_t quota = std::max<std::size_t>(capacity / 4, 1);
    std::vector<std::size_t> chosen;
    if (rows.size() <= quota) {
      chosen = rows;
    } else {
      // Deterministic stratified subsample with a call-dependent offset.
      std::uint64_t state = o.seed ^ (static_cast<std::uint64_t>(call) * 0x2545F4914F6CDD1DULL) ^
                            static_cast<std::uint64_t>(leaf.id + 7);
      const double stride = static_cast<double>(rows.size()) / static_cast<double>(quota);
      const double offset = stride * static_cast<double>(splitmix(state) >> 11) * 0x1.0p-53;
      for (std::size_t i = 0; i < quota; ++i) {
        chosen.push_back(rows[std::min(rows.size() - 1, static_cast<std::size_t>(offset + stride * i))]);
      }
    }
    for (std::size_t r : chosen) {
      leaf.xs.insert(leaf.xs.end(), &batch.features[r * d], &batch.features[r * d] + d);
      leaf.ys.insert(leaf.ys.end(), &batch.targets[r * t], &batch.targets[r * t] + t);
      leaf.calls.push_back(call);
      leaf.seqs.push_back(seq++);
    }
    // Rows whose forgetting weight fell below e^-3 carry little evidence but
    // can hold a stale law in a slowly fed domain: drop them.
    std::size_t stale = 0;
    if (o.forgetting < 1.0) {
      const double maxAge = 3.0 / -std::log(o.forgetting);
      while (stale < leaf.rows() && static_cast<double>(call - leaf.calls[stale]) > maxAge) ++stale;
    }
    if (leaf.rows() > capacity || stale) {
      const std::size_t drop = std::max(stale, leaf.rows() > capacity ? leaf.rows() - capacity : 0);
      leaf.xs.erase(leaf.xs.begin(), leaf.xs.begin() + static_cast<long>(drop * d));
      leaf.ys.erase(leaf.ys.begin(), leaf.ys.begin() + static_cast<long>(drop * t));
      leaf.calls.erase(leaf.calls.begin(), leaf.calls.begin() + static_cast<long>(drop));
      leaf.seqs.erase(leaf.seqs.begin(), leaf.seqs.begin() + static_cast<long>(drop));
    }
  }

  // ---- subdivision -----------------------------------------------------------

  // Two-fold cross-validated SSE of separate fits on each part (std units of
  // the parent). Folds alternate by arrival sequence. Returns NaN if a fold
  // is too small to fit.
  double crossValidated(const Design& x, const std::vector<std::uint64_t>& seqs,
                        const std::vector<std::vector<int64_t>>& parts) const {
    double total = 0.0;
    for (const auto& part : parts) {
      std::vector<int64_t> folds[2];
      for (int64_t i : part) folds[seqs[static_cast<std::size_t>(i)] % 2].push_back(i);
      if (folds[0].size() < p + 2 || folds[1].size() < p + 2) return kNaN;
      for (int f = 0; f < 2; ++f) {
        const auto train = at::tensor(folds[f], at::kLong);
        const auto test = at::tensor(folds[1 - f], at::kLong);
        const auto [beta, unused] = fit(x.phi.index_select(0, train), x.y.index_select(0, train),
                                        x.w.index_select(0, train));
        const auto residual = x.y.index_select(0, test) - x.phi.index_select(0, test).mm(beta);
        total += (residual.square() * x.w.index_select(0, test).unsqueeze(1)).sum().item<double>();
      }
    }
    return total;
  }

  std::optional<Candidate> searchSplit(Leaf& leaf, std::string* reason) {
    const std::size_t n = leaf.rows();
    const std::size_t side = minSide();
    if (!leaf.fitted || n < 2 * side) { *reason = "too_few_rows"; return std::nullopt; }
    const auto w = weights(leaf);
    const Design x = design(leaf, w);
    const auto [beta, sseParts] = fit(x.phi, x.y, x.w);
    const double sseParent = sseParts.sum().item<double>();
    const double total = x.w.sum().item<double>();
    const double neff = total * total / std::max(x.w.square().sum().item<double>(), 1e-300);
    // A law that already explains the rows to rounding has nothing to split.
    if (sseParent <= o.exactLaw * total * static_cast<double>(t)) { *reason = "law_fits"; return std::nullopt; }

    // Directions: feature axes, then leading principal axes (LibTorch eigh).
    std::vector<std::vector<double>> directions;
    for (std::size_t f = 0; f < d; ++f) {
      if (leaf.zHi[f] > leaf.zLo[f]) {
        std::vector<double> v(d, 0.0);
        v[f] = 1.0;
        directions.push_back(v);
      }
    }
    if (d >= 2) {
      const auto mean = (x.z * x.w.unsqueeze(1)).sum(0) / total;
      const auto centered = x.z - mean;
      const auto cov = (centered * x.w.unsqueeze(1)).t().mm(centered) / total;
      const auto [values, vectors] = at::linalg_eigh(cov);
      const auto vals = toVector(values);
      const auto vecs = toVector(vectors.t().contiguous());
      for (std::size_t a = d; a-- > 0 && a + 3 >= d;) {
        if (!(vals[a] > 1e-12 * std::max(vals[d - 1], 1e-300))) continue;
        std::vector<double> v(vecs.begin() + static_cast<long>(a * d), vecs.begin() + static_cast<long>((a + 1) * d));
        const auto pivot = std::max_element(v.begin(), v.end(), [](double l, double r) { return std::abs(l) < std::abs(r); });
        if (std::abs(*pivot) > 0.995) continue;  // already an axis
        if (*pivot < 0) for (double& c : v) c = -c;
        directions.push_back(v);
      }
    }

    // Residual directions: where the parent law errs, regressed on the
    // features. A hinge or an oblique boundary between two laws shows up as a
    // linear trend of the absolute (or signed) residual, which neither the
    // feature axes nor the principal axes need to align with.
    {
      const auto residual = x.y - x.phi.mm(beta);
      const auto mean = (x.z * x.w.unsqueeze(1)).sum(0, true) / total;
      const auto centered = x.z - mean;
      const auto gram = (centered * x.w.unsqueeze(1)).t().mm(centered);
      const auto reg = gram + at::eye(static_cast<int64_t>(d), at::kDouble) *
                                  (gram.diagonal().mean().clamp_min(1e-300) * 1e-8);
      for (std::size_t k = 0; k < t; ++k) {
        for (int kind = 0; kind < 2; ++kind) {
          auto r = residual.select(1, static_cast<int64_t>(k));
          if (kind == 0) r = r.abs();
          r = r - (r * x.w).sum() / total;
          const auto coef = toVector(at::linalg_solve(reg, (centered * x.w.unsqueeze(1)).t().mv(r)));
          double norm = 0.0;
          for (double c : coef) norm += c * c;
          norm = std::sqrt(norm);
          if (!(norm > 0.0) || !std::isfinite(norm)) continue;
          std::vector<double> v(d);
          for (std::size_t f = 0; f < d; ++f) v[f] = coef[f] / norm;
          const auto pivot = std::max_element(v.begin(), v.end(), [](double l, double r2) { return std::abs(l) < std::abs(r2); });
          if (std::abs(*pivot) > 0.995) continue;  // already an axis
          if (*pivot < 0) for (double& c : v) c = -c;
          directions.push_back(v);
        }
      }
    }

    std::vector<Candidate> candidates;
    const auto zValues = toVector(x.z);
    for (const auto& v : directions) {
      std::vector<std::pair<double, std::size_t>> order(n);
      for (std::size_t i = 0; i < n; ++i) {
        double s = 0.0;
        for (std::size_t f = 0; f < d; ++f) s += v[f] * zValues[i * d + f];
        order[i] = {s, static_cast<std::size_t>(leaf.seqs[i])};
      }
      std::vector<std::size_t> index(n);
      std::iota(index.begin(), index.end(), 0);
      std::sort(index.begin(), index.end(), [&](std::size_t a, std::size_t b) { return order[a] < order[b]; });
      // Candidate cuts between distinct projections, spread by rank.
      std::vector<std::size_t> cuts;
      const std::size_t k = std::max<std::size_t>(o.capacity.splitCandidates, 2);
      for (std::size_t c = 0; c < k; ++c) {
        std::size_t pos = side + (n - 2 * side) * c / (k - 1);
        while (pos < n - side && order[index[pos]].first <= order[index[pos - 1]].first) ++pos;
        if (pos >= side && pos <= n - side && order[index[pos]].first > order[index[pos - 1]].first &&
            (cuts.empty() || cuts.back() != pos)) {
          cuts.push_back(pos);
        }
      }
      if (cuts.empty()) continue;
      std::vector<int64_t> sorted(index.begin(), index.end());
      const auto idx = at::tensor(sorted, at::kLong);
      const auto phi = x.phi.index_select(0, idx);
      const auto y = x.y.index_select(0, idx);
      const auto ww = x.w.index_select(0, idx);
      // SSE of both sides at each cut: chunk sums between consecutive cuts,
      // then prefix sums and batched solves, O(n p^2) per call.
      auto scoreCuts = [&](const std::vector<std::size_t>& at) {
        std::vector<at::Tensor> as, bs, cs;
        std::size_t start = 0;
        for (std::size_t c = 0; c <= at.size(); ++c) {
          const std::size_t end = c < at.size() ? at[c] : n;
          const auto ph = phi.slice(0, static_cast<int64_t>(start), static_cast<int64_t>(end));
          const auto yy = y.slice(0, static_cast<int64_t>(start), static_cast<int64_t>(end));
          const auto wc = ww.slice(0, static_cast<int64_t>(start), static_cast<int64_t>(end)).unsqueeze(1);
          as.push_back((ph * wc).t().mm(ph));
          bs.push_back((ph * wc).t().mm(yy));
          cs.push_back((yy.square() * wc).sum());
          start = end;
        }
        const auto aCum = at::stack(as).cumsum(0);
        const auto bCum = at::stack(bs).cumsum(0);
        const auto cCum = at::stack(cs).cumsum(0);
        const auto m = static_cast<int64_t>(at.size());
        const auto aL = aCum.slice(0, 0, m), bL = bCum.slice(0, 0, m), cL = cCum.slice(0, 0, m);
        const auto aR = aCum[m].unsqueeze(0) - aL, bR = bCum[m].unsqueeze(0) - bL, cR = cCum[m] - cL;
        // Lean pair Trech.Methods.LeastSquares (include/trech/ml/LeastSquaresStatistics.hpp).
        auto sse = [&](const at::Tensor& a, const at::Tensor& b, const at::Tensor& c) {
          return sseFromStatistics(a, b, c, at::linalg_solve(regularized(a), b));
        };
        return toVector((sse(aL, bL, cL) + sse(aR, bR, cR)).clamp_min(0.0));
      };
      auto distinct = [&](std::size_t pos) {
        return pos >= side && pos <= n - side && order[index[pos]].first > order[index[pos - 1]].first;
      };
      auto record = [&](const std::vector<std::size_t>& at, const std::vector<double>& scores) {
        for (std::size_t c = 0; c < at.size(); ++c) {
          if (!std::isfinite(scores[c])) continue;
          const double cut = 0.5 * (order[index[at[c] - 1]].first + order[index[at[c]]].first);
          candidates.push_back({scores[c], v, cut});
        }
      };
      const auto coarse = scoreCuts(cuts);
      record(cuts, coarse);
      // Refine the best coarse cut over every distinct position between its
      // neighbours (strided to at most 128), so boundaries are not quantised.
      const std::size_t best = static_cast<std::size_t>(
          std::min_element(coarse.begin(), coarse.end()) - coarse.begin());
      const std::size_t lo = best ? cuts[best - 1] : side;
      const std::size_t hi = best + 1 < cuts.size() ? cuts[best + 1] : n - side;
      const std::size_t stride = std::max<std::size_t>(1, (hi - lo) / 128);
      std::vector<std::size_t> fine;
      for (std::size_t pos = lo; pos <= hi; pos += stride) {
        if (distinct(pos) && pos != cuts[best]) fine.push_back(pos);
      }
      if (!fine.empty()) record(fine, scoreCuts(fine));
    }
    if (candidates.empty()) { *reason = "no_candidate"; return std::nullopt; }
    std::stable_sort(candidates.begin(), candidates.end(),
                     [](const Candidate& a, const Candidate& b) { return a.score < b.score; });
    const double penalty = o.splitPenalty * static_cast<double>(p * t + 1) * std::log(std::max(neff, 2.0));
    const double cvParent = crossValidated(x, leaf.seqs, {[&] {
      std::vector<int64_t> all(n);
      std::iota(all.begin(), all.end(), 0);
      return all;
    }()});
    *reason = "no_gain";
    std::size_t tried = 0;
    for (const auto& candidate : candidates) {
      if (tried >= 6) break;
      // BIC on the rows' effective count.
      if (!bicSplitAccepted(neff, candidate.score, sseParent, penalty)) break;  // Trech.Methods.LeastSquares.bicGate_iff
      ++tried;
      std::vector<int64_t> left, right;
      std::set<long> leftCalls, rightCalls;
      for (std::size_t i = 0; i < n; ++i) {
        double s = 0.0;
        for (std::size_t f = 0; f < d; ++f) s += candidate.v[f] * zValues[i * d + f];
        if (s <= candidate.cut) { left.push_back(static_cast<int64_t>(i)); leftCalls.insert(leaf.calls[i]); }
        else { right.push_back(static_cast<int64_t>(i)); rightCalls.insert(leaf.calls[i]); }
      }
      if (left.size() < side || right.size() < side) continue;
      if (leftCalls.size() < o.minSupportCalls || rightCalls.size() < o.minSupportCalls) {
        *reason = "unsupported";
        continue;
      }
      const double cvSplit = crossValidated(x, leaf.seqs, {left, right});
      if (!std::isfinite(cvSplit) || !std::isfinite(cvParent)) continue;
      if (std::getenv("TRECH_DEBUG_LEARNER")) {
        std::fprintf(stderr, "[learner] call %ld leaf %d n=%zu sseP/total=%.3g best/sseP=%.3g cvS/cvP=%.3g\n",
                     call, leaf.id, n, sseParent / total, candidate.score / sseParent, cvSplit / cvParent);
      }
      // Relative and material: the split must remove a share of the error
      // and a share of the variance, so numerical residue never qualifies.
      if (cvSplit < (1.0 - o.minGain) * cvParent &&
          cvParent - cvSplit > o.exactLaw * total * static_cast<double>(t)) {
        return candidate;
      }
    }
    return std::nullopt;
  }

  void split(int nodeIndex, Leaf& parent, const Candidate& candidate) {
    // Express the z-space half-space in raw units: v.(x - m)/s <= cut.
    std::vector<double> direction(d);
    double threshold = candidate.cut;
    for (std::size_t f = 0; f < d; ++f) {
      direction[f] = candidate.v[f] / parent.xScale[f];
      threshold += candidate.v[f] * parent.xMean[f] / parent.xScale[f];
    }
    const int leftId = newLeaf({parent.id}, parent.depth + 1);
    const int rightId = newLeaf({parent.id}, parent.depth + 1);
    Leaf& left = leaves.at(leftId);
    Leaf& right = leaves.at(rightId);
    for (std::size_t i = 0; i < parent.rows(); ++i) {
      double s = 0.0;
      for (std::size_t f = 0; f < d; ++f) s += direction[f] * parent.xs[i * d + f];
      Leaf& target = s <= threshold ? left : right;
      target.xs.insert(target.xs.end(), &parent.xs[i * d], &parent.xs[i * d] + d);
      target.ys.insert(target.ys.end(), &parent.ys[i * t], &parent.ys[i * t] + t);
      target.calls.push_back(parent.calls[i]);
      target.seqs.push_back(parent.seqs[i]);
    }
    left.seen = static_cast<std::uint64_t>(left.rows());
    right.seen = static_cast<std::uint64_t>(right.rows());
    if (parent.seen > parent.rows()) {
      // Keep the reservoirs' sampling rates: scale by each side's share.
      const double rate = static_cast<double>(parent.seen) / static_cast<double>(std::max<std::size_t>(parent.rows(), 1));
      left.seen = static_cast<std::uint64_t>(std::llround(static_cast<double>(left.rows()) * rate));
      right.seen = static_cast<std::uint64_t>(std::llround(static_cast<double>(right.rows()) * rate));
    }
    refresh(left);
    refresh(right);
    lineage[parent.id].retired = call;
    Node& node = nodes[static_cast<std::size_t>(nodeIndex)];
    node.leaf = false;
    node.leafId = -1;
    node.direction = direction;
    node.threshold = threshold;
    const int parentId = parent.id;
    leaves.erase(parentId);
    nodes.push_back(Node{true, leftId});
    nodes.push_back(Node{true, rightId});
    nodes[static_cast<std::size_t>(nodeIndex)].left = static_cast<int>(nodes.size()) - 2;
    nodes[static_cast<std::size_t>(nodeIndex)].right = static_cast<int>(nodes.size()) - 1;
    std::string detail;
    for (std::size_t f = 0; f < d; ++f) {
      if (std::abs(candidate.v[f]) > 1e-9) {
        detail += (detail.empty() ? "" : " + ") + std::to_string(direction[f]) + "*" + o.features[f];
      }
    }
    detail += " <= " + std::to_string(threshold);
    events.push_back({"split", parentId, {leftId, rightId}, detail});
  }

  // Merge sibling leaves whose single law explains both within the BIC margin.
  void tryMerges() {
    for (std::size_t n = 0; n < nodes.size(); ++n) {
      Node& node = nodes[n];
      if (!node.alive || node.leaf) continue;
      Node& l = nodes[static_cast<std::size_t>(node.left)];
      Node& r = nodes[static_cast<std::size_t>(node.right)];
      if (!l.leaf || !r.leaf) continue;
      Leaf& a = leaves.at(l.leafId);
      Leaf& b = leaves.at(r.leafId);
      if (call < a.cooldownUntil || call < b.cooldownUntil) continue;
      // Only a refit (enough new rows) can change the verdict on a pair.
      if (!a.refitNow && !b.refitNow) continue;
      Leaf merged;
      merged.xs = a.xs; merged.xs.insert(merged.xs.end(), b.xs.begin(), b.xs.end());
      merged.ys = a.ys; merged.ys.insert(merged.ys.end(), b.ys.begin(), b.ys.end());
      merged.calls = a.calls; merged.calls.insert(merged.calls.end(), b.calls.begin(), b.calls.end());
      merged.seqs = a.seqs; merged.seqs.insert(merged.seqs.end(), b.seqs.begin(), b.seqs.end());
      if (merged.rows() < 2 * minSide()) continue;
      const auto w = weights(merged);
      rescale(merged, w, false);
      const Design x = design(merged, w);
      const double total = x.w.sum().item<double>();
      const double neff = total * total / std::max(x.w.square().sum().item<double>(), 1e-300);
      const double sseMerged = fit(x.phi, x.y, x.w).second.sum().item<double>();
      std::vector<int64_t> ia(a.rows()), ib(b.rows());
      std::iota(ia.begin(), ia.end(), 0);
      std::iota(ib.begin(), ib.end(), static_cast<int64_t>(a.rows()));
      double sseSplit = 0.0;
      for (const auto* part : {&ia, &ib}) {
        if (part->size() < p + 2) { sseSplit = kNaN; break; }
        const auto idx = at::tensor(*part, at::kLong);
        sseSplit += fit(x.phi.index_select(0, idx), x.y.index_select(0, idx), x.w.index_select(0, idx))
                        .second.sum().item<double>();
      }
      if (!std::isfinite(sseSplit)) continue;
      const double floor = o.exactLaw * total * static_cast<double>(t);
      const double penalty = o.splitPenalty * static_cast<double>(p * t + 1) * std::log(std::max(neff, 2.0));
      if (std::getenv("TRECH_DEBUG_LEARNER")) {
        std::fprintf(stderr, "[learner-merge] call %ld %d+%d rows %zu+%zu merged/total=%.3g split/total=%.3g neff=%.1f\n",
                     call, a.id, b.id, a.rows(), b.rows(), sseMerged / total, sseSplit / total, neff);
      }
      const bool sameLaw = sseMerged <= floor ||
          (sseSplit > floor && neff * std::log(sseMerged / sseSplit) < 0.5 * penalty);
      if (!sameLaw) continue;
      const int aId = a.id, bId = b.id;
      const std::size_t depth = std::min(a.depth, b.depth) - (std::min(a.depth, b.depth) ? 1 : 0);
      const int id = newLeaf({aId, bId}, depth);
      Leaf& fresh = leaves.at(id);
      fresh.xs = std::move(merged.xs);
      fresh.ys = std::move(merged.ys);
      fresh.calls = std::move(merged.calls);
      fresh.seqs = std::move(merged.seqs);
      fresh.seen = std::max<std::uint64_t>(a.seen + b.seen, fresh.rows());
      if (fresh.rows() > o.capacity.bufferRows) {
        // Two full reservoirs: keep a deterministic uniform subset.
        std::vector<std::size_t> keep(fresh.rows());
        std::iota(keep.begin(), keep.end(), 0);
        std::uint64_t state = o.seed ^ static_cast<std::uint64_t>(id + 101);
        for (std::size_t i = keep.size(); i > 1; --i) std::swap(keep[i - 1], keep[splitmix(state) % i]);
        keep.resize(o.capacity.bufferRows);
        std::sort(keep.begin(), keep.end());
        Leaf trimmed;
        for (std::size_t i : keep) {
          trimmed.xs.insert(trimmed.xs.end(), &fresh.xs[i * d], &fresh.xs[i * d] + d);
          trimmed.ys.insert(trimmed.ys.end(), &fresh.ys[i * t], &fresh.ys[i * t] + t);
          trimmed.calls.push_back(fresh.calls[i]);
          trimmed.seqs.push_back(fresh.seqs[i]);
        }
        fresh.xs = std::move(trimmed.xs);
        fresh.ys = std::move(trimmed.ys);
        fresh.calls = std::move(trimmed.calls);
        fresh.seqs = std::move(trimmed.seqs);
      }
      refresh(fresh);
      lineage[aId].retired = call;
      lineage[bId].retired = call;
      leaves.erase(aId);
      leaves.erase(bId);
      l.alive = false;
      r.alive = false;
      node.leaf = true;
      node.leafId = id;
      node.left = node.right = -1;
      node.direction.clear();
      events.push_back({"merge", id, {aId, bId}, "one law explains both"});
    }
  }

  // ---- tendencies ------------------------------------------------------------

  void track(Leaf& leaf, double time) {
    const double decay = o.tendencyDecay;
    leaf.trends["elements"].update(time, static_cast<double>(leaf.elementsNow), decay);
    if (!leaf.elementsNow) return;
    const double count = static_cast<double>(leaf.elementsNow);
    std::vector<double> mean(d);
    for (std::size_t f = 0; f < d; ++f) {
      mean[f] = leaf.featureSum[f] / count;
      leaf.trends["feature:" + o.features[f]].update(time, mean[f], decay);
    }
    if (leaf.scoredNow) {
      for (std::size_t k = 0; k < t; ++k) {
        leaf.trends["target:" + o.targets[k]].update(time, leaf.targetSum[k] / static_cast<double>(leaf.scoredNow), decay);
      }
    }
    if (!leaf.fitted) return;
    // Model parameters as raw-unit local sensitivities at the population mean.
    std::vector<double> z(d), phi(p), grad(p);
    standardize(leaf, mean.data(), z.data());
    clampToEnvelope(leaf, z.data());
    basis(z.data(), d, o.capacity.basisDegree, phi.data());
    for (std::size_t k = 0; k < t; ++k) {
      double value = 0.0;
      for (std::size_t j = 0; j < p; ++j) value += phi[j] * leaf.beta[j * t + k];
      leaf.trends["value:" + o.targets[k]].update(time, value * leaf.yScale[k] + leaf.yMean[k], decay);
      for (std::size_t f = 0; f < d; ++f) {
        basisGradient(z.data(), d, o.capacity.basisDegree, f, grad.data());
        double g = 0.0;
        for (std::size_t j = 0; j < p; ++j) g += grad[j] * leaf.beta[j * t + k];
        leaf.trends["sensitivity:" + o.targets[k] + "/" + o.features[f]].update(
            time, g * leaf.yScale[k] / leaf.xScale[f], decay);
      }
    }
  }

  DomainSummary summarize(const Leaf& leaf) const {
    DomainSummary s;
    s.id = leaf.id;
    s.predecessors = leaf.predecessors;
    s.bornCall = leaf.born;
    s.depth = leaf.depth;
    s.elements = leaf.elementsNow;
    s.bufferRows = leaf.rows();
    // Envelope and effective rows as of the domain's last refit.
    s.effectiveRows = leaf.effectiveRows;
    if (leaf.scaled && !leaf.zLo.empty()) {
      for (std::size_t f = 0; f < d; ++f) {
        s.featureMin.push_back(leaf.zLo[f] * leaf.xScale[f] + leaf.xMean[f]);
        s.featureMax.push_back(leaf.zHi[f] * leaf.xScale[f] + leaf.xMean[f]);
      }
    }
    s.model = modelName(leaf);
    s.residualStd = leaf.residualStd;
    s.errorRmse.resize(t, kNaN);
    if (leaf.errW > 0.0) {
      for (std::size_t k = 0; k < t; ++k) s.errorRmse[k] = std::sqrt(leaf.errSq[k] / leaf.errW);
    }
    for (const auto& [name, trend] : leaf.trends) s.tendencies.push_back(trend.estimate(name, horizon));
    if (leaf.fitted) {
      for (std::size_t k = 0; k < t; ++k) {
        auto it = leaf.trends.find("value:" + o.targets[k]);
        s.valueAtMean.push_back(it == leaf.trends.end() ? kNaN : it->second.lastV);
        for (std::size_t f = 0; f < d; ++f) {
          auto st = leaf.trends.find("sensitivity:" + o.targets[k] + "/" + o.features[f]);
          s.sensitivity.push_back(st == leaf.trends.end() ? kNaN : st->second.lastV);
        }
      }
    }
    const auto it = leaf.trends.find("elements");
    if (it != leaf.trends.end()) {
      const auto e = it->second.estimate("elements", horizon);
      if (e.significant && e.slope < 0.0 && e.level > 0.0) s.extinctionEta = e.level / -e.slope;
    }
    return s;
  }

  static constexpr const char* kPredictorNames[4] = {"ridge", "ridge+mlp", "pooled", "ridge+trend"};

  // Move each context to the predictor with the lowest weighted prequential
  // error once it has evidence, with a 10% margin against the incumbent.
  void selectPredictors(Leaf& leaf) {
    for (int c = 0; c < 2; ++c) {
      for (int k = 0; k < 4; ++k) {
        leaf.selSse[c][k] = leaf.selSse[c][k] * o.forgetting + leaf.selNow[c][k];
        leaf.selCount[c][k] = leaf.selCount[c][k] * o.forgetting + leaf.selNowCount[c][k];
      }
      const double evidence = *std::max_element(leaf.selCount[c].begin(), leaf.selCount[c].end());
      if (evidence < 20.0) continue;
      auto mean = [&](int k) {
        return leaf.selCount[c][k] >= 0.8 * evidence ? leaf.selSse[c][k] / leaf.selCount[c][k]
                                                     : std::numeric_limits<double>::infinity();
      };
      int best = leaf.choice[c];
      for (int k = 0; k < 4; ++k) {
        if (mean(k) < mean(best)) best = k;
      }
      // Extrapolation trust is asymmetric: leaving the pooled law for rows
      // outside the envelope needs ten times the evidence and half its error;
      // returning to it needs the usual 10% margin.
      const bool trustOwnOutside = c == 1 && leaf.choice[c] == 2 && best != 2;
      const double margin = trustOwnOutside ? 0.5 : 0.9;
      if (trustOwnOutside && evidence < 10.0 * static_cast<double>(o.minElements)) continue;
      if (best != leaf.choice[c] && (mean(best) < margin * mean(leaf.choice[c]) || !std::isfinite(mean(leaf.choice[c])))) {
        leaf.choice[c] = best;
        events.push_back({"model", leaf.id, {}, std::string(c ? "outside:" : "inside:") + kPredictorNames[best]});
      }
    }
  }

  static std::string modelName(const Leaf& leaf) {
    if (!leaf.fitted) return "none";
    std::string name = kPredictorNames[leaf.choice[0]];
    if (leaf.choice[1] != leaf.choice[0]) name += "|outside:" + std::string(kPredictorNames[leaf.choice[1]]);
    return name;
  }

  // ---- one call ------------------------------------------------------------------

  DomainLearnerResult update(const DomainLearnerBatch& batch) {
    const auto start = std::chrono::steady_clock::now();
    const std::size_t n = batch.count;
    if (batch.features.size() != n * d || (!batch.targets.empty() && batch.targets.size() != n * t)) {
      throw std::invalid_argument("domain learner batch does not match its features and targets");
    }
    if (!std::isfinite(batch.time)) throw std::invalid_argument("domain learner time must be finite");
    if (std::isfinite(lastTime) && batch.time > lastTime) horizon = batch.time - lastTime;
    lastTime = batch.time;
    ++call;
    events.clear();
    const bool learning = !o.frozen && !batch.targets.empty() && t > 0;

    DomainLearnerResult result;
    result.call = call;
    result.elementDomains.assign(n, -1);
    result.predictionDomains.assign(n, -1);
    result.predictions.assign(n * t, kNaN);
    result.predictionStd.assign(n * t, kNaN);
    result.extrapolated.assign(n, 0);
    result.routedRmse.assign(t, kNaN);
    result.pooledRmse.assign(t, kNaN);
    result.intervalCoverage.assign(t, kNaN);
    std::vector<double> covered(t, 0.0);

    for (auto& [id, leaf] : leaves) {
      leaf.elementsNow = leaf.scoredNow = leaf.extrapolatedNow = 0;
      leaf.featureSum.assign(d, 0.0);
      leaf.targetSum.assign(t, 0.0);
      leaf.sqErrNow.assign(t, 0.0);
      leaf.drift = false;
      leaf.changePoint = false;
      leaf.refitNow = false;
      leaf.debugOutsideSq = 0.0;
      for (auto& row : leaf.selNow) row.fill(0.0);
      for (auto& row : leaf.selNowCount) row.fill(0.0);
      leaf.biasNow.assign(t, 0.0);
      leaf.biasRows = 0;
    }
    std::map<int, std::vector<std::size_t>> members;
    std::vector<std::size_t> learnRows;
    std::vector<double> routedSq(t, 0.0), pooledSq(t, 0.0);
    std::vector<double> out(t), alt(4 * t);
    std::array<bool, 4> available{};
    for (std::size_t i = 0; i < n; ++i) {
      const double* x = &batch.features[i * d];
      if (!std::all_of(x, x + d, [](double v) { return std::isfinite(v); })) continue;
      const int id = route(x);
      Leaf& leaf = leaves.at(id);
      result.predictionDomains[i] = id;
      ++leaf.elementsNow;
      for (std::size_t f = 0; f < d; ++f) leaf.featureSum[f] += x[f];
      members[id].push_back(i);
      bool outside = false;
      const bool has = predict(leaf, x, batch.time, out.data(), alt.data(), &available, &outside);
      if (has) {
        result.extrapolated[i] = outside ? 1 : 0;
        result.extrapolatedCount += outside ? 1 : 0;
        leaf.extrapolatedNow += outside ? 1 : 0;
        for (std::size_t k = 0; k < t; ++k) {
          result.predictions[i * t + k] = out[k];
          double sd = leaf.residualStd.empty() ? 0.0 : leaf.residualStd[k];
          if (leaf.errW > 0.0) sd = std::max(sd, std::sqrt(leaf.errSq[k] / leaf.errW));
          result.predictionStd[i * t + k] = outside ? 2.0 * sd : sd;
        }
      }
      if (batch.targets.empty()) continue;
      const double* y = &batch.targets[i * t];
      if (!std::all_of(y, y + t, [](double v) { return std::isfinite(v); })) continue;
      learnRows.push_back(i);
      for (std::size_t k = 0; k < t; ++k) leaf.targetSum[k] += y[k];
      ++leaf.scoredNow;
      if (!has || !available[2]) continue;
      ++result.scored;
      const int context = outside ? 1 : 0;
      for (std::size_t k = 0; k < t; ++k) {
        const double e = out[k] - y[k];
        if (std::abs(e) <= 1.96 * result.predictionStd[i * t + k]) covered[k] += 1.0;
        if (outside) leaf.debugOutsideSq += e * e / (leaf.yScale.empty() ? 1.0 : leaf.yScale[k] * leaf.yScale[k]);
        routedSq[k] += e * e;
        leaf.sqErrNow[k] += e * e;
        const double pe = alt[2 * t + k] - y[k];
        pooledSq[k] += pe * pe;
      }
      if (available[0] && !outside) {
        // Own-law residual bias of rows inside the envelope (its tendency).
        if (leaf.biasNow.empty()) leaf.biasNow.assign(t, 0.0);
        for (std::size_t k = 0; k < t; ++k) leaf.biasNow[k] += y[k] - alt[k];
        ++leaf.biasRows;
      }
      if (leaf.fitted) {
        for (std::size_t c = 0; c < 4; ++c) {
          if (!available[c]) continue;
          double err = 0.0;
          for (std::size_t k = 0; k < t; ++k) err += std::pow((alt[c * t + k] - y[k]) / leaf.yScale[k], 2);
          leaf.selNow[context][c] += err;
          leaf.selNowCount[context][c] += 1.0;
        }
      }
    }
    if (result.scored) {
      for (std::size_t k = 0; k < t; ++k) {
        result.routedRmse[k] = std::sqrt(routedSq[k] / static_cast<double>(result.scored));
        result.pooledRmse[k] = std::sqrt(pooledSq[k] / static_cast<double>(result.scored));
        result.intervalCoverage[k] = covered[k] / static_cast<double>(result.scored);
      }
    }

    if (std::getenv("TRECH_DEBUG_LEARNER") && result.scored) {
      std::fprintf(stderr, "[learner-call] %ld leaves=%zu", call, leaves.size());
      for (std::size_t k = 0; k < t; ++k) std::fprintf(stderr, " %s r=%.3g p=%.3g", o.targets[k].c_str(), result.routedRmse[k], result.pooledRmse[k]);
      for (const auto& [id, leaf] : leaves) {
        if (leaf.scoredNow) {
          double e = 0;
          for (std::size_t k = 0; k < t; ++k) e += leaf.sqErrNow[k] / (leaf.yScale.empty() ? 1.0 : leaf.yScale[k] * leaf.yScale[k]);
          std::fprintf(stderr, " | %d n=%zu ext=%zu rows=%zu e=%.3g eout=%.3g ch=%d/%d", id, leaf.scoredNow, leaf.extrapolatedNow,
                       leaf.rows(), std::sqrt(e / leaf.scoredNow),
                       leaf.extrapolatedNow ? std::sqrt(leaf.debugOutsideSq / leaf.extrapolatedNow) : 0.0,
                       leaf.choice[0], leaf.choice[1]);
        }
      }
      std::fprintf(stderr, "\n");
    }
    // Prequential per-domain error, model selection and drift. A frozen
    // learner only grades: nothing that drives its predictions may change.
    for (auto& [id, leaf] : leaves) {
      if (o.frozen || !leaf.scoredNow || !leaf.fitted) continue;
      if (leaf.errSq.empty()) leaf.errSq.assign(t, 0.0);
      double normalized = 0.0, history = 0.0;
      for (std::size_t k = 0; k < t; ++k) {
        const double scale2 = leaf.yScale[k] * leaf.yScale[k];
        if (leaf.errW > 0.0) history += leaf.errSq[k] / leaf.errW / scale2;
        leaf.errSq[k] = leaf.errSq[k] * o.forgetting + leaf.sqErrNow[k];
        normalized += leaf.sqErrNow[k] / static_cast<double>(leaf.scoredNow) / scale2;
      }
      // A change point: the domain's own law errs far beyond its established
      // error on rows inside its envelope, without waiting for a trend
      // history. Judged on the own law, whichever predictor is selected.
      leaf.fastSse = 0.5 * leaf.fastSse + leaf.selNow[0][0];
      leaf.fastCount = 0.5 * leaf.fastCount + leaf.selNowCount[0][0];
      const double ownNow = leaf.fastCount > 0.0 ? leaf.fastSse / leaf.fastCount : 0.0;
      const double ownHistory = leaf.selCount[0][0] > 0.0 ? leaf.selSse[0][0] / leaf.selCount[0][0] : 0.0;
      if (leaf.selCount[0][0] >= static_cast<double>(2 * o.minElements) &&
          leaf.fastCount * 2.0 >= static_cast<double>(o.minElements) &&
          ownNow > o.driftZ * o.driftZ * std::max(ownHistory, o.exactLaw * static_cast<double>(t))) {
        leaf.drift = true;
        leaf.changePoint = true;
        events.push_back({"drift", id, {}, "own-law error jumped " +
                                               std::to_string(ownNow / std::max(ownHistory, 1e-300)) + "x"});
      }
      leaf.errW = leaf.errW * o.forgetting + static_cast<double>(leaf.scoredNow);
      auto& trend = leaf.trends["error"];
      trend.update(batch.time, std::sqrt(normalized / static_cast<double>(t)), o.tendencyDecay);
      if (!leaf.changePoint && trend.updates >= 4 && trend.lastZ > o.driftZ) {
        leaf.drift = true;
        leaf.changePoint = true;
        events.push_back({"drift", id, {}, "prediction error above its forecast (z=" + std::to_string(trend.lastZ) + ")"});
      }
      if (leaf.extrapolatedNow * 5 > leaf.scoredNow && !leaf.drift) {
        leaf.drift = true;
        events.push_back({"drift", id, {}, "population left the domain envelope"});
      }
      selectPredictors(leaf);
      if (leaf.biasRows) {
        for (std::size_t k = 0; k < t; ++k) {
          leaf.trends["bias:" + o.targets[k]].update(batch.time, leaf.biasNow[k] / static_cast<double>(leaf.biasRows),
                                                     o.tendencyDecay);
        }
      }
    }

    if (learning && !learnRows.empty()) {
      std::map<int, std::vector<std::size_t>> learnMembers;
      for (std::size_t i : learnRows) learnMembers[result.predictionDomains[i]].push_back(i);
      for (auto& [id, rows] : learnMembers) {
        Leaf& leaf = leaves.at(id);
        const bool first = !leaf.scaled;
        // Only a forgetting learner treats a change point as a new law; a
        // stationary one keeps its sample and lets the drift force a search.
        if (leaf.changePoint && leaf.rows() && o.forgetting < 1.0) {
          // A change point: rows from before it belong to the old law.
          events.push_back({"reset", id, {}, "dropped " + std::to_string(leaf.rows()) + " pre-drift rows"});
          leaf.xs.clear();
          leaf.ys.clear();
          leaf.calls.clear();
          leaf.seqs.clear();
          for (auto& row : leaf.selSse) row.fill(0.0);
          for (auto& row : leaf.selCount) row.fill(0.0);
          leaf.fastSse = leaf.fastCount = 0.0;
          for (auto it = leaf.trends.begin(); it != leaf.trends.end();) {
            it = it->first.rfind("bias:", 0) == 0 ? leaf.trends.erase(it) : std::next(it);
          }
        }
        addRows(leaf, rows, batch, o.capacity.bufferRows);
        refresh(leaf);
        if (first && leaf.fitted && id == 0) events.push_back({"birth", id, {}, "root domain"});
      }
      addRows(pooled, learnRows, batch, o.capacity.bufferRows);
      refresh(pooled, false);

      // Subdivide where one law cannot explain a domain, then merge back
      // siblings that a single law explains again.
      std::vector<int> ids;
      for (const auto& [id, leaf] : leaves) ids.push_back(id);
      for (int id : ids) {
        if (leaves.size() >= o.capacity.maxDomains) break;
        auto it = leaves.find(id);
        if (it == leaves.end()) continue;
        Leaf& leaf = it->second;
        const bool scheduled = call % static_cast<long>(o.refineEvery) == 0;
        if (!(scheduled || leaf.drift) || !leaf.scoredNow || leaf.depth >= o.maxDepth) continue;
        std::string reason;
        if (auto candidate = searchSplit(leaf, &reason)) split(nodeOfLeaf(id), leaf, *candidate);
      }
      tryMerges();
    }

    // Post-refinement membership.
    for (std::size_t i = 0; i < n; ++i) {
      if (result.predictionDomains[i] >= 0) result.elementDomains[i] = route(&batch.features[i * d]);
    }
    // Recount the current leaves for tendencies and summaries.
    std::map<int, std::size_t> now;
    std::map<int, std::vector<double>> sums, targetSums;
    std::map<int, std::size_t> scoredNow;
    for (std::size_t i = 0; i < n; ++i) {
      const int id = result.elementDomains[i];
      if (id < 0) continue;
      ++now[id];
      auto& sum = sums[id];
      sum.resize(d, 0.0);
      for (std::size_t f = 0; f < d; ++f) sum[f] += batch.features[i * d + f];
      if (!batch.targets.empty()) {
        const double* y = &batch.targets[i * t];
        if (std::all_of(y, y + t, [](double v) { return std::isfinite(v); })) {
          auto& ts = targetSums[id];
          ts.resize(t, 0.0);
          for (std::size_t k = 0; k < t; ++k) ts[k] += y[k];
          ++scoredNow[id];
        }
      }
    }
    for (auto& [id, leaf] : leaves) {
      leaf.elementsNow = now[id];
      leaf.featureSum = sums.count(id) ? sums[id] : std::vector<double>(d, 0.0);
      leaf.targetSum = targetSums.count(id) ? targetSums[id] : std::vector<double>(t, 0.0);
      leaf.scoredNow = scoredNow[id];
      track(leaf, batch.time);
    }
    globalTrends["domains"].update(batch.time, static_cast<double>(leaves.size()), o.tendencyDecay);
    if (result.scored) {
      double gain = 0.0;
      for (std::size_t k = 0; k < t; ++k) {
        globalTrends["routed_rmse:" + o.targets[k]].update(batch.time, result.routedRmse[k], o.tendencyDecay);
        globalTrends["pooled_rmse:" + o.targets[k]].update(batch.time, result.pooledRmse[k], o.tendencyDecay);
        gain += result.pooledRmse[k] > 0.0 ? 1.0 - result.routedRmse[k] / result.pooledRmse[k] : 0.0;
      }
      globalTrends["gain"].update(batch.time, gain / static_cast<double>(t), o.tendencyDecay);
    }
    for (const auto& [name, trend] : globalTrends) result.tendencies.push_back(trend.estimate(name, horizon));
    for (const auto& [id, leaf] : leaves) result.domains.push_back(summarize(leaf));
    result.events = events;
    result.seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    return result;
  }

  // ---- state -----------------------------------------------------------------------

  static nlohmann::json leafModel(const Leaf& leaf) {
    nlohmann::json j = {{"id", leaf.id}, {"depth", leaf.depth}, {"born", leaf.born},
                        {"predecessors", leaf.predecessors}, {"fitted", leaf.fitted}};
    if (leaf.scaled) {
      j["x_mean"] = leaf.xMean; j["x_scale"] = leaf.xScale;
      j["y_mean"] = leaf.yMean; j["y_scale"] = leaf.yScale;
      j["z_lo"] = leaf.zLo; j["z_hi"] = leaf.zHi;
      if (!leaf.yLo.empty()) { j["y_lo"] = leaf.yLo; j["y_hi"] = leaf.yHi; }
      if (!leaf.centers.empty()) { j["support_centers"] = leaf.centers; j["support_radius"] = leaf.supportRadius; }
    }
    if (leaf.fitted) {
      j["beta"] = leaf.beta;
      j["residual_std"] = leaf.residualStd;
      j["model"] = modelName(leaf);
      j["choice"] = {leaf.choice[0], leaf.choice[1]};
      if (leaf.mlp) j["residual_network"] = leaf.mlp->toJson();
    }
    return j;
  }

  void loadLeaf(Leaf& leaf, const nlohmann::json& j) {
    leaf.id = j.at("id").get<int>();
    leaf.depth = j.at("depth").get<std::size_t>();
    leaf.born = j.at("born").get<long>();
    leaf.predecessors = j.at("predecessors").get<std::vector<int>>();
    leaf.fitted = j.at("fitted").get<bool>();
    if (j.contains("x_mean")) {
      leaf.scaled = true;
      leaf.xMean = j.at("x_mean").get<std::vector<double>>();
      leaf.xScale = j.at("x_scale").get<std::vector<double>>();
      leaf.yMean = j.at("y_mean").get<std::vector<double>>();
      leaf.yScale = j.at("y_scale").get<std::vector<double>>();
      leaf.zLo = j.at("z_lo").get<std::vector<double>>();
      leaf.zHi = j.at("z_hi").get<std::vector<double>>();
      if (j.contains("support_centers")) {
        leaf.centers = j.at("support_centers").get<std::vector<double>>();
        leaf.supportRadius = j.at("support_radius").get<double>();
        if (leaf.centers.empty() || leaf.centers.size() % d || !(leaf.supportRadius > 0.0)) {
          throw std::invalid_argument("domain learner support set is malformed");
        }
      }
      if (j.contains("y_lo")) {
        leaf.yLo = j.at("y_lo").get<std::vector<double>>();
        leaf.yHi = j.at("y_hi").get<std::vector<double>>();
        if (leaf.yLo.size() != t || leaf.yHi.size() != t) {
          throw std::invalid_argument("domain learner leaf target range size mismatch");
        }
      }
      if (leaf.xMean.size() != d || leaf.xScale.size() != d || leaf.zLo.size() != d ||
          leaf.zHi.size() != d || leaf.yMean.size() != t || leaf.yScale.size() != t) {
        throw std::invalid_argument("domain learner leaf scaler size mismatch");
      }
    }
    if (leaf.fitted) {
      leaf.beta = j.at("beta").get<std::vector<double>>();
      leaf.residualStd = j.at("residual_std").get<std::vector<double>>();
      if (leaf.beta.size() != p * t || leaf.residualStd.size() != t || !leaf.scaled) {
        throw std::invalid_argument("domain learner leaf model size mismatch");
      }
      if (j.contains("choice")) {
        const auto choice = j.at("choice").get<std::vector<int>>();
        if (choice.size() != 2 || choice[0] < 0 || choice[0] > 3 || choice[1] < 0 || choice[1] > 3) {
          throw std::invalid_argument("domain learner predictor choice is malformed");
        }
        leaf.choice = {choice[0], choice[1]};
      }
      if (j.contains("residual_network")) leaf.mlp = Mlp::fromJson(j.at("residual_network"), d, t);
      if ((leaf.choice[0] == 1 || leaf.choice[1] == 1) && !leaf.mlp) {
        throw std::invalid_argument("ridge+mlp choice without a residual network");
      }
    }
    leaf.cooldownUntil = 0;
    if (j.contains("rows")) {
      const auto& rows = j.at("rows");
      leaf.xs = rows.at("x").get<std::vector<double>>();
      leaf.ys = rows.at("y").get<std::vector<double>>();
      leaf.calls = rows.at("call").get<std::vector<long>>();
      leaf.seqs = rows.at("seq").get<std::vector<std::uint64_t>>();
      leaf.seen = std::max<std::uint64_t>(rows.value("seen", std::uint64_t{0}), leaf.calls.size());
      if (leaf.xs.size() != leaf.calls.size() * d || leaf.ys.size() != leaf.calls.size() * t ||
          leaf.seqs.size() != leaf.calls.size() || leaf.calls.size() > o.capacity.bufferRows) {
        throw std::invalid_argument("domain learner buffered rows are malformed");
      }
    }
  }
};

DomainLearner::DomainLearner(DomainLearnerOptions options)
    : impl_(std::make_unique<Impl>(std::move(options))) {}
DomainLearner::~DomainLearner() = default;
DomainLearner::DomainLearner(DomainLearner&&) noexcept = default;
DomainLearner& DomainLearner::operator=(DomainLearner&&) noexcept = default;

DomainLearnerResult DomainLearner::update(const DomainLearnerBatch& batch) { return impl_->update(batch); }
std::vector<double> DomainLearner::predict(const std::vector<double>& features, std::size_t count, double time,
                                           std::vector<double>* remoteness) const {
  const auto& s = *impl_;
  if (features.size() != count * s.d) throw std::invalid_argument("domain learner predict does not match its features");
  std::vector<double> out(count * s.t, std::numeric_limits<double>::quiet_NaN());
  if (remoteness) remoteness->assign(count, std::numeric_limits<double>::infinity());
  std::vector<double> value(s.t), alt(4 * s.t);
  std::array<bool, 4> available{};
  for (std::size_t i = 0; i < count; ++i) {
    const double* x = &features[i * s.d];
    if (!std::all_of(x, x + s.d, [](double v) { return std::isfinite(v); })) continue;
    bool outside = false;
    const auto& leaf = s.leaves.at(s.route(x));
    if (s.predict(leaf, x, time, value.data(), alt.data(), &available, &outside))
      std::copy(value.begin(), value.end(), out.begin() + static_cast<std::ptrdiff_t>(i * s.t));
    // Remoteness of the row from the support of the law that predicted it (1 = far: half a
    // span past its box or three support radii from its joint support).
    if (remoteness && available[0]) (*remoteness)[i] = std::max(s.excess(leaf, x) / 0.5, s.jointRatio(leaf, x) / 3.0);
    else if (remoteness && available[2]) (*remoteness)[i] = std::max(s.excess(s.pooled, x) / 0.5, s.jointRatio(s.pooled, x) / 3.0);
  }
  return out;
}
const DomainLearnerOptions& DomainLearner::options() const { return impl_->o; }
long DomainLearner::calls() const { return impl_->call; }

nlohmann::json DomainLearner::exportState(bool includeRows) const {
  const auto& s = *impl_;
  nlohmann::json nodes = nlohmann::json::array();
  // Compact live nodes, renumbering children.
  std::map<int, int> renumber;
  std::vector<int> order;
  std::vector<int> stack{0};
  while (!stack.empty()) {
    const int n = stack.back();
    stack.pop_back();
    renumber[n] = static_cast<int>(order.size());
    order.push_back(n);
    if (!s.nodes[static_cast<std::size_t>(n)].leaf) {
      stack.push_back(s.nodes[static_cast<std::size_t>(n)].right);
      stack.push_back(s.nodes[static_cast<std::size_t>(n)].left);
    }
  }
  for (int n : order) {
    const auto& node = s.nodes[static_cast<std::size_t>(n)];
    if (node.leaf) nodes.push_back({{"leaf", node.leafId}});
    else nodes.push_back({{"direction", node.direction}, {"threshold", node.threshold},
                          {"left", renumber.at(node.left)}, {"right", renumber.at(node.right)}});
  }
  nlohmann::json leaves = nlohmann::json::array();
  for (const auto& [id, leaf] : s.leaves) {
    leaves.push_back(Impl::leafModel(leaf));
    if (includeRows) {
      leaves.back()["rows"] = {{"x", leaf.xs}, {"y", leaf.ys}, {"call", leaf.calls}, {"seq", leaf.seqs},
                               {"seen", leaf.seen}};
    }
  }
  nlohmann::json lineage = nlohmann::json::array();
  for (const auto& [id, entry] : s.lineage) {
    lineage.push_back({{"id", id}, {"predecessors", entry.predecessors}, {"born", entry.born},
                       {"retired", entry.retired}, {"depth", entry.depth}});
  }
  const auto& o = s.o;
  return {{"schema", "trech_domain_learner_v1"},
          {"features", o.features},
          {"targets", o.targets},
          {"options", {{"min_elements", o.minElements}, {"max_depth", o.maxDepth},
                       {"forgetting", o.forgetting}, {"ridge", o.ridge}, {"exact_law", o.exactLaw},
                       {"split_penalty", o.splitPenalty}, {"min_gain", o.minGain},
                       {"min_support_calls", o.minSupportCalls}, {"refine_every", o.refineEvery},
                       {"merge_cooldown", o.mergeCooldown}, {"tendency_decay", o.tendencyDecay},
                       {"drift_z", o.driftZ}, {"seed", o.seed},
                       {"tendency_predictor", o.tendencyPredictor}}},
          {"capacity", o.capacity.toJson()},
          {"budget", o.budget.toJson()},
          {"calls", s.call},
          {"next_id", s.nextId},
          {"nodes", nodes},
          {"leaves", leaves},
          {"pooled", [&] {
             auto pooled = Impl::leafModel(s.pooled);
             if (includeRows) {
               pooled["rows"] = {{"x", s.pooled.xs}, {"y", s.pooled.ys}, {"call", s.pooled.calls},
                                 {"seq", s.pooled.seqs}, {"seen", s.pooled.seen}};
             }
             return pooled;
           }()},
          {"seq", s.seq},
          {"lineage", lineage}};
}

DomainLearner DomainLearner::fromState(const nlohmann::json& state, bool frozen) {
  if (!state.is_object() || state.value("schema", std::string()) != "trech_domain_learner_v1") {
    throw std::invalid_argument("not a trech_domain_learner_v1 state");
  }
  DomainLearnerOptions o;
  o.features = state.at("features").get<std::vector<std::string>>();
  o.targets = state.at("targets").get<std::vector<std::string>>();
  const auto& opt = state.at("options");
  o.minElements = opt.at("min_elements").get<std::size_t>();
  o.maxDepth = opt.at("max_depth").get<std::size_t>();
  o.forgetting = opt.at("forgetting").get<double>();
  o.ridge = opt.at("ridge").get<double>();
  o.exactLaw = opt.value("exact_law", o.exactLaw);
  o.splitPenalty = opt.at("split_penalty").get<double>();
  o.minGain = opt.at("min_gain").get<double>();
  o.minSupportCalls = opt.at("min_support_calls").get<std::size_t>();
  o.refineEvery = opt.at("refine_every").get<std::size_t>();
  o.mergeCooldown = opt.at("merge_cooldown").get<std::size_t>();
  o.tendencyDecay = opt.at("tendency_decay").get<double>();
  o.driftZ = opt.at("drift_z").get<double>();
  o.tendencyPredictor = opt.value("tendency_predictor", true);
  o.seed = opt.at("seed").get<std::uint64_t>();
  const auto& cap = state.at("capacity");
  o.capacity.maxDomains = cap.at("max_domains").get<std::size_t>();
  o.capacity.bufferRows = cap.at("buffer_rows").get<std::size_t>();
  o.capacity.splitCandidates = cap.at("split_candidates").get<std::size_t>();
  o.capacity.basisDegree = cap.at("basis_degree").get<int>();
  o.capacity.residualHidden = cap.at("residual_hidden").get<std::size_t>();
  o.capacity.residualSteps = cap.at("residual_steps").get<std::size_t>();
  o.capacity.specialistWidth = cap.value("specialist_width", std::size_t{32});
  o.capacity.specialistEpochs = cap.value("specialist_epochs", std::size_t{600});
  o.budget = ComputeBudget::fromJson(state.at("budget"));
  o.frozen = frozen;
  DomainLearner learner(o);
  auto& s = *learner.impl_;
  s.leaves.clear();
  s.lineage.clear();
  s.nodes.clear();
  s.call = state.at("calls").get<long>();
  s.nextId = state.at("next_id").get<int>();
  s.seq = state.value("seq", std::uint64_t{0});
  std::set<int> leafIds;
  for (const auto& j : state.at("leaves")) {
    Leaf leaf;
    s.loadLeaf(leaf, j);
    if (leaf.id < 0 || leaf.id >= s.nextId || !leafIds.insert(leaf.id).second) {
      throw std::invalid_argument("domain learner leaf ids are invalid");
    }
    const int id = leaf.id;
    s.leaves.emplace(id, std::move(leaf));
  }
  const auto& nodes = state.at("nodes");
  std::set<int> referenced;
  for (const auto& j : nodes) {
    Node node;
    if (j.contains("leaf")) {
      node.leafId = j.at("leaf").get<int>();
      if (!s.leaves.count(node.leafId) || !referenced.insert(node.leafId).second) {
        throw std::invalid_argument("domain learner node references an unknown leaf");
      }
    } else {
      node.leaf = false;
      node.direction = j.at("direction").get<std::vector<double>>();
      node.threshold = j.at("threshold").get<double>();
      node.left = j.at("left").get<int>();
      node.right = j.at("right").get<int>();
      if (node.direction.size() != s.d || node.left <= 0 || node.right <= 0 ||
          node.left >= static_cast<int>(nodes.size()) || node.right >= static_cast<int>(nodes.size())) {
        throw std::invalid_argument("domain learner split node is malformed");
      }
    }
    s.nodes.push_back(node);
  }
  if (s.nodes.empty() || referenced.size() != s.leaves.size()) {
    throw std::invalid_argument("domain learner tree does not cover its leaves");
  }
  s.loadLeaf(s.pooled, state.at("pooled"));
  for (const auto& j : state.at("lineage")) {
    s.lineage[j.at("id").get<int>()] = {j.at("predecessors").get<std::vector<int>>(),
                                        j.at("born").get<long>(), j.at("retired").get<long>(),
                                        j.at("depth").get<std::size_t>()};
  }
  return learner;
}

}  // namespace trech::ml
