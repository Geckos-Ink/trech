// QuickJS vs V8: the same scenario and hook calls must produce the same bytes on both
// engines (built only with TRECH_ENABLE_V8). The rest of the JavaScript suite runs on V8
// through its `_v8` CTest twins (TRECH_JS_ENGINE=v8).
#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"
#include "TemporaryDirectory.hpp"

#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>

namespace {

int failures = 0;

void expect(bool condition, const std::string& message) {
  if (!condition) {
    ++failures;
    std::cerr << "FAIL: " << message << "\n";
  }
}

void write(const std::filesystem::path& path, const std::string& text) {
  std::ofstream out(path);
  out << text;
}

// Everything observable from one engine for one scenario and a fixed hook sequence.
struct Transcript {
  std::string config;
  std::string parameters;
  std::string authoring;
  std::vector<std::string> hooks;  // report + emits + patched config per dispatch
  std::string error;
};

Transcript transcript(trech::JsEngine engine, const std::filesystem::path& scenario,
                      const std::vector<std::string>& overrides = {}) {
  Transcript out;
  try {
    trech::JsRuntime js(engine);
    js.setScriptParameterOverrides(overrides);
    out.config = js.evalExperimentAndGetConfigJson(scenario.string());
    out.parameters = js.scriptParametersJson();
    out.authoring = js.authoringMetadataJson();
    auto cfg = trech::configFromJsonString(out.config);
    const char* sequence[] = {"onInit", "onRunStart", "onEventStart", "onStep", "onStep",
                              "onEventEnd", "onEventStart", "onStep", "onEventEnd", "onRunEnd"};
    int event = -1;
    int step = 0;
    for (const char* hook : sequence) {
      trech::HookRuntimeContext context;
      context.seed = cfg.run.seed;
      context.nEvents = cfg.run.nEvents;
      context.determinismMode = cfg.determinism.mode;
      if (std::string(hook) == "onEventStart") ++event, step = 0;
      context.eventId = event;
      context.stepIndex = std::string(hook) == "onStep" ? step++ : -1;
      context.stepEdepMeV = 0.125 * (step + 1) + event;
      context.stepLengthMm = 0.5 + 0.25 * step;
      context.eventEdepMeV = 1.5 + event;
      context.runId = 0;
      const auto report = js.dispatchHook(hook, context, &cfg, std::string(hook) == "onInit");
      nlohmann::json record = {{"hook", hook},
                               {"invoked", report.invoked},
                               {"patched", report.patchedPaths},
                               {"ignored", report.ignoredPatchPaths},
                               {"emit_count", report.emitCount},
                               {"dropped", report.emitDroppedCount},
                               {"predict", report.predictCount}};
      for (const auto& emit : js.takeEmittedRecords())
        record["emits"].push_back({emit.tag, emit.payloadJson, emit.eventId, emit.stepIndex});
      record["config"] = trech::configToJsonString(cfg);
      out.hooks.push_back(record.dump());
    }
  } catch (const std::exception& error) {
    out.error = error.what();
  }
  return out;
}

void compare(const std::string& label, const Transcript& q, const Transcript& v) {
  // Messages must match; stack frames are each engine's own (names, columns of a call).
  const auto firstLine = [](const std::string& text) { return text.substr(0, text.find('\n')); };
  expect(firstLine(q.error) == firstLine(v.error),
         label + ": errors differ:\n  quickjs: " + q.error + "\n  v8: " + v.error);
  expect(q.config == v.config, label + ": config JSON differs");
  expect(q.parameters == v.parameters, label + ": TRECH_VALUE parameters differ");
  expect(q.authoring == v.authoring, label + ": authoring metadata differs");
  expect(q.hooks.size() == v.hooks.size(), label + ": hook transcript length differs");
  for (std::size_t i = 0; i < q.hooks.size() && i < v.hooks.size(); ++i)
    expect(q.hooks[i] == v.hooks[i], label + ": dispatch " + std::to_string(i) + " differs:\n  quickjs: " +
                                         q.hooks[i] + "\n  v8: " + v.hooks[i]);
}

constexpr const char* kHookScenario = R"JS(
const amplitude = TRECH_VALUE.number("amplitude", { default: 0.75, min: 0, max: 4 });
const grid = [];
for (let i = -12; i <= 12; i++) grid.push(i * 0.37 + 1e-3 * i * i);
const math = {};
for (const name of ["sin", "cos", "tan", "exp", "expm1", "log1p", "atan", "sinh", "cosh", "tanh",
                    "asinh", "cbrt"]) {
  math[name] = grid.map((x) => Math[name](x));
}
math.log = grid.map((x) => Math.log(Math.abs(x) + 1e-9));
math.pow = grid.map((x) => Math.pow(Math.abs(x) + 0.5, 0.5 + x / 7));
math.hypot = grid.map((x) => Math.hypot(x, x / 3, 1));
math.atan2 = grid.map((x) => Math.atan2(x, 1 - x));
math.special = [Math.pow(1, Infinity), Math.pow(-1, NaN), Math.hypot(), Math.hypot(-3), Math.exp("1"),
                Math.sin(undefined), String(0.1 + 0.2), (1e21).toString(), (123.456).toFixed(2),
                JSON.stringify({ a: -0, b: [1e-7, 5e-324] })];
globalThis.TRECH_CONFIG = {
  run: { nEvents: 2, seed: 4242 },
  determinism: { mode: "strict" },
  notes: { math, amplitude, keys: Object.keys({ b: 1, a: 2, 10: 3, 2: 4 }) },
};
globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    const draws = [ctx.rng.uniform(), ctx.rng.int(-5, 5), ctx.rng.normal(1, 2), ctx.rng.normal()];
    ctx.emit("init", { draws, seed: ctx.runtime.seed, mode: ctx.runtime.mode });
    __TRECH_HOOK_STATE.total = 0;
    return { override: { run: { nEvents: 3 }, unknown: { key: 1 } } };
  },
  onEventStart(ctx) { ctx.emit("event", { id: ctx.event.id, u: ctx.rng.uniform() }); },
  onStep(ctx) {
    __TRECH_HOOK_STATE.total += ctx.step.edepMeV * amplitude;
    ctx.emit("step", { e: Math.exp(-ctx.step.stepLengthMm) * ctx.step.edepMeV, n: ctx.rng.normal(0, 0.1) });
  },
  onEventEnd(ctx) { ctx.emit("event_end", { total: __TRECH_HOOK_STATE.total, keys: Object.keys(ctx) }); },
  onRunEnd(ctx) { ctx.emit("run_end", { total: __TRECH_HOOK_STATE.total }); },
};
)JS";

}  // namespace

