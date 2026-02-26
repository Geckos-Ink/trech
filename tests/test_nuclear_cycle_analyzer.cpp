#include "trech/sim/NuclearCycleAnalyzer.hpp"

#include <cmath>
#include <iostream>

namespace {

int expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << "\n";
    return 1;
  }
  return 0;
}

bool closeTo(double value, double expected, double tol) {
  return std::fabs(value - expected) <= tol;
}

} // namespace

int main() {
  trech::NuclearCycleConfig cycle;
  cycle.name = "nitrogen_carbon14_cycle";
  cycle.enable = true;
  cycle.source.symbol = "N";
  cycle.source.z = 7;
  cycle.source.a = 14;
  cycle.source.phase = "gas";
  cycle.source.densityGcm3 = 0.0012506;
  cycle.target.symbol = "C";
  cycle.target.z = 6;
  cycle.target.a = 14;
  cycle.target.phase = "solid";
  cycle.target.densityGcm3 = 2.267;

  cycle.forward.name = "n14_neutron_capture";
  cycle.forward.reactants = {{"", 7, 14}, {"neutron", 0, 0}};
  cycle.forward.products = {{"", 6, 14}, {"proton", 0, 0}};

  cycle.backward.name = "c14_beta_decay";
  cycle.backward.halfLifeYears = 5730.0;
  cycle.backward.reactants = {{"", 6, 14}};
  cycle.backward.products = {{"", 7, 14}, {"e-", 0, 0}, {"anti_nu_e", 0, 0}};

  const auto metrics = trech::sim::analyzeNuclearCycle(cycle);
  if (expect(metrics.enabled, "Expected enabled cycle.")) {
    return 1;
  }
  if (expect(metrics.atomicMassConserved, "Expected mass number conservation.")) {
    return 1;
  }
  if (expect(metrics.forward.available && metrics.forward.massResolved,
             "Expected forward reaction to resolve.")) {
    return 1;
  }
  if (expect(metrics.forward.baryonConserved && metrics.forward.chargeConserved,
             "Expected forward conservation laws.")) {
    return 1;
  }
  if (expect(metrics.backward.available && metrics.backward.massResolved,
             "Expected backward reaction to resolve.")) {
    return 1;
  }
  if (expect(metrics.backward.baryonConserved && metrics.backward.chargeConserved,
             "Expected backward conservation laws.")) {
    return 1;
  }
  if (expect(closeTo(metrics.forward.qValueMeV, 0.626, 0.05),
             "Forward Q-value mismatch for N-14(n,p)C-14.")) {
    return 1;
  }
  if (expect(closeTo(metrics.backward.qValueMeV, 0.156, 0.05),
             "Backward Q-value mismatch for C-14 beta decay.")) {
    return 1;
  }
  if (expect(metrics.phaseTransition == "gas_to_solid",
             "Expected gas-to-solid macro phase transition.")) {
    return 1;
  }
  if (expect(metrics.densityRatio > 1000.0, "Expected large density ratio shift.")) {
    return 1;
  }
  if (expect(metrics.cycleConsistent, "Expected cycle consistency to pass.")) {
    return 1;
  }

  return 0;
}
