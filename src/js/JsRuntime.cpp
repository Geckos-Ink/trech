#include "trech/js/JsRuntime.hpp"

#include <fstream>
#include <sstream>
#include <stdexcept>

extern "C" {
#include "quickjs.h"
}

namespace trech {

struct JsRuntime::Impl {
  JSRuntime* rt = nullptr;
  JSContext* ctx = nullptr;
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

JsRuntime::JsRuntime() : impl_(new Impl) {
  impl_->rt = JS_NewRuntime();
  impl_->ctx = JS_NewContext(impl_->rt);
  if (!impl_->rt || !impl_->ctx) {
    throw std::runtime_error("QuickJS init failed");
  }
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

  JSValue result = JS_Eval(impl_->ctx, code.c_str(), code.size(), path.c_str(),
                           JS_EVAL_TYPE_GLOBAL);
  if (JS_IsException(result)) {
    JSValue exc = JS_GetException(impl_->ctx);
    const char* msg = JS_ToCString(impl_->ctx, exc);
    std::string err = msg ? msg : "JS exception";
    if (msg) {
      JS_FreeCString(impl_->ctx, msg);
    }
    JS_FreeValue(impl_->ctx, exc);
    JS_FreeValue(impl_->ctx, result);
    throw std::runtime_error(err);
  }
  JS_FreeValue(impl_->ctx, result);

  JSValue global = JS_GetGlobalObject(impl_->ctx);
  JSValue cfg = JS_GetPropertyStr(impl_->ctx, global, "TRECH_CONFIG");
  JS_FreeValue(impl_->ctx, global);

  if (JS_IsUndefined(cfg)) {
    JS_FreeValue(impl_->ctx, cfg);
    throw std::runtime_error("Experiment must define global TRECH_CONFIG (JSON string).");
  }

  const char* s = JS_ToCString(impl_->ctx, cfg);
  std::string out = s ? s : "";
  if (s) {
    JS_FreeCString(impl_->ctx, s);
  }
  JS_FreeValue(impl_->ctx, cfg);
  return out;
}

} // namespace trech
