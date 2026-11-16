#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <limits>

namespace trech::sim {

// Sum IEEE binary64 inputs as integers in units of the smallest subnormal.
// The limbs leave room for more than 2^64 maximum finite inputs of each sign.
// Round once to nearest, ties to even, after the last merge.
class ExactSum {
public:
  void add(double value) {
    static_assert(sizeof(double) == sizeof(std::uint64_t) &&
                  std::numeric_limits<double>::is_iec559 &&
                  std::numeric_limits<double>::digits == 53);
    std::uint64_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    const bool negative = (bits >> 63) != 0;
    const auto exponent = static_cast<unsigned>((bits >> 52) & 0x7ff);
    const std::uint64_t fraction = bits & ((std::uint64_t{1} << 52) - 1);
    if (exponent == 0x7ff) {
      nonfinite_ |= fraction ? kNaN : (negative ? kNegativeInfinity : kPositiveInfinity);
      return;
    }
    if (exponent == 0 && fraction == 0) return;

    const std::uint64_t significand = exponent ? fraction | (std::uint64_t{1} << 52) : fraction;
    const unsigned shift = exponent ? exponent - 1 : 0;
    auto& words = negative ? negative_ : positive_;
    addAt(words, shift / 32, (significand & 0xffffffff) << (shift % 32));
    addAt(words, shift / 32 + 1, (significand >> 32) << (shift % 32));
  }

  void merge(const ExactSum& other) {
    mergeWords(positive_, other.positive_);
    mergeWords(negative_, other.negative_);
    nonfinite_ |= other.nonfinite_;
  }

  double value() const {
    if ((nonfinite_ & kNaN) || nonfinite_ == (kPositiveInfinity | kNegativeInfinity)) {
      return std::numeric_limits<double>::quiet_NaN();
    }
    if (nonfinite_ & kPositiveInfinity) return std::numeric_limits<double>::infinity();
    if (nonfinite_ & kNegativeInfinity) return -std::numeric_limits<double>::infinity();

    const bool negative = std::lexicographical_compare(
        positive_.rbegin(), positive_.rend(), negative_.rbegin(), negative_.rend());
    const auto& larger = negative ? negative_ : positive_;
    const auto& smaller = negative ? positive_ : negative_;
    Words magnitude;
    std::uint64_t borrow = 0;
    for (std::size_t i = 0; i < magnitude.size(); ++i) {
      const std::uint64_t subtrahend = std::uint64_t{smaller[i]} + borrow;
      magnitude[i] = static_cast<std::uint32_t>(larger[i] - subtrahend);
      borrow = larger[i] < subtrahend;
    }

    int high = static_cast<int>(magnitude.size() * 32) - 1;
    while (high >= 0 && !bit(magnitude, high)) --high;
    if (high < 0) return 0.0;

    const int shift = std::max(0, high - 52);
    std::uint64_t significand = 0;
    for (int i = high; i >= shift; --i) {
      significand = (significand << 1) | bit(magnitude, i);
    }
    if (shift > 0 && bit(magnitude, shift - 1)) {
      bool sticky = false;
      for (int i = (shift - 1) / 32 - 1; i >= 0 && !sticky; --i) {
        sticky = magnitude[static_cast<std::size_t>(i)] != 0;
      }
      const auto mask = (std::uint32_t{1} << ((shift - 1) % 32)) - 1;
      sticky = sticky || (magnitude[static_cast<std::size_t>((shift - 1) / 32)] & mask) != 0;
      if (sticky || (significand & 1)) ++significand;
    }
    if (significand == (std::uint64_t{1} << 53)) {
      significand >>= 1;
      ++high;
    }
    const auto exponent = static_cast<std::uint64_t>(std::clamp(high - 51, 0, 0x7ff));
    const std::uint64_t fraction = exponent == 0x7ff ? 0 :
        significand & ((std::uint64_t{1} << 52) - 1);
    const std::uint64_t bits = (std::uint64_t{negative} << 63) | (exponent << 52) | fraction;
    double rounded;
    std::memcpy(&rounded, &bits, sizeof(rounded));
    return rounded;
  }

private:
  using Words = std::array<std::uint32_t, 68>;
  enum { kNaN = 1, kPositiveInfinity = 2, kNegativeInfinity = 4 };

  static void addAt(Words& words, std::size_t i, std::uint64_t value) {
    while (value != 0 && i < words.size()) {
      const std::uint64_t sum = std::uint64_t{words[i]} + (value & 0xffffffff);
      words[i++] = static_cast<std::uint32_t>(sum);
      value = (value >> 32) + (sum >> 32);
    }
  }

  static void mergeWords(Words& target, const Words& source) {
    std::uint64_t carry = 0;
    for (std::size_t i = 0; i < target.size(); ++i) {
      const std::uint64_t sum = std::uint64_t{target[i]} + source[i] + carry;
      target[i] = static_cast<std::uint32_t>(sum);
      carry = sum >> 32;
    }
  }

  static bool bit(const Words& words, int i) {
    return (words[static_cast<std::size_t>(i / 32)] >> (i % 32)) & 1;
  }

  Words positive_{};
  Words negative_{};
  unsigned nonfinite_ = 0;
};

} // namespace trech::sim
