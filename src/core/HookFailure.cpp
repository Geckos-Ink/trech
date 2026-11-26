#include "trech/core/HookFailure.hpp"

#include <atomic>
#include <mutex>

namespace trech::hookfailure {
namespace {

std::mutex& latchMutex() {
  static std::mutex mutex;
  return mutex;
}

std::atomic<bool>& latchFlag() {
  static std::atomic<bool> flag{false};
  return flag;
}

std::string& latchText() {
  static std::string text;
  return text;
}

} // namespace

bool record(const std::string& hookName, const std::string& message) {
  std::lock_guard<std::mutex> lock(latchMutex());
  if (latchFlag().load()) {
    return false;
  }
  latchText() = "hook " + hookName + " threw: " + message;
  latchFlag().store(true);
  return true;
}

bool failed() {
  return latchFlag().load();
}

std::string describe() {
  std::lock_guard<std::mutex> lock(latchMutex());
  return latchFlag().load() ? latchText() : std::string();
}

void reset() {
  std::lock_guard<std::mutex> lock(latchMutex());
  latchText().clear();
  latchFlag().store(false);
}

} // namespace trech::hookfailure
