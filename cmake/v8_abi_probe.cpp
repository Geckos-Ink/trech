// Configure-time probe (cmake/TrechV8.cmake): exits 0 only when the compile definitions it was
// built with match the V8 library's build configuration. V8::Initialize aborts the process on
// a pointer-compression, Smi-size or sandbox mismatch, which try_run reports as a failure.
#include <libplatform/libplatform.h>
#include <v8.h>

#include <cstdio>
#include <memory>
#include <string>

int main() {
  auto platform = v8::platform::NewDefaultPlatform();
  v8::V8::InitializePlatform(platform.get());
  if (!v8::V8::Initialize()) return 1;
  std::unique_ptr<v8::ArrayBuffer::Allocator> allocator(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
  v8::Isolate::CreateParams params;
  params.array_buffer_allocator = allocator.get();
  v8::Isolate* isolate = v8::Isolate::New(params);
  int status = 1;
  {
    v8::Isolate::Scope entered(isolate);
    v8::HandleScope handles(isolate);
    auto context = v8::Context::New(isolate);
    v8::Context::Scope scope(context);
    auto source = v8::String::NewFromUtf8Literal(isolate, "[1, 2, 3].map(x => x * x).join(',')");
    v8::Local<v8::Value> result;
    if (v8::Script::Compile(context, source).ToLocalChecked()->Run(context).ToLocal(&result)) {
      v8::String::Utf8Value text(isolate, result);
      status = (*text && std::string(*text) == "1,4,9") ? 0 : 1;
      std::printf("%s\n", v8::V8::GetVersion());
    }
  }
  isolate->Dispose();
  v8::V8::Dispose();
  v8::V8::DisposePlatform();
  return status;
}
