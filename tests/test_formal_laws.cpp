// Classic side of the optional Lean law pairs (formal/laws.json, docs/engine/formal_laws.md).
//
// Lean is not needed here: every check runs the classic C++/JS implementation against the
// statement of its Lean pair, checks the hypotheses the Lean theorem assumes, and checks that
// the C++ and JavaScript classic implementations agree.
#include "TemporaryDirectory.hpp"

#include "trech/core/FormalLaws.hpp"
#include "trech/core/LatticeContinuum.hpp"
#include "trech/core/Provenance.hpp"
#include "trech/core/LatticeKinetic.hpp"
#include "trech/js/JsRuntime.hpp"
#include "trech/ml/BoundedStep.hpp"
#include "trech/ml/DiscreteTransition.hpp"
#include "trech/ml/GenericSurrogate.hpp"
#include "trech/ml/GroupHierarchy.hpp"
#include "trech/ml/LeastSquaresStatistics.hpp"
#include "trech/ml/MethodArbiter.hpp"
#include "trech/ml/PairInteraction.hpp"
#include "trech/ml/StateEvolution.hpp"
#include "trech/sim/EnergyBalance.hpp"
#include "trech/sim/KleinNishina.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace formal = trech::formal;
namespace kn = trech::sim::klein_nishina;

