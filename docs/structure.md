Below is a **baseline, “boring-but-stable” TRECH C++ skeleton**: repo tree, CMake structure, the embedded JS choice (**QuickJS**), and the **essential Geant4 wiring** (RunManager → DetectorConstruction/PhysicsList/ActionInitialization) that your roadmap already points to.

Note: in this repository, third-party dependencies live under `thirds/` rather than `third_party/` as shown in the example tree below.

---

## 1) Baseline repository tree

Keep early separation between: **core config/provenance**, **JS embedding**, and **Geant4 integration**. (ML, PubChem, chemistry can come later as extra targets.) 

```text
TRECH/
  CMakeLists.txt
  CMakePresets.json
  cmake/
    TrechOptions.cmake
    TrechWarnings.cmake
    TrechFindOrFetch.cmake
  thirds/
    quickjs/                  # vendored QuickJS sources + our tiny CMake wrapper
      CMakeLists.txt
      quickjs/                # upstream quickjs.c/h, libregexp.c/h, ...
    json/                      # nlohmann/json via FetchContent (or vendor)
  include/
    trech/
      core/Config.hpp
      core/Provenance.hpp
      js/JsRuntime.hpp
      sim/GeantRunner.hpp
      sim/DetectorConstruction.hpp
      sim/ActionInitialization.hpp
      sim/SteppingAction.hpp
  src/
    core/
      Config.cpp
      Provenance.cpp
    js/
      JsRuntime.cpp
      TrechJsApi.cpp
    sim/
      GeantRunner.cpp
      DetectorConstruction.cpp
      ActionInitialization.cpp
      PrimaryGeneratorAction.cpp
      RunAction.cpp
      EventAction.cpp
      SteppingAction.cpp
  apps/
    trech-cli/
      main.cpp
  tests/
    CMakeLists.txt
    test_config_roundtrip.cpp
  examples/
    experiments/
      hello_world.js
      water_box.js
```

---

## 2) Dependency choices (practical defaults)

### Embedded JS: **QuickJS**

Why QuickJS here:

* tiny, embeddable, fast start-up
* good modern JS support
* easy to treat JS as “config authoring layer” first (JS → JSON → C++), which is the stable approach you described. 

### Core utilities (minimal set)

* `nlohmann/json` for config parsing/validation
* `spdlog` or minimal `fmt` (optional) for logging/provenance

### Geant4

* keep a “classic Geant4 app skeleton”: `G4RunManagerFactory` + mandatory `SetUserInitialization(...)` objects + actions, as your roadmap stresses. 

---

## 3) Top-level CMake (root `CMakeLists.txt`)

```cmake
cmake_minimum_required(VERSION 3.21)
project(TRECH LANGUAGES C CXX)

include(cmake/TrechOptions.cmake)
include(cmake/TrechWarnings.cmake)
include(cmake/TrechFindOrFetch.cmake)

add_library(trech_core
  src/core/Config.cpp
  src/core/Provenance.cpp
)
target_include_directories(trech_core PUBLIC include)
trech_apply_warnings(trech_core)

add_subdirectory(thirds/quickjs)

add_library(trech_js
  src/js/JsRuntime.cpp
  src/js/TrechJsApi.cpp
)
target_include_directories(trech_js PUBLIC include)
target_link_libraries(trech_js PUBLIC trech_core quickjs)
trech_apply_warnings(trech_js)

# ---- Geant4 integration (optional toggle)
if (TRECH_ENABLE_GEANT4)
  find_package(Geant4 REQUIRED COMPONENTS ui_all vis_all)
  include(${Geant4_USE_FILE})

  add_library(trech_sim
    src/sim/GeantRunner.cpp
    src/sim/DetectorConstruction.cpp
    src/sim/ActionInitialization.cpp
    src/sim/PrimaryGeneratorAction.cpp
    src/sim/RunAction.cpp
    src/sim/EventAction.cpp
    src/sim/SteppingAction.cpp
  )
  target_include_directories(trech_sim PUBLIC include)
  target_link_libraries(trech_sim PUBLIC trech_core ${Geant4_LIBRARIES})
  trech_apply_warnings(trech_sim)
endif()

add_executable(trech apps/trech-cli/main.cpp)
target_link_libraries(trech PRIVATE trech_core trech_js)
if (TRECH_ENABLE_GEANT4)
  target_link_libraries(trech PRIVATE trech_sim)
  target_compile_definitions(trech PRIVATE TRECH_HAS_GEANT4=1)
endif()
trech_apply_warnings(trech)
```

