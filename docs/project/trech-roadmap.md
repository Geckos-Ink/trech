
# TRECH — implementation roadmap (C++ + Geant4 + embedded JS + LibTorch)

## 0) What TRECH is (and isn’t)

**Goal:** build a C++ simulation + reminder/learning system that uses **Geant4** for particle/field transport and “event provenance”, then **bridges into chemistry** via (a) Geant4-DNA’s **chemistry stage** (species production, diffusion, reactions) and (b) **ML surrogates** (LibTorch) where first-principles chemistry is intractable at scale. Geant4-DNA already includes water radiolysis chemistry features (species production, diffusion, reactions) that TRECH can treat as the “chemistry kernel” MVP and then generalize. ([Geant4-DNA][1])

**Non-goal (initially):** a universal quantum-chemistry solver. TRECH will instead focus on:

* **radiation / particle-driven chemistry** (Geant4-DNA style),
* **reaction–diffusion / kinetic networks** in space/time,
* and **ML** to learn effective rates/potentials/closures.

---

## 1) Top-level architecture

### 1.1 Core layers

1. **C++ core (TRECH runtime)**

   * deterministic “experiment runner”
   * logging/provenance
   * caching/data store
2. **Geant4 integration layer**

   * geometry, materials, EM + DNA physics lists
   * stepping/action hooks to emit “chemistry triggers”
3. **Chemistry layer**

   * species registry + reaction network DSL
   * diffusion + reactions (Geant4-DNA chemistry stage where applicable; custom reaction–diffusion engine elsewhere)
4. **ML layer (LibTorch)**

   * TorchScript model loading
   * feature extraction from events + molecules
   * surrogate prediction + uncertainty
5. **Embedded JS layer**

   * user scripting for:

     * experiment definition,
     * reaction network construction,
     * dataset queries,
     * custom scoring/validation.

### 1.2 Recommended repository layout

* `trech-core/` (C++ lib + CLI)
* `trech-js/` (bindings + standard library)
* `trech-sim/` (Geant4 app + kernels)
* `trech-chem/` (species/reactions/diffusion, bridges)
* `trech-ml/` (TorchScript runtime, feature pipelines)
* `trech-data/` (PubChem + other data connectors, caches)
* `bench/` (benchmark datasets + evaluation scripts)
* `docs/` (roadmap + API docs)


### 1.3 Geant4 integration skeleton (API-anchored)

Geant4 applications are most stable when you follow the kernel’s intended wiring:

1) create a run manager (single-threaded or multi-threaded),
2) register the three **mandatory** “user initialization” objects:
   * `G4VUserDetectorConstruction`
   * `G4VUserPhysicsList` (typically via a ready `G4VModularPhysicsList`, e.g. `QBBC`)
   * `G4VUserActionInitialization` (where you register actions, including the primary generator),
3) call `/run/initialize` (or `Initialize()`),
4) run events via `/run/beamOn N` (or `BeamOn(N)`).

This is explicitly documented in the Geant4 “mandatory actions” guidance. ([9])

**Recommended TRECH mapping (keep it boring, keep it robust)**

* **TRECH “geometry/material config”** → `DetectorConstruction : G4VUserDetectorConstruction` ([12])
* **TRECH “physics preset”** → a stock physics list (start with `QBBC` / other reference lists; add custom processes only later) ([9])
* **TRECH “experiment hooks”** → `ActionInitialization : G4VUserActionInitialization`, registering:
  * `G4VUserPrimaryGeneratorAction` (primary particles),
  * `G4UserRunAction` (run-level provenance, file open/close),
  * `G4UserEventAction` (event-level bookkeeping),
  * `G4UserSteppingAction` (bridge: step → “chemistry injections”),
  * optionally `G4UserTrackingAction` / `G4UserStackingAction` for higher-level filtering. ([9], [13])

**Why this matters for TRECH:** it cleanly separates (a) Geant4 ownership/lifecycle from (b) your JS-driven configuration, and it makes multi-threading and reproducibility easier to reason about. Geant4 also provides a canonical “main program” pattern for batch/interactive execution via the UI manager. ([10])

**Concrete minimum `main()` shape**

You’ll typically create the run manager via `G4RunManagerFactory::CreateRunManager(...)` so you can select MT/ST at runtime and keep your app code identical. ([11])

---

## 2) Milestones and deliverables

### M1 — “Hello Geant4 + JS + provenance” (API-anchored)

**Deliverables**

* CLI: `trech run experiment.js`
* Embedded JS interpreter (QuickJS/Duktape/etc.) that **produces a TRECH config** (JSON) consumed by C++ (avoid calling Geant4 directly from JS at first).
* A canonical Geant4 application skeleton wired according to the mandatory initialization pattern:
  * create run manager via `G4RunManagerFactory::CreateRunManager(...)`,
  * `SetUserInitialization(new DetectorConstruction(...))`,
  * `SetUserInitialization(physicsList)`,
  * `SetUserInitialization(new ActionInitialization(...))`. ([9], [11], [12])
* Provenance log (JSONL) written by `RunAction`:
  * `geant4_version`: `G4RunManager::GetVersionString()` and/or `G4VERSION_NUMBER` from `G4Version.hh` ([23], [24])
  * random engine + seed (e.g., `CLHEP::HepRandom::setTheSeed(seed)`; record seed + engine name) ([25])
  * physics list name + key parameters
  * geometry/material config hash (TRECH-side)
  * optional: “macro transcript” (if you also support Geant4 UI macros)

**Implementation notes (stability-first)**

* Put **step-level extraction** behind a single, well-defined hook: `G4UserSteppingAction::UserSteppingAction(const G4Step*)`. Start by extracting only what you need (e.g., `edep`, `pos`, `volume`, `trackID`, `parentID`, `particle`, `globalTime`) to avoid perf collapse. ([13])
* Prefer **built-in scoring** for aggregated quantities (dose/edep by volume) instead of logging every step:
  * `G4MultiFunctionalDetector` + primitive scorers (e.g., `G4PSEnergyDeposit`) produce `G4THitsMap` outputs per event/run. ([14], [21], [26], [27])
