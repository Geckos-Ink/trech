// Unit test for StateEvolution: the engine-side per-element inference operator
// that replaces hand-written per-element rate laws in scenario JavaScript.
// Covers the d_<field>_dt / set_<field> naming convention, rate accumulation
// across stages, intermediates chaining by scale band, declared bounds, the
// reserved `dt` input, aux/shared precedence, missing-input and
// unapplied-output reporting, aggregated per-element coverage, and graceful
// skipping of unloaded stages.  Geant4-free: builds tiny generic surrogates
// from temp JSON files.

#include "trech/ml/StateEvolution.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include "trech/ml/GenericSurrogate.hpp"

namespace {

int failures = 0;

void expect(bool cond, const char* msg) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", msg);
    ++failures;
  }
}

bool approx(double a, double b, double tol = 1e-9) {
  return std::abs(a - b) <= tol;
}

std::string jsonStringArray(const std::vector<std::string>& items) {
  std::string out = "[";
  for (std::size_t i = 0; i < items.size(); ++i) {
    out += "\"" + items[i] + "\"";
    if (i + 1 < items.size()) out += ",";
  }
  return out + "]";
}

// A one-layer linear generic model with unit scaling:
//   out_o = bias[o] + sum_i weights[o][i] * in_i
// `radius` >= 0 attaches a MEASURED per-input training hull so coverage is
// precisely controllable; a negative radius leaves the model hull-free (the
// heuristic 3-sigma default, domainMeasured false).
std::unique_ptr<trech::ml::GenericSurrogate> makeLinear(
    const std::string& file, const std::vector<std::string>& in,
    const std::vector<std::string>& out,
    const std::vector<std::vector<double>>& weights,
    const std::vector<double>& bias, double radius = -1.0) {
  std::string wjson = "[";
  for (std::size_t o = 0; o < weights.size(); ++o) {
    wjson += "[";
    for (std::size_t i = 0; i < weights[o].size(); ++i) {
      wjson += std::to_string(weights[o][i]);
      if (i + 1 < weights[o].size()) wjson += ",";
    }
    wjson += "]";
    if (o + 1 < weights.size()) wjson += ",";
  }
  wjson += "]";
  std::string bjson = "[";
  for (std::size_t o = 0; o < bias.size(); ++o) {
    bjson += std::to_string(bias[o]);
    if (o + 1 < bias.size()) bjson += ",";
  }
  bjson += "]";
  std::string means = "[", stds = "[", radii = "[";
  for (std::size_t i = 0; i < in.size(); ++i) {
    means += "0.0";
    stds += "1.0";
    radii += std::to_string(radius);
    if (i + 1 < in.size()) {
      means += ",";
      stds += ",";
      radii += ",";
    }
  }
  means += "]";
  stds += "]";
  radii += "]";

  const std::string path = std::string("./") + file;
  {
    std::ofstream f(path);
    f << "{\"model\":\"generic_surrogate_v1\","
      << "\"input_features\":" << jsonStringArray(in) << ","
      << "\"output_features\":" << jsonStringArray(out) << ","
      << "\"input_mean\":" << means << ",\"input_std\":" << stds << ",";
    if (radius >= 0.0) {
      f << "\"input_domain\":{\"standardized_radius\":" << radii << "},";
    }
    f << "\"layers\":[{\"weights\":" << wjson << ",\"bias\":" << bjson
      << ",\"activation\":\"none\"}]}";
  }
  auto m = std::make_unique<trech::ml::GenericSurrogate>();
  m->load(path);
  std::remove(path.c_str());
  return m;
}

// Two elements, two fields (a, b), one aux (k).
trech::ml::EvolutionRequest twoElementRequest(double dt) {
  trech::ml::EvolutionRequest req;
  req.fields.push_back({"a", 0.0, 1.0});
  req.fields.push_back({"b", 0.0, 1000.0});
  req.auxNames.push_back("k");
  req.elementCount = 2;
  req.state = {0.10, 300.0,   // element 0: a=0.10, b=300
               0.50, 320.0};  // element 1: a=0.50, b=320
  req.aux = {1.0, 2.0};       // k = 1.0 and 2.0
  req.dt = dt;
  return req;
}

}  // namespace

