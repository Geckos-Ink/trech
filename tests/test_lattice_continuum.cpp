// Verification of the engine's lattice Boltzmann method (trech/core/LatticeContinuum.hpp).
// Exact and closed-form anchors are independent of the solver; the heated cavity is a published
// numerical benchmark (de Vahl Davis 1983). Numerical verification only: never a physical
// validation or particle-training data.
#include "trech/core/LatticeContinuum.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

using namespace trech::lattice;

namespace {
int failures = 0;
void check(bool ok, const std::string& message) {
  if (!ok) { std::fprintf(stderr, "FAIL: %s\n", message.c_str()); ++failures; }
}
double order(double coarse, double fine) { return std::log(coarse / fine) / std::log(2.0); }
const double kPi = 3.14159265358979323846;

double rms(const std::vector<double>& a, const std::vector<double>& b) {
  double s = 0;
  for (std::size_t i = 0; i < a.size(); ++i) s += (a[i] - b[i]) * (a[i] - b[i]);
  return std::sqrt(s / static_cast<double>(a.size()));
}

// 1. Taylor-Green vortex (D2Q9, periodic), diffusive scaling.
double taylorGreen(int N) {
  const double tau = 0.8, u0 = 0.04 * 16 / N, k = 2 * kPi / N;
  const int steps = static_cast<int>(std::lround(100.0 * (N / 16.0) * (N / 16.0)));
  LatticeSpec s;
  s.shape = {N, N, 1}; s.periodic = {true, true, true}; s.flowLattice = "D2Q9"; s.tau = tau; s.scalar = false;
  s.initialFlow = [&](int x, int y, int) {
    return std::array<double, 4>{1 - 0.75 * u0 * u0 * (std::cos(2 * k * x) + std::cos(2 * k * y)),
                                 -u0 * std::cos(k * x) * std::sin(k * y), u0 * std::sin(k * x) * std::cos(k * y), 0.0};
  };
  Lattice l(s);
  l.advance(static_cast<std::uint64_t>(steps));
  std::vector<double> rho, ux, uy, uz;
  l.flowMoments(rho, ux, uy, uz);
  const double decay = std::exp(-2 * l.viscosity() * k * k * steps);
  std::vector<double> a, e;
  for (std::size_t i = 0; i < l.domain().count(); ++i) {
    a.push_back(ux[i] / u0);
    e.push_back(-std::cos(k * l.domain().x[i]) * std::sin(k * l.domain().y[i]) * decay);
  }
  return rms(a, e);
}

// 2. Kolmogorov flow (D3Q19, per-cell Guo force): steady u = F/(nu k^2) sin(k y).
double kolmogorov(int N) {
  const double k = 2 * kPi / N, F0 = 1e-6;
  LatticeSpec s;
  s.shape = {1, N, 1}; s.periodic = {true, true, true}; s.tau = 0.8; s.scalar = false;
  Lattice l(s);
  const std::size_t F = l.domain().count();
  l.forceX().assign(F, 0.0); l.forceY().assign(F, 0.0); l.forceZ().assign(F, 0.0);
  for (std::size_t i = 0; i < F; ++i) l.forceX()[i] = F0 * std::sin(k * l.domain().y[i]);
  l.advance(static_cast<std::uint64_t>(std::lround(14 / (l.viscosity() * k * k))));
  const double amp = F0 / (l.viscosity() * k * k);
  double err = 0;
  for (std::size_t i = 0; i < F; ++i) err = std::max(err, std::abs(l.ux()[i] - amp * std::sin(k * l.domain().y[i])));
  return err / amp;
}

// 3. Body-force Poiseuille: TRT Lambda = 3/16 is exact for every tau.
double poiseuille(double tau) {
  const int H = 10;
  const double Fx = 1e-6;
  LatticeSpec s;
  s.shape = {1, 1, H + 2}; s.periodic = {true, true, false}; s.tau = tau; s.scalar = false;
  s.solid = [&](int, int, int z) { return z == 0 || z == H + 1; };
  s.uniformForce = {Fx, 0, 0};
  Lattice l(s);
  const double nu = l.viscosity();
  l.advance(static_cast<std::uint64_t>(std::lround(4.0 * H * H / nu)));
  double err = 0, peak = 0;
  for (std::size_t i = 0; i < l.domain().count(); ++i) {
    const double z = l.domain().z[i], exact = Fx / (2 * nu) * (z - 0.5) * (H + 0.5 - z);
    err = std::max(err, std::abs(l.ux()[i] - exact)); peak = std::max(peak, exact);
  }
  return err / peak;
}

// 4. Moving-wall Couette: exact linear profile.
double couette(double tau) {
  const int H = 8;
  const double U = 0.01;
  LatticeSpec s;
  s.shape = {1, 1, H + 2}; s.periodic = {true, true, false}; s.tau = tau; s.scalar = false;
  s.solid = [&](int, int, int z) { return z == 0 || z == H + 1; };
  s.wallVelocity = [&](int, int, int z, std::array<double, 3>& u) {
    if (z != H + 1) return false;
    u = {U, 0, 0};
    return true;
  };
  Lattice l(s);
  l.advance(static_cast<std::uint64_t>(std::lround(4.0 * H * H / l.viscosity())));
  std::vector<double> rho, ux, uy, uz;
  l.flowMoments(rho, ux, uy, uz);
  double err = 0;
  for (std::size_t i = 0; i < l.domain().count(); ++i) err = std::max(err, std::abs(ux[i] - U * (l.domain().z[i] - 0.5) / H));
  return err / U;
}

// 5. Advected, diffusing sine (scalar-only D3Q7 with a prescribed velocity): second order.
double advectionDiffusion(int N) {
  const double D = 0.025, k = 2 * kPi / N, U = 0.05 * 16 / N;
  const int steps = static_cast<int>(std::lround(60.0 * (N / 16.0) * (N / 16.0)));
  LatticeSpec s;
  s.shape = {N, 1, 1}; s.periodic = {true, true, true}; s.flow = false; s.diffusivity = D;
  s.initialScalar = [&](int x, int, int) { return 1 + 0.5 * std::sin(k * x); };
  Lattice l(s);
  const std::size_t F = l.domain().count();
  l.advectionX().assign(F, U); l.advectionY().assign(F, 0.0); l.advectionZ().assign(F, 0.0);
  l.advance(static_cast<std::uint64_t>(steps));
  const auto& v = l.scalarValues();
  std::vector<double> e;
  for (std::size_t i = 0; i < F; ++i)
    e.push_back(1 + 0.5 * std::sin(k * (l.domain().x[i] - U * steps)) * std::exp(-D * k * k * steps));
  return rms(v, e);
}

// 6. Steady conduction between anti-bounce-back Dirichlet walls: exact linear profile.
double conduction() {
  const int H = 8;
  LatticeSpec s;
  s.shape = {1, 1, H}; s.periodic = {true, true, false}; s.flow = false; s.diffusivity = 0.1;
  s.dirichlet = [](int, int, int wz, int, int, int, double& value) { value = wz < 0 ? 1.0 : 0.0; return true; };
  Lattice l(s);
  l.advance(static_cast<std::uint64_t>(std::lround(4.0 * H * H / 0.1)));
  const auto& v = l.scalarValues();
  double err = 0;
  for (std::size_t i = 0; i < l.domain().count(); ++i) err = std::max(err, std::abs(v[i] - (1 - (l.domain().z[i] + 0.5) / H)));
  return err;
}

// 8. Differentially heated cavity Ra = 1e3, Pr = 0.71 (de Vahl Davis 1983: Nu = 1.118).
double cavityNusselt(int N) {
  const double Ra = 1e3, Pr = 0.71, U = 0.05, gb = U * U / N;
  const double nu = std::sqrt(Pr / Ra) * U * N, kappa = nu / Pr;
  LatticeSpec s;
  s.shape = {N, N, 1}; s.flowLattice = "D2Q9"; s.scalarLattice = "D2Q5";
  s.tau = 0.5 + 3 * nu; s.diffusivity = kappa;
  s.dirichlet = [&](int wx, int, int, int, int, int, double& value) {
    if (wx < 0) { value = 0.5; return true; }
    if (wx >= N) { value = -0.5; return true; }
    return false;
  };
  s.buoyancyAxis = 1; s.buoyancyCoefficient = gb;
  Lattice l(s);
  double nusselt = 0, previous = 0;
  for (int block = 0; block < 40; ++block) {
    l.advance(500);
    const auto& T = l.scalarValues();
    double flux = 0;
    for (std::size_t i = 0; i < l.domain().count(); ++i) flux += l.ux()[i] * T[i];
    nusselt = 1 + flux / static_cast<double>(l.domain().count()) * N / kappa;
    if (std::abs(nusselt - previous) < 1e-5 * nusselt) break;
    previous = nusselt;
  }
  return nusselt;
}

// 9. Staggered-mode guard: weakly diffusive scalar heated from below in a closed box.
double staggeredBox(double scalarMagic, double& rmsFirst, double& rmsLast) {
  LatticeSpec s;
  s.shape = {6, 6, 16}; s.tau = 0.58; s.diffusivity = 0.0018; s.scalarMagic = scalarMagic;
  s.initialScalar = [](int x, int, int) { return 1e-4 * (x - 2.5); };
  s.buoyancyAxis = 2; s.buoyancyCoefficient = 2e-4; s.meanReference = true;
  Lattice l(s);
  const std::size_t F = l.domain().count();
  for (std::size_t i = 0; i < F; ++i) {
    if (l.domain().z[i] == 0) { l.rate()[i] = 4e-4; l.target()[i] = 1; }
    if (l.domain().z[i] == 15) l.rate()[i] = 4e-4;
  }
  auto speed = [&] {
    double e = 0;
    for (std::size_t i = 0; i < F; ++i) e += l.ux()[i] * l.ux()[i] + l.uy()[i] * l.uy()[i] + l.uz()[i] * l.uz()[i];
    return std::sqrt(e / static_cast<double>(F));
  };
  for (int k = 0; k < 5; ++k) {
    l.advance(3000);
    if (k == 0) rmsFirst = speed();
  }
  rmsLast = speed();
  return staggeredFraction(l.domain(), l.ux(), l.uy(), l.uz());
}

}  // namespace

