#pragma once

#include "trech/ml/FieldMethods.hpp"

#include <array>
#include <memory>
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
// On the first call every method of the engine's field-method registry (FieldMethods.hpp) is
// built for the declared system; a method that cannot represent it records why and is not a
// candidate. Built-ins: lattice_convective, lattice_conductive, learned_operator, persistence.
// Every candidate advances on the same clock from the same observed state; a MethodArbiter
// (MethodArbiter.hpp) over the call context predicts each method's error BEFORE learning the
// call and selects the lowest per cell, so the best-fitting method emerges by context domain.
// The context is method-independent (FieldEvolution::contextNames) plus the descriptors that
// candidates contribute (prefixed "<method>."). A method added to the registry later joins the
// arbitration with no change here.
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
  // Names of the registered methods, in registry order (candidates are the applicable ones).
  static std::vector<std::string> methodNames();
  // Method-independent context of each field cell and call.
  static const std::vector<std::string>& contextNames();

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace trech::ml