### `cmake/TrechOptions.cmake`

```cmake
option(TRECH_ENABLE_GEANT4 "Build Geant4 simulation layer" ON)
option(TRECH_ENABLE_TORCH  "Build LibTorch ML layer" OFF)
option(TRECH_ENABLE_DNA_CHEM "Enable Geant4-DNA chemistry wiring (when available)" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
```

### `CMakePresets.json` (minimal)

```json
{
  "version": 6,
  "configurePresets": [
    {
      "name": "dev",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/dev",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "TRECH_ENABLE_GEANT4": "ON"
      }
    },
    {
      "name": "rel",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/rel",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "TRECH_ENABLE_GEANT4": "ON"
      }
    }
  ]
}
```

Build:

```bash
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
```

---

## 4) QuickJS as a proper CMake target (`thirds/quickjs/CMakeLists.txt`)

You can vendor upstream sources under `thirds/quickjs/quickjs/`.

```cmake
add_library(quickjs STATIC
  quickjs/quickjs.c
  quickjs/libregexp.c
  quickjs/libunicode.c
  quickjs/cutils.c
)
target_include_directories(quickjs PUBLIC ${CMAKE_CURRENT_LIST_DIR}/quickjs)

# QuickJS wants some feature macros depending on platform; keep it conservative.
if (UNIX AND NOT APPLE)
  target_link_libraries(quickjs PUBLIC m dl pthread)
endif()
```

---

## 5) Core “config-first” contract (C++ types)

### `include/trech/core/Config.hpp`

```cpp
#pragma once
#include <string>
#include <vector>

namespace trech {

struct DetectorConfig {
  double worldSizeMm = 100.0;
  std::string worldMaterial = "G4_WATER";
};

struct BeamConfig {
  std::string particle = "e-";
  double energyMeV = 1.0;
};

struct RunConfig {
  int nEvents = 10;
  uint64_t seed = 12345;
};

struct TrechConfig {
  DetectorConfig detector;
  BeamConfig beam;
  RunConfig run;
};

TrechConfig configFromJsonString(const std::string& json);

} // namespace trech
```

This keeps **JS → JSON** as the stable interface boundary (early on, you avoid binding Geant4 APIs directly into JS, which is exactly the maintainability move you outlined). 

---

## 6) Embedded JS runtime wrapper (QuickJS)

### `include/trech/js/JsRuntime.hpp`

```cpp
#pragma once
#include <string>

namespace trech {

class JsRuntime {
public:
  JsRuntime();
  ~JsRuntime();

  // Evaluate a JS file which must assign global TRECH_CONFIG (stringified JSON)
  std::string evalExperimentAndGetConfigJson(const std::string& path);

private:
  struct Impl;
  Impl* impl_;
};

} // namespace trech
```

### `src/js/JsRuntime.cpp` (essential QuickJS calls)

