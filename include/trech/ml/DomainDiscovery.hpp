#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace trech::ml {

struct DomainDiscoveryRequest {
  std::size_t featureCount = 0;
  std::vector<double> values;  // element-major, features in a fixed order
  std::vector<std::string> parents;  // optional routing ids, one per element
  std::size_t minElements = 16;
  std::size_t maxDepth = 3;
};

struct DetectedDomain {
  std::string parent;
  std::string path;  // binary split decisions within parent, local to this batch
  std::size_t elements = 0;
};

struct DomainDiscovery {
  std::vector<DetectedDomain> groups;
  std::vector<int> elementGroups;  // indices into groups, -1 for non-finite rows
};

// Find gaps on original features and on standardized principal components.
// Membership is diagnostic and never changes operator selection or state.
DomainDiscovery discoverDomains(const DomainDiscoveryRequest& request);

}  // namespace trech::ml
