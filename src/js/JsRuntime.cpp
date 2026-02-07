#include "trech/js/JsRuntime.hpp"

#include "trech/core/Config.hpp"

#include <filesystem>
#include <fstream>
#include <cstring>
#include <cctype>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <vector>

#include <nlohmann/json.hpp>

extern "C" {
#include "quickjs.h"
}

namespace trech {

struct JsRuntimeState {
  std::string baseDir;
  std::vector<std::string> includeStack;
  std::string lastConfigJson;
  std::string activeHookName;
  HookRuntimeContext activeHookContext;
  std::vector<HookEmitRecord> emittedRecords;
  std::vector<HookEmitRecord> callEmits;
  bool experimentLoaded = false;
};

struct JsRuntime::Impl {
  JSRuntime* rt = nullptr;
  JSContext* ctx = nullptr;
  JsRuntimeState state;
  std::mutex mutex;
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
  HookEmitRecord emit;
  emit.hook = state->activeHookName;
  emit.tag = tagRaw;
  emit.eventId = state->activeHookContext.eventId;
  emit.stepIndex = state->activeHookContext.stepIndex;
  JS_FreeCString(ctx, tagRaw);
  if (argc > 1) {
    emit.payloadJson = jsonStringifyValue(ctx, argv[1]);
  } else {
    emit.payloadJson = "null";
  }
  state->emittedRecords.push_back(emit);
  state->callEmits.push_back(emit);
  return JS_UNDEFINED;
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
  JS_FreeValue(impl_->ctx, global);
  installFlowHelpers(impl_->ctx);
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
  impl_->state.lastConfigJson.clear();
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
        err = stackMsg;
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
  return out;
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

  if (context.eventId >= 0) {
    JSValue eventObj = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, eventObj, "id", JS_NewInt32(ctx, context.eventId));
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
        err = stackMsg;
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
