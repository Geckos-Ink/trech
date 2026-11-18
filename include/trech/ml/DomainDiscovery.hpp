#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace trech::ml {

enum class DomainDiscoveryMethod { Projected, Density };

struct DomainDiscoveryRequest {
  std::size_t featureCount = 0;
  std::vector<double> values;  // element-major, features in a fixed order
  std::vector<std::string> parents;  // optional routing ids, one per element
  std::size_t minElements = 16;
  std::size_t maxDepth = 3;
  DomainDiscoveryMethod method = DomainDiscoveryMethod::Projected;
  bool sharedDistanceScale = false;  // preserve geometry in common units
};

struct DetectedDomain {
  std::string parent;
  std::string path;  // local to this batch and parent
  std::size_t elements = 0;
};

struct DomainDiscovery {
  std::vector<DetectedDomain> groups;
  std::vector<int> elementGroups;  // indices into groups, -1 for non-finite rows
};

// Find projected gaps or connected components of a local distance graph.
// Membership is diagnostic and never changes operator selection or state.
DomainDiscovery discoverDomains(const DomainDiscoveryRequest& request);

}  // namespace trech::ml
