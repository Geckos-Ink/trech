#include "trech/ml/FieldMethods.hpp"

#include "trech/core/LatticeContinuum.hpp"
#include "trech/ml/ComputeBudget.hpp"
#include "trech/ml/DomainLearner.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <mutex>
#include <stdexcept>

namespace trech::ml {
namespace {

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
constexpr double kPi = 3.14159265358979323846;
const std::vector<std::string> kLatticeDescriptors = {"cell_peclet", "cell_reynolds", "mach", "scalar_step",
                                                      "velocity_curvature", "wall_distance"};

double overlap1(double a0, double a1, double b0, double b1) { return std::max(0.0, std::min(a1, b1) - std::max(a0, b0)); }

double nanMean(const std::vector<double>& v) {
  double s = 0; std::size_t n = 0;
  for (double x : v) if (std::isfinite(x)) { s += x; ++n; }
  return n ? s / static_cast<double>(n) : kNaN;
}

// One lattice Boltzmann realisation of the declared region (the method's state).
struct LatticeRun {
  bool available = false, failed = false;
  std::string reason;
  std::unique_ptr<lattice::Lattice> lattice;
  double dxM = 0.0, dt = 0.0, time = 0.0, velocityScale = 0.0, freeFall = 0.0;
  // Per lattice cell: (field cell, volume fraction of the lattice cell inside that field cell).
  std::vector<std::vector<std::pair<int, double>>> toField;
  std::vector<double> fieldVolume;  // per field cell: fluid lattice volume inside it (cell units)
  std::vector<double> lastField;
  nlohmann::json info;
};

// Lattice geometry of the declared region at cell size dxMm.
void geometry(const FieldRegion& region, double dxMm, std::array<int, 3>& shape,
              std::function<bool(int, int, int)>& solid, std::array<double, 3>& origin) {
  if (region.shape == "cylinder") {
    const int nxy = std::max(2, static_cast<int>(std::ceil(2 * region.radiusMm / dxMm)));
    const int nz = std::max(4, static_cast<int>(std::lround(region.lengthMm / dxMm)));
    shape = {nxy, nxy, nz};
    origin = {-region.radiusMm, -region.radiusMm, 0.0};
    const double R = region.radiusMm;
    solid = [=](int x, int y, int) { return std::hypot((x + 0.5) * dxMm - R, (y + 0.5) * dxMm - R) > R; };
  } else {
    shape = {std::max(1, static_cast<int>(std::lround(region.sizeMm[0] / dxMm))),
             std::max(1, static_cast<int>(std::lround(region.sizeMm[1] / dxMm))),
             std::max(1, static_cast<int>(std::lround(region.sizeMm[2] / dxMm)))};
    origin = {0, 0, 0};
    solid = nullptr;
  }
}

int gravityAxis(const FieldProperties& p, double& magnitude) {
  int axis = -1; magnitude = 0;
  for (int a = 0; a < 3; ++a) {
    const double g = p.bodyAccelerationM2S[static_cast<std::size_t>(a)];
    if (g == 0.0) continue;
    if (axis >= 0) return -2;  // not axis-aligned
    axis = a; magnitude = g;
  }
  return axis;
}

std::vector<double> fieldOf(const FieldSystem& sys, LatticeRun& m) {
  const auto& T = m.lattice->scalarValues();
  std::vector<double> sum(sys.cells(), 0.0);
  for (std::size_t i = 0; i < m.toField.size(); ++i)
    for (const auto& [c, w] : m.toField[i]) sum[static_cast<std::size_t>(c)] += w * T[i];
  std::vector<double> out(sys.cells(), kNaN);
  for (std::size_t c = 0; c < sys.cells(); ++c) if (m.fieldVolume[c] > 0) out[c] = sys.offset + sum[c] / m.fieldVolume[c];
  return out;
}

// Build one lattice. `flow` selects convective (D3Q19 + D3Q7, Boussinesq) vs conductive numerics.
void buildLattice(const FieldSystem& sys, LatticeRun& m, double dxMm, bool flow) {
  const auto& props = sys.properties;
  const auto& opt = sys.options;
  m.dxM = dxMm * 1e-3;
  std::array<int, 3> shape{}; std::function<bool(int, int, int)> solid; std::array<double, 3> origin{};
  geometry(sys.region, dxMm, shape, solid, origin);
  const double nu = props.kinematicViscosityM2S, kappa = props.diffusivityM2S;
  if (!(kappa > 0)) { m.reason = "no positive scalar diffusivity declared"; return; }
  lattice::LatticeSpec s;
  s.shape = shape; s.solid = solid;
  double g = 0;
  const int axis = gravityAxis(props, g);
  if (flow) {
    if (!(nu > 0)) { m.reason = "no positive kinematic viscosity declared"; return; }
    if (axis == -2) { m.reason = "body acceleration is not axis-aligned"; return; }
    const double extent = axis >= 0 ? shape[static_cast<std::size_t>(axis)] * m.dxM : 0.0;
    m.freeFall = axis >= 0 ? std::sqrt(std::abs(g * props.expansionPerUnit) * sys.span * extent) : 0.0;
    double dt = 0.5 * m.dxM * m.dxM / nu;  // tau <= 2
    if (m.freeFall > 0) dt = std::min(dt, opt.machTarget * std::sqrt(1.0 / 3.0) * m.dxM / m.freeFall);
    s.tau = 0.5 + 3.0 * nu * dt / (m.dxM * m.dxM);
    if (!(s.tau - 0.5 > 1e-6)) { m.reason = "lattice cannot represent this viscosity at this cell"; return; }
    s.diffusivity = kappa * dt / (m.dxM * m.dxM);
    if (axis >= 0) {
      s.buoyancyAxis = axis;
      s.buoyancyCoefficient = -props.expansionPerUnit * g * dt * dt / m.dxM;
      s.meanReference = true;  // a uniformly warming closed region carries no net body force
    }
    m.dt = dt;
  } else {
    s.flow = false;
    s.diffusivity = 0.25 * (opt.conductiveTau - 0.5);
    m.dt = s.diffusivity * m.dxM * m.dxM / kappa;
  }
  if (!(s.diffusivity > 0)) { m.reason = "lattice cannot represent this diffusivity at this cell"; return; }
  // Seed-derived horizontal tilt (1e-5 of the span) breaks the lattice's mirror symmetry the
  // way any real perturbation would; deterministic per run seed.
  const double angle = 2 * kPi * static_cast<double>(opt.seed % 3600) / 3600.0;
  // Initial lattice values: volume-weighted field values of the overlapping field cells.
  lattice::Domain probe(shape, solid);
  std::vector<double> init(probe.count(), 0.0);
  m.toField.assign(probe.count(), {});
  m.fieldVolume.assign(sys.cells(), 0.0);
  for (std::size_t i = 0; i < probe.count(); ++i) {
    const double x0 = origin[0] + probe.x[i] * dxMm, y0 = origin[1] + probe.y[i] * dxMm, z0 = origin[2] + probe.z[i] * dxMm;
    double wsum = 0, vsum = 0;
    for (std::size_t c = 0; c < sys.cells(); ++c) {
      const double v = overlap1(x0, x0 + dxMm, sys.cellMin[c][0], sys.cellMax[c][0]) *
                       overlap1(y0, y0 + dxMm, sys.cellMin[c][1], sys.cellMax[c][1]) *
                       overlap1(z0, z0 + dxMm, sys.cellMin[c][2], sys.cellMax[c][2]) / (dxMm * dxMm * dxMm);
      if (v <= 0) continue;
      m.toField[i].push_back({static_cast<int>(c), v});
      m.fieldVolume[c] += v;
      wsum += v; vsum += v * (sys.initial[c] - sys.offset);
    }
    init[i] = wsum > 0 ? vsum / wsum : 0.0;
    const int horizontal[2] = {axis == 0 ? 1 : 0, axis == 2 || axis < 0 ? 1 : 2};
    const double h0 = (horizontal[0] == 0 ? probe.x[i] : probe.y[i]) + 0.5 - 0.5 * shape[static_cast<std::size_t>(horizontal[0])];
    const double h1 = (horizontal[1] == 1 ? probe.y[i] : probe.z[i]) + 0.5 - 0.5 * shape[static_cast<std::size_t>(horizontal[1])];
    init[i] += 1e-5 * sys.span * (std::cos(angle) * h0 + std::sin(angle) * h1) / std::max(1, shape[0]);
  }
  s.initialScalar = [&](int x, int y, int z) { return init[static_cast<std::size_t>(probe.at(x, y, z))]; };
  try {
    m.lattice = std::make_unique<lattice::Lattice>(s);
  } catch (const std::exception& e) {
    m.reason = std::string("lattice construction failed: ") + e.what();
    return;
  }
  m.available = true;
  m.velocityScale = m.dxM / m.dt;
  m.lastField = fieldOf(sys, m);
  m.info = {{"cell_mm", dxMm}, {"shape", shape}, {"fluid_cells", m.lattice->domain().count()}, {"dt_s", m.dt},
            {"tau", flow ? s.tau : kNaN}, {"scalar_diffusivity_lattice", s.diffusivity},
            {"free_fall_velocity_m_s", m.freeFall}, {"field_span", sys.span}};
}

void advanceLattice(const FieldSystem& sys, LatticeRun& m, const FieldEvolutionInput& in) {
  if (!m.available || m.failed) return;
  const auto steps = static_cast<std::uint64_t>(std::max(0.0, std::floor((in.timeS - m.time) / m.dt + 1e-9)));
  auto& rate = m.lattice->rate(); auto& target = m.lattice->target(); auto& constant = m.lattice->constant();
  for (std::size_t i = 0; i < m.toField.size(); ++i) {
    double r = 0, rt = 0, k = 0;
    for (const auto& [c, w] : m.toField[i]) {
      const auto cc = static_cast<std::size_t>(c);
      if (cc < in.rate.size() && in.rate[cc] > 0) {
        r += w * in.rate[cc] * m.dt;
        rt += w * in.rate[cc] * m.dt * ((cc < in.target.size() ? in.target[cc] : sys.offset) - sys.offset);
      }
      if (cc < in.loadPerS.size()) k += w * in.loadPerS[cc] * m.dt;
    }
    rate[i] = r; target[i] = r > 0 ? rt / r : 0.0; constant[i] = k;
  }
  if (!steps) return;
  if (!m.lattice->advance(steps)) {
    m.failed = true;
    m.reason = "lattice diverged (nonphysical state) after t = " + std::to_string(m.time) + " s";
    return;
  }
  m.time += static_cast<double>(steps) * m.dt;
  m.lastField = fieldOf(sys, m);
}

// Nudge the lattice to the reference cell means; sub-cell structure and flow are kept.
void synchronise(const FieldSystem& sys, LatticeRun& m, const std::vector<double>& reference) {
  if (!m.available || m.failed) return;
  const auto current = fieldOf(sys, m);
  std::vector<double> delta(m.toField.size(), 0.0);
  for (std::size_t i = 0; i < m.toField.size(); ++i) {
    double w = 0, d = 0;
    for (const auto& [c, v] : m.toField[i]) {
      const auto cc = static_cast<std::size_t>(c);
      if (!std::isfinite(reference[cc]) || !std::isfinite(current[cc])) continue;
      w += v; d += v * (reference[cc] - current[cc]);
    }
    delta[i] = w > 0 ? d / w : 0.0;
  }
  m.lattice->addScalar(delta);
  m.lastField = fieldOf(sys, m);
}

// Lattice Boltzmann method: convective (with a coarser twin for self-consistency evidence and
// lattice-local descriptors) or conductive (scalar only).
class LatticeFieldMethod final : public FieldMethod {
 public:
  LatticeFieldMethod(std::string name, bool flow) : FieldMethod(std::move(name)), flow_(flow) {}

