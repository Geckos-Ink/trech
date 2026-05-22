#include "trech/ml/OpticsSurrogate.hpp"

#if defined(TRECH_ENABLE_TORCH)
#include <torch/script.h>
#include <torch/torch.h>
#endif

#include <algorithm>
#include <unordered_map>

namespace trech::ml {

OpticsSurrogate::OpticsSurrogate() = default;
OpticsSurrogate::~OpticsSurrogate() = default;

bool OpticsSurrogate::load(const std::string& path) {
  modelPath_ = path;
  note_.clear();
#if defined(TRECH_ENABLE_TORCH)
  module_.reset();
  if (modelPath_.empty()) {
    note_ = "empty modelPath";
    return false;
  }
  try {
    module_ = std::make_unique<torch::jit::Module>(torch::jit::load(modelPath_));
    module_->eval();
    note_ = "model loaded";
    return true;
  } catch (const c10::Error& err) {
    module_.reset();
    note_ = std::string("torch::jit::load failed: ") + err.what();
    return false;
  }
#else
  note_ = "Torch disabled at build time (TRECH_ENABLE_TORCH off)";
  return false;
#endif
}

bool OpticsSurrogate::loaded() const {
#if defined(TRECH_ENABLE_TORCH)
  return static_cast<bool>(module_);
#else
  return false;
#endif
}

bool OpticsSurrogate::predict(const std::vector<float>& composition,
                              std::array<float, 3>* out) const {
  if (!out) {
    return false;
  }
  if (composition.size() != static_cast<std::size_t>(kInputFeatureCount)) {
    return false;
  }
#if defined(TRECH_ENABLE_TORCH)
  if (!module_) {
    return false;
  }
  torch::NoGradGuard noGrad;
  auto input = torch::from_blob(const_cast<float*>(composition.data()),
                                {1, static_cast<long>(composition.size())},
                                torch::kFloat32)
                   .clone();
  std::vector<torch::jit::IValue> inputs;
  inputs.emplace_back(input);
  torch::jit::IValue output;
  try {
    output = module_->forward(inputs);
  } catch (const c10::Error&) {
    return false;
  }
  if (!output.isTensor()) {
    return false;
  }
  auto tensor =
      output.toTensor().to(torch::kCPU).to(torch::kFloat32).flatten().contiguous();
  if (tensor.numel() < 3) {
    return false;
  }
  auto accessor = tensor.accessor<float, 1>();
  (*out)[0] = accessor[0];
  (*out)[1] = accessor[1];
  (*out)[2] = accessor[2];
  return true;
#else
  (void)composition;
  return false;
#endif
}

std::vector<float> OpticsSurrogate::encodeComposition(
    const std::vector<std::pair<std::string, double>>& massFractions,
    double densityGcm3) {
  std::vector<float> out(kInputFeatureCount, 0.0f);
  std::unordered_map<std::string, std::size_t> indexFor;
  for (std::size_t i = 0; i < kCompositionElements.size(); ++i) {
    indexFor[kCompositionElements[i]] = i;
  }
  const std::size_t otherIndex = kCompositionElements.size() - 1;
  for (const auto& [name, fraction] : massFractions) {
    const auto it = indexFor.find(name);
    const std::size_t idx = it != indexFor.end() ? it->second : otherIndex;
    out[idx] += static_cast<float>(std::max(0.0, fraction));
  }
  // Renormalize element fractions to sum <= 1.
  double sum = 0.0;
  for (std::size_t i = 0; i + 1 < out.size() - 1; ++i) {
    sum += out[i];
  }
  if (sum > 1.0) {
    for (std::size_t i = 0; i + 1 < out.size() - 1; ++i) {
      out[i] = static_cast<float>(out[i] / sum);
    }
  }
  out.back() = static_cast<float>(densityGcm3);
  return out;
}

}  // namespace trech::ml
