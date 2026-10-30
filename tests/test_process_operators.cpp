#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

int main() {
  namespace fs = std::filesystem;
  const auto directory = fs::temp_directory_path() / ("trech_process_operators_" +
      std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  fs::create_directories(directory);
  try {
    // Synthetic maps test the host/library boundary, not a physical response.
    const auto model = nlohmann::json::parse(R"({
      "model":"generic_surrogate_v1", "input_features":["forcing"],
      "output_features":["d_temperature_k_dt"],
      "layers":[{"weights":[[1.0]],"bias":[0.0],"activation":"none"}]
    })");
    std::ofstream(directory / "thermal.json") << model.dump();
    auto measured = model;
    measured["trained_scale_bands"] = {"meso"};
    measured["input_domain"] = {{"standardized_radius", {4.0}}};
    measured["holdout"] = {{"r2_min", 0.87}, {"n", 12},
                            {"r2", {{"d_temperature_k_dt", 0.87}}},
                            {"mae", {{"d_temperature_k_dt", 0.2}}},
                            {"rmse", {{"d_temperature_k_dt", 0.3}}}};
    std::ofstream(directory / "measured.json") << measured.dump();
    auto discrete = model;
    discrete["output_features"] = {"hazard_transfer"};
    discrete["layers"][0]["weights"] = {{0.0}};
    discrete["layers"][0]["bias"] = {0.7};
    std::ofstream(directory / "transfer.json") << discrete.dump();
    const auto scriptPath = directory / "main.js";
    {
      std::ofstream script(scriptPath);
      for (const auto* file : {"trech_process_runtime.js", "trech_process_operators.js"})
        script << "TRECH_INCLUDE(" << nlohmann::json((fs::path(TRECH_SOURCE_DIR) / "js" / file).string()).dump() << ");\n";
      script << R"JS(
function check(ok, message) { if (!ok) throw new Error(message); }
function rejects(fn) { let caught=false; try {fn();} catch (_) {caught=true;} check(caught,'Invalid contract accepted'); }
const definition = {id:'prepare', operation:'evolve', operator_role:'thermal', element_kind:'test_material',
  fields:[{name:'temperature_k',unit:'K',min:0,max:500}], aux:[{name:'mass_kg',unit:'kg',min:0}],
  context:[{name:'forcing',unit:'K/s'}], provenance:{basis:'Synthetic boundary test only'}};
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...definition,operation:'unknown'}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...definition,schema:'unknown'}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...definition,fields:[{name:'temperature_k'}]}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...definition,provenance:null}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...definition,aux:[{name:'temperature_k',unit:'K'}]}));
const thermal = TRECH_PROCESS_OPERATORS.bind(definition);
definition.operator_role='tampered'; thermal.contract.fields[0].max=1;
const fakeState = {temperature_k:[300,310],mass_kg:[1,2]}, original=JSON.stringify(fakeState);
let calls=0;
const fake = {runtime:{mode:'predictive'},evolve(spec) {
  calls++; check(spec.operator_role==='thermal','Contract metadata changed execution');
  spec.aux.mass_kg[0]=999; spec.state.temperature_k[0]=320; return {ran:true,inferenceCount:2};
}};
check(thermal.advance({runtime:{mode:'strict'}},fakeState,1,{forcing:1}).error.code==='strict_disabled','Strict binding ran');
check(thermal.advance(fake,fakeState,1).error.code==='missing_context' && calls===0,'Missing context invoked operator');
check(thermal.advance(fake,fakeState,1,{forcing:NaN}).error.code==='invalid_context' && calls===0,'Nonfinite context ran');
check(thermal.advance(fake,fakeState,1,null).error.code==='invalid_context' && calls===0,'Malformed context ran');
check(thermal.advance({runtime:{mode:'predictive'}},fakeState,1,{forcing:1}).error.code==='operator_unavailable','Missing API not reported');
check(thermal.advance(fake,{temperature_k:[300],mass_kg:[1,2]},1,{forcing:1}).error.code==='invalid_binding','Array lengths ignored');
check(thermal.advance(fake,{temperature_k:[300,,310],mass_kg:[1,2,3]},1,{forcing:1}).error.code==='invalid_binding' && calls===0,'Sparse arrays ran');
check(JSON.stringify(fakeState)===original,'Preflight changed state');
check(thermal.advance(fake,fakeState,1,{forcing:0}).accepted && fakeState.temperature_k[0]===320 &&
  fakeState.mass_kg[0]===1,'Explicit zero context or read-only aux broken');