  std::string build(const FieldSystem& sys, const FieldEvolutionInput&) override {
    sys_ = &sys;
    buildLattice(sys, main_, sys.options.cellMm, flow_);
    if (!main_.available) return main_.reason;
    if (flow_) buildLattice(sys, twin_, sys.options.cellMm * sys.options.twinRatio, true);
    descriptors_.assign(sys.cells() * descriptorNames().size(), 0.0);
    return {};
  }

  void advance(const FieldCall& call) override {
    advanceLattice(*sys_, main_, call.input);
    advanceLattice(*sys_, twin_, call.input);
    if (main_.failed && !failed()) fail(main_.reason);
    if (flow_ && !main_.failed) {
      computeDescriptors();
      consistency_ = selfConsistency();
    } else {
      consistency_ = nullptr;
    }
  }

  std::vector<double> prediction() const override { return main_.lastField; }

  void observe(const FieldCall&, const std::vector<double>& reference) override {
    synchronise(*sys_, main_, reference);
    synchronise(*sys_, twin_, reference);
  }

  std::vector<std::string> descriptorNames() const override { return flow_ ? kLatticeDescriptors : std::vector<std::string>{}; }
  std::vector<double> descriptors() const override { return descriptors_; }

  nlohmann::json report() const override {
    nlohmann::json m = {{"family", "lattice"}, {"failed", main_.failed}, {"reason", main_.reason}, {"time_s", main_.time},
                        {"steps", main_.lattice->steps()}, {"max_mach", main_.lattice->maxMach()}};
    if (!main_.failed && main_.lattice->hasFlow()) {
      const auto& L = *main_.lattice;
      double e = 0;
      for (std::size_t i = 0; i < L.domain().count(); ++i) e += L.ux()[i] * L.ux()[i] + L.uy()[i] * L.uy()[i] + L.uz()[i] * L.uz()[i];
      m["rms_speed_m_s"] = std::sqrt(e / static_cast<double>(L.domain().count())) * main_.velocityScale;
      m["staggered_fraction"] = lattice::staggeredFraction(L.domain(), L.ux(), L.uy(), L.uz());
    }
    if (flow_) m["self_consistency"] = consistency_;
    return m;
  }

