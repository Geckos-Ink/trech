#include "trech/core/ScalarField.hpp"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace trech {
nlohmann::json scalarFieldStatistics(const std::vector<double>& values, double spacing) {
  if (values.empty() || values.size() > 131072 || !std::isfinite(spacing) || spacing <= 0)
    throw std::invalid_argument("Scalar field requires 1..131072 values and finite positive spacing");
  const double volume = spacing * spacing * spacing;
  if (!std::isfinite(volume) || volume <= 0) throw std::invalid_argument("Invalid voxel volume");
  double integral = 0, absolute = 0, positive = 0, negative = 0;
  auto magnitude = values;
  for (std::size_t i = 0; i < values.size(); ++i) {
    const auto v = values[i];
    if (!std::isfinite(v)) throw std::invalid_argument("Scalar field has non-finite values");
    integral += v * volume; absolute += std::abs(v) * volume;
    positive += std::max(0., v) * volume; negative += std::max(0., -v) * volume;
    magnitude[i] = std::abs(v);
  }
  if (!std::isfinite(absolute)) throw std::invalid_argument("Scalar field integral overflow");
  std::sort(magnitude.begin(), magnitude.end(), std::greater<double>());
  auto levels = nlohmann::json::array();
  std::size_t next = 0;
  double enclosed = 0;
  if (absolute > 0) for (int percentile = 1; percentile <= 99; ++percentile) {
    const auto target = absolute * (percentile / 100.);
    while (next < magnitude.size() && (next == 0 || enclosed < target)) enclosed += magnitude[next++] * volume;
    const auto threshold = magnitude[next-1];
    // Include the whole threshold tie: the reported fraction matches the mask.
    while (next < magnitude.size() && magnitude[next] == threshold) enclosed += magnitude[next++] * volume;
    levels.push_back({{"fraction", percentile / 100.}, {"threshold", threshold},
      {"enclosed_fraction", enclosed / absolute}, {"voxel_count", next}});
  }
  const auto bounds = std::minmax_element(values.begin(), values.end());
  return {{"integral", integral}, {"absolute_integral", absolute}, {"positive_integral", positive},
    {"negative_integral", negative}, {"minimum", *bounds.first}, {"maximum", *bounds.second},
    {"mass_levels", levels}, {"semantics", "finite cell-grid quadrature; absolute-value ranking for signed fields; no renormalization"}};
}
}
