// Scenario-backed live lab, JavaScript side (include/trech/js/LabScriptHost.hpp): a stable
// runtime address, transactional re-evaluation with TRECH_VALUE changes and edited hook
// bodies, onInit tallies reported once per load, the per-batch script identity (digests of
// the bytes that ran, data files, trigger) and the --watch change detection.
#include "trech/js/LabScriptHost.hpp"

#include "trech/core/Provenance.hpp"

#include "TemporaryDirectory.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

#include <nlohmann/json.hpp>

namespace {

int failures = 0;

void expect(bool condition, const std::string& message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << "\n";
    ++failures;
  }
}

// One event-end dispatch; returns the payload of the single "tally" emit.
nlohmann::json eventEnd(trech::JsRuntime& js, double edepMeV) {
  trech::HookRuntimeContext context;
  context.seed = 3;
  context.nEvents = 1;
  context.eventId = 0;
  context.eventEdepMeV = edepMeV;
  context.maxEmitsPerCallback = 8;
  context.maxEmitPayloadBytes = 4096;
  js.dispatchHook("onEventEnd", context, nullptr, false);
  const auto records = js.takeEmittedRecords();
  for (const auto& record : records) {
    if (record.tag == "tally") return nlohmann::json::parse(record.payloadJson);
  }
  return nullptr;
}

void writeText(const std::filesystem::path& path, const std::string& text) {
  std::ofstream out(path, std::ios::binary);
  out << text;
}

std::string sourceSha(const nlohmann::json& identity, const std::string& key, const std::string& path) {
  for (const auto& file : identity.at(key)) {
    if (file.at("path") == path) return file.at("sha256");
  }
  return {};
}

void writeScenario(const std::filesystem::path& path, const std::string& weight) {
  std::ofstream out(path);
  out << "TRECH_INCLUDE('helper.js');\n"
         "const data = TRECH_READ_JSON('data.json');\n"
         "const threshold = TRECH_VALUE.number('threshold', {default: 0.25, min: 0, max: 5});\n"
         "let seen = 0;\n"
         "var TRECH_CONFIG = { run: { nEvents: 4, seed: 11 },\n"
         "  beam: { particle: 'gamma', energyMeV: 1.0 },\n"
         "  hooks: { maxEmitsPerCallback: 8, inputs: { label: 'lab' } } };\n"
         "var TRECH_HOOKS = {\n"
         "  onInit(ctx) { ctx.emit('init', { threshold }); },\n"
         "  onEventEnd(ctx) {\n"
         "    seen += 1;\n"
         "    ctx.emit('tally', { seen, above: ctx.event.edepMeV > threshold, threshold,\n"
         "                        weight: " << weight << ", helper: helperValue(), k: data.k });\n"
         "  }\n"
         "};\n";
}

}  // namespace

