#include "trech/ml/FieldEvolution.hpp"

#include "trech/ml/ComputeBudget.hpp"
#include "trech/ml/MethodArbiter.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace trech::ml {
namespace {

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
// Method-independent context of a cell over the coming interval, in field-span units:
//   diffusive_drive   kappa * sum_j G_ij (v_j - v_i) / V_i * interval  (face conductance G)
//   exchange_drive    (1 - exp(-rate * interval)) * (target - v)
//   load_drive        load * interval
//   recent_change     v - (v at the previous call)
//   field_level       v - mean initial value
//   exposed_fraction  share of the cell's faces not shared with another declared cell
const std::vector<std::string> kContext = {"diffusive_drive", "exchange_drive", "load_drive",
                                           "recent_change", "field_level", "exposed_fraction"};

double overlap1(double a0, double a1, double b0, double b1) { return std::max(0.0, std::min(a1, b1) - std::max(a0, b0)); }

// Face adjacency of axis-aligned cells (touching along one axis, overlapping in the other two).
void buildAdjacency(FieldSystem& sys) {
  const std::size_t C = sys.cells();
  sys.links.assign(C, {});
  sys.volumeMm3.assign(C, 0.0);
  sys.exposedFraction.assign(C, 1.0);
  std::vector<double> faceArea(C, 0.0), shared(C, 0.0);
  for (std::size_t i = 0; i < C; ++i) {
    const auto &a0 = sys.cellMin[i], &a1 = sys.cellMax[i];
    const double ex = a1[0] - a0[0], ey = a1[1] - a0[1], ez = a1[2] - a0[2];
    sys.volumeMm3[i] = ex * ey * ez;
    faceArea[i] = 2 * (ex * ey + ey * ez + ex * ez);
  }
  for (std::size_t i = 0; i < C; ++i) {
    const auto &a0 = sys.cellMin[i], &a1 = sys.cellMax[i];
    for (std::size_t j = i + 1; j < C; ++j) {
      const auto &b0 = sys.cellMin[j], &b1 = sys.cellMax[j];
      for (int axis = 0; axis < 3; ++axis) {
        const auto ax = static_cast<std::size_t>(axis);
        const double tol = 1e-9 * std::max(1.0, std::abs(a1[ax]) + std::abs(b1[ax]));
        if (std::abs(a1[ax] - b0[ax]) > tol && std::abs(b1[ax] - a0[ax]) > tol) continue;
        const auto u = static_cast<std::size_t>((axis + 1) % 3), w = static_cast<std::size_t>((axis + 2) % 3);
        const double area = overlap1(a0[u], a1[u], b0[u], b1[u]) * overlap1(a0[w], a1[w], b0[w], b1[w]);
        if (area <= 0) continue;
        double d2 = 0;
        for (std::size_t k = 0; k < 3; ++k) {
          const double dc = 0.5 * (a0[k] + a1[k]) - 0.5 * (b0[k] + b1[k]);
          d2 += dc * dc;
        }
        const double g = area / std::sqrt(d2);
        sys.links[i].push_back({j, g});
        sys.links[j].push_back({i, g});
        shared[i] += area; shared[j] += area;
        break;
      }
    }
  }
  for (std::size_t i = 0; i < C; ++i) sys.exposedFraction[i] = std::clamp(1.0 - shared[i] / faceArea[i], 0.0, 1.0);
}

}  // namespace

struct FieldEvolution::Impl {
  FieldSystem sys;
  bool built = false;
  struct Candidate {
    std::string name, family;
    std::unique_ptr<FieldMethod> method;
  };
  std::vector<Candidate> candidates;
  nlohmann::json excluded = nlohmann::json::object();  // registered but not applicable: reason
  std::vector<std::string> features;
  std::unique_ptr<MethodArbiter> arbiter;
  std::vector<double> state, previousState;
  double previousTime = kNaN;
  long calls = 0;

  std::vector<double> context(const FieldEvolutionInput& in, double interval) const {
    const std::size_t C = sys.cells(), F = kContext.size();
    std::vector<double> out(C * F, 0.0);
    const double kappaMm2 = sys.properties.diffusivityM2S * 1e6, inv = 1.0 / sys.span;
    for (std::size_t c = 0; c < C; ++c) {
      double flux = 0;
      for (const auto& l : sys.links[c]) flux += l.conductanceMm * (state[l.other] - state[c]);
      const double rate = c < in.rate.size() ? in.rate[c] : 0.0;
      const double target = c < in.target.size() ? in.target[c] : sys.offset;
      double* row = &out[c * F];
      row[0] = kappaMm2 * flux / sys.volumeMm3[c] * interval * inv;
      row[1] = rate > 0 ? -std::expm1(-rate * interval) * (target - state[c]) * inv : 0.0;
      row[2] = (c < in.loadPerS.size() ? in.loadPerS[c] : 0.0) * interval * inv;
      row[3] = (state[c] - previousState[c]) * inv;
      row[4] = (state[c] - sys.offset) * inv;
      row[5] = sys.exposedFraction[c];
    }
    return out;
  }

