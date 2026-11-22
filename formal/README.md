# TRECH formal laws (optional Lean package)

Lean 4 definitions and proofs that sit beside TRECH's classic C++/JavaScript implementations,
for validation. Lean is optional: the classic code is what runs, and nothing in the TRECH build
needs this folder. Guide: [`docs/engine/formal_laws.md`](../docs/engine/formal_laws.md).
Contract: [formal-laws handbook](../AGENTS/engine/formal/AGENTS.md).

| File | Lean namespace | Classic implementation |
| --- | --- | --- |
| [`Trech/Laws/Compton.lean`](Trech/Laws/Compton.lean) | `Trech.Laws.Compton` | [`KleinNishina.hpp`](../include/trech/sim/KleinNishina.hpp), [`trech_formal_laws.js`](../js/trech_formal_laws.js) |
| [`Trech/Laws/Attenuation.lean`](Trech/Laws/Attenuation.lean) | `Trech.Laws.Attenuation` | [`AnalyticCrossCheck.cpp`](../src/sim/AnalyticCrossCheck.cpp), [`trech_formal_laws.js`](../js/trech_formal_laws.js) |
| [`Trech/Methods/Lattice.lean`](Trech/Methods/Lattice.lean) | `Trech.Methods.Lattice` | [`LatticeKinetic.cpp`](../src/core/LatticeKinetic.cpp) |

[`laws.json`](laws.json) lists the pairs. `tests/test_formal_law_pairs.py` checks that both sides
exist and cite each other; `tests/test_formal_laws.cpp` runs the classic code against each
statement. Neither needs Lean.

**Status: the Lean files have not been compiled yet** (no toolchain installed; the build is a
gated step). The proofs use only Mathlib lemmas whose names were checked against the pinned
`thirds/mathlib4`, but they are unverified until `lake build` succeeds.

To check the proofs (heavy; needs an explicit go-ahead):

```bash
scripts/pull_lean.sh
cd formal && lake exe cache get && lake build
```

`lake` must match [`lean-toolchain`](lean-toolchain), which must equal
`thirds/mathlib4/lean-toolchain`. Configuring TRECH with `-DTRECH_ENABLE_LEAN_CHECK=ON`
registers the same `lake build` as the CTest entry `trech_formal_lean_build`.