* Use Geant4 analysis (`G4AnalysisManager::Instance()`) for histograms/ntuples and keep output thread-safe. ([15])
* For MT correctness, use `G4AccumulablesManager` / `G4Accumulable` to merge scalar counters cleanly. ([16], [22])

**Acceptance criteria**

* 100% reproducibility given the same TRECH config hash + seed (and recorded Geant4 version).
* JS can define geometry/material parameters and run loops (via TRECH config → C++ → Geant4).
* A first “provenance bundle” exists: config JSON + hashes + software version + seed(s).

---

### M2 — Chemistry MVP via Geant4-DNA chemistry stage (water + scavengers)

Use Geant4-DNA’s **track-structure + chemistry stage** as TRECH’s first end-to-end “physics → chemistry” capability:

* particle interactions produce species (radiolysis),
* species diffuse + react over time windows (step-by-step / IRT depending on the chosen model).

Geant4-DNA chemistry is managed through the DNA chemistry manager and reaction tables; Geant4 documents chemical reactions as part of its physics process guidance. ([17], [2])

**Deliverables**

* Build option: `TRECH_ENABLE_DNA_CHEM=ON`
* A “known-good” DNA example parity target (TRECH should replicate one of the canonical Geant4-DNA chemistry examples before generalizing). The Geant4-DNA project lists chemistry examples such as `chem1`/`chem2` in the Geant4 distribution. ([20])
* Chemistry list wiring:
  * start from `G4EmDNAChemistry` (or the appropriate `..._option*` constructor in your targeted Geant4 version) and register it as your chemistry list. ([19])
* Reaction network configuration:
  * allow JS to enable/disable reaction channels or scavengers (by producing a config that C++ applies to the relevant DNA reaction table via the chemistry manager). ([17], [2])

**Example experiments**

* Water box radiolysis yields vs dose and time
* Scavenger networks (configurable reaction sets / concentrations)

**Acceptance criteria**

* Run produces time-resolved species yields (CSV/ROOT/JSON) written via Geant4 analysis tools. ([15])
* JS can swap reaction networks and diffusion coefficients through the TRECH config.
* TRECH records enough provenance to reproduce published curves (version, physics preset, chemistry model, seed policy).

---

### M3 — General reaction–diffusion engine (beyond water radiolysis)

**Goal:** keep Geant4 as the particle/field + event engine, but allow chemistry in arbitrary media.

**Deliverables**

* TRECH chemistry kernel (independent of Geant4-DNA):

  * species: `id, charge, mass, diffusion, tags`
  * reaction: `A + B -> C + ...` with rate law
  * spatial discretization plugin (voxel / mesh / particle-based)
* bridge: Geant4 energy deposition / excitations → “species injections” (time, position, parent track id)

**Acceptance criteria**

* same experiment can run:

  * “DNA chemistry mode” (where supported) and
  * “TRECH RD mode” (generic), producing comparable outputs for overlapping scenarios.

---

### M4 — ML surrogates (LibTorch)

**Use cases**

* learn effective reaction rates from conditions
* approximate expensive microphysics
* predict missing parameters (e.g., diffusion/rate priors) with uncertainty

**Deliverables**

* TorchScript model loader + registry
* feature schemas:

  * event features (LET, dose map stats, track cluster metrics)
  * molecule features (from PubChem descriptors + fingerprints via offline pipeline)
* inference hooks callable from JS:

  * `ml.predict(model, features)`

**Acceptance criteria**

* model inference is deterministic + logged with model hash + input feature hash
* can run in “no-ML mode” for baseline comparisons

---

## 3) PubChem integration for studies + validation (detailed spec)

PubChem has two key REST-style programmatic interfaces you’ll use:

* **PUG-REST**: best for *computed properties, identifiers, structures*, and some cross-references. ([iupac.github.io][3])
* **PUG-View**: best for *annotations collected from many sources* (experimental properties, literature links, safety, etc.), with the ability to request specific “headings” or list headings available for a compound. ([Springer][4])
  They are often explicitly contrasted as “computed (PUG-REST) vs collected annotations (PUG-View)”. ([OUP Academic][5])

### 3.1 Exact endpoint patterns TRECH will support

#### 3.1.1 PUG-REST (computed properties / structures / searches)

PUG-REST URLs are composed of **prolog + input + operation + output (+ options)**. ([iupac.github.io][3])

**Prolog**

```text
https://pubchem.ncbi.nlm.nih.gov/rest/pug
```

**A) CID → computed properties (single or many)**

```text
GET /compound/cid/{cid}/property/{prop}/TXT
GET /compound/cid/{cid}/property/{prop}/JSON
GET /compound/cid/{cid_list_comma}/property/{prop_list_comma}/CSV
GET /compound/cid/{cid_list_comma}/property/{prop_list_comma}/JSON
```

Examples shown in the IUPAC cookbook:

````text
GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/MolecularFormula/txt
GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/MolecularWeight/txt
GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/MolecularWeight,HBondDonorCount,XLogP,TPSA/csv
GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244,1983,3672,156391/property/MolecularWeight,XLogP,TPSA/csv
``` :contentReference[oaicite:6]{index=6}

**B) CID → line notations (treat as “properties”)**
```text
GET /compound/cid/{cid_list}/property/CanonicalSMILES,IsomericSMILES,InChI,InChIKey/CSV
````

(Shown by example in the cookbook.) ([iupac.github.io][3])

**C) CID → structure records / images**

```text
GET /compound/cid/{cid}/record/PNG?image_size={small|large}[&record_type=3d]
GET /compound/cid/{cid}/record/SDF?record_type={2d|3d}
```

