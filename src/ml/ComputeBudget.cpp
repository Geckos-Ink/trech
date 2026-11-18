#include "trech/ml/ComputeBudget.hpp"

#include <ATen/ATen.h>
#include <ATen/Parallel.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <thread>

#if defined(__APPLE__)
#include <sys/sysctl.h>
#include <sys/types.h>
#elif defined(__unix__)
#include <unistd.h>
#endif

namespace trech::ml {
namespace {

double physicalMemory() {
#if defined(__APPLE__)
  std::uint64_t bytes = 0;
  std::size_t size = sizeof(bytes);
  if (sysctlbyname("hw.memsize", &bytes, &size, nullptr, 0) == 0) return static_cast<double>(bytes);
#elif defined(__unix__)
  const long pages = sysconf(_SC_PHYS_PAGES);
  const long page = sysconf(_SC_PAGE_SIZE);
  if (pages > 0 && page > 0) return static_cast<double>(pages) * static_cast<double>(page);
#endif
  return 0.0;
}

// Median of three timed 256x256 double matmuls; the first call warms up.
double measureGflops() {
  constexpr int64_t n = 256;
  const auto options = at::TensorOptions().dtype(at::kDouble).device(at::kCPU);
  const auto a = at::linspace(-1.0, 1.0, n * n, options).reshape({n, n});
  const auto b = a.t().contiguous();
  auto c = a.mm(b);
  double samples[3] = {0.0, 0.0, 0.0};
  for (double& seconds : samples) {
    const auto start = std::chrono::steady_clock::now();
    for (int r = 0; r < 4; ++r) c = a.mm(b);
    seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count() / 4.0;
  }
  std::sort(samples, samples + 3);
  const double flops = 2.0 * static_cast<double>(n * n * n);
  return samples[1] > 0.0 ? flops / samples[1] / 1e9 : 0.0;
}

ComputeBudget probe() {
  ComputeBudget budget;
  budget.hardwareThreads = std::max(1u, std::thread::hardware_concurrency());
  budget.torchThreads = static_cast<std::size_t>(std::max(1, at::get_num_threads()));
  budget.memoryBytes = physicalMemory();
  budget.gflops = measureGflops();
  budget.source = "probe";
  return budget;
}

}  // namespace

nlohmann::json ComputeBudget::toJson() const {
  return {{"schema", "trech_compute_budget_v1"},
          {"hardware_threads", hardwareThreads},
          {"torch_threads", torchThreads},
          {"memory_bytes", memoryBytes},
          {"gflops", gflops},
          {"memory_fraction", memoryFraction},
          {"seconds_per_call", secondsPerCall},
          {"source", source}};
}

ComputeBudget ComputeBudget::fromJson(const nlohmann::json& value) {
  if (!value.is_object()) throw std::invalid_argument("compute budget must be an object");
  ComputeBudget budget;
  auto number = [&](const char* key, double fallback, double low) {
    if (!value.contains(key)) return fallback;
    const auto& entry = value.at(key);
    if (!entry.is_number() || !std::isfinite(entry.get<double>()) || entry.get<double>() < low) {
      throw std::invalid_argument(std::string("compute budget ") + key + " must be a finite number >= " +
                                  std::to_string(low));
    }
    return entry.get<double>();
  };
  budget.hardwareThreads = static_cast<std::size_t>(number("hardware_threads", 1.0, 1.0));
  budget.torchThreads = static_cast<std::size_t>(number("torch_threads", 1.0, 1.0));
  budget.memoryBytes = number("memory_bytes", 0.0, 0.0);
  budget.gflops = number("gflops", 1.0, 0.0);
  budget.memoryFraction = number("memory_fraction", budget.memoryFraction, 0.0);
  budget.secondsPerCall = number("seconds_per_call", budget.secondsPerCall, 0.0);
  budget.source = value.value("source", std::string("override"));
  return budget;
}

nlohmann::json LearnerCapacity::toJson() const {
  return {{"max_domains", maxDomains},
          {"buffer_rows", bufferRows},
          {"split_candidates", splitCandidates},
          {"basis_degree", basisDegree},
          {"residual_hidden", residualHidden},
          {"residual_steps", residualSteps},
          {"specialist_width", specialistWidth},
          {"specialist_epochs", specialistEpochs}};
}

const ComputeBudget& hostComputeBudget() {
  static std::once_flag once;
  static ComputeBudget budget;
  std::call_once(once, [] {
    if (const char* env = std::getenv("TRECH_COMPUTE_BUDGET"); env && *env) {
      std::string text(env);
      if (text.front() != '{') {
        std::ifstream file(text);
        if (!file) throw std::runtime_error("TRECH_COMPUTE_BUDGET: cannot open " + text);
        text.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
      }
      budget = ComputeBudget::fromJson(nlohmann::json::parse(text));
      budget.source = "env";
    } else {
      budget = probe();
    }
  });
  return budget;
}

LearnerCapacity learnerCapacity(const ComputeBudget& budget, std::size_t features,
                                std::size_t targets) {
  LearnerCapacity capacity;
  const double d = static_cast<double>(std::max<std::size_t>(features, 1));
  const double t = static_cast<double>(std::max<std::size_t>(targets, 1));
  // Work per call: every buffered row of every domain is refit and scored
  // across split candidates, ~ rows * p^2 * directions flops.
  const double quadratic = 1.0 + d + d * (d + 1.0) / 2.0;
  capacity.basisDegree = (quadratic <= 64.0 && budget.gflops >= 0.5) ? 2 : 1;
  const double p = capacity.basisDegree == 2 ? quadratic : 1.0 + d;
  const double flopsPerCall = std::max(budget.gflops, 0.05) * 1e9 * budget.secondsPerCall;
  const double rowBytes = 8.0 * (d + t + 2.0);
  const double memoryRows = budget.memoryBytes > 0.0
      ? budget.memoryBytes * budget.memoryFraction / rowBytes
      : 1.0e6;
  // Total buffered rows: bounded by memory and by one call's refit work.
  // Scalar loops, sorting and small-tensor overhead run far below the
  // matmul rate: assume a tenth of it.
  const double workRows = 0.1 * flopsPerCall / (p * p * (d + 4.0) * 4.0);
  const double totalRows = std::clamp(std::min(memoryRows, workRows), 2048.0, 1.0e6);
  capacity.maxDomains = static_cast<std::size_t>(
      std::clamp(std::floor(std::log2(totalRows / 256.0)) * 3.0, 4.0, 32.0));
  capacity.bufferRows = static_cast<std::size_t>(
      std::clamp(totalRows / static_cast<double>(capacity.maxDomains), 512.0, 65536.0));
  capacity.splitCandidates = budget.gflops >= 2.0 ? 48 : 24;
  // A residual network is worth its cost only with spare throughput.
  if (budget.gflops >= 4.0 && budget.hardwareThreads >= 4) {
    capacity.residualHidden = budget.gflops >= 20.0 ? 32 : 16;
    capacity.residualSteps = budget.gflops >= 20.0 ? 24 : 12;
  }
  // Offline specialists: width grows with throughput, epochs with threads.
  capacity.specialistWidth = budget.gflops >= 20.0 ? 64 : budget.gflops >= 4.0 ? 32 : 16;
  // A wider network needs at least as many optimisation steps, so epochs
  // grow with throughput too (sqrt: a faster host spends part of its gain on
  // width). Measured on the atomic photon-table study: 1200 epochs at width 64
  // under-trained two of three targets.
  capacity.specialistEpochs = static_cast<std::size_t>(
      std::clamp(200.0 * std::sqrt(std::max(budget.gflops, 0.25)), 600.0, 6000.0));
  return capacity;
}

}  // namespace trech::ml
