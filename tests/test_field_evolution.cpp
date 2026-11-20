// The engine, not the caller, picks the prediction method. Covered here:
//  1. the generic MethodArbiter, domain-free: two methods, each better in its own context
//     domain, and the selection follows the domains;
//  2. FieldEvolution on one declared system graded against two references: the selection
//     follows the evidence (a conducting reference vs a frozen one);
//  3. a method registered later joins the arbitration with no other change and emerges where
//     it is best;
//  4. a method that cannot represent the declared system is excluded with its reason and the
//     arbitration still runs among the others;
//  5. an exported arbiter (with the learned operator's state) restored in a later run: frozen
//     on its own regime it beats learning from scratch and learns nothing; on a held-out
//     exchange regime it falls back to the prior where its evidence never reached and stays
//     near the oracle.
#include "trech/ml/FieldEvolution.hpp"
#include "trech/ml/MethodArbiter.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

using trech::ml::FieldEvolution;

namespace {
int failures = 0;
void check(bool ok, const std::string& message) {
  if (!ok) { std::fprintf(stderr, "FAIL: %s\n", message.c_str()); ++failures; }
}

// Independent reference: explicit 1-D slab conduction with the same exchanges.
struct Column {
  std::vector<double> t;
  double dz, kappa;
  void advance(double seconds, double rate, double target) {
    const double dt = 0.2 * dz * dz / kappa;
    for (double done = 0; done < seconds - 1e-12;) {
      const double h = std::min(dt, seconds - done);
      std::vector<double> next = t;
      for (std::size_t c = 0; c < t.size(); ++c) {
        const double below = c ? t[c - 1] : t[c], above = c + 1 < t.size() ? t[c + 1] : t[c];
        next[c] += kappa * h / (dz * dz) * (below - 2 * t[c] + above);
      }
      next[0] += rate * (target - next[0]) * h;
      t = next; done += h;
    }
  }
};

// The reference of the current frame, visible to the test-only method registered in case 3.
const std::vector<double>* gNextReference = nullptr;

class ForesightMethod final : public trech::ml::FieldMethod {
 public:
  ForesightMethod() : FieldMethod("test_foresight") {}
  std::string build(const trech::ml::FieldSystem&, const trech::ml::FieldEvolutionInput&) override { return {}; }
  void advance(const trech::ml::FieldCall& call) override { field_ = gNextReference ? *gNextReference : call.state; }
  std::vector<double> prediction() const override { return field_; }
 private:
  std::vector<double> field_;
};

nlohmann::json run(bool frozenReference, double viscosity, std::vector<double>* reference = nullptr) {
  const int cells = 8;
  const double heightMm = 120, slab = heightMm / cells, kappa = 1e-5, rate = 0.2, target = 10;
  std::vector<std::array<double, 3>> lo, hi;
  for (int c = 0; c < cells; ++c) { lo.push_back({0, 0, c * slab}); hi.push_back({30, 30, (c + 1) * slab}); }
  trech::ml::FieldRegion region;
  region.shape = "box"; region.sizeMm = {30, 30, heightMm};
  trech::ml::FieldProperties props;
  props.kinematicViscosityM2S = viscosity; props.diffusivityM2S = kappa;  // no gravity: no buoyancy
  trech::ml::FieldEvolutionOptions opt;
  opt.cellMm = 5; opt.minElements = 16; opt.seed = 7;
  FieldEvolution evolution(region, lo, hi, props, std::vector<double>(cells, 0.0), opt);
  Column column{std::vector<double>(cells, 0.0), slab * 1e-3, kappa};
  // Like a scenario, declare at t = 0 with the initial state, then every 2 s.
  for (int frame = 0; frame <= 60; ++frame) {
    if (!frozenReference && frame > 0) column.advance(2.0, rate, target);
    if (reference) { *reference = column.t; gNextReference = reference; }
    trech::ml::FieldEvolutionInput in;
    in.timeS = 2.0 * frame;
    in.rate.assign(cells, 0.0); in.rate[0] = rate;
    in.target.assign(cells, 0.0); in.target[0] = target;
    in.reference = column.t;
    evolution.step(in);
  }
  gNextReference = nullptr;
  return evolution.summary();
}

double share(const nlohmann::json& s, const char* m) { return s.at("methods").at(m).at("selected_share").get<double>(); }
double rmse(const nlohmann::json& s, const char* m) { return s.at("methods").at(m).at("rmse").get<double>(); }

void print(const char* label, const nlohmann::json& s) {
  std::printf("%s: arbitrated %.4f oracle %.4f learned-share %.2f |", label, s.at("arbitrated_rmse").get<double>(),
              s.at("oracle_rmse").get<double>(), s.at("learned_selection_share").get<double>());
  for (const auto& [name, m] : s.at("methods").items())
    if (m.value("available", false))
      std::printf(" %s rmse %.4f share %.2f;", name.c_str(), m.at("rmse").get<double>(), m.at("selected_share").get<double>());
    else
      std::printf(" %s excluded (%s);", name.c_str(), m.at("reason").get<std::string>().c_str());
  std::printf("\n");
  for (const auto& p : s.at("phases")) {
    std::printf("   phase calls %s: arbitrated %.4f oracle %.4f |", p.at("calls").dump().c_str(), p.at("arbitrated_rmse").get<double>(), p.at("oracle_rmse").get<double>());
    for (const auto& [name, m] : p.at("methods").items())
      std::printf(" %s %.4f/%.4f/cov %.2f/sel %.2f", name.c_str(), m.at("rmse").get<double>(), m.at("rmse_common").get<double>(),
                  m.at("coverage").get<double>(), m.at("selected_share").get<double>());
    std::printf("\n");
  }
}

// 1. Domain-free arbitration: method "a" is exact for x < 0 and off by 1 above, "b" the reverse.
void arbiterDomains() {
  trech::ml::MethodArbiterOptions o;
  o.methods = {"a", "b"}; o.features = {"x"}; o.minElements = 16; o.seed = 3; o.fallback = "b";
  trech::ml::MethodArbiter arbiter(o);
  double lateCorrect = 0, lateTotal = 0;
  for (int call = 0; call < 40; ++call) {
    trech::ml::MethodArbiterBatch b;
    b.time = call; b.count = 64;
    for (int i = 0; i < 64; ++i) {
      const double x = -1.0 + 2.0 * ((i * 37 + call * 11) % 64) / 63.0, truth = std::sin(3 * x + call);
      b.features.push_back(x);
      b.predictions.push_back(truth + (x < 0 ? 0.0 : 1.0));
      b.predictions.push_back(truth + (x < 0 ? 1.0 : 0.0));
      b.reference.push_back(truth);
    }
    const auto r = arbiter.step(b);
    if (call >= 30)
      for (int i = 0; i < 64; ++i) {
        lateTotal += 1;
        lateCorrect += (r.selection[static_cast<std::size_t>(i)] == (b.features[static_cast<std::size_t>(i)] < 0 ? 0 : 1)) ? 1 : 0;
      }
  }
  const auto s = arbiter.summary();
  std::printf("arbiter domains: late correct share %.3f arbitrated %.4f best single %.4f\n", lateCorrect / lateTotal,
              s.at("arbitrated_rmse").get<double>(), std::min(rmse(s, "a"), rmse(s, "b")));
  check(lateCorrect / lateTotal > 0.95, "the arbiter did not learn which method wins in which context domain");
  check(s.at("arbitrated_rmse").get<double>() < 0.5 * std::min(rmse(s, "a"), rmse(s, "b")),
        "the arbiter did not beat the best single method on complementary methods");
}
}  // namespace

