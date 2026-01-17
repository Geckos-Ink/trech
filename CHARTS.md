# CHARTS

Mermaid diagrams that capture TRECH dataflow, Geant4 wiring, outputs, and the
future stratification/prediction loop. Keep these in sync with runtime behavior
and config/output schema changes.

## End-to-end workflow (JS -> JSON -> Geant4 -> outputs)

```mermaid
flowchart LR
  subgraph Authoring
    JS["JS experiment file"] -->|writes| CFG["TRECH_CONFIG JSON string"]
  end
  subgraph Runtime
    CLI["trech run ..."] --> OV["CLI overrides\nseed/events/output"]
    CFG --> PARSE["Config parser"]
    OV --> PARSE
  end
  subgraph Geant4
    PARSE --> RM["G4RunManager"]
    RM --> DET["G4VUserDetectorConstruction"]
    RM --> PHY["G4VModularPhysicsList"]
    RM --> ACT["G4VUserActionInitialization"]
    RM --> INIT["Initialize"]
    INIT --> BEAM["BeamOn"]
  end
  BEAM --> SCORE["Scoring + feature capture"]
  BEAM --> PROV["Provenance capture"]
  SCORE --> OUT1["trech_scores.jsonl"]
  SCORE --> OUT2["trech_event_scores.jsonl\n(stratify.enable)"]
  SCORE --> OUT3["trech_event_features.jsonl\n(stratify.dumpFeatures)"]
  SCORE --> OUT4["trech_resim_queue.jsonl\n(stratify.dumpResimQueue)"]
  PROV --> OUT5["trech_provenance.jsonl"]
```

## Geant4 lifecycle wiring (canonical order)

```mermaid
sequenceDiagram
  participant CLI as trech CLI
  participant QJS as QuickJS
  participant CFG as Config loader
  participant RM as G4RunManager
  participant DET as DetectorConstruction
  participant PHY as PhysicsList
  participant ACT as ActionInitialization
  CLI->>QJS: execute JS experiment
  QJS->>CFG: provide TRECH_CONFIG JSON
  CLI->>CFG: apply overrides (seed/events/output)
  CFG->>RM: build and configure
  RM->>DET: Construct()
  RM->>PHY: ConstructProcess()
  RM->>ACT: Build()
  RM->>RM: Initialize()
  RM->>RM: BeamOn(nEvents)
```

## Detector + physics assembly (optics + DNA path)

```mermaid
flowchart TB
  CFG["Config detector + optics + chemistry"] --> DETB["Detector builder"]
  DETB --> GEO["Water box geometry\n+ CNT stub (optional)"]
  DETB --> ENV["Environment: temperature/pressure"]
  DETB --> MAT["Materials + properties\n(constant or spectral optics)"]
  CFG --> OPT{optics.enable?}
  CFG --> CHEM{chemistry.enable?}
  OPT -- no --> PHYBASE["Base physics list (QBBC)"]
  OPT -- yes --> OPTPHYS["G4OpticalPhysics"]
  OPTPHYS --> PHYBASE
  CHEM -- yes --> DNAPHYS["Replace EM with\nG4EmDNAPhysics (option)"]
  CHEM -- yes --> DNACHEM["Register G4EmDNAChemistry\n(solver != stub)"]
  DNAPHYS --> PHYBASE
  DNACHEM --> PHYBASE
  OPTPHYS --> OP["Optical processes:\nscattering/absorption/refraction"]
  MAT --> OP
  GEO --> SD["Scoring volumes"]
  OP --> SD
```

## Outputs + provenance (JSONL artifacts)

```mermaid
flowchart LR
  RUN["Geant4 run"] --> SCORING["Scoring summaries"]
  RUN --> PROV["Provenance record"]
  SCORING --> S1["trech_scores.jsonl\n(run summaries + CNT observables + DNA/stratify flags)"]
  SCORING --> S2["trech_event_scores.jsonl\n(stratify.enable)"]
  SCORING --> S3["trech_event_features.jsonl\n(stratify.dumpFeatures)"]
  SCORING --> S4["trech_resim_queue.jsonl\n(stratify.dumpResimQueue)"]
  PROV --> P1["trech_provenance.jsonl"]
```

## System aggregation (point-agnostic ensemble layer)

```mermaid
flowchart LR
  RUN["Geant4 run"] --> SCORE["Run-level totals\n(energy, photons, counts)"]
  SCORE --> SYS["System aggregation\n(point-agnostic densities)"]
  SYS --> OUTS["trech_scores.jsonl\nsystem_* fields"]
  SYS --> ML["ML/ROM scaling\n(TorchScript)"]
```

## Event stratification + prediction loop (future-facing)

```mermaid
flowchart LR
  EVENTS["Event-level features"] --> SCORE["Event scoring"]
  SCORE --> THR["Thresholds + labels\n(stratify.*)"]
  THR --> CLASS["Predictable vs exceptional"]
  CLASS --> RESIM["Resim queue\n(trech_resim_queue.jsonl)"]
  CLASS --> STATS["Aggregate stats\n(distributions, moments)"]
  STATS --> MODEL["TorchScript inference\n(TRECH_ENABLE_TORCH + stratify.modelPath)"]
  MODEL --> PRED["Predicted phenomena"]
  PRED --> COMP["Compare vs observed"]
  COMP --> THR
```

## Scale-up ML loop (Geant4 -> Torch training -> inference gate)

```mermaid
flowchart LR
  SIM["High-fidelity Geant4 runs\n(H2O/CNT scenarios)"] --> FEAT["Event features + run scores\n(JSONL outputs)"]
  FEAT --> DATA["Dataset builder\n(normalize/aggregate/label)"]
  DATA --> TRAIN["Torch training/finetuning\n(export TorchScript)"]
  TRAIN --> VALID["Accuracy + coverage gates\n(compare vs Geant4)"]
  VALID -- pass --> DEPLOY["Deploy TorchScript model\n(stratify.modelPath)"]
  VALID -- fail --> SIM
  DEPLOY --> INFER["Runtime inference\n(rapid surrogate)"]
  INFER --> CONF{"Confidence OK?"}
  CONF -- yes --> PRED["Use prediction\n(lower zoom)"]
  CONF -- no --> RESIM["Queue resim\n(Geant4)"]
  RESIM --> FEAT
```

## TRECH -> Geant4 API mapping (where APIs are leveraged)

```mermaid
flowchart LR
  subgraph Trech
    T1["DetectorConstruction"]
    T2["PhysicsList"]
    T3["ActionInitialization"]
    T4["PrimaryGenerator"]
    T5["RunAction"]
    T6["EventAction"]
    T7["SteppingAction"]
    T8["CLI macros/UI"]
  end
  subgraph Geant4
    G1["G4VUserDetectorConstruction"]
    G2["G4VModularPhysicsList"]
    G3["G4VUserActionInitialization"]
    G4["G4VUserPrimaryGeneratorAction"]
    G5["G4UserRunAction"]
    G6["G4UserEventAction"]
    G7["G4UserSteppingAction"]
    G8["G4UImanager / UI session"]
  end
  T1 --> G1
  T2 --> G2
  T3 --> G3
  T4 --> G4
  T5 --> G5
  T6 --> G6
  T7 --> G7
  T8 --> G8
```
