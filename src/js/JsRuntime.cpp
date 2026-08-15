#include "trech/js/JsRuntime.hpp"

#include "trech/core/Config.hpp"
#include "trech/ml/DiscreteTransition.hpp"
#include "trech/ml/GenericSurrogate.hpp"
#include "trech/ml/PairInteraction.hpp"
#include "trech/ml/ScaleCascade.hpp"
#include "trech/ml/StateEvolution.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <cstdlib>
#include <cstring>
#include <cctype>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <vector>

#include <nlohmann/json.hpp>

extern "C" {
#include "quickjs.h"
}

namespace trech {

struct ModelOperatorMetadata {
  std::string role;
  std::vector<std::string> requiredContextKeys;
  std::string elementKind;
};

struct JsRuntimeState {
  std::string baseDir;
  std::vector<std::string> includeStack;
  std::string lastConfigJson;
  std::string activeHookName;
  HookRuntimeContext activeHookContext;
  std::vector<HookEmitRecord> emittedRecords;
  std::vector<HookEmitRecord> callEmits;
  int callMaxEmitsPerCallback = 0;
  int callMaxEmitPayloadBytes = 0;
  std::size_t callDroppedEmits = 0;
  bool experimentLoaded = false;
  // Typed scenario values declared through TRECH_VALUE. Overrides arrive from
  // `trech run/inspect --param name=<json>`; definitions are retained in source
  // order for Studio's right-sidebar controls.
  nlohmann::json scriptParameterOverrides = nlohmann::json::object();
  std::set<std::string> usedScriptParameterOverrides;
  std::vector<nlohmann::json> scriptParameters;
  std::map<std::string, nlohmann::json> scriptParameterDefinitions;
  // Scenario-declared learned-inference models, keyed by config name. Loaded
  // once after config eval; called from hooks via ctx.predict. std::map keeps
  // the provenance model-name listing deterministic (sorted).
  std::map<std::string, std::unique_ptr<trech::ml::GenericSurrogate>> models;
  // Per-model dimension-scale band (name -> "atomic"/.../"macro"/""), captured
  // alongside the models so `ctx.cascade` can chain them by scale.
  std::map<std::string, std::string> modelScales;
  // Contextual operator selection metadata. Models without a role remain
  // ordinary point/cascade models and are never pulled into ctx.evolve merely
  // because they happen to be declared in the same scenario.
  std::map<std::string, ModelOperatorMetadata> modelOperatorMetadata;
  std::size_t callReactSequence = 0;  // deterministic sub-seed per ctx.react call
  std::size_t callPredictCount = 0;   // reset per dispatch (report parity)
  std::size_t totalPredictCount = 0;  // run-total (init-hook path etc.)
  // Subset of the above that ran outside the model's trained domain
  // (low-confidence extrapolations) -- workstream 3a run-level accountability.
  std::size_t callOutOfDomainCount = 0;
  std::size_t totalOutOfDomainCount = 0;
};

struct JsRuntime::Impl {
  JSRuntime* rt = nullptr;
  JSContext* ctx = nullptr;
  JsRuntimeState state;
  mutable std::mutex mutex;
};

static std::string readFile(const std::string& path) {
  std::ifstream file(path);
  if (!file) {
    throw std::runtime_error("Cannot open: " + path);
  }
  std::stringstream buffer;
  buffer << file.rdbuf();
  return buffer.str();
}

static std::string baseDirFromPath(const std::string& path) {
  std::filesystem::path pathObj(path);
  if (pathObj.has_parent_path()) {
    return pathObj.parent_path().string();
  }
  return ".";
}

static std::string resolveIncludePath(const JsRuntimeState* state,
                                      const std::string& includePath) {
  std::filesystem::path inc(includePath);
  if (inc.is_absolute()) {
    return inc.lexically_normal().string();
  }
  std::filesystem::path base(".");
  if (state && !state->includeStack.empty()) {
    base = std::filesystem::path(state->includeStack.back()).parent_path();
  } else if (state && !state->baseDir.empty()) {
    base = state->baseDir;
  }
  return (base / inc).lexically_normal().string();
}

static std::string slugifyPubChemName(const std::string& name) {
  std::string out;
  bool lastDash = false;
  for (unsigned char ch : name) {
    if (std::isalnum(ch)) {
      out.push_back(static_cast<char>(std::tolower(ch)));
      lastDash = false;
    } else if (!lastDash && !out.empty()) {
      out.push_back('-');
      lastDash = true;
    }
  }
  while (!out.empty() && out.back() == '-') {
    out.pop_back();
  }
  return out;
}

static std::vector<std::filesystem::path> pubChemCacheDirs(const JsRuntimeState* state) {
  std::vector<std::filesystem::path> dirs;
  if (const char* env = std::getenv("TRECH_PUBCHEM_CACHE_DIR")) {
    if (env[0] != '\0') {
      dirs.emplace_back(env);
    }
  }
  if (state && !state->baseDir.empty()) {
    dirs.push_back((std::filesystem::path(state->baseDir) / ".." / ".." /
                    "data" / "pubchem").lexically_normal());
  }
  dirs.push_back((std::filesystem::current_path() / "data" / "pubchem").lexically_normal());
  return dirs;
}

static std::string readPubChemCompoundJson(const JsRuntimeState* state,
                                           const std::string& name,
                                           std::filesystem::path& resolvedPath) {
  const std::string slug = slugifyPubChemName(name);
  if (slug.empty()) {
    throw std::runtime_error("empty PubChem compound name");
  }
  for (const auto& dir : pubChemCacheDirs(state)) {
    std::filesystem::path candidate = dir / (slug + ".json");
    if (!std::filesystem::exists(candidate)) {
      continue;
    }
    resolvedPath = candidate.lexically_normal();
    return readFile(resolvedPath.string());
  }
  throw std::runtime_error("PubChem cache miss for '" + name +
                           "' (set TRECH_PUBCHEM_CACHE_DIR or fetch it first)");
}

static std::string normalizeDeterminismMode(std::string mode) {
  for (auto& ch : mode) {
    ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
  }
  if (mode == "predictive") {
    return mode;
  }
  return "strict";
}

static std::string jsonStringifyValue(JSContext* ctx, JSValueConst value) {
  JSValue jsonValue = JS_JSONStringify(ctx, value, JS_UNDEFINED, JS_UNDEFINED);
  if (JS_IsException(jsonValue)) {
    JS_FreeValue(ctx, jsonValue);
    return {};
  }
  const char* raw = JS_ToCString(ctx, jsonValue);
  std::string out = raw ? raw : "";
  if (raw) {
    JS_FreeCString(ctx, raw);
  }
  JS_FreeValue(ctx, jsonValue);
  return out;
}

static bool validScriptParameterId(const std::string& id) {
  if (id.empty()) {
    return false;
  }
  for (unsigned char ch : id) {
    if (!std::isalnum(ch) && ch != '_' && ch != '-' && ch != '.') {
      return false;
    }
  }
  return true;
}

static bool scriptParameterValueValid(const nlohmann::json& definition,
                                      const nlohmann::json& value,
                                      std::string& reason) {
  const std::string type = definition.value("type", std::string());
  if (type == "number") {
    if (!value.is_number() || !std::isfinite(value.get<double>())) {
      reason = "must be a finite number";
      return false;
    }
  } else if (type == "integer") {
    if (!value.is_number_integer()) {
      reason = "must be an integer";
      return false;
    }
  } else if (type == "boolean") {
    if (!value.is_boolean()) {
      reason = "must be a boolean";
      return false;
    }
  } else if (type == "string") {
    if (!value.is_string()) {
      reason = "must be a string";
      return false;
    }
  } else if (type == "choice") {
    const auto choices = definition.find("choices");
    if (choices == definition.end() || !choices->is_array() || choices->empty()) {
      reason = "requires a non-empty choices array";
      return false;
    }
    if (std::find(choices->begin(), choices->end(), value) == choices->end()) {
      reason = "must be one of the declared choices";
      return false;
    }
  } else {
    reason = "has unsupported type '" + type + "'";
    return false;
  }

  if ((type == "number" || type == "integer") && value.is_number()) {
    const double numeric = value.get<double>();
    if (definition.contains("min") && definition.at("min").is_number() &&
        numeric < definition.at("min").get<double>()) {
      reason = "is below min";
      return false;
    }
    if (definition.contains("max") && definition.at("max").is_number() &&
        numeric > definition.at("max").get<double>()) {
      reason = "is above max";
      return false;
    }
  }
  return true;
}

// __TRECH_VALUE(name, definition) is wrapped by the ergonomic TRECH_VALUE
// helpers installed below. It validates metadata and returns either the
// command-line/Studio override or the declaration's default.
static JSValue jsTrechValue(JSContext* ctx, JSValueConst /*this_val*/, int argc,
                            JSValueConst* argv) {
  auto* state = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  if (!state || argc < 2) {
    return JS_ThrowTypeError(ctx, "TRECH_VALUE requires a name and definition");
  }
  const char* rawId = JS_ToCString(ctx, argv[0]);
  if (!rawId) {
    return JS_ThrowTypeError(ctx, "TRECH_VALUE name must be a string");
  }
  const std::string id = rawId;
  JS_FreeCString(ctx, rawId);
  if (!validScriptParameterId(id)) {
    return JS_ThrowTypeError(
        ctx, "TRECH_VALUE name may contain only letters, digits, '.', '_' and '-'");
  }

  const std::string rawDefinition = jsonStringifyValue(ctx, argv[1]);
  nlohmann::json supplied = nlohmann::json::parse(
      rawDefinition, nullptr, /*allow_exceptions=*/false);
  if (!supplied.is_object() || !supplied.contains("default")) {
    return JS_ThrowTypeError(ctx, "TRECH_VALUE definition requires a default value");
  }

  nlohmann::json definition = nlohmann::json::object();
  definition["id"] = id;
  if (!supplied.contains("type") || !supplied.at("type").is_string()) {
    return JS_ThrowTypeError(ctx, "TRECH_VALUE type must be a string");
  }
  if (supplied.contains("label") && !supplied.at("label").is_string()) {
    return JS_ThrowTypeError(ctx, "TRECH_VALUE label must be a string");
  }
  for (const char* key : {"description", "group", "unit"}) {
    if (supplied.contains(key) && !supplied.at(key).is_string()) {
      return JS_ThrowTypeError(ctx, "TRECH_VALUE %s must be a string", key);
    }
  }
  definition["type"] = supplied.at("type");
  definition["label"] = supplied.contains("label") ? supplied.at("label")
                                                      : nlohmann::json(id);
  definition["default"] = supplied.at("default");
  for (const char* key : {"description", "group", "unit", "min", "max", "step",
                          "choices"}) {
    if (supplied.contains(key)) {
      definition[key] = supplied.at(key);
    }
  }
  const std::string type = definition.value("type", std::string());
  if (type == "number" || type == "integer") {
    for (const char* key : {"min", "max", "step"}) {
      if (definition.contains(key) &&
          (!definition.at(key).is_number() ||
           !std::isfinite(definition.at(key).get<double>()))) {
        return JS_ThrowTypeError(ctx, "TRECH_VALUE numeric %s must be finite", key);
      }
      if (type == "integer" && definition.contains(key) &&
          !definition.at(key).is_number_integer()) {
        return JS_ThrowTypeError(ctx, "TRECH_VALUE integer %s must be an integer", key);
      }
    }
  }
  if ((type == "number" || type == "integer") && definition.contains("step") &&
      definition.at("step").get<double>() <= 0.0) {
    return JS_ThrowRangeError(ctx, "TRECH_VALUE numeric step must be positive");
  }
  if ((type == "number" || type == "integer") && definition.contains("min") &&
      definition.contains("max") && definition.at("min").is_number() &&
      definition.at("max").is_number() &&
      definition.at("min").get<double>() > definition.at("max").get<double>()) {
    return JS_ThrowRangeError(ctx, "TRECH_VALUE min must not exceed max");
  }
  std::string reason;
  if (!scriptParameterValueValid(definition, definition.at("default"), reason)) {
    return JS_ThrowTypeError(ctx, "TRECH_VALUE '%s' default %s", id.c_str(), reason.c_str());
  }
  if (state->scriptParameterDefinitions.count(id) != 0) {
    return JS_ThrowTypeError(ctx, "TRECH_VALUE name '%s' is declared more than once", id.c_str());
  }

  nlohmann::json selected = definition.at("default");
  bool overridden = false;
  const auto override = state->scriptParameterOverrides.find(id);
  if (override != state->scriptParameterOverrides.end()) {
    if (!scriptParameterValueValid(definition, *override, reason)) {
      return JS_ThrowRangeError(ctx, "TRECH_VALUE '%s' override %s", id.c_str(), reason.c_str());
    }
    selected = *override;
    overridden = true;
    state->usedScriptParameterOverrides.insert(id);
  }
  definition["value"] = selected;
  definition["overridden"] = overridden;
  state->scriptParameterDefinitions[id] = definition;
  state->scriptParameters.push_back(definition);

  const std::string selectedJson = selected.dump();
  return JS_ParseJSON(ctx, selectedJson.c_str(), selectedJson.size(), "<TRECH_VALUE>");
}

static bool applyHookOverridePatch(TrechConfig& cfg, const nlohmann::json& patch,
                                   std::vector<std::string>& appliedPaths) {
  bool changed = false;
  if (!patch.is_object()) {
    return false;
  }

  if (patch.contains("beam") && patch.at("beam").is_object()) {
    const auto& beam = patch.at("beam");
    if (beam.contains("particle") && beam.at("particle").is_string()) {
      cfg.beam.particle = beam.at("particle").get<std::string>();
      appliedPaths.push_back("beam.particle");
      changed = true;
    }
    if (beam.contains("energyMeV") && beam.at("energyMeV").is_number()) {
      cfg.beam.energyMeV = beam.at("energyMeV").get<double>();
      appliedPaths.push_back("beam.energyMeV");
      changed = true;
    }
    if (beam.contains("direction")) {
      const auto& dir = beam.at("direction");
      if (dir.is_array() && dir.size() >= 3) {
        cfg.beam.directionX = dir.at(0).get<double>();
        cfg.beam.directionY = dir.at(1).get<double>();
        cfg.beam.directionZ = dir.at(2).get<double>();
        appliedPaths.push_back("beam.direction");
        changed = true;
      } else if (dir.is_object()) {
        if (dir.contains("x") && dir.at("x").is_number()) {
          cfg.beam.directionX = dir.at("x").get<double>();
        }
        if (dir.contains("y") && dir.at("y").is_number()) {
          cfg.beam.directionY = dir.at("y").get<double>();
        }
        if (dir.contains("z") && dir.at("z").is_number()) {
          cfg.beam.directionZ = dir.at("z").get<double>();
        }
        appliedPaths.push_back("beam.direction");
        changed = true;
      }
    }
  }

  if (patch.contains("run") && patch.at("run").is_object()) {
    const auto& run = patch.at("run");
    if (run.contains("nEvents") && run.at("nEvents").is_number_integer()) {
      const auto nEvents = run.at("nEvents").get<int>();
      if (nEvents > 0) {
        cfg.run.nEvents = nEvents;
        appliedPaths.push_back("run.nEvents");
        changed = true;
      }
    }
    if (run.contains("seed") && run.at("seed").is_number_unsigned()) {
      cfg.run.seed = run.at("seed").get<std::uint64_t>();
      appliedPaths.push_back("run.seed");
      changed = true;
    } else if (run.contains("seed") && run.at("seed").is_number_integer()) {
      const auto seed = run.at("seed").get<long long>();
      if (seed >= 0) {
        cfg.run.seed = static_cast<std::uint64_t>(seed);
        appliedPaths.push_back("run.seed");
        changed = true;
      }
    }
  }

  if (patch.contains("optics") && patch.at("optics").is_object()) {
    const auto& optics = patch.at("optics");
    if (optics.contains("enable") && optics.at("enable").is_boolean()) {
      cfg.optics.enable = optics.at("enable").get<bool>();
      appliedPaths.push_back("optics.enable");
      changed = true;
    }
    if (optics.contains("refractiveIndex") && optics.at("refractiveIndex").is_number()) {
      cfg.optics.refractiveIndex = optics.at("refractiveIndex").get<double>();
      appliedPaths.push_back("optics.refractiveIndex");
      changed = true;
    }
    if (optics.contains("absorptionLengthMm") &&
        optics.at("absorptionLengthMm").is_number()) {
      cfg.optics.absorptionLengthMm = optics.at("absorptionLengthMm").get<double>();
      appliedPaths.push_back("optics.absorptionLengthMm");
      changed = true;
    }
    if (optics.contains("scatterLengthMm") && optics.at("scatterLengthMm").is_number()) {
      cfg.optics.scatterLengthMm = optics.at("scatterLengthMm").get<double>();
      appliedPaths.push_back("optics.scatterLengthMm");
      changed = true;
    }
  }

  if (patch.contains("system") && patch.at("system").is_object()) {
    const auto& system = patch.at("system");
    if (system.contains("enable") && system.at("enable").is_boolean()) {
      cfg.system.enable = system.at("enable").get<bool>();
      appliedPaths.push_back("system.enable");
      changed = true;
    }
    if (system.contains("mode") && system.at("mode").is_string()) {
      cfg.system.mode = system.at("mode").get<std::string>();
      appliedPaths.push_back("system.mode");
      changed = true;
    }
    if (system.contains("frame") && system.at("frame").is_string()) {
      cfg.system.frame = system.at("frame").get<std::string>();
      appliedPaths.push_back("system.frame");
      changed = true;
    }
    if (system.contains("ensemble") && system.at("ensemble").is_string()) {
      cfg.system.ensemble = system.at("ensemble").get<std::string>();
      appliedPaths.push_back("system.ensemble");
      changed = true;
    }
    if (system.contains("volumeMm3") && system.at("volumeMm3").is_number()) {
      cfg.system.volumeMm3 = system.at("volumeMm3").get<double>();
      appliedPaths.push_back("system.volumeMm3");
      changed = true;
    }
  }

  if (patch.contains("stratify") && patch.at("stratify").is_object()) {
    const auto& stratify = patch.at("stratify");
    if (stratify.contains("edepMeVThreshold") &&
        stratify.at("edepMeVThreshold").is_number()) {
      cfg.stratify.edepMeVThreshold = stratify.at("edepMeVThreshold").get<double>();
      appliedPaths.push_back("stratify.edepMeVThreshold");
      changed = true;
    }
    if (stratify.contains("opticalTrackLengthMmThreshold") &&
        stratify.at("opticalTrackLengthMmThreshold").is_number()) {
      cfg.stratify.opticalTrackLengthMmThreshold =
          stratify.at("opticalTrackLengthMmThreshold").get<double>();
      appliedPaths.push_back("stratify.opticalTrackLengthMmThreshold");
      changed = true;
    }
    if (stratify.contains("totalTrackLengthMmThreshold") &&
        stratify.at("totalTrackLengthMmThreshold").is_number()) {
      cfg.stratify.totalTrackLengthMmThreshold =
          stratify.at("totalTrackLengthMmThreshold").get<double>();
      appliedPaths.push_back("stratify.totalTrackLengthMmThreshold");
      changed = true;
    }
    if (stratify.contains("totalTrackCountThreshold") &&
        stratify.at("totalTrackCountThreshold").is_number_integer()) {
      cfg.stratify.totalTrackCountThreshold =
          stratify.at("totalTrackCountThreshold").get<int>();
      appliedPaths.push_back("stratify.totalTrackCountThreshold");
      changed = true;
    }
    if (stratify.contains("totalStepCountThreshold") &&
        stratify.at("totalStepCountThreshold").is_number_integer()) {
      cfg.stratify.totalStepCountThreshold =
          stratify.at("totalStepCountThreshold").get<int>();
      appliedPaths.push_back("stratify.totalStepCountThreshold");
      changed = true;
    }
    if (stratify.contains("opticalPhotonTrackThreshold") &&
        stratify.at("opticalPhotonTrackThreshold").is_number_integer()) {
      cfg.stratify.opticalPhotonTrackThreshold =
          stratify.at("opticalPhotonTrackThreshold").get<int>();
      appliedPaths.push_back("stratify.opticalPhotonTrackThreshold");
      changed = true;
    }
    if (stratify.contains("opticalPhotonStepThreshold") &&
        stratify.at("opticalPhotonStepThreshold").is_number_integer()) {
      cfg.stratify.opticalPhotonStepThreshold =
          stratify.at("opticalPhotonStepThreshold").get<int>();
      appliedPaths.push_back("stratify.opticalPhotonStepThreshold");
      changed = true;
    }
    if (stratify.contains("labelPredictable") &&
        stratify.at("labelPredictable").is_string()) {
      cfg.stratify.labelPredictable =
          stratify.at("labelPredictable").get<std::string>();
      appliedPaths.push_back("stratify.labelPredictable");
      changed = true;
    }
    if (stratify.contains("labelExceptional") &&
        stratify.at("labelExceptional").is_string()) {
      cfg.stratify.labelExceptional =
          stratify.at("labelExceptional").get<std::string>();
      appliedPaths.push_back("stratify.labelExceptional");
      changed = true;
    }
    if (stratify.contains("labelUnclassified") &&
        stratify.at("labelUnclassified").is_string()) {
      cfg.stratify.labelUnclassified =
          stratify.at("labelUnclassified").get<std::string>();
      appliedPaths.push_back("stratify.labelUnclassified");
      changed = true;
    }
  }

  return changed;
}

static std::uint64_t hashHookSeed(const std::string& hookName,
                                  const HookRuntimeContext& context) {
  std::uint64_t hash = 14695981039346656037ull;
  const std::uint64_t prime = 1099511628211ull;
  const auto mixByte = [&](unsigned char byte) {
    hash ^= static_cast<std::uint64_t>(byte);
    hash *= prime;
  };
  for (unsigned char ch : hookName) {
    mixByte(ch);
  }
  const auto mixIntegral = [&](std::uint64_t value) {
    for (int i = 0; i < 8; ++i) {
      mixByte(static_cast<unsigned char>((value >> (8 * i)) & 0xffu));
    }
  };
  mixIntegral(context.seed);
  mixIntegral(static_cast<std::uint64_t>(context.nEvents));
  mixIntegral(static_cast<std::uint64_t>(context.eventId + 1));
  mixIntegral(static_cast<std::uint64_t>(context.stepIndex + 1));
  return hash;
}

static std::uint64_t xorshift64(std::uint64_t state) {
  state ^= (state << 13);
  state ^= (state >> 7);
  state ^= (state << 17);
  return state;
}

static JSValue jsHookEmit(JSContext* ctx, JSValueConst /*this_val*/, int argc,
                          JSValueConst* argv) {
  auto* state = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  if (!state) {
    return JS_EXCEPTION;
  }
  if (argc < 1) {
    return JS_ThrowTypeError(ctx, "ctx.emit(tag, payload) requires a tag");
  }
  const char* tagRaw = JS_ToCString(ctx, argv[0]);
  if (!tagRaw) {
    return JS_ThrowTypeError(ctx, "ctx.emit tag must be a string");
  }
  if (tagRaw[0] == '\0') {
    JS_FreeCString(ctx, tagRaw);
    return JS_ThrowTypeError(ctx, "ctx.emit tag must be a non-empty string");
  }
  if (state->callMaxEmitsPerCallback > 0 &&
      static_cast<int>(state->callEmits.size()) >= state->callMaxEmitsPerCallback) {
    JS_FreeCString(ctx, tagRaw);
    state->callDroppedEmits += 1;
    return JS_UNDEFINED;
  }
  HookEmitRecord emit;
  emit.hook = state->activeHookName;
  emit.tag = tagRaw;
  emit.eventId = state->activeHookContext.eventId;
  emit.stepIndex = state->activeHookContext.stepIndex;
  JS_FreeCString(ctx, tagRaw);
  if (argc > 1) {
    emit.payloadJson = jsonStringifyValue(ctx, argv[1]);
    if (emit.payloadJson.empty()) {
      state->callDroppedEmits += 1;
      return JS_UNDEFINED;
    }
  } else {
    emit.payloadJson = "null";
  }
  if (state->callMaxEmitPayloadBytes > 0 &&
      static_cast<int>(emit.payloadJson.size()) > state->callMaxEmitPayloadBytes) {
    state->callDroppedEmits += 1;
    return JS_UNDEFINED;
  }
  state->emittedRecords.push_back(emit);
  state->callEmits.push_back(emit);
  return JS_UNDEFINED;
}

// Build the `{ <output>: {r2?, mae?, rmse?} }` object every learned-inference
// path reports its MEASURED held-out accuracy through. An output whose model
// carries no metric is simply absent (an illustrative hand-authored map yields
// an empty object) -- absent means "not measured", never "zero error".
JSValue newOutputAccuracyObject(
    JSContext* ctx, const std::vector<trech::ml::NamedOutputAccuracy>& records) {
  JSValue accuracy = JS_NewObject(ctx);
  for (const auto& record : records) {
    JSValue entry = JS_NewObject(ctx);
    if (record.hasR2) {
      JS_SetPropertyStr(ctx, entry, "r2", JS_NewFloat64(ctx, record.r2));
    }
    if (record.hasMeanAbsoluteError) {
      JS_SetPropertyStr(ctx, entry, "mae",
                        JS_NewFloat64(ctx, record.meanAbsoluteError));
    }
    if (record.hasRootMeanSquaredError) {
      // Measured 1-sigma held-out residual, in this output's own units.
      JS_SetPropertyStr(ctx, entry, "rmse",
                        JS_NewFloat64(ctx, record.rootMeanSquaredError));
    }
    JS_SetPropertyStr(ctx, accuracy, record.name.c_str(), entry);
  }
  return accuracy;
}

// ctx.predict(modelName, featuresObject) -> { outputName: value, ... } | null
//
// The general Torch-inference entry point for any scenario: look up a declared
// GenericSurrogate model by name, feed it the named numeric fields of the
// features object (unknown inputs default to 0, extras ignored), and return the
// named outputs. Returns null (never throws for control flow) when learned
// inference is unavailable, so scenarios degrade gracefully:
//   * strict determinism mode disables model inference paths (invariant);
//   * an undeclared name or a model that failed to load (e.g. a `.pt` without
//     LibTorch) yields null.
// Deterministic: a pure function of the loaded weights and numeric inputs.
static JSValue jsHookPredict(JSContext* ctx, JSValueConst /*this_val*/, int argc,
                             JSValueConst* argv) {
  auto* state = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  if (!state) {
    return JS_EXCEPTION;
  }
  if (argc < 1) {
    return JS_ThrowTypeError(ctx, "ctx.predict(model, features) requires a model name");
  }
  // Strict mode disables learned inference (determinism invariant).
  if (normalizeDeterminismMode(state->activeHookContext.determinismMode) !=
      "predictive") {
    return JS_NULL;
  }
  const char* nameRaw = JS_ToCString(ctx, argv[0]);
  if (!nameRaw) {
    return JS_ThrowTypeError(ctx, "ctx.predict model name must be a string");
  }
  const std::string modelName = nameRaw;
  JS_FreeCString(ctx, nameRaw);

  const auto it = state->models.find(modelName);
  if (it == state->models.end() || !it->second || !it->second->loaded()) {
    return JS_NULL;  // undeclared or unloaded model: degrade gracefully
  }

  std::unordered_map<std::string, double> inputs;
  if (argc > 1 && JS_IsObject(argv[1])) {
    JSPropertyEnum* props = nullptr;
    uint32_t propCount = 0;
    if (JS_GetOwnPropertyNames(ctx, &props, &propCount, argv[1],
                               JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) == 0) {
      for (uint32_t i = 0; i < propCount; ++i) {
        JSValue key = JS_AtomToString(ctx, props[i].atom);
        const char* keyRaw = JS_ToCString(ctx, key);
        JSValue val = JS_GetProperty(ctx, argv[1], props[i].atom);
        double num = 0.0;
        if (keyRaw && JS_ToFloat64(ctx, &num, val) == 0) {
          inputs[keyRaw] = num;
        }
        if (keyRaw) {
          JS_FreeCString(ctx, keyRaw);
        }
        JS_FreeValue(ctx, val);
        JS_FreeValue(ctx, key);
        JS_FreeAtom(ctx, props[i].atom);
      }
      js_free(ctx, props);
    }
  }

  std::unordered_map<std::string, double> outputs;
  if (!it->second->predict(inputs, &outputs)) {
    return JS_NULL;
  }
  state->callPredictCount += 1;
  state->totalPredictCount += 1;

  JSValue result = JS_NewObject(ctx);
  for (const auto& [key, value] : outputs) {
    JS_SetPropertyStr(ctx, result, key.c_str(), JS_NewFloat64(ctx, value));
  }
  // Reserved `__coverage`: the honest "am I extrapolating?" signal for this
  // single-model prediction (the same domain check the cascade surfaces per
  // stage). inDomain=false means the model predicted on inputs outside the
  // region it was trained on -- the caller should treat the output as
  // low-confidence, not a silent guess.
  const trech::ml::GenericSurrogate::Coverage cov =
      it->second->coverage(inputs);
  if (!cov.inDomain) {
    state->callOutOfDomainCount += 1;
    state->totalOutOfDomainCount += 1;
  }
  JSValue covObj = JS_NewObject(ctx);
  JS_SetPropertyStr(ctx, covObj, "inDomain", JS_NewBool(ctx, cov.inDomain));
  JS_SetPropertyStr(ctx, covObj, "domainMeasured",
                    JS_NewBool(ctx, cov.domainMeasured));
  JS_SetPropertyStr(ctx, covObj, "extrapolation",
                    JS_NewFloat64(ctx, cov.extrapolation));
  JS_SetPropertyStr(ctx, covObj, "maxStandardizedDeviation",
                    JS_NewFloat64(ctx, cov.maxStandardizedDeviation));
  JSValue ood = JS_NewArray(ctx);
  for (std::size_t di = 0; di < cov.outOfDomainInputs.size(); ++di) {
    JS_SetPropertyUint32(ctx, ood, static_cast<uint32_t>(di),
                         JS_NewString(ctx, cov.outOfDomainInputs[di].c_str()));
  }
  JS_SetPropertyStr(ctx, covObj, "outOfDomainInputs", ood);
  JSValue covStarved = JS_NewArray(ctx);
  for (std::size_t vi = 0; vi < cov.starvedInputs.size(); ++vi) {
    JS_SetPropertyUint32(ctx, covStarved, static_cast<uint32_t>(vi),
                         JS_NewString(ctx, cov.starvedInputs[vi].c_str()));
  }
  JS_SetPropertyStr(ctx, covObj, "starvedInputs", covStarved);
  // Joint (multivariate) starvation: in range on every axis yet far from any
  // training point. `jointMeasured:false` means the model carries no joint
  // reference and the check was NOT performed -- unknown, not a pass.
  JS_SetPropertyStr(ctx, covObj, "jointMeasured",
                    JS_NewBool(ctx, cov.jointMeasured));
  JS_SetPropertyStr(ctx, covObj, "jointStarved",
                    cov.jointMeasured ? JS_NewBool(ctx, cov.jointStarved)
                                      : JS_NULL);
  JS_SetPropertyStr(ctx, covObj, "jointDistance",
                    cov.jointMeasured ? JS_NewFloat64(ctx, cov.jointDistance)
                                      : JS_NULL);
  JS_SetPropertyStr(ctx, covObj, "jointRadius",
                    cov.jointMeasured ? JS_NewFloat64(ctx, cov.jointRadius)
                                      : JS_NULL);
  JS_SetPropertyStr(ctx, result, "__coverage", covObj);

  // Reserved `__accuracy`: the model's MEASURED held-out error for each output
  // it just produced, keyed by output name. `rmse` is a measured 1-sigma
  // residual in that output's own units, so a scenario can emit the engine's
  // uncertainty instead of typing a sigma of its own. The key is absent
  // entirely for a model that carries no held-out metrics (an illustrative
  // hand-authored map) -- absent means unknown, never "zero error".
  if (it->second->hasOutputAccuracy()) {
    JS_SetPropertyStr(
        ctx, result, "__accuracy",
        newOutputAccuracyObject(ctx,
                                trech::ml::collectOutputAccuracy(*it->second)));
  }
  return result;
}

// Build the ambient Geant4 seed for ctx.cascade: the real particle/nano-scale
// facts already carried on the active hook context -- per-event Geant4 tallies
// (edep, track length, step/track counts, optical-photon transport) plus the
// material-composition probes (density, electron density, mean excitation
// energy I, radiation length, per-element number densities). Keyed by stable,
// physics-agnostic names so a stage model can declare them as inputs.
//
// This is workstream 1 of the multi-scale doctrine ("the bottom of the ladder
// is ALWAYS the real Geant4 base", see the ROADMAP "Multi-scale statistical
// inference" standing objective): the scenario no longer has to copy
// ctx.event/ctx.materials into a features object by hand -- ctx.cascade() with
// no argument auto-seeds from these. Deterministic: a pure function of the
// numeric Geant4 facts.
static std::unordered_map<std::string, double> buildAmbientGeant4Seed(
    const HookRuntimeContext& context) {
  std::unordered_map<std::string, double> seed;

  // Per-event Geant4 tallies (only meaningful inside an event: eventId >= 0).
  if (context.eventId >= 0) {
    seed["edep_mev"] = context.eventEdepMeV;
    seed["track_length_mm"] = context.eventTotalTrackLengthMm;
    seed["step_count"] = static_cast<double>(context.eventTotalStepCount);
    seed["track_count"] = static_cast<double>(context.eventTotalTrackCount);
    seed["optical_photon_steps"] =
        static_cast<double>(context.eventOpticalPhotonSteps);
    seed["optical_photon_tracks"] =
        static_cast<double>(context.eventOpticalPhotonTracks);
    seed["optical_photon_track_length_mm"] =
        context.eventOpticalPhotonTrackLengthMm;
  }

  // Geant4 material-composition probes (run-constant): namespaced by material
  // name so multiple materials never collide (material.<name>.<fact>).
  if (!context.materialsJson.empty()) {
    nlohmann::json parsed =
        nlohmann::json::parse(context.materialsJson, nullptr, /*allow_exceptions=*/false);
    if (parsed.is_array()) {
      for (const auto& mat : parsed) {
        if (!mat.is_object()) continue;
        const std::string name = mat.value("name", std::string());
        if (name.empty()) continue;
        const std::string prefix = "material." + name + ".";
        auto setNum = [&](const char* jsonKey, const char* seedKey) {
          const auto it = mat.find(jsonKey);
          if (it != mat.end() && it->is_number()) {
            seed[prefix + seedKey] = it->get<double>();
          }
        };
        setNum("density_g_per_cm3", "density_g_per_cm3");
        setNum("electron_density_per_cm3", "electron_density_per_cm3");
        setNum("mean_excitation_energy_ev", "mean_excitation_energy_ev");
        setNum("radiation_length_mm", "radiation_length_mm");
        const auto nd = mat.find("numberDensityPerCm3");
        if (nd != mat.end() && nd->is_object()) {
          for (const auto& [sym, val] : nd->items()) {
            if (val.is_number()) {
              seed[prefix + "number_density." + sym] = val.get<double>();
            }
          }
        }
      }
    }
  }

  // Geant4-derived optical facts, namespaced like materials. These are the
  // exact spectra attached to transport and emitted to the viz scene.
  if (!context.opticsJson.empty()) {
    nlohmann::json parsed =
        nlohmann::json::parse(context.opticsJson, nullptr, /*allow_exceptions=*/false);
    if (parsed.is_array()) {
      for (const auto& opt : parsed) {
        if (!opt.is_object()) continue;
        std::string name = opt.value("config_material_key", std::string());
        if (name.empty()) name = opt.value("material_name", std::string());
        if (name.empty()) continue;
        const std::string prefix = "optics." + name + ".";
        auto setNum = [&](const char* jsonKey, const char* seedKey) {
          const auto it = opt.find(jsonKey);
          if (it != opt.end() && it->is_number()) {
            seed[prefix + seedKey] = it->get<double>();
          }
        };
        setNum("mean_refractive_index", "mean_refractive_index");
        setNum("mean_absorption_length_mm", "mean_absorption_length_mm");
        setNum("mean_scatter_length_mm", "mean_scatter_length_mm");
        const auto rgb = opt.find("display_rgb");
        if (rgb != opt.end() && rgb->is_array() && rgb->size() >= 3) {
          for (std::size_t i = 0; i < 3; ++i) {
            if ((*rgb)[i].is_number()) {
              static const char* keys[] = {"display_r", "display_g", "display_b"};
              seed[prefix + keys[i]] = (*rgb)[i].get<double>();
            }
          }
        }
      }
    }
  }

  return seed;
}

// ctx.cascade(seedFeatures?, modelNames?) ->
//   { ...context, __cascade: {stagesRun, trace} } | null
//
// The multi-scale entry point: chain every declared model by its `scale` band
// (atomic->nano->micro->meso->macro, unscaled last) into ONE deterministic
// pass. The seed object (Geant4-derived facts + whatever the hook supplies)
// becomes the initial context; each stage reads the named inputs it needs from
// the current context (seed + lower-scale outputs) and merges its named outputs
// back, so a higher-scale model automatically consumes lower-scale predictions
// without the scenario hand-wiring the chain. Returns the flat, augmented
// context (every fact + prediction as { name: value }) plus a reserved
// `__cascade` metadata object (stagesRun + per-stage trace + seedKeys). Like
// ctx.predict: deterministic, disabled in strict mode (returns null), degrades
// to just the seed when no models load, and each stage that runs counts as one
// inference (hook_predict_count).
//
// The cascade ALWAYS starts from the ambient Geant4 base (buildAmbientGeant4Seed
// above), so ctx.cascade() with no argument auto-populates from the real
// per-event tallies + material probes; an explicit seed object overrides or
// augments those (override-on-demand). The optional second argument narrows the
// pass to named stages. This matters when one scenario declares independent
// model families (for example a property cascade plus a per-element operator):
// a missing-input model must not be evaluated on implicit zeros merely because
// it shares the config's `models` registry.
static JSValue jsHookCascade(JSContext* ctx, JSValueConst /*this_val*/, int argc,
                             JSValueConst* argv) {
  auto* state = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  if (!state) {
    return JS_EXCEPTION;
  }
  // Strict mode disables learned inference (determinism invariant).
  if (normalizeDeterminismMode(state->activeHookContext.determinismMode) !=
      "predictive") {
    return JS_NULL;
  }

  // Seed the bottom of the ladder with the real Geant4 base by default; the
  // explicit argument (if any) overrides/augments per key below.
  std::unordered_map<std::string, double> seed =
      buildAmbientGeant4Seed(state->activeHookContext);
  if (argc > 0 && JS_IsObject(argv[0])) {
    JSPropertyEnum* props = nullptr;
    uint32_t propCount = 0;
    if (JS_GetOwnPropertyNames(ctx, &props, &propCount, argv[0],
                               JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) == 0) {
      for (uint32_t i = 0; i < propCount; ++i) {
        JSValue key = JS_AtomToString(ctx, props[i].atom);
        const char* keyRaw = JS_ToCString(ctx, key);
        JSValue val = JS_GetProperty(ctx, argv[0], props[i].atom);
        double num = 0.0;
        if (keyRaw && JS_ToFloat64(ctx, &num, val) == 0) {
          seed[keyRaw] = num;
        }
        if (keyRaw) {
          JS_FreeCString(ctx, keyRaw);
        }
        JS_FreeValue(ctx, val);
        JS_FreeValue(ctx, key);
        JS_FreeAtom(ctx, props[i].atom);
      }
      js_free(ctx, props);
    }
  }

  std::set<std::string> selectedModels;
  bool modelsFiltered = false;
  if (argc > 1 && !JS_IsUndefined(argv[1]) && !JS_IsNull(argv[1])) {
    if (JS_IsArray(ctx, argv[1]) != 1) {
      return JS_ThrowTypeError(
          ctx, "ctx.cascade modelNames must be an array of model names");
    }
    JSValue lengthVal = JS_GetPropertyStr(ctx, argv[1], "length");
    std::uint32_t modelCount = 0;
    const bool lengthOk = JS_ToUint32(ctx, &modelCount, lengthVal) == 0;
    JS_FreeValue(ctx, lengthVal);
    if (!lengthOk) {
      return JS_ThrowTypeError(
          ctx, "ctx.cascade modelNames must be an array of model names");
    }
    modelsFiltered = true;
    for (std::uint32_t i = 0; i < modelCount; ++i) {
      JSValue entry = JS_GetPropertyUint32(ctx, argv[1], i);
      if (!JS_IsString(entry)) {
        JS_FreeValue(ctx, entry);
        return JS_ThrowTypeError(
            ctx, "ctx.cascade modelNames entries must be strings");
      }
      const char* raw = JS_ToCString(ctx, entry);
      if (!raw) {
        JS_FreeValue(ctx, entry);
        return JS_ThrowTypeError(
            ctx, "ctx.cascade modelNames entries must be strings");
      }
      selectedModels.insert(raw);
      JS_FreeCString(ctx, raw);
      JS_FreeValue(ctx, entry);
    }
  }

  trech::ml::ScaleCascade cascade;
  for (const auto& [name, model] : state->models) {
    if (modelsFiltered && selectedModels.find(name) == selectedModels.end()) {
      continue;
    }
    const auto scaleIt = state->modelScales.find(name);
    const std::string scaleName = scaleIt != state->modelScales.end()
                                      ? scaleIt->second
                                      : std::string("");
    cascade.addStage(name, trech::ml::parseDimensionScale(scaleName),
                     model.get());
  }

  const trech::ml::CascadeResult run = cascade.run(seed);
  state->callPredictCount += static_cast<std::size_t>(run.stagesRun);
  state->totalPredictCount += static_cast<std::size_t>(run.stagesRun);
  state->callOutOfDomainCount +=
      static_cast<std::size_t>(run.stagesExtrapolating);
  state->totalOutOfDomainCount +=
      static_cast<std::size_t>(run.stagesExtrapolating);

  // Flat, ergonomic result: every fact + prediction as { name: value }.
  JSValue result = JS_NewObject(ctx);
  for (const auto& [key, value] : run.context) {
    JS_SetPropertyStr(ctx, result, key.c_str(), JS_NewFloat64(ctx, value));
  }

  // Reserved metadata: stage count + deterministic per-stage trace + the
  // (sorted) seed keys the cascade started from. seedKeys surfaces the ambient
  // Geant4 base a scenario can confirm was auto-populated (workstream 1).
  JSValue meta = JS_NewObject(ctx);
  JS_SetPropertyStr(ctx, meta, "stagesRun", JS_NewInt32(ctx, run.stagesRun));
  // Count of ran stages whose inputs fell outside their model's trained domain
  // -- the cascade's honest low-confidence signal (workstream 3). 0 means every
  // stage predicted in-distribution.
  JS_SetPropertyStr(ctx, meta, "stagesExtrapolating",
                    JS_NewInt32(ctx, run.stagesExtrapolating));
  // Count of ran stages applied OFF the dimension-scale band their model was
  // trained on (workstream 3b) -- 0 when every stage runs at a scale it learned.
  JS_SetPropertyStr(ctx, meta, "stagesScaleMismatched",
                    JS_NewInt32(ctx, run.stagesScaleMismatched));
  // Count of ran stages with an input in an unpopulated training bin (in-hull
  // hole / starved region, workstream-3 follow-up) -- 0 when every stage's
  // inputs sat in a region the training set actually sampled.
  JS_SetPropertyStr(ctx, meta, "stagesStarved",
                    JS_NewInt32(ctx, run.stagesStarved));
  std::vector<std::string> seedKeys;
  seedKeys.reserve(seed.size());
  for (const auto& [key, value] : seed) {
    (void)value;
    seedKeys.push_back(key);
  }
  std::sort(seedKeys.begin(), seedKeys.end());
  JSValue seedKeysArr = JS_NewArray(ctx);
  for (std::size_t si = 0; si < seedKeys.size(); ++si) {
    JS_SetPropertyUint32(ctx, seedKeysArr, static_cast<uint32_t>(si),
                         JS_NewString(ctx, seedKeys[si].c_str()));
  }
  JS_SetPropertyStr(ctx, meta, "seedKeys", seedKeysArr);
  JSValue trace = JS_NewArray(ctx);
  uint32_t ti = 0;
  for (const auto& stage : run.stages) {
    JSValue s = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, s, "model", JS_NewString(ctx, stage.model.c_str()));
    JS_SetPropertyStr(ctx, s, "scale",
                      JS_NewString(ctx, trech::ml::dimensionScaleName(stage.scale)));
    JS_SetPropertyStr(ctx, s, "ran", JS_NewBool(ctx, stage.ran));
    JSValue missing = JS_NewArray(ctx);
    for (std::size_t mi = 0; mi < stage.missingInputs.size(); ++mi) {
      JS_SetPropertyUint32(ctx, missing, static_cast<uint32_t>(mi),
                           JS_NewString(ctx, stage.missingInputs[mi].c_str()));
    }
    JS_SetPropertyStr(ctx, s, "missingInputs", missing);
    JSValue outs = JS_NewArray(ctx);
    for (std::size_t oi = 0; oi < stage.outputs.size(); ++oi) {
      JS_SetPropertyUint32(ctx, outs, static_cast<uint32_t>(oi),
                           JS_NewString(ctx, stage.outputs[oi].c_str()));
    }
    JS_SetPropertyStr(ctx, s, "outputs", outs);
    // Training-domain coverage for this stage (workstream 3): whether it
    // predicted in-distribution, how far it extrapolated (training-sigma units),
    // and which inputs sat outside the trained hull -- surfaced so a scenario /
    // Studio can flag a low-confidence stage instead of trusting a silent guess.
    JS_SetPropertyStr(ctx, s, "inDomain", JS_NewBool(ctx, stage.inDomain));
    JS_SetPropertyStr(ctx, s, "domainMeasured",
                      JS_NewBool(ctx, stage.domainMeasured));
    JS_SetPropertyStr(ctx, s, "extrapolation",
                      JS_NewFloat64(ctx, stage.extrapolation));
    JS_SetPropertyStr(ctx, s, "maxStandardizedDeviation",
                      JS_NewFloat64(ctx, stage.maxStandardizedDeviation));
    JSValue ood = JS_NewArray(ctx);
    for (std::size_t di = 0; di < stage.outOfDomainInputs.size(); ++di) {
      JS_SetPropertyUint32(ctx, ood, static_cast<uint32_t>(di),
                           JS_NewString(ctx, stage.outOfDomainInputs[di].c_str()));
    }
    JS_SetPropertyStr(ctx, s, "outOfDomainInputs", ood);
    JSValue starved = JS_NewArray(ctx);
    for (std::size_t vi = 0; vi < stage.starvedInputs.size(); ++vi) {
      JS_SetPropertyUint32(ctx, starved, static_cast<uint32_t>(vi),
                           JS_NewString(ctx, stage.starvedInputs[vi].c_str()));
    }
    JS_SetPropertyStr(ctx, s, "starvedInputs", starved);
    JS_SetPropertyStr(ctx, s, "jointMeasured",
                      JS_NewBool(ctx, stage.jointMeasured));
    JS_SetPropertyStr(ctx, s, "jointStarved",
                      stage.jointMeasured ? JS_NewBool(ctx, stage.jointStarved)
                                          : JS_NULL);
    JS_SetPropertyStr(ctx, s, "jointDistance",
                      stage.jointMeasured
                          ? JS_NewFloat64(ctx, stage.jointDistance)
                          : JS_NULL);
    JS_SetPropertyStr(ctx, s, "jointRadius",
                      stage.jointMeasured
                          ? JS_NewFloat64(ctx, stage.jointRadius)
                          : JS_NULL);
    // Training provenance / quality carried with the stage's model (workstream 3
    // b + c): applied off its trained band? which band(s)? and its held-out
    // accuracy (null, never 0, when the model carries no metrics).
    JS_SetPropertyStr(ctx, s, "scaleMismatch",
                      JS_NewBool(ctx, stage.scaleMismatch));
    JS_SetPropertyStr(ctx, s, "trainedScale",
                      JS_NewString(ctx, stage.trainedScale.c_str()));
    JS_SetPropertyStr(ctx, s, "holdoutR2",
                      stage.hasHoldout ? JS_NewFloat64(ctx, stage.holdoutR2)
                                       : JS_NULL);
    JS_SetPropertyStr(ctx, s, "holdoutSamples",
                      stage.hasHoldout ? JS_NewInt32(ctx, stage.holdoutSamples)
                                       : JS_NULL);
    // Per-output held-out error for the quantities this stage contributed:
    // `holdoutR2` above is the model's worst output, this is the split, and
    // `rmse` is a MEASURED 1-sigma residual in the quantity's own units. Absent
    // (empty object) for a model that carries no per-output metrics.
    JS_SetPropertyStr(ctx, s, "outputAccuracy",
                      newOutputAccuracyObject(ctx, stage.outputAccuracy));
    JS_SetPropertyUint32(ctx, trace, ti++, s);
  }
  JS_SetPropertyStr(ctx, meta, "trace", trace);
  JS_SetPropertyStr(ctx, result, "__cascade", meta);
  return result;
}