// 5. A learned field arbiter across runs: run the same declared system on an exchange regime,
// optionally restoring an exported state first. Returns the summary; `exported` receives the
// final state (through text, as a later run reads it).
nlohmann::json runRegime(double rate, double target, const nlohmann::json* warm, bool frozen,
                         nlohmann::json* exported, nlohmann::json* restoredBefore = nullptr) {
  const int cells = 8;
  const double heightMm = 120, slab = heightMm / cells, kappa = 1e-5;
  std::vector<std::array<double, 3>> lo, hi;
  for (int c = 0; c < cells; ++c) { lo.push_back({0, 0, c * slab}); hi.push_back({30, 30, (c + 1) * slab}); }
  trech::ml::FieldRegion region;
  region.shape = "box"; region.sizeMm = {30, 30, heightMm};
  trech::ml::FieldProperties props;
  props.kinematicViscosityM2S = 1e-5; props.diffusivityM2S = kappa;
  trech::ml::FieldEvolutionOptions opt;
  opt.cellMm = 5; opt.minElements = 16; opt.seed = 7;
  FieldEvolution evolution(region, lo, hi, props, std::vector<double>(cells, 0.0), opt);
  if (warm) evolution.restore(*warm, frozen);
  Column column{std::vector<double>(cells, 0.0), slab * 1e-3, kappa};
  for (int frame = 0; frame <= 60; ++frame) {
    if (frame > 0) column.advance(2.0, rate, target);
    trech::ml::FieldEvolutionInput in;
    in.timeS = 2.0 * frame;
    in.rate.assign(cells, 0.0); in.rate[0] = rate;
    in.target.assign(cells, 0.0); in.target[0] = target;
    in.reference = column.t;
    evolution.step(in);
    if (frame == 0 && restoredBefore) *restoredBefore = nlohmann::json::parse(evolution.exportState(true).dump());
  }
  if (exported) *exported = nlohmann::json::parse(evolution.exportState(true).dump());
  return evolution.summary();
}