int main() {
  namespace fs = std::filesystem;
  using trech::JsEngine;
  const trech::test::TemporaryDirectory fixture("trech_js_engine_parity");

  expect(trech::JsRuntime::engineAvailable(JsEngine::QuickJs), "QuickJS must always be available");
  expect(trech::JsRuntime::engineAvailable(JsEngine::V8), "V8 must be available in a TRECH_ENABLE_V8 build");
  expect(trech::parseJsEngine("v8") == JsEngine::V8 && trech::parseJsEngine("quickjs") == JsEngine::QuickJs,
         "engine names must parse");
  {
    trech::JsRuntime v8(JsEngine::V8);
    trech::JsRuntime qjs(JsEngine::QuickJs);
    expect(v8.engine() == JsEngine::V8 && v8.engineIdentity().rfind("v8 ", 0) == 0,
           "V8 identity: " + v8.engineIdentity());
    expect(qjs.engineIdentity().rfind("quickjs ", 0) == 0, "QuickJS identity: " + qjs.engineIdentity());
  }

  // 1. Scenario evaluation, TRECH_VALUE, Math, RNG, emits, state and overrides.
  const auto hooks = fixture.path() / "parity_hooks.js";
  write(hooks, kHookScenario);
  compare("hook scenario", transcript(JsEngine::QuickJs, hooks), transcript(JsEngine::V8, hooks));
  compare("hook scenario with override", transcript(JsEngine::QuickJs, hooks, {"amplitude=2.5"}),
          transcript(JsEngine::V8, hooks, {"amplitude=2.5"}));
  {
    const auto v8 = transcript(JsEngine::V8, hooks);
    expect(v8.error.empty() && v8.hooks.size() == 10, "V8 hook transcript must run: " + v8.error);
  }

  // 2. Repository scenarios: identical configs, parameters and authoring metadata.
  const fs::path root = TRECH_SOURCE_DIR;
  for (const char* scenario : {"examples/scenarios/config_hook_dispatch/config_hook_dispatch.js",
                               "examples/scenarios/glass_from_sand/glass_from_sand.js",
                               "examples/scenarios/lava_lamp/lava_lamp.js",
                               "examples/scenarios/aerodynamics_reference/aerodynamics_reference.js"}) {
    compare(scenario, transcript(JsEngine::QuickJs, root / scenario), transcript(JsEngine::V8, root / scenario));
  }

  // 3. The `**` operator: QuickJS accepts it; V8 refuses it with its location.
  const auto pow = fixture.path() / "pow_operator.js";
  write(pow, "var base = 3;\nglobalThis.TRECH_CONFIG = { run: { nEvents: base ** 2 } };\n");
  expect(transcript(JsEngine::QuickJs, pow).error.empty(), "QuickJS must accept `**`");
  const auto refused = transcript(JsEngine::V8, pow).error;
  expect(refused.find("pow_operator.js:2:50") != std::string::npos && refused.find("Math.pow") != std::string::npos,
         "V8 must refuse `**` with its location: " + refused);
  const auto powEval = fixture.path() / "pow_eval.js";
  write(powEval, "var n = eval('2 * 3') + new Function('return 1')();\n"
                 "var refused = false;\n"
                 "try { eval('2 ** 3'); } catch (e) { refused = e instanceof EvalError; }\n"
                 "globalThis.TRECH_CONFIG = { run: { nEvents: n }, note: { refused: refused } };\n");
  {
    const auto config = nlohmann::json::parse(transcript(JsEngine::V8, powEval).config);
    expect(config.at("run").at("nEvents") == 7 && config.at("note").at("refused") == true,
           "V8 eval must run plain code and refuse `**`: " + config.dump());
  }
  const auto powString = fixture.path() / "pow_string.js";
  write(powString, "// a ** b in a comment\nglobalThis.TRECH_CONFIG = { run: { nEvents: 2 }, note: 'x ** y' };\n");
  compare("`**` only in text", transcript(JsEngine::QuickJs, powString), transcript(JsEngine::V8, powString));

  // 4. Errors: same message, a location for syntax errors, host-function errors propagate.
  const auto thrown = fixture.path() / "throws.js";
  write(thrown, "function fail() { throw new TypeError('bad value ' + 42); }\nfail();\n");
  const auto qThrown = transcript(JsEngine::QuickJs, thrown).error;
  const auto vThrown = transcript(JsEngine::V8, thrown).error;
  expect(qThrown.rfind("TypeError: bad value 42", 0) == 0 && vThrown.rfind("TypeError: bad value 42", 0) == 0,
         "thrown errors must start with the same message:\n  " + qThrown + "\n  " + vThrown);
  expect(vThrown.find("at fail (") != std::string::npos && vThrown.find("throws.js:1:") != std::string::npos,
         "V8 stack must name the function and location: " + vThrown);
  const auto syntax = fixture.path() / "syntax.js";
  write(syntax, "var ok = 1;\nvar broken = ;\n");
  const auto vSyntax = transcript(JsEngine::V8, syntax).error;
  expect(vSyntax.rfind("SyntaxError", 0) == 0 && vSyntax.find("syntax.js:2:") != std::string::npos,
         "V8 syntax errors must carry file:line: " + vSyntax);
  const auto include = fixture.path() / "include_missing.js";
  write(include, "TRECH_INCLUDE('does_not_exist.js');\n");
  const auto qInclude = transcript(JsEngine::QuickJs, include).error;
  const auto vInclude = transcript(JsEngine::V8, include).error;
  expect(!vInclude.empty() && qInclude.substr(0, qInclude.find('\n')) == vInclude.substr(0, vInclude.find('\n')),
         "host-function errors must match:\n  " + qInclude + "\n  " + vInclude);

  // 5. A runtime can be swapped across engines (the live lab swaps re-evaluations in place).
  {
    trech::JsRuntime a(JsEngine::QuickJs);
    trech::JsRuntime b(JsEngine::V8);
    a.evalExperimentAndGetConfigJson(hooks.string());
    a.swap(b);
    expect(a.engine() == JsEngine::V8 && b.engine() == JsEngine::QuickJs, "swap must exchange engines");
    expect(!b.scriptParametersJson().empty() && b.scriptParametersJson() != "[]", "swap must move evaluated state");
  }

  // 6. Hook dispatch from several threads, one at a time (Geant4 workers do this).
  {
    trech::JsRuntime js(JsEngine::V8);
    auto cfg = trech::configFromJsonString(js.evalExperimentAndGetConfigJson(hooks.string()));
    std::vector<std::thread> workers;
    for (int t = 0; t < 4; ++t) {
      workers.emplace_back([&js, &cfg, t] {
        for (int i = 0; i < 50; ++i) {
          trech::HookRuntimeContext context;
          context.seed = cfg.run.seed;
          context.eventId = t * 100 + i;
          context.stepIndex = 0;
          context.stepEdepMeV = 0.5;
          js.dispatchHook("onStep", context, nullptr, false);
        }
      });
    }
    for (auto& worker : workers) worker.join();
    expect(js.takeEmittedRecords().size() == 200, "every threaded V8 dispatch must emit once");
  }

  if (failures) {
    std::cerr << failures << " QuickJS/V8 parity check(s) failed\n";
    return 1;
  }
  std::cout << "QuickJS/V8 parity: all checks pass\n";
  return 0;
}
