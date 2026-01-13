#include "trech/sim/ActionInitialization.hpp"

#include "trech/sim/EventAction.hpp"
#include "trech/sim/PrimaryGeneratorAction.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/sim/SteppingAction.hpp"

namespace trech {

void TrechActionInitialization::Build() const {
  SetUserAction(new TrechPrimaryGeneratorAction(cfg_.beam));
  SetUserAction(new TrechRunAction(cfg_));
  SetUserAction(new TrechEventAction());
  SetUserAction(new TrechSteppingAction());
}

} // namespace trech
