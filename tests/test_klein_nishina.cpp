// Geant4-free checks of the Klein-Nishina reference used by the
// `compton_energy_transfer` analytic cross-check.
#include "trech/sim/KleinNishina.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

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

    // Angular distribution. Thomson limit: <cos theta> -> 0 and the bins are
    // symmetric about 90 degrees with the (1 + cos^2) shape.
    require(std::abs(kn::meanCosTheta(small)) < 1e-3, "Thomson <cos theta> != 0");
    {
      const auto thomsonBins = kn::cosThetaBinProbabilities(small);
      const int n = kn::kCosThetaHistogramBins;
      for (int k = 0; k < n / 2; ++k) {
        require(std::abs(thomsonBins[static_cast<std::size_t>(k)] -
                         thomsonBins[static_cast<std::size_t>(n - 1 - k)]) < 1e-3,
                "Thomson cos(theta) bins must be symmetric");
      }
      require(thomsonBins.front() > thomsonBins[n / 2], "Thomson 1+cos^2 shape missing");
    }
    double previousCos = -1.0;
    for (double energyMeV : {0.01, 0.1, 0.6617, 3.0, 10.0}) {
      const double epsA = energyMeV / kElectronRestMeV;
      const double meanCos = kn::meanCosTheta(epsA);
      require(std::abs(meanCos - kn::meanCosTheta(epsA, 16384)) < 1e-9,
              "<cos theta> quadrature not converged");
      require(meanCos > previousCos && meanCos < 1.0, "<cos theta> must rise with energy");
      previousCos = meanCos;
      const auto probs = kn::cosThetaBinProbabilities(epsA);
      require(static_cast<int>(probs.size()) == kn::kCosThetaHistogramBins, "cos bin count");
      double total = 0.0;
      double binnedMean = 0.0;
      for (std::size_t k = 0; k < probs.size(); ++k) {
        require(probs[k] > 0.0, "every cos(theta) bin must have positive probability");
        total += probs[k];
      }
      require(std::abs(total - 1.0) < 1e-12, "cos(theta) bin probabilities must sum to 1");
      const auto refined = kn::cosThetaBinProbabilities(epsA, kn::kCosThetaHistogramBins, 4096);
      for (std::size_t k = 0; k < probs.size(); ++k) {
        require(std::abs(probs[k] - refined[k]) < 1e-10, "cos(theta) bins not converged");
      }
      const int fine = 4000;
      const auto fineProbs = kn::cosThetaBinProbabilities(epsA, fine, 16);
      for (int k = 0; k < fine; ++k) {
        binnedMean += fineProbs[static_cast<std::size_t>(k)] * (-1.0 + 2.0 * (k + 0.5) / fine);
      }
      require(std::abs(binnedMean - meanCos) < 1e-6, "binned cos(theta) moments disagree");
      // Forward peaking: above the Thomson regime the forward bin dominates.
      if (energyMeV >= 0.6617) {
        require(probs.back() > probs.front(), "forward peak missing");
      }
      std::cout << energyMeV << " MeV: <cos theta>=" << meanCos << '\n';
    }
    // Cross-reading closure: each u = T/T_max bin maps one-to-one onto a
    // cos(theta) interval, so the integrated probability over cos >= cos(u)
    // equals the cumulative u-bin probability (both are the same KN integral).
    {
      const auto uProbs = kn::transferBinProbabilities(eps, kn::kTransferHistogramBins, 2048);
      const auto cosFine = kn::cosThetaBinProbabilities(eps, 20000, 8);
      double cumulativeU = 0.0;
      for (int k = 0; k < kn::kTransferHistogramBins; ++k) {
        cumulativeU += uProbs[static_cast<std::size_t>(k)];
        const double c = kn::cosThetaForEdgeFraction(eps, (k + 1.0) / kn::kTransferHistogramBins);
        double forward = 0.0;
        for (int j = 0; j < 20000; ++j) {
          const double lo = -1.0 + 2.0 * j / 20000.0;
          const double hi = lo + 2.0 / 20000.0;
          if (lo >= c) {
            forward += cosFine[static_cast<std::size_t>(j)];
          } else if (hi > c) {
            forward += cosFine[static_cast<std::size_t>(j)] * (hi - c) / (hi - lo);
          }
        }
        require(std::abs(forward - cumulativeU) < 2e-5, "u and cos(theta) CDFs disagree");
      }
    }
    // Bin assignment over [-1, 1].
    require(kn::cosThetaHistogramBin(-1.0) == 0, "back-scatter must be bin 0");
    require(kn::cosThetaHistogramBin(1.0) == kn::kCosThetaHistogramBins - 1, "forward bin");
    require(kn::cosThetaHistogramBin(1.0 + 1e-12) == kn::kCosThetaHistogramBins - 1,
            "overshoot must clamp");
    require(kn::cosThetaHistogramBin(std::nan("")) == -1, "NaN must be unbinned");
    for (int k = 0; k < kn::kCosThetaHistogramBins; ++k) {
      const double c = -1.0 + 2.0 * (k + 0.5) / kn::kCosThetaHistogramBins;
      require(kn::cosThetaHistogramBin(c) == k, "cos(theta) bin interior misassigned");
    }
    // Energy-angle closure: P(cos) inverts cosThetaForEdgeFraction.
    for (double u : {0.0, 0.25, 0.5, 0.9, 1.0}) {
      const double c = kn::cosThetaForEdgeFraction(eps, u);
      const double p = kn::scatteredEnergyRatio(eps, c);
      require(std::abs((1.0 - p) - u * edge) < 1e-12, "energy-angle relation not closed");
    }

    // Pooled Pearson chi^2: exact expectation gives 0; a perfect 4-bin case has
    // dof 3; low-expectation bins (incl. a trailing remainder) are pooled.
    {
      const std::vector<double> p4{0.25, 0.25, 0.25, 0.25};
      const auto exact = kn::pooledPearsonChi2(std::vector<int>{25, 25, 25, 25}, p4);
      require(exact.valid && exact.chi2 == 0.0 && exact.dof == 3 && exact.entries == 100,
              "exact histogram chi^2");
      const auto off = kn::pooledPearsonChi2(std::vector<int>{30, 20, 25, 25}, p4);
      require(std::abs(off.chi2 - 2.0) < 1e-12, "chi^2 value");  // (25+25)/25
      // n = 20, p {.1, .1, .1, .7}: expected counts {2, 2, 2, 14}.
      const std::vector<double> skew{0.1, 0.1, 0.1, 0.7};
      const auto pooled = kn::pooledPearsonChi2(std::vector<int>{2, 2, 2, 14}, skew);
      // Cells: {2+2+2 exp 6} and {14 exp 14} -> dof 1, chi^2 0.
      require(pooled.valid && pooled.dof == 1 && pooled.chi2 == 0.0, "pooling of low bins");
      const std::vector<double> tail{0.7, 0.1, 0.1, 0.1};
      const auto trailing = kn::pooledPearsonChi2(std::vector<int>{14, 2, 2, 2}, tail);
      // Cells {14 exp 14} then {2+2+2 exp 6}: the remainder reaches 6 >= 5 only at
      // the end, so it closes on its own -> dof 1.
      require(trailing.valid && trailing.dof == 1, "trailing pooling");
      const std::vector<double> tail2{0.85, 0.05, 0.05, 0.05};
      const auto merged = kn::pooledPearsonChi2(std::vector<int>{17, 1, 1, 1}, tail2);
      // Remainder exp 3 < 5 merges into the first cell -> one cell, dof 0.
      require(merged.valid && merged.dof == 0 && merged.chi2 == 0.0, "remainder merge");
      require(!kn::pooledPearsonChi2(std::vector<int>{1, 2}, p4).valid, "size mismatch");
      require(!kn::pooledPearsonChi2(std::vector<int>{0, 0, 0, 0}, p4).valid, "empty");
    }
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
