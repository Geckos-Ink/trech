#pragma once

// Learned-model side of the engine trace (trech/core/Trace.hpp): which model was loaded with
// which backend (LibTorch TorchScript or a JSON law), every forward pass, and what the engine
// trained online with LibTorch. Observation-only, a no-op when the trace is off.
//
// Category `torch`:
//   info:  model loaded / load failed (component, path, backend, parameters, methods, LibTorch
//          version and threads).
//   debug: one record per training burst (learner, rows, steps, hidden width, loss before/after).
//   trace: one record per forward pass (component, model, backend, input and output digests).
// Tallies: torch.forwards_by_model, torch.forward_failures_by_model,
//          torch.train_steps_by_learner, torch.train_bursts_by_learner.

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

namespace torch::jit {
class Module;
}

namespace trech::ml::mltrace {

// LibTorch identity: version, intra-/inter-op threads, MKL/OpenMP availability.
nlohmann::json torchRuntime();
// Parameter and buffer counts, submodules and methods of a loaded TorchScript module.
nlohmann::json describe(const torch::jit::Module& module);

void modelLoaded(std::string_view component, const std::string& path, std::string_view backend, bool ok,
                 std::string_view note, nlohmann::json details = nullptr);
void forward(std::string_view component, const std::string& path, std::string_view backend,
             const std::vector<double>& inputs, const std::vector<double>& outputs, bool ok);
void trainBurst(std::string_view learner, std::size_t steps, nlohmann::json details);

}  // namespace trech::ml::mltrace
