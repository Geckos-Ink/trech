# Studio reference renders

Compact animation GIFs of a **curated, small** subset of example scenarios, rendered through
Studio's own offscreen viewport (`trech_studio.capture`). They are a visual regression
reference — glance at them to confirm Studio still renders glass/water/optics scenes the way it
should (transparent dielectrics, Fresnel-glossy glass, coloured photon trajectories growing on
the engine clock) — and they are what `studio/README.md` embeds as "rendered by Studio".

The committed set (`viz_refraction`, `validation_gow`, `glass_shaken`,
`beaker_water_pentane`) is the honest subset Studio renders faithfully: optics **trajectory**
scenes (transparent media + bending photons), the shaken-glass **fluid particle** playback,
and material-resolved water/n-pentane observer
frames. The beaker reference uses explicitly labelled blue/gold display tints to distinguish its
two physically colourless phases; layout and evaporation remain cascade outputs. Scenarios
whose output is a bespoke 2D plot
(g(r), D(T), MRI, CNT band structure) are not here — Studio's 3D viewport does not reproduce
them, and showing an empty stage would be dishonest.

## They are NOT regenerated on every run

Rendering these is **gated** so the repo doesn't accumulate binary churn (GitHub space). The
example capture suite only writes here when you explicitly ask:

```bash
# refresh the committed reference GIFs (curated subset only)
studio/run_examples_suite.sh --update-refs viz_refraction validation_gow
#   glass_shaken is slow — include it explicitly (or with --all):
studio/run_examples_suite.sh --update-refs --all glass_shaken
#   water+n-pentane fetches PubChem structure metadata before rendering:
studio/run_examples_suite.sh --update-refs beaker_water_pentane
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

`capture_reference` caps the GIF at 360×260 px · 12 fps · 4 s with a palette-diff encode. Most
references land below ~0.5 MiB; particle-dense scenes such as `glass_shaken` can be modestly
larger. If you add an id to the curated set (`STUDIO_REF_IDS` or the `REF_IDS` default in
`run_examples_suite.sh`), keep the set short and prefer fast, visually distinctive scenarios.

## Honesty

Every pixel is Studio's render of engine output on the engine's clock; the slow turntable,
trajectory/fluid colours, and explicitly labelled beaker phase tints are the only rendering
choices (see `studio/AGENTS.md`).
