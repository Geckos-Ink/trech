#pragma once

#include <string>

namespace trech {

class JsRuntime {
public:
  JsRuntime();
  ~JsRuntime();

  std::string evalExperimentAndGetConfigJson(const std::string& path);

private:
  struct Impl;
  Impl* impl_ = nullptr;
};

} // namespace trech