(Shown by example in the cookbook.) ([iupac.github.io][3])

**D) CID → conformer ensemble**

```text
GET /compound/cid/{cid}/conformers/TXT
GET /conformers/{conformer_id}/SDF
```

(Shown by example in the cookbook.) ([iupac.github.io][3])

**E) Name → CIDs (synonym search)**

```text
GET /compound/name/{name}/cids/TXT
GET /compound/name/{name}/cids/TXT?name_type={complete|word}
GET /compound/name/{name}/cids/JSON
```

(Example endpoints and `name_type` variants are documented in course materials; PubChem’s own tutorial pages echo these patterns.) ([Chemistry LibreTexts][6])

**F) SMILES/InChI → CIDs (identity)**

```text
GET  /compound/smiles/{smiles}/cids/TXT
GET  /compound/smiles/cids/TXT?smiles={urlencoded_smiles}
POST /compound/smiles/cids/TXT   (form field: smiles=...)
GET  /compound/inchi/cids/TXT?inchi={urlencoded_inchi}
POST /compound/inchi/cids/TXT    (form field: inchi=...)
```

(Explicitly shown, including the “special characters” caveat and the URL-parameter/POST workarounds.) ([iupac.github.io][7])

**G) Fast identity / similarity (structure search)**

```text
GET  /compound/fastidentity/cid/{cid}/cids/TXT[?identity_type=...]
POST /compound/fastsimilarity_2d/smiles/cids/TXT  (form field: smiles=...)
```

(Explicit examples in the cookbook.) ([iupac.github.io][7])

> **Implementation note (TRECH):** Treat “A–G” as the *supported stable surface* for dataset building and validation. Everything else is “best effort / future”.

---

#### 3.1.2 PUG-View (annotations / experimental values / headings)

**Prolog**

```text
https://pubchem.ncbi.nlm.nih.gov/rest/pug_view
```

**A) Get the Table-of-Contents (“index”) for a compound**

```text
GET /index/compound/{cid}/JSON
```

Used to discover available headings before fetching full data. ([Springer][4])

**B) Get annotation data for a compound (optionally filtered by heading)**

```text
GET /data/compound/{cid}/JSON
GET /data/compound/{cid}/JSON?heading={Heading+Name}
```

Examples (heading filter): ([Springer][4])

```text
GET https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/1983/JSON?heading=Experimental+Properties
GET https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/1983/JSON?heading=Solubility
```

**C) Retrieve all annotations under a heading across records**

```text
GET /annotations/heading/{Heading}/JSON
GET /annotations/heading/JSON?heading={Heading}
GET /annotations/heading/JSON?heading={Heading}&source={SourceName}
```

(Examples include demonstrating `source=` filtering.) ([Springer][4])

**D) High-value “sections” endpoints (compound-centric)**
PUG-View paper provides multiple examples you can treat as supported patterns:

```text
GET /categories/compound/{cid}/JSON
GET /neighbors/compound/{cid}/JSON
GET /literature/compound/{cid}/JSON
GET /structure/compound/{cid}/JSON
GET /linkout/compound/{cid}/JSON
```

(Examples are explicitly shown.) ([Springer][4])

---

### 3.2 Caching: keys + provenance fields

PubChem employs **dynamic request throttling** and can reject excessive requests (503) and temporarily block clients that keep exceeding limits; it also exposes **throttling status headers** (e.g., `X-Throttling-Control`). ([OUP Academic][8])
So caching is not optional in TRECH; it’s part of correctness (reproducibility) and politeness.

#### 3.2.1 Cache key design (deterministic + collision-resistant)

**Canonical request fingerprint**

* `service`: `pug_rest` | `pug_view`
* `method`: `GET` | `POST`
* `path`: exact path (no scheme/host)
* `query`: sorted by key, then by value; URL-decoded then re-encoded canonically
* `body`: for POST, hash of normalized form body (sorted keys)
* `accept`: requested output format (`JSON|CSV|TXT|SDF|PNG|SVG`) as part of key

**Key format**

```text
pubchem:v1:{service}:{method}:{accept}:{sha256(canonical_path_and_params_and_body)}
```

**Two-tier storage**

1. **Raw HTTP cache**: store bytes + headers (so you can re-parse later if your parser improves).
2. **Parsed artifact cache**: normalized JSON (or structured record) used by TRECH pipelines.

#### 3.2.2 Provenance fields (minimum “auditability contract”)

Store these with every cached response:

**Request**

* `prov.request.url_full` (exact URL used)
* `prov.request.method`
* `prov.request.headers` (at least `Accept`, `User-Agent`)
* `prov.request.body_hash` (if POST)
* `prov.request.timestamp_utc`
* `prov.request.client_version` (TRECH git hash)
* `prov.request.normalized_cache_key`

**Response**

* `prov.response.status_code`
* `prov.response.headers.content_type`
* `prov.response.headers.etag` (if present)
* `prov.response.headers.last_modified` (if present)
* `prov.response.headers.x_throttling_control` (if present) ([OUP Academic][8])
* `prov.response.bytes_sha256`
* `prov.response.received_timestamp_utc`

**Domain-specific**

* `prov.pubchem.interface`: `PUG-REST` | `PUG-View`
* `prov.pubchem.record_type`: `compound|substance|assay|conformer|...`
* `prov.pubchem.record_id`: CID/SID/AID/conformer id
* For PUG-View: `prov.pubchem.heading` (if used), `prov.pubchem.source` (if used) ([Springer][4])

> **Repro rule:** A benchmark run is only “comparable” if it pins *both* (a) the CID list and (b) the cache snapshot hash (or retrieval timestamps + bytes hashes).

---

### 3.3 Benchmark dataset builder spec (frozen CID lists + property extraction rules)

TRECH should ship a **deterministic dataset builder** that creates “frozen” evaluation sets from PubChem.

