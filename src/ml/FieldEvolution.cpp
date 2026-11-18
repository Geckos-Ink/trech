#include "trech/ml/FieldEvolution.hpp"

#include "trech/ml/ComputeBudget.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace trech::ml {
namespace {

const std::vector<std::string> kMethods = {"lattice_convective", "lattice_conductive", "persistence"};
const std::vector<std::string> kFeatures = {"cell_peclet", "cell_reynolds", "mach", "scalar_step",
                                            "velocity_curvature", "wall_distance"};
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
constexpr double kPi = 3.14159265358979323846;

double overlap1(double a0, double a1, double b0, double b1) { return std::max(0.0, std::min(a1, b1) - std::max(a0, b0)); }

// One lattice-based method on the declared region.
struct LatticeMethod {
  std::string name;
  bool available = false, failed = false;
  std::string reason;
  std::unique_ptr<lattice::Lattice> lattice;
  double dxM = 0.0, dt = 0.0, time = 0.0, velocityScale = 0.0, span = 1.0, freeFall = 0.0;
  // Per lattice cell: (field cell, volume fraction of the lattice cell inside that field cell).
  std::vector<std::vector<std::pair<int, double>>> toField;
  std::vector<double> fieldVolume;  // per field cell: fluid lattice volume inside it (cell units)
  std::vector<double> lastField;
  nlohmann::json info;
};

double nanMean(const std::vector<double>& v) {
  double s = 0; std::size_t n = 0;
  for (double x : v) if (std::isfinite(x)) { s += x; ++n; }
  return n ? s / static_cast<double>(n) : kNaN;
}

}  // namespace

struct FieldEvolution::Impl {
  FieldRegion region;
  std::vector<std::array<double, 3>> cellMin, cellMax;
  FieldProperties props;
  std::vector<double> initial;
  FieldEvolutionOptions opt;
  double offset = 0.0;  // lattices evolve value - offset
  bool built = false;
  LatticeMethod convective, conductive, twin;
  std::vector<double> lastReference;
  std::unique_ptr<DomainLearner> arbitration, consistency;
  long calls = 0;
  // Run accumulators.
  std::vector<double> sumSq = std::vector<double>(kMethods.size(), 0.0);
  std::vector<double> selected = std::vector<double>(kMethods.size(), 0.0);
  double arbitratedSq = 0.0, oracleSq = 0.0, gradedCells = 0.0, learnedSelections = 0.0;
  double learnedSq = 0.0, learnedCells = 0.0;  // cells whose method was chosen by learned errors
  nlohmann::json lastDomains = nlohmann::json::array();
  nlohmann::json consistencySeries = nlohmann::json::array();

  std::size_t cells() const { return cellMin.size(); }

