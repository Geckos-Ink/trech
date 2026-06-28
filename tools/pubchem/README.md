# trech-pubchem — PubChem property + structure cache

A small offline-first helper that fetches substance physical properties and 2D
structure depictions from [PubChem](https://pubchem.ncbi.nlm.nih.gov/) (PUG-REST)
and **caches them under `data/pubchem/`** so scenarios, validation references and
visualization stay reproducible and network-free.

Nothing here runs inside the deterministic Geant4/hook path — it is an
authoring / validation / visualization helper. A run reads only the committed
cache (`load_compound`), never the network.

## Use

```bash
# from the repo root
PYTHONPATH=tools/pubchem python3 -m trech_pubchem fetch benzene "D-glucose"
PYTHONPATH=tools/pubchem python3 -m trech_pubchem show benzene
PYTHONPATH=tools/pubchem python3 -m trech_pubchem list
```

`fetch` writes, per compound:

- `data/pubchem/<slug>.json` — CID, molecular weight/formula, **XLogP**
  (octanol-water partition coefficient), TPSA, H-bond donors/acceptors, SMILES,
  IUPAC name, plus provenance (source URLs + UTC fetch time).
- `data/pubchem/<slug>.png` — the PubChem 2D structure depiction (300×300).

## Why XLogP matters here

`XLogP` is the lipophilicity that governs **passive membrane permeation**
(Overton's rule): a molecule with `XLogP > 0` partitions into the lipid bilayer
and can cross it; a polar molecule (`XLogP < 0`) cannot and is retained. The
membrane-efflux scenario
([`testscenario_efflux.js`](../../examples/experiments/testscenario_efflux.js))
uses this directly — benzene (`XLogP +2.1`) is cleared, D-glucose (`XLogP −2.6`)
is retained — so a real measured substance property decides the chemistry of the
simulation, and the validation (`efflux_first_order_kinetics`) asserts it.

## Python API

```python
import sys; sys.path.insert(0, "tools/pubchem")
from trech_pubchem import load_compound          # cache-only, no network
c = load_compound("benzene")
c.cid, c.xlogp, c.lipophilic, c.smiles, c.png_path
```

## Cache

The committed cache is the source of truth. Re-fetch only to add compounds or
refresh values (PubChem occasionally revises computed properties); the JSON
records the fetch time and source URLs so drift is auditable in `git diff`.
