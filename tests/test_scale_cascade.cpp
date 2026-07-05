// Unit test for ScaleCascade: the multi-scale statistical-inference cascade.
// Covers scale ordering (independent of registration order), output->input
// chaining across scales, missing-input recording, unscaled-runs-last, and
// graceful skipping of unloaded stages.  Geant4-free: builds tiny generic
// surrogates from temp JSON files and chains them.

#include "trech/ml/ScaleCascade.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <memory>
#include <string>
#include <unordered_map>
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

// A one-layer linear generic model: out = bias + sum(w_i * in_i), no scaling.
std::unique_ptr<trech::ml::GenericSurrogate> makeLinear(
    const std::string& file, const std::vector<std::string>& in,
    const std::string& out, const std::vector<double>& weights, double bias) {
  std::string wjson = "[[";
  for (std::size_t i = 0; i < weights.size(); ++i) {
    wjson += std::to_string(weights[i]);
    if (i + 1 < weights.size()) wjson += ",";
  }
  wjson += "]]";
  std::string infeat = "[";
  for (std::size_t i = 0; i < in.size(); ++i) {
    infeat += "\"" + in[i] + "\"";
    if (i + 1 < in.size()) infeat += ",";
  }
  infeat += "]";
  const std::string path = std::string("./") + file;
  {
    std::ofstream f(path);
    f << "{\"model\":\"generic_surrogate_v1\","
      << "\"input_features\":" << infeat << ","
      << "\"output_features\":[\"" << out << "\"],"
      << "\"layers\":[{\"weights\":" << wjson << ",\"bias\":[" << bias
      << "],\"activation\":\"none\"}]}";
  }
  auto m = std::make_unique<trech::ml::GenericSurrogate>();
  m->load(path);
  std::remove(path.c_str());
  return m;
}

}  // namespace

int main() {
  using trech::ml::DimensionScale;

  // parse/name round-trip.
  expect(trech::ml::parseDimensionScale("atomic") == DimensionScale::kAtomic,
         "parse atomic");
  expect(trech::ml::parseDimensionScale("macro") == DimensionScale::kMacro,
         "parse macro");
  expect(trech::ml::parseDimensionScale("") == DimensionScale::kUnscaled,
         "parse empty -> unscaled");
  expect(trech::ml::parseDimensionScale("bogus") == DimensionScale::kUnscaled,
         "parse unknown -> unscaled");
  expect(std::string(trech::ml::dimensionScaleName(DimensionScale::kMeso)) ==
             "meso",
         "name meso");
  expect(std::string(trech::ml::dimensionScaleName(DimensionScale::kUnscaled)) ==
             "unscaled",
         "name unscaled");

  // 1) Two-stage chain across scales: nano feeds meso.  Register meso FIRST to
  //    prove the cascade orders by scale, not by registration order.
  {
    auto nano = makeLinear("test_cascade_nano.json", {"proton_density"},
                           "nano_signal", {2.0}, 1.0);   // 2*pd + 1
    auto meso = makeLinear("test_cascade_meso.json", {"nano_signal"},
                           "observed", {3.0}, 0.5);       // 3*ns + 0.5
    expect(nano->loaded() && meso->loaded(), "both stage models loaded");

    trech::ml::ScaleCascade cascade;
    cascade.addStage("meso", DimensionScale::kMeso, meso.get());
    cascade.addStage("nano", DimensionScale::kNano, nano.get());

    const auto r = cascade.run({{"proton_density", 5.0}});
    expect(r.stagesRun == 2, "two stages ran");
    // nano_signal = 2*5+1 = 11 ; observed = 3*11+0.5 = 33.5
    expect(r.context.count("nano_signal") &&
               approx(r.context.at("nano_signal"), 11.0),
           "nano stage produced nano_signal=11");
    expect(r.context.count("observed") &&
               approx(r.context.at("observed"), 33.5),
           "meso stage consumed nano_signal -> observed=33.5");
    // Executed order is nano (lower scale) then meso, despite reverse reg.
    expect(r.stages.size() == 2 && r.stages[0].model == "nano" &&
               r.stages[1].model == "meso",
           "executed in ascending-scale order (nano before meso)");
    expect(r.stages[0].missingInputs.empty(),
           "nano input present in seed (no missing)");
    expect(r.stages[1].missingInputs.empty(),
           "meso input produced by nano stage (no missing)");
    expect(r.stages[1].outputs.size() == 1 &&
               r.stages[1].outputs[0] == "observed",
           "meso recorded its output name");
    // The seed itself is preserved in the context.
    expect(r.context.count("proton_density") &&
               approx(r.context.at("proton_density"), 5.0),
           "seed preserved in context");
  }

  // 2) Missing-input recording: a declared input absent from the context is
  //    surfaced (defaulted to 0, not hidden).
  {
    auto m = makeLinear("test_cascade_missing.json", {"x", "y"}, "z", {1.0, 1.0},
                        0.0);  // z = x + y
    trech::ml::ScaleCascade cascade;
    cascade.addStage("m", DimensionScale::kMicro, m.get());
    const auto r = cascade.run({{"x", 4.0}});  // y missing -> 0
    expect(r.stagesRun == 1, "missing-input stage still runs");
    expect(r.context.count("z") && approx(r.context.at("z"), 4.0),
           "missing input defaults to 0 (z = 4 + 0)");
    expect(r.stages.size() == 1 && r.stages[0].missingInputs.size() == 1 &&
               r.stages[0].missingInputs[0] == "y",
           "missing input 'y' recorded");
  }

  // 3) Unloaded / null stage is recorded but skipped (graceful degradation).
  {
    auto ok = makeLinear("test_cascade_ok.json", {"a"}, "b", {2.0}, 0.0);
    trech::ml::ScaleCascade cascade;
    cascade.addStage("ok", DimensionScale::kNano, ok.get());
    cascade.addStage("null_stage", DimensionScale::kMeso, nullptr);
    const auto r = cascade.run({{"a", 3.0}});
    expect(r.stagesRun == 1, "only the loaded stage counts as run");
    expect(r.stages.size() == 2, "both stages recorded in trace");
    expect(r.stages[0].ran && !r.stages[1].ran,
           "loaded stage ran, null stage did not");
    expect(r.context.count("b") && approx(r.context.at("b"), 6.0),
           "loaded stage still produced its output");
  }

  // 4) Unscaled model runs LAST (after macro), where it can see everything.
  {
    auto macro = makeLinear("test_cascade_macro.json", {"seed_v"}, "macro_out",
                            {1.0}, 0.0);
    auto uns = makeLinear("test_cascade_uns.json", {"macro_out"}, "final_out",
                          {1.0}, 0.0);
    trech::ml::ScaleCascade cascade;
    cascade.addStage("unscaled", DimensionScale::kUnscaled, uns.get());
    cascade.addStage("macro", DimensionScale::kMacro, macro.get());
    const auto r = cascade.run({{"seed_v", 7.0}});
    expect(r.stages.size() == 2 && r.stages[0].model == "macro" &&
               r.stages[1].model == "unscaled",
           "unscaled stage runs after macro");
    expect(r.context.count("final_out") &&
               approx(r.context.at("final_out"), 7.0),
           "unscaled stage consumed the macro output");
  }

  if (failures == 0) {
    std::printf("test_scale_cascade: all checks passed\n");
    return 0;
  }
  std::fprintf(stderr, "test_scale_cascade: %d check(s) failed\n", failures);
  return 1;
}
