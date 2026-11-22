// Classic side of the optional Lean law pairs (formal/laws.json, docs/engine/formal_laws.md).
//
// Lean is not needed here: every check runs the classic C++/JS implementation against the
// statement of its Lean pair, checks the hypotheses the Lean theorem assumes, and checks that
// the C++ and JavaScript classic implementations agree.
#include "TemporaryDirectory.hpp"

#include "trech/core/FormalLaws.hpp"
#include "trech/core/LatticeKinetic.hpp"
#include "trech/js/JsRuntime.hpp"
#include "trech/sim/KleinNishina.hpp"

#include <nlohmann/json.hpp>

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
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

}  // namespace

int main() {
  try {
    comptonPairs();
    attenuationPairs();
    latticePairs();
    javascriptPairs();
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
