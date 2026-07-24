#pragma once

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace torch::jit {
class Module;
}

namespace trech::ml {

// Scenario-agnostic learned-inference surrogate: maps a set of NAMED numeric
// inputs to a set of NAMED numeric outputs.  This is the general mechanism that
// lets any TRECH scenario (present or future) attach a Torch-trained model and
// call it deterministically from the hook layer (`ctx.predict`), without the
// C++ engine hardcoding what is being predicted.
//
// The portable, LibTorch-free representation is a JSON feed-forward model
// (`generic_surrogate_v1`); it works in a stock build, which is why it is the
// deployment format.  The two earlier specialised models are special cases and
// load through the SAME class so committed models are callable generically:
//   * ridge_optics_n_v1      -> inputs = 14 elements + density_gcm3,
//                               output  = refractive_index (linear)
//   * logistic_stratifier_v1 -> inputs = trech_event_features_v1 names,
//                               output  = p_exceptional (sigmoid)
// When TRECH_ENABLE_TORCH is built a TorchScript `.pt` also loads, but only the
// positional predictVector() path (a raw module carries no feature names).
class GenericSurrogate {
 public:
  GenericSurrogate();
  ~GenericSurrogate();

  GenericSurrogate(const GenericSurrogate&) = delete;
  GenericSurrogate& operator=(const GenericSurrogate&) = delete;

  bool load(const std::string& modelPath);
  bool loaded() const;

  const std::string& modelPath() const { return modelPath_; }
  const std::string& modelId() const { return modelId_; }
  const std::string& note() const { return note_; }
  const std::vector<std::string>& inputNames() const { return inputNames_; }
  const std::vector<std::string>& outputNames() const { return outputNames_; }

  // Named prediction: unknown inputs default to 0, extra inputs are ignored,
  // so scenarios can pass whatever context they have.  Writes the named
  // outputs and returns true on success (JSON models only; a positional `.pt`
  // has no names, so use predictVector()).
  bool predict(const std::unordered_map<std::string, double>& inputs,
               std::unordered_map<std::string, double>* out) const;

  // Positional prediction over the declared input order.
  bool predictVector(const std::vector<double>& inputs,
                     std::vector<double>* out) const;

  // Training-domain coverage: does this input point fall inside the region the
  // model was trained on?  This is the honest "am I extrapolating?" signal that
  // lets the cascade (and ctx.predict) flag a low-confidence prediction instead
  // of silently guessing on inputs the model never saw.  It is a DOMAIN check on
  // the *inputs* (in-distribution?), NOT a fabricated confidence on the output.
  //
  // Metric: each declared input's standardized deviation z_i =
  // (x_i - mean_i)/std_i (missing inputs default to 0, matching predict()).  An
  // input is out-of-domain when |z_i| exceeds its domain radius; that radius is
  // the per-feature training hull edge when the model carries a measured
  // `input_domain` block (domainMeasured() true), otherwise a heuristic default
  // (kDefaultStandardizedDomainRadius).  `extrapolation` is the largest overflow
  // in std units (0 when fully in-domain).
  struct Coverage {
    bool inDomain = true;
    bool domainMeasured = false;       // radii came from training, not the default
    double extrapolation = 0.0;        // max_i max(0, |z_i| - radius_i), std units
    double maxStandardizedDeviation = 0.0;  // max_i |z_i|
    std::vector<std::string> outOfDomainInputs;  // inputs beyond their radius
  };

  // Heuristic per-feature domain radius (in standardized units) used when the
  // model carries no measured `input_domain` block.  ~3 sigma is the textbook
  // outlier edge; the measured hull, when present, always wins over it.
  static constexpr double kDefaultStandardizedDomainRadius = 3.0;

  Coverage coverage(const std::unordered_map<std::string, double>& inputs) const;
  bool domainMeasured() const { return domainMeasured_; }

 private:
  enum class Activation { kNone, kRelu, kSilu, kTanh, kSigmoid };

  struct Layer {
    // weights[o] is the weight row for output neuron o (length = layer inputs).
    std::vector<std::vector<double>> weights;
    std::vector<double> bias;
    Activation activation = Activation::kNone;
  };

  bool loadJson(const std::string& path);
  bool buildFromGeneric(const void* jsonPtr);
  bool buildFromRidge(const void* jsonPtr);
  bool buildFromLogistic(const void* jsonPtr);
  // Fill inputDomainRadius_/domainMeasured_ from an optional `input_domain`
  // block (jsonPtr may be null -> heuristic default for every input).
  void loadInputDomain(const void* jsonPtr, std::size_t nIn);
  static Activation parseActivation(const std::string& name);

  std::string modelPath_;
  std::string modelId_;
  std::string note_;
  std::vector<std::string> inputNames_;
  std::vector<std::string> outputNames_;
  std::vector<double> inputMean_;   // length = inputs (defaults 0)
  std::vector<double> inputStd_;    // length = inputs (defaults 1)
  std::vector<double> outputMean_;  // length = outputs (defaults 0)
  std::vector<double> outputStd_;   // length = outputs (defaults 1)
  std::vector<double> inputDomainRadius_;  // per-input |z| hull edge (length nIn)
  bool domainMeasured_ = false;     // inputDomainRadius_ came from training
  std::vector<Layer> layers_;
  bool valid_ = false;

#if defined(TRECH_ENABLE_TORCH)
  std::unique_ptr<torch::jit::Module> module_;
  int torchInputCount_ = 0;
#endif
};

}  // namespace trech::ml