#### 3.3.1 Builder inputs (versioned manifest)

`bench/pubchem/{dataset_name}.manifest.json`:

* `dataset_id` (semantic version + short hash)
* `created_utc`
* `selection`

  * `cid_list`: explicit frozen list (primary)
  * optionally `cid_query_recipe`: how it was assembled (for transparency)
* `tasks`: list of prediction targets (e.g., solubility, logP, melting point)
* `sources`

  * `computed`: PUG-REST properties
  * `experimental`: PUG-View headings + allowed sources

#### 3.3.2 Recommended CID list strategy

Use **two CID sets**, both frozen:

1. **Core-1000**: hand-curated, stable chemicals (common solvents, small organics, ions).
2. **Chem-Diverse-10k**: derived from a similarity search seed set, deduped.

(How you *build* them can evolve, but the *published benchmark* is always an explicit CID list.)

#### 3.3.3 Property extraction rules (deterministic)

**A) Computed descriptors (PUG-REST)**

* Fetch in bulk via:

  * `/compound/cid/{cids}/property/{props}/JSON` or `/CSV` ([iupac.github.io][3])
* Recommended baseline descriptor set (stable + commonly available):

  * `MolecularFormula`
  * `MolecularWeight`
  * `CanonicalSMILES`
  * `IsomericSMILES`
  * `InChI`
  * `InChIKey`
  * `XLogP`
  * `TPSA`
  * `HBondDonorCount`
  * `HBondAcceptorCount`
  * `HeavyAtomCount` ([iupac.github.io][3])

**B) Experimental/annotated targets (PUG-View)**
Use **index-first** to avoid accidental “missing heading” errors:

1. `GET /index/compound/{cid}/JSON`
2. If heading exists, `GET /data/compound/{cid}/JSON?heading={...}` ([Springer][4])

Recommended first targets (chemistry-friendly, often multi-source):

* `Experimental Properties`
* `Solubility`
* optionally: other specific headings you standardize later

**Extraction normalization**

* Store **all** values as a list of “observations” (do not collapse early).
* Each observation record:

  * `value_raw` (string as given)
  * `value_num` (float if parsable)
  * `units` (normalized to canonical unit when possible)
  * `conditions` (temp, pH, solvent, ionic strength if present)
  * `source_name` (if available)
  * `reference_ids` (PMID/DOI links if present)
  * `pubchem_heading` (e.g., `Solubility`)
  * `parse_warnings`

#### 3.3.4 Dataset output format

Write two artifacts:

1. `dataset.parquet` (tabular)
2. `dataset_prov.jsonl` (per-row provenance + cache keys)

Minimal row schema:

* `cid`
* computed descriptors…
* `target_observations` (nested)
* `missingness_flags`
* `prov_cache_keys` (list)

---

### 3.4 Keeping PubChem-sourced validation fair

PubChem aggregates heterogeneous data. If you don’t control for that, “validation” becomes misleading.

#### 3.4.1 Experimental vs computed: never mix without labeling

* Treat **PUG-REST descriptors** as *inputs/features* (computed by PubChem). ([OUP Academic][5])
* Treat **PUG-View values** as *candidate ground truth* only when they represent experimental measurements or curated annotations (often multi-source). ([Springer][4])

Rule: every target datum must be tagged:

* `target.kind = experimental | curated | computed | unknown`

#### 3.4.2 Multiple values per CID: evaluation protocols

For a given `(CID, target)` you may see many observations (different labs, conditions, units, even contradictions).

Provide **three scoring modes**, and report all three:

1. **Best-effort canonical**: pick one value using strict precedence:

   * preferred units,
   * preferred temperature window (e.g., 20–25°C),
   * preferred source whitelist,
   * else drop to “missing”.
2. **Distributional**: compare predicted value to the observation distribution:

   * MAE to median,
   * and penalty if prediction lies outside IQR (robust).
3. **Condition-aware** (future): model predicts `(value | conditions)`.

Also: PUG-View allows filtering by `source=` for some heading queries; use this to create “source-stratified” evaluations when feasible. ([Springer][4])

#### 3.4.3 Missingness and selection bias

* Always compute missingness per target:

  * `missing_completely` (heading absent; discovered via `/index`) ([Springer][4])
  * `missing_unparsable` (present but can’t parse into numeric)
  * `missing_filtered_out` (excluded by your fairness filters)
* Report coverage:

  * `N_total`, `N_with_any_obs`, `N_with_canonical_obs`
* Never compare models on different CID subsets without stating it.

#### 3.4.4 Throttling-aware and snapshot-consistent validation

Dynamic throttling exists; repeated live pulls can drift in subtle ways (and can fail with 503 under load). ([OUP Academic][5])

Fairness rule:

* Benchmarks must run against a **frozen cache snapshot** (hash of raw response bytes).
* If you must refresh, you refresh *everything* and publish a new dataset version.

---

## 4) TRECH + PubChem: how it wires into the prediction loop

### 4.1 Where PubChem fits

* **Feature enrichment**

  * PUG-REST descriptors → ML features, priors, sanity checks
* **Validation**

  * PUG-View experimental properties → target observations
* **Scenario parameterization**

  * use PubChem SMILES/InChI to seed:

    * reactive species registries,
    * approximate diffusion constants,
    * reaction-network templates (later).

### 4.2 JS-facing API (proposed)

```js
// Resolve identifiers
const cid = await pubchem.nameToCids("aspirin", { nameType: "complete" });

// Fetch descriptors (computed)
const props = await pubchem.properties([2244, 1983], [
  "MolecularWeight", "XLogP", "TPSA", "InChIKey"
], { format: "JSON" });

// Fetch experimental annotation “Solubility” if available
const headings = await pubchem.pugViewIndex(2244);
if (headings.has("Solubility")) {
  const sol = await pubchem.pugViewData(2244, { heading: "Solubility" });
}

// Dataset builder
await bench.build("pubchem_core_1000_v1");
```

