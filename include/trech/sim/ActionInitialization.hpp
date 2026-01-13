#pragma once

#include "trech/core/Config.hpp"
#include "G4VUserActionInitialization.hh"

namespace trech {

class TrechActionInitialization : public G4VUserActionInitialization {
public:
  explicit TrechActionInitialization(const TrechConfig& cfg) : cfg_(cfg) {}
  void Build() const override;

private:
  TrechConfig cfg_;
};

} // namespace trech
