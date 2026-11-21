// V8 implementation of the QuickJS C API subset used by TRECH's JavaScript host.
// See V8QuickJsApi.hpp for the contract.
#include "V8QuickJsApi.hpp"

#include "trech/js/DeterministicMath.h"
#include "trech/js/PowOperatorScan.hpp"

#include <libplatform/libplatform.h>
#include <v8-fast-api-calls.h>

#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <string>

namespace trech::v8engine {
namespace {

std::unique_ptr<v8::Platform>& platformSlot() {
  static std::unique_ptr<v8::Platform> platform;
  return platform;
}

void initializeV8Once() {
  static std::once_flag once;
  std::call_once(once, [] {
#ifdef TRECH_V8_ICU_DATA
    v8::V8::InitializeICU(TRECH_V8_ICU_DATA);
#endif
    platformSlot() = v8::platform::NewDefaultPlatform();
    v8::V8::InitializePlatform(platformSlot().get());
    if (!v8::V8::Initialize()) throw std::runtime_error("V8 initialization failed");
  });
}

v8::Local<v8::Value> toLocal(JSContext* ctx, JSValueConst value) {
  switch (value.tag) {
    case JsTag::Value: return value.local;
    case JsTag::Null: return v8::Null(ctx->isolate);
    case JsTag::False: return v8::False(ctx->isolate);
    case JsTag::True: return v8::True(ctx->isolate);
    case JsTag::Undefined:
    case JsTag::Exception: break;
  }
  return v8::Undefined(ctx->isolate);
}

v8::Local<v8::String> newString(v8::Isolate* isolate, const char* text, int length = -1,
                                v8::NewStringType type = v8::NewStringType::kNormal) {
  v8::Local<v8::String> out;
  if (!v8::String::NewFromUtf8(isolate, text, type, length).ToLocal(&out))
    throw std::runtime_error("V8 string allocation failed");
  return out;
}

v8::Local<v8::String> keyString(JSContext* ctx, const char* name) {
  return newString(ctx->isolate, name, -1, v8::NewStringType::kInternalized);
}

JSValue catchInto(JSContext* ctx, v8::TryCatch& caught) {
  if (caught.HasCaught()) ctx->pending.Reset(ctx->isolate, caught.Exception());
  return JS_EXCEPTION;
}

int catchStatus(JSContext* ctx, v8::TryCatch& caught) {
  if (caught.HasCaught()) ctx->pending.Reset(ctx->isolate, caught.Exception());
  return -1;
}

JSValue throwError(JSContext* ctx, v8::Local<v8::Value> (*make)(v8::Local<v8::String>, v8::Local<v8::Value>),
                   const char* name, const char* format, va_list args) {
  va_list copy;
  va_copy(copy, args);
  const int needed = std::vsnprintf(nullptr, 0, format, copy);
  va_end(copy);
  std::string message(needed > 0 ? static_cast<std::size_t>(needed) : 0, '\0');
  if (needed > 0) std::vsnprintf(message.data(), message.size() + 1, format, args);
  auto error = make(newString(ctx->isolate, message.c_str()), v8::Local<v8::Value>());
  if (name && error->IsObject())
    (void)error.As<v8::Object>()->Set(ctx->local(), keyString(ctx, "name"), keyString(ctx, name));
  ctx->pending.Reset(ctx->isolate, error);
  return JS_EXCEPTION;
}

// Receiver object for property access. QuickJS reads properties of primitives through
// ToObject and throws a TypeError for undefined/null.
bool receiver(JSContext* ctx, JSValueConst value, v8::Local<v8::Object>* out, const char* key) {
  const auto local = toLocal(ctx, value);
  if (local->IsObject()) {
    *out = local.As<v8::Object>();
    return true;
  }
  if (local->IsNullOrUndefined()) {
    const std::string message = std::string("cannot read property '") + (key ? key : "") +
                                "' of " + (local->IsNull() ? "null" : "undefined");
    ctx->pending.Reset(ctx->isolate,
                       v8::Exception::TypeError(newString(ctx->isolate, message.c_str())));
    return false;
  }
  v8::TryCatch caught(ctx->isolate);
  if (!local->ToObject(ctx->local()).ToLocal(out)) {
    catchStatus(ctx, caught);
    return false;
  }
  return true;
}

const char* duplicate(v8::Isolate* isolate, v8::Local<v8::String> text, std::size_t* length) {
  const std::size_t size = text->Utf8LengthV2(isolate);
  char* out = static_cast<char*>(std::malloc(size + 1));
  if (!out) return nullptr;
  text->WriteUtf8V2(isolate, out, size + 1, v8::String::WriteFlags::kNullTerminate);
  if (length) *length = size;
  return out;
}

// ---- host functions -------------------------------------------------------------------

void hostTrampoline(const v8::FunctionCallbackInfo<v8::Value>& info) {
  auto* host = static_cast<JsHostFunction*>(info.DataV2().As<v8::External>()->Value(v8::kExternalPointerTypeTagDefault));
  JSContext* ctx = host->ctx;
  const int argc = info.Length();
  const int padded = argc > host->length ? argc : host->length;
  JSValue inline_args[8];
  std::vector<JSValue> heap_args;
  JSValue* argv = inline_args;
  if (padded > 8) {
    heap_args.resize(static_cast<std::size_t>(padded));
    argv = heap_args.data();
  }
  for (int i = 0; i < argc; ++i) argv[i] = JSValue(info[i]);
  for (int i = argc; i < padded; ++i) argv[i] = JS_UNDEFINED;
  JSValue result;
  try {
    result = host->fn(ctx, JSValue(info.This()), argc, argv);
  } catch (const std::exception& error) {
    ctx->pending.Reset(ctx->isolate, v8::Exception::Error(newString(ctx->isolate, error.what())));
    result = JS_EXCEPTION;
  }
  if (JS_IsException(result)) {
    v8::Local<v8::Value> exception = ctx->pending.IsEmpty()
        ? v8::Exception::Error(newString(ctx->isolate, "host function failed"))
        : ctx->pending.Get(ctx->isolate);
    ctx->pending.Reset();
    ctx->isolate->ThrowException(exception);
    return;
  }
  ctx->pending.Reset();
  info.GetReturnValue().Set(toLocal(ctx, result));
}

// ---- deterministic Math ---------------------------------------------------------------
// The same trech_dmath functions QuickJS's Math uses, with QuickJS's JavaScript wrappers:
// ToNumber of each argument in order (missing arguments are undefined -> NaN), js_pow's
// non-IEEE |x| = 1 case, and hypot folded pairwise. Fast API entries let optimized code call
// them directly with number arguments; any other argument takes the slow path.

double argNumber(const v8::FunctionCallbackInfo<v8::Value>& info, int index, bool* ok) {
  if (index >= info.Length()) return std::numeric_limits<double>::quiet_NaN();
  double out = 0.0;
  if (!info[index]->NumberValue(info.GetIsolate()->GetCurrentContext()).To(&out)) *ok = false;
  return out;
}

double quickJsPow(double a, double b) {
  if (!std::isfinite(b) && std::fabs(a) == 1.0) return std::numeric_limits<double>::quiet_NaN();
  return trech_dmath_pow(a, b);
}

template <double (*F)(double)>
double fastUnary(v8::Local<v8::Object>, double x) { return F(x); }

template <double (*F)(double)>
void slowUnary(const v8::FunctionCallbackInfo<v8::Value>& info) {
  bool ok = true;
  const double x = argNumber(info, 0, &ok);
  if (ok) info.GetReturnValue().Set(F(x));
}

template <double (*F)(double, double)>
double fastBinary(v8::Local<v8::Object>, double x, double y) { return F(x, y); }

template <double (*F)(double, double)>
void slowBinary(const v8::FunctionCallbackInfo<v8::Value>& info) {
  bool ok = true;
  const double x = argNumber(info, 0, &ok);
  if (!ok) return;
  const double y = argNumber(info, 1, &ok);
  if (ok) info.GetReturnValue().Set(F(x, y));
}

void slowHypot(const v8::FunctionCallbackInfo<v8::Value>& info) {
  const int n = info.Length();
  bool ok = true;
  double r = 0.0;
  if (n > 0) {
    r = argNumber(info, 0, &ok);
    if (!ok) return;
    if (n == 1) {
      r = std::fabs(r);
    } else {
      for (int i = 1; i < n; ++i) {
        const double a = argNumber(info, i, &ok);
        if (!ok) return;
        r = trech_dmath_hypot(r, a);
      }
    }
  }
  info.GetReturnValue().Set(r);
}

double fastHypot(v8::Local<v8::Object>, double x, double y) { return trech_dmath_hypot(x, y); }

void defineMath(JSContext* ctx, v8::Local<v8::Object> math, const char* name, int length,
                v8::FunctionCallback slow, const v8::CFunction* fast) {
  auto isolate = ctx->isolate;
  auto context = ctx->local();
  auto tmpl = v8::FunctionTemplate::New(isolate, slow, v8::Local<v8::Value>(), v8::Local<v8::Signature>(),
                                        length, v8::ConstructorBehavior::kThrow,
                                        v8::SideEffectType::kHasNoSideEffect, fast);
  auto function = tmpl->GetFunction(context).ToLocalChecked();
  auto key = keyString(ctx, name);
  function->SetName(key);
  math->DefineOwnProperty(context, key, function, v8::DontEnum).Check();
}

#define TRECH_V8_UNARY(name)                                                              \
  do {                                                                                    \
    static const v8::CFunction fast = v8::CFunction::Make(fastUnary<trech_dmath_##name>); \
    defineMath(ctx, math, #name, 1, slowUnary<trech_dmath_##name>, &fast);                \
  } while (0)

void installDeterministicMath(JSContext* ctx) {
  auto context = ctx->local();
  auto math = context->Global()->Get(context, keyString(ctx, "Math")).ToLocalChecked().As<v8::Object>();
  TRECH_V8_UNARY(sin);
  TRECH_V8_UNARY(cos);
  TRECH_V8_UNARY(tan);
  TRECH_V8_UNARY(asin);
  TRECH_V8_UNARY(acos);
  TRECH_V8_UNARY(atan);
  TRECH_V8_UNARY(exp);
  TRECH_V8_UNARY(expm1);
  TRECH_V8_UNARY(log);
  TRECH_V8_UNARY(log1p);
  TRECH_V8_UNARY(log2);
  TRECH_V8_UNARY(log10);
  TRECH_V8_UNARY(sinh);
  TRECH_V8_UNARY(cosh);
  TRECH_V8_UNARY(tanh);
  TRECH_V8_UNARY(asinh);
  TRECH_V8_UNARY(acosh);
  TRECH_V8_UNARY(atanh);
  TRECH_V8_UNARY(cbrt);
  static const v8::CFunction fastAtan2 = v8::CFunction::Make(fastBinary<trech_dmath_atan2>);
  defineMath(ctx, math, "atan2", 2, slowBinary<trech_dmath_atan2>, &fastAtan2);
  static const v8::CFunction fastPow = v8::CFunction::Make(fastBinary<quickJsPow>);
  defineMath(ctx, math, "pow", 2, slowBinary<quickJsPow>, &fastPow);
  static const v8::CFunction fastHypotFn = v8::CFunction::Make(fastHypot);
  defineMath(ctx, math, "hypot", 2, slowHypot, &fastHypotFn);
}
#undef TRECH_V8_UNARY

// ---- QuickJS-style stacks ------------------------------------------------------------

std::string callSiteText(v8::Local<v8::Context> context, v8::Local<v8::Object> site, const char* method) {
  v8::Isolate* isolate = v8::Isolate::GetCurrent();
  v8::Local<v8::Value> fn;
  if (!site->Get(context, newString(isolate, method)).ToLocal(&fn) || !fn->IsFunction()) return {};
  v8::Local<v8::Value> value;
  if (!fn.As<v8::Function>()->Call(context, site, 0, nullptr).ToLocal(&value) || value->IsNullOrUndefined())
    return {};
  v8::String::Utf8Value text(isolate, value);
  return *text ? *text : "";
}

v8::MaybeLocal<v8::Value> prepareStackTrace(v8::Local<v8::Context> context, v8::Local<v8::Value>,
                                            v8::Local<v8::Array> sites) {
  std::string out;
  for (std::uint32_t i = 0; i < sites->Length(); ++i) {
    v8::Local<v8::Value> entry;
    if (!sites->Get(context, i).ToLocal(&entry) || !entry->IsObject()) continue;
    const auto site = entry.As<v8::Object>();
    std::string name = callSiteText(context, site, "getFunctionName");
    std::string file = callSiteText(context, site, "getScriptNameOrSourceURL");
    const std::string line = callSiteText(context, site, "getLineNumber");
    const std::string column = callSiteText(context, site, "getColumnNumber");
    if (name.empty()) name = callSiteText(context, site, "isToplevel") == "true" ? "<eval>" : "<anonymous>";
    if (file.empty()) file = "<native>";
    out += "    at " + name + " (" + file;
    if (!line.empty()) out += ":" + line + (column.empty() ? "" : ":" + column);
    out += ")\n";
  }
  return newString(v8::Isolate::GetCurrent(), out.c_str());
}

// eval() and new Function() compile strings at run time, past JS_Eval's check. The context
// disallows code generation from strings, so V8 asks this callback, which allows any source
// without the exponent operator. A refused string throws EvalError.
v8::ModifyCodeGenerationFromStringsResult allowCodeWithoutPow(v8::Local<v8::Context>, v8::Local<v8::Value> source,
                                                              bool) {
  v8::ModifyCodeGenerationFromStringsResult result;
  if (!source->IsString()) {
    result.codegen_allowed = true;
    return result;
  }
  v8::Isolate* isolate = v8::Isolate::GetCurrent();
  v8::String::Utf8Value text(isolate, source);
  result.codegen_allowed = *text && findJsPowOperators(std::string_view(*text, text.length())).empty();
  return result;
}

}  // namespace

std::string engineVersion() { return v8::V8::GetVersion(); }

JsEnter::JsEnter(JSContext* ctx)
    : ctx_(ctx),
      locker_(ctx->isolate),
      isolateScope_(ctx->isolate),
      handles_(ctx->isolate),
      previous_(ctx->current),
      contextScope_(ctx->context.Get(ctx->isolate)) {
  ctx_->current = ctx_->isolate->GetCurrentContext();
}

JsEnter::~JsEnter() { ctx_->current = previous_; }

JSRuntime* JS_NewRuntime() {
  initializeV8Once();
  auto* rt = new JSRuntime;
  rt->allocator.reset(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
  v8::Isolate::CreateParams params;
  params.array_buffer_allocator = rt->allocator.get();
  rt->isolate = v8::Isolate::New(params);
  {
    v8::Locker locker(rt->isolate);
    rt->isolate->SetMicrotasksPolicy(v8::MicrotasksPolicy::kExplicit);
    rt->isolate->SetPrepareStackTraceCallback(prepareStackTrace);
    rt->isolate->SetModifyCodeGenerationFromStringsCallback(allowCodeWithoutPow);
  }
  return rt;
}

void JS_FreeRuntime(JSRuntime* rt) {
  if (!rt) return;
  if (rt->isolate) rt->isolate->Dispose();
  delete rt;
}

JSContext* JS_NewContext(JSRuntime* rt) {
  auto* ctx = new JSContext;
  ctx->rt = rt;
  ctx->isolate = rt->isolate;
  v8::Locker locker(ctx->isolate);
  v8::Isolate::Scope isolateScope(ctx->isolate);
  v8::HandleScope handles(ctx->isolate);
  auto context = v8::Context::New(ctx->isolate);
  ctx->context.Reset(ctx->isolate, context);
  v8::Context::Scope contextScope(context);
  context->AllowCodeGenerationFromStrings(false);
  ctx->current = context;
  auto json = context->Global()->Get(context, keyString(ctx, "JSON")).ToLocalChecked().As<v8::Object>();
  auto stringify = json->Get(context, keyString(ctx, "stringify")).ToLocalChecked().As<v8::Function>();
  ctx->jsonStringify.Reset(ctx->isolate, stringify);
  installDeterministicMath(ctx);
  ctx->current = v8::Local<v8::Context>();
  return ctx;
}

void JS_FreeContext(JSContext* ctx) {
  if (!ctx) return;
  {
    v8::Locker locker(ctx->isolate);
    v8::Isolate::Scope isolateScope(ctx->isolate);
    ctx->functions.clear();
    ctx->pending.Reset();
    ctx->jsonStringify.Reset();
    ctx->context.Reset();
  }
  delete ctx;
}

void JS_FreeCString(JSContext*, const char* text) { std::free(const_cast<char*>(text)); }

JSValue JS_NewObject(JSContext* ctx) { return JSValue(v8::Object::New(ctx->isolate)); }

JSValue JS_NewObjectProto(JSContext* ctx, JSValueConst proto) {
  return JSValue(v8::Object::New(ctx->isolate, toLocal(ctx, proto), nullptr, nullptr, 0));
}

JSValue JS_NewArray(JSContext* ctx) { return JSValue(v8::Array::New(ctx->isolate)); }

JSValue JS_NewString(JSContext* ctx, const char* text) {
  v8::Local<v8::String> out;
  if (!v8::String::NewFromUtf8(ctx->isolate, text ? text : "").ToLocal(&out))
    return JS_ThrowInternalError(ctx, "string too long");
  return JSValue(out);
}

JSValue JS_NewStringLen(JSContext* ctx, const char* text, std::size_t length) {
  v8::Local<v8::String> out;
  if (length > static_cast<std::size_t>(v8::String::kMaxLength) ||
      !v8::String::NewFromUtf8(ctx->isolate, text, v8::NewStringType::kNormal, static_cast<int>(length)).ToLocal(&out))
    return JS_ThrowInternalError(ctx, "string too long");
  return JSValue(out);
}

JSValue JS_NewFloat64(JSContext* ctx, double value) { return JSValue(v8::Number::New(ctx->isolate, value)); }
JSValue JS_NewInt32(JSContext* ctx, std::int32_t value) { return JSValue(v8::Integer::New(ctx->isolate, value)); }
JSValue JS_NewInt64(JSContext* ctx, std::int64_t value) {
  // QuickJS stores an int64 outside the int32 range as the nearest double, as does this.
  return JSValue(v8::Number::New(ctx->isolate, static_cast<double>(value)));
}

JSValue JS_NewCFunction(JSContext* ctx, JSCFunction* fn, const char* name, int length) {
  auto& slot = ctx->functions[fn];
  if (slot && !slot->function.IsEmpty()) return JSValue(slot->function.Get(ctx->isolate));
  slot = std::make_unique<JsHostFunction>();
  slot->ctx = ctx;
  slot->fn = fn;
  slot->length = length;
  v8::Local<v8::Function> function;
  if (!v8::Function::New(ctx->local(), hostTrampoline, v8::External::New(ctx->isolate, slot.get(), v8::kExternalPointerTypeTagDefault), length,
                         v8::ConstructorBehavior::kThrow).ToLocal(&function))
    return JS_ThrowInternalError(ctx, "cannot create host function %s", name);
  function->SetName(keyString(ctx, name));
  slot->function.Reset(ctx->isolate, function);
  return JSValue(function);
}

JSValue JS_GetGlobalObject(JSContext* ctx) { return JSValue(ctx->local()->Global()); }

JSValue JS_GetPropertyStr(JSContext* ctx, JSValueConst object, const char* name) {
  v8::Local<v8::Object> target;
  if (!receiver(ctx, object, &target, name)) return JS_EXCEPTION;
  v8::TryCatch caught(ctx->isolate);
  v8::Local<v8::Value> out;
  if (!target->Get(ctx->local(), keyString(ctx, name)).ToLocal(&out)) return catchInto(ctx, caught);
  return JSValue(out);
}

JSValue JS_GetPropertyUint32(JSContext* ctx, JSValueConst object, std::uint32_t index) {
  v8::Local<v8::Object> target;
  if (!receiver(ctx, object, &target, "index")) return JS_EXCEPTION;
  v8::TryCatch caught(ctx->isolate);
  v8::Local<v8::Value> out;
  if (!target->Get(ctx->local(), index).ToLocal(&out)) return catchInto(ctx, caught);
  return JSValue(out);
}

JSValue JS_GetProperty(JSContext* ctx, JSValueConst object, JSAtom atom) {
  v8::Local<v8::Object> target;
  if (!receiver(ctx, object, &target, "property")) return JS_EXCEPTION;
  v8::TryCatch caught(ctx->isolate);
  v8::Local<v8::Value> out;
  if (!target->Get(ctx->local(), atom.key).ToLocal(&out)) return catchInto(ctx, caught);
  return JSValue(out);
}

int JS_SetPropertyStr(JSContext* ctx, JSValueConst object, const char* name, JSValue value) {
  const auto local = toLocal(ctx, object);
  if (!local->IsObject()) {
    JS_ThrowTypeError(ctx, "cannot set property '%s' of a non-object", name);
    return -1;
  }
  v8::TryCatch caught(ctx->isolate);
  if (local.As<v8::Object>()->Set(ctx->local(), keyString(ctx, name), toLocal(ctx, value)).IsNothing())
    return catchStatus(ctx, caught);
  return 0;
}

int JS_SetPropertyUint32(JSContext* ctx, JSValueConst object, std::uint32_t index, JSValue value) {
  const auto local = toLocal(ctx, object);
  if (!local->IsObject()) {
    JS_ThrowTypeError(ctx, "cannot set an index of a non-object");
    return -1;
  }
  v8::TryCatch caught(ctx->isolate);
  if (local.As<v8::Object>()->Set(ctx->local(), index, toLocal(ctx, value)).IsNothing())
    return catchStatus(ctx, caught);
  return 0;
}

int JS_GetOwnPropertyNames(JSContext* ctx, JSPropertyEnum** properties, std::uint32_t* count,
                           JSValueConst object, int flags) {
  *properties = nullptr;
  *count = 0;
  const auto local = toLocal(ctx, object);
  if (!local->IsObject()) {
    JS_ThrowTypeError(ctx, "not an object");
    return -1;
  }
  const auto filter = static_cast<v8::PropertyFilter>(
      v8::SKIP_SYMBOLS | ((flags & JS_GPN_ENUM_ONLY) ? v8::ONLY_ENUMERABLE : 0));
  v8::TryCatch caught(ctx->isolate);
  v8::Local<v8::Array> names;
  if (!local.As<v8::Object>()->GetOwnPropertyNames(ctx->local(), filter, v8::KeyConversionMode::kConvertToString)
           .ToLocal(&names))
    return catchStatus(ctx, caught);
  const std::uint32_t n = names->Length();
  auto* out = new JSPropertyEnum[n > 0 ? n : 1];
  for (std::uint32_t i = 0; i < n; ++i) {
    v8::Local<v8::Value> key;
    if (!names->Get(ctx->local(), i).ToLocal(&key)) {
      delete[] out;
      return catchStatus(ctx, caught);
    }
    out[i].atom.key = key;
  }
  *properties = out;
  *count = n;
  return 0;
}

JSValue JS_AtomToString(JSContext*, JSAtom atom) { return JSValue(atom.key); }

const char* JS_AtomToCString(JSContext* ctx, JSAtom atom) { return JS_ToCString(ctx, JSValue(atom.key)); }

int JS_ToFloat64(JSContext* ctx, double* out, JSValueConst value) {
  const auto local = toLocal(ctx, value);
  if (local->IsNumber()) {
    *out = local.As<v8::Number>()->Value();
    return 0;
  }
  v8::TryCatch caught(ctx->isolate);
  if (!local->NumberValue(ctx->local()).To(out)) {
    *out = std::numeric_limits<double>::quiet_NaN();
    return catchStatus(ctx, caught);
  }
  return 0;
}

int JS_ToInt32(JSContext* ctx, std::int32_t* out, JSValueConst value) {
  v8::TryCatch caught(ctx->isolate);
  if (!toLocal(ctx, value)->Int32Value(ctx->local()).To(out)) {
    *out = 0;
    return catchStatus(ctx, caught);
  }
  return 0;
}

int JS_ToUint32(JSContext* ctx, std::uint32_t* out, JSValueConst value) {
  v8::TryCatch caught(ctx->isolate);
  if (!toLocal(ctx, value)->Uint32Value(ctx->local()).To(out)) {
    *out = 0;
    return catchStatus(ctx, caught);
  }
  return 0;
}

int JS_ToInt64(JSContext* ctx, std::int64_t* out, JSValueConst value) {
  double d = 0.0;
  if (JS_ToFloat64(ctx, &d, value) != 0) {
    *out = 0;
    return -1;
  }
  // QuickJS JS_ToInt64Free: truncate, wrap modulo 2^64 for large magnitudes, NaN/Inf -> 0.
  std::uint64_t bits = 0;
  std::memcpy(&bits, &d, sizeof bits);
  const int e = static_cast<int>((bits >> 52) & 0x7ff);
  if (e <= 1023 + 62) {
    *out = static_cast<std::int64_t>(d);
  } else if (e <= 1023 + 62 + 53) {
    std::uint64_t v = (bits & ((std::uint64_t{1} << 52) - 1)) | (std::uint64_t{1} << 52);
    v <<= (e - 1023) - 52;
    if (bits >> 63) v = ~v + 1;
    *out = static_cast<std::int64_t>(v);
  } else {
    *out = 0;
  }
  return 0;
}

int JS_ToBool(JSContext* ctx, JSValueConst value) {
  return toLocal(ctx, value)->BooleanValue(ctx->isolate) ? 1 : 0;
}

const char* JS_ToCStringLen(JSContext* ctx, std::size_t* length, JSValueConst value) {
  const auto local = toLocal(ctx, value);
  v8::Local<v8::String> text;
  if (local->IsString()) {
    text = local.As<v8::String>();
  } else {
    v8::TryCatch caught(ctx->isolate);
    if (!local->ToString(ctx->local()).ToLocal(&text)) {
      catchStatus(ctx, caught);
      return nullptr;
    }
  }
  return duplicate(ctx->isolate, text, length);
}

const char* JS_ToCString(JSContext* ctx, JSValueConst value) { return JS_ToCStringLen(ctx, nullptr, value); }

JSValue JS_ParseJSON(JSContext* ctx, const char* text, std::size_t length, const char*) {
  if (length > static_cast<std::size_t>(v8::String::kMaxLength))
    return JS_ThrowInternalError(ctx, "JSON text too long");
  v8::TryCatch caught(ctx->isolate);
  v8::Local<v8::String> source;
  v8::Local<v8::Value> out;
  if (!v8::String::NewFromUtf8(ctx->isolate, text, v8::NewStringType::kNormal, static_cast<int>(length))
           .ToLocal(&source) ||
      !v8::JSON::Parse(ctx->local(), source).ToLocal(&out))
    return catchInto(ctx, caught);
  return JSValue(out);
}

JSValue JS_JSONStringify(JSContext* ctx, JSValueConst value, JSValueConst replacer, JSValueConst space) {
  v8::Local<v8::Value> args[3] = {toLocal(ctx, value), toLocal(ctx, replacer), toLocal(ctx, space)};
  v8::TryCatch caught(ctx->isolate);
  v8::Local<v8::Value> out;
  if (!ctx->jsonStringify.Get(ctx->isolate)->Call(ctx->local(), v8::Undefined(ctx->isolate), 3, args).ToLocal(&out))
    return catchInto(ctx, caught);
  return JSValue(out);
}

JSValue JS_Eval(JSContext* ctx, const char* code, std::size_t length, const char* filename, int) {
  const std::string_view source(code, length);
  const auto pow = findJsPowOperators(source);
  if (!pow.empty()) {
    return JS_ThrowSyntaxError(
        ctx,
        "%s:%d:%d: the `**` operator is not supported by TRECH's V8 backend: V8 evaluates it "
        "with its own pow, not trech_dmath, so results would not replay QuickJS bit for bit. "
        "Write Math.pow(a, b) (scripts/check_js_pow_operator.py lists every use)",
        filename, pow.front().first, pow.front().second);
  }
  if (length > static_cast<std::size_t>(v8::String::kMaxLength))
    return JS_ThrowInternalError(ctx, "script too long");
  v8::TryCatch caught(ctx->isolate);
  auto context = ctx->local();
  v8::Local<v8::String> text;
  if (!v8::String::NewFromUtf8(ctx->isolate, code, v8::NewStringType::kNormal, static_cast<int>(length)).ToLocal(&text))
    return catchInto(ctx, caught);
  v8::ScriptOrigin origin(newString(ctx->isolate, filename));
  v8::Local<v8::Script> script;
  if (!v8::Script::Compile(context, text, &origin).ToLocal(&script)) {
    // A compile error has no frames; record its location the way QuickJS's stack shows it.
    auto message = caught.Message();
    if (caught.HasCaught() && caught.Exception()->IsObject() && !message.IsEmpty()) {
      const int line = message->GetLineNumber(context).FromMaybe(0);
      const int column = message->GetStartColumn(context).FromMaybe(0) + 1;
      const std::string stack = std::string("    at ") + filename + ":" + std::to_string(line) + ":" +
                                std::to_string(column) + "\n";
      (void)caught.Exception().As<v8::Object>()->Set(context, keyString(ctx, "stack"),
                                                     newString(ctx->isolate, stack.c_str()));
    }
    return catchInto(ctx, caught);
  }
  v8::Local<v8::Value> out;
  if (!script->Run(context).ToLocal(&out)) return catchInto(ctx, caught);
  return JSValue(out);
}

JSValue JS_Call(JSContext* ctx, JSValueConst function, JSValueConst thisValue, int argc, JSValueConst* argv) {
  const auto callee = toLocal(ctx, function);
  if (!callee->IsFunction()) return JS_ThrowTypeError(ctx, "not a function");
  JSValue none;
  std::vector<v8::Local<v8::Value>> args(static_cast<std::size_t>(argc > 0 ? argc : 0));
  for (int i = 0; i < argc; ++i) args[static_cast<std::size_t>(i)] = toLocal(ctx, argv ? argv[i] : none);
  v8::TryCatch caught(ctx->isolate);
  v8::Local<v8::Value> out;
  if (!callee.As<v8::Function>()->Call(ctx->local(), toLocal(ctx, thisValue), argc, args.data()).ToLocal(&out))
    return catchInto(ctx, caught);
  return JSValue(out);
}

JSValue JS_GetException(JSContext* ctx) {
  if (ctx->pending.IsEmpty()) return JS_NULL;
  JSValue out(ctx->pending.Get(ctx->isolate));
  ctx->pending.Reset();
  return out;
}

#define TRECH_V8_THROW(fn, maker, name)                           \
  JSValue fn(JSContext* ctx, const char* format, ...) {           \
    va_list args;                                                 \
    va_start(args, format);                                       \
    JSValue out = throwError(ctx, maker, name, format, args);     \
    va_end(args);                                                 \
    return out;                                                   \
  }
TRECH_V8_THROW(JS_ThrowTypeError, v8::Exception::TypeError, nullptr)
TRECH_V8_THROW(JS_ThrowRangeError, v8::Exception::RangeError, nullptr)
TRECH_V8_THROW(JS_ThrowReferenceError, v8::Exception::ReferenceError, nullptr)
TRECH_V8_THROW(JS_ThrowSyntaxError, v8::Exception::SyntaxError, nullptr)
TRECH_V8_THROW(JS_ThrowInternalError, v8::Exception::Error, "InternalError")
#undef TRECH_V8_THROW

}  // namespace trech::v8engine
