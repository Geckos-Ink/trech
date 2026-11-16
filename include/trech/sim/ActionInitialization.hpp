#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/sim/EventRecords.hpp"
#include "G4VUserActionInitialization.hh"

#include <memory>

namespace trech {

class TrechActionInitialization : public G4VUserActionInitialization {
public:
  TrechActionInitialization(const TrechConfig& cfg, const RunOptions& options)
      : cfg_(cfg), options_(options), eventRecords_(std::make_shared<EventRecords>(options.outputDir)) {}
  void Build() const override;
  void BuildForMaster() const override;

private:
  TrechConfig cfg_;
  RunOptions options_;
  std::shared_ptr<EventRecords> eventRecords_;
};

} // namespace trech
