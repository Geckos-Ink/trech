#include "trech/sim/ActionInitialization.hpp"

#include "trech/sim/EventAction.hpp"
#include "trech/sim/PrimaryGeneratorAction.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/sim/SteppingAction.hpp"

namespace trech {

void TrechActionInitialization::Build() const {
  SetUserAction(new TrechPrimaryGeneratorAction(cfg_.beam));
  SetUserAction(new TrechRunAction(cfg_, options_));
  SetUserAction(new TrechEventAction(cfg_, options_));
  SetUserAction(new TrechSteppingAction(cfg_));
}

void TrechActionInitialization::BuildForMaster() const {
  SetUserAction(new TrechRunAction(cfg_, options_));
}

} // namespace trech
