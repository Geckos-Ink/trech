#include "trech/ml/TorchScriptStub.hpp"

namespace trech::ml {

bool TorchScriptStub::Load(const std::string& path) {
  modelPath_ = path;
  return false;
}

bool TorchScriptStub::PredictLabel(const std::vector<float>& /*features*/,
                                   std::string* /*outLabel*/) const {
  return false;
}

const std::string& TorchScriptStub::modelPath() const {
  return modelPath_;
}

} // namespace trech::ml
