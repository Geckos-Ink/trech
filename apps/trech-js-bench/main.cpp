// trech-js-bench: time scenario evaluation and hook dispatch on each JavaScript engine.
//
//   trech-js-bench [--dispatches N] [--hook NAME] [--engine quickjs|v8|both] [scenario.js]
//
// Without a scenario it runs a built-in hook workload: a small Lennard-Jones particle step
// in onStep (pure JavaScript arithmetic, Math.sqrt/exp, state kept across dispatches) and a
// trivial onEventStart that measures the fixed cost of building ctx and calling the hook.
// With a scenario it evaluates the file and dispatches the chosen hook (default onStep) with a
// synthetic context; hooks that need Geant4 material probes or other run facts may throw.
// Prints one JSON object per engine. Geant4 is not involved.
#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace {

constexpr const char* kWorkload = R"JS(
const N = TRECH_VALUE.integer("particles", { default: 96, min: 8, max: 4096 });
globalThis.TRECH_CONFIG = { run: { nEvents: 1, seed: 7 }, determinism: { mode: "strict" } };
function init() {
  const s = { x: [], y: [], vx: [], vy: [] };
  const side = Math.ceil(Math.sqrt(N));
  for (let i = 0; i < N; i++) {
    s.x.push((i % side) * 1.12); s.y.push(Math.floor(i / side) * 1.12);
    s.vx.push(0); s.vy.push(0);
  }
  return s;
}
globalThis.TRECH_HOOKS = {
  onEventStart(ctx) { return null; },
  onStep(ctx) {
    const s = __TRECH_HOOK_STATE.p || (__TRECH_HOOK_STATE.p = init());
    const dt = 1e-3, x = s.x, y = s.y, vx = s.vx, vy = s.vy;
    let energy = 0;
    for (let i = 0; i < N; i++) {
      let fx = 0, fy = 0;
      for (let j = 0; j < N; j++) {
        if (i === j) continue;
        const dx = x[i] - x[j], dy = y[i] - y[j];
        const r2 = dx * dx + dy * dy;
        if (r2 > 6.25) continue;
        const inv6 = 1 / (r2 * r2 * r2);
        const f = (48 * inv6 * inv6 - 24 * inv6) / r2;
        fx += f * dx; fy += f * dy;
        energy += 4 * (inv6 * inv6 - inv6) * Math.exp(-r2 * 1e-3);
      }
      vx[i] += fx * dt; vy[i] += fy * dt;
    }
    for (let i = 0; i < N; i++) { x[i] += vx[i] * dt; y[i] += vy[i] * dt; }
    __TRECH_HOOK_STATE.energy = energy + ctx.step.edepMeV * 0;
  },
};
)JS";

double seconds(std::chrono::steady_clock::duration d) {
  return std::chrono::duration<double>(d).count();
}

nlohmann::json bench(trech::JsEngine engine, const std::string& path, const std::vector<std::string>& hooks,
                     int dispatches) {
  using clock = std::chrono::steady_clock;
  nlohmann::json out = {{"engine", trech::jsEngineName(engine)}};
  const auto t0 = clock::now();
  trech::JsRuntime js(engine);
  const auto t1 = clock::now();
  const auto config = trech::configFromJsonString(js.evalExperimentAndGetConfigJson(path));
  const auto t2 = clock::now();
  out["identity"] = js.engineIdentity();
  out["create_ms"] = 1e3 * seconds(t1 - t0);
  out["evaluate_ms"] = 1e3 * seconds(t2 - t1);
  for (const auto& hook : hooks) {
    trech::HookRuntimeContext context;
    context.seed = config.run.seed;
    context.nEvents = config.run.nEvents;
    context.determinismMode = config.determinism.mode;
    context.eventId = 0;
    context.stepIndex = 0;
    context.stepEdepMeV = 0.25;
    context.stepLengthMm = 0.1;
    const auto start = clock::now();
    for (int i = 0; i < dispatches; ++i) {
      context.stepIndex = i;
      js.dispatchHook(hook, context, nullptr, false);
    }
    const auto elapsed = seconds(clock::now() - start);
    js.takeEmittedRecords();
    out["hooks"][hook] = {{"dispatches", dispatches}, {"us_per_dispatch", 1e6 * elapsed / dispatches}};
  }
  return out;
}

}  // namespace

int main(int argc, char** argv) {
  int dispatches = 2000;
  std::string hook;
  std::string engineArg = "both";
  std::string scenario;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--dispatches" && i + 1 < argc) {
      dispatches = std::max(1, std::atoi(argv[++i]));
    } else if (arg == "--hook" && i + 1 < argc) {
      hook = argv[++i];
    } else if (arg == "--engine" && i + 1 < argc) {
      engineArg = argv[++i];
    } else if (arg == "-h" || arg == "--help") {
      std::cout << "Usage: trech-js-bench [--dispatches N] [--hook NAME] [--engine quickjs|v8|both] [scenario.js]\n";
      return 0;
    } else if (!arg.empty() && arg[0] != '-' && scenario.empty()) {
      scenario = arg;
    } else {
      std::cerr << "trech-js-bench: unknown argument " << arg << "\n";
      return 2;
    }
  }
  std::vector<std::string> hooks;
  std::string path = scenario;
  std::filesystem::path scratch;
  if (scenario.empty()) {
    scratch = std::filesystem::temp_directory_path() / "trech_js_bench_workload.js";
    std::ofstream(scratch) << kWorkload;
    path = scratch.string();
    hooks = hook.empty() ? std::vector<std::string>{"onEventStart", "onStep"} : std::vector<std::string>{hook};
  } else {
    hooks = {hook.empty() ? std::string("onStep") : hook};
  }
  std::vector<trech::JsEngine> engines;
  if (engineArg == "both") {
    engines.push_back(trech::JsEngine::QuickJs);
    if (trech::JsRuntime::engineAvailable(trech::JsEngine::V8)) engines.push_back(trech::JsEngine::V8);
  } else {
    engines.push_back(trech::parseJsEngine(engineArg));
  }
  int status = 0;
  for (const auto engine : engines) {
    try {
      std::cout << bench(engine, path, hooks, dispatches).dump() << "\n";
    } catch (const std::exception& error) {
      std::cerr << trech::jsEngineName(engine) << ": " << error.what() << "\n";
      status = 1;
    }
  }
  if (!scratch.empty()) std::filesystem::remove(scratch);
  return status;
}