  nlohmann::json summary() const override {
    nlohmann::json m = {{"family", "lattice"}, {"failed", main_.failed}, {"reason", main_.reason}, {"lattice", main_.info},
                        {"steps", main_.lattice->steps()},
                        {"cell_steps", static_cast<double>(main_.lattice->steps()) * static_cast<double>(main_.lattice->domain().count())}};
    if (flow_) {
      m["twin"] = {{"available", twin_.available}, {"failed", twin_.failed}, {"reason", twin_.reason}, {"lattice", twin_.info}};
      m["self_consistency_series"] = series_;
    }
    return m;
  }

 private:
  void computeDescriptors() {
    const auto d = lattice::localDescriptors(*main_.lattice, std::max(1e-300, sys_->span));
    const std::vector<double>* cols[6] = {&d.cellPeclet, &d.cellReynolds, &d.mach, &d.scalarStep, &d.velocityCurvature, &d.wallDistance};
    const std::size_t F = kLatticeDescriptors.size(), C = sys_->cells();
    std::vector<double> out(C * F, 0.0), wsum(C, 0.0);
    for (std::size_t i = 0; i < main_.toField.size(); ++i)
      for (const auto& [c, w] : main_.toField[i]) {
        const auto cc = static_cast<std::size_t>(c);
        wsum[cc] += w;
        for (std::size_t f = 0; f < F; ++f) out[cc * F + f] += w * (*cols[f])[i];
      }
    for (std::size_t c = 0; c < C; ++c)
      for (std::size_t f = 0; f < F; ++f) out[c * F + f] = wsum[c] > 0 ? out[c * F + f] / wsum[c] : 0.0;
    descriptors_ = std::move(out);  // a failed lattice keeps its last valid descriptors
  }

