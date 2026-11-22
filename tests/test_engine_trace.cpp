// Engine trace (trech/core/Trace.hpp): spec parsing, the attribution of every ctx.* inference
// call, scenario reports (ctx.log / ctx.authored / TRECH_LOG), the run summary, and the contract
// that tracing is observation-only (identical emits and config with the trace on or off).
#include "trech/core/RunOptions.hpp"
#include "trech/core/Trace.hpp"
#include "trech/js/JsRuntime.hpp"
#include "trech/ml/MethodArbiter.hpp"
#include "TemporaryDirectory.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace {

int failures = 0;

void expect(bool condition, const std::string& message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << "\n";
    ++failures;
  }
}

void write(const std::filesystem::path& path, const std::string& text) {
  std::ofstream out(path);
  out << text;
}

std::vector<nlohmann::json> readTrace(const std::filesystem::path& path) {
  std::vector<nlohmann::json> out;
  std::ifstream in(path);
  std::string line;
  while (std::getline(in, line)) {
    if (!line.empty()) out.push_back(nlohmann::json::parse(line));
  }
  return out;
}

std::size_t countRecords(const std::vector<nlohmann::json>& records, const std::string& cat) {
  std::size_t n = 0;
  for (const auto& r : records) n += r.value("cat", std::string()) == cat ? 1 : 0;
  return n;
}

// One scenario, two hooks: onEventEnd asks the engine (a model that is not declared, so the
// result is null and the scenario falls back to an authored law), onRunEnd emits a Geant4 tally.
std::string scenario(const std::string& mode) {
  return R"JS(
TRECH_LOG("evaluating", { mode: ")JS" + mode + R"JS(" });
globalThis.TRECH_CONFIG = { run: { nEvents: 2, seed: 7 }, determinism: { mode: ")JS" + mode + R"JS(" } };
globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    const learned = ctx.predict("absent_model", { x: 1 });
    const cascade = ctx.cascade({ x: 1 });
    let value;
    if (learned === null) {
      ctx.authored("linear_fallback", { reason: "no engine result" });
      value = 2 * ctx.event.edepMeV + 1;
    } else {
      value = learned.y;
    }
    ctx.log("event value", { value });
    ctx.emit("value", { value, cascadeNull: cascade === null, u: ctx.rng.uniform() });
  },
  onRunEnd(ctx) { ctx.emit("tally", { n: ctx.runtime.nEvents }); },
};
)JS";
}

// The script API: TRECH_TRACE levels, channels, counters, spans, enabled(), console routing.
constexpr const char* kApiScenario = R"JS(
const lib = TRECH_TRACE.channel("glass_model");
lib.info("library loaded", { version: 2 });
console.log("eval", 1, { a: [1, 2] });
globalThis.TRECH_CONFIG = { run: { nEvents: 1, seed: 3 }, determinism: { mode: "strict" } };
globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    const v = TRECH_TRACE.span("solve", () => 6 * 7, { step: 1 });
    if (TRECH_TRACE.enabled("debug")) TRECH_TRACE.debug("debug payload", { v });
    TRECH_TRACE.trace("fine detail", { v });
    TRECH_TRACE.warn("viscosity clamped", { at: 1 });
    lib.count("calls");
    lib.count("calls", 2);
    console.debug("console debug");
    console.error("console error");
    ctx.emit("v", { v, level: TRECH_TRACE.level(), host: TRECH_TRACE.host });
  },
};
)JS";

struct Transcript {
  std::string config;
  std::vector<std::string> emits;
};

Transcript runScenario(const std::filesystem::path& script,
                       trech::JsEngine engine = trech::JsRuntime::defaultEngine()) {
  Transcript t;
  trech::JsRuntime js(engine);
  t.config = js.evalExperimentAndGetConfigJson(script.string());
  const auto cfg = nlohmann::json::parse(t.config);
  for (int event = 0; event < 2; ++event) {
    trech::HookRuntimeContext ctx;
    ctx.seed = 7;
    ctx.nEvents = 2;
    ctx.eventId = event;
    ctx.eventEdepMeV = 0.5 + event;
    ctx.determinismMode = cfg.at("determinism").at("mode").get<std::string>();
    (void)js.dispatchHook("onEventEnd", ctx, nullptr, false);
  }
  trech::HookRuntimeContext end;
  end.seed = 7;
  end.nEvents = 2;
  end.determinismMode = cfg.at("determinism").at("mode").get<std::string>();
  (void)js.dispatchHook("onRunEnd", end, nullptr, false);
  for (const auto& e : js.takeEmittedRecords()) t.emits.push_back(e.hook + "/" + e.tag + "/" + e.payloadJson);
  return t;
}

