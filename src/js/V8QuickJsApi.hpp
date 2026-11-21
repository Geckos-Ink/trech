// The subset of the QuickJS C API that TRECH's JavaScript host uses, implemented on V8.
//
// TRECH's host (src/js/JsRuntime.cpp: TRECH_INCLUDE, TRECH_VALUE, the hook ctx, ctx.rng and
// every inference API) is written once against the QuickJS C API. src/js/JsRuntimeV8.cpp
// compiles that same source a second time against this header, so the V8 backend runs the
// identical marshalling, validation and inference code; there is no second copy to drift.
//
// Everything lives in namespace trech::v8engine, so these names never collide with the real
// QuickJS symbols linked into the same binary. Only the 62 functions and macros the host uses
// exist. The semantics follow QuickJS where they matter for replay:
//   - values are V8 handles valid inside the JsEnter scope of the current entry point;
//     JS_FreeValue / JS_DupValue are no-ops (V8 is garbage collected);
//   - an operation that runs JavaScript (getters, valueOf, calls, eval) catches the V8
//     exception, stores it as the context's pending exception and returns JS_EXCEPTION or -1;
//     JS_GetException takes it back, and a host function that returns JS_EXCEPTION rethrows it;
//   - host functions see argv padded with undefined up to their declared length, as in QuickJS;
//   - JS_ToInt64 uses QuickJS's exact float-to-int64 rule (modulo 2^64, NaN/Infinity -> 0);
//   - Math.* transcendentals are replaced by the same trech_dmath C functions QuickJS uses, with
//     QuickJS's JavaScript-level wrappers, so Math results are bit-identical across engines;
//   - the `**` operator cannot be routed through trech_dmath, so JS_Eval refuses scripts that
//     contain it, and eval / new Function refuse such strings with an EvalError (see
//     include/trech/js/PowOperatorScan.hpp and docs/engine/v8.md);
//   - promise jobs never run (QuickJS's host never runs pending jobs either);
//   - error stacks use QuickJS's "    at name (file:line:column)" line format.
#pragma once

