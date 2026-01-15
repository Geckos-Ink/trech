#pragma once

#include "trech/core/Config.hpp"

#include <string>

namespace trech::sim {

struct MultiscaleStatus {
  bool enabled = false;
  std::string method;
  std::string mode;
  std::string status;
};

class MultiscaleBridge {
public:
  explicit MultiscaleBridge(const MultiscaleConfig& cfg);

  MultiscaleStatus Configure();

private:
  MultiscaleConfig cfg_;
};

} // namespace trech::sim