// --- ctx.evolve: the per-element inference OPERATOR ------------------------
//
// ctx.evolve(spec) -> { stagesRun, elementsEvolved, inferenceCount, trace, ... }
//                     | null
//
// Where ctx.cascade answers "given this context, what are the properties?",
// ctx.evolve answers "given this state, how does it CHANGE over dt?" -- the half
// of the physics scenarios have had to hand-write as JavaScript loops (a
// reaction rate law, a relaxation law, a transfer law). Declaring the state and
// letting scale-tagged trained models drive it moves that law out of the
// scenario and into the engine's inference layer, where it carries a training
// domain, a scale band and held-out accuracy like any other stage.
//
//   ctx.evolve({
//     dt: 0.04,
//     fields: [{ name: "gel", min: 0, max: 1 }, "temperature_k"],
//     state:  { gel: Float64Array, temperature_k: Float64Array },  // in place
//     aux:    { exposure: Float64Array },                          // read-only
//     context:{ ...whatever a ctx.cascade already inferred },
//     operator_role: "reaction_state",     // contextual default
//     element_kind: "foam_parcel",
//     models: ["reaction_operator"]        // optional explicit override
//   })
//
// A stage output named `d_<field>_dt` is a rate (accumulated across stages,
// integrated once over dt), `set_<field>` is an assignment, anything else is an
// intermediate a higher-scale stage can consume. The engine knows only the
// names; which fields exist and what bounds are physical are the scenario's
// declarations.
//
// The `state` arrays are mutated IN PLACE (they are typically Float64Arrays the
// scenario already owns), so an operator call allocates no per-step JS garbage.
// Like ctx.predict/ctx.cascade: deterministic, disabled in strict mode (returns
// null), degrades to leaving the state untouched when no model loads, and every
// model evaluation counts as one inference -- a batched operator over N
// elements reports N*stagesRun predictions rather than hiding them behind one
// call. The shared context always starts from the ambient Geant4 base, so the
// operator's run-constant facts are the real particle base by default.
namespace {

// Read an array-like JS value (Array or Float64Array) into `out` at `stride`
// spacing starting at `offset`; returns false when it is not array-like or is
// shorter than `count`.
bool readNumericSeries(JSContext* ctx, JSValueConst arr, std::size_t count,
                       std::size_t offset, std::size_t stride,
                       std::vector<double>* out) {
  if (!JS_IsObject(arr)) {
    return false;
  }
  JSValue lengthVal = JS_GetPropertyStr(ctx, arr, "length");
  std::uint32_t length = 0;
  const bool ok = JS_ToUint32(ctx, &length, lengthVal) == 0;
  JS_FreeValue(ctx, lengthVal);
  if (!ok || length < count) {
    return false;
  }
  for (std::size_t i = 0; i < count; ++i) {
    JSValue item = JS_GetPropertyUint32(ctx, arr, static_cast<uint32_t>(i));
    double num = 0.0;
    const bool numeric = JS_ToFloat64(ctx, &num, item) == 0;
    JS_FreeValue(ctx, item);
    if (!numeric) {
      return false;
    }
    (*out)[i * stride + offset] = num;
  }
  return true;
}

// Length of an array-like JS value, or -1 when it is not array-like.
long long numericSeriesLength(JSContext* ctx, JSValueConst arr) {
  if (!JS_IsObject(arr)) {
    return -1;
  }
  JSValue lengthVal = JS_GetPropertyStr(ctx, arr, "length");
  std::uint32_t length = 0;
  const bool ok = JS_ToUint32(ctx, &length, lengthVal) == 0;
  JS_FreeValue(ctx, lengthVal);
  return ok ? static_cast<long long>(length) : -1;
}

// Copy a numeric property from a JS object into a map, ignoring non-numerics.
void collectNumericProperties(JSContext* ctx, JSValueConst obj,
                              std::unordered_map<std::string, double>* out) {
  if (!JS_IsObject(obj)) {
    return;
  }
  JSPropertyEnum* props = nullptr;
  uint32_t propCount = 0;
  if (JS_GetOwnPropertyNames(ctx, &props, &propCount, obj,
                             JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) != 0) {
    return;
  }
  for (uint32_t i = 0; i < propCount; ++i) {
    JSValue key = JS_AtomToString(ctx, props[i].atom);
    const char* keyRaw = JS_ToCString(ctx, key);
    JSValue val = JS_GetProperty(ctx, obj, props[i].atom);
    double num = 0.0;
    if (keyRaw && JS_ToFloat64(ctx, &num, val) == 0) {
      (*out)[keyRaw] = num;
    }
    if (keyRaw) {
      JS_FreeCString(ctx, keyRaw);
    }
    JS_FreeValue(ctx, val);
    JS_FreeValue(ctx, key);
    JS_FreeAtom(ctx, props[i].atom);
  }
  js_free(ctx, props);
}

JSValue newStringArray(JSContext* ctx, const std::vector<std::string>& items) {
  JSValue arr = JS_NewArray(ctx);
  for (std::size_t i = 0; i < items.size(); ++i) {
    JS_SetPropertyUint32(ctx, arr, static_cast<uint32_t>(i),
                         JS_NewString(ctx, items[i].c_str()));
  }
  return arr;
}

struct OperatorSelectionEntry {
  std::string model;
  std::string role;
  std::string elementKind;
  std::string reason;
  std::vector<std::string> missingContextKeys;
  bool compatible = false;
  // Which requested element kind this compatibility verdict was reached FOR.
  // With several materials in one call the same model is judged once per kind.
  std::string requestedFor;
};

// One requested element kind (one material/species population) and the operator
// group it selected. A call over several kinds carries one group per kind, so a
// scenario is no longer locked to a single fixed operator for the whole run.
struct OperatorSelectionGroup {
  std::string elementKind;
  std::string status;                 // selected|ambiguous|no_compatible
  std::set<std::string> selected;
  std::size_t elementCount = 0;       // filled by the caller that knows the data
};

struct OperatorSelection {
  bool explicitSelection = false;
  std::string requestedRole;
  std::string requestedElementKind;   // scalar form (single-population call)
  // selected | partial | ambiguous | no_compatible. `partial` only occurs for a
  // multi-kind call where some materials selected an operator and others did
  // not -- the unselected ones are reported and left untouched.
  std::string status;
  std::set<std::string> selected;     // union over groups
  std::vector<OperatorSelectionGroup> groups;
  std::vector<OperatorSelectionEntry> trace;
};

std::string optionalStringProperty(JSContext* ctx, JSValueConst object,
                                   const char* snake, const char* camel) {
  JSValue value = JS_GetPropertyStr(ctx, object, snake);
  if (JS_IsUndefined(value) && camel) {
    JS_FreeValue(ctx, value);
    value = JS_GetPropertyStr(ctx, object, camel);
  }
  std::string out;
  if (JS_IsString(value)) {
    const char* raw = JS_ToCString(ctx, value);
    if (raw) {
      out = raw;
      JS_FreeCString(ctx, raw);
    }
  }
  JS_FreeValue(ctx, value);
  return out;
}

bool objectKeysWithin(JSContext* ctx, JSValueConst object,
                      const std::set<std::string>& allowed,
                      std::string* unexpected) {
  if (!JS_IsObject(object)) {
    return false;
  }
  JSPropertyEnum* props = nullptr;
  uint32_t count = 0;
  if (JS_GetOwnPropertyNames(ctx, &props, &count, object,
                             JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) != 0) {
    return false;
  }
  bool valid = true;
  for (uint32_t i = 0; i < count; ++i) {
    JSValue key = JS_AtomToString(ctx, props[i].atom);
    const char* raw = JS_ToCString(ctx, key);
    if (raw && allowed.find(raw) == allowed.end() && valid) {
      valid = false;
      if (unexpected) {
        *unexpected = raw;
      }
    }
    if (raw) {
      JS_FreeCString(ctx, raw);
    }
    JS_FreeValue(ctx, key);
    JS_FreeAtom(ctx, props[i].atom);
  }
  js_free(ctx, props);
  return valid;
}

// Match the loaded operator models against one requested role + element kind.
// Returns the status and fills `trace` with a per-model verdict tagged with the
// kind it was judged for.
OperatorSelectionGroup matchOperatorGroup(
    const JsRuntimeState* state, const std::string& requestedRole,
    const std::string& requestedElementKind,
    const std::unordered_map<std::string, double>& shared,
    std::vector<OperatorSelectionEntry>* trace) {
  OperatorSelectionGroup group;
  group.elementKind = requestedElementKind;
  std::map<std::pair<std::string, std::string>, std::vector<std::string>>
      compatibleGroups;
  const std::size_t traceBegin = trace->size();
  for (const auto& [name, model] : state->models) {
    OperatorSelectionEntry entry;
    entry.model = name;
    entry.requestedFor = requestedElementKind;
    const auto metaIt = state->modelOperatorMetadata.find(name);
    if (metaIt != state->modelOperatorMetadata.end()) {
      entry.role = metaIt->second.role;
      entry.elementKind = metaIt->second.elementKind;
    }
    if (!model || !model->loaded()) {
      entry.reason = "unloaded";
    } else if (entry.role.empty()) {
      entry.reason = "not_operator";
    } else if (entry.elementKind.empty()) {
      entry.reason = "missing_element_kind_metadata";
    } else if (!requestedRole.empty() && entry.role != requestedRole) {
      entry.reason = "role_mismatch";
    } else if (!requestedElementKind.empty() &&
               entry.elementKind != requestedElementKind) {
      entry.reason = "element_kind_mismatch";
    } else {
      for (const std::string& key : metaIt->second.requiredContextKeys) {
        if (shared.find(key) == shared.end()) {
          entry.missingContextKeys.push_back(key);
        }
      }
      if (!entry.missingContextKeys.empty()) {
        entry.reason = "missing_context";
      } else {
        entry.compatible = true;
        entry.reason = "compatible";
        compatibleGroups[{entry.role, entry.elementKind}].push_back(name);
      }
    }
    trace->push_back(std::move(entry));
  }
  if (compatibleGroups.empty()) {
    group.status = "no_compatible";
  } else if (compatibleGroups.size() > 1) {
    group.status = "ambiguous";
    // Compatibility means "could run", not "selected". Make the distinction
    // explicit in the trace while declining all mutation for this kind.
    for (std::size_t i = traceBegin; i < trace->size(); ++i) {
      if ((*trace)[i].compatible) {
        (*trace)[i].reason = "ambiguous_group";
      }
    }
  } else {
    group.status = "selected";
    group.selected.insert(compatibleGroups.begin()->second.begin(),
                          compatibleGroups.begin()->second.end());
  }
  return group;
}

// `elementKinds` non-empty selects PER KIND (one group each): the multi-material
// form, where every population in the same call is matched to its own operator.
// Read an optional per-element material-kind array from a spec
// (`element_kind` / `element_kinds`, singular string = "not per element").
// Fills `names` with the deterministic sorted vocabulary and `indexOf` with one
// index per element. Returns false when the property is absent or scalar.
bool readElementKinds(JSContext* ctx, JSValueConst spec, std::size_t elementCount,
                      std::vector<std::string>* names,
                      std::vector<std::size_t>* indexOf) {
  JSValue value = JS_GetPropertyStr(ctx, spec, "element_kinds");
  if (JS_IsUndefined(value)) {
    JS_FreeValue(ctx, value);
    value = JS_GetPropertyStr(ctx, spec, "elementKinds");
  }
  if (JS_IsUndefined(value)) {
    JS_FreeValue(ctx, value);
    JSValue single = JS_GetPropertyStr(ctx, spec, "element_kind");
    if (JS_IsUndefined(single)) {
      JS_FreeValue(ctx, single);
      single = JS_GetPropertyStr(ctx, spec, "elementKind");
    }
    if (JS_IsString(single)) {
      JS_FreeValue(ctx, single);  // scalar form: one population
      return false;
    }
    value = single;
  }
  const long long count = numericSeriesLength(ctx, value);
  if (count < static_cast<long long>(elementCount) || elementCount == 0) {
    JS_FreeValue(ctx, value);
    return false;
  }
  std::vector<std::string> perElement(elementCount);
  std::map<std::string, std::size_t> indexOfKind;
  for (std::size_t e = 0; e < elementCount; ++e) {
    JSValue item = JS_GetPropertyUint32(ctx, value, static_cast<uint32_t>(e));
    const char* raw = JS_ToCString(ctx, item);
    if (raw) {
      perElement[e] = raw;
      JS_FreeCString(ctx, raw);
    }
    JS_FreeValue(ctx, item);
    indexOfKind.emplace(perElement[e], 0);
  }
  JS_FreeValue(ctx, value);
  std::size_t next = 0;
  names->clear();
  for (auto& [name, index] : indexOfKind) {
    index = next++;
    names->push_back(name);  // sorted: kind indices never depend on element order
  }
  indexOf->assign(elementCount, trech::ml::kAnyElementKind);
  for (std::size_t e = 0; e < elementCount; ++e) {
    (*indexOf)[e] = indexOfKind[perElement[e]];
  }
  return true;
}

OperatorSelection selectOperatorModels(
    JSContext* ctx, JSValueConst spec, const JsRuntimeState* state,
    const std::unordered_map<std::string, double>& shared,
    const std::vector<std::string>& elementKinds = {}) {
  OperatorSelection selection;
  JSValue modelsVal = JS_GetPropertyStr(ctx, spec, "models");
  const long long modelCount = numericSeriesLength(ctx, modelsVal);
  if (modelCount >= 0) {
    selection.explicitSelection = true;
    for (long long i = 0; i < modelCount; ++i) {
      JSValue item =
          JS_GetPropertyUint32(ctx, modelsVal, static_cast<uint32_t>(i));
      const char* raw = JS_ToCString(ctx, item);
      if (raw) {
        selection.selected.insert(raw);
        JS_FreeCString(ctx, raw);
      }
      JS_FreeValue(ctx, item);
    }
  }
  JS_FreeValue(ctx, modelsVal);
  selection.requestedRole =
      optionalStringProperty(ctx, spec, "operator_role", "operatorRole");
  selection.requestedElementKind =
      optionalStringProperty(ctx, spec, "element_kind", "elementKind");

  if (selection.explicitSelection) {
    for (const std::string& name : selection.selected) {
      OperatorSelectionEntry entry;
      entry.model = name;
      const auto modelIt = state->models.find(name);
      if (modelIt == state->models.end()) {
        entry.reason = "unknown_model";
      } else {
        entry.compatible = true;
        entry.reason = "explicit_override";
        const auto metaIt = state->modelOperatorMetadata.find(name);
        if (metaIt != state->modelOperatorMetadata.end()) {
          entry.role = metaIt->second.role;
          entry.elementKind = metaIt->second.elementKind;
        }
      }
      selection.trace.push_back(std::move(entry));
    }
    selection.status =
        std::any_of(selection.trace.begin(), selection.trace.end(),
                    [](const OperatorSelectionEntry& entry) {
                      return entry.compatible;
                    })
            ? "selected"
            : "no_compatible";
    // An explicit model list applies to every requested kind.
    for (const std::string& kind : elementKinds) {
      OperatorSelectionGroup group;
      group.elementKind = kind;
      group.status = selection.status;
      group.selected = selection.selected;
      selection.groups.push_back(std::move(group));
    }
    return selection;
  }

  const std::vector<std::string> kinds =
      elementKinds.empty()
          ? std::vector<std::string>{selection.requestedElementKind}
          : elementKinds;
  std::size_t selectedGroups = 0;
  for (const std::string& kind : kinds) {
    OperatorSelectionGroup group = matchOperatorGroup(
        state, selection.requestedRole, kind, shared, &selection.trace);
    if (group.status == "selected") {
      ++selectedGroups;
      selection.selected.insert(group.selected.begin(), group.selected.end());
    }
    selection.groups.push_back(std::move(group));
  }
  if (elementKinds.empty()) {
    // Single-population call: the run's status IS that one group's status
    // (unchanged contract).
    selection.status = selection.groups.front().status;
  } else if (selectedGroups == kinds.size()) {
    selection.status = "selected";
  } else if (selectedGroups == 0) {
    // Nothing selected anywhere: report the shared reason when the kinds agree.
    const bool anyAmbiguous =
        std::any_of(selection.groups.begin(), selection.groups.end(),
                    [](const OperatorSelectionGroup& g) {
                      return g.status == "ambiguous";
                    });
    selection.status = anyAmbiguous ? "ambiguous" : "no_compatible";
  } else {
    // Some materials have an operator and some do not. The ones that do run;
    // the ones that do not are reported and left untouched -- never advanced by
    // another material's law.
    selection.status = "partial";
  }
  return selection;
}

JSValue operatorSelectionToJs(JSContext* ctx,
                              const OperatorSelection& selection) {
  JSValue out = JS_NewObject(ctx);
  JS_SetPropertyStr(
      ctx, out, "mode",
      JS_NewString(ctx, selection.explicitSelection ? "explicit"
                                                    : "contextual"));
  JS_SetPropertyStr(ctx, out, "status",
                    JS_NewString(ctx, selection.status.c_str()));
  JS_SetPropertyStr(ctx, out, "operatorRole",
                    JS_NewString(ctx, selection.requestedRole.c_str()));
  JS_SetPropertyStr(
      ctx, out, "elementKind",
      JS_NewString(ctx, selection.requestedElementKind.c_str()));
  const std::vector<std::string> selectedNames(selection.selected.begin(),
                                                selection.selected.end());
  JS_SetPropertyStr(ctx, out, "selectedModels",
                    newStringArray(ctx, selectedNames));
  // Per-material groups: which operator each requested element kind selected,
  // and how many elements it covers. Present for every call (one entry for the
  // single-population form) so a consumer reads one shape.
  JSValue groups = JS_NewArray(ctx);
  for (std::size_t g = 0; g < selection.groups.size(); ++g) {
    const OperatorSelectionGroup& group = selection.groups[g];
    JSValue item = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, item, "elementKind",
                      JS_NewString(ctx, group.elementKind.c_str()));
    JS_SetPropertyStr(ctx, item, "status",
                      JS_NewString(ctx, group.status.c_str()));
    const std::vector<std::string> names(group.selected.begin(),
                                         group.selected.end());
    JS_SetPropertyStr(ctx, item, "selectedModels", newStringArray(ctx, names));
    JS_SetPropertyStr(
        ctx, item, "elements",
        JS_NewInt64(ctx, static_cast<std::int64_t>(group.elementCount)));
    JS_SetPropertyUint32(ctx, groups, static_cast<uint32_t>(g), item);
  }
  JS_SetPropertyStr(ctx, out, "groups", groups);
  JSValue trace = JS_NewArray(ctx);
  for (std::size_t i = 0; i < selection.trace.size(); ++i) {
    const OperatorSelectionEntry& entry = selection.trace[i];
    JSValue item = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, item, "model",
                      JS_NewString(ctx, entry.model.c_str()));
    JS_SetPropertyStr(ctx, item, "operatorRole",
                      JS_NewString(ctx, entry.role.c_str()));
    JS_SetPropertyStr(ctx, item, "elementKind",
                      JS_NewString(ctx, entry.elementKind.c_str()));
    JS_SetPropertyStr(ctx, item, "requestedFor",
                      JS_NewString(ctx, entry.requestedFor.c_str()));
    JS_SetPropertyStr(ctx, item, "compatible",
                      JS_NewBool(ctx, entry.compatible));
    JS_SetPropertyStr(ctx, item, "reason",
                      JS_NewString(ctx, entry.reason.c_str()));
    JS_SetPropertyStr(ctx, item, "missingContextKeys",
                      newStringArray(ctx, entry.missingContextKeys));
    JS_SetPropertyUint32(ctx, trace, static_cast<uint32_t>(i), item);
  }
  JS_SetPropertyStr(ctx, out, "trace", trace);
  return out;
}

}  // namespace

