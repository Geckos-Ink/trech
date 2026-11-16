#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/sim/EventRecords.hpp"
#include "G4VUserActionInitialization.hh"

#include <memory>

namespace trech {

class TrechActionInitialization : public G4VUserActionInitialization {
public:
  TrechActionInitialization(const TrechConfig& cfg, const RunOptions& options, bool orderedOutput)
      : cfg_(cfg), options_(options), orderedOutput_(orderedOutput),
        eventRecords_(std::make_shared<EventRecords>(options.outputDir)) {}
  void Build() const override;
  void BuildForMaster() const override;

private:
  TrechConfig cfg_;
  RunOptions options_;
  bool orderedOutput_;
  std::shared_ptr<EventRecords> eventRecords_;
};

} // namespace trech