```cpp
#include "trech/js/JsRuntime.hpp"
#include <stdexcept>
#include <fstream>
#include <sstream>

extern "C" {
#include "quickjs.h"
}

namespace trech {

struct JsRuntime::Impl {
  JSRuntime* rt = nullptr;
  JSContext* ctx = nullptr;
};

static std::string readFile(const std::string& p) {
  std::ifstream f(p);
  if (!f) throw std::runtime_error("Cannot open: " + p);
  std::stringstream ss; ss << f.rdbuf();
  return ss.str();
}

JsRuntime::JsRuntime() : impl_(new Impl) {
  impl_->rt = JS_NewRuntime();
  impl_->ctx = JS_NewContext(impl_->rt);
  if (!impl_->rt || !impl_->ctx) throw std::runtime_error("QuickJS init failed");
}

JsRuntime::~JsRuntime() {
  if (impl_) {
    if (impl_->ctx) JS_FreeContext(impl_->ctx);
    if (impl_->rt)  JS_FreeRuntime(impl_->rt);
    delete impl_;
  }
}

std::string JsRuntime::evalExperimentAndGetConfigJson(const std::string& path) {
  const std::string code = readFile(path);

  JSValue result = JS_Eval(impl_->ctx, code.c_str(), code.size(), path.c_str(),
                           JS_EVAL_TYPE_GLOBAL);
  if (JS_IsException(result)) {
    JSValue exc = JS_GetException(impl_->ctx);
    const char* msg = JS_ToCString(impl_->ctx, exc);
    std::string err = msg ? msg : "JS exception";
    if (msg) JS_FreeCString(impl_->ctx, msg);
    JS_FreeValue(impl_->ctx, exc);
    JS_FreeValue(impl_->ctx, result);
    throw std::runtime_error(err);
  }
  JS_FreeValue(impl_->ctx, result);

  JSValue global = JS_GetGlobalObject(impl_->ctx);
  JSValue cfg = JS_GetPropertyStr(impl_->ctx, global, "TRECH_CONFIG");
  JS_FreeValue(impl_->ctx, global);

  if (JS_IsUndefined(cfg)) {
    JS_FreeValue(impl_->ctx, cfg);
    throw std::runtime_error("Experiment must define global TRECH_CONFIG (JSON string).");
  }

  const char* s = JS_ToCString(impl_->ctx, cfg);
  std::string out = s ? s : "";
  if (s) JS_FreeCString(impl_->ctx, s);
  JS_FreeValue(impl_->ctx, cfg);
  return out;
}

} // namespace trech
```

---

## 7) Geant4 “disposition” (canonical wiring)

Your roadmap’s stability rule is exactly right: wire Geant4 in the intended lifecycle order: **RunManager → DetectorConstruction + PhysicsList + ActionInitialization → Initialize → BeamOn**. 

### `include/trech/sim/GeantRunner.hpp`

```cpp
#pragma once
#include "trech/core/Config.hpp"

namespace trech {
int runGeant4(const TrechConfig& cfg, int argc, char** argv);
}
```

### `src/sim/GeantRunner.cpp` (minimal main loop)

```cpp
#include "trech/sim/GeantRunner.hpp"
#include "trech/sim/DetectorConstruction.hpp"
#include "trech/sim/ActionInitialization.hpp"

#include "G4RunManagerFactory.hh"
#include "G4UImanager.hh"
#include "G4UIExecutive.hh"
#include "G4VisExecutive.hh"
#include "G4PhysListFactory.hh"
#include "G4VModularPhysicsList.hh"

namespace trech {

int runGeant4(const TrechConfig& cfg, int argc, char** argv) {
  auto* runManager = G4RunManagerFactory::CreateRunManager();

  runManager->SetUserInitialization(new TrechDetectorConstruction(cfg.detector));

  // Start stable: use a reference list (e.g., QBBC), customize later.
  G4PhysListFactory factory;
  G4VModularPhysicsList* phys = factory.GetReferencePhysList("QBBC");
  runManager->SetUserInitialization(phys);

  runManager->SetUserInitialization(new TrechActionInitialization(cfg));

  // UI / batch
  G4UIExecutive* ui = (argc == 1) ? new G4UIExecutive(argc, argv) : nullptr;
  G4VisManager* vis = nullptr;

  if (ui) {
    vis = new G4VisExecutive();
    vis->Initialize();
  }

  runManager->Initialize();

  auto* UImanager = G4UImanager::GetUIpointer();
  if (ui) {
    UImanager->ApplyCommand("/control/execute init_vis.mac");
    ui->SessionStart();
    delete ui;
    delete vis;
  } else {
    // e.g. trech run exp.js --macro run.mac
    // you can parse argv and execute the given macro here.
    UImanager->ApplyCommand("/run/beamOn " + std::to_string(cfg.run.nEvents));
  }

  delete runManager;
  return 0;
}

} // namespace trech
```

---

## 8) Mandatory user classes (thin skeletons)

### DetectorConstruction (world volume)

```cpp
// include/trech/sim/DetectorConstruction.hpp
#pragma once
#include "trech/core/Config.hpp"
#include "G4VUserDetectorConstruction.hh"

class G4VPhysicalVolume;

namespace trech {
class TrechDetectorConstruction : public G4VUserDetectorConstruction {
public:
  explicit TrechDetectorConstruction(const trech::DetectorConfig& cfg) : cfg_(cfg) {}
  G4VPhysicalVolume* Construct() override;
private:
  trech::DetectorConfig cfg_;
};
}
```

