#include "trech/core/LatticeKinetic.hpp"

#include <cmath>
#include <vector>

namespace trech {
namespace {

// One TRT collide-and-stream step with Guo forcing. Returns false on a nonphysical cell.
// Lean pair (optional, for validation): Trech.Methods.Lattice (formal/Trech/Methods/Lattice.lean)
// proves the collision and streaming below conserve mass under the hypotheses that
// tests/test_formal_laws.cpp checks (velocity moments, opp involution, src bijection).
bool flowStep(LatticeFlowView& v, const double* gxField, const double* gyField,
              const double* gzField, const LatticeCoupling& c, double& peak) {
  const std::size_t F = v.cells, Q = v.set.q;
  const double* cx = v.set.cx; const double* cy = v.set.cy; const double* cz = v.set.cz;
  const double* w = v.set.w; const int32_t* opp = v.set.opp;
  const double cs2 = v.set.cs2, wp = v.omegaPlus, wm = v.omegaMinus;
  std::vector<double> eq(Q), fs(Q);
  for (std::size_t i = 0; i < F; ++i) {
    double r = 0, mx = 0, my = 0, mz = 0;
    for (std::size_t q = 0; q < Q; ++q) {
      const double value = v.f[q * F + i];
      r += value; mx += cx[q] * value; my += cy[q] * value; mz += cz[q] * value;
    }
    const double gx = gxField ? gxField[i] : c.base[0];
    const double gy = gyField ? gyField[i] : c.base[1];
    const double gz = gzField ? gzField[i] : c.base[2];
    if (!(r > 0) || !std::isfinite(mx + my + mz)) return false;
    const double vx = (mx + 0.5 * gx) / r, vy = (my + 0.5 * gy) / r, vz = (mz + 0.5 * gz) / r;
    v.rho[i] = r; v.ux[i] = vx; v.uy[i] = vy; v.uz[i] = vz;
    const double speed2 = vx * vx + vy * vy + vz * vz;
    if (speed2 > peak) peak = speed2;
    for (std::size_t q = 0; q < Q; ++q) {
      const double cuEq = (cx[q] * vx + cy[q] * vy + cz[q] * vz) / cs2;
      eq[q] = w[q] * r * (1 + cuEq + 0.5 * cuEq * cuEq - 0.5 * (vx * vx + vy * vy + vz * vz) / cs2);
      const double cu = cx[q] * vx + cy[q] * vy + cz[q] * vz;
      fs[q] = w[q] * (((cx[q] - vx) * gx + (cy[q] - vy) * gy + (cz[q] - vz) * gz) / cs2 +
                      cu * (cx[q] * gx + cy[q] * gy + cz[q] * gz) / (cs2 * cs2));
    }
    for (std::size_t q = 0; q < Q; ++q) {
      const std::size_t p = static_cast<std::size_t>(opp[q]), a = q * F + i, b = p * F + i;
      const double fp = 0.5 * (v.f[a] + v.f[b]), fm = 0.5 * (v.f[a] - v.f[b]);
      const double ep = 0.5 * (eq[q] + eq[p]), em = 0.5 * (eq[q] - eq[p]);
      const double sp = 0.5 * (fs[q] + fs[p]), sm = 0.5 * (fs[q] - fs[p]);
      v.post[a] = v.f[a] - wp * (fp - ep) - wm * (fm - em) + (1 - 0.5 * wp) * sp + (1 - 0.5 * wm) * sm;
    }
  }
  const std::size_t total = Q * F;
  for (std::size_t k = 0; k < total; ++k) {
    v.f[k] = v.post[v.src[k]];
    if (v.wallTerm && v.wall && v.wall[k]) v.f[k] += v.wallTerm[k] * v.rho[k % F];
  }
  return true;
}

void scalarValues(LatticeScalarView& s) {
  const std::size_t F = s.cells, Q = s.set.q;
  for (std::size_t i = 0; i < F; ++i) {
    double sum = 0;
    for (std::size_t q = 0; q < Q; ++q) sum += s.g[q * F + i];
    s.value[i] = sum;
  }
}

// One TRT advection-diffusion step with a per-cell source; velocity arrays may be null (rest).
void scalarStep(LatticeScalarView& s, const double* ux, const double* uy, const double* uz,
                const double* source) {
  const std::size_t F = s.cells, Q = s.set.q;
  const double* cx = s.set.cx; const double* cy = s.set.cy; const double* cz = s.set.cz;
  const double* w = s.set.w; const int32_t* opp = s.set.opp;
  const double cs2 = s.set.cs2, wp = s.omegaPlus, wm = s.omegaMinus;
  std::vector<double> eq(Q);
  for (std::size_t i = 0; i < F; ++i) {
    double sum = 0;
    for (std::size_t q = 0; q < Q; ++q) sum += s.g[q * F + i];
    s.value[i] = sum;
    const double vx = ux ? ux[i] : 0, vy = uy ? uy[i] : 0, vz = uz ? uz[i] : 0;
    const double add = source ? source[i] : 0;
    for (std::size_t q = 0; q < Q; ++q)
      eq[q] = w[q] * sum * (1 + (cx[q] * vx + cy[q] * vy + cz[q] * vz) / cs2);
    for (std::size_t q = 0; q < Q; ++q) {
      const std::size_t p = static_cast<std::size_t>(opp[q]), a = q * F + i, b = p * F + i;
      const double gp = 0.5 * (s.g[a] + s.g[b]), gm = 0.5 * (s.g[a] - s.g[b]);
      const double ep = 0.5 * (eq[q] + eq[p]), em = 0.5 * (eq[q] - eq[p]);
      s.post[a] = s.g[a] - wp * (gp - ep) - wm * (gm - em) + w[q] * add;
    }
  }
  const std::size_t total = Q * F;
  for (std::size_t k = 0; k < total; ++k)
    s.g[k] = (s.anti && s.anti[k]) ? -s.post[s.src[k]] + s.dirichlet[k] : s.post[s.src[k]];
}

}  // namespace

LatticeAdvanceResult advanceLattice(LatticeFlowView& flow, LatticeScalarView* scalar,
                                    const LatticeCoupling& coupling, std::uint64_t steps) {
  LatticeAdvanceResult result;
  const std::size_t F = flow.cells;
  std::vector<double> forceX, forceY, forceZ, source;
  if (scalar) {
    forceX.resize(F); forceY.resize(F); forceZ.resize(F);
    if (scalar->rate || scalar->constant) source.resize(F);
  }
  for (std::uint64_t n = 0; n < steps; ++n) {
    double peak = 0;
    bool ok = true;
    if (scalar) {
      scalarValues(*scalar);
      double reference = coupling.reference;
      if (coupling.meanReference) {
        double sum = 0;
        for (std::size_t i = 0; i < F; ++i) sum += scalar->value[i];
        reference = sum / static_cast<double>(F);
      }
      double* axisField = coupling.axis == 0 ? forceX.data() : coupling.axis == 1 ? forceY.data() : forceZ.data();
      for (std::size_t i = 0; i < F; ++i) { forceX[i] = coupling.base[0]; forceY[i] = coupling.base[1]; forceZ[i] = coupling.base[2]; }
      for (std::size_t i = 0; i < F; ++i) axisField[i] += coupling.coefficient * (scalar->value[i] - reference);
      ok = flowStep(flow, forceX.data(), forceY.data(), forceZ.data(), coupling, peak);
      if (ok && !source.empty()) {
        for (std::size_t i = 0; i < F; ++i) {
          double add = 0;
          if (scalar->rate) add = scalar->rate[i] * (scalar->target[i] - scalar->value[i]);
          if (scalar->constant) add += scalar->constant[i];
          source[i] = add;
        }
      }
      if (ok) scalarStep(*scalar, flow.ux, flow.uy, flow.uz, source.empty() ? nullptr : source.data());
    } else {
      ok = flowStep(flow, coupling.forceX, coupling.forceY, coupling.forceZ, coupling, peak);
    }
    if (!ok) { result.nonphysical = true; break; }
    result.steps += 1;
    const double mach = std::sqrt(peak / flow.set.cs2);
    if (mach > result.maxMach) result.maxMach = mach;
  }
  return result;
}

LatticeAdvanceResult advanceScalarLattice(LatticeScalarView& scalar, const double* ux, const double* uy,
                                          const double* uz, std::uint64_t steps) {
  LatticeAdvanceResult result;
  const std::size_t F = scalar.cells;
  std::vector<double> source;
  if (scalar.rate || scalar.constant) source.resize(F);
  for (std::uint64_t n = 0; n < steps; ++n) {
    if (!source.empty()) {
      scalarValues(scalar);
      for (std::size_t i = 0; i < F; ++i) {
        double add = 0;
        if (scalar.rate) add = scalar.rate[i] * (scalar.target[i] - scalar.value[i]);
        if (scalar.constant) add += scalar.constant[i];
        source[i] = add;
      }
    }
    scalarStep(scalar, ux, uy, uz, source.empty() ? nullptr : source.data());
    result.steps += 1;
  }
  return result;
}

}  // namespace trech