void testSpecParsing() {
  using trech::trace::Level;
  expect(trech::trace::parseSpec("debug").level == Level::Debug, "debug level");
  expect(trech::trace::parseSpec("TRACE").level == Level::Trace, "level names are case-insensitive");
  expect(trech::trace::parseSpec("2").level == Level::Info, "numeric level");
  const auto spec = trech::trace::parseSpec("trace: predict , evolve,");
  expect(spec.categories.size() == 2 && spec.categories.count("predict") && spec.categories.count("evolve"),
         "category list is trimmed and empty items dropped");
  bool threw = false;
  try {
    (void)trech::trace::parseSpec("loud");
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  expect(threw, "an unknown level is refused");

  const char* ok[] = {"trech", "run", "exp.js", "--trace", "debug:hook", "--trace-file", "t.jsonl",
                      "--trace-stderr"};
  const auto options = trech::parseRunOptions(8, const_cast<char**>(ok));
  expect(options.valid && options.traceSpec == "debug:hook" && options.traceFile == "t.jsonl" &&
             options.traceStderr,
         "CLI trace flags parse: " + options.error);
  const char* bad[] = {"trech", "run", "exp.js", "--trace", "loud"};
  const auto refused = trech::parseRunOptions(5, const_cast<char**>(bad));
  expect(!refused.valid && refused.error.find("--trace") != std::string::npos,
         "an invalid --trace value is a CLI error: " + refused.error);
}

void testDigest() {
  nlohmann::json big = nlohmann::json::object();
  big["values"] = std::vector<double>(1000, 1.5);
  big["name"] = std::string(500, 'a');
  big["nested"] = {{"a", {{"b", {{"c", {{"d", 1}}}}}}}};
  const auto d = trech::trace::digest(big, 512);
  expect(d.dump().size() < 1200, "digest is bounded: " + std::to_string(d.dump().size()));
  expect(d.at("values").size() == 9, "digest truncates long arrays");
}

}  // namespace

