# trech-pubchem

Small helper for fetching PubChem compound properties and 2D structure depictions
through PUG-REST.

`fetch --conformer` additionally retrieves **comparison-only** 3D coordinates, explicit
atom IDs/bond orders and available MMFF94 charges:

```bash
PYTHONPATH=tools/pubchem python3 -m trech_pubchem fetch --conformer \
  --cache-dir build/pubchem_cache ethane ethanol formamide
```

This writes `<slug>-3d.raw.json` and `<slug>-3d.json`, with source URL, UTC fetch time
and raw-response SHA-256. Coordinates are joined by atom ID; missing 3D data is an error,
never a 2D substitute. Missing charge properties stay null. PubChem conformers/charges
are theoretical MMFF references, not experimental electronic density. The molecular
series pins normalized comparison fixtures beside its learned models, excluded from fitting;
see [`docs/molecular_series.md`](../../docs/molecular_series.md).

Use a build-local cache for runtime/validation work:

```bash
PYTHONPATH=tools/pubchem python3 -m trech_pubchem fetch \
  --cache-dir build/dev/pubchem_cache --no-png water hydrogen oxygen

TRECH_PUBCHEM_CACHE_DIR=build/dev/pubchem_cache \
  ./build/dev/trech run examples/experiments/testscenario_h2o_electrolysis_combustion.js
```

`TRECH_PUBCHEM_CACHE_DIR` is also honored by the Python API and by the C++ JS
runtime helper `TRECH_PUBCHEM(name)`. Plain `fetch` defaults to
`build/pubchem_cache`; the legacy `data/pubchem/` cache is read only as a
fallback. New `data/pubchem/*.json` and `*.png` files are ignored by git, but
the standard path is still build-local cache data rather than committed blobs.

## CLI

```bash
PYTHONPATH=tools/pubchem python3 -m trech_pubchem fetch --cache-dir build/pubchem benzene
PYTHONPATH=tools/pubchem python3 -m trech_pubchem show --cache-dir build/pubchem benzene
PYTHONPATH=tools/pubchem python3 -m trech_pubchem list --cache-dir build/pubchem
```

`fetch` writes, per compound:

- `<cache>/<slug>.json`: CID, molecular weight/formula, XLogP, TPSA, H-bond
  donors/acceptors, SMILES, IUPAC name, and provenance URLs/timestamp.
- `<cache>/<slug>.png`: PubChem 2D structure depiction, unless `--no-png`.

## Python API

```python
from trech_pubchem import fetch_compound, load_compound

fetch_compound("water", cache_root="build/pubchem", png=False)
c = load_compound("water", cache_root="build/pubchem")
```

`XLogP` remains useful for membrane scenarios: a molecule with `XLogP > 0`
partitions into lipid more readily than a polar molecule with `XLogP < 0`.