---

## 5) Engineering checklist (what to build next)

### 5.1 PubChem connector module

* [ ] URL builder + canonicalization
* [ ] GET + POST client with retry/backoff and 503 handling
* [ ] throttling header capture (`X-Throttling-Control`) ([OUP Academic][8])
* [ ] raw cache + parsed cache
* [ ] schema validators + parsers for:

  * PUG-REST PropertyTable JSON
  * PUG-View Record/Section trees

### 5.2 Benchmark tooling

* [ ] manifest-driven dataset build
* [ ] cache snapshot hash + provenance emit
* [ ] evaluation scripts implementing the 3 scoring modes

### 5.3 Chemistry/physics bridge

Build this bridge using *specific* Geant4 hooks so it stays maintainable and performant:

* [ ] **Step-level “injection extraction”** via `G4UserSteppingAction`:
  * extract `edep`, `position`, `time`, `trackID/parentID`, `particle`, and the touched volume/material id,
  * convert into a compact “injection record” (time, pos, species-type or excitation label, weight). ([13])
* [ ] **Aggregated dose/edep maps** via scoring where possible:
  * `G4MultiFunctionalDetector` + primitive scorers like `G4PSEnergyDeposit` (per-volume/per-cell), producing `G4THitsMap` per event. ([14], [21], [26], [27])
* [ ] **Output + merging**:
  * histograms/ntuples via `G4AnalysisManager` (thread-aware),
  * scalar counters via `G4AccumulablesManager::Merge()` at end of run. ([15], [16])
* [ ] **DNA chemistry pathway (when enabled)**:
  * route chemistry configuration through `G4DNAChemistryManager` and the DNA reaction tables, rather than inventing parallel data structures. ([17], [2])
* [ ] Chemistry kernel consumes the injection stream and evolves the system (RD / particle-based).
* [ ] ML learns correction terms (optional), but never hides provenance: log model hash + feature hash.

---

[1]: https://geant4-dna.in2p3.fr/styled-11/index.html "Chemistry - Geant4-DNA"
[2]: https://apc.u-paris.fr/~franco/g4doxy/html/classG4DNAChemistryManager.html "Geant4: G4DNAChemistryManager Class Reference"
[3]: https://iupac.github.io/WFChemCookbook/datasources/pubchem_pugrest1.html "Accessing PubChem through PUG-REST - Part I — IUPAC FAIR Chemistry Cookbook"
[4]: https://link.springer.com/article/10.1186/s13321-019-0375-2 "PUG-View: programmatic access to chemical annotations integrated in PubChem | Journal of Cheminformatics"
[5]: https://academic.oup.com/nar/article/47/D1/D1102/5146201 "PubChem 2019 update: improved access to chemical data"
[6]: https://chem.libretexts.org/Courses/University_of_Arkansas_Little_Rock/ChemInformatics_%282017%29%3A_Chem_4399_5399/7%3A_Programmatic_Access_to_Public_Chemical_Databases "7: Programmatic Access to Public Chemical Databases"
[7]: https://iupac.github.io/WFChemCookbook/datasources/pubchem_pugrest3.html "Accessing PubChem through PUG-REST: Part III — IUPAC FAIR Chemistry Cookbook"
[8]: https://academic.oup.com/nar/article/46/W1/W563/4990016 "update on PUG-REST: RESTful interface for programmatic access to PubChem | Nucleic Acids Research | Oxford Academic"
[9]: https://geant4.web.cern.ch/documentation/pipelines/master/bfad_html/ForApplicationDevelopers/UserActions/mandatoryActions.html "Mandatory User Actions and Initializations — Geant4 Book For Application Developers"
[10]: https://geant4.web.cern.ch/documentation/pipelines/master/bfad_html/ForApplicationDevelopers/GettingStarted/executeProgram.html "How to Execute a Program — Geant4 Book For Application Developers"
[11]: https://apc.u-paris.fr/~franco/g4doxy4.11/html/classG4RunManagerFactory.html "Geant4: G4RunManagerFactory Class Reference (Doxygen mirror)"
[12]: https://apc.u-paris.fr/~franco/g4doxy4.11/html/classG4RunManager.html "Geant4: G4RunManager Class Reference (Doxygen mirror)"
[13]: https://apc.u-paris.fr/~franco/g4doxy/html/classG4UserSteppingAction.html "Geant4: G4UserSteppingAction Class Reference (Doxygen mirror)"
[14]: https://geant4.web.cern.ch/documentation/pipelines/master/bfad_html/ForApplicationDevelopers/Detector/hit.html "Hits and scorers — Geant4 Book For Application Developers"
[15]: https://geant4.web.cern.ch/documentation/pipelines/master/bfad_html/ForApplicationDevelopers/Analysis/managers.html "Analysis manager classes — Geant4 Book For Application Developers"
[16]: https://geant4.web.cern.ch/documentation/pipelines/master/bfad_html/ForApplicationDevelopers/Analysis/accumulables.html "Accumulables — Geant4 Book For Application Developers"
[17]: https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/TrackingAndPhysics/physicsProcess.html "Physics processes (includes Geant4-DNA chemistry reactions) — Geant4 BFAD"
[19]: https://apc.u-paris.fr/~franco/g4doxy4.11/html/classG4EmDNAChemistry.html "Geant4: G4EmDNAChemistry Class Reference (Doxygen mirror)"
[20]: https://geant4-dna.in2p3.fr/styled-5/index.html "Geant4-DNA examples overview"
[21]: https://apc.u-paris.fr/~franco/g4doxy4.10/html/class_g4_p_s_energy_deposit.html "Geant4: G4PSEnergyDeposit Class Reference (Doxygen mirror)"
[22]: https://geant4.web.cern.ch/documentation/pipelines/master/bfad_html/ForApplicationDevelopers/Examples/BasicCodes.html "Basic Examples Summary — Geant4 Book For Application Developers"
[23]: https://geant4-forum.web.cern.ch/t/get-geant4-version-number-in-c-code/6413 "Geant4 forum: get Geant4 version number in C++"
[24]: https://apc.u-paris.fr/~franco/g4doxy/html/G4Version_8hh-source.html "Geant4: G4Version.hh source (Doxygen mirror)"
[25]: https://geant4-forum.web.cern.ch/t/re-run-the-same-event-by-controlling-the-seeds/2234 "Geant4 forum: controlling seeds for reproducibility"
[26]: https://apc.u-paris.fr/~franco/g4doxy/html/classG4MultiFunctionalDetector.html "Geant4: G4MultiFunctionalDetector Class Reference (Doxygen mirror)"
[27]: https://apc.u-paris.fr/~franco/g4doxy/html/classG4VPrimitiveScorer.html "Geant4: G4VPrimitiveScorer Class Reference (Doxygen mirror)"