  // Self-consistency against the coarser twin (rows = main lattice cells), learned prequentially.
  nlohmann::json selfConsistency() {
    if (!twin_.available || twin_.failed) return nullptr;
    auto& main = *main_.lattice;
    auto& tw = *twin_.lattice;
    const auto& T = main.scalarValues();
    const std::vector<double> Tw = tw.scalarValues();
    const auto& dom = main.domain();
    const std::size_t F = dom.count();
    double rms = 0;
    for (std::size_t i = 0; i < F; ++i) rms += main.ux()[i] * main.ux()[i] + main.uy()[i] * main.uy()[i] + main.uz()[i] * main.uz()[i];
    rms = std::sqrt(rms / static_cast<double>(F)) * main_.velocityScale;
    const double ratio = twin_.dxM / main_.dxM;
    const auto d = lattice::localDescriptors(main, std::max(1e-300, sys_->span));
    const std::vector<double>* cols[6] = {&d.cellPeclet, &d.cellReynolds, &d.mach, &d.scalarStep, &d.velocityCurvature, &d.wallDistance};
    DomainLearnerBatch batch;
    batch.time = main_.time;
    std::vector<double> observedT, observedU;
    for (std::size_t i = 0; i < F; ++i) {
      const double x = (dom.x[i] + 0.5) / ratio - 0.5, y = (dom.y[i] + 0.5) / ratio - 0.5, z = (dom.z[i] + 0.5) / ratio - 0.5;
      double tt = 0, ux = 0, uy = 0, uz = 0;
      if (!lattice::sample(tw.domain(), Tw, x, y, z, tt)) continue;
      lattice::sample(tw.domain(), tw.ux(), x, y, z, ux);
      lattice::sample(tw.domain(), tw.uy(), x, y, z, uy);
      lattice::sample(tw.domain(), tw.uz(), x, y, z, uz);
      const double eT = std::abs(T[i] - tt) / sys_->span;
      const double eU = std::hypot(main.ux()[i] * main_.velocityScale - ux * twin_.velocityScale,
                                   main.uy()[i] * main_.velocityScale - uy * twin_.velocityScale,
                                   main.uz()[i] * main_.velocityScale - uz * twin_.velocityScale) / (rms + 1e-12);
      for (const auto* col : cols) batch.features.push_back((*col)[i]);
      batch.targets.push_back(eT); batch.targets.push_back(eU);
      observedT.push_back(eT); observedU.push_back(eU);
    }
    batch.count = observedT.size();
    if (!batch.count) return nullptr;
    if (!learner_) {
      DomainLearnerOptions o;
      o.features = kLatticeDescriptors; o.targets = {"twin_scalar_error", "twin_velocity_error"};
      o.seed = sys_->options.seed; o.minElements = 64;
      o.budget = hostComputeBudget(); o.capacity = learnerCapacity(o.budget, kLatticeDescriptors.size(), 2);
      learner_ = std::make_unique<DomainLearner>(o);
    }
    const auto r = learner_->update(batch);
    std::vector<double> pT, pU;
    for (std::size_t i = 0; i < batch.count; ++i) { pT.push_back(r.predictions[2 * i]); pU.push_back(r.predictions[2 * i + 1]); }
    nlohmann::json out = {{"call", r.call}, {"rows", batch.count}, {"domains", r.domains.size()},
                          {"predicted_mean", {{"twin_scalar_error", nanMean(pT)}, {"twin_velocity_error", nanMean(pU)}}},
                          {"observed_mean", {{"twin_scalar_error", nanMean(observedT)}, {"twin_velocity_error", nanMean(observedU)}}},
                          {"routed_rmse", r.routedRmse}, {"pooled_rmse", r.pooledRmse}};
    series_.push_back({{"time_s", main_.time}, {"predicted_mean", out["predicted_mean"]}, {"observed_mean", out["observed_mean"]}});
    return out;
  }

