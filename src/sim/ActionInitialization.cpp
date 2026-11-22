#include "trech/sim/ActionInitialization.hpp"

#include "trech/core/Trace.hpp"

#include "trech/sim/EventAction.hpp"
#include "trech/sim/PrimaryGeneratorAction.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/sim/SteppingAction.hpp"
#include "trech/sim/TrackingAction.hpp"

namespace trech {

void TrechActionInitialization::Build() const {
  SetUserAction(new TrechPrimaryGeneratorAction(cfg_.beam));
  SetUserAction(new TrechRunAction(cfg_, options_, eventRecords_, orderedOutput_));
  SetUserAction(new TrechEventAction(cfg_, options_, eventRecords_));
  SetUserAction(new TrechSteppingAction(cfg_));
  // Only when a track hook is registered or the engine trace is on (it then only reads each
  // track for the geant4 tallies; its hooks stay off): other runs keep no tracking action.
  if (registersTrackHook(cfg_) || trace::active()) {
    SetUserAction(new TrechTrackingAction(cfg_));
  }
}

void TrechActionInitialization::BuildForMaster() const {
  SetUserAction(new TrechRunAction(cfg_, options_, eventRecords_, orderedOutput_));
}

} // namespace trech
