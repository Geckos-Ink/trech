#pragma once
#include "trech/core/FormalLaws.hpp"
#include "trech/core/LatticeKinetic.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace trech::lattice {

// Engine-owned lattice Boltzmann method for continuum transport: a flow lattice (D2Q9/D3Q19,
// two-relaxation-time, Guo forcing, half-way bounce-back walls, optional moving walls) and a
// scalar lattice (D2Q5/D3Q7 advection-diffusion, zero-flux or anti-bounce-back Dirichlet
// walls, linear relaxation source), coupled by a linear scalar->body-force law (Boussinesq).
// Everything is in lattice units (dx = dt = 1). It is a general continuum method like Geant4
// transport is a general particle method: it names no material, scenario or domain. Scenarios
// never construct it; the engine's field-evolution arbitration (trech/ml/FieldEvolution.hpp)
// decides where it is used. Verified by tests/test_lattice_continuum.cpp.

struct VelocitySet {
  std::string name;
  int dimensions = 3;
  std::vector<double> cx, cy, cz, w;
  std::vector<int32_t> opp;
  double cs2 = 1.0 / 3.0;
  std::size_t q() const { return w.size(); }
};
// D2Q9, D3Q19 (flow); D2Q5, D3Q7 (scalar). Throws for any other name.
const VelocitySet& velocitySet(const std::string& name);

// Fluid cells of a box lattice, compacted; out-of-range coordinates are walls unless periodic.
class Domain {
 public:
  Domain(std::array<int, 3> shape, const std::function<bool(int, int, int)>& solid,
         std::array<bool, 3> periodic = {false, false, false});
  int at(int x, int y, int z) const;  // fluid index or -1
  std::size_t count() const { return x.size(); }
  std::array<int, 3> shape;
  std::array<bool, 3> periodic;
  std::vector<int> x, y, z;
  // Axis neighbours (6 per cell, -1 = wall) and breadth-first wall distance in cells.
  const std::vector<int>& neighbours() const;
  const std::vector<double>& wallDistance() const;

 private:
  std::vector<int> index_;
  mutable std::vector<int> neighbours_;
  mutable std::vector<double> wallDistance_;
};

struct LatticeSpec {
  std::array<int, 3> shape{1, 1, 1};
  std::array<bool, 3> periodic{false, false, false};
  std::function<bool(int, int, int)> solid;  // empty: no interior solids
  bool flow = true;
  std::string flowLattice = "D3Q19";
  double tau = 1.0;
  double flowMagic = 3.0 / 16.0;  // TRT Lambda; 3/16 places half-way walls exactly
  bool scalar = true;
  std::string scalarLattice = "D3Q7";
  double diffusivity = 0.1;       // lattice units
  // Scalar TRT magic; negative = default (even modes relax at tau+ = 1). The tempting
  // Lambda = 1/4 leaves period-2 scalar modes undamped at small diffusivity and, through
  // buoyancy, pumps the flow's staggered momentum invariant (tests/test_lattice_continuum.cpp).
  double scalarMagic = -1.0;
  std::function<std::array<double, 4>(int, int, int)> initialFlow;  // rho, ux, uy, uz
  std::function<double(int, int, int)> initialScalar;
  // Wall velocity of the wall cell at (x,y,z); return false for a resting wall.
  std::function<bool(int, int, int, std::array<double, 3>&)> wallVelocity;
  // Dirichlet value for a scalar link from wall cell (wx,wy,wz) into fluid cell (fx,fy,fz).
  std::function<bool(int, int, int, int, int, int, double&)> dirichlet;
  // Body force = uniformForce + buoyancyCoefficient * (scalar - reference) along buoyancyAxis.
  std::array<double, 3> uniformForce{0.0, 0.0, 0.0};
  int buoyancyAxis = 2;
  double buoyancyCoefficient = 0.0;
  double buoyancyReference = 0.0;
  bool meanReference = false;  // reference = instantaneous fluid-mean scalar
};

class Lattice {
 public:
  explicit Lattice(const LatticeSpec& spec);
  Lattice(Lattice&&) noexcept = default;
  Lattice& operator=(Lattice&&) noexcept = default;

  const Domain& domain() const { return domain_; }
  bool hasFlow() const { return spec_.flow; }
  bool hasScalar() const { return spec_.scalar; }
  double viscosity() const;     // cs2 (tau - 1/2)
  double diffusivity() const { return spec_.diffusivity; }
  double soundSpeed() const;

