#include "trech/core/ScalarField.hpp"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace trech {
nlohmann::json scalarFieldError(const std::vector<double>& actual,
                               const std::vector<double>& reference, double spacing) {
  if (actual.empty() || actual.size() > 131072 || actual.size() != reference.size() ||
      !std::isfinite(spacing) || spacing <= 0)
    throw std::invalid_argument("Field error requires equal nonempty bounded arrays and positive spacing");
  const double volume = spacing * spacing * spacing;
  const double support = volume * actual.size();
  if (!std::isfinite(support) || support <= 0 || volume <= 0)
    throw std::invalid_argument("Invalid field-error support volume");
  double maximum = 0;
  for (std::size_t i = 0; i < actual.size(); ++i) {
    if (!std::isfinite(actual[i]) || !std::isfinite(reference[i]))
      throw std::invalid_argument("Field error has non-finite values");
    const double difference = actual[i] - reference[i];
    if (!std::isfinite(difference)) throw std::invalid_argument("Field error difference overflow");
    maximum = std::max(maximum, std::abs(difference));
  }
  // Scale before accumulating/squaring, including on platforms where long double
  // has double precision. Finite large and subnormal errors remain representable.
  double sum = 0, square = 0, bias = 0;
  if (maximum > 0) for (std::size_t i = 0; i < actual.size(); ++i) {
    const double scaled = (actual[i] - reference[i]) / maximum;
    sum += std::abs(scaled); square += scaled * scaled; bias += scaled;
  }
  const double l1 = maximum * (sum / actual.size());
  const double l2 = maximum * std::sqrt(square / actual.size());
  const double linf = maximum;
  const double mean = maximum * (bias / actual.size());
  if (!std::isfinite(l1) || !std::isfinite(l2) || !std::isfinite(linf) || !std::isfinite(mean))
    throw std::invalid_argument("Field error norm overflow");
  return {{"cell_count", actual.size()}, {"support_volume", support}, {"l1", l1},
    {"l2", l2}, {"linf", linf}, {"bias", mean},
    {"semantics", "volume-normalized error of co-located cell averages; same units; no interpolation"}};
}
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