static JSValue jsHookEvolve(JSContext* ctx, JSValueConst /*this_val*/, int argc,
                            JSValueConst* argv) {
  auto* state = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  if (!state) {
    return JS_EXCEPTION;
  }
  // Strict mode disables learned inference (determinism invariant).
  if (normalizeDeterminismMode(state->activeHookContext.determinismMode) !=
      "predictive") {
    return JS_NULL;
  }
  if (argc < 1 || !JS_IsObject(argv[0])) {
    return JS_ThrowTypeError(ctx, "ctx.evolve(spec) requires a spec object");
  }
  JSValueConst spec = argv[0];

  trech::ml::EvolutionRequest request;

  JSValue dtVal = JS_GetPropertyStr(ctx, spec, "dt");
  if (JS_ToFloat64(ctx, &request.dt, dtVal) != 0) {
    request.dt = 0.0;
  }
  JS_FreeValue(ctx, dtVal);

  // ---- declared fields: "name" or { name, min, max } ----------------------
  JSValue fieldsVal = JS_GetPropertyStr(ctx, spec, "fields");
  const long long fieldCountRaw = numericSeriesLength(ctx, fieldsVal);
  if (fieldCountRaw <= 0) {
    JS_FreeValue(ctx, fieldsVal);
    return JS_ThrowTypeError(ctx, "ctx.evolve spec.fields must be a non-empty array");
  }
  for (long long i = 0; i < fieldCountRaw; ++i) {
    JSValue entry = JS_GetPropertyUint32(ctx, fieldsVal, static_cast<uint32_t>(i));
    trech::ml::EvolutionField field;
    if (JS_IsString(entry)) {
      const char* raw = JS_ToCString(ctx, entry);
      if (raw) {
        field.name = raw;
        JS_FreeCString(ctx, raw);
      }
    } else if (JS_IsObject(entry)) {
      JSValue nameVal = JS_GetPropertyStr(ctx, entry, "name");
      const char* raw = JS_ToCString(ctx, nameVal);
      if (raw) {
        field.name = raw;
        JS_FreeCString(ctx, raw);
      }
      JS_FreeValue(ctx, nameVal);
      JSValue minVal = JS_GetPropertyStr(ctx, entry, "min");
      double bound = 0.0;
      if (!JS_IsUndefined(minVal) && JS_ToFloat64(ctx, &bound, minVal) == 0) {
        field.minValue = bound;
      }
      JS_FreeValue(ctx, minVal);
      JSValue maxVal = JS_GetPropertyStr(ctx, entry, "max");
      if (!JS_IsUndefined(maxVal) && JS_ToFloat64(ctx, &bound, maxVal) == 0) {
        field.maxValue = bound;
      }
      JS_FreeValue(ctx, maxVal);
    }
    JS_FreeValue(ctx, entry);
    if (field.name.empty()) {
      JS_FreeValue(ctx, fieldsVal);
      return JS_ThrowTypeError(ctx, "ctx.evolve spec.fields entries need a name");
    }
    request.fields.push_back(std::move(field));
  }
  JS_FreeValue(ctx, fieldsVal);
  const std::size_t fieldCount = request.fields.size();

  // ---- per-element state arrays (mutated in place) ------------------------
  JSValue stateObj = JS_GetPropertyStr(ctx, spec, "state");
  if (!JS_IsObject(stateObj)) {
    JS_FreeValue(ctx, stateObj);
    return JS_ThrowTypeError(ctx, "ctx.evolve spec.state must be an object of arrays");
  }
  std::vector<JSValue> stateArrays(fieldCount, JS_UNDEFINED);
  auto releaseStateArrays = [&]() {
    for (JSValue& v : stateArrays) {
      JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, stateObj);
  };
  long long elementCount = -1;
  for (std::size_t f = 0; f < fieldCount; ++f) {
    stateArrays[f] = JS_GetPropertyStr(ctx, stateObj, request.fields[f].name.c_str());
    const long long len = numericSeriesLength(ctx, stateArrays[f]);
    if (len < 0) {
      const std::string name = request.fields[f].name;
      releaseStateArrays();
      return JS_ThrowTypeError(ctx, "ctx.evolve spec.state.%s must be an array",
                               name.c_str());
    }
    if (elementCount < 0) {
      elementCount = len;
    } else if (len != elementCount) {
      const std::string name = request.fields[f].name;
      releaseStateArrays();
      return JS_ThrowTypeError(
          ctx, "ctx.evolve spec.state.%s length %lld != %lld (every field must "
               "cover the same elements)",
          name.c_str(), len, elementCount);
    }
  }
  if (elementCount <= 0) {
    releaseStateArrays();
    return JS_NULL;  // no elements: nothing to evolve, and nothing to report
  }
  request.elementCount = static_cast<std::size_t>(elementCount);
  request.state.assign(request.elementCount * fieldCount, 0.0);
  for (std::size_t f = 0; f < fieldCount; ++f) {
    if (!readNumericSeries(ctx, stateArrays[f], request.elementCount, f,
                           fieldCount, &request.state)) {
      const std::string name = request.fields[f].name;
      releaseStateArrays();
      return JS_ThrowTypeError(ctx, "ctx.evolve spec.state.%s is not numeric",
                               name.c_str());
    }
  }

  // ---- read-only per-element aux facts ------------------------------------
  JSValue auxObj = JS_GetPropertyStr(ctx, spec, "aux");
  if (JS_IsObject(auxObj)) {
    JSPropertyEnum* props = nullptr;
    uint32_t propCount = 0;
    if (JS_GetOwnPropertyNames(ctx, &props, &propCount, auxObj,
                               JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) == 0) {
      for (uint32_t i = 0; i < propCount; ++i) {
        JSValue key = JS_AtomToString(ctx, props[i].atom);
        const char* keyRaw = JS_ToCString(ctx, key);
        JSValue val = JS_GetProperty(ctx, auxObj, props[i].atom);
        if (keyRaw && numericSeriesLength(ctx, val) >=
                          static_cast<long long>(request.elementCount)) {
          request.auxNames.push_back(keyRaw);
        }
        JS_FreeValue(ctx, val);
        if (keyRaw) {
          JS_FreeCString(ctx, keyRaw);
        }
        JS_FreeValue(ctx, key);
        JS_FreeAtom(ctx, props[i].atom);
      }
      js_free(ctx, props);
    }
    // Deterministic aux ordering regardless of property-enumeration order.
    std::sort(request.auxNames.begin(), request.auxNames.end());
    const std::size_t auxCount = request.auxNames.size();
    request.aux.assign(request.elementCount * auxCount, 0.0);
    for (std::size_t a = 0; a < auxCount; ++a) {
      JSValue arr = JS_GetPropertyStr(ctx, auxObj, request.auxNames[a].c_str());
      readNumericSeries(ctx, arr, request.elementCount, a, auxCount, &request.aux);
      JS_FreeValue(ctx, arr);
    }
  }
  JS_FreeValue(ctx, auxObj);

  // ---- run-constant shared context: ambient Geant4 base, then overrides ----
  request.shared = buildAmbientGeant4Seed(state->activeHookContext);
  JSValue contextObj = JS_GetPropertyStr(ctx, spec, "context");
  collectNumericProperties(ctx, contextObj, &request.shared);
  JS_FreeValue(ctx, contextObj);

  // ---- per-element material kinds (dynamic, in-scenario operator level) ----
  // `element_kind` may be a single string (one population) OR an array of
  // per-element kinds. The array form is what lets ONE call advance several
  // materials: each kind selects its own operator from its own context, so the
  // inference level is not fixed for the run -- a wax parcel and a carrier cell
  // in the same state arrays are advanced by different trained operators, and a
  // material that selects nothing is left untouched rather than being pushed
  // through someone else's law.
  std::vector<std::string> requestedKinds;
  if (readElementKinds(ctx, spec, request.elementCount,
                       &request.elementKindNames, &request.elementKindIndex)) {
    requestedKinds = request.elementKindNames;
  }

  // ---- stage selection: explicit override or contextual role match --------
  OperatorSelection selection =
      selectOperatorModels(ctx, spec, state, request.shared, requestedKinds);
  for (OperatorSelectionGroup& group : selection.groups) {
    std::size_t index = 0;
    while (index < request.elementKindNames.size() &&
           request.elementKindNames[index] != group.elementKind) {
      ++index;
    }
    if (index < request.elementKindNames.size()) {
      for (std::size_t e = 0; e < request.elementKindIndex.size(); ++e) {
        if (request.elementKindIndex[e] == index) {
          ++group.elementCount;
        }
      }
    } else {
      group.elementCount = request.elementCount;  // single-population call
    }
  }

  trech::ml::StateEvolution op;
  for (std::size_t g = 0; g < selection.groups.size(); ++g) {
    const OperatorSelectionGroup& group = selection.groups[g];
    // Bind each group's stages to its own element kind (or to every element for
    // the single-population form).
    std::size_t kindIndex = trech::ml::kAnyElementKind;
    if (!request.elementKindNames.empty()) {
      for (std::size_t i = 0; i < request.elementKindNames.size(); ++i) {
        if (request.elementKindNames[i] == group.elementKind) {
          kindIndex = i;
          break;
        }
      }
    }
    for (const auto& [name, model] : state->models) {
      if (group.selected.find(name) == group.selected.end()) {
        continue;
      }
      const auto scaleIt = state->modelScales.find(name);
      const std::string scaleName =
          scaleIt != state->modelScales.end() ? scaleIt->second : std::string("");
      op.addStage(name, trech::ml::parseDimensionScale(scaleName), model.get(),
                  kindIndex);
    }
  }

  const trech::ml::EvolutionResult run = op.evolve(request);

  // ---- write the evolved state back into the caller's own arrays ----------
  if (run.ran) {
    for (std::size_t f = 0; f < fieldCount; ++f) {
      for (std::size_t e = 0; e < request.elementCount; ++e) {
        JS_SetPropertyUint32(
            ctx, stateArrays[f], static_cast<uint32_t>(e),
            JS_NewFloat64(ctx, run.state[e * fieldCount + f]));
      }
    }
  }
  releaseStateArrays();

  // Every model evaluation is one inference, so a batched operator cannot hide
  // N predictions behind a single call (same accounting as ctx.predict).
  state->callPredictCount += run.inferenceCount;
  state->totalPredictCount += run.inferenceCount;
  state->callOutOfDomainCount += run.outOfDomainInferenceCount;
  state->totalOutOfDomainCount += run.outOfDomainInferenceCount;

  JSValue result = JS_NewObject(ctx);
  JS_SetPropertyStr(ctx, result, "ran", JS_NewBool(ctx, run.ran));
  JS_SetPropertyStr(ctx, result, "stagesRun", JS_NewInt32(ctx, run.stagesRun));
  JS_SetPropertyStr(ctx, result, "stagesExtrapolating",
                    JS_NewInt32(ctx, run.stagesExtrapolating));
  JS_SetPropertyStr(ctx, result, "stagesScaleMismatched",
                    JS_NewInt32(ctx, run.stagesScaleMismatched));
  JS_SetPropertyStr(ctx, result, "stagesStarved",
                    JS_NewInt32(ctx, run.stagesStarved));
  JS_SetPropertyStr(ctx, result, "elementsEvolved",
                    JS_NewInt64(ctx, static_cast<std::int64_t>(run.elementsEvolved)));
  JS_SetPropertyStr(ctx, result, "inferenceCount",
                    JS_NewInt64(ctx, static_cast<std::int64_t>(run.inferenceCount)));
  JS_SetPropertyStr(
      ctx, result, "outOfDomainInferences",
      JS_NewInt64(ctx, static_cast<std::int64_t>(run.outOfDomainInferenceCount)));
  std::vector<std::string> sharedKeys;
  sharedKeys.reserve(request.shared.size());
  for (const auto& [key, value] : request.shared) {
    (void)value;
    sharedKeys.push_back(key);
  }
  std::sort(sharedKeys.begin(), sharedKeys.end());
  JS_SetPropertyStr(ctx, result, "sharedKeys", newStringArray(ctx, sharedKeys));
  JS_SetPropertyStr(ctx, result, "auxKeys",
                    newStringArray(ctx, request.auxNames));
  JS_SetPropertyStr(ctx, result, "selection",
                    operatorSelectionToJs(ctx, selection));

  JSValue trace = JS_NewArray(ctx);
  uint32_t ti = 0;
  for (const auto& stage : run.stages) {
    JSValue s = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, s, "model", JS_NewString(ctx, stage.model.c_str()));
    JS_SetPropertyStr(ctx, s, "scale",
                      JS_NewString(ctx, trech::ml::dimensionScaleName(stage.scale)));
    JS_SetPropertyStr(ctx, s, "ran", JS_NewBool(ctx, stage.ran));
    JS_SetPropertyStr(ctx, s, "missingInputs",
                      newStringArray(ctx, stage.missingInputs));
    JS_SetPropertyStr(ctx, s, "integratedFields",
                      newStringArray(ctx, stage.integratedFields));
    JS_SetPropertyStr(ctx, s, "assignedFields",
                      newStringArray(ctx, stage.assignedFields));
    JS_SetPropertyStr(ctx, s, "intermediateOutputs",
                      newStringArray(ctx, stage.intermediateOutputs));
    JS_SetPropertyStr(ctx, s, "unappliedFieldOutputs",
                      newStringArray(ctx, stage.unappliedFieldOutputs));
    // Which material population this stage was bound to, and how many of its
    // elements it actually evaluated (a multi-material call runs each kind's
    // own operator over its own elements).
    JS_SetPropertyStr(ctx, s, "elementKind",
                      JS_NewString(ctx, stage.elementKind.c_str()));
    JS_SetPropertyStr(
        ctx, s, "elementsMatched",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.elementsMatched)));
    // Per-element trust profile, aggregated: how many elements this stage
    // predicted out of its trained domain, and how far the worst one sat past
    // the hull edge (training-sigma units).
    JS_SetPropertyStr(ctx, s, "domainMeasured",
                      JS_NewBool(ctx, stage.domainMeasured));
    JS_SetPropertyStr(
        ctx, s, "elementsOutOfDomain",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.elementsOutOfDomain)));
    JS_SetPropertyStr(
        ctx, s, "elementsStarved",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.elementsStarved)));
    JS_SetPropertyStr(
        ctx, s, "elementsJointStarved",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.elementsJointStarved)));
    JS_SetPropertyStr(ctx, s, "maxJointDistance",
                      stage.jointMeasured
                          ? JS_NewFloat64(ctx, stage.maxJointDistance)
                          : JS_NULL);
    JS_SetPropertyStr(ctx, s, "maxExtrapolation",
                      JS_NewFloat64(ctx, stage.maxExtrapolation));
    JS_SetPropertyStr(ctx, s, "maxStandardizedDeviation",
                      JS_NewFloat64(ctx, stage.maxStandardizedDeviation));
    JS_SetPropertyStr(ctx, s, "outOfDomainInputs",
                      newStringArray(ctx, stage.outOfDomainInputs));
    JS_SetPropertyStr(ctx, s, "starvedInputs",
                      newStringArray(ctx, stage.starvedInputs));
    JS_SetPropertyStr(ctx, s, "scaleMismatch",
                      JS_NewBool(ctx, stage.scaleMismatch));
    JS_SetPropertyStr(ctx, s, "trainedScale",
                      JS_NewString(ctx, stage.trainedScale.c_str()));
    JS_SetPropertyStr(ctx, s, "holdoutR2",
                      stage.hasHoldout ? JS_NewFloat64(ctx, stage.holdoutR2)
                                       : JS_NULL);
    JS_SetPropertyStr(ctx, s, "holdoutSamples",
                      stage.hasHoldout ? JS_NewInt32(ctx, stage.holdoutSamples)
                                       : JS_NULL);
    JS_SetPropertyStr(ctx, s, "outputAccuracy",
                      newOutputAccuracyObject(ctx, stage.outputAccuracy));
    JS_SetPropertyUint32(ctx, trace, ti++, s);
  }
  JS_SetPropertyStr(ctx, result, "trace", trace);
  return result;
}

