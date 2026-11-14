// Geant4-free checks of the run-level event-deposit shape summary that backs
// the `system_event_edep_*`, `system_event_secondaries_*` and
// `system_event_track_length_*` shape observables, plus the species classes
// behind `system_event_secondaries_<species>_*`.
#include "trech/sim/EventHistogram.hpp"
#include "trech/sim/EventMoments.hpp"
#include "trech/sim/SecondarySpecies.hpp"

#include <array>
#include <cstdint>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace em = trech::sim::event_moments;
namespace eh = trech::sim::event_histogram;

namespace {

void require(bool ok, const std::string& what) {
  if (!ok) {
    throw std::runtime_error(what);
  }
}

bool near(double a, double b, double tol) { return std::abs(a - b) <= tol; }

em::PowerSums sumsOf(const std::vector<double>& values) {
  em::PowerSums sums;
  for (double v : values) {
    em::add(sums, v);
  }
  return sums;
}

} // namespace

int main() {
  try {
    // Empty run: everything zero, shape undefined.
    const auto empty = em::summarize(em::PowerSums{});
    require(empty.mean == 0.0 && !empty.shapeDefined && empty.minimum == 0.0,
            "empty summary must be zero/undefined");

    // Symmetric sample: zero skew; {1,2,3,4,5} has population excess kurtosis -1.3.
    const auto sym = em::summarize(sumsOf({1, 2, 3, 4, 5}));
    require(near(sym.mean, 3.0, 1e-12), "mean of 1..5");
    require(near(sym.variance, 2.0, 1e-12), "population variance of 1..5");
    require(near(sym.stderrMean, std::sqrt(2.0 / 4.0), 1e-12), "stderr of 1..5");
    require(sym.shapeDefined, "1..5 shape defined");
    require(near(sym.skewness, 0.0, 1e-12), "1..5 skewness");
    require(near(sym.excessKurtosis, -1.3, 1e-12), "1..5 excess kurtosis");
    require(sym.minimum == 1.0 && sym.maximum == 5.0, "1..5 min/max");

    // Right-skewed pass-through-like sample: many zeros and one large deposit.
    // {0,0,0,0,10}: mean 2, mu2 16, mu3 96, mu4 1664/5*... computed directly.
    const std::vector<double> tail = {0, 0, 0, 0, 10};
    double mean = 2.0, m2 = 0, m3 = 0, m4 = 0;
    for (double v : tail) {
      const double d = v - mean;
      m2 += d * d / 5.0;
      m3 += d * d * d / 5.0;
      m4 += d * d * d * d / 5.0;
    }
    const auto t = em::summarize(sumsOf(tail));
    require(near(t.zeroFraction, 0.8, 1e-15), "zero fraction 4/5");
    require(near(t.skewness, m3 / std::pow(m2, 1.5), 1e-12), "tail skewness");
    require(t.skewness > 1.0, "tail must be right-skewed");
    require(near(t.excessKurtosis, m4 / (m2 * m2) - 3.0, 1e-12), "tail kurtosis");

    // Thread merge equals the single-stream summary.
    const auto a = sumsOf({0.5, 1.5, 7.0});
    const auto b = sumsOf({0.0, 2.25, 3.0, 11.0});
    const auto whole = em::summarize(sumsOf({0.5, 1.5, 7.0, 0.0, 2.25, 3.0, 11.0}));
    const auto split = em::summarize(em::merge(a, b));
    require(near(whole.skewness, split.skewness, 1e-12) &&
                near(whole.excessKurtosis, split.excessKurtosis, 1e-12) &&
                whole.minimum == split.minimum && whole.maximum == split.maximum &&
                whole.zeroFraction == split.zeroFraction,
            "merged sums must reproduce the single-stream summary");

    // Degenerate and cancellation-floor cases: shape undefined, never noise.
    require(!em::summarize(sumsOf({4.0, 4.0, 4.0, 4.0})).shapeDefined,
            "constant sample shape must be undefined");
    require(!em::summarize(sumsOf({1.0, 2.0})).shapeDefined, "n<3 shape must be undefined");
    const double big = 1e9;
    const auto cancel = em::summarize(sumsOf({big, big + 1e-6, big + 2e-6}));
    require(!cancel.shapeDefined, "spread below cancellation floor must be undefined");

    // Admissibility: excess kurtosis >= skew^2 - 2 for a two-point distribution.
    const auto two = em::summarize(sumsOf({0, 0, 0, 1}));
    require(two.excessKurtosis >= two.skewness * two.skewness - 2.0 - 1e-12,
            "kurtosis admissibility bound");

    // Merge identity: an empty partial sum leaves min/max untouched.
    const auto withEmpty = em::summarize(em::merge(a, em::PowerSums{}));
    require(withEmpty.minimum == 0.5 && withEmpty.maximum == 7.0,
            "merging an empty worker must not move min/max");

    // Index of dispersion of a count variable (secondary multiplicity).
    // {2,2,2,2}: zero variance -> 0 (perfectly regular).
    require(em::dispersionIndex(em::summarize(sumsOf({2, 2, 2, 2}))) == 0.0,
            "constant count dispersion must be 0");
    // {0,1,2,3,4}: mean 2, population variance 2 -> 1 (Poisson-like spread).
    require(near(em::dispersionIndex(em::summarize(sumsOf({0, 1, 2, 3, 4}))), 1.0, 1e-12),
            "dispersion of 0..4");
    // {0,0,0,0,10}: mean 2, variance 16 -> 8 (clustered / over-dispersed).
    require(near(em::dispersionIndex(t), 8.0, 1e-12), "tail dispersion");
    // Zero mean: undefined, never 0 or infinity.
    require(std::isnan(em::dispersionIndex(em::summarize(sumsOf({0, 0, 0})))),
            "zero-mean dispersion must be NaN");
    require(std::isnan(em::dispersionIndex(em::summarize(em::PowerSums{}))),
            "empty dispersion must be NaN");

    // Secondary species classes: optical photons by name (PDG 0 or -22 by
    // Geant4 release), the rest by PDG code, everything else "other".
    namespace ss = trech::sim::secondary_species;
    require(ss::classify(22, "gamma") == ss::kGamma, "gamma class");
    require(ss::classify(11, "e-") == ss::kElectron, "electron class");
    require(ss::classify(-11, "e+") == ss::kPositron, "positron class");
    require(ss::classify(2112, "neutron") == ss::kNeutron, "neutron class");
    require(ss::classify(-22, "opticalphoton") == ss::kOpticalPhoton, "optical photon (-22)");
    require(ss::classify(0, "opticalphoton") == ss::kOpticalPhoton, "optical photon (0)");
    require(ss::classify(2212, "proton") == ss::kProton, "proton class");
    require(ss::classify(1000020040, "alpha") == ss::kAlpha, "alpha class");
    require(ss::classify(1000010020, "deuteron") == ss::kIon, "deuteron is an ion");
    require(ss::classify(1000020030, "He3") == ss::kIon, "He3 is an ion");
    require(ss::classify(1000060120, "C12") == ss::kIon, "C12 is an ion");
    require(ss::classify(1000080160, "O16[6049.000]") == ss::kIon, "excited O16 is an ion");
    require(ss::classify(-1000020040, "anti_alpha") == ss::kOther, "antinuclei are other");
    require(ss::classify(-2212, "anti_proton") == ss::kOther, "antiproton is other");
    require(ss::classify(211, "pi+") == ss::kOther, "pions are other");
    require(ss::classify(0, "geantino") == ss::kOther, "geantino is other");
    require(ss::name(ss::kIon) == "ion" && ss::name(ss::kOther) == "other",
            "new class names keep other last");
    require(ss::name(ss::kOpticalPhoton) == "optical_photon", "species score name");
    require(ss::kNames.size() == ss::kCount, "one name per class");
    // Per-species counts of the same events sum to the total multiplicity, so
    // the summarised species means add up to the total mean.
    {
      const std::vector<std::array<int, ss::kCount>> events = {
          {1, 2, 0, 0, 0, 0, 0, 0, 0}, {0, 0, 0, 0, 0, 0, 0, 0, 0},
          {3, 4, 1, 5, 0, 2, 1, 3, 1}, {0, 1, 0, 0, 2, 1, 0, 0, 0}};
      std::array<em::PowerSums, ss::kCount> perSpecies{};
      em::PowerSums total;
      for (const auto& counts : events) {
        int sum = 0;
        for (std::size_t i = 0; i < counts.size(); ++i) {
          em::add(perSpecies[i], counts[i]);
          sum += counts[i];
        }
        em::add(total, sum);
      }
      double meanSum = 0.0;
      for (const auto& sums : perSpecies) {
        meanSum += em::summarize(sums).mean;
      }
      require(near(meanSum, em::summarize(total).mean, 1e-12), "species means sum to total");
    }

    // ---- Fixed-binning per-event histograms (system_event_*_histogram). ----
    require(eh::kDepositBins == 120, "1 eV .. 1 TeV at 10 bins per decade");
    require(near(eh::depositEdgeMeV(0), 1e-6, 1e-21), "low edge 1 eV");
    require(near(eh::depositEdgeMeV(eh::kDepositBins), 1e6, 1e-6), "high edge 1 TeV");
    require(eh::depositSlot(0.0) == eh::kDepositZeroSlot, "exact zero has its own slot");
    require(eh::depositSlot(1e-9) == eh::kDepositUnderflowSlot, "below 1 eV underflows");
    require(eh::depositSlot(-1.0) == eh::kDepositUnderflowSlot, "negative underflows");
    require(eh::depositSlot(2e6) == eh::kDepositOverflowSlot, "above 1 TeV overflows");
    require(eh::depositSlot(std::nan("")) == eh::kDepositOverflowSlot, "NaN overflows");
    // Every bin edge lands in the bin it opens, and every value lies inside
    // the edges of the bin it is assigned to.
    for (int bin = 0; bin < eh::kDepositBins; ++bin) {
      const double lo = eh::depositEdgeMeV(bin);
      const double hi = eh::depositEdgeMeV(bin + 1);
      require(lo < hi, "edges increase");
      require(eh::depositSlot(lo) == eh::kDepositFirstBinSlot + bin, "edge opens its bin");
      const double inside = std::nextafter(hi, 0.0);
      require(eh::depositSlot(inside) == eh::kDepositFirstBinSlot + bin, "just below next edge");
      const double mid = std::sqrt(lo * hi);
      require(eh::depositSlot(mid) == eh::kDepositFirstBinSlot + bin, "geometric midpoint");
    }
    require(eh::depositSlot(1.0) == eh::kDepositFirstBinSlot + 60, "1 MeV opens bin 60");
    require(eh::depositSlot(0.662) == eh::kDepositFirstBinSlot + 58, "662 keV in [0.631, 0.794)");

    // The deposit, volume-deposit and track-length histograms share one grid.
    require(eh::kLogSlots == eh::kDepositSlots && eh::kLogBins == eh::kDepositBins,
            "deposit histogram is the shared log grid");
    for (int bin = 0; bin <= eh::kLogBins; ++bin) {
      require(eh::trackLengthEdgeMm(bin) == eh::depositEdgeMeV(bin) &&
                  eh::logEdge(bin) == eh::depositEdgeMeV(bin),
              "track-length edges are the shared grid");
    }
    require(eh::trackLengthSlot(0.0) == eh::kLogZeroSlot, "zero track length");
    require(eh::trackLengthSlot(5e-7) == eh::kLogUnderflowSlot, "below 1 nm underflows");
    require(eh::trackLengthSlot(2e6) == eh::kLogOverflowSlot, "beyond 1 km overflows");
    require(eh::trackLengthSlot(100.0) == eh::kLogFirstBinSlot + 80, "100 mm opens bin 80");
    require(eh::trackLengthSlot(367.0) == eh::kLogFirstBinSlot + 85, "367 mm in [316, 398)");
    for (const double v : {1e-5, 0.3, 12.0, 4.5e4}) {
      require(eh::trackLengthSlot(v) == eh::depositSlot(v), "same slot on the shared grid");
    }

    require(eh::kMultiplicityBins == 43, "16 exact + 27 octaves");
    require(eh::multiplicityEdge(eh::kMultiplicityBins) == (std::int64_t{1} << 31), "overflow edge");
    for (int n = 0; n < 16; ++n) {
      require(eh::multiplicitySlot(n) == n, "exact small counts");
    }
    require(eh::multiplicitySlot(16) == 16 && eh::multiplicitySlot(31) == 16, "[16, 32)");
    require(eh::multiplicitySlot(32) == 17 && eh::multiplicitySlot(1000) == 21, "octaves");
    require(eh::multiplicitySlot(2.4) == 2 && eh::multiplicitySlot(2.6) == 3, "rounded counts");
    require(eh::multiplicitySlot(-1.0) == eh::kMultiplicityOverflowSlot, "negative overflows");
    require(eh::multiplicitySlot(4.0e9) == eh::kMultiplicityOverflowSlot, "huge overflows");
    for (int bin = 0; bin < eh::kMultiplicityBins; ++bin) {
      const auto lo = eh::multiplicityEdge(bin);
      const auto hi = eh::multiplicityEdge(bin + 1);
      require(lo < hi, "multiplicity edges increase");
      require(eh::multiplicitySlot(static_cast<double>(lo)) == bin, "edge opens bin");
      require(eh::multiplicitySlot(static_cast<double>(hi - 1)) == bin, "last value in bin");
    }
    // Two partial histograms merge by addition into the single-thread result.
    {
      const std::vector<double> values = {0.0, 0.0, 1e-3, 0.5, 0.662, 0.662, 3.0, 1e-8, 5e6};
      std::vector<std::int64_t> whole(eh::kDepositSlots, 0), left(eh::kDepositSlots, 0),
          right(eh::kDepositSlots, 0);
      for (std::size_t i = 0; i < values.size(); ++i) {
        const int slot = eh::depositSlot(values[i]);
        whole[slot] += 1;
        (i % 2 == 0 ? left : right)[slot] += 1;
      }
      std::int64_t total = 0;
      for (int slot = 0; slot < eh::kDepositSlots; ++slot) {
        require(whole[slot] == left[slot] + right[slot], "integer merge is exact");
        total += whole[slot];
      }
      require(total == static_cast<std::int64_t>(values.size()), "every event counted once");
      require(whole[eh::kDepositZeroSlot] == 2 && whole[eh::kDepositUnderflowSlot] == 1 &&
                  whole[eh::kDepositOverflowSlot] == 1,
              "zero / underflow / overflow slots");
      const std::vector<std::int64_t> bins(whole.begin() + eh::kDepositFirstBinSlot,
                                           whole.begin() + eh::kDepositOverflowSlot);
      const auto span = eh::populatedSpan(bins);
      require(span.first == 30 && span.last == 64, "populated span 1 keV .. 3 MeV");
      require(eh::populatedSpan(std::vector<std::int64_t>(4, 0)).last == -1, "empty span");
    }

    std::cout << "event moments ok\n";
    return 0;
  } catch (const std::exception& ex) {
    std::cerr << "test_event_moments failed: " << ex.what() << "\n";
    return 1;
  }
}
