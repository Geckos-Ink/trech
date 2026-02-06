#include "trech/js/JsRuntime.hpp"

#include <filesystem>
#include <fstream>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <vector>

extern "C" {
#include "quickjs.h"
}

namespace trech {

struct JsRuntimeState {
  std::string baseDir;
  std::vector<std::string> includeStack;
};

struct JsRuntime::Impl {
  JSRuntime* rt = nullptr;
  JSContext* ctx = nullptr;
  JsRuntimeState state;
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
  const std::string code = readFile(path);
  impl_->state.baseDir = baseDirFromPath(path);
  impl_->state.includeStack.clear();
  impl_->state.includeStack.push_back(path);

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
  return out;
}

} // namespace trech
