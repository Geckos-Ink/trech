// Geant4-free checks of the Klein-Nishina reference used by the
// `compton_energy_transfer` analytic cross-check.
#include "trech/sim/KleinNishina.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

namespace kn = trech::sim::klein_nishina;

namespace {

void require(bool ok, const std::string& what) {
  if (!ok) {
    throw std::runtime_error(what);
  }
}

constexpr double kElectronRestMeV = 0.51099895;

} // namespace

int main() {
  try {
    // Thomson limit: for eps -> 0 the scatter is symmetric about 90 degrees, so
    // <1 - cos theta> = 1 and <T>/E -> eps (to first order).
    const double small = 1e-4;
    const double thomson = kn::meanTransferFraction(small);
    require(std::abs(thomson / small - 1.0) < 1e-3, "Thomson limit <T>/E != eps");

    // Tabulated reference (Attix, Introduction to Radiological Physics, Table
    // 7.1 / Hubbell): sigma_tr/sigma = 0.440 at 1 MeV.
    const double oneMeV = kn::meanTransferFraction(1.0 / kElectronRestMeV);
    require(std::abs(oneMeV - 0.440) < 0.0022, "1 MeV <T>/E differs from 0.440 by >0.5%");

    // Edge formula at Cs-137 (0.6617 MeV): the textbook Compton edge 0.4774 MeV.
    const double eps662 = 0.6617 / kElectronRestMeV;
    const double edgeMeV = kn::comptonEdgeFraction(eps662) * 0.6617;
    require(std::abs(edgeMeV - 0.4774) < 0.0005, "Cs-137 Compton edge is not 0.477 MeV");

    // Quadrature convergence and physical ordering across energies.
    double previous = 0.0;
    for (double energyMeV : {0.01, 0.05, 0.1, 0.3, 0.6617, 1.0, 3.0, 10.0}) {
      const double eps = energyMeV / kElectronRestMeV;
      const double mean = kn::meanTransferFraction(eps);
      const double refined = kn::meanTransferFraction(eps, 16384);
      require(std::abs(mean - refined) < 1e-8 * refined, "Simpson quadrature not converged");
      require(mean > previous, "<T>/E must increase with photon energy");
      require(mean > 0.0 && mean < kn::comptonEdgeFraction(eps),
              "<T>/E must lie strictly between 0 and the Compton edge");
      previous = mean;
      std::cout << energyMeV << " MeV: <T>/E=" << mean
                << " edge=" << kn::comptonEdgeFraction(eps) << '\n';
    }
    require(kn::meanTransferFraction(0.0) == 0.0 && kn::comptonEdgeFraction(-1.0) == 0.0,
            "non-positive epsilon must return 0");
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