const invalid = thermal.advance({...fake,evolve(spec){spec.state.temperature_k[0]=NaN;return {ran:true,inferenceCount:2};}},fakeState,1,{forcing:1});
check(invalid.error.code==='invalid_proposal' && invalid.engine.inferenceCount===2 && fakeState.temperature_k[0]===320,
  'Rejected proposal changed state or hid engine report');
const blocked=thermal.advance({...fake,evolve(spec){spec.state.temperature_k[0]=400;return {ran:false};}},fakeState,1,{forcing:1});
check(blocked.error.code==='operator_blocked' && fakeState.temperature_k[0]===320,'Blocked operator committed');
const thrown=thermal.advance({...fake,evolve(spec){spec.state.temperature_k[0]=400;throw new Error('operator failed');}},fakeState,1,{forcing:1});
check(thrown.error.code==='operator_exception' && fakeState.temperature_k[0]===320,'Exception lost rollback');

const transfer=TRECH_PROCESS_OPERATORS.bind({id:'exchange',operation:'react',operator_role:'transfer',element_kind:'other_material',
  species:[{name:'source',unit:'parcel'},{name:'sink',unit:'parcel'}], context:[{name:'forcing',unit:'1/s'}],
  channels:[{name:'transfer',delta:{source:-1,sink:1}}], conservation:[{name:'amount',coefficients:{source:1,sink:1}}],
  provenance:{basis:'Synthetic boundary test only'}});
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...transfer.contract,channels:[{name:'loss',delta:{source:-1}}]}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...transfer.contract,conservation:[{name:'bad',coefficients:{unknown:1}}]}));
check(transfer.advance(fake,{source:[Number.MAX_SAFE_INTEGER],sink:[1]},1,{forcing:1}).error.code==='operator_unavailable',
  'Missing discrete host not reported');
check(transfer.advance({...fake,react(){throw new Error('must not run');}},
  {source:[Number.MAX_SAFE_INTEGER],sink:[1]},1,{forcing:1}).error.code==='invalid_binding','Unsafe conservation invoked operator');
const amount={source:[2],sink:[0]};
check(transfer.advance({...fake,react(spec){spec.state.sink[0]++;return {ran:true};}},amount,1,{forcing:1}).error.code==='invalid_proposal' &&
  amount.sink[0]===0,'Discrete conservation proposal committed');
function machine() {return TRECH_PROCESS_RUNTIME.create({initial:{temperature_k:[300],mass_kg:[1]},
  stages:[{id:'prepare',complete:s=>s.temperature_k[0]>=304,
    advance:(ctx,state,dt)=>thermal.advance(ctx,state,dt,{forcing:2})}], validate(s){check(s.temperature_k[0]>0,'Invalid temperature');}});}
const rejected=machine();
check(rejected.step({...fake,evolve(spec){spec.state.temperature_k[0]=600;return {ran:true};}},1).status==='rejected' &&
  rejected.snapshot().elapsed_s===0 && rejected.snapshot().state.temperature_k[0]===300,'Runtime committed rejected binding');
