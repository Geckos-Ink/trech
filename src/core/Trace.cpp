#include "trech/core/Trace.hpp"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>

namespace trech::trace {

namespace detail {
std::atomic<int> gLevel{0};
}

namespace {

struct HookTally {
  std::size_t invocations = 0;
  std::size_t emits = 0;
  // Emits produced by invocations that made no engine-backed ctx.* call: those values came from
  // Geant4 tallies on ctx or from scenario-authored JavaScript, not from learned inference.
  std::size_t emitsWithoutInference = 0;
  std::size_t invocationsWithEngine = 0;
  std::size_t engineCalls = 0;
  std::size_t engineBackedCalls = 0;
};

// Attribution counters. The state keeps two copies: one for the whole session (the run summary)
// and one since the last batch summary (one Geant4 run; a `trech lab` session has several).
// ctx calls and authored laws made under a purpose role (a validation companion, a forced
// reference): kept apart so they never count as the scenario's own path.
struct RoleTally {
  std::map<std::string, std::map<std::string, std::size_t>> calls;
  std::map<std::string, std::size_t> authored;
};

struct Tallies {
  std::map<std::string, std::map<std::string, std::size_t>> calls;
  std::map<std::string, HookTally> hooks;
  std::map<std::string, std::size_t> authored;
  std::map<std::string, double> counters;
  std::map<std::string, RoleTally> roles;
  std::map<std::string, std::map<std::string, double>> tallies;
  void clear() {
    tallies.clear();
    calls.clear();
    hooks.clear();
    authored.clear();
    counters.clear();
    roles.clear();
  }
};

struct State {
  std::mutex mutex;
  Options options;
  std::ofstream file;
  std::uint64_t seq = 0;
  bool finished = true;
  std::map<std::string, std::size_t> recordsPerCategory;
  std::map<std::string, std::size_t> suppressed;
  Tallies session;
  Tallies batch;
  std::size_t batches = 0;
  std::map<std::string, bool> models;
  struct Span {
    std::string category, name, hook;
    long long event = -1;
    std::chrono::steady_clock::time_point start;
  };
  std::map<std::uint64_t, Span> spans;
  std::uint64_t nextSpan = 0;
};

State& state() {
  static State s;
  return s;
}

thread_local std::string tHook;
thread_local long long tEvent = -1;
thread_local long long tStep = -1;
thread_local std::string tRole;

std::string trim(std::string s) {
  const auto notSpace = [](unsigned char c) { return !std::isspace(c); };
  s.erase(s.begin(), std::find_if(s.begin(), s.end(), notSpace));
  s.erase(std::find_if(s.rbegin(), s.rend(), notSpace).base(), s.end());
  return s;
}

bool isEngineBacked(std::string_view outcome) {
  return outcome == "engine" || outcome == "engine_extrapolated";
}

nlohmann::json digestImpl(const nlohmann::json& v, int depth, std::size_t& budget) {
  constexpr std::size_t kMaxString = 160;
  constexpr std::size_t kMaxItems = 8;
  if (budget == 0) return "…";
  if (v.is_string()) {
    auto s = v.get<std::string>();
    if (s.size() > kMaxString) s = s.substr(0, kMaxString) + "…";
    budget -= std::min(budget, s.size() + 2);
    return s;
  }
  if (!v.is_structured()) {
    budget -= std::min<std::size_t>(budget, 12);
    return v;
  }
  if (depth <= 0) {
    budget -= std::min<std::size_t>(budget, 16);
    return v.is_array() ? nlohmann::json("[" + std::to_string(v.size()) + " items]")
                        : nlohmann::json("{" + std::to_string(v.size()) + " keys}");
  }
  if (v.is_array()) {
    nlohmann::json out = nlohmann::json::array();
    std::size_t i = 0;
    for (const auto& item : v) {
      if (i++ == kMaxItems || budget == 0) {
        out.push_back("… " + std::to_string(v.size()) + " items");
        break;
      }
      out.push_back(digestImpl(item, depth - 1, budget));
    }
    return out;
  }
  nlohmann::json out = nlohmann::json::object();
  std::size_t i = 0;
  for (const auto& [key, item] : v.items()) {
    if (i++ == 4 * kMaxItems || budget == 0) {
      out["…"] = std::to_string(v.size()) + " keys";
      break;
    }
    budget -= std::min(budget, key.size() + 3);
    out[key] = digestImpl(item, depth - 1, budget);
  }
  return out;
}

void writeLocked(State& s, Level level, std::string_view category, std::string_view message,
                 const nlohmann::json& data, std::string_view severity = {}) {
  nlohmann::json line = {{"schema", "trech_trace_v1"},
                         {"seq", ++s.seq},
                         {"level", levelName(level)},
                         {"cat", std::string(category)},
                         {"msg", std::string(message)}};
  if (!severity.empty()) line["severity"] = std::string(severity);
  if (!tHook.empty()) line["hook"] = tHook;
  if (!tRole.empty()) line["role"] = tRole;
  if (tEvent >= 0) line["event"] = tEvent;
  if (tStep >= 0) line["step"] = tStep;
  if (!data.is_null()) line["data"] = data;
  if (s.file.is_open()) {
    // Flushed per record so a live reader (Studio's trace panel) sees it as it happens.
    s.file << line.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace) << '\n';
    s.file.flush();
  }
  if (s.options.toStderr) {
    std::ostringstream os;
    os << "[trech:" << levelName(level) << "] ";
    if (!severity.empty()) os << severity << " ";
    os << category;
    if (!tHook.empty()) {
      os << " " << tHook;
      if (tEvent >= 0) os << "#" << tEvent;
    }
    os << " " << message;
    if (!data.is_null()) {
      auto text = data.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace);
      if (text.size() > 400) text = text.substr(0, 400) + "…";
      os << " " << text;
    }
    std::cerr << os.str() << '\n';
  }
}