  void build(const FieldEvolutionInput& in) {
    double lo = std::numeric_limits<double>::infinity(), hi = -lo;
    for (std::size_t c = 0; c < sys.cells(); ++c) {
      lo = std::min(lo, sys.initial[c]); hi = std::max(hi, sys.initial[c]);
      if (c < in.rate.size() && in.rate[c] > 0 && c < in.target.size()) { lo = std::min(lo, in.target[c]); hi = std::max(hi, in.target[c]); }
    }
    sys.span = hi > lo ? hi - lo : 1.0;
    sys.contextNames = kContext;
    buildAdjacency(sys);
    features = kContext;
    for (const auto& entry : fieldMethodRegistry()) {
      auto method = entry.make();
      const std::string reason = method->build(sys, in);
      if (!reason.empty()) { excluded[entry.name] = {{"family", entry.family}, {"reason", reason}}; continue; }
      for (const auto& d : method->descriptorNames()) features.push_back(entry.name + "." + d);
      candidates.push_back({entry.name, entry.family, std::move(method)});
    }
    if (candidates.empty()) throw std::runtime_error("no field method can represent the declared system");
    MethodArbiterOptions o;
    for (const auto& c : candidates) o.methods.push_back(c.name);
    o.features = features;
    o.fallback = std::find(o.methods.begin(), o.methods.end(), "persistence") != o.methods.end() ? "persistence" : "";
    o.minElements = sys.options.minElements;
    o.seed = sys.options.seed;
    arbiter = std::make_unique<MethodArbiter>(o);
    built = true;
  }
};

std::vector<std::string> FieldEvolution::methodNames() {
  std::vector<std::string> out;
  for (const auto& e : fieldMethodRegistry()) out.push_back(e.name);
  return out;
}
const std::vector<std::string>& FieldEvolution::contextNames() { return kContext; }

FieldEvolution::FieldEvolution(FieldRegion region, std::vector<std::array<double, 3>> cellMin,
                               std::vector<std::array<double, 3>> cellMax, FieldProperties properties,
                               std::vector<double> initialValues, FieldEvolutionOptions options)
    : impl_(std::make_unique<Impl>()) {
  auto& s = *impl_;
  if (region.shape != "box" && region.shape != "cylinder") throw std::invalid_argument("region.shape must be box or cylinder");
  if (region.shape == "cylinder" && !(region.radiusMm > 0 && region.lengthMm > 0)) throw std::invalid_argument("cylinder needs radius and length");
  if (region.shape == "box" && !(region.sizeMm[0] > 0 && region.sizeMm[1] > 0 && region.sizeMm[2] > 0)) throw std::invalid_argument("box needs a positive size");
  if (cellMin.empty() || cellMin.size() != cellMax.size() || initialValues.size() != cellMin.size())
    throw std::invalid_argument("field cells and initial values must have equal, nonzero length");
  for (std::size_t c = 0; c < cellMin.size(); ++c)
    for (std::size_t a = 0; a < 3; ++a)
      if (!(cellMax[c][a] > cellMin[c][a])) throw std::invalid_argument("every field cell needs max > min");
  for (double v : initialValues) if (!std::isfinite(v)) throw std::invalid_argument("initial values must be finite");
  if (!(options.cellMm > 0) || !(options.machTarget > 0) || !(options.twinRatio > 1) || !(options.conductiveTau > 0.5))
    throw std::invalid_argument("invalid field-evolution options");
  s.sys.region = region; s.sys.cellMin = std::move(cellMin); s.sys.cellMax = std::move(cellMax);
  s.sys.properties = properties; s.sys.initial = std::move(initialValues); s.sys.options = options;
  double sum = 0;
  for (double v : s.sys.initial) sum += v;
  s.sys.offset = sum / static_cast<double>(s.sys.initial.size());
  s.state = s.previousState = s.sys.initial;
}

FieldEvolution::~FieldEvolution() = default;
FieldEvolution::FieldEvolution(FieldEvolution&&) noexcept = default;
FieldEvolution& FieldEvolution::operator=(FieldEvolution&&) noexcept = default;