globalThis.TRECH_CONFIG={models:[
  {name:'z_thermal',path:'thermal.json',scale:'meso',operator_role:'thermal',element_kind:'test_material',required_context_keys:['forcing']},
  {name:'a_missing',path:'missing.json',operator_role:'unavailable',element_kind:'test_material'},
  {name:'m_measured',path:'measured.json',scale:'meso',operator_role:'diagnostic',element_kind:'test_material'},
  {name:'point_only',path:'thermal.json'},
  {name:'transfer',path:'transfer.json',scale:'meso',operator_role:'transfer',element_kind:'other_material',required_context_keys:['forcing']}
]};
let skipCatalog=false, savedCatalog;
globalThis.TRECH_HOOKS={onEventEnd(ctx) {
  const catalog=skipCatalog?JSON.parse(JSON.stringify(savedCatalog)):ctx.operatorCatalog();
  const again=skipCatalog?JSON.parse(JSON.stringify(savedCatalog)):ctx.operatorCatalog();
  savedCatalog=JSON.parse(JSON.stringify(again));
  catalog.operators[0].loaded=true; catalog.operators[3].inputs[0]='tampered';
  check(!again.operators[0].loaded && again.operators[3].inputs[0]==='forcing','Catalog is not detached');
  const process=machine(), state=process.step(ctx,2), amount={source:Array(32).fill(2),sink:Array(32).fill(0)};
  const exchange=transfer.advance(ctx,amount,1,{forcing:1});
  // Catalog reads must consume neither inference nor the deterministic react sequence.
  ctx.emit('boundary',{catalog:again,state,exchange,amount,rng:ctx.rng.uniform()});
}, onRunStart() {skipCatalog=true;}};
)JS";
    }
    trech::JsRuntime runtime;
    (void)runtime.evalExperimentAndGetConfigJson(scriptPath.string());
    trech::HookRuntimeContext context;
    context.seed = 42;
    context.determinismMode = "strict";
    auto report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    auto emits = runtime.takeEmittedRecords();
    if (report.predictCount || emits.size() != 1) throw std::runtime_error("Strict catalog caused inference or lost emit");
    const auto strict = nlohmann::json::parse(emits[0].payloadJson);
    const auto catalog = strict.at("catalog");
    const auto& entries = catalog.at("operators");
    if (catalog.at("schema") != "trech_operator_catalog_v1" || entries.size() != 4 ||
        entries[0].at("name") != "a_missing" || entries[0].at("loaded") != false ||
        !entries[0].at("holdout").is_null() || entries[0].at("path") != "missing.json" ||
        entries[2].at("element_kind") != "other_material" ||
        entries[3].at("required_context_keys") != nlohmann::json::array({"forcing"}) ||
        entries[3].at("inputs") != nlohmann::json::array({"forcing"}) ||
        !entries[3].at("holdout").is_null() || entries[3].at("domain_measured") != false ||
        !entries[3].at("output_accuracy").empty()) throw std::runtime_error("Catalog invented or lost capability metadata");
    if (entries[1].at("holdout").at("r2_min") != 0.87 || entries[1].at("holdout").at("samples") != 12 ||
        entries[1].at("domain_measured") != true || entries[1].at("trained_scale_bands") != nlohmann::json::array({"meso"}) ||
        entries[1].at("output_accuracy").at("d_temperature_k_dt").at("rmse") != 0.3)
      throw std::runtime_error("Catalog lost carried validation metadata");
    if (strict.at("state").at("status") != "strict_disabled" || strict.at("amount").at("source")[0] != 2)
      throw std::runtime_error("Strict process binding changed state");
    context.determinismMode = "predictive";
    report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    emits = runtime.takeEmittedRecords();
    const auto predicted = nlohmann::json::parse(emits.at(0).payloadJson);
    if (report.predictCount != 33 || predicted.at("state").at("status") != "complete" ||
        predicted.at("state").at("state").at("temperature_k")[0] != 304 ||
        predicted.at("catalog") != catalog) throw std::runtime_error("Bound operators lost execution/accounting/catalog parity");
    int accepted = 0;
    for (int i = 0; i < 32; ++i) {
      const int source = predicted.at("amount").at("source")[i];
      const int sink = predicted.at("amount").at("sink")[i];
      if (source + sink != 2 || sink < 0 || sink > 1) throw std::runtime_error("Discrete transfer violated inventory");
      accepted += sink;
    }
    if (accepted == 0 || accepted == 32) throw std::runtime_error("Discrete fixture did not exercise stochastic choices");
    runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto replay = runtime.takeEmittedRecords();
    if (replay.at(0).payloadJson != emits.at(0).payloadJson) throw std::runtime_error("Process replay changed");
    runtime.dispatchHook("onRunStart", context, nullptr, false);
    const auto referenceReport = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto reference = runtime.takeEmittedRecords();
    if (referenceReport.predictCount != 33 || reference.at(0).payloadJson != emits.at(0).payloadJson)
      throw std::runtime_error("Catalog reads changed RNG, discrete operator sequence or counters");
    fs::remove_all(directory);
    std::cout << "Process units, capabilities, rollback, strict gating and engine execution pass\n";
  } catch (const std::exception& error) {
    fs::remove_all(directory);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