namespace {

int failures = 0;

void expect(const formal::LawCheck& check, bool shouldPass = true) {
  std::printf("%-40s %-44s samples %-5zu max_err %.3e %s\n", check.law.c_str(),
              check.leanDeclaration.c_str(), check.samples, check.maxAbsError,
              check.passed ? "pass" : "FAIL");
  if (check.passed != shouldPass) {
    std::fprintf(stderr, "unexpected verdict for %s: %s\n", check.law.c_str(), check.detail.c_str());
    ++failures;
  }
}

const std::vector<double> kEps = {1e-4, 0.01, 0.1, 0.5, 1.0, 1.295, 2.0, 5.0, 20.0, 200.0};

std::vector<double> cosGrid() {
  std::vector<double> c;
  for (int i = 0; i <= 40; ++i) c.push_back(-1.0 + 0.05 * i);
  return c;
}

void comptonPairs() {
  // Trech.Laws.Compton.transferFraction_le_edge / transferFraction_nonneg on the classic
  // KleinNishina.hpp functions, and transferFraction_backscatter (equality at cos = -1).
  std::vector<double> values, lower, upper, back, edges;
  for (double eps : kEps) {
    const double edge = kn::comptonEdgeFraction(eps);
    for (double c : cosGrid()) {
      values.push_back(1.0 - kn::scatteredEnergyRatio(eps, c));
      lower.push_back(0.0);
      upper.push_back(edge);
    }
    back.push_back(1.0 - kn::scatteredEnergyRatio(eps, -1.0));
    edges.push_back(edge);
  }
  expect(formal::checkWithinBounds("compton.transfer_within_edge",
                                   "Trech.Laws.Compton.transferFraction_le_edge", values, lower, upper,
                                   1e-15));
  expect(formal::checkAgreement("compton.edge_at_backscatter",
                                "Trech.Laws.Compton.transferFraction_backscatter", back, edges, 1e-15,
                                1e-15));
  // The check must catch a violation: an edge 1% too low.
  std::vector<double> tight = upper;
  for (double& u : tight) u *= 0.99;
  expect(formal::checkWithinBounds("compton.negative_control", "", values, lower, tight, 1e-15), false);
}

void energyBalancePairs() {
  // Trech.Laws.EnergyBalance on the classic energy_balance::relativeResidual. Steps are formed
  // the way Geant4's free-electron Compton model forms them: E' = ratio * E, the electron gets
  // E - E' unless that is below the 100 eV secondary threshold (then it is deposited), and a
  // photon left below the threshold is killed with its energy deposited.
  namespace eb = trech::sim::energy_balance;
  const double me = 0.51099895;     // MeV
  const double threshold = 100e-6;  // MeV
  std::vector<double> residuals, zeros, tolerances, posts, pres;
  for (double eps : kEps) {
    const double e = eps * me;
    for (double c : cosGrid()) {
      double post = kn::scatteredEnergyRatio(eps, c) * e;
      std::vector<double> secondaries;
      double deposit = 0.0;
      const double electron = e - post;
      if (electron > threshold) secondaries.push_back(electron); else deposit += electron;
      if (post <= threshold) { deposit += post; post = 0.0; }
      residuals.push_back(eb::relativeResidual(e, 0.0, post, secondaries, deposit));
      zeros.push_back(0.0);
      tolerances.push_back(eb::kRelativeTolerance);
      posts.push_back(post);
      pres.push_back(e);
    }
  }
  expect(formal::checkWithinBounds("energy.step_balance", "Trech.Laws.EnergyBalance.residual_eq_zero_iff",
                                   residuals, zeros, tolerances, 0.0));
  // post_le_pre: with Q = 0 the scattered photon never gains energy.
  expect(formal::checkWithinBounds("energy.post_le_pre", "Trech.Laws.EnergyBalance.post_le_pre", posts,
                                   zeros, pres, 0.0));
  // A gamma conversion releases Q = -2 m_e c^2: 10 MeV -> e- 6 MeV + e+ (10 - 2 me - 6) MeV.
  const double conversion = eb::relativeResidual(10.0, -2.0 * me, 0.0, {6.0, 10.0 - 2.0 * me - 6.0}, 0.0);
  expect(formal::checkWithinBounds("energy.conversion_balance", "Trech.Laws.EnergyBalance.residual_eq_zero_iff",
                                   {conversion}, {0.0}, {eb::kRelativeTolerance}, 0.0));
  // track_released_sum: what balanced steps hand on adds up to the kinetic-energy drop.
  std::vector<double> before = {pres.back()}, after;
  double k = pres.back();
  for (double c : cosGrid()) {
    const double next = kn::scatteredEnergyRatio(k / me, c) * k;
    after.push_back(k - next);  // released by this step
    k = next;
  }
  after.push_back(k);
  expect(formal::checkConservedTotal("energy.track_released_sum", "Trech.Laws.EnergyBalance.track_released_sum",
                                     before, after, 1e-13));
  // The check must catch a step that loses its electron, and refuse non-finite input.
  const double lost = eb::relativeResidual(1.0, 0.0, 0.6, {}, 0.0);
  expect(formal::checkWithinBounds("energy.lost_secondary_negative_control", "", {lost}, {0.0},
                                   {eb::kRelativeTolerance}, 0.0),
         false);
  if (!std::isnan(eb::relativeResidual(1.0, 0.0, std::nan(""), {}, 0.0)) ||
      eb::relativeResidual(0.0, 0.0, 0.0, {}, 0.0) != 0.0) {
    std::fprintf(stderr, "relativeResidual mishandles non-finite or empty steps\n");
    ++failures;
  }
}

void twoBodyPairs() {
  // Trech.Laws.TwoBody.compton_relation: the classic scatteredEnergyRatio must give kinematics
  // that conserve three-momentum when the electron is built the way Geant4's free-electron model
  // builds it: direction (E k - E' k').unit(), magnitude sqrt(T (T + 2 m)) with T = E - E'.
  namespace eb = trech::sim::energy_balance;
  const double me = 0.51099895;
  std::vector<double> residuals, wrong, zeros, tolerances;
  auto residualFor = [&](double eps, double c, double ratioScale) {
    const double e = eps * me;
    const double post = kn::scatteredEnergyRatio(eps, c) * e * ratioScale;
    const double s = std::sqrt(std::max(0.0, 1.0 - c * c));
    const eb::Momentum k = {0.0, 0.0, e}, kp = {post * s, 0.0, post * c};
    const double t = e - post;
    double dx = k[0] - kp[0], dy = k[1] - kp[1], dz = k[2] - kp[2];
    const double norm = std::sqrt(dx * dx + dy * dy + dz * dz);
    const double pe = std::sqrt(std::max(0.0, t * (t + 2.0 * me)));
    if (norm > 0.0) { dx *= pe / norm; dy *= pe / norm; dz *= pe / norm; }
    return eb::relativeMomentumResidual(k, kp, {{dx, dy, dz}});
  };
  std::vector<double> flat;
  for (double eps : kEps)
    for (double c : cosGrid()) {
      residuals.push_back(residualFor(eps, c, 1.0));
      wrong.push_back(residualFor(eps, c, 1.01));
      zeros.push_back(0.0);
      const double e = eps * me;
      tolerances.push_back(eb::momentumRoundingBound(e - kn::scatteredEnergyRatio(eps, c) * e, me));
      flat.push_back(eb::kRelativeTolerance);
    }
  expect(formal::checkWithinBounds("compton.momentum_balance", "Trech.Laws.TwoBody.compton_relation",
                                   residuals, zeros, tolerances, 0.0));
  // The rounding model is needed: a flat 1e-12 misses at eps = 1e-4 (2.7e-12 measured), where
  // the electron's energy is a tiny difference of two photon energies.
  expect(formal::checkWithinBounds("compton.momentum_flat_tolerance_negative_control", "", residuals, zeros,
                                   flat, 0.0),
         false);
  // A scattered energy 1% off the relation leaves momentum unbalanced.
  expect(formal::checkWithinBounds("compton.momentum_negative_control", "", wrong, zeros, tolerances, 0.0),
         false);
}

void attenuationPairs() {
  // Trech.Laws.Attenuation.survival_add on the classic std::exp(-mu x) of the beer_lambert check.
  const double mu = 0.0707;  // 1/mm, any positive coefficient
  std::vector<double> joint, split;
  for (double x : {0.0, 0.5, 3.0, 12.5, 40.0})
    for (double y : {0.0, 1.0, 7.0, 25.0}) {
      joint.push_back(std::exp(-(mu * (x + y))));
      split.push_back(std::exp(-(mu * x)) * std::exp(-(mu * y)));
    }
  // Over the reals the two sides are equal; in doubles each exp rounds (libm is not correctly
  // rounded) and so does the product, so they differ by a few ulp (2.3e-16 relative is seen on
  // macOS arm64). The tolerance states that float gap explicitly.
  expect(formal::checkAgreement("attenuation.memoryless", "Trech.Laws.Attenuation.survival_add", joint,
                                split, 0.0, 2e-15));
  expect(formal::checkAgreement("attenuation.memoryless_exact_negative_control", "", joint, split, 0.0, 0.0),
         false);
}

// D2Q9 on a periodic nx * ny box, population-major as LatticeKinetic.hpp expects.
struct D2Q9 {
  static constexpr std::size_t q = 9;
  double cx[q] = {0, 1, 0, -1, 0, 1, -1, -1, 1};
  double cy[q] = {0, 0, 1, 0, -1, 1, 1, -1, -1};
  double cz[q] = {0, 0, 0, 0, 0, 0, 0, 0, 0};
  double w[q] = {4.0 / 9, 1.0 / 9, 1.0 / 9, 1.0 / 9, 1.0 / 9, 1.0 / 36, 1.0 / 36, 1.0 / 36, 1.0 / 36};
  int32_t opp[q] = {0, 3, 4, 1, 2, 7, 8, 5, 6};
};

void latticePairs() {
  const D2Q9 set;
  const int nx = 7, ny = 5;
  const std::size_t cells = static_cast<std::size_t>(nx * ny), total = set.q * cells;

  // Hypotheses of Trech.Methods.Lattice.relaxTRT_sum_eq (opp is an involution, the moments give
  // sum feq = rho and a zero-sum Guo forcing) and of stream_sum_eq (src is a bijection).
  expect(formal::checkVelocityMoments("lattice.velocity_moments", "Trech.Methods.Lattice.relaxTRT_sum_eq",
                                      set.q, set.cx, set.cy, set.cz, set.w, 1.0 / 3.0, 2, 1e-15));
  expect(formal::checkInvolution("lattice.opposite_involution", "Trech.Methods.Lattice.relaxTRT_sum_eq",
                                 set.opp, set.q));

  std::vector<int32_t> src(total);
  for (std::size_t k = 0; k < set.q; ++k)
    for (int y = 0; y < ny; ++y)
      for (int x = 0; x < nx; ++x) {
        // Pull streaming: slot (k, cell) receives the post-collision value from upstream.
        const int ux = ((x - static_cast<int>(set.cx[k])) % nx + nx) % nx;
        const int uy = ((y - static_cast<int>(set.cy[k])) % ny + ny) % ny;
        src[k * cells + static_cast<std::size_t>(y * nx + x)] =
            static_cast<int32_t>(k * cells + static_cast<std::size_t>(uy * nx + ux));
      }
  expect(formal::checkPermutation("lattice.streaming_bijection", "Trech.Methods.Lattice.stream_sum_eq",
                                  src.data(), total));
  std::vector<int32_t> broken = src;
  broken[3] = broken[4];
  expect(formal::checkPermutation("lattice.negative_control", "", broken.data(), total), false);

  // Conformance: the classic kernel conserves the total over many steps, with a body force.
  std::vector<double> f(total), post(total), rho(cells), ux(cells), uy(cells), uz(cells);
  std::uint64_t state = 0x9e3779b97f4a7c15ULL;
  for (std::size_t k = 0; k < set.q; ++k)
    for (std::size_t i = 0; i < cells; ++i) {
      state = state * 6364136223846793005ULL + 1442695040888963407ULL;
      const double jitter = static_cast<double>(state >> 11) / 9007199254740992.0;  // [0, 1)
      f[k * cells + i] = set.w[k] * (1.0 + 0.2 * (jitter - 0.5));
    }
  const std::vector<double> before = f;
  trech::LatticeFlowView view;
  view.set = {set.q, set.cx, set.cy, set.cz, set.w, set.opp, 1.0 / 3.0};
  view.cells = cells;
  view.omegaPlus = 1.0 / 0.8;
  view.omegaMinus = 1.0 / (0.5 + 0.1875 / (0.8 - 0.5));  // magic parameter 3/16
  view.f = f.data();
  view.post = post.data();
  view.src = src.data();
  view.rho = rho.data();
  view.ux = ux.data();
  view.uy = uy.data();
  view.uz = uz.data();
  trech::LatticeCoupling coupling;
  coupling.base[0] = 1e-5;
  coupling.base[1] = -2e-5;
  const auto result = trech::advanceLattice(view, nullptr, coupling, 300);
  if (result.nonphysical || result.steps != 300) {
    std::fprintf(stderr, "lattice advance stopped early\n");
    ++failures;
  }
  expect(formal::checkConservedTotal("lattice.collision_conserves_mass",
                                     "Trech.Methods.Lattice.relaxTRT_sum_eq", before, f, 1e-13));
}

void scalarLatticePairs() {
  // Trech.Methods.Lattice.advectedEquilibrium_sum + relaxTRT_sum_eq + stream_sum_eq on the engine's
  // scalar lattice: zero-flux walls, an interior solid block, a prescribed advection velocity and
  // no source conserve the total. The engine's own build-time hypothesis checks must all pass.
  trech::lattice::LatticeSpec spec;
  spec.shape = {11, 8, 1};
  spec.flow = false;
  spec.scalarLattice = "D2Q5";
  spec.diffusivity = 0.05;
  spec.solid = [](int x, int y, int) { return x >= 4 && x <= 5 && y >= 3 && y <= 4; };
  spec.initialScalar = [](int x, int y, int) { return 1.0 + 0.1 * x - 0.03 * y * y; };
  trech::lattice::Lattice lattice(spec);
  const std::size_t F = lattice.domain().count();
  lattice.advectionX().assign(F, 0.04);
  lattice.advectionY().assign(F, -0.02);
  lattice.advectionZ().assign(F, 0.0);
  for (const auto& check : lattice.lawChecks()) expect(check);
  if (lattice.lawChecks().size() != 3) {
    std::fprintf(stderr, "scalar lattice recorded %zu law checks, expected 3\n", lattice.lawChecks().size());
    ++failures;
  }
  const std::vector<double> before = lattice.scalarValues();
  lattice.advance(400);
  const std::vector<double> after = lattice.scalarValues();
  expect(formal::checkConservedTotal("lattice.scalar_conserves_total",
                                     "Trech.Methods.Lattice.advectedEquilibrium_sum", before, after, 1e-13));
  // A Dirichlet wall exchanges scalar by design: the bijection still holds, and the check says why
  // conservation does not apply, while the total moves.
  spec.dirichlet = [](int, int, int, int, int, int, double& value) { value = 3.0; return true; };
  trech::lattice::Lattice open(spec);
  const auto& stream = open.lawChecks().back();
  if (!stream.passed || stream.detail.find("by design") == std::string::npos) {
    std::fprintf(stderr, "Dirichlet lattice should note that it is not conservative by design\n");
    ++failures;
  }
  const std::vector<double> openBefore = open.scalarValues();
  open.advance(50);
  expect(formal::checkConservedTotal("lattice.scalar_dirichlet_negative_control", "", openBefore, open.scalarValues(),
                                     1e-13),
         false);
  // A walled D3Q19 flow lattice: the engine's flow hypotheses hold.
  trech::lattice::LatticeSpec flow;
  flow.shape = {6, 5, 4};
  flow.scalar = false;
  trech::lattice::Lattice walled(flow);
  for (const auto& check : walled.lawChecks()) expect(check);
}

void transitionPairs() {
  // Trech.Methods.Transition on the engine's own two-stage draw (selectTransitionChannel): sweep the
  // uniform draw over a grid of [0, 1) and compare each outcome's share with h * s_c / S.
  const std::size_t N = 1u << 20;
  struct Case { double hazard; std::vector<double> scores; };
  std::vector<Case> cases = {
      {0.3, {0.2, 0.5, 0.3}},           // weighted mode: event hazard and channel weights
      {0.12, {0.07, 0.0, 0.05}},        // direct mode below 1: h = sum, a zero channel never fires
      {1.0, {0.6, 0.9, 0.25, 0.4}},     // direct mode renormalised: sum > 1, h = 1
      {0.999, {1e-3, 1.0}},             // a rare channel
  };
  std::vector<double> measured, expected, withoutHazard;
  for (const auto& k : cases) {
    double S = 0.0;
    for (double s : k.scores) S += s;
    std::vector<double> hits(k.scores.size() + 1, 0.0);  // channels, then "no transition"
    for (std::size_t i = 0; i < N; ++i) {
      const double u = static_cast<double>(i) / static_cast<double>(N);
      const long c = trech::ml::selectTransitionChannel(u, k.hazard, k.scores.data(), S, k.scores.size());
      hits[c < 0 ? k.scores.size() : static_cast<std::size_t>(c)] += 1.0 / static_cast<double>(N);
    }
    expect(formal::checkProbabilityVector("transition.outcomes_probability_vector",
                                          "Trech.Methods.Transition.noEvent_nonneg", hits, 1e-12));
    for (std::size_t c = 0; c < k.scores.size(); ++c) {
      measured.push_back(hits[c]);
      expected.push_back(k.hazard * k.scores[c] / S);
      withoutHazard.push_back(k.scores[c] / S);
    }
    measured.push_back(hits.back());
    expected.push_back(1.0 - k.hazard);
    withoutHazard.push_back(0.0);
  }
  // Each interval edge can land between two grid points: at most 2/N per outcome.
  expect(formal::checkAgreement("transition.channel_probability", "Trech.Methods.Transition.sum_stepProbability",
                                measured, expected, 2.0 / static_cast<double>(N), 0.0));
  expect(formal::checkAgreement("transition.negative_control", "", measured, withoutHazard,
                                2.0 / static_cast<double>(N), 0.0),
         false);
}

void loadConformanceModel(trech::ml::GenericSurrogate& model, const std::string& path,
                          std::vector<std::string> outputs, std::vector<double> bias) {
  const nlohmann::json layer = {{"weights", std::vector<std::vector<double>>(bias.size(), {0.0})},
                                {"bias", bias}, {"activation", "none"}};
  const nlohmann::json spec = {{"model", "generic_surrogate_v1"}, {"input_features", {"dt"}},
                               {"output_features", outputs}, {"layers", {layer}}};
  std::ofstream(path) << spec;
  if (!model.load(path)) throw std::runtime_error("Could not load conformance model: " + path);
}

void transitionConservation() {
  const trech::test::TemporaryDirectory fixture;
  trech::ml::GenericSurrogate model;
  loadConformanceModel(model, (fixture.path() / "transition.json").string(), {"hazard_split"}, {1.0});
  trech::ml::DiscreteTransition transition;
  transition.addStage("split", trech::ml::DimensionScale::kMicro, &model);
  const auto limit = std::numeric_limits<std::int64_t>::max();
  trech::ml::DiscreteTransitionRequest request;
  request.speciesNames = {"whole", "half"};
  request.elementCount = 4;
  request.dt = 1.0;
  request.state = {5, 1, 0, 4, 1, limit - 1, 1, limit - 2};
  request.channels = {{"split", {-1, 2}}};
  request.conservation = {{"units", {2, 1}}};
  const auto run = transition.react(request);
  if (run.transitionsAccepted != 2 || run.rejectedAvailability != 2 ||
      run.state != std::vector<std::int64_t>{4, 3, 0, 4, 1, limit - 1, 0, limit}) {
    throw std::runtime_error("Transition failed to apply or reject each full channel atomically");
  }
  std::vector<double> before, after;
  for (std::size_t i = 0; i < 4; i += 2) {
    before.push_back(static_cast<double>(2 * request.state[i] + request.state[i + 1]));
    after.push_back(static_cast<double>(2 * run.state[i] + run.state[i + 1]));
  }
  expect(formal::checkAgreement("transition.declared_conservation",
                                "Trech.Methods.Transition.applyChannel_conserves",
                                before, after, 0.0, 0.0));
  const bool allInRange = std::all_of(run.state.begin(), run.state.end(),
                                     [](std::int64_t count) { return count >= 0; });
  expect(formal::checkAgreement("transition.nonnegative_counts",
                                "Trech.Methods.Transition.applyChannel_nonnegative",
                                {static_cast<double>(allInRange)}, {1.0}, 0.0, 0.0));

  request.channels[0].delta = {-1, 1};
  const auto unbalanced = transition.react(request);
  if (unbalanced.transitionSchemaValid || unbalanced.drawCount != 0 || unbalanced.state != request.state ||
      unbalanced.channelTrace.at(0).violatedConservation != std::vector<std::string>{"units"}) {
    throw std::runtime_error("Unbalanced transition must be reported before drawing or applying");
  }
  request.conservation.clear();
  request.channels[0].delta = {std::numeric_limits<std::int64_t>::min(), 1};
  const auto insufficient = transition.react(request);
  if (insufficient.rejectedAvailability != request.elementCount || insufficient.state != request.state) {
    throw std::runtime_error("Most negative signed delta must be rejected atomically");
  }
}

void pairConservation() {
  const trech::test::TemporaryDirectory fixture;
  trech::ml::GenericSurrogate model;
  loadConformanceModel(model, (fixture.path() / "pair.json").string(), {"d_heat_dt", "add_heat"}, {1.3, 0.2});
  trech::ml::PairInteraction interaction;
  interaction.addStage("exchange", trech::ml::DimensionScale::kMicro, &model);
  trech::ml::PairInteractionRequest request;
  request.elementCount = 3;
  request.fields = {{"heat"}};
  request.links = {{0, 1}, {1, 2}};
  request.state = {4.0, 3.0, 2.0};
  request.dt = 0.3;
  const auto run = interaction.interact(request);
  if (run.inferenceCount != 2 || run.state == request.state) {
    throw std::runtime_error("Both pair links must contribute to the exchange");
  }
  const char* declaration = "Trech.Methods.PairInteraction.exchange_preserves_sum";
  expect(formal::checkAgreement("pair.antisymmetric_exchange", declaration,
                                run.state, {4.59, 3.0, 1.41}, 2e-15, 0.0));
  expect(formal::checkConservedTotal("pair.exchange_conserves_total", declaration, request.state, run.state, 1e-15));
  request.fields[0].maxValue = 4.0;
  const auto clipped = interaction.interact(request);
  expect(formal::checkConservedTotal("pair.clipped_exchange_negative_control", "", request.state, clipped.state, 1e-15),
         false);
}

void evolvePairs() {
  // Trech.Methods.Evolve on the engine's StateEvolution::evolve: one constant-rate stage drives
  // bounded fields across both bounds and an unbounded field; the classic step must stay within
  // ordered bounds, leave an unclipped step exact, and scale its increment with dt.
  const trech::test::TemporaryDirectory fixture;
  trech::ml::GenericSurrogate model;
  const double rateA = 0.75, rateB = -1.5;
  loadConformanceModel(model, (fixture.path() / "evolve.json").string(), {"d_a_dt", "d_b_dt"}, {rateA, rateB});
  trech::ml::StateEvolution evolution;
  evolution.addStage("drive", trech::ml::DimensionScale::kMicro, &model);
  trech::ml::EvolutionRequest request;
  request.fields = {{"a", 0.0, 1.0}, {"b"}};
  request.fields[1].minValue = -2.0;  // one-sided: no upper bound
  const std::size_t n = 41;
  request.elementCount = n;
  for (std::size_t e = 0; e < n; ++e) {
    const double x = -0.5 + 2.0 * static_cast<double>(e) / static_cast<double>(n - 1);  // [-0.5, 1.5]
    request.state.push_back(x);
    request.state.push_back(x);
  }
  request.dt = 0.4;
  const auto run = evolution.evolve(request);
  if (run.state.size() != request.state.size() || run.inferenceCount != n) {
    throw std::runtime_error("Evolution conformance stage must run on every element");
  }
  std::vector<double> stepped, expected, inside, insideExpected;
  std::vector<double> a, b;
  for (std::size_t e = 0; e < n; ++e) {
    const double x = request.state[2 * e];
    a.push_back(run.state[2 * e]);
    b.push_back(run.state[2 * e + 1]);
    for (int f = 0; f < 2; ++f) {
      const double rate = f == 0 ? rateA : rateB;
      const double unclamped = x + rate * request.dt;
      const auto& field = request.fields[static_cast<std::size_t>(f)];
      stepped.push_back(run.state[2 * e + static_cast<std::size_t>(f)]);
      expected.push_back(std::min(field.maxValue, std::max(field.minValue, unclamped)));  // Lean clampBounds
      if (unclamped >= field.minValue && unclamped <= field.maxValue) {
        inside.push_back(run.state[2 * e + static_cast<std::size_t>(f)]);
        insideExpected.push_back(unclamped);
      }
    }
  }
  const char* mem = "Trech.Methods.Evolve.boundedStep_mem";
  expect(formal::checkWithinBounds("evolve.bounded_step_within_bounds", mem, a, std::vector<double>(n, 0.0),
                                   std::vector<double>(n, 1.0), 0.0));
  expect(formal::checkWithinBounds("evolve.bounded_step_within_bounds", mem, b, std::vector<double>(n, -2.0),
                                   std::vector<double>(n, std::numeric_limits<double>::infinity()), 0.0));
  expect(formal::checkAgreement("evolve.bounded_step_within_bounds", "Trech.Methods.Evolve.clampBounds_eq_projIcc",
                                stepped, expected, 0.0, 1e-15));
  if (inside.size() < n / 2 || inside.size() == stepped.size()) {
    throw std::runtime_error("Evolution conformance grid must hold clipped and unclipped steps");
  }
  expect(formal::checkAgreement("evolve.unclipped_step_exact", "Trech.Methods.Evolve.boundedStep_of_mem", inside,
                                insideExpected, 0.0, 1e-15));

  // Linear in dt: with bounds wide enough to stay unclipped, k * dt gives k times the increment,
  // and two steps of dt equal one of 2 dt (eulerStep_add_dt), within a few ulp.
  request.fields = {{"a"}, {"b"}};
  const auto one = evolution.evolve(request);
  std::vector<double> scaled, scaledExpected;
  for (double k : {0.25, 2.0, 3.0}) {
    auto longer = request;
    longer.dt = k * request.dt;
    const auto r = evolution.evolve(longer);
    for (std::size_t i = 0; i < request.state.size(); ++i) {
      scaled.push_back(r.state[i] - request.state[i]);
      scaledExpected.push_back(k * (one.state[i] - request.state[i]));
    }
  }
  auto twice = request;
  twice.state = one.state;
  const auto second = evolution.evolve(twice);
  auto doubled = request;
  doubled.dt = 2.0 * request.dt;
  const auto once = evolution.evolve(doubled);
  expect(formal::checkAgreement("evolve.rate_linear_in_dt", "Trech.Methods.Evolve.eulerStep_smul_dt", scaled,
                                scaledExpected, 1e-15, 1e-14));
  expect(formal::checkAgreement("evolve.rate_linear_in_dt", "Trech.Methods.Evolve.eulerStep_add_dt", second.state,
                                once.state, 1e-15, 1e-15));

  // The hypothesis lo <= hi: the JS boundary rejects what boundsOrdered refuses (tests/test_js_runtime.cpp).
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double inf = std::numeric_limits<double>::infinity();
  std::vector<double> ordered;
  for (const auto& [lo, hi] : std::vector<std::pair<double, double>>{
           {0.0, 1.0}, {-inf, inf}, {2.0, 2.0}, {1.0, 0.0}, {nan, 1.0}, {0.0, nan}}) {
    ordered.push_back(trech::ml::boundsOrdered(lo, hi) ? 1.0 : 0.0);
  }
  expect(formal::checkAgreement("evolve.ordered_bounds_rejected", "Trech.Methods.Evolve.boundedStep_mem", ordered,
                                {1, 1, 1, 0, 0, 0}, 0.0, 0.0));
  // Negative control: unordered bounds (what the boundary rejects) break the lower bound.
  expect(formal::checkWithinBounds("evolve.unordered_bounds_negative_control", "",
                                   {trech::ml::boundedEulerStep(0.5, 0.0, 1.0, 1.0, 0.0)}, {1.0}, {0.0}, 0.0),
         false);
}

void setPoolPairs() {
  // Trech.Methods.SetPool on GenericSurrogate::predictSet: the committed set-network fixtures
  // (DeepSets with a max pool, message passing with a sum aggregate and a mean pool) and their
  // sum/mean/max and aggregate variants, evaluated under all 24 orders of their four element
  // blocks. Max pools are exact; sums round in a different order, so a tolerance is stated.
  const std::string dir = std::string(TRECH_SOURCE_DIR) + "/tests/fixtures/ml_set_networks/";
  const auto rows = nlohmann::json::parse(std::ifstream(dir + "expected.json")).at("rows")
                        .get<std::vector<std::vector<double>>>();
  const trech::test::TemporaryDirectory fixture;
  struct Variant { std::string kind, pool, aggregate; };
  const std::vector<Variant> variants = {{"deepsets", "max", ""}, {"deepsets", "sum", ""}, {"deepsets", "mean", ""},
                                         {"mpnn", "mean", "sum"}, {"mpnn", "max", "mean"}, {"mpnn", "sum", "sum"}};
  for (const auto& v : variants) {
    auto spec = nlohmann::json::parse(std::ifstream(dir + v.kind + ".json"));
    spec["network"]["pool"] = v.pool;
    if (!v.aggregate.empty()) spec["network"]["aggregate"] = v.aggregate;
    const std::string label = v.kind + "/" + v.pool + (v.aggregate.empty() ? "" : "/" + v.aggregate);
    const auto path = (fixture.path() / (v.kind + "_" + v.pool + "_" + v.aggregate + ".json")).string();
    std::ofstream(path) << spec;
    trech::ml::GenericSurrogate model;
    if (!model.load(path)) throw std::runtime_error("Set-network variant failed to load: " + label);
    const std::size_t E = spec["network"]["elements"], F = spec["network"]["element_features"];
    const std::size_t mask = spec["network"]["mask_feature"];
    trech::ml::GenericSurrogate::Workspace workspace;
    std::vector<double> original, permuted;
    std::vector<std::size_t> order(E);
    for (const auto& row : rows) {
      double reference = 0.0;
      if (!model.predictInto(row.data(), row.size(), &reference, 1, workspace)) {
        throw std::runtime_error("Set-network variant failed to predict: " + label);
      }
      std::iota(order.begin(), order.end(), 0);
      do {
        auto shuffled = row;
        for (std::size_t e = 0; e < E; ++e)
          std::copy(row.begin() + static_cast<long>(order[e] * F), row.begin() + static_cast<long>((order[e] + 1) * F),
                    shuffled.begin() + static_cast<long>(e * F));
        double out = 0.0;
        model.predictInto(shuffled.data(), shuffled.size(), &out, 1, workspace);
        original.push_back(reference);
        permuted.push_back(out);
      } while (std::next_permutation(order.begin(), order.end()));
    }
    const bool exact = v.pool == "max" && (v.kind == "deepsets");
    expect(formal::checkAgreement("set.permutation_invariance",
                                  v.kind == "mpnn" ? "Trech.Methods.SetPool.mpnnRound_perm"
                                                   : "Trech.Methods.SetPool.deepSets_perm",
                                  original, permuted, 0.0, exact ? 0.0 : 1e-12));
    // An absent element (raw mask <= 0.5) takes no part: its other features may change freely.
    std::vector<double> kept, changed;
    for (const auto& row : rows) {
      for (std::size_t e = 0; e < E; ++e) {
        if (row[e * F + mask] > 0.5) continue;
        auto moved = row;
        for (std::size_t f = 0; f < F; ++f)
          if (f != mask) moved[e * F + f] = 37.0 * static_cast<double>(f + 1) - 11.0;
        double a = 0.0, b = 0.0;
        model.predictInto(row.data(), row.size(), &a, 1, workspace);
        model.predictInto(moved.data(), moved.size(), &b, 1, workspace);
        kept.push_back(a);
        changed.push_back(b);
      }
    }
    if (kept.empty()) throw std::runtime_error("Set-network fixtures need an absent element: " + label);
    expect(formal::checkAgreement("set.absent_element_ignored", "Trech.Methods.SetPool.sumPool_update_absent", kept,
                                  changed, 0.0, 0.0));
  }
  // The hypothesis: element slots share input standardisation. A model whose slot 2 differs is
  // refused at load, because permuting its blocks would change the standardised inputs.
  auto untied = nlohmann::json::parse(std::ifstream(dir + "deepsets.json"));
  const std::size_t F = untied["network"]["element_features"];
  untied["input_mean"][2 * F] = untied["input_mean"][2 * F].get<double>() + 0.25;
  const auto untiedPath = (fixture.path() / "untied.json").string();
  std::ofstream(untiedPath) << untied;
  trech::ml::GenericSurrogate refused;
  const bool loaded = refused.load(untiedPath);
  const bool noted = refused.note().find("share input_mean/input_std") != std::string::npos;
  expect(formal::checkAgreement("set.shared_slot_standardisation", "Trech.Methods.SetPool.deepSets_perm",
                                {loaded ? 1.0 : 0.0, noted ? 1.0 : 0.0}, {0.0, 1.0}, 0.0, 0.0));
}

void groupPairs() {
  // Trech.Methods.Group on GroupHierarchy::run: the committed three-level lift fixtures (cell,
  // block and system models) with unequal member weights, and an explicit first level. At each
  // level every lower element has one parent, the group weights add up to the lower total, and
  // the weighted first moment of the groups (weight times centroid) equals the lower one.
  const std::string dir = std::string(TRECH_SOURCE_DIR) + "/tests/fixtures/ml_group_hierarchy/";
  trech::ml::GenericSurrogate cell, block, system;
  if (!cell.load(dir + "cell.json") || !block.load(dir + "block.json") || !system.load(dir + "system.json")) {
    throw std::runtime_error("Group-lift fixtures failed to load");
  }
  using Spec = trech::ml::GroupLevelSpec;
  std::vector<Spec> levels(3);
  levels[0] = {"cell", trech::ml::DimensionScale::kNano, &cell, Spec::Grouping::kCell, cell.groupLift().cellSize, {}, 0.0};
  levels[1] = {"block", trech::ml::DimensionScale::kMicro, &block, Spec::Grouping::kCell, block.groupLift().cellSize, {}, 0.0};
  levels[2] = {"system", trech::ml::DimensionScale::kMeso, &system, Spec::Grouping::kAll, 0.0, {}, 4.0};
  const auto expected = nlohmann::json::parse(std::ifstream(dir + "expected.json"));
  std::vector<double> parentsOk, lowerWeight, groupWeight, lowerMoment, groupMoment;
  std::size_t levelsChecked = 0;
  auto checkRun = [&](const trech::ml::GroupLiftInput& input, const std::vector<Spec>& specs, bool requireAll) {
    const auto run = trech::ml::GroupHierarchy::run(input, specs);
    if (requireAll && run.levelsRun != specs.size()) throw std::runtime_error("Group lift stopped: " + run.stopReason);
    std::vector<double> w = input.weights, p = input.positions;
    for (const auto& lr : run.levels) {
      if (!lr.ran) break;
      std::vector<long long> seen(lr.groups, 0);
      bool ok = lr.parent.size() == w.size();
      for (long long g : lr.parent) {
        ok = ok && g >= 0 && static_cast<std::size_t>(g) < lr.groups;
        if (ok) ++seen[static_cast<std::size_t>(g)];
      }
      for (std::size_t g = 0; ok && g < lr.groups; ++g) ok = seen[g] == lr.memberCount[g] && seen[g] > 0;
      parentsOk.push_back(ok ? 1.0 : 0.0);
      lowerWeight.push_back(formal::compensatedSum(w.data(), w.size()));
      groupWeight.push_back(formal::compensatedSum(lr.weights.data(), lr.weights.size()));
      for (int a = 0; a < 3; ++a) {
        double lower = 0.0, upper = 0.0;
        for (std::size_t i = 0; i < w.size(); ++i) lower += w[i] * p[i * 3 + static_cast<std::size_t>(a)];
        for (std::size_t g = 0; g < lr.groups; ++g) upper += lr.weights[g] * lr.positions[g * 3 + static_cast<std::size_t>(a)];
        lowerMoment.push_back(lower);
        groupMoment.push_back(upper);
      }
      w = lr.weights;
      p = lr.positions;
      ++levelsChecked;
    }
  };
  for (const auto& c : expected.at("cases")) {
    trech::ml::GroupLiftInput input;
    input.featureNames = {"q"};
    input.features = c.at("features").at("q").get<std::vector<double>>();
    input.count = input.features.size();
    input.hasPositions = true;
    const auto x = c.at("positions").at("x").get<std::vector<double>>();
    const auto y = c.at("positions").at("y").get<std::vector<double>>();
    const auto z = c.at("positions").at("z").get<std::vector<double>>();
    for (std::size_t i = 0; i < input.count; ++i) {
      input.positions.insert(input.positions.end(), {x[i], y[i], z[i]});
      input.weights.push_back(0.5 + 0.37 * static_cast<double>(i % 5));
    }
    input.context["g"] = c.at("context").at("g").get<double>();
    checkRun(input, levels, true);
    auto explicitLevels = levels;  // an explicit first level: groups of four by index
    explicitLevels[0].grouping = Spec::Grouping::kExplicit;
    explicitLevels[0].length = 1.0;
    for (std::size_t i = 0; i < input.count; ++i) explicitLevels[0].groupIds.push_back(static_cast<long long>(i / 4));
    checkRun(input, explicitLevels, false);
  }
  if (levelsChecked < 6) throw std::runtime_error("Group-lift conformance checked too few levels");
  expect(formal::checkAgreement("group.member_unique", "Trech.Methods.Group.mem_group_unique", parentsOk,
                                std::vector<double>(parentsOk.size(), 1.0), 0.0, 0.0));
  expect(formal::checkAgreement("group.weight_conserved", "Trech.Methods.Group.sum_groupWeight", lowerWeight,
                                groupWeight, 0.0, 1e-14));
  expect(formal::checkAgreement("group.moment_conserved", "Trech.Methods.Group.sum_weight_centroid", lowerMoment,
                                groupMoment, 1e-13, 1e-13));
  // Negative control: a group whose members weigh zero has no centroid (NaN), the excluded case.
  trech::ml::GroupLiftInput zero;
  zero.count = 2;
  zero.featureNames = {"q"};
  zero.features = {1.0, 2.0};
  zero.hasPositions = true;
  zero.positions = {0.2, 0.2, 0.2, 0.4, 0.4, 0.4};
  zero.weights = {0.0, 0.0};
  zero.context["g"] = 0.0;
  const auto run = trech::ml::GroupHierarchy::run(zero, {levels[0]});
  expect(formal::checkAgreement("group.zero_weight_negative_control", "", {run.levels.at(0).positions.at(0)}, {0.3},
                                1e-12, 0.0),
         false);
}

void leastSquaresPairs() {
  // Trech.Methods.LeastSquares on sseFromStatistics, the domain learner's split score: weighted
  // rows with a quadratic basis and two targets, scored from statistics at 9 cuts (prefix sums
  // for the left side, total minus prefix for the right) and directly from residuals.
  const int64_t n = 240, p = 4, t = 2;
  std::uint64_t state = 0x9e3779b97f4a7c15ULL;
  auto uniform = [&]() {
    state = state * 6364136223846793005ULL + 1442695040888963407ULL;
    return static_cast<double>(state >> 11) / 9007199254740992.0;
  };
  std::vector<double> phiData, yData, wData;
  for (int64_t i = 0; i < n; ++i) {
    const double x = 4.0 * uniform() - 2.0, z = uniform();
    phiData.insert(phiData.end(), {1.0, x, x * x, z});
    yData.push_back((x < 0.3 ? 1.5 * x : 3.0 - x) + 0.1 * (uniform() - 0.5));
    yData.push_back(2.0 * z * z + 0.05 * (uniform() - 0.5));
    wData.push_back(0.25 + uniform());
  }
  const auto opts = at::TensorOptions().dtype(at::kDouble);
  const auto phi = at::from_blob(phiData.data(), {n, p}, opts).clone();
  const auto y = at::from_blob(yData.data(), {n, t}, opts).clone();
  const auto w = at::from_blob(wData.data(), {n}, opts).clone();
  auto stats = [&](int64_t a, int64_t b) {
    const auto ph = phi.slice(0, a, b), yy = y.slice(0, a, b), wc = w.slice(0, a, b).unsqueeze(1);
    return std::array<at::Tensor, 3>{(ph * wc).t().mm(ph), (ph * wc).t().mm(yy), (yy.square() * wc).sum()};
  };
  auto direct = [&](int64_t a, int64_t b, const at::Tensor& beta) {
    const auto r = y.slice(0, a, b) - phi.slice(0, a, b).mm(beta);
    return (r.square() * w.slice(0, a, b).unsqueeze(1)).sum().item<double>();
  };
  auto ridge = [&](const at::Tensor& a) { return a + 1e-6 * at::eye(p, opts); };
  const auto total = stats(0, n);
  std::vector<double> fromStats, fromRows, scale, sumParts, sumWhole, splitError, parentError;
  for (int64_t cut = 24; cut < n; cut += 24) {
    const auto left = stats(0, cut), right = stats(cut, n);
    for (int s = 0; s < 3; ++s) {  // gram_union, moment_union, yy_union
      const auto parts = (left[static_cast<std::size_t>(s)] + right[static_cast<std::size_t>(s)]).flatten();
      const auto whole = total[static_cast<std::size_t>(s)].flatten();
      for (int64_t k = 0; k < parts.numel(); ++k) {
        sumParts.push_back(parts[k].item<double>());
        sumWhole.push_back(whole[k].item<double>());
      }
    }
    // The learner's form: prefix sums and total minus prefix, batched over [left, right].
    const auto a = at::stack({left[0], total[0] - left[0]});
    const auto b = at::stack({left[1], total[1] - left[1]});
    const auto c = at::stack({left[2], total[2] - left[2]});
    const auto betas = at::linalg_solve(ridge(a), b);
    const auto scores = trech::ml::sseFromStatistics(a, b, c, betas);
    const double rows[2] = {direct(0, cut, betas[0]), direct(cut, n, betas[1])};
    for (int side = 0; side < 2; ++side) {
      fromStats.push_back(scores[side].item<double>());
      fromRows.push_back(rows[side]);
      scale.push_back(c[side].item<double>());
    }
    // split_le_parent at exact least-squares minimisers.
    const auto exact = at::linalg_solve(a, b);
    const auto parentBeta = at::linalg_solve(total[0], total[1]);
    splitError.push_back(direct(0, cut, exact[0]) + direct(cut, n, exact[1]));
    parentError.push_back(direct(0, n, parentBeta));
  }
  // sse_eq_stat within eps-scale cancellation of c: |stat - direct| <= 1e-12 * c.
  double worst = 0.0;
  for (std::size_t i = 0; i < fromStats.size(); ++i)
    worst = std::max(worst, std::abs(fromStats[i] - fromRows[i]) / scale[i]);
  expect(formal::checkAgreement("least_squares.sse_from_statistics", "Trech.Methods.LeastSquares.sse_eq_stat",
                                {worst}, {0.0}, 1e-12, 0.0));
  expect(formal::checkAgreement("least_squares.statistics_add", "Trech.Methods.LeastSquares.gram_union", sumParts,
                                sumWhole, 1e-12, 1e-13));
  std::vector<double> margin;
  for (std::size_t i = 0; i < splitError.size(); ++i) margin.push_back(parentError[i] - splitError[i]);
  expect(formal::checkWithinBounds("least_squares.split_le_parent", "Trech.Methods.LeastSquares.split_le_parent",
                                   margin, std::vector<double>(margin.size(), -1e-12),
                                   std::vector<double>(margin.size(), std::numeric_limits<double>::infinity()), 0.0));
  // split_le_parent_ridge with the learner's per-side scale (mean Gram diagonal * 1e-9 + 1e-12).
  std::vector<double> ridgeMargin;
  auto lambda = [&](const at::Tensor& g) { return g.diagonal().mean().item<double>() * 1e-9 + 1e-12; };
  for (int64_t cut = 24; cut < n; cut += 24) {
    const auto left = stats(0, cut), right = stats(cut, n);
    const double lL = lambda(left[0]), lR = lambda(right[0]), lP = lambda(total[0]);
    const auto bL = at::linalg_solve(left[0] + lL * at::eye(p, opts), left[1]);
    const auto bR = at::linalg_solve(right[0] + lR * at::eye(p, opts), right[1]);
    const auto bP = at::linalg_solve(total[0] + lP * at::eye(p, opts), total[1]);
    ridgeMargin.push_back(direct(0, n, bP) + (lL + lR) * bP.square().sum().item<double>() -
                          direct(0, cut, bL) - direct(cut, n, bR));
  }
  expect(formal::checkWithinBounds("least_squares.split_le_parent_ridge",
                                   "Trech.Methods.LeastSquares.split_le_parent_ridge", ridgeMargin,
                                   std::vector<double>(ridgeMargin.size(), -1e-12),
                                   std::vector<double>(ridgeMargin.size(), std::numeric_limits<double>::infinity()),
                                   0.0));
  // bicGate_iff / bicGate_rejects on the learner's gate over a grid of scores and penalties.
  std::vector<double> gate, threshold, rejected;
  for (double neff : {3.0, 40.0, 900.0})
    for (double pen : {0.0, 1.5, 25.0})
      for (double ratio : {0.05, 0.5, 0.9, 0.97, 0.999, 1.0, 1.2}) {
        const double parent = 7.25, score = ratio * parent;
        const bool accepted = trech::ml::bicSplitAccepted(neff, score, parent, pen);
        const double cutoff = parent * std::exp(-pen / neff);
        if (std::abs(score - cutoff) <= 1e-12 * parent) continue;  // rounding at the boundary itself
        gate.push_back(accepted ? 1.0 : 0.0);
        threshold.push_back(score < cutoff ? 1.0 : 0.0);
        if (ratio >= 1.0) rejected.push_back(accepted ? 1.0 : 0.0);
      }
  expect(formal::checkAgreement("least_squares.bic_gate_threshold", "Trech.Methods.LeastSquares.bicGate_iff", gate,
                                threshold, 0.0, 0.0));
  expect(formal::checkAgreement("least_squares.bic_gate_rejects", "Trech.Methods.LeastSquares.bicGate_rejects",
                                rejected, std::vector<double>(rejected.size(), 0.0), 0.0, 0.0));
  // Negative control: the score with a wrong sign on the cross term is not the error.
  const auto a = total[0].unsqueeze(0), b = total[1].unsqueeze(0), c = total[2].unsqueeze(0);
  const auto beta = at::linalg_solve(ridge(a), b);
  const double wrong = (c + 2.0 * (beta * b).sum({1, 2}) + (beta * a.bmm(beta)).sum({1, 2}))[0].item<double>();
  expect(formal::checkAgreement("least_squares.sign_negative_control", "", {wrong}, {direct(0, n, beta[0])}, 1e-9, 0.0),
         false);
}

void arbiterPairs() {
  // Trech.Methods.Arbiter.squaredScore_mean_lt on the engine's MethodArbiter: with noisy references,
  // the method that predicts the conditional mean scores lowest and leads; biased methods lose.
  trech::ml::MethodArbiterOptions o;
  o.methods = {"low", "mean", "high"};
  o.features = {"x"};
  o.fallback = "low";  // the prior favours a biased method; evidence must overturn it
  trech::ml::MethodArbiter arbiter(o);
  std::uint64_t state = 0x2545f4914f6cdd1dULL;
  auto noise = [&]() {
    state = state * 6364136223846793005ULL + 1442695040888963407ULL;
    return 2.0 * (static_cast<double>(state >> 11) / 9007199254740992.0) - 1.0;  // [-1, 1)
  };
  const std::size_t n = 64;
  const double sigma = 0.2;
  std::string leader;
  for (int call = 0; call < 40; ++call) {
    trech::ml::MethodArbiterBatch b;
    b.time = call;
    b.count = n;
    for (std::size_t e = 0; e < n; ++e) {
      const double x = static_cast<double>(e) / static_cast<double>(n);
      const double mean = std::sin(3.0 * x) + 0.5 * x;
      b.features.push_back(x);
      b.predictions.insert(b.predictions.end(), {mean - 0.5 * sigma, mean, mean + 0.3 * sigma});
      b.reference.push_back(mean + sigma * noise());
    }
    leader = arbiter.step(b).leader;
  }
  const auto summary = arbiter.summary();
  std::vector<double> meanScore, otherScores;
  for (const char* m : {"low", "high"}) {
    meanScore.push_back(summary.at("methods").at("mean").at("rmse_common").get<double>());
    otherScores.push_back(summary.at("methods").at(m).at("rmse_common").get<double>());
  }
  // Bounds check: mean score <= each biased score (upper bound), from 0.
  expect(formal::checkWithinBounds("arbiter.mean_scores_lowest", "Trech.Methods.Arbiter.squaredScore_mean_lt",
                                   meanScore, {0.0, 0.0}, otherScores, 0.0));
  formal::LawCheck leads;
  leads.law = "arbiter.mean_leads";
  leads.leanDeclaration = "Trech.Methods.Arbiter.logError_lt_iff";
  leads.kind = "invariant";
  leads.samples = 1;
  leads.passed = leader == "mean" && summary.at("best_single_method") == "mean";
  if (!leads.passed) {
    leads.violations = 1;
    leads.detail = "leader " + leader + ", best single " + summary.at("best_single_method").get<std::string>();
  }
  expect(leads);
}

void javascriptPairs() {
  // The JS classic implementations: their own checks, then agreement with the C++ ones.
  const auto root = std::filesystem::path(TRECH_SOURCE_DIR);
  const trech::test::TemporaryDirectory fixture;
  const auto path = fixture.path() / "formal.js";
  nlohmann::json eps = kEps, cosines = cosGrid();
  {
    std::ofstream script(path);
    script << "TRECH_INCLUDE(" << nlohmann::json((root / "js/trech_formal_laws.js").string()).dump() << ");\n"
           << "const L = TRECH_FORMAL_LAWS, eps = " << eps.dump() << ", cosines = " << cosines.dump() << ";\n"
           << R"JS(
const ratios = [], edges = [];
for (const e of eps) { edges.push(L.compton.edgeFraction(e)); for (const c of cosines) ratios.push(L.compton.scatteredEnergyRatio(e, c)); }
globalThis.TRECH_CONFIG = {formal: {
  checks: L.checkComptonBounds(eps, cosines, 1e-15).concat([
    L.checkAttenuationMemoryless(0.0707, [[0.5, 1], [3, 7], [12.5, 25], [40, 25]], 2e-15),
    L.checkConservedTotal('negative_control', '', [1, 2, 3], [1, 2, 3.5], 1e-12)]),
  ratios, edges}};
)JS";
  }
  trech::JsRuntime runtime;
  const auto config = nlohmann::json::parse(runtime.evalExperimentAndGetConfigJson(path.string()));
  const auto& out = config.at("formal");
  for (const auto& check : out.at("checks")) {
    formal::LawCheck c;
    c.law = "js:" + check.at("law").get<std::string>();
    c.leanDeclaration = check.at("lean_declaration").get<std::string>();
    c.samples = check.at("samples").get<std::size_t>();
    c.maxAbsError = check.at("max_abs_error").get<double>();
    c.passed = check.at("passed").get<bool>();
    c.detail = check.at("detail").get<std::string>();
    if (check.at("lean_status") != "not_checked_by_this_check" || check.at("role") != "validation") {
      std::fprintf(stderr, "JS law record overclaims its Lean status or role\n");
      ++failures;
    }
    expect(c, c.law != "js:negative_control");
  }
  std::vector<double> cppRatios, cppEdges, jsRatios = out.at("ratios"), jsEdges = out.at("edges");
  for (double e : kEps) {
    cppEdges.push_back(kn::comptonEdgeFraction(e));
    for (double c : cosGrid()) cppRatios.push_back(kn::scatteredEnergyRatio(e, c));
  }
  expect(formal::checkAgreement("compton.cpp_js_ratio", "Trech.Laws.Compton.scatteredEnergyRatio", cppRatios,
                                jsRatios, 0.0, 0.0));
  expect(formal::checkAgreement("compton.cpp_js_edge", "Trech.Laws.Compton.edgeFraction", cppEdges, jsEdges,
                                0.0, 0.0));
}

