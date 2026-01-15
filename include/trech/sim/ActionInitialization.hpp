#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "G4VUserActionInitialization.hh"

namespace trech {

class TrechActionInitialization : public G4VUserActionInitialization {
public:
  TrechActionInitialization(const TrechConfig& cfg, const RunOptions& options)
      : cfg_(cfg), options_(options) {}
  void Build() const override;
  void BuildForMaster() const override;

private:
  TrechConfig cfg_;
  RunOptions options_;
};

} // namespace trech