int main() {
  namespace fs = std::filesystem;
  const trech::test::TemporaryDirectory fixture("trech_engine_trace");
  testSpecParsing();
  testDigest();

  const auto strictScript = fixture.path() / "strict.js";
  const auto predictiveScript = fixture.path() / "predictive.js";
  write(strictScript, scenario("strict"));
  write(predictiveScript, scenario("predictive"));

  // Baseline with tracing off: no file, and ctx.log / ctx.authored / TRECH_LOG are no-ops.
  trech::trace::configure({});
  expect(!trech::trace::active(), "trace is off by default");
  const auto untraced = runScenario(strictScript);
  expect(untraced.emits.size() == 3, "untraced scenario runs");

  // Strict: every inference call is null_strict and the emits have no engine backing.
  const auto strictPath = fixture.path() / "strict_trace.jsonl";
  trech::trace::Options options;
  options.level = trech::trace::Level::Trace;
  options.path = strictPath.string();
  trech::trace::configure(options);
  const auto traced = runScenario(strictScript);
  expect(traced.config == untraced.config, "tracing never changes the config JSON");
  expect(traced.emits == untraced.emits, "tracing never changes emits or RNG streams");
  auto summary = trech::trace::summary();
  expect(summary.at("calls").at("predict").value("null_strict", 0) == 2, "strict predict -> null_strict");
  expect(summary.at("calls").at("cascade").value("null_strict", 0) == 2, "strict cascade -> null_strict");
  expect(summary.at("totals").value("engine_backed", 1) == 0, "no engine-backed call in strict mode");
  expect(summary.at("hooks").at("onEventEnd").value("emits_without_inference", 0) == 2,
         "strict emits are not backed by inference");
  expect(summary.at("authored").value("linear_fallback", 0) == 2, "ctx.authored is counted per law");
  expect(summary.at("verdict").get<std::string>().find("fallback") != std::string::npos,
         "the verdict names the fallback path: " + summary.at("verdict").get<std::string>());
  trech::trace::finish();
  const auto records = readTrace(strictPath);
  expect(!records.empty() && records.back().value("cat", std::string()) == "summary",
         "the trace file ends with the summary");
  expect(countRecords(records, "predict") == 2 && countRecords(records, "cascade") == 2,
         "one trace-level record per inference call");
  expect(countRecords(records, "hook") == 3, "one debug record per hook invocation");
  expect(countRecords(records, "authored") == 2, "one debug record per ctx.authored");
  expect(countRecords(records, "scenario") == 3, "TRECH_LOG + ctx.log records");
  for (const auto& r : records) {
    if (r.value("cat", std::string()) == "predict") {
      expect(r.at("data").at("name") == "absent_model" && r.at("hook") == "onEventEnd" && r.contains("event"),
             "predict records carry the model name and hook scope: " + r.dump());
    }
  }

  // Predictive, model undeclared: null_unavailable (not a strict-mode null).
  options.path = (fixture.path() / "predictive_trace.jsonl").string();
  options.level = trech::trace::Level::Summary;
  trech::trace::configure(options);
  (void)runScenario(predictiveScript);
  summary = trech::trace::summary();
  expect(summary.at("calls").at("predict").value("null_unavailable", 0) == 2,
         "predictive predict on an undeclared model -> null_unavailable: " + summary.dump());
  trech::trace::finish();
  const auto summaryOnly = readTrace(options.path);
  expect(summaryOnly.size() == 1 && summaryOnly.front().at("cat") == "summary",
         "summary level writes only the run summary");

  // Category filter: only arbiter records, plus the summary.
  options.path = (fixture.path() / "arbiter_trace.jsonl").string();
  options.level = trech::trace::Level::Debug;
  options.categories = {"arbiter"};
  trech::trace::configure(options);
  {
    trech::ml::MethodArbiterOptions o;
    o.methods = {"a", "b"};
    o.features = {"x"};
    trech::ml::MethodArbiter arbiter(o);
    trech::ml::MethodArbiterBatch batch;
    batch.count = 4;
    batch.features = {0.0, 1.0, 2.0, 3.0};
    batch.predictions = {1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0};
    batch.reference = {1.0, 1.0, 1.0, 1.0};
    (void)arbiter.step(batch);
    (void)arbiter.step(batch);
  }
  (void)runScenario(strictScript);
  trech::trace::finish();
  const auto filtered = readTrace(options.path);
  expect(countRecords(filtered, "arbiter") >= 2, "arbiter steps are traced at debug");
  expect(countRecords(filtered, "hook") == 0 && countRecords(filtered, "scenario") == 0,
         "the category filter drops other categories");
  expect(countRecords(filtered, "summary") == 1, "the summary is never filtered");

  // Script API on every available engine; V8 must write the same records as QuickJS.
  const auto apiScript = fixture.path() / "api.js";
  write(apiScript, kApiScenario);
  std::vector<std::vector<nlohmann::json>> perEngine;
  std::vector<std::string> emitsPerEngine;
  for (const auto engine : {trech::JsEngine::QuickJs, trech::JsEngine::V8}) {
    if (!trech::JsRuntime::engineAvailable(engine)) continue;
    trech::trace::Options api;
    api.level = trech::trace::Level::Debug;
    api.path = (fixture.path() / (engine == trech::JsEngine::V8 ? "api_v8.jsonl" : "api_qjs.jsonl")).string();
    trech::trace::configure(api);
    const auto t = runScenario(apiScript, engine);
    const auto summary = trech::trace::summary();
    expect(summary.contains("counters") && summary.at("counters").value("glass_model.calls", 0.0) == 6.0,
           "channel counters are summed over both events: " + summary.dump());
    trech::trace::finish();
    auto records = readTrace(api.path);
    std::string emits;
    for (const auto& e : t.emits) emits += e + "\n";
    emitsPerEngine.push_back(emits);
    expect(emits.find("\"level\":\"debug\"") != std::string::npos && emits.find("\"host\":\"trech\"") != std::string::npos,
           "TRECH_TRACE.level()/host reach the script: " + emits);
    std::size_t lib = 0, console = 0, span = 0, warn = 0, traceLevel = 0, debugPayload = 0;
    for (auto& r : records) {
      const auto cat = r.value("cat", std::string());
      if (cat == "trace") r["data"].erase("path");  // each engine writes its own file
      if (cat == "glass_model" && r.value("msg", std::string()) == "library loaded") ++lib;
      if (cat == "console") ++console;
      if (r.value("msg", std::string()) == "solve") {
        ++span;
        expect(r.at("data").at("span") == "solve" && r.at("data").at("duration_ms").is_number() &&
                   r.at("data").at("data").at("step") == 1 && r.at("hook") == "onEventEnd",
               "span record: " + r.dump());
        r["data"].erase("duration_ms");  // the only wall-clock field; engines differ there
      }
      if (r.value("severity", std::string()) == "warn") ++warn;
      if (r.value("msg", std::string()) == "fine detail") ++traceLevel;
      if (r.value("msg", std::string()) == "debug payload") ++debugPayload;
      if (cat == "console" && r.value("level", std::string()) == "info" && r.value("msg", std::string()).rfind("eval", 0) == 0) {
        expect(r.at("msg") == "eval 1 {\"a\":[1,2]}", "console formats like Node: " + r.dump());
      }
    }
    expect(lib == 1, "channel info at evaluation time");
    expect(console == 5, "console.log at evaluation and debug/error per event are recorded (got " + std::to_string(console) + ")");
    expect(span == 2 && warn == 2 && debugPayload == 2, "span, warn and enabled()-guarded debug records per event");
    expect(traceLevel == 0, "a trace-level call is not recorded at debug level");
    perEngine.push_back(std::move(records));
  }
  if (perEngine.size() == 2) {
    for (std::size_t i = 0; i < std::max(perEngine[0].size(), perEngine[1].size()); ++i) {
      const auto q = i < perEngine[0].size() ? perEngine[0][i].dump() : std::string("<none>");
      const auto v = i < perEngine[1].size() ? perEngine[1][i].dump() : std::string("<none>");
      if (q != v) {
        expect(false, "V8 writes the same trace records as QuickJS; first difference:\n  quickjs: " + q +
                          "\n  v8:      " + v);
        break;
      }
    }
    expect(emitsPerEngine[0] == emitsPerEngine[1], "V8 and QuickJS emit the same values");
  }

  // Batches (one Geant4 run each; a lab session has several): every batch summary covers only
  // what happened since the previous one, the run summary covers the session, and the provenance
  // reference is stable for identical batches.
  {
    trech::trace::Options batches;
    batches.level = trech::trace::Level::Summary;
    batches.path = (fixture.path() / "batches.jsonl").string();
    trech::trace::configure(batches);
    (void)runScenario(strictScript);
    const auto first = trech::trace::batchSummary(0);
    (void)runScenario(strictScript);
    const auto second = trech::trace::batchSummary(1);
    expect(first.value("schema", std::string()) == "trech_trace_ref_v1" && first.at("batch") == 1 &&
               second.at("batch") == 2,
           "batch references are numbered: " + first.dump());
    expect(first.at("totals").value("calls", 0) == 4 && second.at("totals").value("calls", 0) == 4,
           "each batch counts only its own calls: " + second.dump());
    expect(first.at("summary_hash") == second.at("summary_hash") ||
               first.at("summary_hash").get<std::string>().size() == 16,
           "the reference carries a 16-hex summary hash");
    expect(first.at("path") == batches.path && first.at("level") == "summary" && first.contains("verdict"),
           "the reference names the trace file, level and verdict");
    const auto session = trech::trace::summary();
    expect(session.at("totals").value("calls", 0) == 8 && session.value("batches", 0) == 2,
           "the run summary still covers the whole session: " + session.dump());
    trech::trace::finish();
    const auto lines = readTrace(batches.path);
    std::size_t batchLines = 0;
    for (const auto& r : lines) {
      if (r.value("msg", std::string()) == "batch attribution summary") {
        ++batchLines;
        expect(r.at("data").at("batch") == batchLines && r.at("data").at("run_id") == batchLines - 1,
               "batch records carry their index and run id: " + r.dump());
      }
    }
    expect(batchLines == 2 && lines.back().value("msg", std::string()) == "run attribution summary",
           "two batch summaries, then the run summary");
    trech::trace::configure({});
    expect(trech::trace::batchSummary(0).is_null(), "no batch reference when tracing is off");
  }

  // Purpose roles: a validation companion's functions (wrapped by the host while tracing) and
  // TRECH_TRACE.role(...) blocks are tallied under `roles`, never as the scenario's own path.
  {
    const auto bundle = fixture.path() / "roles";
    fs::create_directories(bundle);
    write(bundle / "roles.validation.js", R"JS(
globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["roles"] = {
  observe(ctx, x) {
    ctx.authored("reference_law");
    return { graded: ctx.predict("absent_reference", { x }) === null, self: this === TRECH_CHECKS["roles"] };
  },
};
)JS");
    write(bundle / "roles.js", R"JS(
globalThis.TRECH_CONFIG = { run: { nEvents: 2, seed: 7 }, determinism: { mode: "strict" } };
globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    const check = TRECH_CHECKS["roles"].observe(ctx, 2);
    const forced = TRECH_TRACE.role("reference", () => { TRECH_TRACE.authored("forced_reference"); return 3; });
    let rejected = false;
    try { TRECH_TRACE.role("decision", () => 0); } catch (e) { rejected = e instanceof TypeError; }
    const own = ctx.predict("absent_model", { x: 1 });
    if (own === null) ctx.authored("own_fallback");
    ctx.emit("v", { check, forced, rejected, u: ctx.rng.uniform() });
  },
  onRunEnd(ctx) { ctx.emit("t", { n: ctx.runtime.nEvents }); },
};
)JS");
    trech::trace::configure({});
    const auto plain = runScenario(bundle / "roles.js");
    trech::trace::Options roles;
    roles.level = trech::trace::Level::Debug;
    roles.path = (fixture.path() / "roles.jsonl").string();
    trech::trace::configure(roles);
    const auto traced = runScenario(bundle / "roles.js");
    expect(traced.emits == plain.emits && traced.config == plain.config,
           "roles never change emits or config");
    expect(!plain.emits.empty() && plain.emits.front().find("\"rejected\":true") != std::string::npos &&
               plain.emits.front().find("\"self\":true") != std::string::npos,
           "an unknown role is rejected and wrapped companions keep `this`: " +
               (plain.emits.empty() ? std::string() : plain.emits.front()));
    const auto summary = trech::trace::summary();
    expect(summary.at("calls").size() == 1 && summary.at("calls").at("predict").value("null_strict", 0) == 2,
           "only the scenario's own predict is in `calls`: " + summary.dump());
    expect(summary.at("authored").size() == 1 && summary.at("authored").value("own_fallback", 0) == 2,
           "only the scenario's own law is in `authored`");
    const auto& byRole = summary.at("roles");
    expect(byRole.at("validation").at("calls").at("predict").value("null_strict", 0) == 2 &&
               byRole.at("validation").at("authored").value("reference_law", 0) == 2 &&
               byRole.at("reference").at("authored").value("forced_reference", 0) == 2,
           "companion and role() work is tallied per role: " + byRole.dump());
    expect(summary.at("totals").value("calls", 0) == 2 && summary.at("totals").value("role_calls", 0) == 2 &&
               summary.at("totals").value("role_authored_reports", 0) == 4,
           "role work stays out of the scenario totals");
    expect(summary.at("hooks").at("onEventEnd").value("engine_calls", 0) == 2,
           "role calls never count toward a hook's engine calls");
    expect(summary.at("verdict").get<std::string>().find("Off the decision path") != std::string::npos,
           "the verdict names the role work");
    trech::trace::finish();
    std::size_t stamped = 0;
    for (const auto& r : readTrace(roles.path)) {
      if (r.value("cat", std::string()) == "authored" && r.contains("role")) ++stamped;
    }
    expect(stamped >= 2, "authored records under a role carry `role`");
    expect(trech::trace::role().empty(), "the role is restored after every block");
  }

  // Off: no file, the API is silent, warn/error still reach stderr, results unchanged.
  trech::trace::configure({});
  {
    const auto t = runScenario(apiScript);
    expect(t.emits.size() == 2 && t.emits[0].find("\"level\":\"off\"") != std::string::npos,
           "TRECH_TRACE.level() is off when tracing is off");
  }
  if (failures) {
    std::cerr << failures << " engine trace check(s) failed\n";
    return 1;
  }
  std::cout << "engine trace: ok\n";
  return 0;
}
