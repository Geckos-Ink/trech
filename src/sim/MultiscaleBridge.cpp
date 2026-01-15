#include "trech/sim/MultiscaleBridge.hpp"

namespace trech::sim {

MultiscaleBridge::MultiscaleBridge(const MultiscaleConfig& cfg) : cfg_(cfg) {}

MultiscaleStatus MultiscaleBridge::Configure() {
  MultiscaleStatus status;
  status.enabled = cfg_.enable;
  status.method = cfg_.method;
  status.mode = cfg_.mode;
  status.status = cfg_.enable ? "stub_configured" : "disabled";
  return status;
}

} // namespace trech::sim
