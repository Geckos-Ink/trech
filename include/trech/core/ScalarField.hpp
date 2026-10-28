#pragma once
#include <nlohmann/json_fwd.hpp>
#include <vector>
namespace trech {
// Numerical diagnostics only: finite regular-grid integrals and |value|-ranked
// enclosed mass thresholds. No physical model or normalization is introduced.
nlohmann::json scalarFieldStatistics(const std::vector<double>& values, double spacing);
}