// --- ctx.react: learned, seeded, discrete integer-state transitions --------
//
// The scenario declares integer species inventories, a stoichiometric channel
// matrix, and conserved linear quantities (atoms, charge, packet identity).
// Learned models predict bounded hazards; the engine owns the RNG draw,
// availability, conservation, and atomic state mutation.
static JSValue jsHookReact(JSContext* ctx, JSValueConst /*this_val*/, int argc,
                           JSValueConst* argv) {
  auto* runtime = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  if (!runtime) {
    return JS_EXCEPTION;
  }
  if (normalizeDeterminismMode(runtime->activeHookContext.determinismMode) !=
      "predictive") {
    return JS_NULL;  // strict: no inference, no RNG consumption, no mutation
  }
  if (argc < 1 || !JS_IsObject(argv[0])) {
    return JS_ThrowTypeError(ctx, "ctx.react(spec) requires a spec object");
  }
  JSValueConst spec = argv[0];
  trech::ml::DiscreteTransitionRequest request;

  JSValue dtVal = JS_GetPropertyStr(ctx, spec, "dt");
  if (JS_ToFloat64(ctx, &request.dt, dtVal) != 0) {
    request.dt = 0.0;
  }
  JS_FreeValue(ctx, dtVal);

  // ---- species names ------------------------------------------------------
  JSValue speciesVal = JS_GetPropertyStr(ctx, spec, "species");
  const long long speciesCountRaw = numericSeriesLength(ctx, speciesVal);
  if (speciesCountRaw <= 0) {
    JS_FreeValue(ctx, speciesVal);
    return JS_ThrowTypeError(
        ctx, "ctx.react spec.species must be a non-empty string array");
  }
  for (long long i = 0; i < speciesCountRaw; ++i) {
    JSValue entry =
        JS_GetPropertyUint32(ctx, speciesVal, static_cast<uint32_t>(i));
    if (!JS_IsString(entry)) {
      JS_FreeValue(ctx, entry);
      JS_FreeValue(ctx, speciesVal);
      return JS_ThrowTypeError(
          ctx, "ctx.react spec.species entries must be strings");
    }
    const char* raw = JS_ToCString(ctx, entry);
    request.speciesNames.emplace_back(raw ? raw : "");
    if (raw) {
      JS_FreeCString(ctx, raw);
    }
    JS_FreeValue(ctx, entry);
  }
  JS_FreeValue(ctx, speciesVal);
  const std::size_t speciesCount = request.speciesNames.size();
  const std::set<std::string> speciesSet(request.speciesNames.begin(),
                                         request.speciesNames.end());

  // ---- integer state arrays, retained for in-place writeback --------------
  JSValue stateObj = JS_GetPropertyStr(ctx, spec, "state");
  if (!JS_IsObject(stateObj)) {
    JS_FreeValue(ctx, stateObj);
    return JS_ThrowTypeError(
        ctx, "ctx.react spec.state must be an object of integer arrays");
  }
  std::vector<JSValue> stateArrays(speciesCount, JS_UNDEFINED);
  auto releaseState = [&]() {
    for (JSValue& array : stateArrays) {
      JS_FreeValue(ctx, array);
    }
    JS_FreeValue(ctx, stateObj);
  };
  long long elementCount = -1;
  for (std::size_t s = 0; s < speciesCount; ++s) {
    stateArrays[s] =
        JS_GetPropertyStr(ctx, stateObj, request.speciesNames[s].c_str());
    const long long length = numericSeriesLength(ctx, stateArrays[s]);
    if (length < 0) {
      const std::string name = request.speciesNames[s];
      releaseState();
      return JS_ThrowTypeError(
          ctx, "ctx.react spec.state.%s must be an integer array",
          name.c_str());
    }
    if (elementCount < 0) {
      elementCount = length;
    } else if (length != elementCount) {
      const std::string name = request.speciesNames[s];
      releaseState();
      return JS_ThrowTypeError(
          ctx, "ctx.react spec.state.%s length %lld != %lld", name.c_str(),
          length, elementCount);
    }
  }
  if (elementCount <= 0) {
    releaseState();
    return JS_NULL;
  }
  request.elementCount = static_cast<std::size_t>(elementCount);
  request.state.assign(request.elementCount * speciesCount, 0);
  constexpr double kMaxExactInteger = 9007199254740991.0;  // 2^53 - 1
  for (std::size_t s = 0; s < speciesCount; ++s) {
    for (std::size_t e = 0; e < request.elementCount; ++e) {
      JSValue item =
          JS_GetPropertyUint32(ctx, stateArrays[s], static_cast<uint32_t>(e));
      double value = 0.0;
      const bool integer =
          JS_ToFloat64(ctx, &value, item) == 0 && std::isfinite(value) &&
          std::trunc(value) == value && std::abs(value) <= kMaxExactInteger;
      JS_FreeValue(ctx, item);
      if (!integer) {
        const std::string name = request.speciesNames[s];
        releaseState();
        return JS_ThrowTypeError(
            ctx, "ctx.react spec.state.%s must contain exact integers",
            name.c_str());
      }
      request.state[e * speciesCount + s] =
          static_cast<std::int64_t>(value);
    }
  }

  // ---- optional per-element aux arrays -----------------------------------
  JSValue auxObj = JS_GetPropertyStr(ctx, spec, "aux");
  if (JS_IsObject(auxObj)) {
    JSPropertyEnum* props = nullptr;
    uint32_t propCount = 0;
    if (JS_GetOwnPropertyNames(ctx, &props, &propCount, auxObj,
                               JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) == 0) {
      for (uint32_t i = 0; i < propCount; ++i) {
        JSValue key = JS_AtomToString(ctx, props[i].atom);
        const char* raw = JS_ToCString(ctx, key);
        JSValue value = JS_GetProperty(ctx, auxObj, props[i].atom);
        if (raw && numericSeriesLength(ctx, value) >= elementCount) {
          request.auxNames.push_back(raw);
        }
        JS_FreeValue(ctx, value);
        if (raw) {
          JS_FreeCString(ctx, raw);
        }
        JS_FreeValue(ctx, key);
        JS_FreeAtom(ctx, props[i].atom);
      }
      js_free(ctx, props);
    }
    std::sort(request.auxNames.begin(), request.auxNames.end());
    request.aux.assign(request.elementCount * request.auxNames.size(), 0.0);
    for (std::size_t a = 0; a < request.auxNames.size(); ++a) {
      JSValue array =
          JS_GetPropertyStr(ctx, auxObj, request.auxNames[a].c_str());
      if (!readNumericSeries(ctx, array, request.elementCount, a,
                             request.auxNames.size(), &request.aux)) {
        JS_FreeValue(ctx, array);
        JS_FreeValue(ctx, auxObj);
        releaseState();
        return JS_ThrowTypeError(
            ctx, "ctx.react spec.aux.%s must be numeric",
            request.auxNames[a].c_str());
      }
      JS_FreeValue(ctx, array);
    }
  }
  JS_FreeValue(ctx, auxObj);

  // ---- ambient + explicit shared context ---------------------------------
  request.shared = buildAmbientGeant4Seed(runtime->activeHookContext);
  JSValue contextObj = JS_GetPropertyStr(ctx, spec, "context");
  collectNumericProperties(ctx, contextObj, &request.shared);
  JS_FreeValue(ctx, contextObj);

  // ---- stoichiometric channels -------------------------------------------
  JSValue channelsVal = JS_GetPropertyStr(ctx, spec, "channels");
  const long long channelCount = numericSeriesLength(ctx, channelsVal);
  if (channelCount <= 0) {
    JS_FreeValue(ctx, channelsVal);
    releaseState();
    return JS_ThrowTypeError(
        ctx, "ctx.react spec.channels must be a non-empty array");
  }
  for (long long c = 0; c < channelCount; ++c) {
    JSValue entry =
        JS_GetPropertyUint32(ctx, channelsVal, static_cast<uint32_t>(c));
    if (!JS_IsObject(entry)) {
      JS_FreeValue(ctx, entry);
      JS_FreeValue(ctx, channelsVal);
      releaseState();
      return JS_ThrowTypeError(
          ctx, "ctx.react spec.channels entries must be objects");
    }
    trech::ml::TransitionChannel channel;
    channel.name = optionalStringProperty(ctx, entry, "name", nullptr);
    channel.delta.assign(speciesCount, 0);
    JSValue deltaObj = JS_GetPropertyStr(ctx, entry, "delta");
    if (!JS_IsObject(deltaObj)) {
      JS_FreeValue(ctx, deltaObj);
      JS_FreeValue(ctx, entry);
      JS_FreeValue(ctx, channelsVal);
      releaseState();
      return JS_ThrowTypeError(
          ctx, "ctx.react channel %s requires a delta object",
          channel.name.c_str());
    }
    std::string unexpectedDelta;
    if (!objectKeysWithin(ctx, deltaObj, speciesSet, &unexpectedDelta)) {
      JS_FreeValue(ctx, deltaObj);
      JS_FreeValue(ctx, entry);
      JS_FreeValue(ctx, channelsVal);
      releaseState();
      return JS_ThrowTypeError(
          ctx, "ctx.react channel %s delta names unknown species %s",
          channel.name.c_str(), unexpectedDelta.c_str());
    }
    for (std::size_t s = 0; s < speciesCount; ++s) {
      JSValue value =
          JS_GetPropertyStr(ctx, deltaObj, request.speciesNames[s].c_str());
      if (!JS_IsUndefined(value)) {
        double number = 0.0;
        const bool integer =
            JS_ToFloat64(ctx, &number, value) == 0 &&
            std::isfinite(number) && std::trunc(number) == number &&
            std::abs(number) <= kMaxExactInteger;
        JS_FreeValue(ctx, value);
        if (!integer) {
          JS_FreeValue(ctx, deltaObj);
          JS_FreeValue(ctx, entry);
          JS_FreeValue(ctx, channelsVal);
          releaseState();
          return JS_ThrowTypeError(
              ctx, "ctx.react channel deltas must be exact integers");
        }
        channel.delta[s] = static_cast<std::int64_t>(number);
      } else {
        JS_FreeValue(ctx, value);
      }
    }
    JS_FreeValue(ctx, deltaObj);
    JS_FreeValue(ctx, entry);
    request.channels.push_back(std::move(channel));
  }
  JS_FreeValue(ctx, channelsVal);

  // ---- caller-declared conserved linear quantities ------------------------
  JSValue conservationVal = JS_GetPropertyStr(ctx, spec, "conservation");
  const long long conservationCount = numericSeriesLength(ctx, conservationVal);
  if (conservationCount >= 0) {
    for (long long q = 0; q < conservationCount; ++q) {
      JSValue entry = JS_GetPropertyUint32(
          ctx, conservationVal, static_cast<uint32_t>(q));
      if (!JS_IsObject(entry)) {
        JS_FreeValue(ctx, entry);
        JS_FreeValue(ctx, conservationVal);
        releaseState();
        return JS_ThrowTypeError(
            ctx, "ctx.react conservation entries must be objects");
      }
      trech::ml::TransitionConservation invariant;
      invariant.name = optionalStringProperty(ctx, entry, "name", nullptr);
      invariant.coefficients.assign(speciesCount, 0);
      JSValue coeffObj = JS_GetPropertyStr(ctx, entry, "coefficients");
      if (!JS_IsObject(coeffObj)) {
        JS_FreeValue(ctx, coeffObj);
        JS_FreeValue(ctx, entry);
        JS_FreeValue(ctx, conservationVal);
        releaseState();
        return JS_ThrowTypeError(
            ctx, "ctx.react conservation %s requires coefficients",
            invariant.name.c_str());
      }
      {
        std::string unexpectedCoefficient;
        if (!objectKeysWithin(ctx, coeffObj, speciesSet,
                              &unexpectedCoefficient)) {
          JS_FreeValue(ctx, coeffObj);
          JS_FreeValue(ctx, entry);
          JS_FreeValue(ctx, conservationVal);
          releaseState();
          return JS_ThrowTypeError(
              ctx,
              "ctx.react conservation %s names unknown species %s",
              invariant.name.c_str(), unexpectedCoefficient.c_str());
        }
        for (std::size_t s = 0; s < speciesCount; ++s) {
          JSValue value = JS_GetPropertyStr(
              ctx, coeffObj, request.speciesNames[s].c_str());
          if (!JS_IsUndefined(value)) {
            double number = 0.0;
            const bool integer =
                JS_ToFloat64(ctx, &number, value) == 0 &&
                std::isfinite(number) && std::trunc(number) == number &&
                std::abs(number) <= kMaxExactInteger;
            JS_FreeValue(ctx, value);
            if (!integer) {
              JS_FreeValue(ctx, coeffObj);
              JS_FreeValue(ctx, entry);
              JS_FreeValue(ctx, conservationVal);
              releaseState();
              return JS_ThrowTypeError(
                  ctx, "ctx.react conservation coefficients must be exact integers");
            }
            invariant.coefficients[s] =
                static_cast<std::int64_t>(number);
          } else {
            JS_FreeValue(ctx, value);
          }
        }
      }
      JS_FreeValue(ctx, coeffObj);
      JS_FreeValue(ctx, entry);
      request.conservation.push_back(std::move(invariant));
    }
  }
  JS_FreeValue(ctx, conservationVal);

  // Per-element material kinds: the array form of `element_kind` binds each
  // cell's own chemistry, so a batch cell and a melt cell in the same
  // inventories evaluate different learned hazards -- required by any run in
  // which a cell CHANGES material as the reaction proceeds.
  std::vector<std::string> requestedKinds;
  if (readElementKinds(ctx, spec, request.elementCount,
                       &request.elementKindNames, &request.elementKindIndex)) {
    requestedKinds = request.elementKindNames;
  }
  OperatorSelection selection =
      selectOperatorModels(ctx, spec, runtime, request.shared, requestedKinds);
  for (OperatorSelectionGroup& group : selection.groups) {
    if (request.elementKindNames.empty()) {
      group.elementCount = request.elementCount;
      continue;
    }
    for (std::size_t e = 0; e < request.elementKindIndex.size(); ++e) {
      if (request.elementKindIndex[e] < request.elementKindNames.size() &&
          request.elementKindNames[request.elementKindIndex[e]] ==
              group.elementKind) {
        ++group.elementCount;
      }
    }
  }
  trech::ml::DiscreteTransition op;
  for (const OperatorSelectionGroup& group : selection.groups) {
    std::size_t kindIndex = trech::ml::kAnyElementKind;
    for (std::size_t i = 0; i < request.elementKindNames.size(); ++i) {
      if (request.elementKindNames[i] == group.elementKind) {
        kindIndex = i;
        break;
      }
    }
    for (const auto& [name, model] : runtime->models) {
      if (group.selected.find(name) == group.selected.end()) {
        continue;
      }
      const auto scaleIt = runtime->modelScales.find(name);
      const std::string scaleName =
          scaleIt == runtime->modelScales.end() ? "" : scaleIt->second;
      op.addStage(name, trech::ml::parseDimensionScale(scaleName), model.get(),
                  kindIndex);
    }
  }

  const std::size_t callIndex = runtime->callReactSequence++;
  request.seed =
      hashHookSeed(runtime->activeHookName, runtime->activeHookContext) ^
      (0x9e3779b97f4a7c15ull * static_cast<std::uint64_t>(callIndex + 1));
  const trech::ml::DiscreteTransitionResult run = op.react(request);

  if (run.transitionsAccepted > 0) {
    for (std::size_t s = 0; s < speciesCount; ++s) {
      for (std::size_t e = 0; e < request.elementCount; ++e) {
        JS_SetPropertyUint32(
            ctx, stateArrays[s], static_cast<uint32_t>(e),
            JS_NewInt64(ctx, run.state[e * speciesCount + s]));
      }
    }
  }
  releaseState();

  runtime->callPredictCount += run.inferenceCount;
  runtime->totalPredictCount += run.inferenceCount;
  runtime->callOutOfDomainCount += run.outOfDomainInferenceCount;
  runtime->totalOutOfDomainCount += run.outOfDomainInferenceCount;

  JSValue result = JS_NewObject(ctx);
  JS_SetPropertyStr(ctx, result, "ran", JS_NewBool(ctx, run.ran));
  JS_SetPropertyStr(ctx, result, "transitionSchemaValid",
                    JS_NewBool(ctx, run.transitionSchemaValid));
  JS_SetPropertyStr(ctx, result, "hazardSchemaValid",
                    JS_NewBool(ctx, run.hazardSchemaValid));
  JS_SetPropertyStr(ctx, result, "hazardMode",
                    JS_NewString(ctx, run.hazardMode.c_str()));
  JS_SetPropertyStr(ctx, result, "elementsEvaluated",
                    JS_NewInt64(ctx, run.elementsEvaluated));
  JS_SetPropertyStr(ctx, result, "stagesRun",
                    JS_NewInt32(ctx, run.stagesRun));
  JS_SetPropertyStr(ctx, result, "stagesExtrapolating",
                    JS_NewInt32(ctx, run.stagesExtrapolating));
  JS_SetPropertyStr(ctx, result, "stagesScaleMismatched",
                    JS_NewInt32(ctx, run.stagesScaleMismatched));
  JS_SetPropertyStr(ctx, result, "stagesStarved",
                    JS_NewInt32(ctx, run.stagesStarved));
  JS_SetPropertyStr(ctx, result, "inferenceCount",
                    JS_NewInt64(ctx, run.inferenceCount));
  JS_SetPropertyStr(ctx, result, "outOfDomainInferences",
                    JS_NewInt64(ctx, run.outOfDomainInferenceCount));
  JS_SetPropertyStr(ctx, result, "drawCount",
                    JS_NewInt64(ctx, run.drawCount));
  JS_SetPropertyStr(ctx, result, "transitionAttempts",
                    JS_NewInt64(ctx, run.transitionAttempts));
  JS_SetPropertyStr(ctx, result, "transitionsAccepted",
                    JS_NewInt64(ctx, run.transitionsAccepted));
  JS_SetPropertyStr(ctx, result, "rejectedAvailability",
                    JS_NewInt64(ctx, run.rejectedAvailability));
  JS_SetPropertyStr(ctx, result, "hazardsClamped",
                    JS_NewInt64(ctx, run.hazardsClamped));
  JS_SetPropertyStr(ctx, result, "weightsClamped",
                    JS_NewInt64(ctx, run.weightsClamped));
  JS_SetPropertyStr(ctx, result, "hazardRenormalizedElements",
                    JS_NewInt64(ctx, run.hazardRenormalizedElements));
  JS_SetPropertyStr(ctx, result, "rngCallIndex",
                    JS_NewInt64(ctx, callIndex));
  JS_SetPropertyStr(ctx, result, "selection",
                    operatorSelectionToJs(ctx, selection));
  std::vector<std::string> sharedKeys;
  for (const auto& [key, value] : request.shared) {
    (void)value;
    sharedKeys.push_back(key);
  }
  std::sort(sharedKeys.begin(), sharedKeys.end());
  JS_SetPropertyStr(ctx, result, "sharedKeys",
                    newStringArray(ctx, sharedKeys));
  JS_SetPropertyStr(ctx, result, "auxKeys",
                    newStringArray(ctx, request.auxNames));

  JSValue channelTrace = JS_NewArray(ctx);
  for (std::size_t c = 0; c < run.channelTrace.size(); ++c) {
    const auto& channel = run.channelTrace[c];
    JSValue item = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, item, "name",
                      JS_NewString(ctx, channel.name.c_str()));
    JS_SetPropertyStr(ctx, item, "valid", JS_NewBool(ctx, channel.valid));
    JS_SetPropertyStr(ctx, item, "nonZero",
                      JS_NewBool(ctx, channel.nonZero));
    JS_SetPropertyStr(ctx, item, "violatedConservation",
                      newStringArray(ctx, channel.violatedConservation));
    JS_SetPropertyStr(ctx, item, "attempted",
                      JS_NewInt64(ctx, channel.attempted));
    JS_SetPropertyStr(ctx, item, "accepted",
                      JS_NewInt64(ctx, channel.accepted));
    JS_SetPropertyStr(ctx, item, "rejectedAvailability",
                      JS_NewInt64(ctx, channel.rejectedAvailability));
    JS_SetPropertyUint32(ctx, channelTrace, static_cast<uint32_t>(c), item);
  }
  JS_SetPropertyStr(ctx, result, "channels", channelTrace);

  JSValue trace = JS_NewArray(ctx);
  for (std::size_t i = 0; i < run.stages.size(); ++i) {
    const auto& stage = run.stages[i];
    JSValue item = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, item, "model",
                      JS_NewString(ctx, stage.model.c_str()));
    JS_SetPropertyStr(
        ctx, item, "scale",
        JS_NewString(ctx, trech::ml::dimensionScaleName(stage.scale)));
    JS_SetPropertyStr(ctx, item, "ran", JS_NewBool(ctx, stage.ran));
    JS_SetPropertyStr(ctx, item, "missingInputs",
                      newStringArray(ctx, stage.missingInputs));
    JS_SetPropertyStr(ctx, item, "intermediateOutputs",
                      newStringArray(ctx, stage.intermediateOutputs));
    JS_SetPropertyStr(ctx, item, "hazardOutputs",
                      newStringArray(ctx, stage.hazardOutputs));
    JS_SetPropertyStr(ctx, item, "unappliedHazardOutputs",
                      newStringArray(ctx, stage.unappliedHazardOutputs));
    JS_SetPropertyStr(ctx, item, "elementKind",
                      JS_NewString(ctx, stage.elementKind.c_str()));
    JS_SetPropertyStr(
        ctx, item, "elementsMatched",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.elementsMatched)));
    JS_SetPropertyStr(ctx, item, "domainMeasured",
                      JS_NewBool(ctx, stage.domainMeasured));
    JS_SetPropertyStr(ctx, item, "elementsOutOfDomain",
                      JS_NewInt64(ctx, stage.elementsOutOfDomain));
    JS_SetPropertyStr(ctx, item, "elementsStarved",
                      JS_NewInt64(ctx, stage.elementsStarved));
    JS_SetPropertyStr(ctx, item, "elementsJointStarved",
                      JS_NewInt64(ctx, stage.elementsJointStarved));
    JS_SetPropertyStr(ctx, item, "maxJointDistance",
                      stage.jointMeasured
                          ? JS_NewFloat64(ctx, stage.maxJointDistance)
                          : JS_NULL);
    JS_SetPropertyStr(ctx, item, "maxExtrapolation",
                      JS_NewFloat64(ctx, stage.maxExtrapolation));
    JS_SetPropertyStr(ctx, item, "maxStandardizedDeviation",
                      JS_NewFloat64(ctx, stage.maxStandardizedDeviation));
    JS_SetPropertyStr(ctx, item, "outOfDomainInputs",
                      newStringArray(ctx, stage.outOfDomainInputs));
    JS_SetPropertyStr(ctx, item, "starvedInputs",
                      newStringArray(ctx, stage.starvedInputs));
    JS_SetPropertyStr(ctx, item, "scaleMismatch",
                      JS_NewBool(ctx, stage.scaleMismatch));
    JS_SetPropertyStr(ctx, item, "trainedScale",
                      JS_NewString(ctx, stage.trainedScale.c_str()));
    JS_SetPropertyStr(ctx, item, "holdoutR2",
                      stage.hasHoldout
                          ? JS_NewFloat64(ctx, stage.holdoutR2)
                          : JS_NULL);
    JS_SetPropertyStr(ctx, item, "holdoutSamples",
                      stage.hasHoldout
                          ? JS_NewInt32(ctx, stage.holdoutSamples)
                          : JS_NULL);
    JS_SetPropertyStr(ctx, item, "outputAccuracy",
                      newOutputAccuracyObject(ctx, stage.outputAccuracy));
    JS_SetPropertyUint32(ctx, trace, static_cast<uint32_t>(i), item);
  }
  JS_SetPropertyStr(ctx, result, "trace", trace);
  return result;
}