std::string verdict(const nlohmann::json& totals) {
  const auto get = [&](const char* k) { return totals.value(k, std::size_t{0}); };
  const std::size_t engine = get("engine_backed");
  const std::size_t calls = get("calls");
  const std::size_t nulls = get("null_strict") + get("null_unavailable") + get("engine_not_ran");
  const std::size_t authored = get("authored_reports");
  const std::size_t emits = get("emits");
  const std::size_t bare = get("emits_without_inference");
  std::ostringstream os;
  if (calls == 0 && emits == 0) {
    os << "No ctx inference call ran and nothing was emitted.";
  } else if (calls == 0) {
    os << "No ctx inference call ran: every emitted value came from Geant4 tallies or "
          "scenario-authored JavaScript.";
  } else {
    os << engine << " of " << calls << " ctx inference calls returned an engine result";
    if (nulls > 0) {
      os << "; " << nulls << " returned null or did not run, so the scenario used its own "
                              "fallback path there";
    }
    os << ".";
  }
  if (emits > 0) {
    os << " " << bare << " of " << emits
       << " emits came from hook calls with no engine-backed inference.";
  }
  if (authored > 0) {
    os << " " << authored << " uses of authored laws were reported (ctx.authored or a library's "
          "reference solver); see `authored` for each law.";
  }
  const std::size_t roleCalls = get("role_calls");
  const std::size_t roleAuthored = get("role_authored_reports");
  if (roleCalls + roleAuthored > 0) {
    os << " Off the decision path (validation/reference roles, not counted above): " << roleCalls
       << " ctx calls and " << roleAuthored << " authored-law uses; see `roles`.";
  }
  return os.str();
}

}  // namespace

const char* levelName(Level level) {
  switch (level) {
    case Level::Off: return "off";
    case Level::Summary: return "summary";
    case Level::Info: return "info";
    case Level::Debug: return "debug";
    case Level::Trace: return "trace";
  }
  return "off";
}

