#pragma once

#include "trech/core/LatticeContinuum.hpp"
#include "trech/ml/DomainLearner.hpp"

#include <array>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech::ml {

// Engine-owned evolution of a declared continuum field, with the prediction METHOD chosen
// statistically by the engine, never by the scenario.
//
// A scenario declares only its system: the region, its own field cells and current values,
// the transport properties it inferred (kinematic viscosity, scalar diffusivity, expansion per
// field unit, body acceleration) and the exchanges at its cells (relaxation rate/target, load).
// Optionally it passes a reference field (a validation teacher or a measurement) at each time.
//
// The engine advances every candidate method it owns on the same clock, each free-running from
// the declared initial state:
//   lattice_convective  thermal lattice Boltzmann (D3Q19 flow + D3Q7 scalar, Boussinesq)
//   lattice_conductive  scalar lattice without flow (pure 3D conduction)
//   persistence         the last reference (or the initial field)
// A DomainLearner over lattice-local context (Mach, cell Reynolds, cell Peclet, scalar step,
// velocity curvature, wall distance) learns each method's error against the reference; every
// field cell is predicted BEFORE its call is learned (prequential), and the method with the
// lowest predicted error is selected per cell. So the best-fitting method emerges by context
// domain. A second learner grades the convective lattice's self-consistency against a coarser
// twin lattice (on-the-fly numerical evidence that needs no reference). A diverging lattice is
// recorded as failed and thereafter predicts its last valid state.
struct FieldRegion {
  std::string shape = "box";          // "box": [0,size]^3; "cylinder": axis z, x,y in [-R,R], z in [0,L]
  std::array<double, 3> sizeMm{0, 0, 0};
  double radiusMm = 0.0, lengthMm = 0.0;
};

struct FieldProperties {
  double kinematicViscosityM2S = 0.0;
  double diffusivityM2S = 0.0;
  double expansionPerUnit = 0.0;      // relative density change per field unit (Boussinesq)
  std::array<double, 3> bodyAccelerationM2S{0, 0, 0};
};

struct FieldEvolutionOptions {
  double cellMm = 6.0;                // lattice cell of the methods
  double machTarget = 0.15;           // lattice Mach number of the free-fall velocity bound
  double twinRatio = 1.5;             // twin cell / main cell for self-consistency evidence
  double conductiveTau = 1.0;         // relaxation time of the conduction-only lattice
  std::size_t minElements = 32;       // arbitration learner rows per split side
  std::uint64_t seed = 0;
};

struct FieldEvolutionInput {
  double timeS = 0.0;
  std::vector<double> rate, target, loadPerS;  // per field cell, may be empty
  std::vector<double> reference;               // per field cell, may be empty
};

class FieldEvolution {
 public:
  FieldEvolution(FieldRegion region, std::vector<std::array<double, 3>> cellMin,
                 std::vector<std::array<double, 3>> cellMax, FieldProperties properties,
                 std::vector<double> initialValues, FieldEvolutionOptions options);
  ~FieldEvolution();
  FieldEvolution(FieldEvolution&&) noexcept;
  FieldEvolution& operator=(FieldEvolution&&) noexcept;

  nlohmann::json step(const FieldEvolutionInput& input);
  nlohmann::json summary() const;
  static const std::vector<std::string>& methodNames();

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace trech::ml