  // Lattice geometry of the declared region at cell size dxMm.
  void geometry(double dxMm, std::array<int, 3>& shape, std::function<bool(int, int, int)>& solid,
                std::array<double, 3>& origin) const {
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

  int gravityAxis(double& magnitude) const {
    int axis = -1; magnitude = 0;
    for (int a = 0; a < 3; ++a) {
      const double g = props.bodyAccelerationM2S[a];
      if (g == 0.0) continue;
      if (axis >= 0) return -2;  // not axis-aligned
      axis = a; magnitude = g;
    }
    return axis;
  }

  // Build one lattice method. `flow` selects convective vs conductive numerics.
  void build(LatticeMethod& m, const std::string& name, double dxMm, bool flow,
             const std::vector<double>& rate, const std::vector<double>& target) {
    m.name = name;
    m.dxM = dxMm * 1e-3;
    std::array<int, 3> shape{}; std::function<bool(int, int, int)> solid; std::array<double, 3> origin{};
    geometry(dxMm, shape, solid, origin);
    const double nu = props.kinematicViscosityM2S, kappa = props.diffusivityM2S;
    if (!(kappa > 0)) { m.reason = "no positive scalar diffusivity declared"; return; }
    double lo = std::numeric_limits<double>::infinity(), hi = -lo;
    for (std::size_t c = 0; c < cells(); ++c) {
      lo = std::min(lo, initial[c]); hi = std::max(hi, initial[c]);
      if (c < rate.size() && rate[c] > 0 && c < target.size()) { lo = std::min(lo, target[c]); hi = std::max(hi, target[c]); }
    }
    m.span = hi > lo ? hi - lo : 1.0;
    lattice::LatticeSpec s;
    s.shape = shape; s.solid = solid;
    double g = 0;
    const int axis = gravityAxis(g);
    if (flow) {
      if (!(nu > 0)) { m.reason = "no positive kinematic viscosity declared"; return; }
      if (axis == -2) { m.reason = "body acceleration is not axis-aligned"; return; }
      const double extent = axis >= 0 ? shape[static_cast<std::size_t>(axis)] * m.dxM : 0.0;
      m.freeFall = axis >= 0 ? std::sqrt(std::abs(g * props.expansionPerUnit) * m.span * extent) : 0.0;
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
    m.fieldVolume.assign(cells(), 0.0);
    for (std::size_t i = 0; i < probe.count(); ++i) {
      const double x0 = origin[0] + probe.x[i] * dxMm, y0 = origin[1] + probe.y[i] * dxMm, z0 = origin[2] + probe.z[i] * dxMm;
      double wsum = 0, vsum = 0;
      for (std::size_t c = 0; c < cells(); ++c) {
        const double v = overlap1(x0, x0 + dxMm, cellMin[c][0], cellMax[c][0]) *
                         overlap1(y0, y0 + dxMm, cellMin[c][1], cellMax[c][1]) *
                         overlap1(z0, z0 + dxMm, cellMin[c][2], cellMax[c][2]) / (dxMm * dxMm * dxMm);
        if (v <= 0) continue;
        m.toField[i].push_back({static_cast<int>(c), v});
        m.fieldVolume[c] += v;
        wsum += v; vsum += v * (initial[c] - offset);
      }
      init[i] = wsum > 0 ? vsum / wsum : 0.0;
      const int horizontal[2] = {axis == 0 ? 1 : 0, axis == 2 || axis < 0 ? 1 : 2};
      const double h0 = (horizontal[0] == 0 ? probe.x[i] : probe.y[i]) + 0.5 - 0.5 * shape[static_cast<std::size_t>(horizontal[0])];
      const double h1 = (horizontal[1] == 1 ? probe.y[i] : probe.z[i]) + 0.5 - 0.5 * shape[static_cast<std::size_t>(horizontal[1])];
      init[i] += 1e-5 * m.span * (std::cos(angle) * h0 + std::sin(angle) * h1) / std::max(1, shape[0]);
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
    m.lastField = fieldOf(m);
    m.info = {{"cell_mm", dxMm}, {"shape", shape}, {"fluid_cells", m.lattice->domain().count()}, {"dt_s", m.dt},
              {"tau", flow ? s.tau : kNaN}, {"scalar_diffusivity_lattice", s.diffusivity},
              {"free_fall_velocity_m_s", m.freeFall}, {"field_span", m.span}};
  }

  std::vector<double> fieldOf(LatticeMethod& m) {
    const auto& T = m.lattice->scalarValues();
    std::vector<double> sum(cells(), 0.0);
    for (std::size_t i = 0; i < m.toField.size(); ++i)
      for (const auto& [c, w] : m.toField[i]) sum[static_cast<std::size_t>(c)] += w * T[i];
    std::vector<double> out(cells(), kNaN);
    for (std::size_t c = 0; c < cells(); ++c) if (m.fieldVolume[c] > 0) out[c] = offset + sum[c] / m.fieldVolume[c];
    return out;
  }

  void advance(LatticeMethod& m, const FieldEvolutionInput& in) {
    if (!m.available || m.failed) return;
    const auto steps = static_cast<std::uint64_t>(std::max(0.0, std::floor((in.timeS - m.time) / m.dt + 1e-9)));
    auto& rate = m.lattice->rate(); auto& target = m.lattice->target(); auto& constant = m.lattice->constant();
    for (std::size_t i = 0; i < m.toField.size(); ++i) {
      double r = 0, rt = 0, k = 0;
      for (const auto& [c, w] : m.toField[i]) {
        const auto cc = static_cast<std::size_t>(c);
        if (cc < in.rate.size() && in.rate[cc] > 0) {
          r += w * in.rate[cc] * m.dt;
          rt += w * in.rate[cc] * m.dt * ((cc < in.target.size() ? in.target[cc] : offset) - offset);
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
    m.lastField = fieldOf(m);
  }

  void synchronise(LatticeMethod& m, const std::vector<double>& reference) {
    if (!m.available || m.failed) return;
    const auto current = fieldOf(m);
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
    m.lastField = fieldOf(m);
  }

  // Field-cell features from the convective lattice (or the conductive one after a failure).
  std::vector<double> features() {
    LatticeMethod& m = convective.available && !convective.failed ? convective : conductive;
    std::vector<double> out(cells() * kFeatures.size(), 0.0);
    if (!m.available) return out;
    const auto d = lattice::localDescriptors(*m.lattice, std::max(1e-300, m.span));
    const std::vector<double>* cols[6] = {&d.cellPeclet, &d.cellReynolds, &d.mach, &d.scalarStep, &d.velocityCurvature, &d.wallDistance};
    std::vector<double> wsum(cells(), 0.0);
    for (std::size_t i = 0; i < m.toField.size(); ++i)
      for (const auto& [c, w] : m.toField[i]) {
        const auto cc = static_cast<std::size_t>(c);
        wsum[cc] += w;
        for (std::size_t f = 0; f < kFeatures.size(); ++f) out[cc * kFeatures.size() + f] += w * (*cols[f])[i];
      }
    for (std::size_t c = 0; c < cells(); ++c)
      for (std::size_t f = 0; f < kFeatures.size(); ++f) out[c * kFeatures.size() + f] = wsum[c] > 0 ? out[c * kFeatures.size() + f] / wsum[c] : 0.0;
    return out;
  }

  // Self-consistency of the convective lattice against its twin (rows = main lattice cells).
  nlohmann::json selfConsistency() {
    if (!convective.available || convective.failed || !twin.available || twin.failed) return nullptr;
    auto& main = *convective.lattice;
    auto& tw = *twin.lattice;
    const auto& T = main.scalarValues();
    const std::vector<double> Tw = tw.scalarValues();
    const auto& dom = main.domain();
    const std::size_t F = dom.count();
    double rms = 0;
    for (std::size_t i = 0; i < F; ++i) rms += main.ux()[i] * main.ux()[i] + main.uy()[i] * main.uy()[i] + main.uz()[i] * main.uz()[i];
    rms = std::sqrt(rms / static_cast<double>(F)) * convective.velocityScale;
    const double ratio = twin.dxM / convective.dxM;
    const auto d = lattice::localDescriptors(main, std::max(1e-300, convective.span));
    const std::vector<double>* cols[6] = {&d.cellPeclet, &d.cellReynolds, &d.mach, &d.scalarStep, &d.velocityCurvature, &d.wallDistance};
    DomainLearnerBatch batch;
    batch.time = convective.time;
    std::vector<double> observedT, observedU;
    for (std::size_t i = 0; i < F; ++i) {
      const double x = (dom.x[i] + 0.5) / ratio - 0.5, y = (dom.y[i] + 0.5) / ratio - 0.5, z = (dom.z[i] + 0.5) / ratio - 0.5;
      double tt = 0, ux = 0, uy = 0, uz = 0;
      if (!lattice::sample(tw.domain(), Tw, x, y, z, tt)) continue;
      lattice::sample(tw.domain(), tw.ux(), x, y, z, ux);
      lattice::sample(tw.domain(), tw.uy(), x, y, z, uy);
      lattice::sample(tw.domain(), tw.uz(), x, y, z, uz);
      const double eT = std::abs(T[i] - tt) / convective.span;
      const double eU = std::hypot(main.ux()[i] * convective.velocityScale - ux * twin.velocityScale,
                                   main.uy()[i] * convective.velocityScale - uy * twin.velocityScale,
                                   main.uz()[i] * convective.velocityScale - uz * twin.velocityScale) / (rms + 1e-12);
      for (const auto* col : cols) batch.features.push_back((*col)[i]);
      batch.targets.push_back(eT); batch.targets.push_back(eU);
      observedT.push_back(eT); observedU.push_back(eU);
    }
    batch.count = observedT.size();
    if (!batch.count) return nullptr;
    if (!consistency) {
      DomainLearnerOptions o;
      o.features = kFeatures; o.targets = {"twin_scalar_error", "twin_velocity_error"};
      o.seed = opt.seed; o.minElements = 64;
      o.budget = hostComputeBudget(); o.capacity = learnerCapacity(o.budget, kFeatures.size(), 2);
      consistency = std::make_unique<DomainLearner>(o);
    }
    const auto r = consistency->update(batch);
    std::vector<double> pT, pU;
    for (std::size_t i = 0; i < batch.count; ++i) { pT.push_back(r.predictions[2 * i]); pU.push_back(r.predictions[2 * i + 1]); }
    nlohmann::json out = {{"call", r.call}, {"rows", batch.count}, {"domains", r.domains.size()},
                          {"predicted_mean", {{"twin_scalar_error", nanMean(pT)}, {"twin_velocity_error", nanMean(pU)}}},
                          {"observed_mean", {{"twin_scalar_error", nanMean(observedT)}, {"twin_velocity_error", nanMean(observedU)}}},
                          {"routed_rmse", r.routedRmse}, {"pooled_rmse", r.pooledRmse}};
    consistencySeries.push_back({{"time_s", convective.time}, {"predicted_mean", out["predicted_mean"]},
                                 {"observed_mean", out["observed_mean"]}});
    return out;
  }
};

const std::vector<std::string>& FieldEvolution::methodNames() { return kMethods; }

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
    for (int a = 0; a < 3; ++a)
      if (!(cellMax[c][a] > cellMin[c][a])) throw std::invalid_argument("every field cell needs max > min");
  for (double v : initialValues) if (!std::isfinite(v)) throw std::invalid_argument("initial values must be finite");
  if (!(options.cellMm > 0) || !(options.machTarget > 0) || !(options.twinRatio > 1) || !(options.conductiveTau > 0.5))
    throw std::invalid_argument("invalid field-evolution options");
  s.region = region; s.cellMin = std::move(cellMin); s.cellMax = std::move(cellMax);
  s.props = properties; s.initial = std::move(initialValues); s.opt = options;
  double sum = 0;
  for (double v : s.initial) sum += v;
  s.offset = sum / static_cast<double>(s.initial.size());
  s.lastReference = s.initial;
  DomainLearnerOptions o;
  o.features = kFeatures;
  for (const auto& m : kMethods) o.targets.push_back("error_" + m);
  o.seed = options.seed; o.minElements = options.minElements;
  o.budget = hostComputeBudget(); o.capacity = learnerCapacity(o.budget, kFeatures.size(), kMethods.size());
  s.arbitration = std::make_unique<DomainLearner>(o);
}

FieldEvolution::~FieldEvolution() = default;
FieldEvolution::FieldEvolution(FieldEvolution&&) noexcept = default;
FieldEvolution& FieldEvolution::operator=(FieldEvolution&&) noexcept = default;

nlohmann::json FieldEvolution::step(const FieldEvolutionInput& in) {
  auto& s = *impl_;
  const std::size_t C = s.cells();
  for (const auto* v : {&in.rate, &in.target, &in.loadPerS, &in.reference})
    if (!v->empty() && v->size() != C) throw std::invalid_argument("per-cell arrays must match the field cells");
  if (!s.built) {
    s.build(s.convective, "lattice_convective", s.opt.cellMm, true, in.rate, in.target);
    s.build(s.conductive, "lattice_conductive", s.opt.cellMm, false, in.rate, in.target);
    s.build(s.twin, "twin", s.opt.cellMm * s.opt.twinRatio, true, in.rate, in.target);
    s.built = true;
  }
  s.advance(s.convective, in); s.advance(s.conductive, in); s.advance(s.twin, in);
  ++s.calls;
  // Candidate predictions per method.
  std::vector<std::vector<double>> pred(kMethods.size());
  pred[0] = s.convective.available ? s.convective.lastField : std::vector<double>(C, kNaN);
  pred[1] = s.conductive.available ? s.conductive.lastField : std::vector<double>(C, kNaN);
  pred[2] = s.lastReference;
  const auto feats = s.features();
  const bool graded = !in.reference.empty();
  // Rows: field cells where every candidate and the reference are finite.
  std::vector<std::size_t> rows;
  for (std::size_t c = 0; c < C; ++c) {
    bool ok = !graded || std::isfinite(in.reference[c]);
    for (const auto& p : pred) ok = ok && std::isfinite(p[c]);
    if (ok) rows.push_back(c);
  }
  // Fallback order: the method with the lowest realized error so far (persistence first).
  std::size_t fallback = 2;
  for (std::size_t k = 0; k < kMethods.size(); ++k)
    if (s.gradedCells > 0 && s.sumSq[k] < s.sumSq[fallback]) fallback = k;
  std::vector<int> selection(C, -1);
  std::vector<uint8_t> learnedCell(C, 0);
  std::vector<double> field(C, kNaN), predictedErrors(C * kMethods.size(), kNaN);
  nlohmann::json arbitrationReport = nullptr;
  if (graded && !rows.empty()) {
    DomainLearnerBatch batch;
    batch.time = in.timeS; batch.count = rows.size();
    for (std::size_t c : rows) {
      for (std::size_t f = 0; f < kFeatures.size(); ++f) batch.features.push_back(feats[c * kFeatures.size() + f]);
      for (std::size_t k = 0; k < kMethods.size(); ++k) batch.targets.push_back(std::abs(pred[k][c] - in.reference[c]));
    }
    const auto r = s.arbitration->update(batch);
    for (std::size_t j = 0; j < rows.size(); ++j)
      for (std::size_t k = 0; k < kMethods.size(); ++k) predictedErrors[rows[j] * kMethods.size() + k] = r.predictions[j * kMethods.size() + k];
    nlohmann::json domains = nlohmann::json::array();
    for (const auto& d : r.domains) {
      if (!d.elements) continue;
      nlohmann::json errors = nlohmann::json::object();
      std::size_t winner = 0;
      for (std::size_t k = 0; k < kMethods.size(); ++k) {
        errors[kMethods[k]] = d.valueAtMean.size() > k ? d.valueAtMean[k] : kNaN;
        if (d.valueAtMean.size() > k && d.valueAtMean[k] < d.valueAtMean[winner]) winner = k;
      }
      nlohmann::json envelope = nlohmann::json::object();
      for (std::size_t f = 0; f < kFeatures.size() && f < d.featureMin.size(); ++f)
        envelope[kFeatures[f]] = {d.featureMin[f], d.featureMax[f]};
      domains.push_back({{"id", d.id}, {"elements", d.elements}, {"model", d.model}, {"predicted_error_at_mean", errors},
                         {"winner", kMethods[winner]}, {"context_envelope", envelope}});
    }
    s.lastDomains = domains;
    arbitrationReport = {{"call", r.call}, {"rows", rows.size()}, {"scored", r.scored},
                         {"routed_rmse", r.routedRmse}, {"pooled_rmse", r.pooledRmse}, {"domains", domains}};
  }
  // Select per cell: lowest learned (prequential) error; fallback before anything is learned.
  for (std::size_t c = 0; c < C; ++c) {
    int best = -1; double bestError = std::numeric_limits<double>::infinity();
    for (std::size_t k = 0; k < kMethods.size(); ++k) {
      const double e = predictedErrors[c * kMethods.size() + k];
      if (std::isfinite(e) && std::isfinite(pred[k][c]) && e < bestError) { bestError = e; best = static_cast<int>(k); }
    }
    const bool learned = best >= 0;
    learnedCell[c] = learned ? 1 : 0;
    if (!learned) best = std::isfinite(pred[fallback][c]) ? static_cast<int>(fallback) : 2;
    selection[c] = best;
    field[c] = pred[static_cast<std::size_t>(best)][c];
    if (graded) { s.selected[static_cast<std::size_t>(best)] += 1; if (learned) s.learnedSelections += 1; }
  }
  // Realized errors (graded calls).
  nlohmann::json methods = nlohmann::json::object();
  double arbitratedSq = 0, oracleSq = 0, n = 0;
  std::vector<double> callSq(kMethods.size(), 0.0);
  if (graded) {
    for (std::size_t c : rows) {
      double best = std::numeric_limits<double>::infinity();
      for (std::size_t k = 0; k < kMethods.size(); ++k) {
        const double e = pred[k][c] - in.reference[c];
        callSq[k] += e * e; best = std::min(best, e * e);
      }
      const double a = field[c] - in.reference[c];
      arbitratedSq += a * a; oracleSq += best; n += 1;
      if (learnedCell[c]) { s.learnedSq += a * a; s.learnedCells += 1; }
    }
    for (std::size_t k = 0; k < kMethods.size(); ++k) s.sumSq[k] += callSq[k];
    s.arbitratedSq += arbitratedSq; s.oracleSq += oracleSq; s.gradedCells += n;
  }
  const LatticeMethod* lm[2] = {&s.convective, &s.conductive};
  for (std::size_t k = 0; k < kMethods.size(); ++k) {
    nlohmann::json m = {{"field", pred[k]}, {"rmse", graded && n > 0 ? std::sqrt(callSq[k] / n) : kNaN}};
    if (k < 2) {
      m["available"] = lm[k]->available; m["failed"] = lm[k]->failed; m["reason"] = lm[k]->reason;
      m["time_s"] = lm[k]->time;
      m["steps"] = lm[k]->available ? lm[k]->lattice->steps() : 0;
      m["max_mach"] = lm[k]->available ? lm[k]->lattice->maxMach() : 0.0;
      if (lm[k]->available && !lm[k]->failed && lm[k]->lattice->hasFlow()) {
        const auto& L = *lm[k]->lattice;
        double e = 0;
        for (std::size_t i = 0; i < L.domain().count(); ++i) e += L.ux()[i] * L.ux()[i] + L.uy()[i] * L.uy()[i] + L.uz()[i] * L.uz()[i];
        m["rms_speed_m_s"] = std::sqrt(e / static_cast<double>(L.domain().count())) * lm[k]->velocityScale;
        m["staggered_fraction"] = lattice::staggeredFraction(L.domain(), L.ux(), L.uy(), L.uz());
      }
    }
    methods[kMethods[k]] = m;
  }
  if (graded) {
    s.lastReference = in.reference;
    // One-step-ahead competition: every method predicts the next interval from the same observed
    // state. Lattices are nudged to the reference cell means (sub-cell structure and flow kept).
    for (LatticeMethod* m : {&s.convective, &s.conductive, &s.twin}) s.synchronise(*m, in.reference);
  }
  std::vector<std::string> selectionNames;
  for (int k : selection) selectionNames.push_back(kMethods[static_cast<std::size_t>(k)]);
  return {{"time_s", in.timeS}, {"call", s.calls}, {"graded", graded}, {"field", field}, {"selection", selectionNames},
          {"arbitrated_rmse", graded && n > 0 ? std::sqrt(arbitratedSq / n) : kNaN},
          {"oracle_rmse", graded && n > 0 ? std::sqrt(oracleSq / n) : kNaN},
          {"methods", methods}, {"arbitration", arbitrationReport}, {"self_consistency", s.selfConsistency()}};
}

nlohmann::json FieldEvolution::summary() const {
  const auto& s = *impl_;
  nlohmann::json methods = nlohmann::json::object();
  const LatticeMethod* lm[2] = {&s.convective, &s.conductive};
  double total = 0;
  for (double v : s.selected) total += v;
  for (std::size_t k = 0; k < kMethods.size(); ++k) {
    nlohmann::json m = {{"rmse", s.gradedCells > 0 ? std::sqrt(s.sumSq[k] / s.gradedCells) : kNaN},
                        {"selected_share", total > 0 ? s.selected[k] / total : kNaN}};
    if (k < 2) {
      m["available"] = lm[k]->available; m["failed"] = lm[k]->failed; m["reason"] = lm[k]->reason;
      m["lattice"] = lm[k]->info;
      m["steps"] = lm[k]->available ? lm[k]->lattice->steps() : 0;
      m["cell_steps"] = lm[k]->available ? static_cast<double>(lm[k]->lattice->steps()) * static_cast<double>(lm[k]->lattice->domain().count()) : 0.0;
    }
    methods[kMethods[k]] = m;
  }
  std::size_t best = 0;
  for (std::size_t k = 1; k < kMethods.size(); ++k) if (s.sumSq[k] < s.sumSq[best]) best = k;
  return {{"calls", s.calls}, {"graded_cells", s.gradedCells}, {"methods", methods},
          {"best_single_method", kMethods[best]},
          {"arbitrated_rmse", s.gradedCells > 0 ? std::sqrt(s.arbitratedSq / s.gradedCells) : kNaN},
          {"oracle_rmse", s.gradedCells > 0 ? std::sqrt(s.oracleSq / s.gradedCells) : kNaN},
          {"learned_selection_share", total > 0 ? s.learnedSelections / total : kNaN},
          {"arbitrated_rmse_learned", s.learnedCells > 0 ? std::sqrt(s.learnedSq / s.learnedCells) : kNaN},
          {"final_domains", s.lastDomains},
          {"twin", {{"available", s.twin.available}, {"failed", s.twin.failed}, {"reason", s.twin.reason}, {"lattice", s.twin.info}}},
          {"self_consistency_series", s.consistencySeries}};
}

}  // namespace trech::ml