int main() {
  using trech::ml::DimensionScale;
  using trech::ml::EvolutionRequest;
  using trech::ml::EvolutionResult;
  using trech::ml::StateEvolution;

  // Naming convention is engine-owned and exposed, so callers/trainers agree.
  expect(StateEvolution::rateOutputName("gel") == "d_gel_dt", "rate name");
  expect(StateEvolution::assignOutputName("gel") == "set_gel", "assign name");

  // 1) A rate output integrates over dt and honours the declared upper bound.
  //    d_a_dt = 2*k  ->  element 0: 0.10 + 2*1*0.25 = 0.60
  //                      element 1: 0.50 + 2*2*0.25 = 1.50 -> clamped to 1.0
  {
    auto rate = makeLinear("se_rate.json", {"k"}, {"d_a_dt"}, {{2.0}}, {0.0});
    expect(rate->loaded(), "rate model loads");
    StateEvolution op;
    op.addStage("rate", DimensionScale::kNano, rate.get());
    const EvolutionRequest req = twoElementRequest(0.25);
    const EvolutionResult res = op.evolve(req);
    expect(res.ran, "rate stage ran");
    expect(res.stagesRun == 1, "one stage ran");
    expect(res.elementsEvolved == 2, "both elements evolved");
    // The honest inference count: a batched operator does not hide N
    // predictions behind one call.
    expect(res.inferenceCount == 2, "inference count = stages * elements");
    expect(approx(res.state[0], 0.60), "element 0 integrated");
    expect(approx(res.state[2], 1.0), "element 1 clamped to declared max");
    // Untouched fields keep their value exactly.
    expect(approx(res.state[1], 300.0), "unaddressed field unchanged (e0)");
    expect(approx(res.state[3], 320.0), "unaddressed field unchanged (e1)");
    expect(res.stages.size() == 1 && res.stages[0].integratedFields.size() == 1 &&
               res.stages[0].integratedFields[0] == "a",
           "trace reports the integrated field");
    expect(res.stages[0].assignedFields.empty(), "no assigned fields");
  }

  // 2) The lower bound holds too (a negative rate cannot drive a below 0).
  {
    auto rate = makeLinear("se_neg.json", {"k"}, {"d_a_dt"}, {{-10.0}}, {0.0});
    StateEvolution op;
    op.addStage("rate", DimensionScale::kNano, rate.get());
    const EvolutionResult res = op.evolve(twoElementRequest(1.0));
    expect(approx(res.state[0], 0.0), "clamped to declared min");
    expect(approx(res.state[2], 0.0), "clamped to declared min (e1)");
  }

  // 3) Two stages driving the SAME field accumulate rather than overwrite --
  //    competing reactions heating one parcel, without the caller sequencing
  //    them.  d_b_dt = 4 (nano) and d_b_dt = 6*k (meso), dt = 0.5:
  //    element 0: 300 + (4 + 6*1)*0.5 = 305 ; element 1: 320 + (4 + 12)*0.5 = 328
  {
    auto slow = makeLinear("se_acc1.json", {"k"}, {"d_b_dt"}, {{0.0}}, {4.0});
    auto fast = makeLinear("se_acc2.json", {"k"}, {"d_b_dt"}, {{6.0}}, {0.0});
    StateEvolution op;
    op.addStage("slow", DimensionScale::kNano, slow.get());
    op.addStage("fast", DimensionScale::kMeso, fast.get());
    const EvolutionResult res = op.evolve(twoElementRequest(0.5));
    expect(res.stagesRun == 2, "two stages ran");
    expect(res.inferenceCount == 4, "2 stages x 2 elements");
    expect(approx(res.state[1], 305.0), "rates accumulate (e0)");
    expect(approx(res.state[3], 328.0), "rates accumulate (e1)");
  }

  // 4) An intermediate chains up the ladder within one call, and the higher
  //    stage is ordered by SCALE, not registration order (register macro first).
  //    nano: drive = 3*k  ->  macro: d_a_dt = drive  ->  a += 3*k*dt
  //    element 0: 0.10 + 3*1*0.1 = 0.40 ; element 1: 0.50 + 3*2*0.1 = 1.10 -> 1.0
  {
    auto lower = makeLinear("se_low.json", {"k"}, {"drive"}, {{3.0}}, {0.0});
    auto upper = makeLinear("se_up.json", {"drive"}, {"d_a_dt"}, {{1.0}}, {0.0});
    StateEvolution op;
    op.addStage("upper", DimensionScale::kMacro, upper.get());  // declared first
    op.addStage("lower", DimensionScale::kNano, lower.get());
    const EvolutionResult res = op.evolve(twoElementRequest(0.1));
    expect(res.stages.size() == 2 && res.stages[0].model == "lower",
           "stages execute in ascending scale order");
    expect(approx(res.state[0], 0.40), "intermediate chained (e0)");
    expect(approx(res.state[2], 1.0), "intermediate chained + clamped (e1)");
    expect(res.stages[0].intermediateOutputs.size() == 1 &&
               res.stages[0].intermediateOutputs[0] == "drive",
           "intermediate reported on the producing stage");
    expect(res.stages[1].missingInputs.empty(),
           "a lower stage's intermediate is not a missing input");
  }

  // 5) The SAME two models with the scale order reversed cannot chain: the
  //    consumer now runs first, so `drive` is a forward reference -> reported
  //    missing, defaulted to 0, and the state does not move.
  {
    auto lower = makeLinear("se_low2.json", {"k"}, {"drive"}, {{3.0}}, {0.0});
    auto upper = makeLinear("se_up2.json", {"drive"}, {"d_a_dt"}, {{1.0}}, {0.0});
    StateEvolution op;
    op.addStage("upper", DimensionScale::kNano, upper.get());
    op.addStage("lower", DimensionScale::kMacro, lower.get());
    const EvolutionResult res = op.evolve(twoElementRequest(0.1));
    expect(res.stages[0].model == "upper", "reversed order executes upper first");
    expect(res.stages[0].missingInputs.size() == 1 &&
               res.stages[0].missingInputs[0] == "drive",
           "forward reference reported missing, not silently zero-filled");
    expect(approx(res.state[0], 0.10), "no movement from a missing input");
  }

  // 6) set_<field> assigns immediately and is visible to a higher stage, while
  //    a rate on the same field still integrates on top of the assigned value.
  //    nano: set_b = 500 ; macro: d_b_dt = 0.1*b (reads the ASSIGNED 500)
  //    -> 500 + 0.1*500*2.0 = 600 for both elements.
  {
    auto assign = makeLinear("se_set.json", {"k"}, {"set_b"}, {{0.0}}, {500.0});
    auto grow = makeLinear("se_grow.json", {"b"}, {"d_b_dt"}, {{0.1}}, {0.0});
    StateEvolution op;
    op.addStage("assign", DimensionScale::kNano, assign.get());
    op.addStage("grow", DimensionScale::kMacro, grow.get());
    const EvolutionResult res = op.evolve(twoElementRequest(2.0));
    expect(approx(res.state[1], 600.0), "assignment visible to higher stage (e0)");
    expect(approx(res.state[3], 600.0), "assignment visible to higher stage (e1)");
    expect(res.stages[0].assignedFields.size() == 1 &&
               res.stages[0].assignedFields[0] == "b",
           "trace reports the assigned field");
  }

  // 7) The reserved `dt` input: an operator that predicts a per-STEP amount
  //    rather than a rate can read the bounded step it is being integrated
  //    over.  d_a_dt = 1/dt with dt = 0.2 -> a += 5 * 0.2 = 1.0 (then clamped).
  {
    auto perStep = makeLinear("se_dt.json", {"dt"}, {"d_a_dt"}, {{0.0}}, {5.0});
    StateEvolution op;
    op.addStage("perStep", DimensionScale::kNano, perStep.get());
    EvolutionRequest req = twoElementRequest(0.2);
    req.state[0] = 0.0;
    const EvolutionResult res = op.evolve(req);
    expect(res.stages[0].missingInputs.empty(), "dt is a resolved input");
    expect(approx(res.state[0], 1.0), "dt-driven step integrated");
  }

  // 8) Shared run-constant facts resolve; an undeclared name is reported.
  //    A per-element field SHADOWS a shared key of the same name (the state is
  //    the more specific meaning), which is what keeps a Geant4 seed and a live
  //    state field from silently colliding.
  {
    auto model = makeLinear("se_shared.json", {"g4_fact", "a", "nope"},
                            {"d_b_dt"}, {{1.0, 100.0, 1.0}}, {0.0});
    StateEvolution op;
    op.addStage("m", DimensionScale::kNano, model.get());
    EvolutionRequest req = twoElementRequest(1.0);
    req.shared["g4_fact"] = 7.0;
    req.shared["a"] = 999.0;  // must NOT win over the per-element field `a`
    const EvolutionResult res = op.evolve(req);
    expect(res.stages[0].missingInputs.size() == 1 &&
               res.stages[0].missingInputs[0] == "nope",
           "only the genuinely absent input is reported missing");
    // element 0: b = 300 + (7 + 100*0.10 + 0)*1.0 = 317
    expect(approx(res.state[1], 317.0), "shared fact used, field shadows shared");
    // element 1: b = 320 + (7 + 100*0.50)*1.0 = 377
    expect(approx(res.state[3], 377.0), "per-element field varies the result");
  }

  // 9) An output aimed at a field the caller never declared updates nothing and
  //    is REPORTED, so a stale model against a changed scenario is visible
  //    instead of looking like physics that quietly stopped.
  {
    auto model = makeLinear("se_unapplied.json", {"k"}, {"d_ghost_dt", "d_a_dt"},
                            {{1.0}, {1.0}}, {0.0, 0.0});
    StateEvolution op;
    op.addStage("m", DimensionScale::kNano, model.get());
    const EvolutionResult res = op.evolve(twoElementRequest(0.1));
    expect(res.stages[0].unappliedFieldOutputs.size() == 1 &&
               res.stages[0].unappliedFieldOutputs[0] == "d_ghost_dt",
           "output for an undeclared field reported");
    expect(approx(res.state[0], 0.20), "the declared field still updates");
  }

  // 10) Per-element coverage aggregates: with a measured hull of |z| <= 1.5 and
  //     inputs k = 1.0 (in) and k = 2.0 (out), exactly one element extrapolates,
  //     and the flagged input name is surfaced.
  {
    auto model = makeLinear("se_cov.json", {"k"}, {"d_a_dt"}, {{1.0}}, {0.0},
                            /*radius=*/1.5);
    expect(model->domainMeasured(), "measured hull carried");
    StateEvolution op;
    op.addStage("m", DimensionScale::kNano, model.get());
    const EvolutionResult res = op.evolve(twoElementRequest(0.1));
    expect(res.stages[0].domainMeasured, "stage reports measured domain");
    expect(res.stages[0].elementsOutOfDomain == 1,
           "exactly one element out of domain");
    expect(res.outOfDomainInferenceCount == 1, "run-level OOD inference count");
    expect(res.stagesExtrapolating == 1, "stage flagged extrapolating");
    expect(approx(res.stages[0].maxExtrapolation, 0.5),
           "worst overflow in training-sigma units");
    expect(res.stages[0].outOfDomainInputs.size() == 1 &&
               res.stages[0].outOfDomainInputs[0] == "k",
           "flagged input surfaced");
  }

  // 11) A hull-free model reports the heuristic default honestly, and an
  //     in-domain run flags nothing.
  {
    auto model = makeLinear("se_nohull.json", {"k"}, {"d_a_dt"}, {{1.0}}, {0.0});
    StateEvolution op;
    op.addStage("m", DimensionScale::kNano, model.get());
    const EvolutionResult res = op.evolve(twoElementRequest(0.1));
    expect(!res.stages[0].domainMeasured,
           "no measured hull -> domainMeasured false");
    expect(res.stages[0].elementsOutOfDomain == 0, "k=1,2 inside heuristic 3 sigma");
    expect(res.stagesExtrapolating == 0, "nothing flagged");
    expect(!res.stages[0].hasHoldout, "illustrative map carries no holdout");
  }

  // 12) Graceful degradation: an unloaded stage is recorded and skipped, and a
  //     request with no elements leaves the state untouched.
  {
    auto missing = std::make_unique<trech::ml::GenericSurrogate>();
    expect(!missing->loaded(), "unloaded model");
    auto rate = makeLinear("se_ok.json", {"k"}, {"d_a_dt"}, {{2.0}}, {0.0});
    StateEvolution op;
    op.addStage("gone", DimensionScale::kNano, missing.get());
    op.addStage("ok", DimensionScale::kMeso, rate.get());
    const EvolutionResult res = op.evolve(twoElementRequest(0.25));
    expect(res.stages.size() == 2, "skipped stage still recorded");
    expect(!res.stages[0].ran && res.stages[1].ran, "only the loaded stage ran");
    expect(res.stagesRun == 1, "stagesRun counts loaded stages only");
    expect(approx(res.state[0], 0.60), "the loaded stage still evolved");

    EvolutionRequest empty = twoElementRequest(0.25);
    empty.elementCount = 0;
    const EvolutionResult none = op.evolve(empty);
    expect(!none.ran && none.inferenceCount == 0, "no elements -> nothing ran");
    expect(none.state == empty.state, "state returned untouched");
  }

  // 13) Determinism: the same request evaluated twice is bit-identical.
  {
    auto lower = makeLinear("se_det1.json", {"k", "a"}, {"drive"},
                            {{0.7, 1.3}}, {0.2});
    auto upper = makeLinear("se_det2.json", {"drive", "b"}, {"d_a_dt", "d_b_dt"},
                            {{0.11, 0.0007}, {0.9, -0.01}}, {0.0, 1.0});
    StateEvolution op;
    op.addStage("lower", DimensionScale::kNano, lower.get());
    op.addStage("upper", DimensionScale::kMacro, upper.get());
    const EvolutionRequest req = twoElementRequest(0.37);
    const EvolutionResult a = op.evolve(req);
    const EvolutionResult b = op.evolve(req);
    expect(a.state == b.state, "evolve is a pure function of its inputs");
  }

  if (failures == 0) {
    std::printf("test_state_evolution: OK\n");
  }
  return failures == 0 ? 0 : 1;
}
