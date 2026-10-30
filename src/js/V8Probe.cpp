// Optional embedding foundation. This is not the TRECH hook backend: it has no
// Geant4, TRECH_INCLUDE, inference registry, subprocess or Studio access.
#include <libplatform/libplatform.h>
#include <v8.h>

#include <nlohmann/json.hpp>

#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {
std::string errorText(v8::Isolate* isolate, v8::TryCatch& caught) {
  v8::String::Utf8Value message(isolate, caught.Exception());
  return *message ? *message : "V8 evaluation failed";
}

std::string evaluate(v8::Isolate* isolate, const std::string& code,
                     const std::string& filename,
                     const v8::ScriptCompiler::CachedData* inputCache,
                     std::unique_ptr<v8::ScriptCompiler::CachedData>& outputCache) {
  v8::HandleScope handles(isolate);
  auto context = v8::Context::New(isolate);
  v8::Context::Scope entered(context);
  v8::TryCatch caught(isolate);
  v8::Local<v8::String> source, name;
  if (!v8::String::NewFromUtf8(isolate, code.c_str()).ToLocal(&source) ||
      !v8::String::NewFromUtf8(isolate, filename.c_str()).ToLocal(&name))
    throw std::runtime_error("V8 source allocation failed");
  v8::ScriptCompiler::Source scriptSource(source, v8::ScriptOrigin(name),
      inputCache ? new v8::ScriptCompiler::CachedData(inputCache->data, inputCache->length,
          v8::ScriptCompiler::CachedData::BufferNotOwned) : nullptr);
  v8::Local<v8::UnboundScript> script;
  if (!v8::ScriptCompiler::CompileUnboundScript(isolate, &scriptSource,
      inputCache ? v8::ScriptCompiler::kConsumeCodeCache : v8::ScriptCompiler::kNoCompileOptions).ToLocal(&script))
    throw std::runtime_error(errorText(isolate, caught));
  if (inputCache && scriptSource.GetCachedData()->rejected)
    throw std::runtime_error("V8 rejected its in-process code cache");
  v8::Local<v8::Value> value;
  if (!script->BindToCurrentContext()->Run(context).ToLocal(&value))
    throw std::runtime_error(errorText(isolate, caught));
  v8::Local<v8::String> json;
  if (!v8::JSON::Stringify(context, value).ToLocal(&json))
    throw std::runtime_error("Script completion must be JSON-serializable");
  v8::String::Utf8Value encoded(isolate, json);
  if (!*encoded) throw std::runtime_error("V8 result encoding failed");
  if (!inputCache) {
    outputCache.reset(v8::ScriptCompiler::CreateCodeCache(script));
    if (!outputCache || outputCache->length == 0)
      throw std::runtime_error("V8 did not produce a code cache");
  }
  return *encoded;
}
} // namespace

int main(int argc, char** argv) {
  std::string code = "(() => { const square = x => x*x; return {sum: [1,2,3,4].map(square).reduce((a,b) => a+b, 0)}; })()";
  std::string filename = "<trech-v8-smoke>";
  if (argc > 2) {std::cerr << "Usage: trech-v8-probe [pure-script.js]\n"; return 2;}
  if (argc == 2) {
    filename = argv[1];
    std::ifstream file(filename);
    if (!file) {std::cerr << "Cannot open " << filename << '\n'; return 2;}
    std::ostringstream buffer; buffer << file.rdbuf(); code = buffer.str();
  }
  auto platform = v8::platform::NewDefaultPlatform();
  v8::V8::InitializePlatform(platform.get());
  if (!v8::V8::Initialize()) {std::cerr << "V8 initialization failed\n"; return 1;}
  std::unique_ptr<v8::ArrayBuffer::Allocator> allocator(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
  v8::Isolate::CreateParams params;
  params.array_buffer_allocator = allocator.get();
  auto* isolate = v8::Isolate::New(params);
  int status = 0;
  {
    v8::Isolate::Scope entered(isolate);
    try {
      std::unique_ptr<v8::ScriptCompiler::CachedData> cache, unused;
      const auto cold = evaluate(isolate, code, filename, nullptr, cache);
      const auto warm = evaluate(isolate, code, filename, cache.get(), unused);
      if (cold != warm) throw std::runtime_error("Cold and cached results differ");
      if (argc == 1 && nlohmann::json::parse(cold).at("sum") != 30)
        throw std::runtime_error("V8 smoke result differs");
      std::cout << nlohmann::json({{"runtime", v8::V8::GetVersion()}, {"code_cache_bytes", cache->length},
          {"cached_result_matches", true}, {"result", nlohmann::json::parse(cold)}}).dump() << '\n';
    } catch (const std::exception& error) {std::cerr << error.what() << '\n'; status = 1;}
  }
  isolate->Dispose();
  v8::V8::Dispose();
  v8::V8::DisposePlatform();
  return status;
}
