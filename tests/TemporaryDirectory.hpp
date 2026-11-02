#pragma once

#include <atomic>
#include <chrono>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <system_error>

namespace trech::test {

// Reserve the directory atomically: a timestamp alone does not isolate test
// processes started concurrently, including binaries from different build trees.
class TemporaryDirectory {
 public:
  explicit TemporaryDirectory(const std::string& prefix = "trech-test") {
    static std::atomic<unsigned long long> sequence{0};
    const auto root = std::filesystem::temp_directory_path();
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    for (unsigned attempt = 0; attempt < 256; ++attempt) {
      const auto candidate = root / (prefix + "-" + std::to_string(stamp) + "-" +
          std::to_string(sequence.fetch_add(1, std::memory_order_relaxed)));
      std::error_code error;
      if (std::filesystem::create_directory(candidate, error)) {
        path_ = candidate;
        return;
      }
      if (error && error != std::errc::file_exists)
        throw std::filesystem::filesystem_error("Could not create test directory", candidate, error);
    }
    throw std::runtime_error("Could not reserve a unique test directory");
  }

  ~TemporaryDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  TemporaryDirectory(const TemporaryDirectory&) = delete;
  TemporaryDirectory& operator=(const TemporaryDirectory&) = delete;

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

}  // namespace trech::test
