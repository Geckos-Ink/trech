#pragma once

#include <memory>
#include <string>
#include <vector>

namespace torch::jit {
class Module;
}

namespace trech::ml {

class TorchScriptStub {
public:
  bool Load(const std::string& path);
  bool PredictLabel(const std::vector<float>& features, std::string* outLabel) const;
  const std::string& modelPath() const;
  void SetLabels(const std::string& predictable, const std::string& exceptional);

private:
  std::string modelPath_;
  std::string predictableLabel_ = "predictable";
  std::string exceptionalLabel_ = "exceptional";
#if defined(TRECH_ENABLE_TORCH)
  std::unique_ptr<torch::jit::Module> module_;
#endif
};

} // namespace trech::ml
