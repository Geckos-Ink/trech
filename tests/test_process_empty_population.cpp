#include "TemporaryDirectory.hpp"

#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

// Declared empty-population completion for ctx.evolve / ctx.react process
// bindings. Synthetic maps test the host/library boundary, not a physical
// response: an empty population may complete only when the contract declares
// it, the engine confirms complete operator selection and nothing was inferred
// or drawn.
int main() {
  namespace fs = std::filesystem;
  const trech::test::TemporaryDirectory fixture;
  const auto& directory = fixture.path();
  try {
    const auto thermal = nlohmann::json::parse(R"({
      "model":"generic_surrogate_v1", "input_features":["forcing"],
      "output_features":["d_temperature_k_dt"],
      "layers":[{"weights":[[1.0]],"bias":[0.0],"activation":"none"}]
    })");
    std::ofstream(directory / "thermal.json") << thermal.dump();
    auto transfer = thermal;
    transfer["output_features"] = {"hazard_transfer"};
    transfer["layers"][0]["weights"] = {{0.0}};
    transfer["layers"][0]["bias"] = {0.7};
    std::ofstream(directory / "transfer.json") << transfer.dump();
    const auto scriptPath = directory / "main.js";
    {
      std::ofstream script(scriptPath);
      for (const auto* file : {"trech_process_runtime.js", "trech_process_operators.js"})
        script << "TRECH_INCLUDE(" << nlohmann::json((fs::path(TRECH_SOURCE_DIR) / "js" / file).string()).dump() << ");\n";
      script << R"JS(
function check(ok, message) { if (!ok) throw new Error(message); }
function rejects(fn) { let caught=false; try {fn();} catch (_) {caught=true;} check(caught,'Invalid contract accepted'); }
globalThis.TRECH_CONFIG={models:[
  {name:'thermal',path:'thermal.json',scale:'meso',operator_role:'thermal',element_kind:'test_material',required_context_keys:['forcing']},
  {name:'transfer',path:'transfer.json',scale:'meso',operator_role:'transfer',element_kind:'other_material',required_context_keys:['forcing']}
]};
const heating={id:'heat',operation:'evolve',operator_role:'thermal',element_kind:'test_material',
  fields:[{name:'temperature_k',unit:'K',min:0,max:1000}], aux:[{name:'mass_kg',unit:'kg',min:0}],
  context:[{name:'forcing',unit:'K/s'}], provenance:{basis:'Synthetic boundary test only'}};
const exchange={id:'exchange',operation:'react',operator_role:'transfer',element_kind:'other_material',
  species:[{name:'source',unit:'parcel'},{name:'sink',unit:'parcel'}], context:[{name:'forcing',unit:'1/s'}],
  channels:[{name:'transfer',delta:{source:-1,sink:1}}], conservation:[{name:'amount',coefficients:{source:1,sink:1}}],
  provenance:{basis:'Synthetic boundary test only'}};
// Declaration shape: only block/complete, and never with spatial or per-element kinds.
for (const value of ['skip', true, 1]) rejects(()=>TRECH_PROCESS_OPERATORS.bind({...heating,empty_population:value}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...heating,element_kind:undefined,
  element_kinds:{field:'kind',allowed:['test_material']},empty_population:'complete'}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({id:'pairs',operation:'interact',operator_role:'thermal',element_kind:'test_material',
  fields:[{name:'temperature_k',unit:'K',symmetry:'symmetric'}],
  spatial:{axes:{x:'x',y:'y',z:'z'},unit:'m',cutoff:1},
  provenance:{basis:'Synthetic boundary test only'},empty_population:'complete'}));
const blockedByDefault=TRECH_PROCESS_OPERATORS.bind({...heating,empty_population:'block'});
const completes=TRECH_PROCESS_OPERATORS.bind({...heating,empty_population:'complete'});
const unavailable=TRECH_PROCESS_OPERATORS.bind({...heating,operator_role:'missing_role',empty_population:'complete'});
const emptyExchange=TRECH_PROCESS_OPERATORS.bind({...exchange,empty_population:'complete'});
const plainExchange=TRECH_PROCESS_OPERATORS.bind(exchange);
let skipEmpty=false;
globalThis.TRECH_HOOKS={onRunStart() {skipEmpty=true;}, onEventEnd(ctx) {
  const empty=()=>({temperature_k:[],mass_kg:[]});
  const raw={fields:[{name:'temperature_k'}],state:{temperature_k:[]},context:{forcing:1},dt:1,
    operator_role:'thermal',element_kind:'test_material'};
  const legacy=ctx.evolve(raw);
  const reported=ctx.evolve({...raw,report_empty_population:true});
  let typeError=false;
  try { ctx.evolve({...raw,report_empty_population:'yes'}); } catch (e) { typeError=e instanceof TypeError; }
  const defaultBlocked=blockedByDefault.advance(ctx,empty(),1,{forcing:1});
  const noOp=completes.advance(ctx,empty(),1,{forcing:1});
  const missing=unavailable.advance(ctx,empty(),1,{forcing:1});
  const populated={temperature_k:[300,310],mass_kg:[1,2]};
  const ran=completes.advance(ctx,populated,2,{forcing:3});
  const machine=TRECH_PROCESS_RUNTIME.create({initial:{temperature_k:[],mass_kg:[]},validate(){},
    stages:[{id:'idle',complete(){return false;},advance:(c,s,dt)=>completes.advance(c,s,dt,{forcing:1})}]});
  const step=machine.step(ctx,0.5);
  // An empty react must not consume the deterministic react call sequence.
  const emptyReact=skipEmpty?null:emptyExchange.advance(ctx,{source:[],sink:[]},1,{forcing:1});
  const amount={source:Array(32).fill(2),sink:Array(32).fill(0)};
  const after=plainExchange.advance(ctx,amount,1,{forcing:1});
  ctx.emit('empty',{legacy,reported,typeError,defaultBlocked,noOp,missing,ran,populated,step,emptyReact,after,amount,
    rng:ctx.rng.uniform()});
}};
)JS";
    }
    trech::JsRuntime runtime;
    (void)runtime.evalExperimentAndGetConfigJson(scriptPath.string());
    trech::HookRuntimeContext context;
    context.seed = 7;
    context.determinismMode = "predictive";
    auto report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto emits = runtime.takeEmittedRecords();
    if (emits.size() != 1) throw std::runtime_error("Missing empty-population emit");
    const auto out = nlohmann::json::parse(emits[0].payloadJson);
    if (!out.at("legacy").is_null())
      throw std::runtime_error("Zero-element evolve without the flag no longer returns null");
    const auto& reported = out.at("reported");
    if (reported.at("ran") != false || reported.at("blockedReason") != "no_elements" ||
        reported.at("inferenceCount") != 0 || reported.at("drawCount") != 0 ||
        reported.at("elementCount") != 0 || reported.at("selection").at("status") != "selected")
      throw std::runtime_error("Opt-in zero-element evolve lost its verdict or selection");
    if (out.at("typeError") != true) throw std::runtime_error("Non-boolean report flag accepted");
    if (out.at("defaultBlocked").at("error").at("code") != "invalid_binding")
      throw std::runtime_error("Undeclared empty population did not stay invalid");
    const auto& noOp = out.at("noOp");
    if (noOp.at("accepted") != true || noOp.at("ran") != false || noOp.at("no_op") != "empty_population" ||
        noOp.at("engine").at("blockedReason") != "no_elements")
      throw std::runtime_error("Declared empty population did not complete as a no-op");
    const auto& missing = out.at("missing");
    if (missing.at("accepted") != false || missing.at("error").at("code") != "operator_blocked" ||
        missing.at("engine").at("blockedReason") != "incomplete_selection")
      throw std::runtime_error("Empty population completed without a selected operator");
    if (out.at("ran").at("ran") != true || out.at("populated").at("temperature_k")[0] != 306)
      throw std::runtime_error("Declared contract changed populated execution");
    const auto& step = out.at("step");
    if (step.at("status") != "advanced" || step.at("no_op") != "empty_population" || step.at("elapsed_s") != 0.5)
      throw std::runtime_error("Process runtime did not commit the empty-population no-op");
    if (out.at("emptyReact").at("no_op") != "empty_population" ||
        out.at("emptyReact").at("engine").at("drawCount") != 0)
      throw std::runtime_error("Declared empty react did not complete without draws");
    // 2 populated evolve inferences + 32 react inferences; empty calls add none.
    if (report.predictCount != 34) throw std::runtime_error("Empty populations changed inference accounting");

    // Same dispatch without the empty react: later react draws must be identical.
    runtime.dispatchHook("onRunStart", context, nullptr, false);
    runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto without = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    if (without.at("amount") != out.at("amount") || without.at("after") != out.at("after") ||
        without.at("rng") != out.at("rng"))
      throw std::runtime_error("Empty react consumed the react call sequence or RNG");

    context.determinismMode = "strict";
    report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto strict = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    if (report.predictCount != 0 || !strict.at("reported").is_null() ||
        strict.at("noOp").at("error").at("code") != "strict_disabled" ||
        strict.at("step").at("status") != "strict_disabled")
      throw std::runtime_error("Strict mode completed or inferred an empty population");
    std::cout << "Declared empty-population no-ops, blocking and replay isolation pass\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