int main() {
  try {
    arbiterDomains();

    // 2. Evidence decides among the built-in methods. Whole-run figures include the first
    //    informative call, which no method can be chosen for by evidence; the later windows
    //    are out-of-sample time for everything learned before them.
    const auto diffusing = run(false, 1e-5), frozen = run(true, 1e-5);
    print("conducting reference", diffusing);
    print("frozen reference", frozen);
    const auto& names = diffusing.at("registered_methods");
    for (const char* m : {"lattice_convective", "lattice_conductive", "learned_operator", "persistence"})
      check(std::find(names.begin(), names.end(), m) != names.end(), std::string("built-in method not registered: ") + m);
    check(share(diffusing, "persistence") < 0.25, "a conducting reference did not make an evolving method emerge");
    check(diffusing.at("arbitrated_rmse").get<double>() < rmse(diffusing, "persistence"),
          "arbitration did not beat persistence on a conducting reference");
    check(diffusing.at("learned_policy_share").get<double>() > 0.1, "the learned per-domain selection was never used");
    for (std::size_t w = 1; w < 3; ++w) {
      const auto& p = diffusing.at("phases").at(w);
      // A single method is a full alternative only where it predicts every cell (a learned
      // operator abstains where it is remote from its support).
      double best = 1e300;
      for (const auto& [name, m] : p.at("methods").items())
        if (m.at("coverage").get<double>() > 0.999) best = std::min(best, m.at("rmse").get<double>());
      check(p.at("arbitrated_rmse").get<double>() <= 1.05 * best + 1e-4,
            "a later window's arbitration did not match the best full-coverage method (window " + std::to_string(w) + ")");
      check(p.at("arbitrated_rmse").get<double>() <= 2.5 * p.at("oracle_rmse").get<double>() + 1e-4,
            "a later window's arbitration is far from the per-cell oracle (window " + std::to_string(w) + ")");
      check(p.at("arbitrated_rmse").get<double>() < 0.5 * p.at("methods").at("persistence").at("rmse").get<double>(),
            "a later window's arbitration did not beat persistence (window " + std::to_string(w) + ")");
    }
    // Away from the exchange every method predicts "no change", so ties there are arbitrary;
    // where they differ, the evidence must remove most of the lattice error.
    const double latticeBest = std::min(rmse(frozen, "lattice_conductive"), rmse(frozen, "lattice_convective"));
    check(frozen.at("arbitrated_rmse").get<double>() < 0.25 * latticeBest,
          "a frozen reference did not make a non-evolving method emerge where methods differ");

    // 4. No viscosity declared: the convective lattice is excluded with its reason.
    const auto still = run(false, 0.0);
    print("no viscosity declared", still);
    const auto& convective = still.at("methods").at("lattice_convective");
    check(!convective.at("available").get<bool>() && !convective.at("reason").get<std::string>().empty(),
          "an inapplicable method was not excluded with a reason");
    check(still.at("graded_cells").get<double>() > 0, "arbitration stopped when one method was inapplicable");
    check(still.at("phases").at(2).at("arbitrated_rmse").get<double>() <
              0.5 * still.at("phases").at(2).at("methods").at("persistence").at("rmse").get<double>(),
          "arbitration without the convective lattice did not beat persistence");

    // 5. Across runs: learn on one exchange regime and export. Deployed frozen on the SAME
    // regime, the carried choice beats learning from scratch. Deployed frozen on a held-out
    // regime (another target and rate), it is the held-out test of the choice.
    {
      nlohmann::json trained, afterSame, atSame, afterHeld, atHeld, continued;
      const auto learning = runRegime(0.2, 10.0, nullptr, false, &trained);
      const auto same = runRegime(0.2, 10.0, &trained, true, &afterSame, &atSame);
      const auto fresh = runRegime(0.5, 4.0, nullptr, false, nullptr);
      const auto held = runRegime(0.5, 4.0, &trained, true, &afterHeld, &atHeld);
      const auto more = runRegime(0.5, 4.0, &trained, false, &continued);
      auto window = [](const nlohmann::json& s, int w) { return s.at("phases").at(w).at("arbitrated_rmse").get<double>(); };
      std::printf("across runs, first/last window arbitrated rmse: learning %.4f/%.4f; same regime frozen %.4f/%.4f; "
                  "held-out regime untrained %.4f/%.4f, frozen %.4f/%.4f (oracle %.4f), continued %.4f/%.4f\n",
                  window(learning, 0), window(learning, 2), window(same, 0), window(same, 2), window(fresh, 0),
                  window(fresh, 2), window(held, 0), window(held, 2),
                  held.at("phases").at(0).at("oracle_rmse").get<double>(), window(more, 0), window(more, 2));
      std::printf("unseen-context share: same regime frozen %.4f, held-out frozen %.4f, continued %.4f\n",
                  same.value("unseen_context_share", 0.0), held.value("unseen_context_share", 0.0),
                  more.value("unseen_context_share", 0.0));
      print("same regime, restored frozen", same);
      print("held-out regime, restored frozen", held);
      check(same.at("restored") == "frozen" && same.value("frozen", false),
            "a frozen restore was not reported in the summary");
      check(window(same, 0) < window(learning, 0) &&
                same.at("arbitrated_rmse").get<double>() < learning.at("arbitrated_rmse").get<double>(),
            "a restored frozen arbiter did not beat learning from scratch on its own regime");
      // Held out: where the restored error laws are all remote (the opening step of a stronger
      // exchange), the median prior is used, so the frozen arbiter stays near the oracle.
      const double heldOracle = held.at("phases").at(0).at("oracle_rmse").get<double>();
      check(window(held, 0) < 1.15 * heldOracle && held.value("unseen_context_share", 0.0) > 0.0,
            "a restored frozen arbiter did not fall back to the prior in contexts its evidence never covered");
      check(held.at("arbitrated_rmse").get<double>() < 0.5 * held.at("methods").at("persistence").at("rmse").get<double>(),
            "a restored frozen arbiter did not beat persistence on a held-out regime");
      check(afterSame.at("arbiter") == atSame.at("arbiter") && afterSame.at("method_states") == atSame.at("method_states") &&
                afterHeld.at("arbiter") == atHeld.at("arbiter") && afterHeld.at("method_states") == atHeld.at("method_states"),
            "a frozen field arbiter or learned method changed while deployed");
      check(atSame.at("arbiter").at("policy_score") == trained.at("arbiter").at("policy_score") &&
                atSame.at("arbiter").at("ew_log") == trained.at("arbiter").at("ew_log"),
            "the restored state was not applied at build");
      check(more.at("restored") == "continued" && !more.contains("frozen") && continued.at("arbiter") != trained.at("arbiter"),
            "a continued restore did not keep learning");

      // A state that does not fit the declared system fails the first step and builds nothing.
      nlohmann::json wrong = trained;
      wrong["cells"] = 9;
      bool threw = false;
      try { runRegime(0.5, 4.0, &wrong, true, nullptr); } catch (const std::invalid_argument&) { threw = true; }
      check(threw, "a field state for another system was accepted");
      bool badFormat = false;
      try { runRegime(0.5, 4.0, &trained.at("arbiter"), true, nullptr); } catch (const std::invalid_argument&) { badFormat = true; }
      check(badFormat, "a field state of another format was accepted");
    }

    // 3. A method registered later joins with no other change (here one that sees the answer).
    trech::ml::registerFieldMethod({"test_foresight", "test", "test only: predicts the coming reference",
                                    [] { return std::make_unique<ForesightMethod>(); }});
    bool duplicateRejected = false;
    try {
      trech::ml::registerFieldMethod({"persistence", "baseline", "duplicate", [] { return std::make_unique<ForesightMethod>(); }});
    } catch (const std::invalid_argument&) { duplicateRejected = true; }
    check(duplicateRejected, "a duplicate method name was accepted");
    std::vector<double> next;
    const auto extended = run(false, 1e-5, &next);
    print("with a registered method", extended);
    check(share(extended, "test_foresight") > 0.8, "a newly registered better method did not emerge");
    check(extended.at("arbitrated_rmse").get<double>() < diffusing.at("arbitrated_rmse").get<double>(),
          "a newly registered better method did not lower the arbitrated error");
    for (std::size_t w = 1; w < 3; ++w)
      check(extended.at("phases").at(w).at("arbitrated_rmse").get<double>() < 1e-9,
            "a newly registered exact method was not used in a later window");
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
  return failures ? 1 : 0;
}
