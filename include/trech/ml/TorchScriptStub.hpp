#pragma once

#include <memory>
#include <string>
#include <vector>

namespace torch::jit {
class Module;
}

namespace trech::ml {

// Stratifier model loader/evaluator with two backends picked by the file
// extension (mirroring OpticsSurrogate):
//   * a TorchScript module (.pt), used only when TRECH_ENABLE_TORCH is built —
//     output contract: label string, or a 1-2 value tensor mapped to the
//     configured predictable/exceptional labels;
//   * a logistic-regression JSON (.json) with standardisation coefficients,
//     which needs no LibTorch — this is the model exported by
//     tools/torch/trech_torch/train_event_stratifier.py, so Geant4-trained
//     event classification works in a stock build.
// The JSON model is validated against the FeaturePipeline schema
// (trech_event_features_v1 feature names, order, and count) at load time.
class TorchScriptStub {
public:
  bool Load(const std::string& path);
  // Predicts the stratification label. outScore (optional) receives the
  // exceptional-class probability/score in [0,1] when the backend provides
  // one (logistic backend and 1-2 value tensor outputs); untouched otherwise.
  bool PredictLabel(const std::vector<float>& features, std::string* outLabel,
                    float* outScore = nullptr) const;
  const std::string& modelPath() const;
  const std::string& note() const { return note_; }
  void SetLabels(const std::string& predictable, const std::string& exceptional);

private:
  // Standardised logistic model:
  //   p(exceptional) = sigmoid(bias + sum_i w_i * (x_i - mean_i) / std_i)
  // Populated when a .json model is loaded; needs no LibTorch.
  struct LogisticModel {
    std::vector<double> weights;
    std::vector<double> mean;
    std::vector<double> std;
    double bias = 0.0;
    double threshold = 0.5;
    bool valid = false;
  };
  bool LoadLogisticJson(const std::string& path);

  std::string modelPath_;
  std::string note_;
  std::string predictableLabel_ = "predictable";
  std::string exceptionalLabel_ = "exceptional";
  LogisticModel logistic_;
#if defined(TRECH_ENABLE_TORCH)
  std::unique_ptr<torch::jit::Module> module_;
#endif
};

} // namespace trech::ml