// --- ctx.interact: learned PAIR / NEIGHBOUR interaction --------------------
//
// ctx.evolve answers "how does THIS element change?"; ctx.interact answers
// "what does one element do TO ANOTHER?" -- the shape of every remaining
// hand-written solver loop in the tree (the MD force loop, the bonded foam
// network, the PBF neighbourhood sums, parcel cohesion/collision terms).
//
//   ctx.interact({
//     dt: 2e-15,
//     fields: [{ name: "vx", symmetry: "antisymmetric", min, max },
//              { name: "rho", symmetry: "symmetric" }],
//     state:  { vx: Float64Array, rho: Float64Array },   // mutated in place
//     aux:    { mass: Float64Array },                    // read-only
//     positions: { x: Float64Array, y: ..., z: ... },
//     cutoff: 7.0,                  // dynamic neighbours (<=0 disables)
//     maxPairs: 400000,             // bounded search, truncation disclosed
//     links: { a: [...], b: [...] },        // persistent bonds
//     pair_fields: [{ name: "rest_length", min: 0 }],
//     pair_state: { rest_length: Float64Array },         // mutated in place
//     context: { ...whatever a ctx.cascade already inferred },
//     operator_role: "pair_interaction", element_kind: "foam_bond"
//   })
//
// A stage output `d_<field>_dt` is a rate contribution to both members
// (integrated once over dt), `add_<field>` a direct increment (a neighbourhood
// sum), `d_<pair field>_dt` / `set_<pair field>` drive the pair's own state,
// anything else is an intermediate a higher-scale stage consumes.  The member
// facts are read as `a_<name>`/`b_<name>` and the geometry through the reserved
// `r`, `dx/dy/dz`, `ux/uy/uz` and `dt`.  Whether a field is equal-and-opposite
// or shared is the SCENARIO's declared invariant; the engine enforces it.
//
// Same contract as the other operators: strict mode returns null and mutates
// nothing, selection is contextual unless `models` overrides it, and every
// model evaluation counts -- pairs x stages inferences, never one per call.
static JSValue jsHookInteract(JSContext* ctx, JSValueConst /*this_val*/,
                              int argc, JSValueConst* argv) {
  auto* runtime = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  if (!runtime) {
    return JS_EXCEPTION;
  }
  if (normalizeDeterminismMode(runtime->activeHookContext.determinismMode) !=
      "predictive") {
    return JS_NULL;  // strict: no inference, no mutation
  }
  if (argc < 1 || !JS_IsObject(argv[0])) {
    return JS_ThrowTypeError(ctx, "ctx.interact(spec) requires a spec object");
  }
  JSValueConst spec = argv[0];

  trech::ml::PairInteractionRequest request;

  JSValue dtVal = JS_GetPropertyStr(ctx, spec, "dt");
  if (JS_ToFloat64(ctx, &request.dt, dtVal) != 0) {
    request.dt = 0.0;
  }
  JS_FreeValue(ctx, dtVal);

  auto numberProperty = [ctx](JSValueConst object, const char* snake,
                              const char* camel, double fallback) -> double {
    JSValue value = JS_GetPropertyStr(ctx, object, snake);
    if (JS_IsUndefined(value) && camel) {
      JS_FreeValue(ctx, value);
      value = JS_GetPropertyStr(ctx, object, camel);
    }
    double out = fallback;
    if (JS_ToFloat64(ctx, &out, value) != 0) {
      out = fallback;
    }
    JS_FreeValue(ctx, value);
    return out;
  };
  request.cutoff = numberProperty(spec, "cutoff", nullptr, 0.0);
  const double maxPairs = numberProperty(spec, "max_pairs", "maxPairs", 0.0);
  request.maxNeighborPairs =
      maxPairs > 0.0 ? static_cast<std::size_t>(maxPairs) : 0;

  // ---- declared element fields: "name" or { name, symmetry, min, max } ----
  JSValue fieldsVal = JS_GetPropertyStr(ctx, spec, "fields");
  const long long fieldCountRaw = numericSeriesLength(ctx, fieldsVal);
  if (fieldCountRaw <= 0) {
    JS_FreeValue(ctx, fieldsVal);
    return JS_ThrowTypeError(
        ctx, "ctx.interact spec.fields must be a non-empty array");
  }
  for (long long i = 0; i < fieldCountRaw; ++i) {
    JSValue entry =
        JS_GetPropertyUint32(ctx, fieldsVal, static_cast<uint32_t>(i));
    trech::ml::PairElementField field;
    if (JS_IsString(entry)) {
      const char* raw = JS_ToCString(ctx, entry);
      if (raw) {
        field.name = raw;
        JS_FreeCString(ctx, raw);
      }
    } else if (JS_IsObject(entry)) {
      JSValue nameVal = JS_GetPropertyStr(ctx, entry, "name");
      const char* raw = JS_ToCString(ctx, nameVal);
      if (raw) {
        field.name = raw;
        JS_FreeCString(ctx, raw);
      }
      JS_FreeValue(ctx, nameVal);
      JSValue symVal = JS_GetPropertyStr(ctx, entry, "symmetry");
      if (JS_IsString(symVal)) {
        const char* symRaw = JS_ToCString(ctx, symVal);
        if (symRaw) {
          const std::string symmetry = symRaw;
          JS_FreeCString(ctx, symRaw);
          if (symmetry == "symmetric" || symmetry == "shared") {
            field.symmetry = trech::ml::PairSymmetry::kSymmetric;
          } else if (symmetry != "antisymmetric" && symmetry != "opposite") {
            JS_FreeValue(ctx, symVal);
            JS_FreeValue(ctx, entry);
            JS_FreeValue(ctx, fieldsVal);
            return JS_ThrowTypeError(
                ctx, "ctx.interact field symmetry must be \"antisymmetric\" or "
                     "\"symmetric\" (got \"%s\")",
                symmetry.c_str());
          }
        }
      }
      JS_FreeValue(ctx, symVal);
      double bound = 0.0;
      JSValue minVal = JS_GetPropertyStr(ctx, entry, "min");
      if (!JS_IsUndefined(minVal) && JS_ToFloat64(ctx, &bound, minVal) == 0) {
        field.minValue = bound;
      }
      JS_FreeValue(ctx, minVal);
      JSValue maxVal = JS_GetPropertyStr(ctx, entry, "max");
      if (!JS_IsUndefined(maxVal) && JS_ToFloat64(ctx, &bound, maxVal) == 0) {
        field.maxValue = bound;
      }
      JS_FreeValue(ctx, maxVal);
    }
    JS_FreeValue(ctx, entry);
    if (field.name.empty()) {
      JS_FreeValue(ctx, fieldsVal);
      return JS_ThrowTypeError(ctx,
                               "ctx.interact spec.fields entries need a name");
    }
    request.fields.push_back(std::move(field));
  }
  JS_FreeValue(ctx, fieldsVal);
  const std::size_t fieldCount = request.fields.size();

  // ---- per-element state arrays (mutated in place) ------------------------
  JSValue stateObj = JS_GetPropertyStr(ctx, spec, "state");
  if (!JS_IsObject(stateObj)) {
    JS_FreeValue(ctx, stateObj);
    return JS_ThrowTypeError(
        ctx, "ctx.interact spec.state must be an object of arrays");
  }
  std::vector<JSValue> stateArrays(fieldCount, JS_UNDEFINED);
  std::vector<JSValue> pairStateArrays;
  JSValue pairStateObj = JS_UNDEFINED;
  auto releaseArrays = [&]() {
    for (JSValue& v : stateArrays) {
      JS_FreeValue(ctx, v);
    }
    for (JSValue& v : pairStateArrays) {
      JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, pairStateObj);
    JS_FreeValue(ctx, stateObj);
  };
  long long elementCount = -1;
  for (std::size_t f = 0; f < fieldCount; ++f) {
    stateArrays[f] =
        JS_GetPropertyStr(ctx, stateObj, request.fields[f].name.c_str());
    const long long len = numericSeriesLength(ctx, stateArrays[f]);
    if (len < 0) {
      const std::string name = request.fields[f].name;
      releaseArrays();
      return JS_ThrowTypeError(ctx, "ctx.interact spec.state.%s must be an array",
                               name.c_str());
    }
    if (elementCount < 0) {
      elementCount = len;
    } else if (len != elementCount) {
      const std::string name = request.fields[f].name;
      releaseArrays();
      return JS_ThrowTypeError(
          ctx, "ctx.interact spec.state.%s length %lld != %lld (every field must "
               "cover the same elements)",
          name.c_str(), len, elementCount);
    }
  }
  if (elementCount <= 0) {
    releaseArrays();
    return JS_NULL;  // no elements: nothing to interact, nothing to report
  }
  request.elementCount = static_cast<std::size_t>(elementCount);
  request.state.assign(request.elementCount * fieldCount, 0.0);
  for (std::size_t f = 0; f < fieldCount; ++f) {
    if (!readNumericSeries(ctx, stateArrays[f], request.elementCount, f,
                           fieldCount, &request.state)) {
      const std::string name = request.fields[f].name;
      releaseArrays();
      return JS_ThrowTypeError(ctx, "ctx.interact spec.state.%s is not numeric",
                               name.c_str());
    }
  }

  // ---- read-only per-element aux facts ------------------------------------
  JSValue auxObj = JS_GetPropertyStr(ctx, spec, "aux");
  if (JS_IsObject(auxObj)) {
    JSPropertyEnum* props = nullptr;
    uint32_t propCount = 0;
    if (JS_GetOwnPropertyNames(ctx, &props, &propCount, auxObj,
                               JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) == 0) {
      for (uint32_t i = 0; i < propCount; ++i) {
        JSValue key = JS_AtomToString(ctx, props[i].atom);
        const char* keyRaw = JS_ToCString(ctx, key);
        JSValue val = JS_GetProperty(ctx, auxObj, props[i].atom);
        if (keyRaw && numericSeriesLength(ctx, val) >=
                          static_cast<long long>(request.elementCount)) {
          request.auxNames.push_back(keyRaw);
        }
        JS_FreeValue(ctx, val);
        if (keyRaw) {
          JS_FreeCString(ctx, keyRaw);
        }
        JS_FreeValue(ctx, key);
        JS_FreeAtom(ctx, props[i].atom);
      }
      js_free(ctx, props);
    }
    std::sort(request.auxNames.begin(), request.auxNames.end());
    const std::size_t auxCount = request.auxNames.size();
    request.aux.assign(request.elementCount * auxCount, 0.0);
    for (std::size_t a = 0; a < auxCount; ++a) {
      JSValue arr = JS_GetPropertyStr(ctx, auxObj, request.auxNames[a].c_str());
      readNumericSeries(ctx, arr, request.elementCount, a, auxCount,
                        &request.aux);
      JS_FreeValue(ctx, arr);
    }
  }
  JS_FreeValue(ctx, auxObj);

  // ---- positions (x/y/z arrays) -------------------------------------------
  JSValue positionsObj = JS_GetPropertyStr(ctx, spec, "positions");
  if (JS_IsObject(positionsObj)) {
    request.positions.assign(3 * request.elementCount, 0.0);
    const char* axes[3] = {"x", "y", "z"};
    for (std::size_t axis = 0; axis < 3; ++axis) {
      JSValue arr = JS_GetPropertyStr(ctx, positionsObj, axes[axis]);
      if (numericSeriesLength(ctx, arr) >=
          static_cast<long long>(request.elementCount)) {
        readNumericSeries(ctx, arr, request.elementCount, axis, 3,
                          &request.positions);
      }
      JS_FreeValue(ctx, arr);
    }
  }
  JS_FreeValue(ctx, positionsObj);

  // ---- persistent pair topology (bonds) + its own state -------------------
  JSValue linksObj = JS_GetPropertyStr(ctx, spec, "links");
  if (JS_IsObject(linksObj)) {
    JSValue aArr = JS_GetPropertyStr(ctx, linksObj, "a");
    JSValue bArr = JS_GetPropertyStr(ctx, linksObj, "b");
    const long long aLen = numericSeriesLength(ctx, aArr);
    const long long bLen = numericSeriesLength(ctx, bArr);
    const long long linkCount = std::min(aLen, bLen);
    for (long long i = 0; i < linkCount; ++i) {
      JSValue aVal = JS_GetPropertyUint32(ctx, aArr, static_cast<uint32_t>(i));
      JSValue bVal = JS_GetPropertyUint32(ctx, bArr, static_cast<uint32_t>(i));
      double a = -1.0;
      double b = -1.0;
      const bool ok =
          JS_ToFloat64(ctx, &a, aVal) == 0 && JS_ToFloat64(ctx, &b, bVal) == 0;
      JS_FreeValue(ctx, aVal);
      JS_FreeValue(ctx, bVal);
      trech::ml::PairLink link;
      // A negative/non-integer index becomes an out-of-range link, which the
      // operator reports as invalid rather than silently reinterpreting.
      link.a = ok && a >= 0.0 ? static_cast<std::size_t>(a)
                              : static_cast<std::size_t>(-1);
      link.b = ok && b >= 0.0 ? static_cast<std::size_t>(b)
                              : static_cast<std::size_t>(-1);
      request.links.push_back(link);
    }
    JS_FreeValue(ctx, aArr);
    JS_FreeValue(ctx, bArr);
  }
  JS_FreeValue(ctx, linksObj);

  JSValue pairFieldsVal = JS_GetPropertyStr(ctx, spec, "pair_fields");
  if (JS_IsUndefined(pairFieldsVal)) {
    JS_FreeValue(ctx, pairFieldsVal);
    pairFieldsVal = JS_GetPropertyStr(ctx, spec, "pairFields");
  }
  const long long pairFieldCountRaw = numericSeriesLength(ctx, pairFieldsVal);
  for (long long i = 0; i < pairFieldCountRaw; ++i) {
    JSValue entry =
        JS_GetPropertyUint32(ctx, pairFieldsVal, static_cast<uint32_t>(i));
    trech::ml::PairStateField field;
    if (JS_IsString(entry)) {
      const char* raw = JS_ToCString(ctx, entry);
      if (raw) {
        field.name = raw;
        JS_FreeCString(ctx, raw);
      }
    } else if (JS_IsObject(entry)) {
      JSValue nameVal = JS_GetPropertyStr(ctx, entry, "name");
      const char* raw = JS_ToCString(ctx, nameVal);
      if (raw) {
        field.name = raw;
        JS_FreeCString(ctx, raw);
      }
      JS_FreeValue(ctx, nameVal);
      double bound = 0.0;
      JSValue minVal = JS_GetPropertyStr(ctx, entry, "min");
      if (!JS_IsUndefined(minVal) && JS_ToFloat64(ctx, &bound, minVal) == 0) {
        field.minValue = bound;
      }
      JS_FreeValue(ctx, minVal);
      JSValue maxVal = JS_GetPropertyStr(ctx, entry, "max");
      if (!JS_IsUndefined(maxVal) && JS_ToFloat64(ctx, &bound, maxVal) == 0) {
        field.maxValue = bound;
      }
      JS_FreeValue(ctx, maxVal);
    }
    JS_FreeValue(ctx, entry);
    if (field.name.empty()) {
      JS_FreeValue(ctx, pairFieldsVal);
      releaseArrays();
      return JS_ThrowTypeError(
          ctx, "ctx.interact spec.pair_fields entries need a name");
    }
    request.pairFields.push_back(std::move(field));
  }
  JS_FreeValue(ctx, pairFieldsVal);

  const std::size_t pairFieldCount = request.pairFields.size();
  if (pairFieldCount > 0) {
    pairStateObj = JS_GetPropertyStr(ctx, spec, "pair_state");
    if (JS_IsUndefined(pairStateObj)) {
      JS_FreeValue(ctx, pairStateObj);
      pairStateObj = JS_GetPropertyStr(ctx, spec, "pairState");
    }
    if (!JS_IsObject(pairStateObj)) {
      releaseArrays();
      return JS_ThrowTypeError(
          ctx, "ctx.interact spec.pair_state must be an object of arrays when "
               "pair_fields are declared");
    }
    pairStateArrays.assign(pairFieldCount, JS_UNDEFINED);
    const std::size_t linkCount = request.links.size();
    request.pairState.assign(linkCount * pairFieldCount, 0.0);
    for (std::size_t p = 0; p < pairFieldCount; ++p) {
      pairStateArrays[p] = JS_GetPropertyStr(
          ctx, pairStateObj, request.pairFields[p].name.c_str());
      const long long len = numericSeriesLength(ctx, pairStateArrays[p]);
      if (len < static_cast<long long>(linkCount)) {
        const std::string name = request.pairFields[p].name;
        releaseArrays();
        return JS_ThrowTypeError(
            ctx, "ctx.interact spec.pair_state.%s must cover every declared link",
            name.c_str());
      }
      readNumericSeries(ctx, pairStateArrays[p], linkCount, p, pairFieldCount,
                        &request.pairState);
    }
  }

  // ---- run-constant shared context: ambient Geant4 base, then overrides ----
  request.shared = buildAmbientGeant4Seed(runtime->activeHookContext);
  JSValue contextObj = JS_GetPropertyStr(ctx, spec, "context");
  collectNumericProperties(ctx, contextObj, &request.shared);
  JS_FreeValue(ctx, contextObj);

  // ---- per-PAIR material kinds --------------------------------------------
  // With per-element kinds declared, the engine composes the canonical
  // combinations (`sand|sand`, `melt|sand`, `melt|melt`) and selects an operator
  // for each: what happens between two grains of the same solid, a grain and its
  // melt, and two melt cells are three different interactions, and a run that
  // creates a material moves pairs between them as its cells transform.
  std::vector<std::string> requestedPairKinds;
  if (readElementKinds(ctx, spec, request.elementCount,
                       &request.elementKindNames, &request.elementKindIndex)) {
    for (std::size_t i = 0; i < request.elementKindNames.size(); ++i) {
      for (std::size_t j = i; j < request.elementKindNames.size(); ++j) {
        request.pairKindNames.push_back(trech::ml::PairInteraction::pairKindName(
            request.elementKindNames[i], request.elementKindNames[j]));
      }
    }
    std::sort(request.pairKindNames.begin(), request.pairKindNames.end());
    request.pairKindNames.erase(
        std::unique(request.pairKindNames.begin(), request.pairKindNames.end()),
        request.pairKindNames.end());
    requestedPairKinds = request.pairKindNames;
  }

  // ---- stage selection: explicit override or contextual role match --------
  OperatorSelection selection = selectOperatorModels(
      ctx, spec, runtime, request.shared, requestedPairKinds);
  trech::ml::PairInteraction op;
  for (const OperatorSelectionGroup& group : selection.groups) {
    std::size_t pairKindIndex = trech::ml::kAnyElementKind;
    for (std::size_t i = 0; i < request.pairKindNames.size(); ++i) {
      if (request.pairKindNames[i] == group.elementKind) {
        pairKindIndex = i;
        break;
      }
    }
    for (const auto& [name, model] : runtime->models) {
      if (group.selected.find(name) == group.selected.end()) {
        continue;
      }
      const auto scaleIt = runtime->modelScales.find(name);
      const std::string scaleName =
          scaleIt == runtime->modelScales.end() ? "" : scaleIt->second;
      op.addStage(name, trech::ml::parseDimensionScale(scaleName), model.get(),
                  pairKindIndex);
    }
  }

  const trech::ml::PairInteractionResult run = op.interact(request);

  // ---- write the result back into the caller's own arrays -----------------
  if (run.ran) {
    for (std::size_t f = 0; f < fieldCount; ++f) {
      for (std::size_t e = 0; e < request.elementCount; ++e) {
        JS_SetPropertyUint32(ctx, stateArrays[f], static_cast<uint32_t>(e),
                             JS_NewFloat64(ctx, run.state[e * fieldCount + f]));
      }
    }
    for (std::size_t p = 0; p < pairStateArrays.size(); ++p) {
      for (std::size_t l = 0; l < request.links.size(); ++l) {
        JS_SetPropertyUint32(
            ctx, pairStateArrays[p], static_cast<uint32_t>(l),
            JS_NewFloat64(ctx, run.pairState[l * pairFieldCount + p]));
      }
    }
  }
  releaseArrays();

  runtime->callPredictCount += run.inferenceCount;
  runtime->totalPredictCount += run.inferenceCount;
  runtime->callOutOfDomainCount += run.outOfDomainInferenceCount;
  runtime->totalOutOfDomainCount += run.outOfDomainInferenceCount;

  JSValue result = JS_NewObject(ctx);
  JS_SetPropertyStr(ctx, result, "ran", JS_NewBool(ctx, run.ran));
  JS_SetPropertyStr(ctx, result, "pairCount",
                    JS_NewInt64(ctx, static_cast<std::int64_t>(run.pairCount)));
  JS_SetPropertyStr(
      ctx, result, "linkPairs",
      JS_NewInt64(ctx, static_cast<std::int64_t>(run.linkPairCount)));
  JS_SetPropertyStr(
      ctx, result, "neighborPairs",
      JS_NewInt64(ctx, static_cast<std::int64_t>(run.neighborPairCount)));
  JS_SetPropertyStr(
      ctx, result, "neighborPairsSkipped",
      JS_NewInt64(ctx, static_cast<std::int64_t>(run.neighborPairsSkipped)));
  JS_SetPropertyStr(ctx, result, "neighborPairsTruncated",
                    JS_NewBool(ctx, run.neighborPairsTruncated));
  JS_SetPropertyStr(
      ctx, result, "invalidLinks",
      JS_NewInt64(ctx, static_cast<std::int64_t>(run.invalidLinks)));
  JS_SetPropertyStr(
      ctx, result, "duplicateLinks",
      JS_NewInt64(ctx, static_cast<std::int64_t>(run.duplicateLinks)));
  JS_SetPropertyStr(ctx, result, "stagesRun", JS_NewInt32(ctx, run.stagesRun));
  JS_SetPropertyStr(ctx, result, "stagesExtrapolating",
                    JS_NewInt32(ctx, run.stagesExtrapolating));
  JS_SetPropertyStr(ctx, result, "stagesScaleMismatched",
                    JS_NewInt32(ctx, run.stagesScaleMismatched));
  JS_SetPropertyStr(ctx, result, "stagesStarved",
                    JS_NewInt32(ctx, run.stagesStarved));
  JS_SetPropertyStr(
      ctx, result, "inferenceCount",
      JS_NewInt64(ctx, static_cast<std::int64_t>(run.inferenceCount)));
  JS_SetPropertyStr(ctx, result, "outOfDomainInferences",
                    JS_NewInt64(ctx, static_cast<std::int64_t>(
                                         run.outOfDomainInferenceCount)));
  JS_SetPropertyStr(ctx, result, "selection",
                    operatorSelectionToJs(ctx, selection));
  std::vector<std::string> sharedKeys;
  sharedKeys.reserve(request.shared.size());
  for (const auto& [key, value] : request.shared) {
    (void)value;
    sharedKeys.push_back(key);
  }
  std::sort(sharedKeys.begin(), sharedKeys.end());
  JS_SetPropertyStr(ctx, result, "sharedKeys", newStringArray(ctx, sharedKeys));
  JS_SetPropertyStr(ctx, result, "auxKeys",
                    newStringArray(ctx, request.auxNames));

  JSValue trace = JS_NewArray(ctx);
  for (std::size_t i = 0; i < run.stages.size(); ++i) {
    const auto& stage = run.stages[i];
    JSValue item = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, item, "model",
                      JS_NewString(ctx, stage.model.c_str()));
    JS_SetPropertyStr(
        ctx, item, "scale",
        JS_NewString(ctx, trech::ml::dimensionScaleName(stage.scale)));
    JS_SetPropertyStr(ctx, item, "ran", JS_NewBool(ctx, stage.ran));
    JS_SetPropertyStr(ctx, item, "missingInputs",
                      newStringArray(ctx, stage.missingInputs));
    JS_SetPropertyStr(ctx, item, "ratedElementFields",
                      newStringArray(ctx, stage.ratedElementFields));
    JS_SetPropertyStr(ctx, item, "incrementedElementFields",
                      newStringArray(ctx, stage.incrementedElementFields));
    JS_SetPropertyStr(ctx, item, "ratedPairFields",
                      newStringArray(ctx, stage.ratedPairFields));
    JS_SetPropertyStr(ctx, item, "assignedPairFields",
                      newStringArray(ctx, stage.assignedPairFields));
    JS_SetPropertyStr(ctx, item, "intermediateOutputs",
                      newStringArray(ctx, stage.intermediateOutputs));
    JS_SetPropertyStr(ctx, item, "unappliedFieldOutputs",
                      newStringArray(ctx, stage.unappliedFieldOutputs));
    // Which material combination this stage served, and how many pairs of it
    // were actually evaluated.
    JS_SetPropertyStr(ctx, item, "pairKind",
                      JS_NewString(ctx, stage.pairKind.c_str()));
    JS_SetPropertyStr(
        ctx, item, "pairsMatched",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.pairsMatched)));
    JS_SetPropertyStr(ctx, item, "domainMeasured",
                      JS_NewBool(ctx, stage.domainMeasured));
    JS_SetPropertyStr(
        ctx, item, "pairsOutOfDomain",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.pairsOutOfDomain)));
    JS_SetPropertyStr(
        ctx, item, "pairsStarved",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.pairsStarved)));
    JS_SetPropertyStr(
        ctx, item, "pairsJointStarved",
        JS_NewInt64(ctx, static_cast<std::int64_t>(stage.pairsJointStarved)));
    JS_SetPropertyStr(ctx, item, "maxJointDistance",
                      stage.jointMeasured
                          ? JS_NewFloat64(ctx, stage.maxJointDistance)
                          : JS_NULL);
    JS_SetPropertyStr(ctx, item, "maxExtrapolation",
                      JS_NewFloat64(ctx, stage.maxExtrapolation));
    JS_SetPropertyStr(ctx, item, "maxStandardizedDeviation",
                      JS_NewFloat64(ctx, stage.maxStandardizedDeviation));
    JS_SetPropertyStr(ctx, item, "outOfDomainInputs",
                      newStringArray(ctx, stage.outOfDomainInputs));
    JS_SetPropertyStr(ctx, item, "starvedInputs",
                      newStringArray(ctx, stage.starvedInputs));
    JS_SetPropertyStr(ctx, item, "scaleMismatch",
                      JS_NewBool(ctx, stage.scaleMismatch));
    JS_SetPropertyStr(ctx, item, "trainedScale",
                      JS_NewString(ctx, stage.trainedScale.c_str()));
    JS_SetPropertyStr(ctx, item, "holdoutR2",
                      stage.hasHoldout ? JS_NewFloat64(ctx, stage.holdoutR2)
                                       : JS_NULL);
    JS_SetPropertyStr(ctx, item, "holdoutSamples",
                      stage.hasHoldout ? JS_NewInt32(ctx, stage.holdoutSamples)
                                       : JS_NULL);
    JS_SetPropertyStr(ctx, item, "outputAccuracy",
                      newOutputAccuracyObject(ctx, stage.outputAccuracy));
    JS_SetPropertyUint32(ctx, trace, static_cast<uint32_t>(i), item);
  }
  JS_SetPropertyStr(ctx, result, "trace", trace);
  return result;
}