Level parseLevel(const std::string& raw) {
  std::string name = trim(raw);
  std::transform(name.begin(), name.end(), name.begin(),
                 [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  if (name == "off" || name == "0" || name == "none" || name == "false") return Level::Off;
  if (name == "summary" || name == "1") return Level::Summary;
  if (name == "info" || name == "2" || name.empty() || name == "on" || name == "true") return Level::Info;
  if (name == "debug" || name == "3") return Level::Debug;
  if (name == "trace" || name == "4" || name == "all") return Level::Trace;
  throw std::invalid_argument("unknown trace level '" + raw +
                              "' (expected off, summary, info, debug or trace)");
}

Options parseSpec(const std::string& spec) {
  Options out;
  const auto colon = spec.find(':');
  out.level = parseLevel(spec.substr(0, colon));
  if (colon != std::string::npos) {
    std::stringstream list(spec.substr(colon + 1));
    std::string item;
    while (std::getline(list, item, ',')) {
      item = trim(item);
      if (!item.empty()) out.categories.insert(item);
    }
  }
  return out;
}

Options optionsFromEnvironment() {
  Options out;
  if (const char* spec = std::getenv("TRECH_TRACE"); spec && spec[0] != '\0') {
    out = parseSpec(spec);
  }
  if (const char* path = std::getenv("TRECH_TRACE_FILE"); path && path[0] != '\0') {
    out.path = path;
  }
  if (const char* err = std::getenv("TRECH_TRACE_STDERR"); err && err[0] != '\0') {
    const std::string v = err;
    out.toStderr = !(v == "0" || v == "false" || v == "off");
  }
  return out;
}

void configure(const Options& options) {
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (s.file.is_open()) s.file.close();
  s.options = options;
  s.seq = 0;
  s.recordsPerCategory.clear();
  s.suppressed.clear();
  tRole.clear();
  s.session.clear();
  s.batch.clear();
  s.batches = 0;
  s.models.clear();
  s.spans.clear();
  s.finished = options.level == Level::Off;
  if (options.level != Level::Off && !options.path.empty()) {
    s.file.open(options.path, std::ios::out | std::ios::trunc);
    if (!s.file) {
      std::cerr << "TRECH trace: cannot open " << options.path << "; tracing to stderr only\n";
      s.options.toStderr = true;
    }
  }
  detail::gLevel.store(static_cast<int>(options.level), std::memory_order_relaxed);
  if (options.level >= Level::Info) {
    nlohmann::json cats = nlohmann::json::array();
    for (const auto& c : options.categories) cats.push_back(c);
    writeLocked(s, Level::Info, "trace", "trace enabled",
                {{"level", levelName(options.level)},
                 {"categories", cats},
                 {"path", options.path},
                 {"observation_only", true}});
  }
}

const Options& options() { return state().options; }

bool isRole(std::string_view name) {
  return name == "validation" || name == "reference" || name == "teacher" || name == "forced";
}

std::string setRole(std::string role) {
  if (!role.empty() && !isRole(role)) {
    throw std::invalid_argument("unknown trace role '" + role +
                                "' (expected validation, reference, teacher or forced)");
  }
  std::string previous = std::move(tRole);
  tRole = std::move(role);
  return previous;
}

const std::string& role() { return tRole; }

bool enabled(Level level, std::string_view category) {
  if (!at(level)) return false;
  const auto& cats = state().options.categories;
  return cats.empty() || cats.count(std::string(category)) > 0;
}

Scope::Scope(std::string hook, long long eventId, long long stepIndex)
    : previousHook_(std::move(tHook)), previousEvent_(tEvent), previousStep_(tStep) {
  tHook = std::move(hook);
  tEvent = eventId;
  tStep = stepIndex;
}

Scope::~Scope() {
  tHook = std::move(previousHook_);
  tEvent = previousEvent_;
  tStep = previousStep_;
}

void record(Level level, std::string_view category, std::string_view message, nlohmann::json data,
            std::string_view severity) {
  const bool loud = severity == "warn" || severity == "error";
  if (loud && (level == Level::Off || !enabled(level, category))) {
    std::ostringstream os;
    os << "TRECH js " << severity << ": " << message;
    if (!data.is_null()) os << " " << data.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace);
    std::cerr << os.str() << '\n';
    return;
  }
  if (level == Level::Off || !enabled(level, category)) return;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (s.finished) return;
  auto& n = s.recordsPerCategory[std::string(category)];
  if (n >= s.options.maxRecordsPerCategory) {
    s.suppressed[std::string(category)] += 1;
    return;
  }
  ++n;
  writeLocked(s, level, category, message, data, severity);
}

void countScript(std::string_view name, double amount) {
  if (!active()) return;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  s.session.counters[std::string(name)] += amount;
  s.batch.counters[std::string(name)] += amount;
}

std::uint64_t spanBegin(std::string_view category, std::string_view name) {
  if (!enabled(Level::Debug, category)) return 0;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  const std::uint64_t id = ++s.nextSpan;
  s.spans[id] = {std::string(category), std::string(name), tHook, tEvent,
                 std::chrono::steady_clock::now()};
  return id;
}

void spanEnd(std::uint64_t id, nlohmann::json data) {
  if (id == 0) return;
  State::Span span;
  {
    auto& s = state();
    std::lock_guard<std::mutex> lock(s.mutex);
    const auto it = s.spans.find(id);
    if (it == s.spans.end()) return;
    span = std::move(it->second);
    s.spans.erase(it);
  }
  const double ms =
      std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - span.start).count();
  nlohmann::json payload = {{"span", span.name}, {"duration_ms", ms}};
  if (!data.is_null()) payload["data"] = std::move(data);
  record(Level::Debug, span.category, span.name, std::move(payload));
}

