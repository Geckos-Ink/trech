#pragma once

#include <string>

namespace trech::hookfailure {

// Process-wide latch for the first scenario hook that threw during a Geant4 run.
//
// A JavaScript hook that throws on a Geant4 worker task cannot unwind into the run
// manager: the task ends and the master waits for it forever. The dispatch site records the
// failure here instead, ends the event loop, and dispatches no further hooks; the runner reports
// it after BeamOn returns, so `trech run` exits with the hook's own message.
//
// Thread-safe. Only the first failure is kept (later hooks see the latch and do not run).

// Record a failure. Returns true when this call is the first one recorded.
bool record(const std::string& hookName, const std::string& message);
bool failed();
// "hook <name> threw: <message>", or "" when nothing failed.
std::string describe();
// Clear the latch before a run starts (a lab kernel runs several batches).
void reset();

} // namespace trech::hookfailure