static JSValue jsHookRngUniform(JSContext* ctx, JSValueConst thisVal, int /*argc*/,
                                JSValueConst* /*argv*/) {
  std::int64_t seed = 0;
  JSValue seedValue = JS_GetPropertyStr(ctx, thisVal, "__seed");
  JS_ToInt64(ctx, &seed, seedValue);
  JS_FreeValue(ctx, seedValue);
  auto next = xorshift64(static_cast<std::uint64_t>(seed));
  JSValue self = JS_DupValue(ctx, thisVal);
  JS_SetPropertyStr(ctx, self, "__seed",
                    JS_NewInt64(ctx, static_cast<std::int64_t>(next)));
  JS_FreeValue(ctx, self);
  const double uniform = static_cast<double>(next & 0x1fffffffffffffull) /
                         static_cast<double>(0x20000000000000ull);
  return JS_NewFloat64(ctx, uniform);
}

static JSValue jsHookRngInt(JSContext* ctx, JSValueConst thisVal, int argc,
                            JSValueConst* argv) {
  if (argc < 2) {
    return JS_ThrowTypeError(ctx, "rng.int(min, max) requires two integer arguments");
  }
  std::int32_t minValue = 0;
  std::int32_t maxValue = 0;
  if (JS_ToInt32(ctx, &minValue, argv[0]) < 0 || JS_ToInt32(ctx, &maxValue, argv[1]) < 0) {
    return JS_ThrowTypeError(ctx, "rng.int(min, max) expects integers");
  }
  if (maxValue < minValue) {
    return JS_ThrowRangeError(ctx, "rng.int(min, max) expects max >= min");
  }
  JSValue uniform = jsHookRngUniform(ctx, thisVal, 0, nullptr);
  if (JS_IsException(uniform)) {
    return uniform;
  }
  double unit = 0.0;
  JS_ToFloat64(ctx, &unit, uniform);
  JS_FreeValue(ctx, uniform);
  const auto span = static_cast<double>(maxValue - minValue + 1);
  const auto sampled = minValue + static_cast<std::int32_t>(unit * span);
  return JS_NewInt32(ctx, sampled > maxValue ? maxValue : sampled);
}

