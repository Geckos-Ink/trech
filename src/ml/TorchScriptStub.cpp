#include "trech/ml/TorchScriptStub.hpp"

#if defined(TRECH_ENABLE_TORCH)
#include <torch/script.h>
#include <torch/torch.h>
#endif

namespace trech::ml {

void TorchScriptStub::SetLabels(const std::string& predictable, const std::string& exceptional) {
  predictableLabel_ = predictable;
  exceptionalLabel_ = exceptional;
}

bool TorchScriptStub::Load(const std::string& path) {
  modelPath_ = path;
#if defined(TRECH_ENABLE_TORCH)
  module_.reset();
  if (modelPath_.empty()) {
    return false;
  }
  try {
    module_ = std::make_unique<torch::jit::Module>(torch::jit::load(modelPath_));
    module_->eval();
  } catch (const c10::Error&) {
    module_.reset();
    return false;
  }
  return true;
#else
  return false;
#endif
}

bool TorchScriptStub::PredictLabel(const std::vector<float>& features,
                                   std::string* outLabel) const {
  if (!outLabel) {
    return false;
  }
#if defined(TRECH_ENABLE_TORCH)
  if (!module_ || features.empty()) {
    return false;
  }
  torch::NoGradGuard noGrad;
  auto input = torch::from_blob(const_cast<float*>(features.data()),
                                {1, static_cast<long>(features.size())},
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

  if (output.isString()) {
    *outLabel = output.toStringRef();
    return true;
  }
  if (output.isTensor()) {
    auto tensor =
      output.toTensor().to(torch::kCPU).to(torch::kFloat32).flatten().contiguous();
    if (tensor.numel() == 1) {
      const float score = tensor.item<float>();
      *outLabel = score >= 0.5f ? exceptionalLabel_ : predictableLabel_;
      return true;
    }
    if (tensor.numel() == 2) {
      auto scores = tensor.accessor<float, 1>();
      *outLabel = scores[1] >= scores[0] ? exceptionalLabel_ : predictableLabel_;
      return true;
    }
  }
  return false;
#else
  return false;
#endif
}

const std::string& TorchScriptStub::modelPath() const {
  return modelPath_;
}

} // namespace trech::ml
