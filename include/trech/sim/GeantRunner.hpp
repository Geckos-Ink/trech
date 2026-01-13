#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"

namespace trech {
int runGeant4(const TrechConfig& cfg, RunOptions options, int argc, char** argv);
}