void tally(std::string_view section, std::string_view key, double amount) {
  if (!active()) return;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  s.session.tallies[std::string(section)][std::string(key)] += amount;
  s.batch.tallies[std::string(section)][std::string(key)] += amount;
}

void countCall(std::string_view call, std::string_view outcome) {
  if (!active()) return;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  for (auto* tallies : {&s.session, &s.batch}) {
    auto& calls = tRole.empty() ? tallies->calls : tallies->roles[tRole].calls;
    calls[std::string(call)][std::string(outcome)] += 1;
  }
}

void countHook(std::string_view hook, std::size_t emits, std::size_t engineBackedCalls,
               std::size_t engineCalls) {
  if (!active()) return;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  for (auto* tallies : {&s.session, &s.batch}) {
    auto& t = tallies->hooks[std::string(hook)];
    t.invocations += 1;
    t.emits += emits;
    t.engineCalls += engineCalls;
    t.engineBackedCalls += engineBackedCalls;
    if (engineBackedCalls > 0) t.invocationsWithEngine += 1;
    else t.emitsWithoutInference += emits;
  }
}

std::size_t countAuthored(std::string_view law) {
  if (!active()) return 0;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (!tRole.empty()) {
    ++s.batch.roles[tRole].authored[std::string(law)];
    return ++s.session.roles[tRole].authored[std::string(law)];
  }
  ++s.batch.authored[std::string(law)];
  return ++s.session.authored[std::string(law)];
}

void countModel(std::string_view name, bool loaded) {
  if (!active()) return;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  s.models[std::string(name)] = loaded;
}

std::vector<std::string> childEnvironment(const std::string& childPath) {
  if (!active()) return {};
  const auto& o = state().options;
  std::string spec = levelName(o.level);
  if (!o.categories.empty()) {
    spec += ":";
    bool first = true;
    for (const auto& c : o.categories) {
      spec += (first ? "" : ",") + c;
      first = false;
    }
  }
  return {"TRECH_TRACE=" + spec, "TRECH_TRACE_FILE=" + childPath, "TRECH_TRACE_STDERR=0"};
}

