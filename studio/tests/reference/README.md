# Studio reference renders

Compact animation GIFs of a **curated, small** subset of example scenarios, rendered through
Studio's own offscreen viewport (`trech_studio.capture`). They are a visual regression
reference — glance at them to confirm Studio still renders glass/water/optics scenes the way it
should (transparent dielectrics, Fresnel-glossy glass, coloured photon trajectories growing on
the engine clock).

## They are NOT regenerated on every run

Rendering these is **gated** so the repo doesn't accumulate binary churn (GitHub space). The
example capture suite only writes here when you explicitly ask:

```bash
# refresh the committed reference GIFs (curated subset only)
studio/run_examples_suite.sh --update-refs viz_refraction validation_gow
#   or, for the whole default set's curated ids:
TRECH_STUDIO_UPDATE_REFS=1 studio/run_examples_suite.sh
```

Without `--update-refs` / `TRECH_STUDIO_UPDATE_REFS=1`, the suite renders previews into
`build/studio/examples_suite/` (gitignored) and leaves this directory untouched.

One-off, straight from a run directory:

```bash
python -m trech_studio.capture --run build/dev/out_viz_refraction \
    --reference studio/tests/reference/viz_refraction.gif
```

## Keep them small

`capture_reference` caps the GIF at 320 px · 10 fps · 3 s with a palette-diff encode, so each
lands well under ~0.5 MiB. If you add an id to the curated set (`STUDIO_REF_IDS` or the
`REF_IDS` default in `run_examples_suite.sh`), keep the set short and prefer the fast, visually
distinctive scenarios.

## Honesty

Every pixel is Studio's render of engine output on the engine's clock; the slow turntable and
the trajectory/fluid colours are the only rendering choices (see `studio/AGENTS.md`).