  // Per-cell scalar source of each step: rate * (target - value) + constant. Mutable between
  // advances (all zero by default).
  std::vector<double>& rate() { return rate_; }
  std::vector<double>& target() { return target_; }
  std::vector<double>& constant() { return constant_; }
  // Flow-only per-cell body force; used when set (non-empty) and no scalar is coupled.
  std::vector<double>& forceX() { return forceX_; }
  std::vector<double>& forceY() { return forceY_; }
  std::vector<double>& forceZ() { return forceZ_; }
  // Scalar-only lattices: optional prescribed advection velocity (lattice units, cells each).
  std::vector<double>& advectionX() { return advectX_; }
  std::vector<double>& advectionY() { return advectY_; }
  std::vector<double>& advectionZ() { return advectZ_; }

  // Advance; returns false (and stops) on a nonphysical state, which callers must treat as
  // evidence that the method failed here, never clip.
  bool advance(std::uint64_t steps);
  std::uint64_t steps() const { return steps_; }
  double maxMach() const { return maxMach_; }

  // Velocity of the last collision (includes the half-force correction); zero without flow.
  const std::vector<double>& ux() const { return ux_; }
  const std::vector<double>& uy() const { return uy_; }
  const std::vector<double>& uz() const { return uz_; }
  // Scalar of the current populations.
  const std::vector<double>& scalarValues();
  // Moments of the current (post-streaming) flow populations, without the force half-step.
  void flowMoments(std::vector<double>& rho, std::vector<double>& ux, std::vector<double>& uy,
                   std::vector<double>& uz) const;
  // Add a per-cell scalar increment (shifts each cell's zeroth moment, keeps its fluxes): used
  // to re-synchronise a lattice to an observed field without discarding its own structure.
  void addScalar(const std::vector<double>& delta);
  double mass() const;
  double scalarTotal() const;

  // Hypotheses of the lattice's Lean law pair (Trech.Methods.Lattice), checked once when the
  // lattice is built: velocity-set moments, opposite-direction involution and the streaming
  // table's bijection, for the flow and the scalar lattice. Observation only: they never change
  // a population, RNG stream, emit or output, and are reported through the engine trace
  // (category "formal"; a failed check is a warning). Moving walls and Dirichlet links add
  // mass by design, so a lattice that has them records conservation as not applicable.
  const std::vector<formal::LawCheck>& lawChecks() const { return lawChecks_; }

 private:
  void checkLaws();
  void build();
  LatticeSpec spec_;
  Domain domain_;
  const VelocitySet* flowSet_ = nullptr;
  const VelocitySet* scalarSet_ = nullptr;
  std::vector<double> f_, fPost_, wallTerm_, rho_, ux_, uy_, uz_;
  std::vector<int32_t> fSrc_;
  std::vector<uint8_t> fWall_;
  std::vector<double> g_, gPost_, dirichlet_, value_;
  std::vector<int32_t> gSrc_;
  std::vector<uint8_t> anti_;
  std::vector<double> rate_, target_, constant_, forceX_, forceY_, forceZ_, advectX_, advectY_, advectZ_;
  double flowOmegaPlus_ = 1.0, flowOmegaMinus_ = 1.0, scalarOmegaPlus_ = 1.0, scalarOmegaMinus_ = 1.0;
  std::uint64_t steps_ = 0;
  double maxMach_ = 0.0;
  std::vector<formal::LawCheck> lawChecks_;
};

// Trilinear sample of a fluid-cell field at lattice coordinates (cell centres at integers).
// Wall corners are dropped and the weights renormalised; false when none remain.
bool sample(const Domain& domain, const std::vector<double>& field, double x, double y, double z,
            double& out);

// Lattice-intrinsic local descriptors of each fluid cell (dimensionless, name no material).
struct LocalDescriptors {
  std::vector<double> mach, cellReynolds, cellPeclet, scalarStep, velocityCurvature, wallDistance;
};
LocalDescriptors localDescriptors(Lattice& lattice, double scalarScale);

// Share of kinetic energy in the period-2 (Nyquist) mode along any lattice axis.
double staggeredFraction(const Domain& domain, const std::vector<double>& ux,
                         const std::vector<double>& uy, const std::vector<double>& uz);

}  // namespace trech::lattice