std::size_t importRecords(const std::string& childPath, std::string_view origin) {
  if (!active()) return 0;
  std::ifstream in(childPath);
  if (!in) return 0;
  std::size_t copied = 0;
  std::string line;
  while (std::getline(in, line)) {
    if (line.empty()) continue;
    const auto r = nlohmann::json::parse(line, nullptr, false);
    if (!r.is_object()) continue;
    const std::string cat = r.value("cat", std::string("script"));
    nlohmann::json data = r.contains("data") ? r.at("data") : nlohmann::json(nullptr);
    if (cat == "summary") {
      // The child's own summary: its tallies and counters join this run's, and the record is
      // kept as an info record so it never reads as this run's summary.
      if (data.is_object()) {
        // Copies, not temporaries: items() of a temporary would dangle in the range-for.
        const nlohmann::json tallies = data.value("tallies", nlohmann::json::object());
        const nlohmann::json counters = data.value("counters", nlohmann::json::object());
        for (const auto& [section, entries] : tallies.items())
          for (const auto& [key, n] : entries.items())
            if (n.is_number()) tally(section, key, n.get<double>());
        for (const auto& [name, n] : counters.items())
          if (n.is_number()) countScript(name, n.get<double>());
      }
      record(Level::Info, origin, std::string(origin) + " worker summary", std::move(data));
      ++copied;
      continue;
    }
    Level level = Level::Info;
    try {
      level = parseLevel(r.value("level", std::string("info")));
    } catch (const std::exception&) {
    }
    if (level == Level::Off || level == Level::Summary) level = Level::Info;
    const std::string severity = r.value("severity", std::string());
    if (!enabled(level, cat) && severity != "warn" && severity != "error") continue;
    nlohmann::json payload = data.is_null() ? nlohmann::json::object() : nlohmann::json(data);
    if (!payload.is_object()) payload = {{"value", std::move(payload)}};
    payload["origin"] = std::string(origin);
    if (r.contains("role")) payload["role"] = r.at("role");
    record(level, cat, r.value("msg", std::string()), std::move(payload), severity);
    ++copied;
  }
  return copied;
}

nlohmann::json digest(const nlohmann::json& value, std::size_t maxBytes) {
  std::size_t budget = maxBytes;
  return digestImpl(value, 3, budget);
}