  bool flow_;
  const FieldSystem* sys_ = nullptr;
  LatticeRun main_, twin_;
  std::vector<double> descriptors_;
  std::unique_ptr<DomainLearner> learner_;
  nlohmann::json consistency_ = nullptr;
  nlohmann::json series_ = nlohmann::json::array();
};

// The last observed state (the reference after a graded call): the baseline every method must beat.
class PersistenceMethod final : public FieldMethod {
 public:
  PersistenceMethod() : FieldMethod("persistence") {}
  std::string build(const FieldSystem&, const FieldEvolutionInput&) override { return {}; }
  void advance(const FieldCall& call) override { field_ = call.state; }
  std::vector<double> prediction() const override { return field_; }
  nlohmann::json report() const override { return {{"family", "baseline"}}; }
  nlohmann::json summary() const override { return {{"family", "baseline"}}; }

 private:
  std::vector<double> field_;
};

// A learned local operator: a DomainLearner over the method-independent call context
// (diffusive, exchange and load drives, recent change, level, exposure) learns the per-interval
// increment of each cell from the observed transitions, online and prequentially. Before it
// has a law for a cell it predicts persistence there (reported as `law_share`); far outside the
// support of its law (remoteness > 1) it abstains for that cell (`abstained_share`). It learns
// from the call's reference, so on a teacher reference it distils the teacher.
class LearnedOperatorMethod final : public FieldMethod {
 public:
  LearnedOperatorMethod() : FieldMethod("learned_operator") {}