---

## A) On-disk cache schema: recommended design (raw HTTP CAS + SQLite index + parsed artifacts)

This is a **draft you can implement immediately** with good reproducibility, deduplication, and “frozen snapshot” support.

### Goals the cache must satisfy

* **Deterministic**: same request fingerprint → same cache key.
* **Reproducible**: benchmarks reference *bytes hashes*, not “whatever PubChem returns today”.
* **Parser-upgradable**: keep **raw bytes** so you can re-parse later with improved parsers.
* **Polite + robust**: supports backoff/throttling + reduces repeat traffic.
* **Snapshot-able**: pin a dataset build to an immutable set of cached responses.
* **Concurrent-safe**: multiple workers can read/write without corrupting state.

---

### Recommended storage layout

Use a **content-addressed store (CAS)** for raw response bodies and **SQLite** for metadata + indexing.

```
~/.cache/trech/pubchem/
  meta.sqlite
  raw/
    sha256/
      ab/
        abcd...<64hex>.bin
  parsed/
    sha256/
      12/
        12ef...<64hex>.json
  locks/
  snapshots/
    pubchem_core_1000_v1/
      snapshot.json
      request_keys.txt
```

* `raw/sha256/...bin` stores **exact response bytes** (JSON/CSV/TXT/SDF/PNG…).
* `parsed/sha256/...json` stores a **normalized parsed form** (TRECH-defined schema).
* `meta.sqlite` indexes: request fingerprint, headers, throttling, mapping to raw bytes hash, parse versions, snapshot membership.

---

### Canonical cache key (request fingerprint)

TRECH should generate a canonical string from:

* `service`: `pug_rest` | `pug_view`
* `method`: `GET` | `POST`
* `path`: exact path (no scheme/host)
* `query`: sorted keys; values sorted; canonical URL encoding
* `body`: for POST (form-encoded), normalize keys/values then SHA256
* `accept`: `application/json` / `text/csv` / `text/plain` / `chemical/x-mdl-sdfile` / `image/png` …
* `api_version`: `"v1"` (so you can change canonicalization later)

**Cache key format**

```
pubchem:v1:{service}:{method}:{accept}:{sha256(canonical_string)}
```

---

### SQLite schema (draft)

Enable **WAL mode** for concurrency.

```sql
-- Requests: one row per unique canonical request
CREATE TABLE IF NOT EXISTS request (
  request_id        INTEGER PRIMARY KEY,
  cache_key         TEXT NOT NULL UNIQUE,
  service           TEXT NOT NULL,         -- pug_rest | pug_view
  method            TEXT NOT NULL,         -- GET | POST
  scheme_host       TEXT NOT NULL,         -- typically https://pubchem.ncbi.nlm.nih.gov
  path              TEXT NOT NULL,
  query_canon       TEXT NOT NULL,         -- canonical query string (sorted)
  body_hash         TEXT,                  -- sha256 of canonical POST body or NULL
  accept            TEXT NOT NULL,
  created_utc       TEXT NOT NULL,
  last_used_utc     TEXT NOT NULL
);

-- Raw HTTP responses: many responses can exist per request if you allow refresh;
-- for "frozen benchmarks" you pin one response hash.
CREATE TABLE IF NOT EXISTS response (
  response_id       INTEGER PRIMARY KEY,
  request_id        INTEGER NOT NULL REFERENCES request(request_id),
  status_code       INTEGER NOT NULL,
  headers_json      TEXT NOT NULL,         -- raw headers captured
  body_sha256       TEXT NOT NULL,         -- CAS key for raw bytes
  body_len          INTEGER NOT NULL,
  content_type      TEXT,
  received_utc      TEXT NOT NULL,
  throttling_json   TEXT,                  -- parsed throttling headers, if any
  etag              TEXT,
  last_modified     TEXT
);

CREATE INDEX IF NOT EXISTS idx_response_request ON response(request_id);
CREATE INDEX IF NOT EXISTS idx_response_bodysha ON response(body_sha256);

-- Objects: CAS objects (raw bytes)
CREATE TABLE IF NOT EXISTS object (
  body_sha256       TEXT PRIMARY KEY,
  storage_relpath   TEXT NOT NULL,         -- raw/sha256/ab/<hash>.bin
  first_seen_utc    TEXT NOT NULL,
  last_seen_utc     TEXT NOT NULL,
  ref_count         INTEGER NOT NULL DEFAULT 1
);

-- Parsed artifacts: normalized JSON extracted from raw bytes using a parser version
CREATE TABLE IF NOT EXISTS parse (
  parse_id          INTEGER PRIMARY KEY,
  body_sha256       TEXT NOT NULL REFERENCES object(body_sha256),
  parser_name       TEXT NOT NULL,         -- e.g. pug_rest_propertytable_json
  parser_version    TEXT NOT NULL,         -- semver or git hash of parser module
  parsed_sha256     TEXT NOT NULL,         -- CAS hash for parsed JSON bytes
  parsed_relpath    TEXT NOT NULL,         -- parsed/sha256/12/<hash>.json
  parsed_type       TEXT NOT NULL,         -- e.g. PropertyTable | PugViewRecord | TextList
  warnings_json     TEXT NOT NULL,         -- parse warnings
  created_utc       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_parse_body ON parse(body_sha256);
CREATE INDEX IF NOT EXISTS idx_parse_parsed ON parse(parsed_sha256);

-- Snapshots: a named, immutable set of cache keys + chosen response body hashes
CREATE TABLE IF NOT EXISTS snapshot (
  snapshot_id       INTEGER PRIMARY KEY,
  name              TEXT NOT NULL UNIQUE,  -- e.g. pubchem_core_1000_v1
  created_utc       TEXT NOT NULL,
  description       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshot_item (
  snapshot_id       INTEGER NOT NULL REFERENCES snapshot(snapshot_id),
  cache_key         TEXT NOT NULL,         -- request cache key
  body_sha256       TEXT NOT NULL,         -- which response is pinned for this request
  PRIMARY KEY (snapshot_id, cache_key)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_item_snap ON snapshot_item(snapshot_id);

-- Pins: prevent GC for anything in a pin
CREATE TABLE IF NOT EXISTS pin (
  pin_id            INTEGER PRIMARY KEY,
  name              TEXT NOT NULL UNIQUE,  -- e.g. "bench:pubchem_core_1000_v1"
  created_utc       TEXT NOT NULL,
  note              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pin_object (
  pin_id            INTEGER NOT NULL REFERENCES pin(pin_id),
  body_sha256       TEXT NOT NULL REFERENCES object(body_sha256),
  PRIMARY KEY (pin_id, body_sha256)
);
```

