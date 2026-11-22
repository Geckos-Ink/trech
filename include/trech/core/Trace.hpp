#pragma once

// Engine trace: a configurable, observation-only verbose log of what the TRECH engine decided
// during a run, and of where each scenario result came from.
//
// The trace answers one question that a rendered scenario cannot: was this value produced by the
// engine's statistical layers (learned inference, cascades, operators, method arbitration), or by
// a law the scenario authored itself? Every `ctx.*` inference call is recorded with an
// attribution outcome (`engine`, `engine_extrapolated`, `engine_not_ran`, `null_strict`,
// `null_unavailable`, `error`), each hook invocation with how many of its emits were backed by an
// engine result, and scenarios can report their own residual laws through `ctx.authored(law)`.
//
// Contract: tracing never changes physics, RNG streams, emitted fields, config JSON or config
// hashes. It is configured from the CLI (`--trace`) or the `TRECH_TRACE` environment variable,
// never from the scenario config, and is off by default. Off costs one relaxed atomic load per
// instrumented site.

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <set>
#include <string>
#include <string_view>

#include <nlohmann/json.hpp>

namespace trech::trace {

// Ordered verbosity levels. Each includes everything below it.
//   summary: run-end attribution summary only (counters, no per-call records).
//   info:    + lifecycle (run, models loaded/missing, method-arbiter leader changes, ctx.log).
//   debug:   + one record per hook invocation and per method-arbiter step.
//   trace:   + one record per ctx.* inference call, with argument and result digests.
enum class Level : int { Off = 0, Summary = 1, Info = 2, Debug = 3, Trace = 4 };

struct Options {
  Level level = Level::Off;
  // Categories to record (empty = all). Counters for the summary are always kept.
  std::set<std::string> categories;
  // JSONL sink; empty = no file. The CLI defaults it to <output>/trech_trace.jsonl.
  std::string path;
  // Human-readable one-line-per-record copy on stderr.
  bool toStderr = false;
  // Per-category record cap; further records are counted as suppressed in the summary.
  std::size_t maxRecordsPerCategory = 20000;
  // Upper bound for a single argument/result digest, in serialized bytes.
  std::size_t maxDigestBytes = 2048;
};

// Parses `<level>[:<cat>,<cat>...]`, e.g. `debug`, `trace:predict,evolve`, `info:arbiter`.
// Level names: off, summary, info, debug, trace (or 0..4). Throws std::invalid_argument.
Options parseSpec(const std::string& spec);
Level parseLevel(const std::string& name);
const char* levelName(Level level);

// Installs the options (opening the file sink) and clears all counters. Safe to call again.
void configure(const Options& options);
// Options from TRECH_TRACE / TRECH_TRACE_FILE / TRECH_TRACE_STDERR; Level::Off when unset.
Options optionsFromEnvironment();
const Options& options();

namespace detail {
extern std::atomic<int> gLevel;
}

// Fast checks used by instrumented sites before building any record.
inline bool active() { return detail::gLevel.load(std::memory_order_relaxed) > 0; }
inline bool at(Level level) {
  return detail::gLevel.load(std::memory_order_relaxed) >= static_cast<int>(level);
}
bool enabled(Level level, std::string_view category);

// The hook invocation currently running on this thread; stamped onto every record.
struct Scope {
  Scope(std::string hook, long long eventId, long long stepIndex);
  ~Scope();
  Scope(const Scope&) = delete;
  Scope& operator=(const Scope&) = delete;

 private:
  std::string previousHook_;
  long long previousEvent_;
  long long previousStep_;
};

// Purpose role of the code running on this thread: "" (the scenario's own path) or one of
// "validation", "reference", "teacher", "forced" (the labels the project principles require for
// code that names or forces a method off the decision path). Set by TRECH_TRACE.role(role, fn)
// and by the JS host around a validation companion's functions. While a role is set, records are
// stamped with `role`, and ctx calls and authored laws are tallied under `roles` in the summary
// instead of the scenario's own counts. setRole returns the previous role so callers can restore
// it; an unknown name throws std::invalid_argument.
std::string setRole(std::string role);
const std::string& role();
bool isRole(std::string_view name);

// Writes one record when `enabled(level, category)`. `data` may be null. A `severity` of
// "warn" or "error" is stamped on the record; when the level or category is not recorded, such a
// record is printed on stderr instead (`TRECH js warn: ...`), so a script's warnings are never silently lost.
void record(Level level, std::string_view category, std::string_view message,
            nlohmann::json data = nullptr, std::string_view severity = {});

// Named counters a script increments (TRECH_TRACE.count); listed in the summary as `counters`.
void countScript(std::string_view name, double amount);

// Timed spans (TRECH_TRACE.span). begin returns an opaque id (0 when the category is off);
// end writes one debug record with the wall-clock duration. The duration only ever reaches the
// trace file, never the script, so a span cannot feed wall time back into a run.
std::uint64_t spanBegin(std::string_view category, std::string_view name);
void spanEnd(std::uint64_t id, nlohmann::json data = nullptr);

// Attribution counters for the run summary (kept at every level above Off).
void countCall(std::string_view call, std::string_view outcome);
void countHook(std::string_view hook, std::size_t emits, std::size_t engineBackedCalls,
               std::size_t engineCalls);
// Returns the law's running count, so callers can thin repeated records (1, 2, 4, 8, ...).
std::size_t countAuthored(std::string_view law);
void countModel(std::string_view name, bool loaded);

// Compact copy of a JSON value: scalars kept, strings/arrays/objects truncated, depth-limited,
// bounded by `maxBytes` of serialized output.
nlohmann::json digest(const nlohmann::json& value, std::size_t maxBytes);

// The run summary: attribution per ctx call, per hook, authored laws, models, suppressed records,
// and a short plain-language verdict.
nlohmann::json summary();

// Closes one batch (one Geant4 run; `trech lab` runs several per session): writes a
// `batch attribution summary` record covering everything since the previous batch summary (the
// first batch also covers configuration and onInit), resets the batch counters and returns the
// reference that run_end provenance stores as `trace` (schema `trech_trace_ref_v1`: level,
// categories, path, batch index, record sequence, summary hash, totals, verdict). Returns null when
// tracing is off, so untraced provenance keeps its shape. The run summary still covers the session.
nlohmann::json batchSummary(long long runId = -1);

// Writes the summary (record + stderr table when level >= Summary) and flushes/closes the sink.
// Idempotent until the next configure().
void finish();

}  // namespace trech::trace
