#!/usr/bin/env bash
# TRECH Studio — examples capture suite.
#
# Runs example scenarios through the engine, then renders each run's Studio viewport
# (scene + timeline playback: trajectory growth / fluid particle frames) OFFSCREEN to a
# still PNG + an MP4/GIF, and writes a manifest.json + index.md so a human or an AI can
# validate that Studio handles each complex scenario and renders it correctly.
#
# The renderer is Studio's own wgpu path (trech_studio.capture), so this exercises the real
# viewport, not a parallel drawing path. Encoding uses ffmpeg (PNG still works without it).
#
# USAGE
#   studio/run_examples_suite.sh [options] [ID ...]
#
#   With no IDs: runs the default set (fast + medium, no external deps).
#   With IDs:    runs exactly those scenarios (see --list for ids), regardless of speed.
#
# OPTIONS
#   --list             list the scenario table and exit
#   --all              include slow scenarios (still excludes network/pubchem ones unless named)
#   --still            capture stills (PNG) only — no MP4/GIF (much faster)
#   --update-refs      ALSO write compact reference GIFs for a curated subset into
#                      studio/tests/reference/ (committed to git). OFF by default so refs are
#                      not regenerated on every run — only when you explicitly ask (GitHub space).
#   --no-run           skip the engine run; capture existing run dirs (re-render only)
#   --events N         override every scenario's event/tick count (quick smoke)
#   --width N          frame width  (default 960, forced even)
#   --height N         frame height (default 640, forced even)
#   --seconds S        animation length in seconds (default 6)
#   --fps N            animation frames per second (default 24)
#   --out DIR          output base dir (default build/studio/examples_suite)
#   -h, --help         this help
#
# ENV
#   TRECH_BIN                 engine binary (default: build/dev/trech, else build/**/trech)
#   STUDIO_PY                 python with wgpu (default: studio/.venv/bin/python, else python3)
#   TRECH_STUDIO_UPDATE_REFS  =1 is equivalent to --update-refs
#   STUDIO_REF_IDS            override the curated reference id set (space-separated)
#
# EXAMPLES
#   studio/run_examples_suite.sh                       # default set, PNG+MP4+GIF
#   studio/run_examples_suite.sh --still viz_refraction glass_shaken
#   studio/run_examples_suite.sh --all                 # add the slow MD/fluid scenarios
#   studio/run_examples_suite.sh --no-run --list

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

# --- scenario table: id|file|events|speed|needs|note ------------------------------------
# speed: fast|med|slow   needs: none|pubchem   (avoid apostrophes: macOS bash 3.2 quirk)
SCENARIOS='hello_world|hello_world.js|4|fast|none|Minimal geometry sanity (world + a box)
water_box|water_box.js|8|fast|none|Single water box in air
viz_refraction|viz_refraction_demo.js|60|fast|none|Optics refraction; photon trajectories bend at the water surface
validation_gow|validation_glass_of_water.js|200|fast|none|Strict single-photon glass-of-water optics
gow_varied|glass_of_water_varied.js|200|fast|none|Spread-source optics (anti-degeneration variety guard)
gow_spectral|glass_of_water_spectral.js|200|fast|none|Blackbody spectrum -> chromatic dispersion (coloured rays)
config_optics|config_optics.js|20|fast|none|Optics spectrum sampling scene
optics_panel|optics_training_panel.js|1|fast|none|Derived-optics panel (colour/opacity from Geant4 cross sections)
surrogate_generic|surrogate_generic_demo.js|4|fast|none|Generic models[]/ctx.predict inference guard
analytic_beer_lambert|analytic_beer_lambert.js|2000|fast|none|Photon attenuation vs Beer-Lambert; absorbed trajectories
analytic_csda|analytic_csda_range.js|500|fast|none|Proton CSDA range vs measured track length
cnt_band|cnt_band_structure.js|5|fast|none|CNT tight-binding band structure scene
cnt_gates|cnt_logic_gates.js|8|fast|none|CNTFET logic-gate device scene
nitrogen_cycle|config_nitrogen_carbon_cycle.js|5|fast|none|Nitrogen-carbon nuclear cycle
h2o_fluid|h2o_fluid.js|50|fast|none|Brine + salt box (element-component regression)
pascal|testscenario_pascal.js|600|med|none|Pascal principle: pressure transmission in a hook-driven bath
osmotic|testscenario_osmotic.js|1500|med|none|Osmosis across a semipermeable membrane (crenation)
h2o_molecule|h2o_molecule_stability.js|800|med|none|Single-molecule rigid-SPC/E MD bond stability
h2o_cluster|h2o_cluster_fluid.js|1500|med|none|Multi-molecule cluster-fluid MD
mr_stage1|testscenario_magnetic_resonance.js|236|med|none|NMR: discovered Larmor line + Geant4 proton density
glass_shaken|glass_of_water_shaken.js|641|slow|none|Multi-scale cascade: ~1 L poured + shaken; fluid_frame particle playback (SLOW ~15-25 min)
h2o_bulk|h2o_bulk_water.js|2500|slow|none|Periodic bulk water, O-O g(r) (SLOW ~4 min)
diffusion_t|h2o_diffusion_temperature.js|8100|slow|none|Self-diffusion D(T) sweep (SLOW ~20 min)
efflux|testscenario_efflux.js|2000|slow|pubchem|Passive membrane efflux vs first-order law (needs PubChem: benzene, D-glucose)
electrolysis|testscenario_h2o_electrolysis_combustion.js|1500|slow|pubchem|Electrolysis + inverse combustion cycle (needs PubChem: water, hydrogen, oxygen)'

