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

  // Reusable scratch for the allocation-free inference path below.  The
  // batched operators (StateEvolution / DiscreteTransition / PairInteraction)
  // evaluate the same model over thousands of elements or pairs per step, so
  // allocating the per-layer activation buffers inside every call costs more
  // than the arithmetic does.  A Workspace carries NO state between calls --
  // every buffer is fully overwritten before it is read -- so reusing one
  // changes nothing but the malloc traffic.
  struct Workspace {
    std::vector<double> a;
    std::vector<double> b;
  };

  // Positional prediction into caller-owned storage: allocates nothing once the
  // workspace is warm.  `inputs` holds inputNames().size() values in declared
  // order; `out` receives outputNames().size() values.  predictVector() is a
  // thin wrapper around this, so there is ONE arithmetic implementation and the
  // two forms cannot drift apart: same accumulation order, bit-identical result.
  bool predictInto(const double* inputs, std::size_t inputCount, double* out,
                   std::size_t outCount, Workspace& workspace) const;

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

    // JOINT starvation: the multivariate version of the check above.  Both
    // radii and occupancy bins are PER FEATURE, so they cannot see a point that
    // is in range on every axis yet nowhere near any training point -- train on
    // (cold, slow) and (hot, fast), ask for (cold, fast), and every per-feature
    // check passes while the model interpolates across a hole it never saw.
    // `jointStarved` is true when NO carried training-region center lies within
    // `jointRadius` (the distance covering the training set's own quantile).
    // `jointDistance` is the exact standardized distance to the nearest center
    // when starved -- the case worth measuring -- and the distance to a
    // covering center (so, <= jointRadius) when not, because the verdict needs
    // only one covering center and the scan stops there.  Only meaningful when
    // `jointMeasured` -- a model with no joint reference reports false/0 and
    // must be read as "not checked", not as "fine".
    bool jointMeasured = false;
    bool jointStarved = false;
    double jointDistance = 0.0;
    double jointRadius = 0.0;
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
  // True when the model carries a JOINT training reference (a covering set of
  // standardized training rows + the radius covering the training set); false
  // -> coverage().jointMeasured is false and the joint check is not performed.
  bool hasJointDomain() const { return !jointCenters_.empty(); }

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

  // Per-OUTPUT held-out accuracy, in that output's own units.  `holdoutR2Min()`
  // above is one number for the whole model; this is the per-quantity split, so
  // a caller can report the uncertainty of the quantity it actually consumed
  // instead of the worst one in the model -- and, with `rmse`, can emit a
  // MEASURED 1-sigma residual rather than a hand-typed sigma.
  //
  // Every field is independently optional: a model trained before the metric
  // existed carries r2/mae but no rmse, and a hand-authored illustrative map
  // carries none.  Absent must be reported as absent (`has*` false), never as
  // 0 -- a 0 residual would read as a perfect model.
  struct OutputAccuracy {
    bool hasR2 = false;
    double r2 = 0.0;
    bool hasMeanAbsoluteError = false;
    double meanAbsoluteError = 0.0;
    bool hasRootMeanSquaredError = false;
    double rootMeanSquaredError = 0.0;  // measured 1-sigma held-out residual
    bool measured() const {
      return hasR2 || hasMeanAbsoluteError || hasRootMeanSquaredError;
    }
  };
  // Accuracy of outputNames()[outputIndex]; all-absent for an out-of-range
  // index or a model that carries no per-output metrics.
  OutputAccuracy outputAccuracy(std::size_t outputIndex) const;
  // True when at least one output carries a metric (cheap pre-check before
  // building a per-output report).
  bool hasOutputAccuracy() const { return hasOutputAccuracy_; }

 private:
  enum class Activation { kNone, kRelu, kSilu, kTanh, kSigmoid };

  struct Layer {
    // Weight block stored INPUT-major: weights[i * rows + o] is the weight from
    // layer input i to output neuron o, so the `rows` weights that all consume
    // input i are contiguous.  The evaluation loop therefore runs over inputs
    // on the outside and neurons on the inside, giving every neuron its own
    // accumulator: each accumulator still sums bias, then i = 0,1,2,... in
    // exactly the declared order (no reassociation), but the inner loop is a
    // contiguous scaled-add the compiler can vectorise -- which a per-neuron
    // dot-product reduction cannot be without reordering the sum.
    //
    // Bit-identity depends on FP contraction being OFF for this translation
    // unit (see the -ffp-contract=off compile option in CMakeLists.txt): with
    // contraction on, the vectorised form fuses multiply-add and the scalar
    // form does not, and the two disagree in the last bits.
    std::vector<double> weights;
    std::vector<double> bias;
    std::size_t rows = 0;  // output neurons  (== bias.size())
    std::size_t cols = 0;  // inputs per neuron
    Activation activation = Activation::kNone;
  };

  // Apply this layer's activation to one accumulated neuron sum.
  static double activate(Activation activation, double sum);

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
  // Joint training reference: `jointCenterCount_` standardized training rows,
  // stored row-major (center c starts at jointCenters_[c * nIn]).
  std::vector<double> jointCenters_;
  std::size_t jointCenterCount_ = 0;
  double jointRadius_ = 0.0;        // standardized distance covering training
  std::vector<std::string> trainedScaleBands_;  // dimension bands seen in training
  bool hasHoldout_ = false;         // held-out metrics carried with the model
  double holdoutR2Min_ = 0.0;       // worst output R^2 on held-out data
  int holdoutSamples_ = 0;          // held-out row count
  // Per-output held-out metrics, indexed like outputNames_ (empty when the
  // model carries none).
  std::vector<OutputAccuracy> outputAccuracy_;
  bool hasOutputAccuracy_ = false;
  std::vector<Layer> layers_;
  bool valid_ = false;

#if defined(TRECH_ENABLE_TORCH)
  std::unique_ptr<torch::jit::Module> module_;
  int torchInputCount_ = 0;
#endif
};

}  // namespace trech::ml