int main() {
  const trech::test::TemporaryDirectory fixture("trech_lab_script_host");
  const auto scenario = fixture.path() / "live.js";
  {
    std::ofstream helper(fixture.path() / "helper.js");
    helper << "function helperValue() { return 7; }\n";
  }
  writeText(fixture.path() / "data.json", "{\"k\": 3}\n");
  writeScenario(scenario, "1");

  trech::LabScriptHost host(scenario.string(), {"threshold=0.5"}, false);
  trech::JsRuntime* stable = host.runtime();
  expect(host.generation() == 0, "no generation before the first commit");

  auto first = host.prepare();
  expect(first.config.run.nEvents == 4 && first.config.beam.particle == "gamma",
         "the candidate carries the scenario config");
  expect(first.init.dispatched && first.init.emitCount == 1, "onInit ran in the candidate");
  host.commit(std::move(first));
  expect(host.runtime() == stable, "the runtime address is stable across commits");
  expect(host.generation() == 1 && host.parameters().at("threshold") == 0.5,
         "generation 1 with the CLI override");

  const auto& identity = host.identity();
  expect(identity.at("sources").size() == 2 &&
             identity.at("sources").at(0).at("path") == "live.js" &&
             identity.at("sources").at(1).at("path") == "helper.js",
         "identity lists the entry and its include, relative to the entry directory");
  expect(identity.at("sources_sha256").get<std::string>().size() == 64, "combined source digest");
  expect(identity.at("trigger") == "start" && identity.at("data").size() == 1 &&
             identity.at("data").at(0).at("path") == "data.json",
         "identity records the trigger and the TRECH_READ_JSON data file");
  const auto firstDigest = identity.at("sources_sha256").get<std::string>();

  // The first batch reports the load's onInit once; later batches report none.
  trech::RuntimeRunMetadata metadata;
  host.prepareBatch(metadata);
  expect(metadata.hasHookInit && metadata.hookInit.dispatched && metadata.hookInit.emitCount == 1,
         "first batch carries the onInit tallies");
  expect(nlohmann::json::parse(metadata.labScriptJson).at("generation") == 1, "batch identity");
  host.batchCompleted();
  host.prepareBatch(metadata);
  expect(metadata.hasHookInit && !metadata.hookInit.dispatched && metadata.hookInit.emitCount == 0,
         "later batches report no onInit");

  stable->takeEmittedRecords();  // drop the onInit emit
  auto tally = eventEnd(*stable, 0.4);
  expect(tally.is_object() && tally.at("above") == false && tally.at("threshold") == 0.5 &&
             tally.at("seen") == 1 && tally.at("helper") == 7 && tally.at("k") == 3,
         "hooks use the overridden threshold");
  tally = eventEnd(*stable, 0.4);
  expect(tally.at("seen") == 2, "hook state persists across batches");

  // A refused re-evaluation (out-of-range value, unknown name) leaves everything intact.
  bool threw = false;
  try {
    host.prepare({{"threshold", 99.0}});
  } catch (const std::exception&) {
    threw = true;
  }
  expect(threw, "an out-of-range TRECH_VALUE is refused");
  threw = false;
  try {
    host.prepare({{"no_such_value", 1}});
  } catch (const std::exception& error) {
    threw = std::string(error.what()).find("no_such_value") != std::string::npos;
  }
  expect(threw, "an unknown TRECH_VALUE is refused by name");
  tally = eventEnd(*stable, 0.4);
  expect(tally.at("seen") == 3 && tally.at("threshold") == 0.5 && host.generation() == 1,
         "refused re-evaluations do not touch the active hooks");

  // A prepared candidate that the caller declines (e.g. the kernel refuses it) changes nothing.
  { auto declined = host.prepare({{"threshold", 0.1}}); }
  expect(eventEnd(*stable, 0.4).at("threshold") == 0.5, "a declined candidate is discarded");

  // params: new value, fresh hook state, same address.
  host.commit(host.prepare({{"threshold", 0.1}}), "params");
  stable->takeEmittedRecords();
  tally = eventEnd(*stable, 0.4);
  expect(host.runtime() == stable && host.generation() == 2, "params commits generation 2");
  expect(tally.at("above") == true && tally.at("threshold") == 0.1 && tally.at("seen") == 1,
         "the new value drives the hooks and hook state restarts");
  expect(host.identity().at("sources_sha256") == firstDigest &&
             host.identity().at("parameter_overrides").at("threshold") == 0.1 &&
             host.identity().at("trigger") == "params",
         "same sources, new overrides");

  // Watch: nothing changed, a touch with equal bytes, then real edits of a source and a data file.
  expect(host.changedSourceFingerprint().empty(), "no edit, no watch change");
  writeText(fixture.path() / "helper.js", "function helperValue() { return 7; }\n");
  expect(host.changedSourceFingerprint().empty(), "rewriting the same bytes is no change");
  writeText(fixture.path() / "helper.js", "function helperValue() { return 8; }\n");
  const auto edited = host.changedSourceFingerprint();
  expect(edited.size() == 64, "an edited include is a watch change");
  host.refuseWatchedEdit(edited);
  expect(host.changedSourceFingerprint().empty(), "a refused on-disk state is reported once");
  writeText(fixture.path() / "data.json", "{\"k\": 4}\n");
  const auto dataEdit = host.changedSourceFingerprint();
  expect(!dataEdit.empty() && dataEdit != edited, "a further data edit is a new watch change");
  host.commit(host.prepare(), "watch");
  stable->takeEmittedRecords();
  tally = eventEnd(*stable, 0.4);
  expect(tally.at("helper") == 8 && tally.at("k") == 4 && host.identity().at("trigger") == "watch" &&
             host.changedSourceFingerprint().empty(),
         "the watch reload runs the edited files and clears the change");
  writeText(fixture.path() / "helper.js", "function helperValue() { return 7; }\n");
  writeText(fixture.path() / "data.json", "{\"k\": 3}\n");
  host.commit(host.prepare(), "reload");

  // reload after editing the hook body: new code, new source digest. The identity hashes the
  // bytes the evaluation read, even when the file changes again before the commit.
  writeScenario(scenario, "2");
  const auto evaluatedSha = trech::sha256Hex(
      [&] { std::ifstream in(scenario, std::ios::binary); std::ostringstream b; b << in.rdbuf(); return b.str(); }());
  auto pending = host.prepare();
  writeScenario(scenario, "5");
  host.commit(std::move(pending), "reload");
  expect(sourceSha(host.identity(), "sources", "live.js") == evaluatedSha,
         "the identity records the evaluated bytes, not a later edit");
  expect(!host.changedSourceFingerprint().empty(), "the later edit is still a watch change");
  writeScenario(scenario, "2");
  stable->takeEmittedRecords();
  tally = eventEnd(*stable, 0.4);
  expect(tally.at("weight") == 2 && tally.at("threshold") == 0.1, "reload picks up edited hooks");
  expect(host.identity().at("sources_sha256") != firstDigest && host.generation() == 5,
         "an edit changes the source digest");

  // null restores the authored default.
  host.commit(host.prepare({{"threshold", nullptr}}));
  stable->takeEmittedRecords();
  expect(eventEnd(*stable, 0.4).at("threshold") == 0.25 && host.parameters().empty(),
         "null restores the default");
  const auto status = host.status();
  expect(status.at("phase") == "lab_script" && status.at("parameters").is_array() &&
             status.at("hooks_registered").size() == 2 && status.at("on_init").at("dispatched") == true,
         "status line");

  // A syntax error on reload is refused and the previous script stays active.
  {
    std::ofstream broken(scenario);
    broken << "var TRECH_CONFIG = {;\n";
  }
  threw = false;
  try {
    host.prepare();
  } catch (const std::exception&) {
    threw = true;
  }
  expect(threw && host.generation() == 6 && eventEnd(*stable, 0.4).at("weight") == 2,
         "a broken edit is refused");

  if (failures) {
    std::cerr << failures << " lab script host check(s) failed\n";
    return 1;
  }
  std::cout << "lab script host: all checks passed\n";
  return 0;
}
