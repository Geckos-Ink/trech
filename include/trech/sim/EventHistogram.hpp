#pragma once

// Fixed-binning histograms of per-event scalars (the event energy deposit,
// each scored volume's event deposit, the event's summed track length and its
// secondary multiplicity). The bin layout is fixed before the run,
// so worker threads fill integer counts that merge by plain addition: the
// merged histogram is independent of worker count and merge order, unlike a
// floating-point sum.
//
// These are descriptive tallies of what Geant4 sampled (a system observable),
// never a fitted or assumed distribution. Pure and Geant4-free so the binning
// can be unit tested without a transport build.
//
// Slot layout of the log10 histograms (deposit, volume deposit, track length):
//   0                         events that deposited exactly zero
//   1                         0 < value < low edge (or negative)
//   2 .. 2 + kDepositBins - 1 log10 bins [edge(i), edge(i + 1))
//   kDepositSlots - 1         value >= high edge, or non-finite
//
// Slot layout of the multiplicity histogram:
//   0 .. kMultiplicityExactBelow - 1     exact counts 0, 1, ..., 15
//   then one slot per power of two       [2^k, 2^(k + 1))
//   kMultiplicitySlots - 1               count >= 2^kMultiplicityLog2Max,
//                                        negative or non-finite

#include <cmath>
#include <cstdint>
#include <vector>

namespace trech {
namespace sim {
namespace event_histogram {

// ---- Shared log10 grid: 10 bins per decade over [1e-6, 1e6) in the
// quantity's unit. The event deposit uses it in MeV (1 eV .. 1 TeV), the
// event track length in mm (1 nm .. 1 km), and every scoreEdep volume's
// per-event deposit in MeV. One grid, one slot layout. ----
inline constexpr int kLogLowExponent = -6;
inline constexpr int kLogHighExponent = 6;
inline constexpr int kLogBinsPerDecade = 10;
inline constexpr int kLogBins = (kLogHighExponent - kLogLowExponent) * kLogBinsPerDecade;
inline constexpr int kLogZeroSlot = 0;
inline constexpr int kLogUnderflowSlot = 1;
inline constexpr int kLogFirstBinSlot = 2;
inline constexpr int kLogOverflowSlot = kLogFirstBinSlot + kLogBins;
inline constexpr int kLogSlots = kLogOverflowSlot + 1;

// Lower edge of log bin `bin` (0 .. kLogBins); logEdge(kLogBins) is the high
// edge. Computed from an integer exponent numerator so every caller gets
// identical edges.
inline double logEdge(int bin) {
  return std::pow(10.0, static_cast<double>(kLogLowExponent * kLogBinsPerDecade + bin) /
                            static_cast<double>(kLogBinsPerDecade));
}

inline int logSlot(double value) {
  if (value == 0.0) {
    return kLogZeroSlot;
  }
  if (!std::isfinite(value)) {
    return kLogOverflowSlot;
  }
  if (value < logEdge(0)) {
    return kLogUnderflowSlot;
  }
  if (value >= logEdge(kLogBins)) {
    return kLogOverflowSlot;
  }
  const double position = (std::log10(value) - static_cast<double>(kLogLowExponent)) *
                          static_cast<double>(kLogBinsPerDecade);
  int bin = static_cast<int>(std::floor(position));
  if (bin < 0) bin = 0;
  if (bin > kLogBins - 1) bin = kLogBins - 1;
  // Settle values that land on an edge against the edges themselves, so the
  // reported edges and the assigned bin always agree: edge(bin) <= v < edge(bin+1).
  while (bin > 0 && value < logEdge(bin)) --bin;
  while (bin < kLogBins - 1 && value >= logEdge(bin + 1)) ++bin;
  return kLogFirstBinSlot + bin;
}

// ---- Event energy deposit (MeV), log10 bins from 1 eV to 1 TeV. ----
inline constexpr int kDepositLowExponent = kLogLowExponent;
inline constexpr int kDepositHighExponent = kLogHighExponent;
inline constexpr int kDepositBinsPerDecade = kLogBinsPerDecade;
inline constexpr int kDepositBins = kLogBins;
inline constexpr int kDepositZeroSlot = kLogZeroSlot;
inline constexpr int kDepositUnderflowSlot = kLogUnderflowSlot;
inline constexpr int kDepositFirstBinSlot = kLogFirstBinSlot;
inline constexpr int kDepositOverflowSlot = kLogOverflowSlot;
inline constexpr int kDepositSlots = kLogSlots;

inline double depositEdgeMeV(int bin) { return logEdge(bin); }
inline int depositSlot(double valueMeV) { return logSlot(valueMeV); }

// ---- Event track length (mm, summed over every stepped track), log10 bins
// from 1 nm to 1 km on the same grid. ----
inline double trackLengthEdgeMm(int bin) { return logEdge(bin); }
inline int trackLengthSlot(double valueMm) { return logSlot(valueMm); }

// ---- Secondary multiplicity: exact small counts, then octaves. ----
inline constexpr int kMultiplicityExactBelow = 16;  // 2^4
inline constexpr int kMultiplicityLog2Min = 4;
inline constexpr int kMultiplicityLog2Max = 31;      // overflow at 2^31
inline constexpr int kMultiplicityBins =
    kMultiplicityExactBelow + (kMultiplicityLog2Max - kMultiplicityLog2Min);
inline constexpr int kMultiplicityOverflowSlot = kMultiplicityBins;
inline constexpr int kMultiplicitySlots = kMultiplicityBins + 1;

// Inclusive lower edge of multiplicity bin `bin` (0 .. kMultiplicityBins);
// edge(kMultiplicityBins) = 2^kMultiplicityLog2Max is the overflow threshold.
inline std::int64_t multiplicityEdge(int bin) {
  if (bin <= kMultiplicityExactBelow) {
    return bin;
  }
  return std::int64_t{1} << (kMultiplicityLog2Min + (bin - kMultiplicityExactBelow));
}

inline int multiplicitySlot(double count) {
  if (!std::isfinite(count) || count < 0.0) {
    return kMultiplicityOverflowSlot;
  }
  const double rounded = std::floor(count + 0.5);
  if (rounded >= static_cast<double>(multiplicityEdge(kMultiplicityBins))) {
    return kMultiplicityOverflowSlot;
  }
  const auto n = static_cast<std::int64_t>(rounded);
  if (n < kMultiplicityExactBelow) {
    return static_cast<int>(n);
  }
  int bin = kMultiplicityExactBelow;
  while (bin < kMultiplicityBins - 1 && n >= multiplicityEdge(bin + 1)) ++bin;
  return bin;
}

// First/last bin (inclusive, in bin coordinates of `counts`) holding a
// non-zero count; first > last when every bin is empty. Used to write only the
// populated span.
struct Span {
  int first = 0;
  int last = -1;
};

inline Span populatedSpan(const std::vector<std::int64_t>& counts) {
  Span span;
  span.first = static_cast<int>(counts.size());
  for (int i = 0; i < static_cast<int>(counts.size()); ++i) {
    if (counts[i] != 0) {
      if (i < span.first) span.first = i;
      span.last = i;
    }
  }
  return span;
}

} // namespace event_histogram
} // namespace sim
} // namespace trech
