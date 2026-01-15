#pragma once

#include <string>
#include <vector>

namespace trech::ml {

class TorchScriptStub {
public:
  bool Load(const std::string& path);
  bool PredictLabel(const std::vector<float>& features, std::string* outLabel) const;
  const std::string& modelPath() const;

private:
  std::string modelPath_;
};

} // namespace trech::ml
