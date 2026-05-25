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
| glass -> air | 4000 | 59.961° | 59.961° | 1.46000 ± 0.00000 | 1.00029 | +0.45971 | 0.4596 |
| water -> glass | 4000 | 29.848° | 30.039° | 1.32529 ± 0.00000 | 1.46000 | -0.13471 | 0.0923 |

## Inverse Fresnel (unpolarized)

Transmittance T = refracted / (refracted + reflected) at each
interface; bisection solves the unpolarized Fresnel formula
for n_2 given the handbook n_1 and the mean incidence angle.

| Interface | Refracted | Reflected | T measured | theta_i mean | n_2 inferred | n_2 reference | delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| glass -> air | 4000 | 0 | 1.0000 | 59.961° | 1.46000 | 1.00029 | +0.45971 |
| water -> glass | 4000 | 0 | 1.0000 | 29.848° | n/a | 1.46000 | n/a |

## Inverse Beer-Lambert (water)

`alpha = -ln(N_survived / N_entered) / mean_path_mm`
(water is highly transparent in the visible, so this is
usually an upper-bound estimate of alpha).

| Entered | Survived | Mean path (mm) | alpha inferred (1/mm) | alpha ref (1/mm) | L_abs inferred (mm) | L_abs ref (mm) |
|---:|---:|---:|---:|---:|---:|---:|
| 4000 | 4000 | 34.623 | 0.000007 | 0.000050 | 138476.16 | 20000.00 |

## Direct cross-check: engine-derived n vs handbook

The MolecularOptics extractor writes its mean refractive index
per material into the scene manifest.  These values feed the
Geant4 transport that produced the trajectories above, so
they should be self-consistent with the inverse-Snell column.

| Material | n derived | n reference | delta |
|---|---:|---:|---:|
| air | 1.000001 | 1.000293 | -0.000292 |
| water | 1.001183 | 1.333000 | -0.331817 |
| glass | 1.005816 | 1.460000 | -0.454184 |