void runRecordContract() {
  // The run record behind `law_checks` and the provenance `formal` object.
  (void)formal::takeRunChecks();  // drop what the earlier sections recorded
  if (!formal::takeRunChecks().empty()) {
    std::fprintf(stderr, "takeRunChecks did not clear the run record\n");
    ++failures;
  }
  // No checks: the provenance record keeps its shape (no "formal" key).
  const trech::test::TemporaryDirectory dir;
  {
    trech::ProvenanceWriter writer((dir.path() / "plain.jsonl").string());
    trech::ProvenanceRecord record;
    record.phase = "run_end";
    writer.write(record);
    std::ifstream in(dir.path() / "plain.jsonl");
    if (nlohmann::json::parse(in).contains("formal")) {
      std::fprintf(stderr, "a run without law checks wrote a formal block\n");
      ++failures;
    }
  }
  // Two identical engine lattices merge into one record per check with count 2; a failing
  // validation record keeps its first detail whatever the arrival order.
  trech::lattice::LatticeSpec spec;
  spec.shape = {5, 4, 1};
  spec.flow = false;
  spec.scalarLattice = "D2Q5";
  trech::lattice::Lattice a(spec), b(spec);
  formal::LawCheck bad = formal::checkProbabilityVector("probability.run_record", "Trech.Methods.Transition.noEvent_nonneg",
                                                        {0.7, 0.7}, 1e-15);
  formal::LawCheck worse = bad;
  worse.detail = "a first detail";
  formal::recordRunCheck(bad, "validation");
  formal::recordRunCheck(worse, "validation");
  const auto checks = formal::takeRunChecks();
  bool merged = checks.size() == 4;
  for (const auto& c : checks) {
    if (c.at("origin") == "engine") merged = merged && c.at("count") == 2 && c.at("passed") == true;
    if (c.at("origin") == "validation")
      merged = merged && c.at("count") == 2 && c.at("passed") == false && c.at("detail") == "a first detail";
  }
  if (!merged || checks.front().at("origin") != "engine") {
    std::fprintf(stderr, "run record did not merge as specified: %s\n", checks.dump().c_str());
    ++failures;
  }
  // The embedded law-source hash equals the one recomputed from the files (the same algorithm as
  // scripts/check_lean_laws.py sources_sha256), so the build is not stale.
  {
    const auto root = std::filesystem::path(TRECH_SOURCE_DIR);
    std::vector<std::string> files = {"formal/laws.json", "formal/Trech.lean"};
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root / "formal/Trech"))
      if (entry.path().extension() == ".lean")
        files.push_back(std::filesystem::relative(entry.path(), root).generic_string());
    std::sort(files.begin(), files.end());
    std::string digest;
    for (const auto& file : files) {
      std::ifstream in(root / file, std::ios::binary);
      const std::string bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
      digest += file + "\n" + trech::sha256Hex(bytes) + "\n";
    }
    if (trech::sha256Hex(digest) != formal::sourcesSha256()) {
      std::fprintf(stderr, "embedded formal sources hash is stale; reconfigure the build\n");
      ++failures;
    }
  }
  // Provenance: no audit, an unreadable one, a mismatched one, a matching one.
  auto status = [&](const std::string& audit) { return formal::provenanceBlock(checks, audit).at("lean_status").get<std::string>(); };
  const auto block = formal::provenanceBlock(checks, "");
  if (formal::manifestSha256().size() != 64 || formal::sourcesSha256().size() != 64 ||
      block.at("failed_checks") != 1 || block.at("declarations").size() != 3 || status("") != "not_checked_by_this_run" ||
      status((dir.path() / "missing.json").string()) != "audit_unreadable") {
    std::fprintf(stderr, "provenance block without a valid audit is wrong: %s\n", block.dump().c_str());
    ++failures;
  }
  auto writeAudit = [&](const std::string& name, const std::string& sources, bool withAll) {
    nlohmann::json declarations = nlohmann::json::array();
    for (const auto& d : block.at("declarations"))
      if (withAll || d != "Trech.Methods.Transition.noEvent_nonneg")
        declarations.push_back({{"name", d}, {"standard_only", true}});
    const nlohmann::json audit = {{"schema", "trech_lean_audit_v1"}, {"passed", true},
                                  {"manifest", {{"sha256", formal::manifestSha256()}}},
                                  {"sources_sha256", sources}, {"declarations", declarations}};
    std::ofstream(dir.path() / name) << audit.dump();
    return (dir.path() / name).string();
  };
  const std::string matching = writeAudit("audit.json", formal::sourcesSha256(), true);
  if (status(writeAudit("stale.json", std::string(64, '0'), true)) != "audit_mismatch" ||
      status(writeAudit("partial.json", formal::sourcesSha256(), false)) != "audit_incomplete" ||
      status(matching) != "audited") {
    std::fprintf(stderr, "provenance block does not grade the audit as specified\n");
    ++failures;
  }
  // The JS side: TRECH_FORMAL_LAWS.record reaches the same record, and rejects foreign records.
  const auto root = std::filesystem::path(TRECH_SOURCE_DIR);
  const auto path = dir.path() / "record.js";
  std::ofstream(path) << "TRECH_INCLUDE(" << nlohmann::json((root / "js/trech_formal_laws.js").string()).dump() << ");\n"
                      << R"JS(