---

### Write-path algorithm (raw + metadata)

1. Build canonical request fingerprint → `cache_key`.
2. Lookup `request.cache_key`.

   * If exists, update `last_used_utc`.
   * Else insert request row.
3. Perform HTTP request with backoff.
4. Compute `body_sha256` over raw bytes.
5. Write CAS file (atomic):

   * write to temp path + `fsync` + rename.
6. Upsert `object` row (`ref_count++`, update last_seen).
7. Insert `response` row with:

   * status, headers_json
   * `throttling_json` extracted (whatever headers you capture)
   * etag/last-modified if present.
8. Optionally parse into normalized JSON:

   * compute `parsed_sha256`
   * write parsed CAS
   * insert `parse` row.

---

### GC + TTL policy (and why you need both)

* **TTL** is for “interactive mode”: you *may* refresh old entries.
* **Pins/snapshots** are for “benchmark mode”: you *must not refresh*.

Recommended rules:

* If a request is part of a **snapshot**, use the snapshot’s pinned `body_sha256` even if TTL expired.
* GC deletes objects only if:

  * not referenced by any `snapshot_item` or `pin_object`
  * and `last_seen_utc` older than threshold (e.g., 180 days)
  * and `ref_count` indicates no references (or recompute by join)

CLI hooks:

* `trech cache gc --dry-run`
* `trech cache pin bench:pubchem_core_1000_v1`
* `trech cache snapshot create pubchem_core_1000_v1 --from-build <build_id>`
* `trech cache snapshot export pubchem_core_1000_v1` (copies raw/parsed + snapshot.json)

---

### Snapshot file (human + machine readable)

Store alongside DB snapshots directory:

`~/.cache/trech/pubchem/snapshots/pubchem_core_1000_v1/snapshot.json`

```json
{
  "name": "pubchem_core_1000_v1",
  "created_utc": "2026-01-10T00:00:00Z",
  "trech_version": "0.1.0",
  "description": "Core 1000 chemicals benchmark",
  "items": [
    {
      "cache_key": "pubchem:v1:pug_rest:GET:application/json:....",
      "body_sha256": "abcd...."
    }
  ]
}
```

This file makes the benchmark portable even if SQLite is rebuilt.

---

## B) “pubchem_core_1000” benchmark spec: manifest + seed strategy + extraction rules

Because a 1000-CID list is long and error-prone to hand-type, the best practice is:

1. ship a **seed list of names** (stable, human reviewed),
2. provide a `freeze` command that resolves names → CIDs,
3. output a **frozen `cid_list.txt`** and a cache snapshot.

You still end up with the “frozen CID list” requirement—just generated deterministically.

---

### Directory layout (recommended)

```
bench/pubchem/pubchem_core_1000_v1/
  manifest.json
  seed_names.txt
  cid_list.txt            # generated by freeze step, then committed or released
  extraction_rules.json
  README.md
```

---

### `manifest.json` (template)

