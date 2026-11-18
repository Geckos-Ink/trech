#pragma once
#include <cstddef>
#include <cstdint>

namespace trech {

// Lattice-kinetic advance (lattice Boltzmann hot loop) over caller-owned arrays. The velocity
// set, weights, relaxation rates, wall links, linear scalar->force coupling and linear relaxation
// source are supplied by the caller (trech/core/LatticeContinuum.hpp builds them); no fluid or
// material is named here. Compiled without FP contraction so results do not depend on an
// optimiser's fused multiply-add choice.
struct LatticeVelocitySet {
  std::size_t q = 0;
  const double* cx = nullptr;   // q entries each
  const double* cy = nullptr;
  const double* cz = nullptr;
  const double* w = nullptr;
  const int32_t* opp = nullptr;
  double cs2 = 0.0;
};

// Two-relaxation-time populations with Guo forcing. Arrays are q*cells (population-major)
// except rho/ux/uy/uz (cells). src[k] is the post-collision slot streamed into slot k;
// wall/wallTerm (optional) add a moving-wall momentum term rho * wallTerm[k] on wall links.
struct LatticeFlowView {
  LatticeVelocitySet set;
  std::size_t cells = 0;
  double omegaPlus = 0.0, omegaMinus = 0.0;
  double* f = nullptr;
  double* post = nullptr;
  const int32_t* src = nullptr;
  const uint8_t* wall = nullptr;
  const double* wallTerm = nullptr;
  double* rho = nullptr;
  double* ux = nullptr;
  double* uy = nullptr;
  double* uz = nullptr;
};

// Advection-diffusion populations. anti[k] marks an anti-bounce-back (Dirichlet) link whose
// streamed value is -post[src[k]] + dirichlet[k]. The per-step source added to cell i is
// rate[i] * (target[i] - value[i]) + constant[i] (each array optional; missing means zero).
struct LatticeScalarView {
  LatticeVelocitySet set;
  std::size_t cells = 0;
  double omegaPlus = 0.0, omegaMinus = 0.0;
  double* g = nullptr;
  double* post = nullptr;
  const int32_t* src = nullptr;
  const uint8_t* anti = nullptr;
  const double* dirichlet = nullptr;
  double* value = nullptr;
  const double* rate = nullptr;
  const double* target = nullptr;
  const double* constant = nullptr;
};

// Body force per cell: base[axis] everywhere, plus coefficient * (scalar - reference) along
// `axis` when a scalar lattice is present. meanReference replaces `reference` by the
// instantaneous cell-mean scalar of each step (summed in cell order).
struct LatticeCoupling {
  double base[3] = {0.0, 0.0, 0.0};
  int axis = 2;
  double coefficient = 0.0;
  double reference = 0.0;
  bool meanReference = false;
  // Flow-only advances: optional per-cell body force (cells each); replaces `base`.
  const double* forceX = nullptr;
  const double* forceY = nullptr;
  const double* forceZ = nullptr;
};

struct LatticeAdvanceResult {
  std::uint64_t steps = 0;
  double maxMach = 0.0;      // max |u| / c_s over the advanced steps
  bool nonphysical = false;  // a non-positive density or non-finite momentum stopped the advance
};

// Advance `steps` coupled steps (scalar may be null). Stops early, flagging `nonphysical`,
// rather than clipping a state.
LatticeAdvanceResult advanceLattice(LatticeFlowView& flow, LatticeScalarView* scalar,
                                    const LatticeCoupling& coupling, std::uint64_t steps);

// Scalar-only advance (no flow lattice): advection by the given fixed velocity arrays, or pure
// diffusion when they are null, with the view's relaxation source.
LatticeAdvanceResult advanceScalarLattice(LatticeScalarView& scalar, const double* ux, const double* uy,
                                          const double* uz, std::uint64_t steps);

}  // namespace trech
