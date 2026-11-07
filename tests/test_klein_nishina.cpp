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

    // Binned spectrum shape: the u = T/T_max bin probabilities must sum to 1, be
    // converged, reproduce the mean transfer via their bin moments, and show the
    // KN Compton-edge rise (the last bin exceeds the middle bins at 662 keV).
    for (double energyMeV : {0.1, 0.6617, 3.0}) {
      const double eps = energyMeV / kElectronRestMeV;
      const auto probs = kn::transferBinProbabilities(eps);
      require(static_cast<int>(probs.size()) == kn::kTransferHistogramBins, "bin count");
      double total = 0.0;
      for (double p : probs) {
        require(p > 0.0, "every KN transfer bin must have positive probability");
        total += p;
      }
      require(std::abs(total - 1.0) < 1e-12, "KN bin probabilities must sum to 1");
      const auto refined = kn::transferBinProbabilities(eps, kn::kTransferHistogramBins, 4096);
      for (std::size_t k = 0; k < probs.size(); ++k) {
        require(std::abs(probs[k] - refined[k]) < 1e-10, "KN bin quadrature not converged");
      }
      // Fine binning: the probability-weighted bin centres approach <T>/E.
      const int fine = 4000;
      const auto fineProbs = kn::transferBinProbabilities(eps, fine, 16);
      double mean = 0.0;
      for (int k = 0; k < fine; ++k) {
        mean += fineProbs[static_cast<std::size_t>(k)] * (k + 0.5) / fine;
      }
      mean *= kn::comptonEdgeFraction(eps);
      require(std::abs(mean - kn::meanTransferFraction(eps)) < 1e-6,
              "binned spectrum moments disagree with the KN mean transfer");
      std::cout << energyMeV << " MeV bins: first=" << probs.front() << " last=" << probs.back()
                << '\n';
    }
    const auto cs = kn::transferBinProbabilities(0.6617 / kElectronRestMeV);
    require(cs.back() > cs[kn::kTransferHistogramBins / 2], "Compton-edge rise missing");

    // Bin assignment: forward (0) is bin 0, the edge and a last-ULP overshoot
    // clamp into the last bin, and each bin's interior lands in that bin.
    const double eps = 0.6617 / kElectronRestMeV;
    const double edge = kn::comptonEdgeFraction(eps);
    require(kn::transferHistogramBin(eps, 0.0) == 0, "zero transfer must be bin 0");
    require(kn::transferHistogramBin(eps, edge) == kn::kTransferHistogramBins - 1, "edge bin");
    require(kn::transferHistogramBin(eps, edge * (1.0 + 1e-12)) ==
                kn::kTransferHistogramBins - 1,
            "overshoot must clamp to the last bin");
    for (int k = 0; k < kn::kTransferHistogramBins; ++k) {
      const double u = (k + 0.5) / kn::kTransferHistogramBins;
      require(kn::transferHistogramBin(eps, u * edge) == k, "bin interior misassigned");
    }
    require(kn::transferHistogramBin(0.0, 0.1) == -1, "non-positive epsilon must be unbinned");
    // The u -> cos(theta) map is monotone from forward (u=0) to back-scatter (u=1).
    require(std::abs(kn::cosThetaForEdgeFraction(eps, 0.0) - 1.0) < 1e-12 &&
                std::abs(kn::cosThetaForEdgeFraction(eps, 1.0) + 1.0) < 1e-9,
            "u -> cos(theta) endpoints");
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