namespace {

nlohmann::json summarizeLocked(const State& s, const Tallies& t) {
  nlohmann::json calls = nlohmann::json::object();
  std::size_t total = 0, engine = 0;
  std::map<std::string, std::size_t> byOutcome;
  for (const auto& [call, outcomes] : t.calls) {
    nlohmann::json row = nlohmann::json::object();
    std::size_t callTotal = 0;
    for (const auto& [outcome, n] : outcomes) {
      row[outcome] = n;
      callTotal += n;
      byOutcome[outcome] += n;
      if (isEngineBacked(outcome)) engine += n;
    }
    row["total"] = callTotal;
    total += callTotal;
    calls[call] = row;
  }
  nlohmann::json hooks = nlohmann::json::object();
  std::size_t emits = 0, bare = 0;
  for (const auto& [hook, h] : t.hooks) {
    hooks[hook] = {{"invocations", h.invocations},
                   {"invocations_with_engine", h.invocationsWithEngine},
                   {"engine_calls", h.engineCalls},
                   {"engine_backed_calls", h.engineBackedCalls},
                   {"emits", h.emits},
                   {"emits_without_inference", h.emitsWithoutInference}};
    emits += h.emits;
    bare += h.emitsWithoutInference;
  }
  std::size_t authoredTotal = 0;
  nlohmann::json authored = nlohmann::json::object();
  for (const auto& [law, n] : t.authored) {
    authored[law] = n;
    authoredTotal += n;
  }
  nlohmann::json models = nlohmann::json::object();
  nlohmann::json missing = nlohmann::json::array();
  for (const auto& [name, loaded] : s.models) {
    models[name] = loaded ? "loaded" : "missing";
    if (!loaded) missing.push_back(name);
  }
  nlohmann::json totals = {{"calls", total},
                           {"engine_backed", engine},
                           {"emits", emits},
                           {"emits_without_inference", bare},
                           {"authored_reports", authoredTotal}};
  for (const auto& [outcome, n] : byOutcome) totals[outcome] = n;
  nlohmann::json roles = nlohmann::json::object();
  std::size_t roleCalls = 0, roleAuthored = 0;
  for (const auto& [name, r] : t.roles) {
    nlohmann::json row = {{"calls", nlohmann::json::object()}, {"authored", r.authored}};
    std::size_t callsN = 0, engineN = 0, authoredN = 0;
    for (const auto& [call, outcomes] : r.calls) {
      for (const auto& [outcome, n] : outcomes) {
        row["calls"][call][outcome] = n;
        callsN += n;
        if (isEngineBacked(outcome)) engineN += n;
      }
    }
    for (const auto& [law, n] : r.authored) authoredN += n;
    row["totals"] = {{"calls", callsN}, {"engine_backed", engineN}, {"authored_reports", authoredN}};
    roles[name] = row;
    roleCalls += callsN;
    roleAuthored += authoredN;
  }
  if (!t.roles.empty()) {
    totals["role_calls"] = roleCalls;
    totals["role_authored_reports"] = roleAuthored;
  }
  nlohmann::json out = {{"totals", totals}, {"calls", calls},       {"hooks", hooks},
                        {"authored", authored}, {"models", models}, {"verdict", verdict(totals)}};
  if (!t.roles.empty()) out["roles"] = roles;
  if (!t.tallies.empty()) out["tallies"] = t.tallies;
  // The base of truth, in one sentence: what Geant4 simulated in this scope.
  if (const auto g4 = t.tallies.find("geant4.events"); g4 != t.tallies.end()) {
    const auto get = [&](const char* section) {
      double n = 0.0;
      if (const auto it = t.tallies.find(section); it != t.tallies.end())
        for (const auto& [k, v] : it->second) n += v;
      return n;
    };
    std::ostringstream os;
    os << " Geant4 simulated " << static_cast<long long>(get("geant4.events")) << " events: "
       << static_cast<long long>(get("geant4.tracks_by_particle")) << " tracks, "
       << static_cast<long long>(get("geant4.steps_by_process")) << " steps";
    if (const auto it = t.tallies.find("geant4.steps_by_process"); it != t.tallies.end() && !it->second.empty()) {
      std::vector<std::pair<double, std::string>> top;
      for (const auto& [k, v] : it->second) top.emplace_back(-v, k);
      std::sort(top.begin(), top.end());
      os << " (most steps: ";
      for (std::size_t i = 0; i < top.size() && i < 3; ++i)
        os << (i ? ", " : "") << top[i].second << " " << static_cast<long long>(-top[i].first);
      os << ")";
    }
    os << ".";
    out["verdict"] = out["verdict"].get<std::string>() + os.str();
  }
  if (const auto torch = t.tallies.find("torch.forwards_by_model"); torch != t.tallies.end()) {
    double n = 0.0;
    for (const auto& [k, v] : torch->second) n += v;
    std::ostringstream os;
    os << " Torch ran " << static_cast<long long>(n) << " forward passes over " << torch->second.size()
       << " models";
    if (const auto train = t.tallies.find("torch.train_steps_by_learner"); train != t.tallies.end()) {
      double m = 0.0;
      for (const auto& [k, v] : train->second) m += v;
      os << " and " << static_cast<long long>(m) << " training steps";
    }
    os << ".";
    out["verdict"] = out["verdict"].get<std::string>() + os.str();
  } else if (const auto train = t.tallies.find("torch.train_steps_by_learner"); train != t.tallies.end()) {
    double m = 0.0;
    for (const auto& [k, v] : train->second) m += v;
    std::ostringstream os;
    os << " Torch ran " << static_cast<long long>(m) << " training steps.";
    out["verdict"] = out["verdict"].get<std::string>() + os.str();
  }
  if (!missing.empty()) out["models_missing"] = missing;
  if (!s.suppressed.empty()) out["suppressed_records"] = s.suppressed;
  if (!t.counters.empty()) out["counters"] = t.counters;
  return out;
}

}  // namespace

nlohmann::json summary() {
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  nlohmann::json out = summarizeLocked(s, s.session);
  if (s.batches > 0) out["batches"] = s.batches;
  return out;
}

