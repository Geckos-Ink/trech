#include "trech/sim/ExactSum.hpp"

#include <cmath>
#include <initializer_list>
#include <iostream>
#include <limits>

using trech::sim::ExactSum;

double sum(std::initializer_list<double> values) {
  ExactSum total;
  for (double value : values) total.add(value);
  return total.value();
}

int main() {
  const double tiny = std::numeric_limits<double>::denorm_min();
  const double largest = std::numeric_limits<double>::max();
  const double halfUlp = std::ldexp(1.0, -53);
  const double next = std::nextafter(1.0, 2.0);
  const double infinity = std::numeric_limits<double>::infinity();
  const double nan = std::numeric_limits<double>::quiet_NaN();
  if (sum({1.0, halfUlp}) != 1.0 ||
      sum({next, halfUlp}) != std::nextafter(next, 2.0) ||
      sum({1.0, halfUlp, tiny}) != next ||
      sum({2.0, -halfUlp}) != 2.0 ||
      sum({2.0, -halfUlp, -tiny}) != std::nextafter(2.0, 1.0) ||
      sum({largest, largest, -largest}) != largest ||
      sum({largest, tiny, -largest, tiny}) != 2 * tiny ||
      sum({-largest, -tiny, largest}) != -tiny ||
      sum({std::numeric_limits<double>::min(), -tiny}) !=
          std::nextafter(std::numeric_limits<double>::min(), 0.0) ||
      std::signbit(sum({1.0, -1.0, -0.0})) ||
      sum({largest, largest}) != infinity ||
      sum({-largest, -largest}) != -infinity ||
      sum({-infinity, 1.0}) != -infinity ||
      !std::isnan(sum({infinity, -infinity})) ||
      !std::isnan(sum({infinity, nan}))) {
    std::cerr << "Incorrect rounding, cancellation, or nonfinite result\n";
    return 1;
  }

  ExactSum a, b, c;
  a.add(largest);
  a.add(largest);
  b.add(-largest);
  c.add(-largest);
  c.add(-3.25);
  auto reversed = c;
  reversed.merge(b);
  reversed.merge(a);
  a.merge(b);
  a.merge(c);
  if (a.value() != -3.25 || reversed.value() != a.value()) {
    std::cerr << "Worker merge lost information or depended on order\n";
    return 1;
  }
}
