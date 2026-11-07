# Spectrum prediction report

Models learn measured spectra from PubChem/NIST facts and graph topology. They are learned predictions for comparison, not Geant4 results, and the atomic rung is not particle-trained.

Dataset d58883cfc4dc · 53 atoms (6 test) · 180 molecules (33 test) · 5-fold CV, seed 20261107.

## Atomic line-strength profiles (200–1000 nm)

| Architecture | Family | CV RMSE | CV cosine | Test RMSE | Test R² | Test cosine | Test peak error (nm) | Export |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| atomic_mlp_silu_wide | mlp | 0.297 ± 0.022 | 0.707 | 0.315 | -0.039 | 0.592 | 270.0 |  |
| atomic_mlp_tanh | mlp | 0.297 ± 0.020 | 0.702 | 0.325 | -0.110 | 0.583 | 103.3 | spectrum_atomic |
| atomic_knn3 | knn | 0.298 ± 0.021 | 0.702 | 0.325 | -0.112 | 0.553 | 163.3 |  |
| atomic_ridge | ridge | 0.303 ± 0.013 | 0.685 | 0.302 | 0.040 | 0.600 | 156.7 |  |
| atomic_mean | mean | 0.333 ± 0.014 | 0.622 | 0.334 | -0.173 | 0.520 | 256.7 |  |

Split-noise check on the training split: 5× repeated 5-fold CV (per-fold RMSE; pooled R² over each repetition's out-of-fold predictions) and leave-one-chemical-group-out CV.

| Architecture | Repeated-CV RMSE | Pooled R² | Pooled cosine | Group-CV RMSE | Group-CV pooled R² |
| --- | --- | --- | --- | --- | --- |
| atomic_mlp_silu_wide | 0.303 ± 0.021 | 0.144 ± 0.027 | 0.696 | 0.379 ± 0.097 | -0.614 |
| atomic_mlp_tanh | 0.305 ± 0.019 | 0.133 ± 0.027 | 0.685 | 0.372 ± 0.072 | -0.410 |
| atomic_knn3 | 0.306 ± 0.016 | 0.128 ± 0.017 | 0.690 | 0.374 ± 0.079 | -0.434 |
| atomic_ridge | 0.312 ± 0.016 | 0.096 ± 0.036 | 0.675 | 0.394 ± 0.105 | -0.617 |
| atomic_mean | 0.336 ± 0.011 | -0.049 ± 0.007 | 0.616 | 0.355 ± 0.048 | -0.204 |

## Molecular UV absorption envelopes (180–500 nm)

| Architecture | Family | CV RMSE | CV cosine | Family-CV RMSE | Test RMSE | Test R² | Test cosine | Test peak error (nm) | Export |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| molecular_mlp_cascade | mlp | 0.231 ± 0.018 | 0.788 | 0.256 | 0.228 | 0.351 | 0.749 | 39.7 | spectrum_molecular |
| molecular_mlp | mlp | 0.233 ± 0.018 | 0.780 | 0.255 | 0.225 | 0.372 | 0.753 | 43.6 |  |
| molecular_ridge | ridge | 0.245 ± 0.021 | 0.760 | 0.280 | 0.246 | 0.245 | 0.744 | 47.9 |  |
| molecular_ridge_cascade | ridge | 0.247 ± 0.015 | 0.767 | 0.303 | 0.244 | 0.260 | 0.742 | 43.9 |  |
| molecular_knn3 | knn | 0.254 ± 0.015 | 0.754 | 0.271 | 0.234 | 0.317 | 0.742 | 40.0 |  |
| molecular_mean | mean | 0.255 ± 0.022 | 0.756 | 0.270 | 0.287 | -0.029 | 0.733 | 40.6 |  |
| molecular_mpnn | mpnn | 0.263 ± 0.029 | 0.722 | 0.288 | 0.263 | 0.141 | 0.726 | 36.1 |  |
| molecular_mpnn_cascade | mpnn | 0.266 ± 0.019 | 0.690 | 0.283 | 0.256 | 0.183 | 0.709 | 42.4 |  |
| molecular_deepsets | deepsets | 0.270 ± 0.021 | 0.705 | 0.293 | 0.286 | -0.016 | 0.684 | 46.7 |  |

## Atomic → molecular cascade ablation

Negative deltas mean the pooled atomic-model features helped.

| Without | With cascade | ΔCV RMSE | ΔFamily-CV RMSE | ΔTest RMSE |
| --- | --- | --- | --- | --- |
| molecular_ridge | molecular_ridge_cascade | 0.0024 | 0.0237 | -0.0025 |
| molecular_mlp | molecular_mlp_cascade | -0.0012 | 0.0010 | 0.0037 |
| molecular_mpnn | molecular_mpnn_cascade | 0.0026 | -0.0046 | -0.0065 |

