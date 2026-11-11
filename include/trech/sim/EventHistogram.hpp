#pragma once

// Fixed-binning histograms of per-event scalars (the event energy deposit and
// the event's secondary multiplicity). The bin layout is fixed before the run,
// so worker threads fill integer counts that merge by plain addition: the
// merged histogram is independent of worker count and merge order, unlike a
// floating-point sum.
//
// These are descriptive tallies of what Geant4 sampled (a system observable),
// never a fitted or assumed distribution. Pure and Geant4-free so the binning
// can be unit tested without a transport build.
//
// Slot layout of the deposit histogram:
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

// ---- Event energy deposit (MeV), log10 bins from 1 eV to 1 TeV. ----
inline constexpr int kDepositLowExponent = -6;
inline constexpr int kDepositHighExponent = 6;
inline constexpr int kDepositBinsPerDecade = 10;
inline constexpr int kDepositBins =
    (kDepositHighExponent - kDepositLowExponent) * kDepositBinsPerDecade;
inline constexpr int kDepositZeroSlot = 0;
inline constexpr int kDepositUnderflowSlot = 1;
inline constexpr int kDepositFirstBinSlot = 2;
inline constexpr int kDepositOverflowSlot = kDepositFirstBinSlot + kDepositBins;
inline constexpr int kDepositSlots = kDepositOverflowSlot + 1;

// Lower edge of log bin `bin` (0 .. kDepositBins); edge(kDepositBins) is the
// high edge. Computed from an integer exponent numerator so every caller gets
// identical edges.
inline double depositEdgeMeV(int bin) {
  return std::pow(10.0, static_cast<double>(kDepositLowExponent * kDepositBinsPerDecade + bin) /
                            static_cast<double>(kDepositBinsPerDecade));
}

inline int depositSlot(double valueMeV) {
  if (valueMeV == 0.0) {
    return kDepositZeroSlot;
  }
  if (!std::isfinite(valueMeV)) {
    return kDepositOverflowSlot;
  }
  if (valueMeV < depositEdgeMeV(0)) {
    return kDepositUnderflowSlot;
  }
  if (valueMeV >= depositEdgeMeV(kDepositBins)) {
    return kDepositOverflowSlot;
  }
  const double position =
      (std::log10(valueMeV) - static_cast<double>(kDepositLowExponent)) *
      static_cast<double>(kDepositBinsPerDecade);
  int bin = static_cast<int>(std::floor(position));
  if (bin < 0) bin = 0;
  if (bin > kDepositBins - 1) bin = kDepositBins - 1;
  // Settle values that land on an edge against the edges themselves, so the
  // reported edges and the assigned bin always agree: edge(bin) <= v < edge(bin+1).
  while (bin > 0 && valueMeV < depositEdgeMeV(bin)) --bin;
  while (bin < kDepositBins - 1 && valueMeV >= depositEdgeMeV(bin + 1)) ++bin;
  return kDepositFirstBinSlot + bin;
}

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