# --- args -------------------------------------------------------------------------------
DO_LIST=0; INCLUDE_SLOW=0; STILL=0; NO_RUN=0
UPDATE_REFS="${TRECH_STUDIO_UPDATE_REFS:-0}"
EVENTS_OVERRIDE=""; WIDTH=960; HEIGHT=640; SECONDS_LEN=6; FPS=24
OUT_BASE="build/studio/examples_suite"
# Curated subset that gets a committed reference GIF (keep small: repo-space discipline).
REF_IDS="${STUDIO_REF_IDS:-viz_refraction validation_gow gow_spectral}"
REF_DIR="studio/tests/reference"
SELECTED=()

print_help() { sed -n '2,49p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) DO_LIST=1; shift;;
    --all) INCLUDE_SLOW=1; shift;;
    --still) STILL=1; shift;;
    --update-refs) UPDATE_REFS=1; shift;;
    --no-run) NO_RUN=1; shift;;
    --events) EVENTS_OVERRIDE="$2"; shift 2;;
    --width) WIDTH="$2"; shift 2;;
    --height) HEIGHT="$2"; shift 2;;
    --seconds) SECONDS_LEN="$2"; shift 2;;
    --fps) FPS="$2"; shift 2;;
    --out) OUT_BASE="$2"; shift 2;;
    -h|--help) print_help; exit 0;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) SELECTED+=("$1"); shift;;
  esac
done

field() { echo "$1" | cut -d'|' -f"$2"; }

if [[ "${DO_LIST}" == "1" ]]; then
  printf "%-22s %-8s %-8s %s\n" "ID" "SPEED" "NEEDS" "SCENARIO"
  printf "%-22s %-8s %-8s %s\n" "----" "-----" "-----" "--------"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    printf "%-22s %-8s %-8s %s\n" "$(field "$line" 1)" "$(field "$line" 4)" "$(field "$line" 5)" "$(field "$line" 2)"
  done <<< "${SCENARIOS}"
  exit 0
fi

# --- locate engine + studio python ------------------------------------------------------
BIN="${TRECH_BIN:-}"
if [[ -z "${BIN}" ]]; then
  if [[ -x "build/dev/trech" ]]; then BIN="build/dev/trech";
  else BIN="$(find build -maxdepth 3 -name trech -type f -perm -u+x 2>/dev/null | head -1 || true)"; fi
fi
if [[ -z "${BIN}" || ! -x "${BIN}" ]]; then
  echo "error: trech binary not found (set TRECH_BIN or build build/dev/trech)." >&2
  exit 2
fi

PY="${STUDIO_PY:-}"
if [[ -z "${PY}" ]]; then
  if [[ -x "studio/.venv/bin/python" ]]; then PY="studio/.venv/bin/python"; else PY="python3"; fi
fi
if ! "${PY}" -c "import wgpu, rendercanvas" >/dev/null 2>&1; then
  echo "warning: ${PY} lacks wgpu/rendercanvas — captures will be JSON-only. Install: (cd studio && pip install -e .)" >&2
fi
command -v ffmpeg >/dev/null 2>&1 || echo "warning: ffmpeg not on PATH — only still PNGs will be produced." >&2

