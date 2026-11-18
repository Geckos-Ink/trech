#include "trech/ml/DomainDiscovery.hpp"

#include <ATen/ATen.h>
#include <ATen/ops/linalg_eigh.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <utility>

namespace trech::ml {
namespace {

using Projection = std::vector<std::pair<double, std::size_t>>;

struct Split {
  double fraction = 0.0;
  std::size_t left = 0;
  Projection ordered;
};

void consider(Projection points, std::size_t minElements, Split& best,
              double minimumFraction = 0.12) {
  std::sort(points.begin(), points.end());
  const double span = points.back().first - points.front().first;
  if (!(span > 0.0)) return;
  const double resolution = span * 1e-12;
  std::vector<double> spacings;
  for (std::size_t i = 1; i < points.size(); ++i) {
    const double gap = points[i].first - points[i - 1].first;
    if (gap > resolution) spacings.push_back(gap);
  }
  if (spacings.empty()) return;
  const double n = static_cast<double>(points.size());
  // A uniform projection has a largest spacing of order log(n)/n.
  // Also compare with the typical distinct spacing to discount repeated grids.
  double threshold = std::max(minimumFraction, 2.0 * std::log(n) / (n - 1.0));
  if (spacings.size() > 1) {
    const auto median = spacings.begin() + (spacings.size() - 1) / 2;
    std::nth_element(spacings.begin(), median, spacings.end());
    threshold = std::max(threshold, 3.0 * *median / span);
  }
  std::size_t cut = 0;
  double fraction = best.fraction;
  for (std::size_t i = minElements; i <= points.size() - minElements; ++i) {
    const double candidate = (points[i].first - points[i - 1].first) / span;
    if (candidate > threshold && candidate > fraction + 1e-12) {
      fraction = candidate;
      cut = i;
    }
  }
  if (cut) best = {fraction, cut, std::move(points)};
}

Split findSplit(const DomainDiscoveryRequest& request, const std::vector<std::size_t>& rows) {
  const auto width = request.featureCount;
  const auto height = rows.size();
  // Rescale each feature by its extrema before subtraction. This keeps even
  // finite inputs near DBL_MAX in the numerical range of the eigensolver.
  auto features = at::empty({static_cast<int64_t>(width), static_cast<int64_t>(height)},
                            at::TensorOptions().dtype(at::kDouble).device(at::kCPU));
  double* buffer = features.data_ptr<double>();
  std::vector<std::int64_t> varying;
  Split best;
  for (std::size_t f = 0; f < width; ++f) {
    double lo = request.values[rows.front() * width + f];
    double hi = lo;
    for (std::size_t row : rows) {
      const double value = request.values[row * width + f];
      lo = std::min(lo, value);
      hi = std::max(hi, value);
    }
    if (lo == hi) continue;
    varying.push_back(static_cast<std::int64_t>(f));
    const double magnitude = std::max(std::abs(lo), std::abs(hi));
    const double offset = lo / magnitude;
    const double scale = hi / magnitude - offset;
    Projection points;
    points.reserve(height);
    for (std::size_t i = 0; i < height; ++i) {
      const double value = request.values[rows[i] * width + f];
      const double normalized = (value / magnitude - offset) / scale;
      buffer[f * height + i] = normalized;
      points.emplace_back(normalized, rows[i]);
    }
    consider(std::move(points), request.minElements, best);
  }
  if (varying.size() < 2) return best;

  const auto data = features.index_select(0, at::tensor(varying, at::kLong));
  const auto centered = data - data.mean(1, true);
  const auto stddev = centered.square().mean(1, true).sqrt();
  const auto standardized = centered / stddev;
  const auto covariance = standardized.mm(standardized.t()) / static_cast<double>(height);
  const auto [eigenvalues, eigenvectors] = at::linalg_eigh(covariance);
  const auto basis = eigenvectors.t().contiguous();
  const auto projections = basis.mm(standardized).contiguous();
  const double* strengths = eigenvalues.data_ptr<double>();
  const double* directions = basis.data_ptr<double>();
  const double* projected = projections.data_ptr<double>();
  const double tolerance = strengths[varying.size() - 1] * 1e-10;
  for (std::size_t axis = varying.size(); axis-- > 0;) {
    // Tied eigenspaces have no stable axis. Near-null components amplify noise.
    if (strengths[axis] <= tolerance ||
        (axis > 0 && strengths[axis] - strengths[axis - 1] <= tolerance) ||
        (axis + 1 < varying.size() && strengths[axis + 1] - strengths[axis] <= tolerance)) {
      continue;
    }
    const double* direction = directions + axis * varying.size();
    const double* pivot = std::find_if(direction, direction + varying.size(),
                                      [](double v) { return std::abs(v) > 1e-10; });
    const double sign = pivot != direction + varying.size() && *pivot < 0.0 ? -1.0 : 1.0;
    Projection points;
    points.reserve(height);
    for (std::size_t i = 0; i < height; ++i) {
      points.emplace_back(sign * projected[axis * height + i], rows[i]);
    }
    consider(std::move(points), request.minElements, best);
  }
  if (best.left) return best;

  // A nearly isotropic population can hide separated groups on both the raw
  // axes and PCA axes. Try fixed pairwise diagonals as a fallback, with a
  // stronger gap requirement to filter sparse slices of packed populations.
  const double* scaled = standardized.data_ptr<double>();
  for (std::size_t a = 0; a < varying.size(); ++a) {
    for (std::size_t b = a + 1; b < varying.size(); ++b) {
      for (double sign : {1.0, -1.0}) {
        Projection points;
        points.reserve(height);
        for (std::size_t i = 0; i < height; ++i) {
          points.emplace_back(scaled[a * height + i] + sign * scaled[b * height + i], rows[i]);
        }
        consider(std::move(points), request.minElements, best, 0.20);
      }
    }
  }
  return best;
}

void subdivide(const DomainDiscoveryRequest& request, const std::string& parent,
               const std::string& path, const std::vector<std::size_t>& rows,
               DomainDiscovery& result) {
  if (path.size() < request.maxDepth && rows.size() / 2 >= request.minElements) {
    const Split split = findSplit(request, rows);
    if (split.left) {
      std::vector<std::size_t> left, right;
      left.reserve(split.left);
      right.reserve(rows.size() - split.left);
      for (std::size_t i = 0; i < split.ordered.size(); ++i) {
        (i < split.left ? left : right).push_back(split.ordered[i].second);
      }
      subdivide(request, parent, path + '0', left, result);
      subdivide(request, parent, path + '1', right, result);
      return;
    }
  }
  const auto group = static_cast<int>(result.groups.size());
  for (std::size_t row : rows) result.elementGroups[row] = group;
  result.groups.push_back({parent, path, rows.size()});
}

}  // namespace

DomainDiscovery discoverDomains(const DomainDiscoveryRequest& request) {
  const auto width = request.featureCount;
  if (!width || request.values.size() % width || request.minElements < 2 ||
      request.maxDepth > 16) {
    throw std::invalid_argument("invalid domain discovery dimensions or subdivision limits");
  }
  const auto count = request.values.size() / width;
  if (!request.parents.empty() && request.parents.size() != count) {
    throw std::invalid_argument("domain discovery parents must match the element count");
  }
  std::map<std::string, std::vector<std::size_t>> populations;
  for (std::size_t row = 0; row < count; ++row) {
    const double* begin = request.values.data() + row * width;
    if (std::all_of(begin, begin + width, [](double v) { return std::isfinite(v); })) {
      populations[request.parents.empty() ? "" : request.parents[row]].push_back(row);
    }
  }
  DomainDiscovery result;
  result.elementGroups.assign(count, -1);
  for (auto& [parent, rows] : populations) {
    // Make tensor reductions independent of input row order.
    std::sort(rows.begin(), rows.end(), [&](std::size_t a, std::size_t b) {
      const double* first = request.values.data() + a * width;
      const double* second = request.values.data() + b * width;
      return std::lexicographical_compare(first, first + width, second, second + width);
    });
    subdivide(request, parent, "", rows, result);
  }
  return result;
}

}  // namespace trech::ml