#include <v8.h>

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace trech::v8engine {

struct JSRuntime;
struct JSContext;

enum class JsTag : std::uint8_t { Value, Undefined, Null, False, True, Exception };

struct JSValue {
  v8::Local<v8::Value> local;
  JsTag tag = JsTag::Undefined;

  JSValue() = default;
  JSValue(v8::Local<v8::Value> value) : local(value), tag(value.IsEmpty() ? JsTag::Exception : JsTag::Value) {}
  static JSValue of(JsTag t) { JSValue v; v.tag = t; return v; }
};
using JSValueConst = JSValue;

struct JSAtom {
  v8::Local<v8::Value> key;
};
struct JSPropertyEnum {
  bool is_enumerable = true;
  JSAtom atom;
};

using JSCFunction = JSValue(JSContext* ctx, JSValueConst this_val, int argc, JSValueConst* argv);

struct JsHostFunction {
  JSContext* ctx = nullptr;
  JSCFunction* fn = nullptr;
  int length = 0;
  v8::Global<v8::Function> function;
};

struct JSRuntime {
  v8::Isolate* isolate = nullptr;
  std::unique_ptr<v8::ArrayBuffer::Allocator> allocator;
};

struct JSContext {
  JSRuntime* rt = nullptr;
  v8::Isolate* isolate = nullptr;
  v8::Global<v8::Context> context;
  v8::Local<v8::Context> current;  // set by JsEnter for the duration of an entry point
  void* opaque = nullptr;
  v8::Global<v8::Value> pending;
  v8::Global<v8::Function> jsonStringify;
  // One function object per host function: the hook ctx is rebuilt on every dispatch, and
  // re-creating ~20 V8 functions each time would dominate a cheap onStep hook.
  std::unordered_map<JSCFunction*, std::unique_ptr<JsHostFunction>> functions;
  v8::Local<v8::Context> local() const { return current; }
};

// Enter the isolate and context for one host entry point (constructor, eval, dispatch, ...).
// Holds a v8::Locker, so Geant4 worker threads may dispatch hooks one at a time.
class JsEnter {
public:
  explicit JsEnter(JSContext* ctx);
  ~JsEnter();
  JsEnter(const JsEnter&) = delete;
  JsEnter& operator=(const JsEnter&) = delete;

private:
  JSContext* ctx_;
  v8::Locker locker_;
  v8::Isolate::Scope isolateScope_;
  v8::HandleScope handles_;
  v8::Local<v8::Context> previous_;
  v8::Context::Scope contextScope_;
};

constexpr int JS_EVAL_TYPE_GLOBAL = 0;
constexpr int JS_GPN_STRING_MASK = 1 << 0;
constexpr int JS_GPN_ENUM_ONLY = 1 << 4;

// Engine identity for provenance ("15.9.128.11").
std::string engineVersion();

JSRuntime* JS_NewRuntime();
void JS_FreeRuntime(JSRuntime* rt);
JSContext* JS_NewContext(JSRuntime* rt);
void JS_FreeContext(JSContext* ctx);
inline void JS_SetContextOpaque(JSContext* ctx, void* opaque) { ctx->opaque = opaque; }
inline void* JS_GetContextOpaque(JSContext* ctx) { return ctx->opaque; }

inline bool JS_IsException(JSValueConst v) { return v.tag == JsTag::Exception; }
inline bool JS_IsUndefined(JSValueConst v) {
  return v.tag == JsTag::Undefined || (v.tag == JsTag::Value && v.local->IsUndefined());
}
inline bool JS_IsNull(JSValueConst v) {
  return v.tag == JsTag::Null || (v.tag == JsTag::Value && v.local->IsNull());
}
inline bool JS_IsBool(JSValueConst v) {
  return v.tag == JsTag::False || v.tag == JsTag::True || (v.tag == JsTag::Value && v.local->IsBoolean());
}
inline bool JS_IsNumber(JSValueConst v) { return v.tag == JsTag::Value && v.local->IsNumber(); }
inline bool JS_IsString(JSValueConst v) { return v.tag == JsTag::Value && v.local->IsString(); }
inline bool JS_IsObject(JSValueConst v) { return v.tag == JsTag::Value && v.local->IsObject(); }
inline int JS_IsArray(JSContext*, JSValueConst v) { return v.tag == JsTag::Value && v.local->IsArray(); }
inline bool JS_IsFunction(JSContext*, JSValueConst v) { return v.tag == JsTag::Value && v.local->IsFunction(); }

inline JSValue JS_DupValue(JSContext*, JSValueConst v) { return v; }
inline void JS_FreeValue(JSContext*, JSValueConst) {}
inline void JS_FreeAtom(JSContext*, JSAtom) {}
void JS_FreeCString(JSContext* ctx, const char* text);
inline void js_free(JSContext*, JSPropertyEnum* props) { delete[] props; }

JSValue JS_NewObject(JSContext* ctx);
JSValue JS_NewObjectProto(JSContext* ctx, JSValueConst proto);
JSValue JS_NewArray(JSContext* ctx);
JSValue JS_NewString(JSContext* ctx, const char* text);
JSValue JS_NewStringLen(JSContext* ctx, const char* text, std::size_t length);
JSValue JS_NewFloat64(JSContext* ctx, double value);
JSValue JS_NewInt32(JSContext* ctx, std::int32_t value);
JSValue JS_NewInt64(JSContext* ctx, std::int64_t value);
inline JSValue JS_NewBool(JSContext*, bool value) { return JSValue::of(value ? JsTag::True : JsTag::False); }
JSValue JS_NewCFunction(JSContext* ctx, JSCFunction* fn, const char* name, int length);
JSValue JS_GetGlobalObject(JSContext* ctx);

JSValue JS_GetPropertyStr(JSContext* ctx, JSValueConst object, const char* name);
JSValue JS_GetPropertyUint32(JSContext* ctx, JSValueConst object, std::uint32_t index);
JSValue JS_GetProperty(JSContext* ctx, JSValueConst object, JSAtom atom);
int JS_SetPropertyStr(JSContext* ctx, JSValueConst object, const char* name, JSValue value);
int JS_SetPropertyUint32(JSContext* ctx, JSValueConst object, std::uint32_t index, JSValue value);
int JS_GetOwnPropertyNames(JSContext* ctx, JSPropertyEnum** properties, std::uint32_t* count,
                           JSValueConst object, int flags);
JSValue JS_AtomToString(JSContext* ctx, JSAtom atom);
const char* JS_AtomToCString(JSContext* ctx, JSAtom atom);

int JS_ToFloat64(JSContext* ctx, double* out, JSValueConst value);
int JS_ToInt32(JSContext* ctx, std::int32_t* out, JSValueConst value);
int JS_ToUint32(JSContext* ctx, std::uint32_t* out, JSValueConst value);
int JS_ToInt64(JSContext* ctx, std::int64_t* out, JSValueConst value);
int JS_ToBool(JSContext* ctx, JSValueConst value);
const char* JS_ToCString(JSContext* ctx, JSValueConst value);
const char* JS_ToCStringLen(JSContext* ctx, std::size_t* length, JSValueConst value);

JSValue JS_ParseJSON(JSContext* ctx, const char* text, std::size_t length, const char* filename);
JSValue JS_JSONStringify(JSContext* ctx, JSValueConst value, JSValueConst replacer, JSValueConst space);
JSValue JS_Eval(JSContext* ctx, const char* code, std::size_t length, const char* filename, int flags);
JSValue JS_Call(JSContext* ctx, JSValueConst function, JSValueConst thisValue, int argc, JSValueConst* argv);
JSValue JS_GetException(JSContext* ctx);

JSValue JS_ThrowTypeError(JSContext* ctx, const char* format, ...);
JSValue JS_ThrowRangeError(JSContext* ctx, const char* format, ...);
JSValue JS_ThrowReferenceError(JSContext* ctx, const char* format, ...);
JSValue JS_ThrowSyntaxError(JSContext* ctx, const char* format, ...);
JSValue JS_ThrowInternalError(JSContext* ctx, const char* format, ...);

}  // namespace trech::v8engine

#define JS_UNDEFINED (::trech::v8engine::JSValue::of(::trech::v8engine::JsTag::Undefined))
#define JS_NULL (::trech::v8engine::JSValue::of(::trech::v8engine::JsTag::Null))
#define JS_FALSE (::trech::v8engine::JSValue::of(::trech::v8engine::JsTag::False))
#define JS_TRUE (::trech::v8engine::JSValue::of(::trech::v8engine::JsTag::True))
#define JS_EXCEPTION (::trech::v8engine::JSValue::of(::trech::v8engine::JsTag::Exception))
