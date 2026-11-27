# Spectrum prediction report

Models learn measured spectra from PubChem/NIST facts, graph topology and, for *_geant4 entries, the Geant4 atomic response (mean excitation energy, photo-absorption cross sections) as inputs. Labels are measurements: these are learned predictions for comparison, not Geant4 results.

Dataset 553b06c64bf1 · 53 atoms (6 test) · 180 molecules (33 test) · 5-fold CV, seed 20261107.

## Atomic line-strength profiles (200–1000 nm)

| Architecture | Family | CV RMSE | CV cosine | Test RMSE | Test R² | Test cosine | Test peak error (nm) | Export |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| atomic_knn3_geant4 | knn | 0.295 ± 0.025 | 0.709 | 0.313 | -0.025 | 0.592 | 240.0 |  |
| atomic_mlp_silu_wide | mlp | 0.297 ± 0.022 | 0.707 | 0.315 | -0.039 | 0.592 | 270.0 |  |
| atomic_mlp_tanh | mlp | 0.297 ± 0.020 | 0.702 | 0.325 | -0.110 | 0.583 | 103.3 |  |
| atomic_knn3 | knn | 0.298 ± 0.021 | 0.702 | 0.325 | -0.112 | 0.553 | 163.3 |  |
| atomic_mlp_tanh_geant4 | mlp | 0.302 ± 0.019 | 0.689 | 0.338 | -0.198 | 0.555 | 183.3 | spectrum_atomic |
| atomic_ridge | ridge | 0.303 ± 0.013 | 0.685 | 0.302 | 0.040 | 0.600 | 156.7 |  |
| atomic_mlp_silu_wide_geant4 | mlp | 0.307 ± 0.028 | 0.690 | 0.339 | -0.205 | 0.575 | 220.0 |  |
| atomic_mlp_tanh_geant4_only | mlp | 0.311 ± 0.042 | 0.693 | 0.349 | -0.282 | 0.606 | 200.0 |  |
| atomic_mean | mean | 0.333 ± 0.014 | 0.622 | 0.334 | -0.173 | 0.520 | 256.7 |  |
| atomic_ridge_geant4 | ridge | 0.337 ± 0.036 | 0.639 | 0.354 | -0.313 | 0.546 | 126.7 |  |