# --- build the run list -----------------------------------------------------------------
should_run_id() {  # $1 = table line ; echoes 1 to include, 0 to skip
  local id speed needs; id="$(field "$1" 1)"; speed="$(field "$1" 4)"; needs="$(field "$1" 5)"
  if [[ ${#SELECTED[@]} -gt 0 ]]; then
    for s in "${SELECTED[@]}"; do [[ "$s" == "$id" ]] && { echo 1; return; }; done
    echo 0; return
  fi
  # Default set: fast + med, no external deps. --all adds slow (still no pubchem).
  [[ "$needs" != "none" ]] && { echo 0; return; }
  if [[ "$speed" == "slow" ]]; then [[ "${INCLUDE_SLOW}" == "1" ]] && echo 1 || echo 0; return; fi
  echo 1
}

# Validate explicit ids.
if [[ ${#SELECTED[@]} -gt 0 ]]; then
  for s in "${SELECTED[@]}"; do
    grep -q "^${s}|" <<< "${SCENARIOS}" || { echo "error: unknown scenario id '${s}' (see --list)" >&2; exit 2; }
  done
fi

RUNS_DIR="${OUT_BASE}/runs"
CAP_DIR="${OUT_BASE}/captures"
mkdir -p "${RUNS_DIR}" "${CAP_DIR}"
STATUS_TSV="${OUT_BASE}/.status.tsv"
: > "${STATUS_TSV}"
PUBCHEM_CACHE="${OUT_BASE}/pubchem_cache"

echo "==> Engine: ${BIN}"
echo "==> Render: ${PY}  (${WIDTH}x${HEIGHT}, $([[ ${STILL} == 1 ]] && echo 'still' || echo "${SECONDS_LEN}s@${FPS}fps"))"
echo "==> Output: ${OUT_BASE}"
echo

fetch_pubchem() {  # $@ = molecule names
  PYTHONPATH="${ROOT}/tools/pubchem:${PYTHONPATH:-}" python3 -m trech_pubchem fetch \
    --cache-dir "${PUBCHEM_CACHE}" --no-png "$@" >/dev/null 2>&1
}

TOTAL=0; RUN_OK=0; CAP_OK=0
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  [[ "$(should_run_id "$line")" == "1" ]] || continue
  id="$(field "$line" 1)"; file="$(field "$line" 2)"; events="$(field "$line" 3)"
  needs="$(field "$line" 5)"; note="$(field "$line" 6)"
  [[ -n "${EVENTS_OVERRIDE}" ]] && events="${EVENTS_OVERRIDE}"
  TOTAL=$((TOTAL+1))
  run_dir="${RUNS_DIR}/${id}"
  run_status="ok"; cap_status="skipped"

  # --- engine run ---
  if [[ "${NO_RUN}" == "1" ]]; then
    [[ -d "${run_dir}" ]] || run_status="missing-run"
  else
    echo "==> [${id}] run ${file} (events=${events})"
    env_prefix=()
    if [[ "${needs}" == "pubchem" ]]; then
      case "${id}" in
        efflux) fetch_pubchem benzene "D-glucose" || run_status="pubchem-fetch-failed";;
        electrolysis) fetch_pubchem water hydrogen oxygen || run_status="pubchem-fetch-failed";;
      esac
      env_prefix=(env "TRECH_PUBCHEM_CACHE_DIR=${PUBCHEM_CACHE}")
    fi
    if [[ "${run_status}" == "ok" ]]; then
      rm -rf "${run_dir}"
      # ${arr[@]+...} guards empty-array expansion under `set -u` on macOS bash 3.2.
      if ! "${env_prefix[@]+"${env_prefix[@]}"}" "${BIN}" run "examples/experiments/${file}" \
            --events "${events}" --output "${run_dir}" > "${RUNS_DIR}/${id}.log" 2>&1; then
        run_status="run-failed"
        echo "    ! run failed (see ${RUNS_DIR}/${id}.log)"
      fi
    fi
  fi
  [[ "${run_status}" == "ok" ]] && RUN_OK=$((RUN_OK+1))

  # --- capture ---
  if [[ -d "${run_dir}" ]]; then
    still_flag=(); [[ "${STILL}" == "1" ]] && still_flag=(--still)
    echo "==> [${id}] capture -> ${CAP_DIR}/${id}.*"
    if "${PY}" -m trech_studio.capture --run "${run_dir}" --out "${CAP_DIR}/${id}" \
          --width "${WIDTH}" --height "${HEIGHT}" --seconds "${SECONDS_LEN}" --fps "${FPS}" \
          "${still_flag[@]+"${still_flag[@]}"}" --label "${note}" > "${CAP_DIR}/${id}.log" 2>&1; then
      cap_status="ok"; CAP_OK=$((CAP_OK+1))
    else
      cap_status="capture-failed"
      echo "    ! capture failed (see ${CAP_DIR}/${id}.log)"
    fi

    # Optionally promote a COMPACT reference GIF into the repo (gated; not every run).
    if [[ "${UPDATE_REFS}" == "1" && "${cap_status}" == "ok" ]] && grep -qw "${id}" <<< "${REF_IDS}"; then
      mkdir -p "${REF_DIR}"
      echo "==> [${id}] update reference -> ${REF_DIR}/${id}.gif"
      "${PY}" -m trech_studio.capture --run "${run_dir}" --reference "${REF_DIR}/${id}.gif" \
          --label "${note}" >> "${CAP_DIR}/${id}.log" 2>&1 \
          || echo "    ! reference update failed (see ${CAP_DIR}/${id}.log)"
    fi
  fi

  printf "%s\t%s\t%s\t%s\t%s\n" "${id}" "${file}" "${run_status}" "${cap_status}" "${note}" >> "${STATUS_TSV}"
done <<< "${SCENARIOS}"

# --- aggregate manifest.json + index.md -------------------------------------------------
echo
echo "==> Writing manifest + index"
"${PY}" - "${OUT_BASE}" "${STATUS_TSV}" "${CAP_DIR}" <<'PYAGG'
import json, sys, datetime
from pathlib import Path
out_base, status_tsv, cap_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
rows = []
for line in status_tsv.read_text().splitlines():
    if not line.strip():
        continue
    id_, file_, run_status, cap_status, note = (line.split("\t") + [""] * 5)[:5]
    sidecar = cap_dir / f"{id_}.json"
    meta = json.loads(sidecar.read_text()) if sidecar.is_file() else {}
    rows.append({
        "id": id_, "file": file_, "note": note,
        "run_status": run_status, "capture_status": cap_status,
        "playback_kind": meta.get("playback_kind"),
        "playback_label": meta.get("playback_label"),
        "emit_tags": meta.get("emit_tags", []),
        "artifacts": [f"captures/{a}" for a in meta.get("artifacts", [])],
        "run_summary": meta.get("run_summary", {}),
    })
manifest = {
    "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    "count": len(rows),
    "run_ok": sum(1 for r in rows if r["run_status"] == "ok"),
    "capture_ok": sum(1 for r in rows if r["capture_status"] == "ok"),
    "cases": rows,
}
(out_base / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

lines = [
    "# TRECH Studio — examples capture suite",
    "",
    f"Generated {manifest['generated']} · {manifest['count']} scenarios · "
    f"runs ok {manifest['run_ok']}/{manifest['count']} · captures ok {manifest['capture_ok']}/{manifest['count']}",
    "",
    "Each case below is an example scenario run through the engine and rendered by Studio's "
    "own viewport (scene + timeline playback). Validate that the still/animation matches the "
    "scenario's expected behaviour noted beside it. Provenance is in each `captures/<id>.json`.",
    "",
]
for r in rows:
    lines.append(f"## {r['id']}  ·  `{r['file']}`")
    lines.append("")
    lines.append(f"- **expected:** {r['note']}")
    lines.append(f"- **status:** run={r['run_status']} · capture={r['capture_status']} · "
                 f"playback={r['playback_kind']}")
    if r["emit_tags"]:
        lines.append(f"- **emit tags:** {', '.join(r['emit_tags'])}")
    pngs = [a for a in r["artifacts"] if a.endswith('.png')]
    gifs = [a for a in r["artifacts"] if a.endswith('.gif')]
    mp4s = [a for a in r["artifacts"] if a.endswith('.mp4')]
    if pngs:
        lines.append("")
        lines.append(f"![{r['id']} still]({pngs[0]})")
    links = []
    if gifs: links.append(f"[animation (gif)]({gifs[0]})")
    if mp4s: links.append(f"[animation (mp4)]({mp4s[0]})")
    if links:
        lines.append("")
        lines.append(" · ".join(links))
    lines.append("")
(out_base / "index.md").write_text("\n".join(lines), encoding="utf-8")
print(f"    manifest.json + index.md ({manifest['count']} cases, "
      f"run_ok={manifest['run_ok']}, capture_ok={manifest['capture_ok']})")
PYAGG

echo
echo "==> Done. Suite: ${TOTAL} · run ok ${RUN_OK} · capture ok ${CAP_OK}"
echo "==> Browse: ${OUT_BASE}/index.md   Machine-readable: ${OUT_BASE}/manifest.json"