static constexpr const char* kTrechFlowBootstrap = R"JS(
(function(global) {
  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function cloneValue(value) {
    if (Array.isArray(value)) {
      return value.map(cloneValue);
    }
    if (isPlainObject(value)) {
      var out = {};
      var keys = Object.keys(value);
      for (var i = 0; i < keys.length; ++i) {
        var key = keys[i];
        out[key] = cloneValue(value[key]);
      }
      return out;
    }
    return value;
  }

  function parsePath(path) {
    if (Array.isArray(path)) {
      if (path.length === 0) {
        throw new TypeError("TRECH_FLOW path cannot be empty");
      }
      return path.slice();
    }
    if (typeof path !== "string" || path.length === 0) {
      throw new TypeError("TRECH_FLOW path must be a non-empty string or array");
    }
    var tokens = path.split(".").filter(function(token) {
      return token.length > 0;
    });
    if (tokens.length === 0) {
      throw new TypeError("TRECH_FLOW path cannot be empty");
    }
    return tokens;
  }

  function ensureObjectNode(parent, key) {
    var node = parent[key];
    if (node === undefined || node === null) {
      node = {};
      parent[key] = node;
      return node;
    }
    if (!isPlainObject(node)) {
      throw new TypeError("TRECH_FLOW path segment '" + key + "' is not an object");
    }
    return node;
  }

  function setPath(target, path, value) {
    var tokens = parsePath(path);
    var node = target;
    for (var i = 0; i < tokens.length - 1; ++i) {
      node = ensureObjectNode(node, tokens[i]);
    }
    node[tokens[tokens.length - 1]] = value;
  }

  function getPath(target, path) {
    var tokens = parsePath(path);
    var node = target;
    for (var i = 0; i < tokens.length; ++i) {
      if (node === undefined || node === null) {
        return undefined;
      }
      node = node[tokens[i]];
    }
    return node;
  }

  function pushPath(target, path, value) {
    var current = getPath(target, path);
    if (current === undefined) {
      setPath(target, path, [value]);
      return;
    }
    if (!Array.isArray(current)) {
      throw new TypeError("TRECH_FLOW push target is not an array");
    }
    current.push(value);
  }

  function deepMerge(target, patch) {
    var keys = Object.keys(patch);
    for (var i = 0; i < keys.length; ++i) {
      var key = keys[i];
      var value = patch[key];
      if (isPlainObject(value)) {
        if (!isPlainObject(target[key])) {
          target[key] = {};
        }
        deepMerge(target[key], value);
      } else {
        target[key] = cloneValue(value);
      }
    }
    return target;
  }

  function deepDefaults(target, patch) {
    var keys = Object.keys(patch);
    for (var i = 0; i < keys.length; ++i) {
      var key = keys[i];
      var value = patch[key];
      if (target[key] === undefined) {
        target[key] = cloneValue(value);
        continue;
      }
      if (isPlainObject(target[key]) && isPlainObject(value)) {
        deepDefaults(target[key], value);
      }
    }
    return target;
  }

  function ensureArrayPath(target, path) {
    var current = getPath(target, path);
    if (current === undefined || current === null) {
      setPath(target, path, []);
      return getPath(target, path);
    }
    if (Array.isArray(current)) {
      return current;
    }
    setPath(target, path, [cloneValue(current)]);
    return getPath(target, path);
  }

  function pickBeam(beams, name) {
    if (!Array.isArray(beams) || beams.length === 0) {
      return undefined;
    }
    if (typeof name === "string" && name.length > 0) {
      for (var i = 0; i < beams.length; ++i) {
        if (beams[i] && beams[i].name === name) {
          return beams[i];
        }
      }
    }
    for (var j = 0; j < beams.length; ++j) {
      if (beams[j] && beams[j].active) {
        return beams[j];
      }
    }
    return beams[0];
  }

  function normalizeDetectorAliases(state) {
    var hasEnvironment = isPlainObject(state.environment);
    var hasMedium = isPlainObject(state.medium);
    var hasDetector = isPlainObject(state.detector);
    if (!hasEnvironment && !hasMedium && !hasDetector) {
      return;
    }
    var detector = {};
    if (hasEnvironment) {
      deepMerge(detector, state.environment);
    }
    if (hasMedium) {
      deepMerge(detector, state.medium);
    }
    if (hasDetector) {
      deepMerge(detector, state.detector);
    }
    state.detector = detector;
    delete state.environment;
    delete state.medium;
  }

  function typeMatches(value, expectedType) {
    if (expectedType === "array") {
      return Array.isArray(value);
    }
    if (expectedType === "null") {
      return value === null;
    }
    if (expectedType === "object") {
      return isPlainObject(value);
    }
    return typeof value === expectedType;
  }

  function requirePath(state, path, check, message) {
    var value = getPath(state, path);
    var ok = true;
    if (check === undefined || check === null) {
      ok = value !== undefined && value !== null;
    } else if (typeof check === "string") {
      ok = typeMatches(value, check);
    } else if (typeof check === "function") {
      ok = !!check(value, cloneValue(state));
    } else {
      throw new TypeError("TRECH_FLOW require check must be a string or function");
    }
    if (!ok) {
      var pathText = Array.isArray(path) ? path.join(".") : String(path);
      var suffix = message ? ": " + message : "";
      throw new Error("TRECH_FLOW require failed at '" + pathText + "'" + suffix);
    }
  }

  function createFlow(initialConfig) {
    var state;
    if (initialConfig === undefined || initialConfig === null) {
      state = {};
    } else if (isPlainObject(initialConfig) || Array.isArray(initialConfig)) {
      state = cloneValue(initialConfig);
    } else {
      throw new TypeError("TRECH_FLOW initial config must be an object or array");
    }

    var flow = {
      set: function(path, value) {
        setPath(state, path, cloneValue(value));
        return flow;
      },
      defaults: function(pathOrPatch, value) {
        if (isPlainObject(pathOrPatch)) {
          deepDefaults(state, pathOrPatch);
          return flow;
        }
        if (typeof pathOrPatch !== "string" && !Array.isArray(pathOrPatch)) {
          throw new TypeError(
              "TRECH_FLOW defaults path must be a string/array, or provide an object patch");
        }
        if (getPath(state, pathOrPatch) === undefined) {
          setPath(state, pathOrPatch, cloneValue(value));
        }
        return flow;
      },
      merge: function(patch) {
        if (!isPlainObject(patch)) {
          throw new TypeError("TRECH_FLOW merge patch must be an object");
        }
        deepMerge(state, patch);
        return flow;
      },
      push: function(path, value) {
        pushPath(state, path, cloneValue(value));
        return flow;
      },
      ensureArray: function(path) {
        ensureArrayPath(state, path);
        return flow;
      },
      derive: function(path, projector) {
        if (typeof projector !== "function") {
          throw new TypeError("TRECH_FLOW derive projector must be a function");
        }
        var next = projector(cloneValue(getPath(state, path)), cloneValue(state));
        if (next !== undefined) {
          setPath(state, path, cloneValue(next));
        }
        return flow;
      },
      selectBeam: function(name) {
        var beams = ensureArrayPath(state, "beams");
        var beam = pickBeam(beams, name);
        if (beam !== undefined) {
          state.beam = cloneValue(beam);
        }
        return flow;
      },
      normalizeDetectorAliases: function() {
        normalizeDetectorAliases(state);
        return flow;
      },
      finalize: function(options) {
        var opts = isPlainObject(options) ? options : {};
        if (opts.normalizeCollections !== false) {
          ensureArrayPath(state, "materials");
          ensureArrayPath(state, "geometry.volumes");
          ensureArrayPath(state, "beams");
          ensureArrayPath(state, "hooks.registered");
        }
        if (opts.normalizeDetectorAliases !== false) {
          normalizeDetectorAliases(state);
        }
        if (opts.selectBeam !== false) {
          var beamName = typeof opts.beamName === "string" ? opts.beamName : "";
          var selected = pickBeam(getPath(state, "beams"), beamName);
          if (selected !== undefined &&
              (opts.overrideBeam === true || getPath(state, "beam") === undefined)) {
            setPath(state, "beam", cloneValue(selected));
          }
        }
        return flow;
      },
      require: function(path, check, message) {
        requirePath(state, path, check, message);
        return flow;
      },
      assert: function(path, check, message) {
        requirePath(state, path, check, message);
        return flow;
      },
      when: function(condition, action) {
        if (!condition) {
          return flow;
        }
        if (typeof action !== "function") {
          throw new TypeError("TRECH_FLOW when action must be a function");
        }
        var next = action(flow);
        return next === undefined ? flow : next;
      },
      tap: function(action) {
        if (typeof action !== "function") {
          throw new TypeError("TRECH_FLOW tap action must be a function");
        }
        var next = action(flow);
        return next === undefined ? flow : next;
      },
      build: function() {
        return cloneValue(state);
      },
      value: function() {
        return cloneValue(state);
      },
      toJSON: function() {
        return cloneValue(state);
      }
    };
    return flow;
  }

  if (typeof global.TRECH_FLOW !== "function") {
    global.TRECH_FLOW = createFlow;
  }
})(globalThis);
)JS";

static void installFlowHelpers(JSContext* ctx) {
  JSValue result = JS_Eval(ctx, kTrechFlowBootstrap, std::strlen(kTrechFlowBootstrap),
                           "<TRECH_FLOW>", JS_EVAL_TYPE_GLOBAL);
  if (JS_IsException(result)) {
    JSValue exc = JS_GetException(ctx);
    const char* msg = JS_ToCString(ctx, exc);
    std::string err = msg ? msg : "TRECH_FLOW bootstrap failed";
    if (msg) {
      JS_FreeCString(ctx, msg);
    }
    JS_FreeValue(ctx, exc);
    JS_FreeValue(ctx, result);
    throw std::runtime_error(err);
  }
  JS_FreeValue(ctx, result);
}

static constexpr const char* kTrechValueBootstrap = R"JS(
(function(global) {
  function declareValue(name, definition) {
    if (definition === null || typeof definition !== "object" || Array.isArray(definition)) {
      throw new TypeError("TRECH_VALUE definition must be an object");
    }
    return global.__TRECH_VALUE(name, definition);
  }
  function typed(type) {
    return function(name, options) {
      var definition = {};
      var source = options || {};
      Object.keys(source).forEach(function(key) { definition[key] = source[key]; });
      definition.type = type;
      return declareValue(name, definition);
    };
  }
  declareValue.number = typed("number");
  declareValue.integer = typed("integer");
  declareValue.boolean = typed("boolean");
  declareValue.string = typed("string");
  declareValue.choice = typed("choice");
  global.TRECH_VALUE = declareValue;
})(globalThis);
)JS";

static void installValueHelpers(JSContext* ctx) {
  JSValue result = JS_Eval(ctx, kTrechValueBootstrap, std::strlen(kTrechValueBootstrap),
                           "<TRECH_VALUE>", JS_EVAL_TYPE_GLOBAL);
  if (JS_IsException(result)) {
    JSValue exc = JS_GetException(ctx);
    const char* msg = JS_ToCString(ctx, exc);
    std::string err = msg ? msg : "TRECH_VALUE bootstrap failed";
    if (msg) {
      JS_FreeCString(ctx, msg);
    }
    JS_FreeValue(ctx, exc);
    JS_FreeValue(ctx, result);
    throw std::runtime_error(err);
  }
  JS_FreeValue(ctx, result);
}

static JSValue parseConfigObject(JSContext* ctx, JSValueConst cfg, int depth = 0) {
  if (depth > 8) {
    return JS_ThrowTypeError(
        ctx, "TRECH_CONFIG nesting too deep; expected object, JSON string, or function result");
  }
  if (JS_IsFunction(ctx, cfg)) {
    JSValue global = JS_GetGlobalObject(ctx);
    JSValue flowFactory = JS_GetPropertyStr(ctx, global, "TRECH_FLOW");
    JSValue argv[1] = {flowFactory};
    JSValue produced = JS_Call(ctx, cfg, global, 1, argv);
    JS_FreeValue(ctx, flowFactory);
    JS_FreeValue(ctx, global);
    if (JS_IsException(produced)) {
      return produced;
    }
    JSValue parsed = parseConfigObject(ctx, produced, depth + 1);
    JS_FreeValue(ctx, produced);
    return parsed;
  }
  if (JS_IsString(cfg)) {
    const char* raw = JS_ToCString(ctx, cfg);
    if (!raw) {
      return JS_ThrowTypeError(ctx, "TRECH_CONFIG JSON string is invalid");
    }
    JSValue parsed = JS_ParseJSON(ctx, raw, std::strlen(raw), "<TRECH_CONFIG>");
    JS_FreeCString(ctx, raw);
    return parsed;
  }
  if (JS_IsObject(cfg)) {
    return JS_DupValue(ctx, cfg);
  }
  return JS_ThrowTypeError(
      ctx, "TRECH_CONFIG must be a JSON string, object, or function returning one");
}

static void attachHookMetadata(JSContext* ctx, JSValue cfgObj, JSValueConst hooksValue) {
  if (!JS_IsObject(hooksValue)) {
    return;
  }
  JSPropertyEnum* props = nullptr;
  uint32_t propCount = 0;
  if (JS_GetOwnPropertyNames(ctx, &props, &propCount, hooksValue,
                             JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) < 0) {
    return;
  }
  std::vector<std::string> hookNames;
  hookNames.reserve(propCount);
  for (uint32_t i = 0; i < propCount; ++i) {
    JSAtom atom = props[i].atom;
    JSValue key = JS_AtomToString(ctx, atom);
    const char* keyStr = JS_ToCString(ctx, key);
    JSValue val = JS_GetProperty(ctx, hooksValue, atom);
    if (keyStr && JS_IsFunction(ctx, val)) {
      hookNames.emplace_back(keyStr);
    }
    JS_FreeValue(ctx, val);
    if (keyStr) {
      JS_FreeCString(ctx, keyStr);
    }
    JS_FreeValue(ctx, key);
    JS_FreeAtom(ctx, atom);
  }
  js_free(ctx, props);

  if (hookNames.empty()) {
    return;
  }

  JSValue hooksObj = JS_GetPropertyStr(ctx, cfgObj, "hooks");
  if (!JS_IsObject(hooksObj)) {
    JS_FreeValue(ctx, hooksObj);
    hooksObj = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, cfgObj, "hooks", hooksObj);
    hooksObj = JS_GetPropertyStr(ctx, cfgObj, "hooks");
  }
  JSValue names = JS_NewArray(ctx);
  for (uint32_t i = 0; i < hookNames.size(); ++i) {
    JS_SetPropertyUint32(ctx, names, i, JS_NewString(ctx, hookNames[i].c_str()));
  }
  JS_SetPropertyStr(ctx, hooksObj, "registered", names);
  JS_FreeValue(ctx, hooksObj);
}

static JSValue jsTrechInclude(JSContext* ctx, JSValueConst /*this_val*/, int argc,
                              JSValueConst* argv) {
  if (argc < 1) {
    return JS_ThrowTypeError(ctx, "TRECH_INCLUDE requires a path");
  }
  const char* rawPath = JS_ToCString(ctx, argv[0]);
  if (!rawPath) {
    return JS_ThrowTypeError(ctx, "TRECH_INCLUDE path must be a string");
  }
  std::string includePath = rawPath;
  JS_FreeCString(ctx, rawPath);

  auto* state = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  const std::string resolved = resolveIncludePath(state, includePath);

  std::string code;
  try {
    code = readFile(resolved);
  } catch (const std::exception&) {
    return JS_ThrowReferenceError(ctx, "TRECH_INCLUDE cannot open: %s",
                                  resolved.c_str());
  }

  if (state) {
    state->includeStack.push_back(resolved);
  }
  JSValue result =
      JS_Eval(ctx, code.c_str(), code.size(), resolved.c_str(), JS_EVAL_TYPE_GLOBAL);
  if (state) {
    state->includeStack.pop_back();
  }
  return result;
}

static JSValue jsTrechPubChem(JSContext* ctx, JSValueConst /*this_val*/, int argc,
                              JSValueConst* argv) {
  if (argc < 1) {
    return JS_ThrowTypeError(ctx, "TRECH_PUBCHEM requires a compound name");
  }
  const char* rawName = JS_ToCString(ctx, argv[0]);
  if (!rawName) {
    return JS_ThrowTypeError(ctx, "TRECH_PUBCHEM name must be a string");
  }
  std::string name = rawName;
  JS_FreeCString(ctx, rawName);

  auto* state = static_cast<JsRuntimeState*>(JS_GetContextOpaque(ctx));
  std::filesystem::path resolved;
  std::string json;
  try {
    json = readPubChemCompoundJson(state, name, resolved);
  } catch (const std::exception& ex) {
    return JS_ThrowReferenceError(ctx, "%s", ex.what());
  }

  JSValue parsed = JS_ParseJSON(ctx, json.c_str(), json.size(), resolved.string().c_str());
  if (JS_IsException(parsed)) {
    JS_FreeValue(ctx, parsed);
    return JS_ThrowSyntaxError(ctx, "TRECH_PUBCHEM cache JSON invalid: %s",
                               resolved.string().c_str());
  }
  return parsed;
}

