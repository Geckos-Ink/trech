#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/core/SimulationBudget.hpp"
#include "trech/js/JsRuntime.hpp"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <nlohmann/json.hpp>

void require(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}

int main() {
  try {
    trech::SimulationBudget budget(1.0);
    budget.begin();
    require(!budget.observeElapsed(0.2), "first event should leave room");
    require(budget.observeElapsed(0.85), "next event should not fit");
    require(budget.observeElapsed(std::numeric_limits<double>::quiet_NaN()), "invalid observation must not reset budget");
    budget.begin();
    require(!budget.exhausted(), "new run must reset budget");
    require(budget.observeElapsed(2.0), "one atomic event may exceed budget");
    auto original = nlohmann::json::parse(trech::configToJsonString(trech::TrechConfig{}));
    require(!original["run"].contains("timeBudgetSeconds"), "default config hash changed");
    auto cfg = trech::configFromJsonString(R"({"run":{"timeBudgetSeconds":0.5},"determinism":{"mode":"predictive"}})");
    trech::RunOptions options;
    trech::applyRunOverrides(cfg, options);
    require(cfg.run.threads == 1, "timed run must record serial work");
    require(trech::configFromJsonString(trech::configToJsonString(cfg)).run.timeBudgetSeconds == 0.5,
            "budget must round trip");
    cfg.determinism.mode = "strict";
    bool rejected = false;
    try { trech::applyRunOverrides(cfg, options); } catch (...) { rejected = true; }
    require(rejected, "strict timed run must be rejected");

    const std::string path = "adaptive_precision_test.js";
    {
      std::ofstream f(path);
      f << "TRECH_INCLUDE(" << nlohmann::json(std::string(TRECH_SOURCE_DIR) + "/js/trech_helpers.js").dump() << ");\n"
           "const p = TRECH_HELPERS.precision.resolve({axes:["
           "{name:'samples',role:'statistical',balanced:10,min:1,max:1000,integer:true},"
           "{name:'step',role:'temporal',balanced:1,direction:'lower_is_finer'}]});"
           "TRECH_CONFIG = {precision:p.config,run:{nEvents:p.value('samples')}};";
    }
    trech::JsRuntime js;
    js.setPrecisionRefinement(3.125);
    const auto resolved = trech::configFromJsonString(js.evalExperimentAndGetConfigJson(path));
    std::remove(path.c_str());
    require(resolved.run.nEvents == 31, "fractional factor must refine counts");
    require(resolved.precision.profile == "custom", "continuous factor must be labelled custom");
    require(resolved.precision.axes.at(1).value == 0.32, "steps must refine in the opposite direction");
    {
      std::ofstream f(path);
      f << "TRECH_CONFIG = {};";
    }
    trech::JsRuntime unsupported;
    unsupported.setPrecisionRefinement(2.0);
    rejected = false;
    try { unsupported.evalExperimentAndGetConfigJson(path); } catch (...) { rejected = true; }
    std::remove(path.c_str());
    require(rejected, "unsupported refinement must not silently succeed");
    {
      std::ofstream model("adaptive_stage.json");
      model << R"({"model":"generic_surrogate_v1","input_features":["x"],"output_features":["x"],"layers":[{"weights":[[1]],"bias":[1],"activation":"none"}]})";
    }
    {
      std::ofstream script(path);
      script << R"(TRECH_CONFIG = {models:[{name:'a',path:'adaptive_stage.json',scale:'nano'},{name:'b',path:'adaptive_stage.json',scale:'macro'}]};
        TRECH_HOOKS = {onEventEnd(ctx) {ctx.emit('limited',ctx.cascade({x:1},null,{maxStages:1}).__cascade);}};)";
    }
    trech::JsRuntime limited;
    auto limitedConfig = trech::configFromJsonString(limited.evalExperimentAndGetConfigJson(path));
    trech::HookRuntimeContext context;
    context.determinismMode = "predictive";
    const auto report = limited.dispatchHook("onEventEnd", context, &limitedConfig, false);
    auto emits = limited.takeEmittedRecords();
    require(report.predictCount == 1 && emits.size() == 1, "JS stage budget must count only executed predictions");
    const auto payload = nlohmann::json::parse(emits.at(0).payloadJson);
    require(payload.at("stagesLimited") == 1 && payload.at("stopReason") == "stage_budget", "JS must disclose limited depth");
    context.determinismMode = "strict";
    // Strict returns null before either model or limit evaluation; the hook's
    // attempt to access null throws, and still consumes no inference.
    try { limited.dispatchHook("onEventEnd", context, &limitedConfig, false); } catch (...) {}
    require(limited.totalPredictCount() == 1, "strict mode must not run bounded inference");
    std::remove(path.c_str());
    std::remove("adaptive_stage.json");
    return 0;
  } catch (const std::exception& ex) {
    std::cerr << ex.what() << '\n';
    return 1;
  }
}