Split-noise check on the training split: 5× repeated 5-fold CV (per-fold RMSE; pooled R² over each repetition's out-of-fold predictions) and leave-one-chemical-group-out CV.

| Architecture | Repeated-CV RMSE | Pooled R² | Pooled cosine | Group-CV RMSE | Group-CV pooled R² |
| --- | --- | --- | --- | --- | --- |
| atomic_knn3_geant4 | 0.300 ± 0.018 | 0.164 ± 0.008 | 0.706 | 0.364 ± 0.055 | -0.333 |
| atomic_mlp_silu_wide | 0.303 ± 0.021 | 0.144 ± 0.027 | 0.696 | 0.379 ± 0.097 | -0.614 |
| atomic_mlp_tanh | 0.305 ± 0.019 | 0.133 ± 0.027 | 0.685 | 0.372 ± 0.072 | -0.410 |
| atomic_knn3 | 0.306 ± 0.016 | 0.128 ± 0.017 | 0.690 | 0.374 ± 0.079 | -0.434 |
| atomic_mlp_tanh_geant4 | 0.310 ± 0.018 | 0.104 ± 0.018 | 0.683 | 0.358 ± 0.058 | -0.275 |
| atomic_ridge | 0.312 ± 0.016 | 0.096 ± 0.036 | 0.675 | 0.394 ± 0.105 | -0.617 |
| atomic_mlp_silu_wide_geant4 | 0.308 ± 0.022 | 0.115 ± 0.022 | 0.689 | 0.378 ± 0.083 | -0.477 |
| atomic_mlp_tanh_geant4_only | 0.318 ± 0.025 | 0.057 ± 0.031 | 0.689 | 0.345 ± 0.058 | -0.298 |
| atomic_mean | 0.336 ± 0.011 | -0.049 ± 0.007 | 0.616 | 0.355 ± 0.048 | -0.204 |
| atomic_ridge_geant4 | 0.339 ± 0.024 | -0.073 ± 0.033 | 0.639 | 0.418 ± 0.102 | -0.799 |

## Molecular UV absorption envelopes (180–500 nm)

| Architecture | Family | CV RMSE | CV cosine | Family-CV RMSE | Test RMSE | Test R² | Test cosine | Test peak error (nm) | Export |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| molecular_mlp_cascade_geant4 | mlp | 0.230 ± 0.019 | 0.784 | 0.252 | 0.225 | 0.367 | 0.752 | 41.8 | spectrum_molecular |
| molecular_mlp_cascade | mlp | 0.231 ± 0.018 | 0.788 | 0.256 | 0.228 | 0.351 | 0.749 | 39.7 |  |
| molecular_mlp | mlp | 0.233 ± 0.018 | 0.780 | 0.255 | 0.225 | 0.372 | 0.753 | 43.6 |  |
| molecular_ridge_cascade_geant4 | ridge | 0.243 ± 0.017 | 0.770 | 0.283 | 0.243 | 0.264 | 0.745 | 45.8 |  |
| molecular_ridge | ridge | 0.245 ± 0.021 | 0.760 | 0.280 | 0.246 | 0.245 | 0.744 | 47.9 |  |
| molecular_ridge_cascade | ridge | 0.247 ± 0.015 | 0.767 | 0.303 | 0.244 | 0.260 | 0.742 | 43.9 |  |
| molecular_knn3 | knn | 0.254 ± 0.015 | 0.754 | 0.271 | 0.234 | 0.317 | 0.742 | 40.0 |  |
| molecular_mean | mean | 0.255 ± 0.022 | 0.756 | 0.270 | 0.287 | -0.029 | 0.733 | 40.6 |  |
| molecular_mpnn | mpnn | 0.263 ± 0.029 | 0.722 | 0.288 | 0.263 | 0.141 | 0.726 | 36.1 |  |
| molecular_mpnn_cascade | mpnn | 0.266 ± 0.019 | 0.690 | 0.283 | 0.256 | 0.183 | 0.709 | 42.4 |  |
| molecular_mpnn_cascade_geant4 | mpnn | 0.268 ± 0.026 | 0.730 | 0.286 | 0.274 | 0.064 | 0.689 | 45.8 |  |
| molecular_deepsets | deepsets | 0.270 ± 0.021 | 0.705 | 0.293 | 0.286 | -0.016 | 0.684 | 46.7 |  |

## Calibrated prediction intervals (exported models)

Per-bin split-conformal intervals at 0.90 nominal coverage, calibrated on the out-of-fold residuals of the ranking CV. Coverage is per (sample, bin) cell; "all bins" is the stricter simultaneous fraction. Out-of-group rows apply the same interval to leave-one-family/group-out predictions.

| Export | Calibration n | Mean width | Test coverage | Test min-bin | Test all bins | Out-of-group coverage | Out-of-group width ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| spectrum_atomic | 47 | 1.102 | 0.875 | 0.500 | 0.000 | 0.864 | 1.17× |
| spectrum_molecular | 147 | 0.734 | 0.906 | 0.848 | 0.515 | 0.891 | 1.05× |

## Atomic → molecular cascade ablation

Negative deltas mean the pooled atomic-model features helped.

| Without | With | ΔCV RMSE | ΔFamily-CV RMSE | ΔTest RMSE |
| --- | --- | --- | --- | --- |
| molecular_ridge | molecular_ridge_cascade | 0.0024 | 0.0237 | -0.0025 |
| molecular_mlp | molecular_mlp_cascade | -0.0012 | 0.0010 | 0.0037 |
| molecular_mpnn | molecular_mpnn_cascade | 0.0026 | -0.0046 | -0.0065 |

## Geant4 atomic-input ablation

Same atomic architecture with and without the Geant4 atomic response (mean excitation energy, photo-absorption 10 eV–10 keV) as inputs. Negative deltas mean the Geant4 inputs helped; the group column is leave-one-chemical-group-out CV.

| Without | With | ΔCV RMSE | ΔGroup-CV RMSE | ΔTest RMSE |
| --- | --- | --- | --- | --- |
| atomic_knn3 | atomic_knn3_geant4 | -0.0030 | -0.0105 | -0.0129 |
| atomic_ridge | atomic_ridge_geant4 | 0.0341 | 0.0241 | 0.0512 |
| atomic_mlp_tanh | atomic_mlp_tanh_geant4 | 0.0050 | -0.0137 | 0.0126 |
| atomic_mlp_silu_wide | atomic_mlp_silu_wide_geant4 | 0.0109 | -0.0016 | 0.0241 |

## Cascade source ablation (Geant4-fed vs PubChem-fed atomic model)

Same molecular architecture pooling the Geant4-fed instead of the PubChem-fed atomic model. Negative deltas favour the Geant4-fed rung.

| Without | With | ΔCV RMSE | ΔFamily-CV RMSE | ΔTest RMSE |
| --- | --- | --- | --- | --- |
| molecular_ridge_cascade | molecular_ridge_cascade_geant4 | -0.0047 | -0.0201 | -0.0007 |
| molecular_mlp_cascade | molecular_mlp_cascade_geant4 | -0.0009 | -0.0037 | -0.0029 |
| molecular_mpnn_cascade | molecular_mpnn_cascade_geant4 | 0.0024 | 0.0028 | 0.0180 |

## Geant4-fed cascade ablation (with vs without pooled Geant4-fed atomic predictions)

Negative deltas mean the pooled Geant4-fed atomic predictions helped.

| Without | With | ΔCV RMSE | ΔFamily-CV RMSE | ΔTest RMSE |
| --- | --- | --- | --- | --- |
| molecular_ridge | molecular_ridge_cascade_geant4 | -0.0023 | 0.0036 | -0.0032 |
| molecular_mlp | molecular_mlp_cascade_geant4 | -0.0021 | -0.0026 | 0.0008 |
| molecular_mpnn | molecular_mpnn_cascade_geant4 | 0.0050 | -0.0018 | 0.0116 |