nlohmann::json FieldEvolution::step(const FieldEvolutionInput& in) {
  auto& s = *impl_;
  const std::size_t C = s.sys.cells();
  for (const auto* v : {&in.rate, &in.target, &in.loadPerS, &in.reference})
    if (!v->empty() && v->size() != C) throw std::invalid_argument("per-cell arrays must match the field cells");
  if (!s.built) s.build(in);
  if (!std::isfinite(s.previousTime)) s.previousTime = in.timeS;
  const double interval = std::max(0.0, in.timeS - s.previousTime);
  const auto context = s.context(in, interval);
  const FieldCall call{in, s.previousTime, s.state, context};
  ++s.calls;
  for (auto& c : s.candidates) c.method->advance(call);
  // Arbitration batch: context + candidate descriptors per cell; one prediction per candidate.
  const std::size_t M = s.candidates.size(), F = s.features.size(), F0 = kContext.size();
  MethodArbiterBatch batch;
  batch.time = in.timeS; batch.count = C;
  batch.features.assign(C * F, 0.0);
  batch.predictions.assign(C * M, kNaN);
  std::vector<std::vector<double>> pred(M);
  std::size_t column = F0;
  for (std::size_t m = 0; m < M; ++m) {
    pred[m] = s.candidates[m].method->prediction();
    for (std::size_t c = 0; c < C; ++c) batch.predictions[c * M + m] = pred[m][c];
    const auto names = s.candidates[m].method->descriptorNames();
    if (names.empty()) continue;
    const auto d = s.candidates[m].method->descriptors();
    for (std::size_t c = 0; c < C; ++c)
      for (std::size_t f = 0; f < names.size(); ++f) batch.features[c * F + column + f] = d[c * names.size() + f];
    column += names.size();
  }
  for (std::size_t c = 0; c < C; ++c)
    for (std::size_t f = 0; f < F0; ++f) batch.features[c * F + f] = context[c * F0 + f];
  const bool graded = !in.reference.empty();
  if (graded) batch.reference = in.reference;
  batch.scale = {s.sys.span};
  const auto r = s.arbiter->step(batch);
  // Report.
  nlohmann::json methods = nlohmann::json::object();
  for (std::size_t m = 0; m < M; ++m) {
    auto rep = s.candidates[m].method->report();
    rep["available"] = true;
    rep["field"] = pred[m];
    rep["rmse"] = r.callRmse[m];
    methods[s.candidates[m].name] = rep;
  }
  for (const auto& [name, why] : s.excluded.items())
    methods[name] = {{"available", false}, {"family", why.at("family")}, {"reason", why.at("reason")}};
  std::vector<std::string> selection;
  for (int k : r.selection) selection.push_back(k >= 0 ? s.candidates[static_cast<std::size_t>(k)].name : std::string());
  // One-step-ahead competition: every method predicts the next interval from the same observed
  // state, so after grading each method observes the reference (lattices are nudged to its cell
  // means, learned methods learn the transition). Without a reference the engine's own
  // arbitrated field becomes the state.
  s.previousState = s.state;
  if (graded) {
    for (auto& c : s.candidates) c.method->observe(call, in.reference);
    for (std::size_t c = 0; c < C; ++c) s.state[c] = std::isfinite(in.reference[c]) ? in.reference[c] : r.value[c];
  } else {
    for (std::size_t c = 0; c < C; ++c) if (std::isfinite(r.value[c])) s.state[c] = r.value[c];
  }
  s.previousTime = in.timeS;
  nlohmann::json out = {{"time_s", in.timeS}, {"call", s.calls}, {"graded", graded}, {"field", r.value},
                        {"selection", selection}, {"arbitrated_rmse", r.arbitratedRmse}, {"oracle_rmse", r.oracleRmse},
                        {"methods", methods}, {"arbitration", graded ? r.report : nlohmann::json(nullptr)}};
  // Kept for readers of the earlier emit: the convective lattice's twin evidence.
  if (methods.contains("lattice_convective") && methods["lattice_convective"].contains("self_consistency"))
    out["self_consistency"] = methods["lattice_convective"]["self_consistency"];
  return out;
}

nlohmann::json FieldEvolution::summary() const {
  const auto& s = *impl_;
  if (!s.built) return {{"calls", s.calls}};
  auto out = s.arbiter->summary();
  out["context_features"] = s.features;
  for (const auto& c : s.candidates) {
    auto m = c.method->summary();
    m["available"] = true;
    m.update(out["methods"][c.name]);
    out["methods"][c.name] = m;
  }
  for (const auto& [name, why] : s.excluded.items())
    out["methods"][name] = {{"available", false}, {"family", why.at("family")}, {"reason", why.at("reason")}};
  out["registered_methods"] = methodNames();
  // Learner capacities derive from it; a run is reproducible only under the same budget.
  out["compute_budget"] = hostComputeBudget().toJson();
  out["graded_cells"] = out["graded_elements"];
  if (out["methods"].contains("lattice_convective")) {
    const auto& lc = out["methods"]["lattice_convective"];
    if (lc.contains("twin")) out["twin"] = lc["twin"];
    if (lc.contains("self_consistency_series")) out["self_consistency_series"] = lc["self_consistency_series"];
  }
  return out;
}

}  // namespace trech::ml
