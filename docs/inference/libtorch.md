# From training data to a running model

[Documentation home](../README.md) · [Inference index](README.md) · [Runtime architecture](../architecture/runtime.md)

TRECH uses **PyTorch** in Python training tools and **LibTorch** in its C++ engine.
They share the Torch ecosystem, but they sit at different points in the workflow.
The physical meaning of a target comes from how the training data were produced.
A PyTorch model can learn from Geant4 estimates, measured data or a comparison
solver, depending on the dataset.

## Offline training and deployment

1. **Harvest.** Run Geant4 at chosen conditions and collect labelled targets, such as
   the fraction of primaries that cross a sample uncollided. Save conditions, seeds and
   provenance so whole runs can be held out.
2. **Fit and select.** Train with the Python tools, choose a model using development
   runs and freeze its weights before testing on new conditions. A model carries
   input/output names, scale metadata, and any measured coverage and errors its
   producer recorded.
3. **Export.** Use a supported portable TRECH JSON artifact or a TorchScript module.
   The supported formats and workflows are in [model definitions and checkpoints](ml_models.md)
   and the [Torch trainer reference](../../tools/torch/README.md).
4. **Load and evaluate.** A scenario's `models` entries identify artifacts; the C++
   engine checks the inputs, evaluates the model and reports which stages ran.
   For the separate optics and stratification paths, the config identifies those
   artifacts through their own loader keys.

| Runtime path | What runs |
| --- | --- |
| Portable generic JSON | TRECH C++ evaluates its supported dense or set model and handles named inputs, output transforms and trust metadata. |
| Generic TorchScript | LibTorch loads the module with `torch::jit::load` and runs `forward` in evaluation mode. A `<model>.pt.io.json` sidecar gives generic hook inference named inputs and outputs, tied to the module by SHA-256. |
| Online response domains | TRECH manages the sample buffer, domains and grading. LibTorch provides numerical operations for fitting, including residual networks where enabled. |
| Stratification and optics | Dedicated loaders accept their supported JSON and TorchScript model contracts and record artifact status separately. |

The build currently requires both LibTorch and a Python environment with Torch and
NumPy. A portable JSON forward pass can still use TRECH's own arithmetic. See
[build prerequisites](../build.md) for setup and
[PyTorch's TorchScript serialization design](https://github.com/pytorch/pytorch/blob/main/torch/csrc/jit/docs/serialization.md)
for the module format.

<details>
<summary>Trace a feature across the boundary</summary>

Start from `ctx.predict` or `ctx.cascade` in the [hook API](../engine/scenario_hooks.md#ctxpredict).
The engine assembles an ambient feature map from available event, material and optics
facts, merges explicit values where supplied, and matches feature names to the
loaded model. A required missing feature blocks the prediction. The generic
TorchScript path forms a float32 tensor, calls `forward` and checks the result
before publishing it. Inspect [`GenericSurrogate.cpp`](../../src/ml/GenericSurrogate.cpp)
and the [backend fixtures](../../tests/test_torch_backends.cpp) for the precise contracts.

</details>

<details>
<summary>Check which model actually ran</summary>

Match the prediction's model or stage name to the
[artifact manifest](../engine/output_schema.md#scenario-model-artifact-manifest) and
check the load status and content fingerprint. Then inspect the
[trust trace](../engine/scenario_hooks.md#per-stage-trust-profile-low-confidence-flags-carried-with-the-model)
for coverage, starvation, scale mismatch and any held-out errors. A content hash
identifies the artifact bytes. Held-out results establish what those bytes predicted
under the recorded tests.

</details>

Follow a real [particle-to-observer campaign](particle_observer.md), inspect the
[response-domain study](multiscale_domain_study.md) or explore the
[architecture-search workflow](evolvo_architectures.md).
