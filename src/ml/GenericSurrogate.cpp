#include "trech/ml/GenericSurrogate.hpp"
#include "trech/core/Provenance.hpp"

#if defined(TRECH_ENABLE_TORCH)
#include <torch/script.h>
#include <torch/torch.h>
#endif

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <sstream>
#include <utility>

#include <nlohmann/json.hpp>

namespace trech::ml {

namespace {

bool endsWith(const std::string& s, const std::string& suffix) {
  return s.size() >= suffix.size() &&
         s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// The 14 optics composition element slots (mirrors OpticsSurrogate); density is
// the implicit 15th input for ridge_optics_n_v1 models.
const char* const kOpticsElements[] = {"H",  "C",  "N", "O",  "F",
                                       "Na", "Mg", "Al", "Si", "P",
                                       "S",  "Cl", "I",  "other"};

}  // namespace

GenericSurrogate::GenericSurrogate() = default;
GenericSurrogate::~GenericSurrogate() = default;

GenericSurrogate::Activation GenericSurrogate::parseActivation(
    const std::string& name) {
  if (name == "relu") return Activation::kRelu;
  if (name == "silu" || name == "swish") return Activation::kSilu;
  if (name == "tanh") return Activation::kTanh;
  if (name == "sigmoid" || name == "logistic") return Activation::kSigmoid;
  return Activation::kNone;  // "none"/"linear"/identity/unknown
}

bool GenericSurrogate::parseLayers(const void* jsonArray, std::size_t inputs,
                                   std::vector<Layer>* out, const char* label) {
  const auto& array = *static_cast<const nlohmann::json*>(jsonArray);
  if (!array.is_array() || array.empty()) {
    note_ = std::string("generic model ") + label + " has no layers";
    return false;
  }
  std::size_t layerInputs = inputs;
  for (const auto& layerJson : array) {
    if (!layerJson.is_object() || !layerJson.contains("weights") ||
        !layerJson.at("weights").is_array() || !layerJson.contains("bias") ||
        !layerJson.at("bias").is_array()) {
      note_ = std::string("generic model ") + label + " layer missing weights|bias";
      return false;
    }
    const auto rows =
        layerJson.at("weights").get<std::vector<std::vector<double>>>();
    Layer layer;
    layer.bias = layerJson.at("bias").get<std::vector<double>>();
    layer.activation = parseActivation(
        layerJson.value("activation", std::string("none")));
    if (rows.empty() || rows.size() != layer.bias.size()) {
      note_ = std::string("generic model ") + label + " layer weights/bias size mismatch";
      return false;
    }
    for (const auto& row : rows) {
      if (row.size() != layerInputs) {
        note_ = std::string("generic model ") + label + " layer input width mismatch";
        return false;
      }
    }
    layer.rows = rows.size();
    layer.cols = layerInputs;
    // Transpose into the input-major layout the evaluation loop wants.
    layer.weights.assign(layer.rows * layer.cols, 0.0);
    for (std::size_t o = 0; o < layer.rows; ++o) {
      for (std::size_t i = 0; i < layer.cols; ++i) {
        layer.weights[i * layer.rows + o] = rows[o][i];
      }
    }
    layerInputs = layer.rows;  // this layer's output width
    out->push_back(std::move(layer));
  }
  return true;
}

bool GenericSurrogate::buildSetNetwork(const void* networkPtr, std::size_t nIn,
                                       std::size_t nOut) {
  const auto& n = *static_cast<const nlohmann::json*>(networkPtr);
  const std::string kind = n.value("kind", std::string());
  if (kind != "deepsets" && kind != "mpnn") {
    note_ = "v3 network.kind must be deepsets or mpnn";
    return false;
  }
  auto count = [&](const char* key, std::size_t fallback, bool required,
                   std::size_t* value) {
    if (!n.contains(key)) {
      *value = fallback;
      return !required;
    }
    if (!n.at(key).is_number_integer() || n.at(key).get<long long>() < 0) return false;
    *value = static_cast<std::size_t>(n.at(key).get<long long>());
    return true;
  };
  SetNetwork set;
  if (!count("elements", 0, true, &set.elements) ||
      !count("element_features", 0, true, &set.features) ||
      !count("context_features", 0, false, &set.context) || set.elements == 0 ||
      set.features == 0 || set.elements * set.features + set.context != nIn) {
    note_ = "v3 set layout (elements x element_features + context_features) "
            "does not match input_features";
    return false;
  }
  const std::string pool = n.value("pool", std::string("sum"));
  if (pool == "sum") set.pool = Pool::kSum;
  else if (pool == "mean") set.pool = Pool::kMean;
  else if (pool == "max") set.pool = Pool::kMax;
  else {
    note_ = "v3 pool must be sum, mean or max";
    return false;
  }
  if (n.contains("mask_feature") && !n.at("mask_feature").is_null()) {
    if (!count("mask_feature", 0, true, &set.maskFeature) ||
        set.maskFeature >= set.features) {
      note_ = "v3 mask_feature must index an element feature";
      return false;
    }
    set.hasMask = true;
  }
  if (!n.contains("phi") || !parseLayers(&n.at("phi"), set.features, &set.phi, "phi")) {
    if (!n.contains("phi")) note_ = "v3 network needs phi layers";
    return false;
  }
  set.hidden = set.phi.back().rows;
  if (!n.contains("rho") ||
      !parseLayers(&n.at("rho"), set.hidden + set.context, &set.rho, "rho")) {
    if (!n.contains("rho")) note_ = "v3 network needs rho layers";
    return false;
  }
  if (set.rho.back().rows != nOut) {
    note_ = "v3 rho output width != output_features";
    return false;
  }
  if (kind == "mpnn") {
    if (!n.contains("rounds") || !n.at("rounds").is_number_integer() ||
        n.at("rounds").get<int>() < 1 || n.at("rounds").get<int>() > 16) {
      note_ = "mpnn rounds must be an integer in [1, 16]";
      return false;
    }
    set.rounds = n.at("rounds").get<int>();
    if (n.contains("relative_features")) {
      const auto& rel = n.at("relative_features");
      if (!rel.is_array()) {
        note_ = "mpnn relative_features must be an array";
        return false;
      }
      for (const auto& v : rel) {
        if (!v.is_number_integer() || v.get<long long>() < 0 ||
            static_cast<std::size_t>(v.get<long long>()) >= set.features) {
          note_ = "mpnn relative_features must index element features";
          return false;
        }
        set.relative.push_back(static_cast<std::size_t>(v.get<long long>()));
      }
    }
    const std::string aggregate = n.value("aggregate", std::string("mean"));
    if (aggregate != "mean" && aggregate != "sum") {
      note_ = "mpnn aggregate must be sum or mean";
      return false;
    }
    set.meanAggregate = aggregate == "mean";
    if (!n.contains("message") ||
        !parseLayers(&n.at("message"), 2 * set.hidden + set.relative.size(),
                     &set.message, "message") ||
        set.message.back().rows != set.hidden) {
      if (note_.empty() || note_.find("message") == std::string::npos)
        note_ = "mpnn message layers must map [h_i, h_j, rel] to the state width";
      return false;
    }
    if (!n.contains("update") ||
        !parseLayers(&n.at("update"), 2 * set.hidden, &set.update, "update") ||
        set.update.size() != 1 || set.update.back().rows != set.hidden) {
      note_ = "mpnn update must be one layer mapping [h_i, m_i] to the state width";
      return false;
    }
    networkKind_ = NetworkKind::kMpnn;
  } else {
    networkKind_ = NetworkKind::kDeepSets;
  }
  set_ = std::move(set);
  return true;
}

const char* GenericSurrogate::networkKind() const {
  switch (networkKind_) {
    case NetworkKind::kDeepSets:
      return "deepsets";
    case NetworkKind::kMpnn:
      return "mpnn";
    case NetworkKind::kDense:
      break;
  }
  return "dense";
}

bool GenericSurrogate::buildFromGeneric(const void* jsonPtr) {
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  const std::string kindName = j.value("model", std::string());
  const bool setNetwork = kindName == "generic_surrogate_v3";
  const bool encoded = kindName == "generic_surrogate_v2" || setNetwork;
  // v2/v3 nest their network so an older reader fails closed rather than
  // silently interpreting a log-space prediction (or a set network's element
  // blocks) as a plain dense model.
  if (encoded && (!j.contains("network") || !j.at("network").is_object())) {
    note_ = "v2/v3 model requires a nested network";
    return false;
  }
  const auto& network = encoded ? j.at("network") : j;
  if (!j.contains("input_features") || !j.at("input_features").is_array() ||
      !j.contains("output_features") || !j.at("output_features").is_array() ||
      (!setNetwork && (!network.contains("layers") || !network.at("layers").is_array()))) {
    note_ = "generic model missing input_features|output_features|layers";
    return false;
  }
  inputNames_ = j.at("input_features").get<std::vector<std::string>>();
  outputNames_ = j.at("output_features").get<std::vector<std::string>>();
  const std::size_t nIn = inputNames_.size();
  const std::size_t nOut = outputNames_.size();
  if (nIn == 0 || nOut == 0) {
    note_ = "generic model has empty input/output feature list";
    return false;
  }

  auto readScaler = [&](const char* key, std::size_t len, double fill,
                        std::vector<double>& out) -> bool {
    if (!j.contains(key)) {
      out.assign(len, fill);
      return true;
    }
    if (!j.at(key).is_array() || j.at(key).size() != len) {
      note_ = std::string("generic model ") + key + " wrong length";
      return false;
    }
    out = j.at(key).get<std::vector<double>>();
    return true;
  };
  if (!readScaler("input_mean", nIn, 0.0, inputMean_) ||
      !readScaler("input_std", nIn, 1.0, inputStd_) ||
      !readScaler("output_mean", nOut, 0.0, outputMean_) ||
      !readScaler("output_std", nOut, 1.0, outputStd_)) {
    return false;
  }
  for (double& s : inputStd_) {
    if (std::abs(s) < 1e-12) s = 1.0;
  }

  outputTransforms_.assign(nOut, OutputTransform::kIdentity);
  if (j.contains("output_transforms")) {
    const auto& transforms = j.at("output_transforms");
    if (!encoded || !transforms.is_array() || transforms.size() != nOut) {
      note_ = "output_transforms requires v2 and one entry per output";
      return false;
    }
    for (std::size_t o = 0; o < nOut; ++o) {
      if (!transforms[o].is_string() ||
          (transforms[o] != "identity" && transforms[o] != "exp" &&
           transforms[o] != "sigmoid")) {
        note_ = "unsupported output transform";
        return false;
      }
      if (transforms[o] == "exp") outputTransforms_[o] = OutputTransform::kExp;
      if (transforms[o] == "sigmoid") outputTransforms_[o] = OutputTransform::kSigmoid;
    }
  } else if (encoded) {
    note_ = "v2/v3 model requires output_transforms";
    return false;
  }

  if (setNetwork) {
    if (!buildSetNetwork(&network, nIn, nOut)) return false;
  } else {
    if (!parseLayers(&network.at("layers"), nIn, &layers_, "dense")) {
      layers_.clear();
      return false;
    }
    if (layers_.back().rows != nOut) {
      note_ = "generic model final layer width != output_features";
      return false;
    }
  }
  loadInputDomain(&j, nIn);
  loadTrainingProvenance(&j);
  modelId_ = j.value("model", std::string("generic_surrogate_v1"));
  valid_ = true;
  note_ = "generic model loaded (" + std::to_string(nIn) + " in -> " +
          std::to_string(nOut) + " out, " +
          (setNetwork ? std::string(networkKind()) + " over " +
                            std::to_string(set_.elements) + " elements"
                      : std::to_string(layers_.size()) + " layer(s)") +
          (domainMeasured_ ? ", measured domain" : "") + ")";
  return true;
}

void GenericSurrogate::loadInputDomain(const void* jsonPtr, std::size_t nIn) {
  // Default: no measured hull -> a heuristic radius for every input, no range
  // or occupancy histogram (so the starved-region signal stays off).
  domainMeasured_ = false;
  inputDomainRadius_.assign(nIn, kDefaultStandardizedDomainRadius);
  inputMin_.clear();
  inputMax_.clear();
  occupancyCounts_.clear();
  occupancyBins_ = 0;
  jointCenters_.clear();
  jointCenterCount_ = 0;
  jointRadius_ = 0.0;
  if (!jsonPtr) {
    return;
  }
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  if (!j.contains("input_domain") || !j.at("input_domain").is_object()) {
    return;
  }
  const auto& dom = j.at("input_domain");
  if (dom.contains("standardized_radius")) {
    const auto& r = dom.at("standardized_radius");
    if (r.is_number()) {
      inputDomainRadius_.assign(nIn, std::max(0.0, r.get<double>()));
      domainMeasured_ = true;
    } else if (r.is_array() && r.size() == nIn) {
      inputDomainRadius_ = r.get<std::vector<double>>();
      for (double& v : inputDomainRadius_) {
        v = std::max(0.0, v);
      }
      domainMeasured_ = true;
    }
    // A malformed/length-mismatched radius leaves the heuristic default in place.
  }

  // Per-feature training range + occupancy histogram (the starved-region signal:
  // a value in-range but in an empty bin is a hole the model interpolated).
  auto readVec = [&](const char* key, std::vector<double>& out) {
    if (dom.contains(key) && dom.at(key).is_array() &&
        dom.at(key).size() == nIn) {
      out = dom.at(key).get<std::vector<double>>();
    }
  };
  readVec("input_min", inputMin_);
  readVec("input_max", inputMax_);
  if (dom.contains("occupancy") && dom.at("occupancy").is_object() &&
      inputMin_.size() == nIn && inputMax_.size() == nIn) {
    const auto& occ = dom.at("occupancy");
    const int bins = occ.value("bins", 0);
    if (bins > 0 && occ.contains("counts") && occ.at("counts").is_array() &&
        occ.at("counts").size() == nIn) {
      std::vector<std::vector<int>> counts;
      counts.reserve(nIn);
      bool ok = true;
      for (const auto& row : occ.at("counts")) {
        if (!row.is_array() || row.size() != static_cast<std::size_t>(bins)) {
          ok = false;
          break;
        }
        counts.push_back(row.get<std::vector<int>>());
      }
      if (ok) {
        occupancyCounts_ = std::move(counts);
        occupancyBins_ = bins;
      }
    }
  }

  // Joint (multivariate) training reference: a covering set of standardized
  // training rows plus the distance that covers the training set's own
  // quantile.  Both blocks above are per-feature and cannot see a point that is
  // in range on every axis yet far from every training point.
  if (dom.contains("joint") && dom.at("joint").is_object()) {
    const auto& joint = dom.at("joint");
    const double radius = joint.value("radius", -1.0);
    if (radius >= 0.0 && joint.contains("centers") &&
        joint.at("centers").is_array()) {
      std::vector<double> flat;
      std::size_t count = 0;
      bool ok = true;
      for (const auto& center : joint.at("centers")) {
        if (!center.is_array() || center.size() != nIn) {
          ok = false;  // a malformed reference is ignored, never half-applied
          break;
        }
        for (const auto& value : center) {
          if (!value.is_number()) {
            ok = false;
            break;
          }
          flat.push_back(value.get<double>());
        }
        if (!ok) {
          break;
        }
        ++count;
      }
      if (ok && count > 0) {
        jointCenters_ = std::move(flat);
        jointCenterCount_ = count;
        jointRadius_ = radius;
      }
    }
  }
}

void GenericSurrogate::loadTrainingProvenance(const void* jsonPtr) {
  trainedScaleBands_.clear();
  hasHoldout_ = false;
  holdoutR2Min_ = 0.0;
  holdoutSamples_ = 0;
  outputAccuracy_.clear();
  hasOutputAccuracy_ = false;
  if (!jsonPtr) {
    return;
  }
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  // Dimension-scale band(s) the training data came from (harvester tags each
  // run); used by the cascade to flag a stage applied off its trained band.
  if (j.contains("trained_scale_bands") &&
      j.at("trained_scale_bands").is_array()) {
    for (const auto& b : j.at("trained_scale_bands")) {
      if (b.is_string()) {
        trainedScaleBands_.push_back(b.get<std::string>());
      }
    }
  }
  // Held-out accuracy carried with the model (grade-the-gap). Require r2_min so
  // a partial/malformed block is treated as "no metrics" rather than a fake 0.
  if (j.contains("holdout") && j.at("holdout").is_object()) {
    const auto& h = j.at("holdout");
    if (h.contains("r2_min") && h.at("r2_min").is_number()) {
      holdoutR2Min_ = h.at("r2_min").get<double>();
      holdoutSamples_ = h.value("n", 0);
      hasHoldout_ = true;
    }
    // Per-output split: `r2`/`mae`/`rmse` are name->value objects keyed by
    // output feature. Each is optional and read independently, so a model
    // trained before a metric existed reports the ones it has and nothing more.
    outputAccuracy_.assign(outputNames_.size(), OutputAccuracy{});
    auto readMetric = [&](const char* key, bool OutputAccuracy::*present,
                          double OutputAccuracy::*value) {
      if (!h.contains(key) || !h.at(key).is_object()) {
        return;
      }
      const auto& block = h.at(key);
      for (std::size_t o = 0; o < outputNames_.size(); ++o) {
        const auto it = block.find(outputNames_[o]);
        if (it != block.end() && it->is_number()) {
          outputAccuracy_[o].*present = true;
          outputAccuracy_[o].*value = it->get<double>();
          hasOutputAccuracy_ = true;
        }
      }
    };
    readMetric("r2", &OutputAccuracy::hasR2, &OutputAccuracy::r2);
    readMetric("mae", &OutputAccuracy::hasMeanAbsoluteError,
               &OutputAccuracy::meanAbsoluteError);
    readMetric("rmse", &OutputAccuracy::hasRootMeanSquaredError,
               &OutputAccuracy::rootMeanSquaredError);
  }
  // Optional calibrated prediction interval: {nominal_coverage in (0,1),
  // half_width: {output: value >= 0}}. Independent of `holdout`; a block
  // without a valid nominal coverage is ignored (no coverage claim -> no
  // interval), and a negative or non-finite half-width is skipped per output.
  if (j.contains("prediction_interval") &&
      j.at("prediction_interval").is_object()) {
    const auto& pi = j.at("prediction_interval");
    const bool coverageOk = pi.contains("nominal_coverage") &&
                            pi.at("nominal_coverage").is_number();
    const double coverage =
        coverageOk ? pi.at("nominal_coverage").get<double>() : 0.0;
    if (coverageOk && coverage > 0.0 && coverage < 1.0 &&
        pi.contains("half_width") && pi.at("half_width").is_object()) {
      if (outputAccuracy_.size() != outputNames_.size()) {
        outputAccuracy_.assign(outputNames_.size(), OutputAccuracy{});
      }
      const auto& block = pi.at("half_width");
      for (std::size_t o = 0; o < outputNames_.size(); ++o) {
        const auto it = block.find(outputNames_[o]);
        if (it == block.end() || !it->is_number()) continue;
        const double width = it->get<double>();
        if (!std::isfinite(width) || width < 0.0) continue;
        outputAccuracy_[o].hasIntervalHalfWidth = true;
        outputAccuracy_[o].intervalHalfWidth = width;
        outputAccuracy_[o].intervalCoverage = coverage;
        hasOutputAccuracy_ = true;
      }
    }
  }
  if (!hasOutputAccuracy_) {
    outputAccuracy_.clear();
  }
}

GenericSurrogate::OutputAccuracy GenericSurrogate::outputAccuracy(
    std::size_t outputIndex) const {
  if (outputIndex < outputAccuracy_.size()) {
    return outputAccuracy_[outputIndex];
  }
  return OutputAccuracy{};  // absent, never a fabricated 0
}

bool GenericSurrogate::buildFromRidge(const void* jsonPtr) {
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  // ridge_optics_n_v1: standardised linear n = bias + sum w_i (x_i-mean_i)/std_i
  // over 14 element slots + density.
  const std::size_t n = sizeof(kOpticsElements) / sizeof(kOpticsElements[0]) + 1;
  auto readVec = [&](const char* key, std::vector<double>& out) -> bool {
    if (!j.contains(key) || !j.at(key).is_array() || j.at(key).size() != n) {
      return false;
    }
    out = j.at(key).get<std::vector<double>>();
    return true;
  };
  std::vector<double> weights, mean, std_;
  if (!readVec("weights", weights) || !readVec("mean", mean) ||
      !readVec("std", std_)) {
    note_ = "ridge_optics_n_v1 missing/wrong-length weights|mean|std";
    return false;
  }
  inputNames_.assign(kOpticsElements,
                     kOpticsElements + (n - 1));
  inputNames_.push_back("density_gcm3");
  outputNames_ = {"refractive_index"};
  inputMean_ = mean;
  inputStd_ = std_;
  for (double& s : inputStd_) {
    if (std::abs(s) < 1e-12) s = 1.0;
  }
  outputMean_ = {0.0};
  outputStd_ = {1.0};
  Layer layer;
  layer.rows = 1;
  layer.cols = weights.size();
  layer.weights = std::move(weights);
  layer.bias = {j.value("bias", 0.0)};
  layer.activation = Activation::kNone;
  layers_.push_back(std::move(layer));
  loadInputDomain(&j, n);  // ridge models carry no hull today -> heuristic
  modelId_ = "ridge_optics_n_v1";
  valid_ = true;
  note_ = "ridge optics model loaded as generic (n)";
  return true;
}

bool GenericSurrogate::buildFromLogistic(const void* jsonPtr) {
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  if (!j.contains("feature_names") || !j.at("feature_names").is_array()) {
    note_ = "logistic_stratifier_v1 missing feature_names";
    return false;
  }
  inputNames_ = j.at("feature_names").get<std::vector<std::string>>();
  const std::size_t n = inputNames_.size();
  auto readVec = [&](const char* key, std::vector<double>& out) -> bool {
    if (!j.contains(key) || !j.at(key).is_array() || j.at(key).size() != n) {
      return false;
    }
    out = j.at(key).get<std::vector<double>>();
    return true;
  };
  std::vector<double> weights, mean, std_;
  if (!readVec("weights", weights) || !readVec("mean", mean) ||
      !readVec("std", std_)) {
    note_ = "logistic_stratifier_v1 missing/wrong-length weights|mean|std";
    return false;
  }
  outputNames_ = {"p_exceptional"};
  inputMean_ = mean;
  inputStd_ = std_;
  for (double& s : inputStd_) {
    if (std::abs(s) < 1e-12) s = 1.0;
  }
  outputMean_ = {0.0};
  outputStd_ = {1.0};
  Layer layer;
  layer.rows = 1;
  layer.cols = weights.size();
  layer.weights = std::move(weights);
  layer.bias = {j.value("bias", 0.0)};
  layer.activation = Activation::kSigmoid;
  layers_.push_back(std::move(layer));
  loadInputDomain(&j, n);  // stratifier models carry no hull today -> heuristic
  modelId_ = "logistic_stratifier_v1";
  valid_ = true;
  note_ = "logistic stratifier model loaded as generic (p_exceptional)";
  return true;
}

bool GenericSurrogate::loadJson(const std::string& bytes) {
  nlohmann::json j;
  try {
    j = nlohmann::json::parse(bytes);
  } catch (const std::exception& e) {
    note_ = std::string("model json parse failed: ") + e.what();
    return false;
  }
  const std::string kind = j.value("model", std::string(""));
  bool built = false;
  if (kind == "ridge_optics_n_v1") {
    built = buildFromRidge(&j);
  } else if (kind == "logistic_stratifier_v1") {
    built = buildFromLogistic(&j);
  } else if (kind.empty() || kind == "generic_surrogate_v1" || kind == "generic_surrogate_v2" ||
             kind == "generic_surrogate_v3") {
    built = buildFromGeneric(&j);
  } else {
    note_ = "unsupported generic model schema: " + kind;
    return false;
  }
  if (!built || !j.contains("feature_units")) return built;
  const auto& units = j.at("feature_units");
  auto readUnits = [&](const char* side, const std::vector<std::string>& names,
                       std::unordered_map<std::string, std::string>& result) {
    if (!units.is_object() || units.size() != 2 || !units.contains(side) ||
        !units.at(side).is_object() || units.at(side).size() != names.size()) return false;
    for (const auto& name : names) {
      const auto& map = units.at(side);
      if (!map.contains(name) || !map.at(name).is_string()) return false;
      const auto label = map.at(name).get<std::string>();
      if (label.find_first_not_of(" \t\r\n\f\v") == std::string::npos ||
          label.find('\0') != std::string::npos || !result.emplace(name, label).second) return false;
    }
    return true;
  };
  if (!readUnits("inputs", inputNames_, inputUnits_) ||
      !readUnits("outputs", outputNames_, outputUnits_)) {
    note_ = "feature_units requires complete named input/output unit maps";
    inputUnits_.clear();
    outputUnits_.clear();
    valid_ = false;
    return false;
  }
  return true;
}

bool GenericSurrogate::load(const std::string& path) {
  modelPath_ = path;
  modelId_.clear();
  contentId_.clear();
  contentSha256_.clear();
  contentSizeBytes_ = 0;
  note_.clear();
  inputNames_.clear();
  outputNames_.clear();
  inputUnits_.clear();
  outputUnits_.clear();
  inputMean_.clear();
  inputStd_.clear();
  outputMean_.clear();
  outputStd_.clear();
  outputTransforms_.clear();
  inputDomainRadius_.clear();
  domainMeasured_ = false;
  inputMin_.clear();
  inputMax_.clear();
  occupancyCounts_.clear();
  occupancyBins_ = 0;
  trainedScaleBands_.clear();
  hasHoldout_ = false;
  holdoutR2Min_ = 0.0;
  holdoutSamples_ = 0;
  outputAccuracy_.clear();
  hasOutputAccuracy_ = false;
  layers_.clear();
  networkKind_ = NetworkKind::kDense;
  set_ = SetNetwork{};
  valid_ = false;
#if defined(TRECH_ENABLE_TORCH)
  module_.reset();
  torchInputCount_ = 0;
#endif
  if (modelPath_.empty()) {
    note_ = "empty modelPath";
    return false;
  }
  // Read once: hashing a reopened path could describe a replacement artifact
  // rather than the bytes from which this model's weights were loaded.
  std::ifstream in(modelPath_, std::ios::binary);
  if (!in) {
    note_ = "cannot open model: " + modelPath_;
    return false;
  }
  const std::string bytes((std::istreambuf_iterator<char>(in)),
                           std::istreambuf_iterator<char>());
  if (in.bad()) {
    note_ = "cannot read model: " + modelPath_;
    return false;
  }
  if (endsWith(modelPath_, ".json")) {
    if (!loadJson(bytes)) return false;
    contentId_ = "fnv1a64:" + trech::fnv1a64Hex(bytes);
    contentSha256_ = trech::sha256Hex(bytes);
    contentSizeBytes_ = bytes.size();
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  try {
    std::istringstream stream(bytes, std::ios::in | std::ios::binary);
    module_ = std::make_unique<torch::jit::Module>(torch::jit::load(stream));
    module_->eval();
    contentId_ = "fnv1a64:" + trech::fnv1a64Hex(bytes);
    contentSha256_ = trech::sha256Hex(bytes);
    contentSizeBytes_ = bytes.size();
    note_ = "torchscript model loaded (positional; use predictVector)";
    return true;
  } catch (const std::exception&) {
    module_.reset();
    note_ = "torch::jit::load failed";
    return false;
  }
#else
  note_ = "non-json model needs LibTorch, which is off (TRECH_ENABLE_TORCH); "
          "supply a generic .json model instead";
  return false;
#endif
}

bool GenericSurrogate::loaded() const {
  if (valid_) {
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  return static_cast<bool>(module_);
#else
  return false;
#endif
}

double GenericSurrogate::activate(Activation activation, double sum) {
  switch (activation) {
    case Activation::kRelu:
      return sum > 0.0 ? sum : 0.0;
    case Activation::kSilu:
      return sum / (1.0 + std::exp(-sum));
    case Activation::kTanh:
      return std::tanh(sum);
    case Activation::kSigmoid:
      return 1.0 / (1.0 + std::exp(-sum));
    case Activation::kNone:
      break;
  }
  return sum;
}

void GenericSurrogate::evalLayer(const Layer& layer, const double* in,
                                 double* out) {
  // Every neuron accumulates bias first, then input 0, 1, 2, ... -- the
  // same term order as a per-neuron dot product, so the result is
  // bit-identical while the inner loop stays vectorisable.
  for (std::size_t o = 0; o < layer.rows; ++o) {
    out[o] = layer.bias[o];
  }
  const double* weights = layer.weights.data();
  for (std::size_t i = 0; i < layer.cols; ++i) {
    const double activation = in[i];
    const double* column = weights + i * layer.rows;
    for (std::size_t o = 0; o < layer.rows; ++o) {
      // Explicit single-rounding fused multiply-add: naming the fusion
      // fixes the rounding of every accumulation step instead of leaving
      // it to whether an optimiser chose to contract `a += b * c`.
      out[o] = std::fma(column[o], activation, out[o]);
    }
  }
  for (std::size_t o = 0; o < layer.rows; ++o) {
    out[o] = activate(layer.activation, out[o]);
  }
}

std::vector<double>& GenericSurrogate::runDense(const std::vector<Layer>& layers,
                                                const double* in,
                                                std::vector<double>& x,
                                                std::vector<double>& y) {
  const double* current = in;
  std::vector<double>* target = &x;
  for (const Layer& layer : layers) {
    target->resize(layer.rows);
    evalLayer(layer, current, target->data());
    current = target->data();
    target = target == &x ? &y : &x;
  }
  // `target` now points at the buffer NOT written last.
  return target == &x ? y : x;
}

std::vector<double>* GenericSurrogate::predictSet(const double* z,
                                                  const double* raw,
                                                  Workspace& w) const {
  const SetNetwork& s = set_;
  const std::size_t E = s.elements, F = s.features, H = s.hidden;
  // Presence from the RAW mask feature (> 0.5), never from standardised units.
  auto present = [&](std::size_t e) {
    return !s.hasMask || raw[e * F + s.maskFeature] > 0.5;
  };
  w.state.resize(E * H);
  for (std::size_t e = 0; e < E; ++e) {
    const auto& h = runDense(s.phi, z + e * F, w.scratchA, w.scratchB);
    std::copy(h.begin(), h.begin() + static_cast<std::ptrdiff_t>(H),
              w.state.begin() + static_cast<std::ptrdiff_t>(e * H));
  }
  if (networkKind_ == NetworkKind::kMpnn) {
    const std::size_t R = s.relative.size();
    for (int round = 0; round < s.rounds; ++round) {
      w.nextState.assign(w.state.begin(), w.state.end());
      for (std::size_t i = 0; i < E; ++i) {
        if (!present(i)) continue;  // absent elements neither send nor pool
        w.aggregate.assign(H, 0.0);
        std::size_t neighbours = 0;
        for (std::size_t j = 0; j < E; ++j) {
          if (j == i || !present(j)) continue;
          w.b.resize(2 * H + R);
          std::copy(w.state.begin() + static_cast<std::ptrdiff_t>(i * H),
                    w.state.begin() + static_cast<std::ptrdiff_t>((i + 1) * H), w.b.begin());
          std::copy(w.state.begin() + static_cast<std::ptrdiff_t>(j * H),
                    w.state.begin() + static_cast<std::ptrdiff_t>((j + 1) * H),
                    w.b.begin() + static_cast<std::ptrdiff_t>(H));
          for (std::size_t r = 0; r < R; ++r) {
            const std::size_t k = s.relative[r];
            w.b[2 * H + r] = z[j * F + k] - z[i * F + k];
          }
          const auto& m = runDense(s.message, w.b.data(), w.scratchA, w.scratchB);
          for (std::size_t h = 0; h < H; ++h) w.aggregate[h] += m[h];
          ++neighbours;
        }
        if (s.meanAggregate && neighbours > 0) {
          for (double& v : w.aggregate) v /= static_cast<double>(neighbours);
        }
        w.b.resize(2 * H);
        std::copy(w.state.begin() + static_cast<std::ptrdiff_t>(i * H),
                  w.state.begin() + static_cast<std::ptrdiff_t>((i + 1) * H), w.b.begin());
        std::copy(w.aggregate.begin(), w.aggregate.end(),
                  w.b.begin() + static_cast<std::ptrdiff_t>(H));
        const auto& u = runDense(s.update, w.b.data(), w.scratchA, w.scratchB);
        std::copy(u.begin(), u.begin() + static_cast<std::ptrdiff_t>(H),
                  w.nextState.begin() + static_cast<std::ptrdiff_t>(i * H));
      }
      std::swap(w.state, w.nextState);
    }
  }
  // Pool present element states in ascending element order, then append the
  // standardised context inputs: the readout's input.
  w.b.assign(H + s.context, 0.0);
  std::size_t count = 0;
  for (std::size_t e = 0; e < E; ++e) {
    if (!present(e)) continue;
    const double* h = w.state.data() + e * H;
    for (std::size_t k = 0; k < H; ++k) {
      if (s.pool == Pool::kMax) {
        w.b[k] = count == 0 ? h[k] : std::max(w.b[k], h[k]);
      } else {
        w.b[k] += h[k];
      }
    }
    ++count;
  }
  if (s.pool == Pool::kMean && count > 0) {
    for (std::size_t k = 0; k < H; ++k) w.b[k] /= static_cast<double>(count);
  }
  for (std::size_t c = 0; c < s.context; ++c) w.b[H + c] = z[E * F + c];
  return &runDense(s.rho, w.b.data(), w.scratchA, w.scratchB);
}

#if defined(TRECH_ENABLE_TORCH)
bool GenericSurrogate::predictTorchVector(const double* inputs,
                                          std::size_t inputCount,
                                          std::vector<double>* out) const {
  if (!module_) return false;
  std::vector<float> features;
  features.reserve(inputCount);
  for (std::size_t i = 0; i < inputCount; ++i) {
    const auto value = static_cast<float>(inputs[i]);
    if (!std::isfinite(inputs[i]) || !std::isfinite(value)) return false;
    features.push_back(value);
  }
  torch::NoGradGuard noGrad;
  try {
    auto input = torch::from_blob(features.data(),
        {1, static_cast<long>(features.size())}, torch::kFloat32).clone();
    const auto output = module_->forward({input});
    if (!output.isTensor()) return false;
    const auto tensor = output.toTensor().to(torch::kCPU).to(torch::kFloat32).flatten().contiguous();
    const auto values = tensor.accessor<float, 1>();
    std::vector<double> decoded(static_cast<std::size_t>(tensor.numel()));
    for (std::size_t i = 0; i < decoded.size(); ++i) {
      if (!std::isfinite(values[i])) return false;
      decoded[i] = static_cast<double>(values[i]);
    }
    // Publish only after the complete tensor passed validation. Both public
    // positional APIs use this path, including conversion/error handling.
    *out = std::move(decoded);
    return true;
  } catch (const std::exception&) {
    return false;
  }
}
#endif

bool GenericSurrogate::predictInto(const double* inputs,
                                   std::size_t inputCount, double* out,
                                   std::size_t outCount,
                                   Workspace& workspace) const {
  if (!inputs || !out) {
    return false;
  }
  // A malformed geometry/context must not publish NaN charges, energies or
  // partially updated operator state. This applies to every backend and link.
  for (std::size_t i = 0; i < inputCount; ++i) {
    if (!std::isfinite(inputs[i])) return false;
  }
  if (valid_) {
    if (inputCount != inputNames_.size() || outCount != outputNames_.size()) {
      return false;
    }
    // Ping-pong between the two workspace buffers: after the first call each
    // resize() is a no-op, so a per-step operator over N elements performs
    // zero allocations.  Every element read below is written first.
    std::vector<double>* current = &workspace.a;
    std::vector<double>* next = &workspace.b;
    current->resize(inputCount);
    for (std::size_t i = 0; i < inputCount; ++i) {
      (*current)[i] = (inputs[i] - inputMean_[i]) / inputStd_[i];
    }
    if (networkKind_ != NetworkKind::kDense) {
      current = predictSet(workspace.a.data(), inputs, workspace);
    } else {
      for (const Layer& layer : layers_) {
        next->resize(layer.rows);
        evalLayer(layer, current->data(), next->data());
        std::swap(current, next);
      }
    }
    for (std::size_t o = 0; o < outCount; ++o) {
      // Destandardise with an explicit single-rounding fused multiply-add.
      // Written as `a * std + mean` this is exactly the expression a compiler
      // is free to contract or not; naming the fusion makes the result the
      // same on every compiler instead of an optimiser setting.
      double value = std::fma((*current)[o], outputStd_[o], outputMean_[o]);
      // Check the encoded value first: sigmoid must not conceal an overflowing
      // network/scaler as a seemingly valid saturated probability.
      if (!std::isfinite(value)) return false;
      const auto transform = o < outputTransforms_.size()
          ? outputTransforms_[o] : OutputTransform::kIdentity;
      if (transform == OutputTransform::kExp) {
        value = std::exp(value);
      } else if (transform == OutputTransform::kSigmoid) {
        // Each exponential has a non-positive argument, including extreme
        // finite logits. Saturation at 0/1 is valid; arithmetic overflow is not.
        const double decay = std::exp(-std::abs(value));
        value = value >= 0.0 ? 1.0 / (1.0 + decay) : decay / (1.0 + decay);
      }
      if (!std::isfinite(value)) return false;
      (*current)[o] = value;
    }
    // Decode every output before publishing any: an overflowing link must not
    // leave a partially written state update in the caller's buffer.
    std::copy(current->begin(), current->end(), out);
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  std::vector<double> decoded;
  if (!predictTorchVector(inputs, inputCount, &decoded) || decoded.size() != outCount) {
    return false;  // caller sized `out` from a different output width
  }
  std::copy(decoded.begin(), decoded.end(), out);
  return true;
#else
  (void)outCount;
  (void)workspace;
  return false;
#endif
}

bool GenericSurrogate::predictVector(const std::vector<double>& inputs,
                                     std::vector<double>* out) const {
  if (!out) {
    return false;
  }
  if (valid_) {
    // One arithmetic implementation: the convenience form allocates its own
    // scratch and delegates, so it can never drift from the batched path.
    Workspace workspace;
    out->resize(outputNames_.size());
    if (!predictInto(inputs.data(), inputs.size(), out->data(), out->size(),
                     workspace)) {
      out->clear();
      return false;
    }
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  // A positional-only TorchScript module carries no declared output width, so
  // the vector form sizes itself from the returned tensor.
  return predictTorchVector(inputs.data(), inputs.size(), out);
#else
  return false;
#endif
}

bool GenericSurrogate::predict(
    const std::unordered_map<std::string, double>& inputs,
    std::unordered_map<std::string, double>* out) const {
  if (!out || !valid_) {
    return false;  // named prediction requires a JSON model with names
  }
  std::vector<double> x(inputNames_.size(), 0.0);
  for (std::size_t i = 0; i < inputNames_.size(); ++i) {
    const auto it = inputs.find(inputNames_[i]);
    if (it == inputs.end()) return false;
    x[i] = it->second;
  }
  std::vector<double> y;
  if (!predictVector(x, &y) || y.size() != outputNames_.size()) {
    return false;
  }
  out->clear();
  for (std::size_t o = 0; o < outputNames_.size(); ++o) {
    (*out)[outputNames_[o]] = y[o];
  }
  return true;
}

GenericSurrogate::Coverage GenericSurrogate::coverage(
    const std::unordered_map<std::string, double>& inputs) const {
  // Build the declared positional layout and delegate. Standalone coverage
  // retains legacy zero-fill diagnostics; prediction rejects missing facts.
  std::vector<double> x(inputNames_.size(), 0.0);
  for (std::size_t i = 0; i < inputNames_.size(); ++i) {
    const auto it = inputs.find(inputNames_[i]);
    if (it != inputs.end()) {
      x[i] = it->second;
    }
  }
  return coverageVector(x);
}

GenericSurrogate::Coverage GenericSurrogate::coverageVector(
    const std::vector<double>& inputs) const {
  Workspace workspace;
  return coverageVector(inputs, workspace);
}

GenericSurrogate::Coverage GenericSurrogate::coverageVector(
    const std::vector<double>& inputs, Workspace& workspace) const {
  Coverage cov;
  cov.domainMeasured = domainMeasured_;
  if (!valid_) {
    // A positional-only model (raw .pt) carries no named domain; report
    // in-domain rather than fabricating a signal we cannot ground.
    return cov;
  }
  const bool checkJoint = jointCenterCount_ > 0 && !inputNames_.empty();
  if (checkJoint) workspace.a.resize(inputNames_.size());
  for (std::size_t i = 0; i < inputNames_.size(); ++i) {
    const double x = (i < inputs.size()) ? inputs[i] : 0.0;  // missing -> 0
    const double z = (x - inputMean_[i]) / inputStd_[i];  // std_ floored at load
    if (checkJoint) workspace.a[i] = z;
    const double absZ = std::abs(z);
    if (absZ > cov.maxStandardizedDeviation) {
      cov.maxStandardizedDeviation = absZ;
    }
    const double radius = (i < inputDomainRadius_.size())
                              ? inputDomainRadius_[i]
                              : kDefaultStandardizedDomainRadius;
    const double over = absZ - radius;
    if (over > 1e-9) {  // tolerance so float noise on a constant feature is safe
      cov.outOfDomainInputs.push_back(inputNames_[i]);
      if (over > cov.extrapolation) {
        cov.extrapolation = over;
      }
    }

    // Starved-region check: within the trained range but in an unpopulated bin
    // (a hole the model interpolated through). Only when an occupancy histogram
    // is carried; a genuinely out-of-range value is already out-of-domain above.
    if (occupancyBins_ > 0 && i < occupancyCounts_.size() &&
        i < inputMin_.size() && i < inputMax_.size()) {
      const double lo = inputMin_[i];
      const double hi = inputMax_[i];
      if (hi > lo && x >= lo && x <= hi) {
        int bin = static_cast<int>((x - lo) / (hi - lo) * occupancyBins_);
        if (bin >= occupancyBins_) bin = occupancyBins_ - 1;  // x==hi edge
        if (bin < 0) bin = 0;
        if (bin < static_cast<int>(occupancyCounts_[i].size()) &&
            occupancyCounts_[i][bin] == 0) {
          cov.starvedInputs.push_back(inputNames_[i]);
        }
      }
    }
  }
  cov.inDomain = cov.outOfDomainInputs.empty();
  std::sort(cov.outOfDomainInputs.begin(), cov.outOfDomainInputs.end());
  std::sort(cov.starvedInputs.begin(), cov.starvedInputs.end());

  // Joint starvation: distance in standardized space to the nearest training
  // region the model carries.  This is the check the two per-feature ones
  // structurally cannot make -- a point inside every feature's range can still
  // sit in a hole between the clusters training actually covered.  Skipped
  // entirely (and reported unmeasured) for a model with no joint reference, so
  // it costs nothing for models that do not carry one.
  if (checkJoint) {
    const std::size_t nIn = inputNames_.size();
    // Tolerance so a training point sitting exactly on the covering radius is
    // not flagged by float noise.
    const double accept = jointRadius_ * (1.0 + 1e-9) + 1e-12;
    const double acceptSquared = accept * accept;
    double best = std::numeric_limits<double>::infinity();
    bool covered = false;
    for (std::size_t c = 0; c < jointCenterCount_ && !covered; ++c) {
      const double* center = jointCenters_.data() + c * nIn;
      double sum = 0.0;
      for (std::size_t i = 0; i < nIn; ++i) {
        const double d = workspace.a[i] - center[i];
        sum += d * d;
        if (sum >= best) {
          break;  // this center cannot win; stop before finishing the row
        }
      }
      if (sum < best) {
        best = sum;
        // The VERDICT only needs one covering center, so stop as soon as one is
        // found: the expensive full scan is reserved for the starved case,
        // which is the one worth measuring exactly.  Centers are exported in
        // farthest-point order from the training mean, so a typical
        // in-distribution point matches an early one.
        covered = sum <= acceptSquared;
      }
    }
    cov.jointMeasured = true;
    cov.jointRadius = jointRadius_;
    cov.jointDistance = std::sqrt(best);
    cov.jointStarved = !covered;
  }
  return cov;
}

}  // namespace trech::ml
