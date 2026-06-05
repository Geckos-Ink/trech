# Glass-of-Water Optical Validation

- Run directory: `/Users/riccardo/Sources/GitHub/trech/build/dev/out_validation_gow`
- Beam energy: 2.2500 eV (~ 551 nm)
- Trajectories analyzed: 4000

Comparison is inverse: from the photon trajectories produced by
TRECH (Geant4 optical photon transport on top of n / abs / scat
tables derived from atomic cross sections), the classical
formulas are solved backwards for n_2 and alpha and the result
is compared against handbook references.

## Inverse Snell's Law

`n_2_inferred = n_1_ref * sin(theta_i) / sin(theta_r)`
aggregated over every refraction at each material interface.

| Interface | Samples | theta_i mean | theta_r mean | n_2 inferred | n_2 reference | delta | rel err |
|---|---:|---:|---:|---:|---:|---:|---:|
| air -> glass | 3998 | 29.595° | 19.869° | 1.45272 ± 0.09239 | 1.46000 | -0.00728 | 0.0050 |
| glass -> air | 4000 | 20.279° | 30.000° | 1.01136 ± 0.09218 | 1.00029 | +0.01107 | 0.0111 |
| glass -> water | 3997 | 19.872° | 22.084° | 1.32000 ± 0.00496 | 1.33300 | -0.01300 | 0.0098 |
| water -> glass | 3998 | 22.081° | 19.869° | 1.47436 ± 0.00548 | 1.46000 | +0.01436 | 0.0098 |

## Inverse Fresnel (unpolarized)

Transmittance T = refracted / (refracted + reflected) at each
interface; bisection solves the unpolarized Fresnel formula
for n_2 given the handbook n_1 and the mean incidence angle.

| Interface | Refracted | Reflected | T measured | theta_i mean | n_2 inferred | n_2 reference | delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| air -> glass | 3998 | 162 | 0.9611 | 29.610° | 1.48111 | 1.46000 | +0.02111 |
| glass -> air | 4000 | 160 | 0.9615 | 20.264° | n/a | 1.00029 | n/a |
| glass -> water | 3997 | 6 | 0.9985 | 19.872° | n/a | 1.33300 | n/a |
| water -> glass | 3998 | 5 | 0.9988 | 22.081° | 1.42953 | 1.46000 | -0.03047 |

## Inverse Beer-Lambert (water)

`alpha = -ln(N_survived / N_entered) / mean_path_mm`
(water is highly transparent in the visible, so this is
usually an upper-bound estimate of alpha).

| Entered | Survived | Mean path (mm) | alpha inferred (1/mm) | alpha ref (1/mm) | L_abs inferred (mm) | L_abs ref (mm) |
|---:|---:|---:|---:|---:|---:|---:|
| 3838 | 3838 | 56.032 | 0.000005 | 0.000050 | 215021.19 | 20000.00 |

## Direct cross-check: engine-derived n vs handbook

The MolecularOptics extractor writes its mean refractive index
per material into the scene manifest.  These values feed the
Geant4 transport that produced the trajectories above, so
they should be self-consistent with the inverse-Snell column.

| Material | n derived | n reference | delta |
|---|---:|---:|---:|
| air | 1.000383 | 1.000293 | +0.000090 |
| water | 1.330739 | 1.333000 | -0.002261 |
| glass | 1.472156 | 1.460000 | +0.012156 |