JsRuntime::JsRuntime() : impl_(new Impl) {
  impl_->rt = JS_NewRuntime();
  impl_->ctx = JS_NewContext(impl_->rt);
  if (!impl_->rt || !impl_->ctx) {
    throw std::runtime_error("QuickJS init failed");
  }
  JS_SetContextOpaque(impl_->ctx, &impl_->state);
  JSValue global = JS_GetGlobalObject(impl_->ctx);
  JS_SetPropertyStr(impl_->ctx, global, "TRECH_INCLUDE",
                    JS_NewCFunction(impl_->ctx, jsTrechInclude, "TRECH_INCLUDE", 1));
  JS_SetPropertyStr(impl_->ctx, global, "TRECH_PUBCHEM",
                    JS_NewCFunction(impl_->ctx, jsTrechPubChem, "TRECH_PUBCHEM", 1));
  JS_SetPropertyStr(impl_->ctx, global, "__TRECH_VALUE",
                    JS_NewCFunction(impl_->ctx, jsTrechValue, "__TRECH_VALUE", 2));
  JS_FreeValue(impl_->ctx, global);
  installFlowHelpers(impl_->ctx);
  installValueHelpers(impl_->ctx);
}

JsRuntime::~JsRuntime() {
  if (!impl_) {
    return;
  }
  if (impl_->ctx) {
    JS_FreeContext(impl_->ctx);
  }
  if (impl_->rt) {
    JS_FreeRuntime(impl_->rt);
  }
  delete impl_;
}

std::string JsRuntime::evalExperimentAndGetConfigJson(const std::string& path) {
  std::lock_guard<std::mutex> lock(impl_->mutex);
  const std::string code = readFile(path);
  impl_->state.baseDir = baseDirFromPath(path);
  impl_->state.includeStack.clear();
  impl_->state.includeStack.push_back(path);
  impl_->state.emittedRecords.clear();
  impl_->state.callEmits.clear();
  impl_->state.callDroppedEmits = 0;
  impl_->state.lastConfigJson.clear();
  impl_->state.usedScriptParameterOverrides.clear();
  impl_->state.scriptParameters.clear();
  impl_->state.scriptParameterDefinitions.clear();
  impl_->state.experimentLoaded = false;

  JSValue result = JS_Eval(impl_->ctx, code.c_str(), code.size(), path.c_str(),
                           JS_EVAL_TYPE_GLOBAL);
  impl_->state.includeStack.pop_back();
  if (JS_IsException(result)) {
    JSValue exc = JS_GetException(impl_->ctx);
    const char* msg = JS_ToCString(impl_->ctx, exc);
    std::string err = msg ? msg : "JS exception";
    if (msg) {
      JS_FreeCString(impl_->ctx, msg);
    }

    JSValue stack = JS_GetPropertyStr(impl_->ctx, exc, "stack");
    if (!JS_IsException(stack) && !JS_IsUndefined(stack) && !JS_IsNull(stack)) {
      const char* stackMsg = JS_ToCString(impl_->ctx, stack);
      if (stackMsg && stackMsg[0] != '\0') {
        err += "\n";
        err += stackMsg;
      }
      if (stackMsg) {
        JS_FreeCString(impl_->ctx, stackMsg);
      }
    }
    JS_FreeValue(impl_->ctx, stack);

    JS_FreeValue(impl_->ctx, exc);
    JS_FreeValue(impl_->ctx, result);
    throw std::runtime_error(err);
  }
  JS_FreeValue(impl_->ctx, result);

  for (const auto& [id, value] : impl_->state.scriptParameterOverrides.items()) {
    (void)value;
    if (impl_->state.usedScriptParameterOverrides.count(id) == 0) {
      throw std::runtime_error("Unknown TRECH_VALUE override: " + id);
    }
  }

  JSValue global = JS_GetGlobalObject(impl_->ctx);
  JSValue cfg = JS_GetPropertyStr(impl_->ctx, global, "TRECH_CONFIG");
  JSValue hooks = JS_GetPropertyStr(impl_->ctx, global, "TRECH_HOOKS");
  JS_FreeValue(impl_->ctx, global);

  if (JS_IsUndefined(cfg)) {
    JS_FreeValue(impl_->ctx, cfg);
    JS_FreeValue(impl_->ctx, hooks);
    throw std::runtime_error(
        "Experiment must define global TRECH_CONFIG (JSON string, object, or function).");
  }

  JSValue cfgObj = parseConfigObject(impl_->ctx, cfg);
  JS_FreeValue(impl_->ctx, cfg);
  if (JS_IsException(cfgObj)) {
    JSValue exc = JS_GetException(impl_->ctx);
    const char* msg = JS_ToCString(impl_->ctx, exc);
    std::string err = msg ? msg : "TRECH_CONFIG parse failed";
    if (msg) {
      JS_FreeCString(impl_->ctx, msg);
    }
    JS_FreeValue(impl_->ctx, exc);
    JS_FreeValue(impl_->ctx, hooks);
    JS_FreeValue(impl_->ctx, cfgObj);
    throw std::runtime_error(err);
  }

  attachHookMetadata(impl_->ctx, cfgObj, hooks);
  JS_FreeValue(impl_->ctx, hooks);

  JSValue jsonVal =
      JS_JSONStringify(impl_->ctx, cfgObj, JS_UNDEFINED, JS_UNDEFINED);
  JS_FreeValue(impl_->ctx, cfgObj);
  if (JS_IsException(jsonVal)) {
    JSValue exc = JS_GetException(impl_->ctx);
    const char* msg = JS_ToCString(impl_->ctx, exc);
    std::string err = msg ? msg : "TRECH_CONFIG stringify failed";
    if (msg) {
      JS_FreeCString(impl_->ctx, msg);
    }
    JS_FreeValue(impl_->ctx, exc);
    JS_FreeValue(impl_->ctx, jsonVal);
    throw std::runtime_error(err);
  }

  const char* s = JS_ToCString(impl_->ctx, jsonVal);
  std::string out = s ? s : "";
  if (s) {
    JS_FreeCString(impl_->ctx, s);
  }
  JS_FreeValue(impl_->ctx, jsonVal);
  impl_->state.lastConfigJson = out;
  impl_->state.experimentLoaded = true;
  loadDeclaredModels();
  return out;
}

void JsRuntime::setScriptParameterOverrides(
    const std::vector<std::string>& overrides) {
  std::lock_guard<std::mutex> lock(impl_->mutex);
  nlohmann::json parsed = nlohmann::json::object();
  for (const auto& entry : overrides) {
    const auto equals = entry.find('=');
    if (equals == std::string::npos || equals == 0 || equals + 1 >= entry.size()) {
      throw std::runtime_error("Invalid --param value; expected name=<json>");
    }
    const std::string id = entry.substr(0, equals);
    if (!validScriptParameterId(id)) {
      throw std::runtime_error("Invalid TRECH_VALUE override name: " + id);
    }
    if (parsed.contains(id)) {
      throw std::runtime_error("Duplicate TRECH_VALUE override: " + id);
    }
    nlohmann::json value = nlohmann::json::parse(
        entry.substr(equals + 1), nullptr, /*allow_exceptions=*/false);
    if (value.is_discarded()) {
      throw std::runtime_error("Invalid JSON for TRECH_VALUE override: " + id);
    }
    parsed[id] = std::move(value);
  }
  impl_->state.scriptParameterOverrides = std::move(parsed);
}

std::string JsRuntime::scriptParametersJson() const {
  std::lock_guard<std::mutex> lock(impl_->mutex);
  return nlohmann::json(impl_->state.scriptParameters).dump();
}

void JsRuntime::loadDeclaredModels() {
  impl_->state.models.clear();
  impl_->state.modelScales.clear();
  impl_->state.modelOperatorMetadata.clear();
  impl_->state.totalPredictCount = 0;
  impl_->state.totalOutOfDomainCount = 0;
  nlohmann::json root;
  try {
    root = nlohmann::json::parse(impl_->state.lastConfigJson);
  } catch (const std::exception&) {
    return;
  }
  if (!root.contains("models") || !root.at("models").is_array()) {
    return;
  }
  for (const auto& entry : root.at("models")) {
    if (!entry.is_object()) {
      continue;
    }
    const std::string name = entry.value("name", std::string(""));
    const std::string path = entry.value("path", std::string(""));
    if (name.empty() || path.empty()) {
      continue;
    }
    auto model = std::make_unique<trech::ml::GenericSurrogate>();
    // Try the path as given (relative to CWD); if that fails and the path is
    // relative, retry relative to the experiment's directory.
    bool ok = model->load(path);
    if (!ok) {
      std::filesystem::path p(path);
      if (p.is_relative() && !impl_->state.baseDir.empty()) {
        const std::string alt =
            (std::filesystem::path(impl_->state.baseDir) / p).string();
        ok = model->load(alt);
      }
    }
    // Keep the entry regardless: an unloaded model makes ctx.predict return
    // null (graceful degradation), which is deterministic and logged.
    impl_->state.models[name] = std::move(model);
    impl_->state.modelScales[name] = entry.value("scale", std::string(""));
    ModelOperatorMetadata metadata;
    metadata.role = entry.value("operator_role", std::string(""));
    metadata.elementKind = entry.value("element_kind", std::string(""));
    if (entry.contains("required_context_keys") &&
        entry.at("required_context_keys").is_array()) {
      for (const auto& key : entry.at("required_context_keys")) {
        if (key.is_string()) {
          metadata.requiredContextKeys.push_back(key.get<std::string>());
        }
      }
    }
    impl_->state.modelOperatorMetadata[name] = std::move(metadata);
  }
}

std::vector<std::string> JsRuntime::loadedModelNames() const {
  std::vector<std::string> names;
  for (const auto& [name, model] : impl_->state.models) {
    if (model && model->loaded()) {
      names.push_back(name);  // std::map iterates sorted -> deterministic
    }
  }
  return names;
}

int JsRuntime::totalPredictCount() const {
  return static_cast<int>(impl_->state.totalPredictCount);
}

int JsRuntime::totalOutOfDomainCount() const {
  return static_cast<int>(impl_->state.totalOutOfDomainCount);
}

HookDispatchReport JsRuntime::dispatchHook(const std::string& hookName,
                                           const HookRuntimeContext& context,
                                           TrechConfig* cfgForPatch,
                                           bool allowPatch) {
  std::lock_guard<std::mutex> lock(impl_->mutex);
  HookDispatchReport report;
  if (!impl_->state.experimentLoaded) {
    return report;
  }

  JSContext* ctx = impl_->ctx;
  JSValue global = JS_GetGlobalObject(ctx);
  JSValue hooks = JS_GetPropertyStr(ctx, global, "TRECH_HOOKS");
  if (!JS_IsObject(hooks)) {
    JS_FreeValue(ctx, hooks);
    JS_FreeValue(ctx, global);
    return report;
  }

  JSValue hookFn = JS_GetPropertyStr(ctx, hooks, hookName.c_str());
  if (!JS_IsFunction(ctx, hookFn)) {
    JS_FreeValue(ctx, hookFn);
    JS_FreeValue(ctx, hooks);
    JS_FreeValue(ctx, global);
    return report;
  }

  impl_->state.activeHookName = hookName;
  impl_->state.activeHookContext = context;
  impl_->state.callEmits.clear();
  impl_->state.callDroppedEmits = 0;
  impl_->state.callPredictCount = 0;
  impl_->state.callOutOfDomainCount = 0;
  impl_->state.callReactSequence = 0;
  impl_->state.callMaxEmitsPerCallback =
      context.maxEmitsPerCallback < 0 ? 0 : context.maxEmitsPerCallback;
  impl_->state.callMaxEmitPayloadBytes =
      context.maxEmitPayloadBytes < 0 ? 0 : context.maxEmitPayloadBytes;

  JSValue contextObj = JS_NewObject(ctx);
  const std::string configJson =
      cfgForPatch ? configToJsonString(*cfgForPatch) : impl_->state.lastConfigJson;
  JSValue configObj = JS_ParseJSON(ctx, configJson.c_str(), configJson.size(), "<hook_ctx>");
  if (JS_IsException(configObj)) {
    JS_FreeValue(ctx, configObj);
    configObj = JS_NewObject(ctx);
  }
  JS_SetPropertyStr(ctx, contextObj, "config", configObj);

  JSValue runtimeObj = JS_NewObject(ctx);
  JS_SetPropertyStr(ctx, runtimeObj, "seed", JS_NewInt64(ctx, static_cast<std::int64_t>(context.seed)));
  JS_SetPropertyStr(ctx, runtimeObj, "nEvents", JS_NewInt32(ctx, context.nEvents));
  JS_SetPropertyStr(ctx, runtimeObj, "mode",
                    JS_NewString(ctx, normalizeDeterminismMode(context.determinismMode).c_str()));
  JS_SetPropertyStr(ctx, contextObj, "runtime", runtimeObj);

  // ctx.materials: Geant4-derived material composition (density, per-element
  // number densities, electron density, mean excitation energy) so scenarios can
  // read what Geant4 knows instead of hard-coding it. Present only when the
  // scenario opted into materialProbe (post-Initialize hooks); otherwise absent.
  if (!context.materialsJson.empty()) {
    JSValue materialsArr = JS_ParseJSON(ctx, context.materialsJson.c_str(),
                                        context.materialsJson.size(), "<hook_materials>");
    if (JS_IsException(materialsArr)) {
      JS_FreeValue(ctx, materialsArr);
    } else {
      // Expose both an array (ordered) and a name-keyed lookup so hooks can do
      // ctx.materials["G4_WATER"].numberDensityPerCm3.H directly.
      JSValue materialsByName = JS_NewObject(ctx);
      if (JS_IsArray(ctx, materialsArr)) {
        JSValue lenVal = JS_GetPropertyStr(ctx, materialsArr, "length");
        uint32_t len = 0;
        JS_ToUint32(ctx, &len, lenVal);
        JS_FreeValue(ctx, lenVal);
        for (uint32_t i = 0; i < len; ++i) {
          JSValue item = JS_GetPropertyUint32(ctx, materialsArr, i);
          JSValue nameVal = JS_GetPropertyStr(ctx, item, "name");
          const char* nameStr = JS_ToCString(ctx, nameVal);
          if (nameStr) {
            JS_SetPropertyStr(ctx, materialsByName, nameStr, JS_DupValue(ctx, item));
            JS_FreeCString(ctx, nameStr);
          }
          JS_FreeValue(ctx, nameVal);
          JS_FreeValue(ctx, item);
        }
      }
      JS_SetPropertyStr(ctx, materialsByName, "list", materialsArr);
      JS_SetPropertyStr(ctx, contextObj, "materials", materialsByName);
    }
  }

  // ctx.optics mirrors ctx.materials: named lookups plus `.list`. Both the
  // Geant4 material name and config material key resolve to the same item.
  if (!context.opticsJson.empty()) {
    JSValue opticsArr = JS_ParseJSON(ctx, context.opticsJson.c_str(),
                                    context.opticsJson.size(), "<hook_optics>");
    if (JS_IsException(opticsArr)) {
      JS_FreeValue(ctx, opticsArr);
    } else {
      JSValue opticsByName = JS_NewObject(ctx);
      if (JS_IsArray(ctx, opticsArr)) {
        JSValue lenVal = JS_GetPropertyStr(ctx, opticsArr, "length");
        uint32_t length = 0;
        JS_ToUint32(ctx, &length, lenVal);
        JS_FreeValue(ctx, lenVal);
        for (uint32_t i = 0; i < length; ++i) {
          JSValue item = JS_GetPropertyUint32(ctx, opticsArr, i);
          const auto bindName = [&](const char* key) {
            JSValue nameVal = JS_GetPropertyStr(ctx, item, key);
            const char* nameStr = JS_ToCString(ctx, nameVal);
            if (nameStr && nameStr[0] != '\0') {
              JS_SetPropertyStr(ctx, opticsByName, nameStr, JS_DupValue(ctx, item));
            }
            if (nameStr) JS_FreeCString(ctx, nameStr);
            JS_FreeValue(ctx, nameVal);
          };
          bindName("material_name");
          bindName("config_material_key");
          JS_FreeValue(ctx, item);
        }
      }
      JS_SetPropertyStr(ctx, opticsByName, "list", opticsArr);
      JS_SetPropertyStr(ctx, contextObj, "optics", opticsByName);
    }
  }

  if (context.eventId >= 0) {
    JSValue eventObj = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, eventObj, "id", JS_NewInt32(ctx, context.eventId));
    JS_SetPropertyStr(ctx, eventObj, "edepMeV",
                      JS_NewFloat64(ctx, context.eventEdepMeV));
    JS_SetPropertyStr(ctx, eventObj, "totalTrackLengthMm",
                      JS_NewFloat64(ctx, context.eventTotalTrackLengthMm));
    JS_SetPropertyStr(ctx, eventObj, "totalStepCount",
                      JS_NewInt32(ctx, context.eventTotalStepCount));
    JS_SetPropertyStr(ctx, eventObj, "totalTrackCount",
                      JS_NewInt32(ctx, context.eventTotalTrackCount));
    JS_SetPropertyStr(ctx, eventObj, "opticalPhotonSteps",
                      JS_NewInt32(ctx, context.eventOpticalPhotonSteps));
    JS_SetPropertyStr(ctx, eventObj, "opticalPhotonTracks",
                      JS_NewInt32(ctx, context.eventOpticalPhotonTracks));
    JS_SetPropertyStr(ctx, eventObj, "opticalPhotonTrackLengthMm",
                      JS_NewFloat64(ctx, context.eventOpticalPhotonTrackLengthMm));
    JS_SetPropertyStr(ctx, contextObj, "event", eventObj);
  } else {
    JS_SetPropertyStr(ctx, contextObj, "event", JS_NULL);
  }

  if (context.stepIndex >= 0) {
    JSValue stepObj = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, stepObj, "index", JS_NewInt32(ctx, context.stepIndex));
    JS_SetPropertyStr(ctx, stepObj, "edepMeV", JS_NewFloat64(ctx, context.stepEdepMeV));
    JS_SetPropertyStr(ctx, stepObj, "stepLengthMm", JS_NewFloat64(ctx, context.stepLengthMm));
    JS_SetPropertyStr(ctx, contextObj, "step", stepObj);
  } else {
    JS_SetPropertyStr(ctx, contextObj, "step", JS_NULL);
  }

  JSValue stateObj = JS_GetPropertyStr(ctx, global, "__TRECH_HOOK_STATE");
  if (!JS_IsObject(stateObj)) {
    JS_FreeValue(ctx, stateObj);
    stateObj = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, global, "__TRECH_HOOK_STATE", JS_DupValue(ctx, stateObj));
  }
  JS_SetPropertyStr(ctx, contextObj, "state", stateObj);

  JSValue rngObj = JS_NewObject(ctx);
  const auto hookSeed = hashHookSeed(hookName, context);
  JS_SetPropertyStr(ctx, rngObj, "__seed", JS_NewInt64(ctx, static_cast<std::int64_t>(hookSeed)));
  JS_SetPropertyStr(ctx, rngObj, "uniform",
                    JS_NewCFunction(ctx, jsHookRngUniform, "uniform", 0));
  JS_SetPropertyStr(ctx, rngObj, "int", JS_NewCFunction(ctx, jsHookRngInt, "int", 2));
  JS_SetPropertyStr(ctx, contextObj, "rng", rngObj);
  JS_SetPropertyStr(ctx, contextObj, "emit", JS_NewCFunction(ctx, jsHookEmit, "emit", 2));
  JS_SetPropertyStr(ctx, contextObj, "predict",
                    JS_NewCFunction(ctx, jsHookPredict, "predict", 2));
  JS_SetPropertyStr(ctx, contextObj, "cascade",
                    JS_NewCFunction(ctx, jsHookCascade, "cascade", 1));
  JS_SetPropertyStr(ctx, contextObj, "evolve",
                    JS_NewCFunction(ctx, jsHookEvolve, "evolve", 1));
  JS_SetPropertyStr(ctx, contextObj, "react",
                    JS_NewCFunction(ctx, jsHookReact, "react", 1));
  JS_SetPropertyStr(ctx, contextObj, "interact",
                    JS_NewCFunction(ctx, jsHookInteract, "interact", 1));

  JSValue argv[1] = {contextObj};
  JSValue hookResult = JS_Call(ctx, hookFn, hooks, 1, argv);
  JS_FreeValue(ctx, contextObj);
  JS_FreeValue(ctx, hookFn);
  JS_FreeValue(ctx, hooks);
  JS_FreeValue(ctx, global);

  if (JS_IsException(hookResult)) {
    JSValue exc = JS_GetException(ctx);
    std::string err = "Hook dispatch failed";
    const char* msg = JS_ToCString(ctx, exc);
    if (msg) {
      err = msg;
      JS_FreeCString(ctx, msg);
    }
    JSValue stack = JS_GetPropertyStr(ctx, exc, "stack");
    if (!JS_IsException(stack) && !JS_IsUndefined(stack) && !JS_IsNull(stack)) {
      const char* stackMsg = JS_ToCString(ctx, stack);
      if (stackMsg && stackMsg[0] != '\0') {
        err += "\n";
        err += stackMsg;
      }
      if (stackMsg) {
        JS_FreeCString(ctx, stackMsg);
      }
    }
    JS_FreeValue(ctx, stack);
    JS_FreeValue(ctx, exc);
    JS_FreeValue(ctx, hookResult);
    throw std::runtime_error(err);
  }

  report.invoked = true;
  report.emitCount = impl_->state.callEmits.size();
  report.emitDroppedCount = impl_->state.callDroppedEmits;
  report.predictCount = impl_->state.callPredictCount;
  report.outOfDomainCount = impl_->state.callOutOfDomainCount;

  if (allowPatch && cfgForPatch && JS_IsObject(hookResult)) {
    JSValue override = JS_GetPropertyStr(ctx, hookResult, "override");
    if (JS_IsObject(override)) {
      const auto overrideJson = jsonStringifyValue(ctx, override);
      if (!overrideJson.empty()) {
        try {
          const auto patch = nlohmann::json::parse(overrideJson);
          report.patchApplied =
              applyHookOverridePatch(*cfgForPatch, patch, report.patchedPaths);
          if (report.patchApplied) {
            impl_->state.lastConfigJson = configToJsonString(*cfgForPatch);
          }
        } catch (const std::exception&) {
          // Keep hook execution deterministic: ignore malformed override payloads.
        }
      }
    }
    JS_FreeValue(ctx, override);
  }

  JS_FreeValue(ctx, hookResult);
  return report;
}

std::vector<HookEmitRecord> JsRuntime::takeEmittedRecords() {
  std::lock_guard<std::mutex> lock(impl_->mutex);
  auto out = impl_->state.emittedRecords;
  impl_->state.emittedRecords.clear();
  return out;
}

} // namespace trech
