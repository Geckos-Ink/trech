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
    // Inputs that are WITHIN the trained range but land in a bin the training
    // set never populated -- a "hole" the model interpolated through (density
    // inside the hull, not just its edge; the planner's starved-region signal).
    // Only meaningful when the model carries an `occupancy` histogram.
    std::vector<std::string> starvedInputs;
  };

  // Heuristic per-feature domain radius (in standardized units) used when the
  // model carries no measured `input_domain` block.  ~3 sigma is the textbook
  // outlier edge; the measured hull, when present, always wins over it.
  static constexpr double kDefaultStandardizedDomainRadius = 3.0;

  Coverage coverage(const std::unordered_map<std::string, double>& inputs) const;
  // Positional form of the same check, over the declared input order (the
  // predictVector() layout).  Batched callers (StateEvolution runs one model per
  // element) resolve the input names to slots ONCE and then evaluate thousands
  // of points, so re-hashing a string-keyed map per element would dominate the
  // cost.  coverage(map) builds this vector and delegates, so the two forms
  // report identically by construction.
  Coverage coverageVector(const std::vector<double>& inputs) const;
  bool domainMeasured() const { return domainMeasured_; }
  // True when the model carries a per-feature training occupancy histogram (the
  // starved-region signal); false -> coverage().starvedInputs stays empty.
  bool hasOccupancy() const { return occupancyBins_ > 0; }

  // --- Carried training provenance / quality (empty for hand-authored maps and
  // the committed ridge/logistic, populated by `trech-train-surrogate`) ---

  // The dimension-scale band(s) the training data came from (harvester tags each
  // run atomic/nano/micro/meso/macro).  A stage used at a scale NOT among these
  // is being applied off the band it learned -- an honesty flag the cascade
  // surfaces.  Empty means "unknown" (do not judge).
  const std::vector<std::string>& trainedScaleBands() const {
    return trainedScaleBands_;
  }
  // Held-out accuracy that travels WITH the model, so a stage can report how
  // well it did on data it did not train on (grade-the-gap).  hasHoldout() is
  // false for models that carry no metrics (illustrative maps): then the numbers
  // are meaningless and must be reported as absent, never as 0 == perfect.
  bool hasHoldout() const { return hasHoldout_; }
  double holdoutR2Min() const { return holdoutR2Min_; }  // worst output's R^2
  int holdoutSamples() const { return holdoutSamples_; }

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
  // Fill trainedScaleBands_/holdout* from optional `trained_scale_bands` +
  // `holdout` blocks (absent -> empty bands / hasHoldout_ false).
  void loadTrainingProvenance(const void* jsonPtr);
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
  std::vector<double> inputMin_;    // per-input trained min (for occupancy bins)
  std::vector<double> inputMax_;    // per-input trained max
  std::vector<std::vector<int>> occupancyCounts_;  // nIn x bins training counts
  int occupancyBins_ = 0;           // 0 -> no occupancy histogram carried
  std::vector<std::string> trainedScaleBands_;  // dimension bands seen in training
  bool hasHoldout_ = false;         // held-out metrics carried with the model
  double holdoutR2Min_ = 0.0;       // worst output R^2 on held-out data
  int holdoutSamples_ = 0;          // held-out row count
  std::vector<Layer> layers_;
  bool valid_ = false;

#if defined(TRECH_ENABLE_TORCH)
  std::unique_ptr<torch::jit::Module> module_;
  int torchInputCount_ = 0;
#endif
};

}  // namespace trech::ml