nlohmann::json batchSummary(long long runId) {
  if (!active()) return nullptr;
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (s.finished) return nullptr;
  nlohmann::json report = summarizeLocked(s, s.batch);
  // Session-wide sections stay in the run summary; a batch lists only what happened in it.
  report.erase("suppressed_records");
  ++s.batches;
  report["batch"] = s.batches;
  if (runId >= 0) report["run_id"] = runId;
  s.batch.clear();
  if (s.file.is_open()) {
    nlohmann::json line = {{"schema", "trech_trace_v1"}, {"seq", ++s.seq},  {"level", "summary"},
                           {"cat", "summary"},           {"msg", "batch attribution summary"},
                           {"data", report}};
    s.file << line.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace) << '\n';
    s.file.flush();
  }
  nlohmann::json cats = nlohmann::json::array();
  for (const auto& c : s.options.categories) cats.push_back(c);
  const std::string dumped = report.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace);
  std::uint64_t hash = 14695981039346656037ull;
  for (unsigned char c : dumped) {
    hash ^= c;
    hash *= 1099511628211ull;
  }
  std::ostringstream hex;
  hex << std::hex;
  hex.width(16);
  hex.fill('0');
  hex << hash;
  nlohmann::json ref = {{"schema", "trech_trace_ref_v1"},
                        {"level", levelName(s.options.level)},
                        {"categories", cats},
                        {"path", s.options.path},
                        {"batch", s.batches},
                        {"seq", s.seq},
                        {"summary_hash", hex.str()},
                        {"totals", report.at("totals")},
                        {"verdict", report.at("verdict")}};
  return ref;
}

void finish() {
  if (!active()) return;
  const nlohmann::json report = summary();
  auto& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (s.finished) return;
  // The summary is the point of every level, so the category filter never drops it.
  if (s.file.is_open()) {
    nlohmann::json line = {{"schema", "trech_trace_v1"}, {"seq", ++s.seq},  {"level", "summary"},
                           {"cat", "summary"},           {"msg", "run attribution summary"},
                           {"data", report}};
    s.file << line.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace) << '\n';
    s.file.flush();
  }
  // A short human table on stderr: the answer to "engine or authored?" without opening a file.
  std::ostringstream os;
  os << "TRECH trace summary: " << report.at("verdict").get<std::string>() << '\n';
  for (const auto& [call, row] : report.at("calls").items()) {
    os << "  ctx." << call << ":";
    for (const auto& [outcome, n] : row.items()) {
      if (outcome != "total") os << " " << outcome << "=" << n.dump();
    }
    os << '\n';
  }
  for (const auto& [hook, row] : report.at("hooks").items()) {
    os << "  hook " << hook << ": invocations=" << row.at("invocations").dump()
       << " emits=" << row.at("emits").dump()
       << " emits_without_inference=" << row.at("emits_without_inference").dump() << '\n';
  }
  for (const auto& [law, n] : report.at("authored").items()) {
    os << "  authored " << law << ": " << n.dump() << '\n';
  }
  if (report.contains("counters")) {
    for (const auto& [name, n] : report.at("counters").items()) {
      os << "  counter " << name << ": " << n.dump() << '\n';
    }
  }
  if (report.contains("tallies")) {
    // Largest entries first, at most six per section.
    for (const auto& [section, entries] : report.at("tallies").items()) {
      std::vector<std::pair<double, std::string>> rows;
      for (const auto& [key, n] : entries.items()) rows.emplace_back(-n.get<double>(), key);
      std::sort(rows.begin(), rows.end());
      os << "  " << section << ":";
      for (std::size_t i = 0; i < rows.size() && i < 6; ++i) {
        std::ostringstream value;
        value << -rows[i].first;
        os << " " << rows[i].second << "=" << value.str();
      }
      if (rows.size() > 6) os << " (+" << rows.size() - 6 << " more)";
      os << '\n';
    }
  }
  if (report.contains("models_missing")) {
    os << "  models missing (ctx.predict/cascade return null for them): "
       << report.at("models_missing").dump() << '\n';
  }
  if (s.file.is_open()) os << "  full trace: " << s.options.path << '\n';
  std::cerr << os.str();
  if (s.file.is_open()) s.file.close();
  s.finished = true;
}

}  // namespace trech::trace