const L = TRECH_FORMAL_LAWS;
let rejected = false;
try { L.record({law: "forged", role: "scenario"}); } catch (e) { rejected = true; }
globalThis.TRECH_CONFIG = {formal: {
  recorded: L.record(L.checkComptonBounds([0.5, 1.3], [-1, 0, 1], 1e-15)),
  probability: L.record(L.checkProbabilityVector("transition.js_probability", "Trech.Methods.Transition.noEvent_nonneg", [0.25, 0.75], 1e-15)),
  rejected}};
)JS";
  trech::JsRuntime runtime;
  const auto out = nlohmann::json::parse(runtime.evalExperimentAndGetConfigJson(path.string())).at("formal");
  const auto jsChecks = formal::takeRunChecks();
  bool js = out.at("recorded") == 2 && out.at("probability") == 1 && out.at("rejected") == true && jsChecks.size() == 3;
  for (const auto& c : jsChecks) js = js && c.at("origin") == "validation" && c.at("passed") == true;
  if (!js) {
    std::fprintf(stderr, "JS law-check recording failed: %s %s\n", out.dump().c_str(), jsChecks.dump().c_str());
    ++failures;
  }
  std::printf("%-40s run record, provenance block and JS recording %s\n", "formal.run_record",
              merged && js ? "pass" : "FAIL");
}

}  // namespace

int main() {
  try {
    comptonPairs();
    energyBalancePairs();
    twoBodyPairs();
    attenuationPairs();
    latticePairs();
    scalarLatticePairs();
    transitionPairs();
    transitionConservation();
    pairConservation();
    evolvePairs();
    setPoolPairs();
    groupPairs();
    leastSquaresPairs();
    arbiterPairs();
    javascriptPairs();
    runRecordContract();
    const auto sample = formal::checkProbabilityVector("probability.example", "", {0.25, 0.25, 0.5}, 1e-15);
    expect(sample);
    if (sample.toJson().at("lean_status") != "not_checked_by_this_check") ++failures;
    expect(formal::checkProbabilityVector("probability.negative_control", "", {0.6, 0.6, -0.2}, 1e-15), false);
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
  return failures ? 1 : 0;
}
