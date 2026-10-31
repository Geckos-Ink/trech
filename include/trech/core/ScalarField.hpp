#pragma once
#include <nlohmann/json_fwd.hpp>
#include <vector>
namespace trech {
// Numerical diagnostics only: finite regular-grid integrals and |value|-ranked
// enclosed mass thresholds. No physical model or normalization is introduced.
nlohmann::json scalarFieldStatistics(const std::vector<double>& values, double spacing);
// Co-located cell averages in the same units/support. No interpolation, relative
// normalization or claim of physical accuracy is supplied by this diagnostic.
nlohmann::json scalarFieldError(const std::vector<double>& actual,
                              const std::vector<double>& reference, double spacing);
}