  std::string build(const FieldSystem& sys, const FieldEvolutionInput&) override {
    sys_ = &sys;
    DomainLearnerOptions o;
    o.features = sys.contextNames; o.targets = {"increment"};
    // A local operator law is a function of the context, not of time: no time-trend bias shift.
    o.tendencyPredictor = false;
    o.seed = sys.options.seed; o.minElements = sys.options.minElements;
    o.budget = hostComputeBudget(); o.capacity = learnerCapacity(o.budget, o.features.size(), 1);
    // The drives are increments over the interval: an affine law per domain represents linear
    // transport and exchange exactly, and nonlinearity enters through domain splits. A full
    // quadratic basis extrapolates wildly where the joint support is sparse.
    o.capacity.basisDegree = 1;
    learner_ = std::make_unique<DomainLearner>(o);
    remoteness_.assign(sys.cells(), 10.0);
    return {};
  }

  // Its own remoteness from the learned support (capped at 10) is context for the arbitration.
  std::vector<std::string> descriptorNames() const override { return {"remoteness"}; }
  std::vector<double> descriptors() const override { return remoteness_; }

  void advance(const FieldCall& call) override {
    const std::size_t C = sys_->cells();
    start_ = call.state;
    context_ = call.context;
    std::vector<double> remoteness;
    const auto increment = learner_->predict(context_, C, call.input.timeS, &remoteness);
    field_.assign(C, kNaN);
    lawCells_ = abstained_ = 0;
    calls_ += 1;
    for (std::size_t c = 0; c < C; ++c) {
      const bool law = std::isfinite(increment[c]);
      lawCells_ += law ? 1 : 0;
      remoteness_[c] = std::isfinite(remoteness[c]) ? std::min(remoteness[c], 10.0) : 10.0;
      // Far outside the support of its law the operator does not predict: it abstains there
      // and is no candidate for that cell. Before any law it predicts persistence.
      if (law && remoteness[c] > 1.0) { ++abstained_; continue; }
      field_[c] = start_[c] + (law ? sys_->span * increment[c] : 0.0);
    }
    abstainedTotal_ += abstained_;
    time_ = call.input.timeS;
  }

  std::vector<double> prediction() const override { return field_; }

  nlohmann::json exportState(bool includeRows) const override {
    return {{"format", "trech_learned_operator_v1"}, {"learner", learner_->exportState(includeRows)}};
  }

  void restoreState(const nlohmann::json& state, bool frozen) override {
    if (!state.is_object() || state.value("format", "") != "trech_learned_operator_v1")
      throw std::invalid_argument("learned_operator state: expected format trech_learned_operator_v1");
    auto learner = std::make_unique<DomainLearner>(DomainLearner::fromState(state.at("learner"), frozen));
    if (learner->options().features != sys_->contextNames)
      throw std::invalid_argument("learned_operator state: its context features differ from this system's");
    learner_ = std::move(learner);
    frozen_ = frozen;
  }

