#include "trech/ml/MlTrace.hpp"

#include "trech/core/Trace.hpp"

#include <torch/script.h>
#include <torch/version.h>
#include <ATen/Parallel.h>

#include <filesystem>

namespace trech::ml::mltrace {
namespace {

using trech::trace::Level;

std::string modelKey(std::string_view component, const std::string& path) {
  const auto name = std::filesystem::path(path).filename().string();
  return std::string(component) + ":" + (name.empty() ? std::string("(inline)") : name);
}

}  // namespace

nlohmann::json torchRuntime() {
  return {{"libtorch", TORCH_VERSION},
          {"intra_op_threads", at::get_num_threads()},
          {"inter_op_threads", at::get_num_interop_threads()},
          {"mkl", at::hasMKL()},
          {"openmp", at::hasOpenMP()},
          {"mps", at::hasMPS()}};
}

nlohmann::json describe(const torch::jit::Module& module) {
  std::int64_t parameters = 0, tensors = 0, buffers = 0;
  for (const auto& p : module.parameters()) {
    parameters += p.numel();
    ++tensors;
  }
  for (const auto& b : module.buffers()) buffers += b.numel();
  nlohmann::json methods = nlohmann::json::array();
  for (const auto& m : module.get_methods()) methods.push_back(m.name());
  std::size_t submodules = 0;
  for (const auto& child : module.named_modules()) {
    (void)child;
    ++submodules;
  }
  return {{"type", module.type() ? module.type()->name()->qualifiedName() : std::string()},
          {"parameters", parameters},
          {"parameter_tensors", tensors},
          {"buffer_values", buffers},
          {"submodules", submodules},
          {"methods", methods}};
}

void modelLoaded(std::string_view component, const std::string& path, std::string_view backend, bool ok,
                 std::string_view note, nlohmann::json details) {
  if (!trace::enabled(Level::Info, "torch")) return;
  nlohmann::json data = {{"component", std::string(component)},
                         {"path", path},
                         {"backend", std::string(backend)},
                         {"loaded", ok},
                         {"note", std::string(note)}};
  if (!details.is_null()) data["model"] = std::move(details);
  if (backend == "torchscript") data["runtime"] = torchRuntime();
  trace::record(Level::Info, "torch", ok ? "model loaded" : "model load failed", std::move(data));
}

void forward(std::string_view component, const std::string& path, std::string_view backend,
             const std::vector<double>& inputs, const std::vector<double>& outputs, bool ok) {
  if (!trace::active()) return;
  const auto key = modelKey(component, path);
  trace::tally(ok ? "torch.forwards_by_model" : "torch.forward_failures_by_model", key);
  if (!trace::enabled(Level::Trace, "torch")) return;
  const auto budget = trace::options().maxDigestBytes;
  trace::record(Level::Trace, "torch", "forward",
                {{"component", std::string(component)},
                 {"model", key},
                 {"backend", std::string(backend)},
                 {"ok", ok},
                 {"input_size", inputs.size()},
                 {"inputs", trace::digest(inputs, budget)},
                 {"output_size", outputs.size()},
                 {"outputs", trace::digest(outputs, budget)}});
}

void trainBurst(std::string_view learner, std::size_t steps, nlohmann::json details) {
  if (!trace::active()) return;
  trace::tally("torch.train_steps_by_learner", learner, static_cast<double>(steps));
  trace::tally("torch.train_bursts_by_learner", learner);
  if (!trace::enabled(Level::Debug, "torch")) return;
  details["learner"] = std::string(learner);
  details["steps"] = steps;
  details["optimizer"] = details.value("optimizer", std::string("adam"));
  trace::record(Level::Debug, "torch", "training burst", std::move(details));
}

}  // namespace trech::ml::mltrace
