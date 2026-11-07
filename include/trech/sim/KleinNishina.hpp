#pragma once

// Free-electron Klein-Nishina kinematics for the `compton_energy_transfer`
// analytic cross-check. Pure, Geant4-free functions so they can be unit tested
// without a transport build. The caller supplies epsilon = E_gamma / (m_e c^2),
// taking m_e c^2 from Geant4's own CLHEP constant (`electron_mass_c2`).
//
// These are CLASSICAL closed-form references ("physics for comparison"): the
// check compares them to the energy loss Geant4 actually samples for a primary
// photon's first Compton interaction. They never drive transport.

#include <algorithm>
#include <cmath>
#include <vector>

namespace trech {
namespace sim {
namespace klein_nishina {

// Scattered-photon energy ratio P = E'/E for scattering angle cos(theta).
inline double scatteredEnergyRatio(double epsilon, double cosTheta) {
  return 1.0 / (1.0 + epsilon * (1.0 - cosTheta));
}

// Unnormalised Klein-Nishina weight dsigma/dcos(theta) / (pi r_e^2):
// P^2 (P + 1/P - sin^2 theta).
inline double differentialWeight(double epsilon, double cosTheta) {
  const double p = scatteredEnergyRatio(epsilon, cosTheta);
  const double sin2 = 1.0 - cosTheta * cosTheta;
  return p * p * (p + 1.0 / p - sin2);
}

// Compton edge: maximum fraction of the photon energy given to the electron
// (back-scatter, theta = pi): T_max / E = 2 eps / (1 + 2 eps).
inline double comptonEdgeFraction(double epsilon) {
  if (!(epsilon > 0.0)) {
    return 0.0;
  }
  return 2.0 * epsilon / (1.0 + 2.0 * epsilon);
}

// Mean fraction of the photon energy transferred to the electron per Compton
// scatter, <T>/E = sigma_tr / sigma = int (1-P) w dcos / int w dcos, evaluated by
// fixed composite Simpson quadrature over cos(theta) in [-1, 1]. The integrand is
// smooth on the closed interval, so a fixed even panel count is deterministic and
// accurate far below Monte-Carlo noise (relative error <1e-8 at 4096 panels up
// to 10 MeV, where the forward peak is sharpest).
inline double meanTransferFraction(double epsilon, int panels = 4096) {
  if (!(epsilon > 0.0)) {
    return 0.0;
  }
  if (panels < 2) {
    panels = 2;
  }
  if (panels % 2 != 0) {
    ++panels;
  }
  const double h = 2.0 / static_cast<double>(panels);
  double weightSum = 0.0;
  double transferSum = 0.0;
  for (int i = 0; i <= panels; ++i) {
    const double cosTheta = -1.0 + h * static_cast<double>(i);
    const double coefficient = (i == 0 || i == panels) ? 1.0 : (i % 2 == 1 ? 4.0 : 2.0);
    const double w = differentialWeight(epsilon, cosTheta);
    const double p = scatteredEnergyRatio(epsilon, cosTheta);
    weightSum += coefficient * w;
    transferSum += coefficient * w * (1.0 - p);
  }
  return weightSum > 0.0 ? transferSum / weightSum : 0.0;
}

// Number of equal-width bins of u = T / T_max (the electron's share of the
// Compton-edge energy) used by the binned spectrum-shape test. Shared by the
// run tally and the reference so both sides bin identically.
constexpr int kTransferHistogramBins = 20;

// Scattering angle cos(theta) at which the electron receives the fraction
// u = T / T_max of the Compton-edge energy. u = 0 is forward (cos = 1), u = 1 is
// back-scatter (cos = -1); the map is monotone, so u bins map to cos intervals.
inline double cosThetaForEdgeFraction(double epsilon, double u) {
  const double edge = comptonEdgeFraction(epsilon);
  const double p = 1.0 - std::clamp(u, 0.0, 1.0) * edge;  // E'/E
  const double cosTheta = 1.0 - (1.0 / p - 1.0) / epsilon;
  return std::clamp(cosTheta, -1.0, 1.0);
}

// Bin index of a sampled transfer fraction T/E for a photon of reduced energy
// epsilon: u = (T/E) / edge, clamped into [0, bins - 1] so a sample exactly at
// (or a last-ULP above) the edge lands in the last bin. Returns -1 when epsilon
// is non-positive.
inline int transferHistogramBin(double epsilon, double transferFraction,
                                int bins = kTransferHistogramBins) {
  const double edge = comptonEdgeFraction(epsilon);
  if (!(edge > 0.0) || bins < 1) {
    return -1;
  }
  const double u = transferFraction / edge;
  const int bin = static_cast<int>(std::floor(u * static_cast<double>(bins)));
  return std::clamp(bin, 0, bins - 1);
}

// Free-electron Klein-Nishina probability that a Compton scatter lands in each
// equal-width u = T/T_max bin: the integral of dsigma/dcos(theta) over the bin's
// cos(theta) interval (fixed composite Simpson, panelsPerBin even panels per
// bin), normalised by the sum over all bins (which is the total cross section).
// This is the binned dsigma/dT spectrum SHAPE -- not just its mean or edge -- and
// is compared to the run's first-Compton transfer histogram by a Pearson chi^2.
inline std::vector<double> transferBinProbabilities(double epsilon,
                                                    int bins = kTransferHistogramBins,
                                                    int panelsPerBin = 512) {
  std::vector<double> probabilities;
  if (!(epsilon > 0.0) || bins < 1) {
    return probabilities;
  }
  if (panelsPerBin < 2) {
    panelsPerBin = 2;
  }
  if (panelsPerBin % 2 != 0) {
    ++panelsPerBin;
  }
  probabilities.resize(static_cast<std::size_t>(bins), 0.0);
  double total = 0.0;
  for (int k = 0; k < bins; ++k) {
    // Higher u is lower cos(theta): integrate from the back edge to the front.
    const double lo = cosThetaForEdgeFraction(epsilon, static_cast<double>(k + 1) / bins);
    const double hi = cosThetaForEdgeFraction(epsilon, static_cast<double>(k) / bins);
    const double h = (hi - lo) / static_cast<double>(panelsPerBin);
    double sum = 0.0;
    for (int i = 0; i <= panelsPerBin; ++i) {
      const double c = (i == 0 || i == panelsPerBin) ? 1.0 : (i % 2 == 1 ? 4.0 : 2.0);
      sum += c * differentialWeight(epsilon, lo + h * static_cast<double>(i));
    }
    const double integral = sum * h / 3.0;
    probabilities[static_cast<std::size_t>(k)] = integral;
    total += integral;
  }
  if (total > 0.0) {
    for (double& p : probabilities) {
      p /= total;
    }
  }
  return probabilities;
}

// ---------------------------------------------------------------------------
// Angular distribution of the scattered photon. The tally reads cos(theta)
// from the primary's pre/post-step momentum DIRECTION, independently of its
// energy loss, so this is a second binned test (direction sampling) rather than
// a re-binning of the u = T/T_max spectrum (energy sampling).

// Number of equal-width cos(theta) bins over [-1, 1]; bin 0 is back-scatter.
constexpr int kCosThetaHistogramBins = 20;

// Bin of a sampled cos(theta) in kCosThetaHistogramBins equal-width bins over
// [-1, 1]; cos = 1 (and last-ULP overshoots) clamp into the last bin. Returns -1
// for a non-finite value.
inline int cosThetaHistogramBin(double cosTheta, int bins = kCosThetaHistogramBins) {
  if (!std::isfinite(cosTheta) || bins < 1) {
    return -1;
  }
  const double x = (std::clamp(cosTheta, -1.0, 1.0) + 1.0) * 0.5;
  const int bin = static_cast<int>(std::floor(x * static_cast<double>(bins)));
  return std::clamp(bin, 0, bins - 1);
}

// Free-electron Klein-Nishina probability per equal-width cos(theta) bin:
// integral of dsigma/dcos(theta) over each bin (composite Simpson), normalised
// by the total.
inline std::vector<double> cosThetaBinProbabilities(double epsilon,
                                                    int bins = kCosThetaHistogramBins,
                                                    int panelsPerBin = 512) {
  std::vector<double> probabilities;
  if (!(epsilon > 0.0) || bins < 1) {
    return probabilities;
  }
  if (panelsPerBin < 2) {
    panelsPerBin = 2;
  }
  if (panelsPerBin % 2 != 0) {
    ++panelsPerBin;
  }
  probabilities.resize(static_cast<std::size_t>(bins), 0.0);
  const double width = 2.0 / static_cast<double>(bins);
  const double h = width / static_cast<double>(panelsPerBin);
  double total = 0.0;
  for (int k = 0; k < bins; ++k) {
    const double lo = -1.0 + width * static_cast<double>(k);
    double sum = 0.0;
    for (int i = 0; i <= panelsPerBin; ++i) {
      const double c = (i == 0 || i == panelsPerBin) ? 1.0 : (i % 2 == 1 ? 4.0 : 2.0);
      sum += c * differentialWeight(epsilon, lo + h * static_cast<double>(i));
    }
    const double integral = sum * h / 3.0;
    probabilities[static_cast<std::size_t>(k)] = integral;
    total += integral;
  }
  if (total > 0.0) {
    for (double& p : probabilities) {
      p /= total;
    }
  }
  return probabilities;
}

// Free-electron Klein-Nishina mean scattering cosine <cos theta> = int cos w /
// int w over [-1, 1] (fixed composite Simpson, as meanTransferFraction). Zero in
// the Thomson limit (symmetric about 90 degrees), rising towards 1 as the
// forward peak sharpens with energy.
inline double meanCosTheta(double epsilon, int panels = 4096) {
  if (!(epsilon > 0.0)) {
    return 0.0;
  }
  if (panels < 2) {
    panels = 2;
  }
  if (panels % 2 != 0) {
    ++panels;
  }
  const double h = 2.0 / static_cast<double>(panels);
  double weightSum = 0.0;
  double cosSum = 0.0;
  for (int i = 0; i <= panels; ++i) {
    const double cosTheta = -1.0 + h * static_cast<double>(i);
    const double coefficient = (i == 0 || i == panels) ? 1.0 : (i % 2 == 1 ? 4.0 : 2.0);
    const double w = differentialWeight(epsilon, cosTheta);
    weightSum += coefficient * w;
    cosSum += coefficient * w * cosTheta;
  }
  return weightSum > 0.0 ? cosSum / weightSum : 0.0;
}

// Pearson chi^2 of an observed histogram against bin probabilities. Adjacent
// bins are pooled (in order) until the expected count reaches minExpected so the
// chi^2 approximation holds; a short trailing remainder is merged into the
// previous pooled bin rather than kept as its own low-expectation cell.
// dof = pooled bins - 1 (the total is fixed by the sample). `valid` is false
// when the sizes differ or the histogram is empty.
struct PooledChi2 {
  double chi2 = 0.0;
  int dof = 0;
  long long entries = 0;
  bool valid = false;
};

template <typename Count>
inline PooledChi2 pooledPearsonChi2(const std::vector<Count>& observed,
                                    const std::vector<double>& probabilities,
                                    double minExpected = 5.0) {
  PooledChi2 out;
  if (observed.empty() || observed.size() != probabilities.size()) {
    return out;
  }
  for (const auto count : observed) {
    out.entries += static_cast<long long>(count);
  }
  if (out.entries <= 0) {
    return out;
  }
  const double n = static_cast<double>(out.entries);
  std::vector<double> pooledExpected;
  std::vector<double> pooledObserved;
  double expectedAcc = 0.0;
  double observedAcc = 0.0;
  for (std::size_t k = 0; k < probabilities.size(); ++k) {
    expectedAcc += n * probabilities[k];
    observedAcc += static_cast<double>(observed[k]);
    if (expectedAcc >= minExpected) {
      pooledExpected.push_back(expectedAcc);
      pooledObserved.push_back(observedAcc);
      expectedAcc = 0.0;
      observedAcc = 0.0;
    }
  }
  if (expectedAcc > 0.0 || observedAcc > 0.0) {
    if (pooledExpected.empty()) {
      pooledExpected.push_back(expectedAcc);
      pooledObserved.push_back(observedAcc);
    } else {
      pooledExpected.back() += expectedAcc;
      pooledObserved.back() += observedAcc;
    }
  }
  int cells = 0;
  for (std::size_t k = 0; k < pooledExpected.size(); ++k) {
    if (pooledExpected[k] > 0.0) {
      const double diff = pooledObserved[k] - pooledExpected[k];
      out.chi2 += diff * diff / pooledExpected[k];
      ++cells;
    }
  }
  out.dof = std::max(0, cells - 1);
  out.valid = true;
  return out;
}

} // namespace klein_nishina
} // namespace sim
} // namespace trech