int main() {
  try {
    const double tg8 = taylorGreen(8), tg16 = taylorGreen(16), tg32 = taylorGreen(32);
    const double o1 = order(tg8, tg16), o2 = order(tg16, tg32);
    check(o1 > 1.8 && o1 < 2.3 && o2 > 1.8 && o2 < 2.3, "Taylor-Green order " + std::to_string(o1) + " " + std::to_string(o2));
    std::printf("taylor_green_d2q9 orders %.4f %.4f\n", o1, o2);

    const double k16 = kolmogorov(16), k32 = kolmogorov(32), ko = order(k16, k32);
    check(ko > 1.8 && ko < 2.3, "Kolmogorov order " + std::to_string(ko));
    std::printf("kolmogorov_d3q19 order %.4f\n", ko);

    for (double tau : {0.6, 0.9, 1.7}) {
      const double e = poiseuille(tau);
      check(e < 1e-9, "Poiseuille not exact at tau " + std::to_string(tau) + ": " + std::to_string(e));
      std::printf("poiseuille_d3q19 tau %.2f linf %.3e\n", tau, e);
    }
    for (double tau : {0.8, 1.4}) {
      const double e = couette(tau);
      check(e < 1e-9, "Couette not exact: " + std::to_string(e));
      std::printf("couette_d3q19 tau %.2f linf %.3e\n", tau, e);
    }
    const double a16 = advectionDiffusion(16), a32 = advectionDiffusion(32), a64 = advectionDiffusion(64);
    const double ao1 = order(a16, a32), ao2 = order(a32, a64);
    check(ao1 > 1.8 && ao1 < 2.3 && ao2 > 1.8 && ao2 < 2.3, "Advection-diffusion order");
    std::printf("advection_diffusion_d3q7 orders %.4f %.4f\n", ao1, ao2);

    const double ce = conduction();
    check(ce < 1e-9, "Dirichlet conduction not exact: " + std::to_string(ce));
    std::printf("conduction_d3q7 linf %.3e\n", ce);

    {  // 7. Closed box: bounce-back conserves mass, zero-flux walls conserve the scalar.
      LatticeSpec s;
      s.shape = {6, 6, 6}; s.tau = 0.9; s.diffusivity = 0.05;
      s.initialScalar = [](int x, int y, int z) { return std::sin(1 + x) * std::cos(0.5 * y + z); };
      s.buoyancyAxis = 2; s.buoyancyCoefficient = 1e-4;
      Lattice l(s);
      const double m0 = l.mass(), h0 = l.scalarTotal();
      l.advance(200);
      const double md = std::abs(l.mass() - m0) / m0, hd = std::abs(l.scalarTotal() - h0) / std::max(1.0, std::abs(h0));
      check(md < 1e-12 && hd < 1e-12 && l.maxMach() > 0, "Closed-box conservation lost");
      std::printf("closed_box_conservation mass %.3e scalar %.3e\n", md, hd);
    }

    const double nu16 = cavityNusselt(16);
    check(std::abs(nu16 / 1.118 - 1) < 0.01, "Heated cavity Nusselt off benchmark: " + std::to_string(nu16));
    std::printf("heated_cavity_d2q9_d2q5 Nu %.4f (benchmark 1.118)\n", nu16);

    double r0 = 0, r1 = 0, q0 = 0, q1 = 0;
    const double guarded = staggeredBox(-1.0, r0, r1), unguarded = staggeredBox(0.25, q0, q1);
    check(guarded < 0.01 && r1 < r0, "Default scalar relaxation lets a staggered lattice mode grow");
    check(unguarded > 0.5, "Lambda=1/4 counterexample no longer shows the staggered mode");
    std::printf("staggered_mode_guard default %.4f lambda_quarter %.4f\n", guarded, unguarded);

    {  // 10. Descriptors: wall distances follow the lattice.
      LatticeSpec s;
      s.shape = {8, 8, 16}; s.tau = 0.8; s.diffusivity = 0.05;
      Lattice l(s);
      const auto d = localDescriptors(l, 1.0);
      const double lo = *std::min_element(d.wallDistance.begin(), d.wallDistance.end());
      const double hi = *std::max_element(d.wallDistance.begin(), d.wallDistance.end());
      check(lo == 1 && hi == 4, "Wall distances do not follow the lattice");
      std::printf("descriptors wall_distance %g..%g\n", lo, hi);
    }
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
  return failures ? 1 : 0;
}
