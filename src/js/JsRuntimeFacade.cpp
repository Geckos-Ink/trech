// trech::JsRuntime: the public JavaScript runtime, delegating to the selected engine backend.
#include "trech/js/JsRuntime.hpp"

#include "JsEngineBackend.hpp"

#include <atomic>
#include <cstdlib>
#include <stdexcept>
#include <utility>

#ifndef TRECH_QUICKJS_VERSION
#define TRECH_QUICKJS_VERSION "unknown"
#endif

namespace trech {
namespace {

// -1: not chosen yet; otherwise the JsEngine value set by setDefaultEngine().
std::atomic<int> chosenDefault{-1};

JsEngine buildDefault() {
#if defined(TRECH_HAS_V8) && defined(TRECH_DEFAULT_JS_ENGINE_V8)
  return JsEngine::V8;
#else
  return JsEngine::QuickJs;
#endif
}

void requireAvailable(JsEngine engine) {
  if (!JsRuntime::engineAvailable(engine)) {
    throw std::runtime_error(std::string("JavaScript engine '") + jsEngineName(engine) +
                             "' is not built into this binary (configure with -DTRECH_ENABLE_V8=ON; "
                             "see docs/engine/v8.md)");
  }
}

}  // namespace

struct JsRuntime::Impl {
  JsEngine engine = JsEngine::QuickJs;
  std::unique_ptr<JsEngineBackend> backend;
};

const char* jsEngineName(JsEngine engine) { return engine == JsEngine::V8 ? "v8" : "quickjs"; }

JsEngine parseJsEngine(const std::string& name) {
  if (name == "quickjs") return JsEngine::QuickJs;
  if (name == "v8") return JsEngine::V8;
  throw std::invalid_argument("unknown JavaScript engine '" + name + "' (expected quickjs or v8)");
}

bool JsRuntime::engineAvailable(JsEngine engine) {
#ifdef TRECH_HAS_V8
  (void)engine;
  return true;
#else
  return engine == JsEngine::QuickJs;
#endif
}

JsEngine JsRuntime::defaultEngine() {
  const int chosen = chosenDefault.load();
  JsEngine engine = buildDefault();
  if (chosen >= 0) {
    engine = static_cast<JsEngine>(chosen);
  } else if (const char* env = std::getenv("TRECH_JS_ENGINE"); env && *env) {
    try {
      engine = parseJsEngine(env);
    } catch (const std::invalid_argument& error) {
      throw std::runtime_error(std::string("TRECH_JS_ENGINE: ") + error.what());
    }
  }
  requireAvailable(engine);
  return engine;
}

void JsRuntime::setDefaultEngine(JsEngine engine) {
  requireAvailable(engine);
  chosenDefault.store(static_cast<int>(engine));
}

JsRuntime::JsRuntime() : JsRuntime(defaultEngine()) {}

JsRuntime::JsRuntime(JsEngine engine) : impl_(new Impl) {
  try {
    requireAvailable(engine);
    impl_->engine = engine;
#ifdef TRECH_HAS_V8
    impl_->backend = engine == JsEngine::V8 ? makeV8Backend() : makeQuickJsBackend();
#else
    impl_->backend = makeQuickJsBackend();
#endif
  } catch (...) {
    delete impl_;
    throw;
  }
}

JsRuntime::~JsRuntime() { delete impl_; }

JsEngine JsRuntime::engine() const { return impl_->engine; }

std::string JsRuntime::engineIdentity() const {
#ifdef TRECH_HAS_V8
  if (impl_->engine == JsEngine::V8) return "v8 " + v8EngineVersion();
#endif
  return std::string("quickjs ") + TRECH_QUICKJS_VERSION;
}

void JsRuntime::swap(JsRuntime& other) noexcept { std::swap(impl_, other.impl_); }

std::string JsRuntime::evalExperimentAndGetConfigJson(const std::string& path) {
  return impl_->backend->evalExperimentAndGetConfigJson(path);
}
void JsRuntime::setScriptParameterOverrides(const std::vector<std::string>& overrides) {
  impl_->backend->setScriptParameterOverrides(overrides);
}
void JsRuntime::setPrecisionRefinement(double factor) { impl_->backend->setPrecisionRefinement(factor); }
std::string JsRuntime::scriptParametersJson() const { return impl_->backend->scriptParametersJson(); }
std::string JsRuntime::authoringMetadataJson() const { return impl_->backend->authoringMetadataJson(); }
std::vector<std::string> JsRuntime::sourceFiles() const { return impl_->backend->sourceFiles(); }
std::vector<JsSourceDigest> JsRuntime::sourceDigests() const { return impl_->backend->sourceDigests(); }
HookDispatchReport JsRuntime::dispatchHook(const std::string& hookName, const HookRuntimeContext& context,
                                           TrechConfig* cfgForPatch, bool allowPatch) {
  return impl_->backend->dispatchHook(hookName, context, cfgForPatch, allowPatch);
}
std::vector<HookEmitRecord> JsRuntime::takeEmittedRecords() { return impl_->backend->takeEmittedRecords(); }
void JsRuntime::loadDeclaredModels() { impl_->backend->loadDeclaredModels(); }
std::vector<std::string> JsRuntime::loadedModelNames() const { return impl_->backend->loadedModelNames(); }
std::string JsRuntime::modelArtifactsJson() const { return impl_->backend->modelArtifactsJson(); }
int JsRuntime::totalPredictCount() const { return impl_->backend->totalPredictCount(); }
int JsRuntime::totalOutOfDomainCount() const { return impl_->backend->totalOutOfDomainCount(); }

}  // namespace trech
