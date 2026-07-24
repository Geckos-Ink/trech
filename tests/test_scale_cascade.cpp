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

// One-input linear model (out = weight*in + bias) with mean 0 / std 1 and a
// MEASURED training-domain radius, so coverage in/out is precisely controllable.
std::unique_ptr<trech::ml::GenericSurrogate> makeLinearDom(
    const std::string& file, const std::string& in, const std::string& out,
    double weight, double bias, double radius) {
  const std::string path = std::string("./") + file;
  {
    std::ofstream f(path);
    f << "{\"model\":\"generic_surrogate_v1\","
      << "\"input_features\":[\"" << in << "\"],"
      << "\"output_features\":[\"" << out << "\"],"
      << "\"input_mean\":[0.0],\"input_std\":[1.0],"
      << "\"input_domain\":{\"standardized_radius\":[" << radius << "]},"
      << "\"layers\":[{\"weights\":[[" << weight << "]],\"bias\":[" << bias
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

  // 5) Per-stage training-domain coverage (workstream 3): a value that is inside
  //    the low stage's wide hull can land OUTSIDE a higher stage's tighter hull
  //    as it propagates up the ladder -- the cascade flags that stage as
  //    extrapolating instead of trusting a silent guess.
  {
    auto nano = makeLinearDom("test_cov_nano.json", "seed_x", "mid", 1.0, 0.0,
                              10.0);  // radius 10: z=5 is comfortably inside
    auto meso = makeLinearDom("test_cov_meso.json", "mid", "top", 1.0, 0.0,
                              2.0);   // radius 2: z=5 is outside by 3
    trech::ml::ScaleCascade cascade;
    cascade.addStage("nano", DimensionScale::kNano, nano.get());
    cascade.addStage("meso", DimensionScale::kMeso, meso.get());
    const auto r = cascade.run({{"seed_x", 5.0}});
    expect(r.stagesRun == 2, "both coverage stages ran");
    expect(r.stagesExtrapolating == 1, "exactly one stage extrapolated");
    // nano saw seed_x=5 (z=5 < radius 10) -> in-domain.
    expect(r.stages[0].model == "nano" && r.stages[0].inDomain,
           "nano predicted in its trained domain");
    expect(r.stages[0].domainMeasured, "nano reports a measured domain");
    // meso saw mid=5 (z=5 > radius 2) -> out-of-domain by 3.
    expect(r.stages[1].model == "meso" && !r.stages[1].inDomain,
           "meso extrapolated (mid propagated outside its hull)");
    expect(approx(r.stages[1].extrapolation, 3.0),
           "meso extrapolation == |z|-radius == 5-2 == 3");
    expect(r.stages[1].outOfDomainInputs.size() == 1 &&
               r.stages[1].outOfDomainInputs[0] == "mid",
           "meso records 'mid' as the out-of-domain input");
  }

  // 6) A stage with no measured hull uses the heuristic radius and reports it as
  //    such (domainMeasured=false), so an unvalidated map cannot masquerade as a
  //    trained-domain guarantee.
  {
    auto heur = makeLinear("test_cov_heur.json", {"v"}, "w", {1.0}, 0.0);
    trech::ml::ScaleCascade cascade;
    cascade.addStage("heur", DimensionScale::kMicro, heur.get());
    const auto rIn = cascade.run({{"v", 1.0}});  // z=1 < 3 -> in
    expect(rIn.stagesExtrapolating == 0 && rIn.stages[0].inDomain,
           "heuristic stage in-domain for z=1");
    expect(!rIn.stages[0].domainMeasured,
           "heuristic stage reports domain NOT measured");
    const auto rOut = cascade.run({{"v", 9.0}});  // z=9 > 3 -> out
    expect(rOut.stagesExtrapolating == 1 && !rOut.stages[0].inDomain,
           "heuristic stage extrapolates for z=9");
  }

  // 7) Trained-scale-band mismatch + carried held-out accuracy (workstream 3
  //    b + c): a stage run at a scale NOT among its model's trained bands is
  //    flagged off-band; its held-out R2 is surfaced per stage.
  {
    const std::string path = "./test_cov_prov.json";
    {
      std::ofstream f(path);
      f << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"seed_x\"],"
        << "\"output_features\":[\"mid\"],"
        << "\"trained_scale_bands\":[\"nano\"],"
        << "\"holdout\":{\"r2_min\":0.9,\"n\":5},"
        << "\"layers\":[{\"weights\":[[1.0]],\"bias\":[0.0],"
        << "\"activation\":\"none\"}]}";
    }
    auto model = std::make_unique<trech::ml::GenericSurrogate>();
    model->load(path);
    std::remove(path.c_str());
    expect(model->loaded(), "provenance stage model loaded");

    // Declared at MESO but trained on NANO -> scale mismatch.
    trech::ml::ScaleCascade mism;
    mism.addStage("offband", DimensionScale::kMeso, model.get());
    const auto rm = mism.run({{"seed_x", 1.0}});
    expect(rm.stagesScaleMismatched == 1, "one stage applied off its band");
    expect(rm.stages[0].scaleMismatch,
           "meso stage flagged off its nano-trained band");
    expect(rm.stages[0].trainedScale == "nano", "trainedScale reported (nano)");
    expect(rm.stages[0].hasHoldout && approx(rm.stages[0].holdoutR2, 0.9),
           "held-out R2 surfaced on the stage");
    expect(rm.stages[0].holdoutSamples == 5, "held-out sample count surfaced");

    // Declared at NANO (its trained band) -> no mismatch.
    trech::ml::ScaleCascade ok;
    ok.addStage("onband", DimensionScale::kNano, model.get());
    const auto ro = ok.run({{"seed_x", 1.0}});
    expect(ro.stagesScaleMismatched == 0 && !ro.stages[0].scaleMismatch,
           "nano stage on its trained band -> no mismatch");
  }

  // 8) A hand-authored map with no trained bands is NEVER flagged off-band
  //    (unknown band -> do not judge) and reports no held-out accuracy.
  {
    auto plain = makeLinear("test_cov_plain.json", {"a"}, "b", {1.0}, 0.0);
    trech::ml::ScaleCascade cascade;
    cascade.addStage("plain", DimensionScale::kMacro, plain.get());
    const auto r = cascade.run({{"a", 1.0}});
    expect(r.stagesScaleMismatched == 0 && !r.stages[0].scaleMismatch,
           "no trained bands -> never an off-band mismatch");
    expect(r.stages[0].trainedScale.empty(), "trainedScale empty when unknown");
    expect(!r.stages[0].hasHoldout, "no held-out metrics on an illustrative map");
  }

  // 9) Starved-region signal surfaced per stage + run-level (density inside the
  //    hull): a stage whose input lands in an empty training bin is flagged.
  {
    const std::string path = "./test_cov_occ.json";
    {
      std::ofstream f(path);
      f << "{\"model\":\"generic_surrogate_v1\","
        << "\"input_features\":[\"seed_x\"],"
        << "\"output_features\":[\"mid\"],"
        << "\"input_mean\":[5.0],\"input_std\":[3.0],"
        << "\"input_domain\":{\"standardized_radius\":[2.0],"
        << "\"input_min\":[0.0],\"input_max\":[10.0],"
        << "\"occupancy\":{\"bins\":4,\"counts\":[[5,0,0,3]]}},"
        << "\"layers\":[{\"weights\":[[1.0]],\"bias\":[0.0],"
        << "\"activation\":\"none\"}]}";
    }
    auto model = std::make_unique<trech::ml::GenericSurrogate>();
    model->load(path);
    std::remove(path.c_str());
    trech::ml::ScaleCascade cascade;
    cascade.addStage("occ", DimensionScale::kNano, model.get());
    const auto rHole = cascade.run({{"seed_x", 3.0}});  // bin 1 empty -> starved
    expect(rHole.stagesStarved == 1, "one stage flagged starved");
    expect(rHole.stages[0].inDomain, "starved stage is still in-domain (not OOD)");
    expect(rHole.stages[0].starvedInputs.size() == 1 &&
               rHole.stages[0].starvedInputs[0] == "seed_x",
           "starved input recorded on the stage");
    const auto rDense = cascade.run({{"seed_x", 1.0}});  // bin 0 populated
    expect(rDense.stagesStarved == 0 && rDense.stages[0].starvedInputs.empty(),
           "populated-bin input is not starved");
  }

  if (failures == 0) {
    std::printf("test_scale_cascade: all checks passed\n");
    return 0;
  }
  std::fprintf(stderr, "test_scale_cascade: %d check(s) failed\n", failures);
  return 1;
}