```cpp
// src/sim/DetectorConstruction.cpp
#include "trech/sim/DetectorConstruction.hpp"
#include "G4NistManager.hh"
#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"

namespace trech {

G4VPhysicalVolume* TrechDetectorConstruction::Construct() {
  auto* nist = G4NistManager::Instance();
  auto* mat = nist->FindOrBuildMaterial(cfg_.worldMaterial);

  const auto half = 0.5 * cfg_.worldSizeMm * mm;
  auto* solidWorld = new G4Box("World", half, half, half);
  auto* logicWorld = new G4LogicalVolume(solidWorld, mat, "World");
  auto* physWorld  = new G4PVPlacement(nullptr, {}, logicWorld, "World", nullptr, false, 0);

  return physWorld;
}

} // namespace trech
```

### ActionInitialization (register Run/Event/Stepping, etc.)

```cpp
// include/trech/sim/ActionInitialization.hpp
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
}
```

```cpp
// src/sim/ActionInitialization.cpp
#include "trech/sim/ActionInitialization.hpp"
#include "trech/sim/PrimaryGeneratorAction.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/sim/EventAction.hpp"
#include "trech/sim/SteppingAction.hpp"

namespace trech {

void TrechActionInitialization::Build() const {
  SetUserAction(new TrechPrimaryGeneratorAction(cfg_.beam));
  SetUserAction(new TrechRunAction(cfg_));
  SetUserAction(new TrechEventAction());
  SetUserAction(new TrechSteppingAction(/* later: injection collector */));
}

} // namespace trech
```

### SteppingAction (your future “chemistry injection” bridge)

This is the stable hook for “step → compact record” that your roadmap calls out. 

```cpp
// src/sim/SteppingAction.cpp
#include "trech/sim/SteppingAction.hpp"
#include "G4Step.hh"
#include "G4Track.hh"

namespace trech {

void TrechSteppingAction::UserSteppingAction(const G4Step* step) {
  const auto* track = step->GetTrack();
  const auto edep = step->GetTotalEnergyDeposit();
  if (edep <= 0) return;

  const auto& pos = track->GetPosition();
  const auto time = track->GetGlobalTime();

  // TODO: push into a compact injection stream:
  // Injection{ time, pos, edep, trackID, parentID, particle, volume/material id }
}

} // namespace trech
```

---

## 9) CLI: glue JS → config → Geant4

### `apps/trech-cli/main.cpp`

```cpp
#include "trech/js/JsRuntime.hpp"
#include "trech/core/Config.hpp"

#ifdef TRECH_HAS_GEANT4
#include "trech/sim/GeantRunner.hpp"
#endif

#include <iostream>

int main(int argc, char** argv) {
  if (argc < 3 || std::string(argv[1]) != "run") {
    std::cerr << "Usage: trech run <experiment.js>\n";
    return 2;
  }

  trech::JsRuntime js;
  const std::string cfgJson = js.evalExperimentAndGetConfigJson(argv[2]);
  trech::TrechConfig cfg = trech::configFromJsonString(cfgJson);

#ifdef TRECH_HAS_GEANT4
  return trech::runGeant4(cfg, argc, argv);
#else
  std::cout << "Config parsed OK (Geant4 disabled)\n";
  return 0;
#endif
}
```

---

## 10) Example experiment JS (`examples/experiments/hello_world.js`)

```js
// JS is just “authoring”; it emits JSON for the C++ runtime.
const cfg = {
  detector: { worldSizeMm: 100.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 1.0 },
  run: { nEvents: 10, seed: 12345 }
};

// Contract: define global TRECH_CONFIG as JSON string
globalThis.TRECH_CONFIG = JSON.stringify(cfg);
```

---

### What this gives you immediately

* A **repeatable build** (CMake presets)
* A **stable API boundary** (JS → JSON → C++)
* The **canonical Geant4 lifecycle** with the mandatory initialization objects and action hooks you already identified as the maintainable approach. 

If you want, next step I can extend this skeleton with:

* a tiny **provenance JSONL writer** (seed, Geant4 version string, config hash),
* a first **“dose/edep scorer”** path (multi-functional detector) instead of step-logging,
* and the toggles for **Geant4-DNA chemistry** wiring behind `TRECH_ENABLE_DNA_CHEM`. 