```json
{
  "dataset_id": "pubchem_core_1000_v1",
  "kind": "pubchem_benchmark",
  "created_utc": "2026-01-10T00:00:00Z",
  "description": "Core 1000 stable chemicals for TRECH validation (features + selected experimental targets).",
  "build": {
    "mode": "freeze",
    "seed_file": "seed_names.txt",
    "cid_file": "cid_list.txt",
    "name_resolution": {
      "strategy": "pug_rest_compound_name_to_cids",
      "name_type": "complete",
      "disambiguation": "manual_review_required"
    }
  },
  "pubchem": {
    "pug_rest": {
      "base": "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
      "computed_properties": [
        "MolecularFormula",
        "MolecularWeight",
        "CanonicalSMILES",
        "IsomericSMILES",
        "InChI",
        "InChIKey",
        "XLogP",
        "TPSA",
        "HBondDonorCount",
        "HBondAcceptorCount",
        "HeavyAtomCount"
      ],
      "bulk_fetch": {
        "max_cids_per_request": 200,
        "format": "JSON"
      }
    },
    "pug_view": {
      "base": "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view",
      "headings": [
        "Experimental Properties",
        "Solubility"
      ],
      "index_first": true
    }
  },
  "tasks": [
    {
      "task_id": "identity_and_descriptors",
      "type": "feature_validation",
      "targets": []
    },
    {
      "task_id": "solubility_obs",
      "type": "experimental_target",
      "target_heading": "Solubility",
      "target_name": "solubility",
      "canonical_units": "g/L",
      "evaluation_modes": ["canonical", "distributional"]
    }
  ],
  "fairness": {
    "experimental_vs_computed": {
      "computed_as_features_only": true,
      "experimental_from_pug_view_only": true
    },
    "multiple_values_policy": {
      "canonical": {
        "temperature_c_window_C": [20, 25],
        "prefer_sources": [],
        "drop_if_ambiguous": true
      },
      "distributional": {
        "compare_to": "median",
        "report_iqr": true
      }
    },
    "missingness": {
      "report": true,
      "distinguish": ["heading_absent", "unparsable", "filtered_out"]
    }
  },
  "reproducibility": {
    "require_cache_snapshot": true,
    "snapshot_name": "pubchem_core_1000_v1"
  }
}
```

---

### `seed_names.txt` (starter seed list)

This is a **starter** seed list (small, safe, diverse). Expand it until you reach ~1000 entries. Each line is a query string.

```text
water
hydrogen peroxide
oxygen
nitrogen
carbon dioxide
ammonia
hydrochloric acid
sulfuric acid
nitric acid
phosphoric acid
sodium chloride
potassium chloride
sodium hydroxide
potassium hydroxide
sodium bicarbonate
sodium carbonate
calcium carbonate
magnesium sulfate
sodium sulfate
sodium nitrate
potassium nitrate
acetic acid
formic acid
citric acid
lactic acid
oxalic acid
ethanol
methanol
isopropanol
acetone
acetonitrile
dimethyl sulfoxide
dimethylformamide
tetrahydrofuran
diethyl ether
ethyl acetate
toluene
benzene
chlorobenzene
phenol
aniline
urea
glucose
sucrose
glycine
alanine
cysteine
histidine
adenine
guanine
cytosine
thymine
uracil
caffeine
aspirin
ibuprofen
paracetamol
nicotine
cholesterol
```

**Freeze step rules**

* If a name resolves to **multiple CIDs**, write all candidates into a `freeze_report.json` and require manual choice (or apply disambiguation rules like “prefer neutral parent”, “prefer smallest heavy atom count”, etc.).
* Once resolved, write final list to `cid_list.txt` and **pin snapshot**.

---

### `cid_list.txt` (generated, frozen)

Format: one CID per line.

```text
# Generated by: trech bench pubchem freeze bench/pubchem/pubchem_core_1000_v1
# Date: 2026-01-10
# Source: PUG-REST name resolution (+ manual disambiguation where needed)
962
702
887
...
```

(Keep the file large; it’s the point of freezing. You can also split into shards if you prefer.)

---

### `extraction_rules.json` (property and observation parsing)

This file defines deterministic parsing, normalization, and filtering. Keep it stable across dataset versions unless you explicitly bump the dataset.

```json
{
  "computed_features": {
    "source": "pug_rest",
    "properties": [
      "MolecularFormula",
      "MolecularWeight",
      "CanonicalSMILES",
      "IsomericSMILES",
      "InChI",
      "InChIKey",
      "XLogP",
      "TPSA",
      "HBondDonorCount",
      "HBondAcceptorCount",
      "HeavyAtomCount"
    ],
    "type_coercion": {
      "numbers": ["MolecularWeight", "XLogP", "TPSA", "HBondDonorCount", "HBondAcceptorCount", "HeavyAtomCount"],
      "strings": ["MolecularFormula", "CanonicalSMILES", "IsomericSMILES", "InChI", "InChIKey"]
    }
  },
  "experimental_targets": [
    {
      "name": "solubility",
      "source": "pug_view",
      "heading": "Solubility",
      "extract": {
        "prefer_numeric": true,
        "unit_normalization": {
          "canonical": "g/L",
          "rules": [
            { "from": "mg/mL", "to": "g/L", "factor": 1.0 },
            { "from": "g/100 mL", "to": "g/L", "factor": 10.0 }
          ]
        },
        "conditions": {
          "parse_temperature": true,
          "parse_ph": true,
          "retain_raw_text": true
        }
      },
      "canonicalization": {
        "temperature_window_C": [20, 25],
        "drop_if_no_units": true,
        "drop_if_range_only": false,
        "max_observations_per_cid": 50
      }
    }
  ],
  "missingness": {
    "heading_absent": "no_index_heading",
    "unparsable": "value_parse_failed",
    "filtered_out": "filtered_by_rules"
  }
}
```

---

### The `freeze` and `build` commands (how TRECH should behave)

* `trech bench pubchem freeze bench/pubchem/pubchem_core_1000_v1`

  * reads `seed_names.txt`
  * calls PubChem name→CID
  * writes:

    * `cid_list.txt`
    * `freeze_report.json` (ambiguities + final choices)
  * creates cache snapshot `pubchem_core_1000_v1`

* `trech bench pubchem build bench/pubchem/pubchem_core_1000_v1`

  * uses **only** `cid_list.txt`
  * bulk fetches computed properties (PUG-REST)
  * fetches PUG-View index then selected headings (only if present)
  * outputs:

    * `dataset.parquet`
    * `dataset_prov.jsonl`
    * `coverage_report.json` (missingness summary)

---

### Small but important fairness defaults (baked into the builder)

* **Never** use PUG-REST computed values as “experimental truth”; treat them as features.
* Always keep **all** observations (raw + parsed). Canonicalize only at evaluation time.
* Report metrics on:

  * canonical subset
  * all-observation distributional scoring
  * coverage (missingness) for transparency

---
