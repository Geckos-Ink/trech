# TRECH formal laws (optional Lean package)

Lean 4 definitions and proofs that sit beside TRECH's classic C++/JavaScript implementations,
for validation. Lean is optional: the classic code is what runs, and nothing in the TRECH build
needs this folder. Guide: [`docs/engine/formal_laws.md`](../docs/engine/formal_laws.md).
Contract: [formal-laws handbook](../AGENTS/engine/formal/AGENTS.md).

| File | Lean namespace | Classic implementation |
| --- | --- | --- |
| [`Trech/Laws/Compton.lean`](Trech/Laws/Compton.lean) | `Trech.Laws.Compton` | [`KleinNishina.hpp`](../include/trech/sim/KleinNishina.hpp), [`trech_formal_laws.js`](../js/trech_formal_laws.js) |
| [`Trech/Laws/EnergyBalance.lean`](Trech/Laws/EnergyBalance.lean) | `Trech.Laws.EnergyBalance` | [`EnergyBalance.hpp`](../include/trech/sim/EnergyBalance.hpp) (read on Geant4 Compton steps in [`SteppingAction.cpp`](../src/sim/SteppingAction.cpp)) |
| [`Trech/Laws/Attenuation.lean`](Trech/Laws/Attenuation.lean) | `Trech.Laws.Attenuation` | [`AnalyticCrossCheck.cpp`](../src/sim/AnalyticCrossCheck.cpp), [`trech_formal_laws.js`](../js/trech_formal_laws.js) |
| [`Trech/Methods/Lattice.lean`](Trech/Methods/Lattice.lean) | `Trech.Methods.Lattice` | [`LatticeKinetic.cpp`](../src/core/LatticeKinetic.cpp), [`LatticeContinuum.cpp`](../src/core/LatticeContinuum.cpp) |
| [`Trech/Methods/Transition.lean`](Trech/Methods/Transition.lean) | `Trech.Methods.Transition` | [`DiscreteTransition.cpp`](../src/ml/DiscreteTransition.cpp) (channel probabilities and count conservation) |
| [`Trech/Methods/PairInteraction.lean`](Trech/Methods/PairInteraction.lean) | `Trech.Methods.PairInteraction` | [`PairInteraction.cpp`](../src/ml/PairInteraction.cpp) (antisymmetric exchange) |
| [`Trech/Methods/Arbiter.lean`](Trech/Methods/Arbiter.lean) | `Trech.Methods.Arbiter` | [`MethodArbiter.cpp`](../src/ml/MethodArbiter.cpp) |

[`laws.json`](laws.json) lists the pairs. `tests/test_formal_law_pairs.py` checks that both sides
exist and cite each other; `tests/test_formal_laws.cpp` runs the classic code against each
statement. Neither needs Lean.

**Status (2026-11-22): all 26 theorems compile and use only the standard axioms**
(`propext`, `Classical.choice`, `Quot.sound`), with Lean `v4.37.0-rc1` and Mathlib
`6ebcce3733`, on macOS arm64. Transition counts are proved over mathematical integers.
Checks for real-valued proofs state a tolerance where the classic results round.

Set up once (the Mathlib cache is about 7 GB, kept in ignored `thirds/mathlib4/.lake`):

```bash
brew install elan-init        # or the elan installer; the toolchain follows lean-toolchain
../scripts/pull_lean.sh
lake exe cache get
```

Check the proofs (build plus axiom audit, about 12 s once cached):

```bash
python3 ../scripts/check_lean_laws.py
python3 ../scripts/check_lean_laws.py --report ../build/lean_audit.json   # also save the audit as JSON
```

`lake` must match [`lean-toolchain`](lean-toolchain), which must equal
`thirds/mathlib4/lean-toolchain`; after a Mathlib pull, copy it, run `lake update` and
`lake exe cache get` again, and commit [`lake-manifest.json`](lake-manifest.json).
Configuring TRECH with `-DTRECH_ENABLE_LEAN_CHECK=ON` registers the same check as the CTest
entry `trech_formal_lean_build`.

Every file uses Lean's module system: `module`, `public import` for what the statements need,
plain `import` for proof tactics, and `@[expose] public section`.