  void observe(const FieldCall&, const std::vector<double>& reference) override {
    if (frozen_) return;  // deployed: predicts from what it learned, learns nothing
    DomainLearnerBatch batch;
    batch.time = time_;
    const std::size_t C = sys_->cells(), F = sys_->contextNames.size();
    for (std::size_t c = 0; c < C; ++c) {
      if (!std::isfinite(reference[c]) || !std::isfinite(start_[c])) continue;
      batch.features.insert(batch.features.end(), context_.begin() + static_cast<std::ptrdiff_t>(c * F),
                            context_.begin() + static_cast<std::ptrdiff_t>((c + 1) * F));
      batch.targets.push_back((reference[c] - start_[c]) / sys_->span);
      ++batch.count;
    }
    if (!batch.count) return;
    const auto r = learner_->update(batch);
    domains_ = r.domains.size();
    lastRmse_ = r.routedRmse.empty() ? kNaN : r.routedRmse[0] * sys_->span;
  }

  nlohmann::json report() const override {
    const double C = static_cast<double>(sys_->cells());
    return {{"family", "learned"}, {"law_share", C > 0 ? static_cast<double>(lawCells_) / C : 0.0},
            {"abstained_share", C > 0 ? static_cast<double>(abstained_) / C : 0.0},
            {"domains", domains_}, {"increment_rmse", lastRmse_}};
  }
  nlohmann::json summary() const override {
    const double cellCalls = static_cast<double>(sys_->cells()) * static_cast<double>(calls_);
    nlohmann::json out = {{"family", "learned"}, {"learner_calls", learner_->calls()}, {"domains", domains_},
            {"abstained_share", cellCalls > 0 ? static_cast<double>(abstainedTotal_) / cellCalls : 0.0},
            {"features", sys_->contextNames}, {"target", "increment over the call interval / field span"}};
    if (frozen_) out["frozen"] = true;
    return out;
  }

 private:
  const FieldSystem* sys_ = nullptr;
  std::unique_ptr<DomainLearner> learner_;
  std::vector<double> start_, context_, field_, remoteness_;
  double time_ = 0.0, lastRmse_ = kNaN;
  std::size_t lawCells_ = 0, domains_ = 0, abstained_ = 0, abstainedTotal_ = 0, calls_ = 0;
  bool frozen_ = false;
};

std::vector<FieldMethodEntry>& registry() {
  static std::vector<FieldMethodEntry> entries = {
      {"lattice_convective", "lattice",
       "thermal lattice Boltzmann: D3Q19 TRT flow + D3Q7 scalar, Boussinesq coupling, coarser twin for self-consistency",
       [] { return std::make_unique<LatticeFieldMethod>("lattice_convective", true); }},
      {"lattice_conductive", "lattice", "scalar lattice Boltzmann without flow (D3Q7 conduction)",
       [] { return std::make_unique<LatticeFieldMethod>("lattice_conductive", false); }},
      {"learned_operator", "learned",
       "online domain-learned local operator over the method-independent call context (increment per interval)",
       [] { return std::make_unique<LearnedOperatorMethod>(); }},
      {"persistence", "baseline", "the last observed state",
       [] { return std::make_unique<PersistenceMethod>(); }},
  };
  return entries;
}

std::mutex& registryMutex() {
  static std::mutex m;
  return m;
}

}  // namespace

const std::vector<FieldMethodEntry>& fieldMethodRegistry() {
  std::lock_guard<std::mutex> lock(registryMutex());
  return registry();
}

void registerFieldMethod(FieldMethodEntry entry) {
  std::lock_guard<std::mutex> lock(registryMutex());
  if (entry.name.empty() || !entry.make) throw std::invalid_argument("a field method needs a name and a factory");
  for (const auto& e : registry())
    if (e.name == entry.name) throw std::invalid_argument("field method already registered: " + entry.name);
  registry().push_back(std::move(entry));
}

}  // namespace trech::ml
