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

static JSValue parseConfigObject(JSContext* ctx, JSValueConst cfg) {
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
  return JS_ThrowTypeError(ctx, "TRECH_CONFIG must be a JSON string or object");
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
    throw std::runtime_error("Experiment must define global TRECH_CONFIG (JSON string or object).");
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
