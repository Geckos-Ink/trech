#include "trech/js/JsRuntime.hpp"
#include "trech/core/Provenance.hpp"

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
      "feature_units":{"inputs":{"forcing":"K/s"},"outputs":{"d_temperature_k_dt":"K/s"}},
      "layers":[{"weights":[[1.0]],"bias":[0.0],"activation":"none"}]
    })");
    std::ofstream(directory / "thermal.json") << model.dump();
    auto measured = model;
    measured.erase("feature_units");  // Legacy metadata remains explicitly unknown.
    measured["trained_scale_bands"] = {"meso"};
    measured["input_domain"] = {{"standardized_radius", {4.0}}};
    measured["holdout"] = {{"r2_min", 0.87}, {"n", 12},
                            {"r2", {{"d_temperature_k_dt", 0.87}}},
                            {"mae", {{"d_temperature_k_dt", 0.2}}},
                            {"rmse", {{"d_temperature_k_dt", 0.3}}}};
    std::ofstream(directory / "measured.json") << measured.dump();
    auto discrete = model;
    discrete["output_features"] = {"hazard_transfer"};
    discrete["feature_units"] = {{"inputs", {{"forcing", "1/s"}}}, {"outputs", {{"hazard_transfer", "1/s"}}}};
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

const pinBase={...definition,operator_role:'thermal'};
const modelUnits={inputs:{forcing:'K/s'},outputs:{d_temperature_k_dt:'K/s'}};
const unitDefinition={...pinBase,model_units:modelUnits};
for (const units of [null,{}, {inputs:{},outputs:{}}, {inputs:{forcing:'K/s'},outputs:{x:0}},
    {inputs:{forcing:'degC/s'},outputs:{d_temperature_k_dt:'K/s'}},
    {inputs:{forcing:'K/s'},outputs:{forcing:'1'}},
    {inputs:{temperature_k:'degC'},outputs:{d_temperature_k_dt:'K/s'}},
    {inputs:{dt:'ms'},outputs:{d_temperature_k_dt:'K/s'}}])
  rejects(()=>TRECH_PROCESS_OPERATORS.bind({...pinBase,model_units:units}));
const unitThermal=TRECH_PROCESS_OPERATORS.bind(unitDefinition);
unitDefinition.model_units.inputs.forcing='mutated';
unitThermal.contract.model_units.outputs.d_temperature_k_dt='mutated';
const unitEntry={name:'thermal',loaded:true,operator_role:'thermal',element_kind:'test_material',
  content_id:'fnv1a64:0123456789abcdef',inputs:['forcing'],outputs:['d_temperature_k_dt'],
  feature_units:{inputs:{forcing:'K/s'},outputs:{d_temperature_k_dt:'K/s'}}};
const unitHost={...fake,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:[unitEntry]};}};
const unitBefore=JSON.stringify(fakeState), unitCalls=calls;
for (const entries of [[],[{...unitEntry,feature_units:null}],
    [{...unitEntry,feature_units:{inputs:{forcing:'K/s'},outputs:{other:'K/s'}}}]])
  check(unitThermal.advance({...unitHost,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:entries};}},
    fakeState,1,{forcing:1}).error.code==='unit_metadata_missing','Missing unit metadata accepted');
for (const entries of [[{...unitEntry,feature_units:{inputs:{forcing:'degC/s'},outputs:{d_temperature_k_dt:'K/s'}}}],
    [unitEntry,{...unitEntry,name:'extra',inputs:['extra'],feature_units:{inputs:{extra:'1'},outputs:{d_temperature_k_dt:'K/s'}}}]])
  check(unitThermal.advance({...unitHost,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:entries};}},
    fakeState,1,{forcing:1}).error.code==='unit_mismatch','Incompatible group units accepted');
check(unitThermal.advance(fake,fakeState,1,{forcing:1}).error.code==='catalog_unavailable','Unit check skipped catalog');
check(unitThermal.advance({...unitHost,runtime:{mode:'strict'},operatorCatalog(){throw new Error('must not read');}},
  fakeState,1,{forcing:1}).error.code==='strict_disabled','Strict units read catalog');
check(calls===unitCalls && JSON.stringify(fakeState)===unitBefore,'Unit preflight changed state or invoked operator');
check(unitThermal.advance(unitHost,fakeState,1,{forcing:1}).accepted,'Compatible units or detached definitions failed');
const chain=TRECH_PROCESS_OPERATORS.bind({...pinBase,
  model_units:{inputs:{forcing:'K/s',response:'K/s'},outputs:{response:'K/s',d_temperature_k_dt:'K/s'}}});
const chainGroup=[{...unitEntry,outputs:['response'],feature_units:{inputs:{forcing:'K/s'},outputs:{response:'K/s'}}},
  {...unitEntry,name:'lift',inputs:['response'],feature_units:{inputs:{response:'K/s'},outputs:{d_temperature_k_dt:'K/s'}}}];
const chainHost={...fake,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:chainGroup};}};
check(chain.advance(chainHost,fakeState,1,{forcing:1}).accepted,'Multistage unit union blocked');
const missingStage={...chainHost,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:chainGroup.slice(0,1)};}};
check(chain.advance(missingStage,fakeState,1,{forcing:1}).error.code==='unit_mismatch','Missing expected stage IO accepted');
const unitMachine=TRECH_PROCESS_RUNTIME.create({initial:{temperature_k:[300],mass_kg:[1]},validate(){},
  stages:[{id:'units',complete(){return false;},advance:(ctx,state,dt)=>unitThermal.advance(ctx,state,dt,{forcing:1})}]});
const unitBlocked=unitMachine.step({...unitHost,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:[]};}},1);
check(unitBlocked.status==='blocked' && unitBlocked.elapsed_s===0 && unitBlocked.state.temperature_k[0]===300,
  'Missing units advanced clock/state');
const pin={name:'thermal_model',content_id:'fnv1a64:0123456789abcdef'};
const pinnedDefinition={...pinBase,model_artifacts:[pin]};
for (const pins of [[],[pin,pin],[{...pin,content_id:'unknown:123'}],[{...pin,name:''}], [null]])
  rejects(()=>TRECH_PROCESS_OPERATORS.bind({...pinBase,model_artifacts:pins}));
const pinned=TRECH_PROCESS_OPERATORS.bind(pinnedDefinition);
pinnedDefinition.model_artifacts[0].content_id='fnv1a64:0000000000000000';
pinned.contract.model_artifacts[0].name='tampered';
let catalogCalls=0;
const entry={name:pin.name,content_id:'fnv1a64:0123456789abcdef',loaded:true,operator_role:'thermal',element_kind:'test_material'};
const pinnedHost={...fake,operatorCatalog(){catalogCalls++;return {schema:'trech_operator_catalog_v1',operators:[entry]};}};
check(pinned.advance({...pinnedHost,runtime:{mode:'strict'}},fakeState,1,{forcing:1}).error.code==='strict_disabled' &&
  catalogCalls===0,'Strict pin verification read catalog');
check(pinned.advance(fake,fakeState,1,{forcing:1}).error.code==='catalog_unavailable','Missing pin catalog accepted');
const beforePins=JSON.stringify(fakeState), beforeCalls=calls;
for (const entries of [[],[{...entry,content_id:'fnv1a64:0000000000000000'}],
    [{...entry,loaded:false}],[{...entry,operator_role:'different'}],[{...entry,element_kind:'different'}],
    [entry,{...entry,name:'added_model'}]]) {
  const result=pinned.advance({...pinnedHost,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:entries};}},fakeState,1,{forcing:1});
  check(result.error.code==='artifact_mismatch' && !result.ran && result.engine===null,'Mismatched artifact group ran');
}
for (const catalog of [null,{}, {schema:'unknown',operators:[]}])
  check(pinned.advance({...pinnedHost,operatorCatalog(){return catalog;}},fakeState,1,{forcing:1}).error.code==='catalog_unavailable',
    'Malformed catalog accepted');
check(pinned.advance({...pinnedHost,operatorCatalog(){throw new Error('catalog failed');}},fakeState,1,{forcing:1}).error.code==='catalog_unavailable',
  'Catalog exception accepted');
check(calls===beforeCalls && JSON.stringify(fakeState)===beforePins,'Artifact preflight invoked inference or changed state');
const pinnedResult=pinned.advance(pinnedHost,fakeState,1,{forcing:1});
check(pinnedResult.accepted && pinnedResult.artifacts[0].name===entry.name,'Pinned contract failed or lost artifact report');
const pinnedUnits=TRECH_PROCESS_OPERATORS.bind({...pinBase,model_artifacts:[{name:unitEntry.name,content_id:unitEntry.content_id}],
  model_units:{inputs:{forcing:'K/s'},outputs:{d_temperature_k_dt:'K/s'}}});
check(pinnedUnits.advance(unitHost,fakeState,1,{forcing:1}).accepted,'Pins and unit checks failed together');
pinnedResult.artifacts[0].name='mutated';
check(entry.name==='thermal_model','Artifact report aliases catalog');
const pinMachine=TRECH_PROCESS_RUNTIME.create({initial:{temperature_k:[300],mass_kg:[1]},validate(){},
  stages:[{id:'pinned',complete(){return false;},advance:(ctx,state,dt)=>pinned.advance(ctx,state,dt,{forcing:1})}]});
const pinBlocked=pinMachine.step(fake,1);
check(pinBlocked.status==='blocked' && pinBlocked.elapsed_s===0 && pinBlocked.state.temperature_k[0]===300,
  'Missing artifacts advanced process clock/state');
const changedPins=pinMachine.step({...pinnedHost,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:[]};}},1);
check(changedPins.status==='blocked' && changedPins.elapsed_s===0 && changedPins.state.temperature_k[0]===300,
  'Artifact mismatch advanced process clock/state');

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
let skipCatalog=false, savedCatalog, skipMismatch=false, savedMismatch, savedDiscreteMismatch;
let skipUnitMismatch=false, savedUnitMismatch, savedDiscreteUnitMismatch;
globalThis.TRECH_HOOKS={onTrackStart() {skipUnitMismatch=true;}, onEventEnd(ctx) {
  const catalog=skipCatalog?JSON.parse(JSON.stringify(savedCatalog)):ctx.operatorCatalog();
  const again=skipCatalog?JSON.parse(JSON.stringify(savedCatalog)):ctx.operatorCatalog();
  savedCatalog=JSON.parse(JSON.stringify(again));
  catalog.operators[0].loaded=true; catalog.operators[3].inputs[0]='tampered';
  catalog.operators[3].feature_units.inputs.forcing='tampered';
  check(!again.operators[0].loaded && again.operators[3].inputs[0]==='forcing' &&
    again.operators[3].feature_units.inputs.forcing==='K/s','Catalog is not detached');
  const process=machine(), state=process.step(ctx,2), amount={source:Array(32).fill(2),sink:Array(32).fill(0)};
  const exchange=transfer.advance(ctx,amount,1,{forcing:1});
  // Catalog reads must consume neither inference nor the deterministic react sequence.
  ctx.emit('boundary',{catalog:again,state,exchange,amount,rng:ctx.rng.uniform()});
}, onRunStart() {skipCatalog=true;}, onTrackEnd() {skipMismatch=true;},
onInit(ctx) {ctx.emit('catalog',ctx.operatorCatalog());}, onRunEnd(ctx) {
  const entries=ctx.operatorCatalog().operators;
  const artifact=entries.find(m=>m.name==='z_thermal');
  const pins=[{name:artifact.name,content_id:artifact.content_id}];
  const binding=TRECH_PROCESS_OPERATORS.bind({...pinBase,model_artifacts:pins});
  const state={temperature_k:[300],mass_kg:[1]};
  const bad=TRECH_PROCESS_OPERATORS.bind({...pinBase,model_artifacts:[{...pins[0],content_id:'fnv1a64:0000000000000000'}]});
  const mismatch=skipMismatch?savedMismatch:bad.advance(ctx,state,2,{forcing:2});
  savedMismatch=mismatch;
  const success=binding.advance(ctx,state,2,{forcing:2});
  const discreteArtifact=entries.find(m=>m.name==='transfer');
  const discreteBinding=TRECH_PROCESS_OPERATORS.bind({...transfer.contract,
    model_artifacts:[{name:discreteArtifact.name,content_id:discreteArtifact.content_id}]});
  const amount={source:Array(32).fill(2),sink:Array(32).fill(0)};
  const badDiscrete=TRECH_PROCESS_OPERATORS.bind({...transfer.contract,
    model_artifacts:[{name:discreteArtifact.name,content_id:'fnv1a64:0000000000000000'}]});
  const discreteMismatch=skipMismatch?savedDiscreteMismatch:badDiscrete.advance(ctx,amount,1,{forcing:1});
  savedDiscreteMismatch=discreteMismatch;
  const exchange=discreteBinding.advance(ctx,amount,1,{forcing:1});
  ctx.emit('pins',{mismatch,discreteMismatch,success,state,exchange,amount,rng:ctx.rng.uniform()});
}, onStep(ctx) {
  const state={temperature_k:[300],mass_kg:[1]}, amount={source:Array(32).fill(2),sink:Array(32).fill(0)};
  const badUnits=TRECH_PROCESS_OPERATORS.bind({...pinBase,
    model_units:{inputs:{forcing:'K/s'},outputs:{d_temperature_k_dt:'degC/s'}}});
  const mismatch=skipUnitMismatch?savedUnitMismatch:badUnits.advance(ctx,state,2,{forcing:2});
  savedUnitMismatch=mismatch;
  const unknown=TRECH_PROCESS_OPERATORS.bind({...unitThermal.contract,operator_role:'diagnostic'})
    .advance(ctx,state,2,{forcing:2});
  const success=unitThermal.advance(ctx,state,2,{forcing:2});
  const badDiscreteUnits=TRECH_PROCESS_OPERATORS.bind({...transfer.contract,
    model_units:{inputs:{forcing:'1/s'},outputs:{hazard_transfer:'1/ms'}}});
  const discreteMismatch=skipUnitMismatch?savedDiscreteUnitMismatch:badDiscreteUnits.advance(ctx,amount,1,{forcing:1});
  savedDiscreteUnitMismatch=discreteMismatch;
  const exchange=TRECH_PROCESS_OPERATORS.bind({...transfer.contract,
    model_units:{inputs:{forcing:'1/s'},outputs:{hazard_transfer:'1/s'}}}).advance(ctx,amount,1,{forcing:1});
  ctx.emit('units',{mismatch,discreteMismatch,unknown,success,state,exchange,amount,rng:ctx.rng.uniform()});
}};
)JS";
    }
    trech::JsRuntime runtime;
    (void)runtime.evalExperimentAndGetConfigJson(scriptPath.string());
    // Replace a relative-path artifact after loading. Catalogs and execution
    // must keep describing the original loaded bytes until an explicit reload.
    auto changed = model;
    changed["layers"][0]["weights"] = {{2.0}};
    std::ofstream(directory / "thermal.json") << changed.dump();
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
        !entries[0].at("content_id").is_null() ||
        !entries[0].at("feature_units").is_null() ||
        !entries[0].at("holdout").is_null() || entries[0].at("path") != "missing.json" ||
        entries[2].at("element_kind") != "other_material" ||
        entries[3].at("required_context_keys") != nlohmann::json::array({"forcing"}) ||
        entries[3].at("inputs") != nlohmann::json::array({"forcing"}) ||
        !entries[3].at("holdout").is_null() || entries[3].at("domain_measured") != false ||
        !entries[3].at("output_accuracy").empty()) throw std::runtime_error("Catalog invented or lost capability metadata");
    if (entries[3].at("content_id") != "fnv1a64:" + trech::fnv1a64Hex(model.dump()) ||
        entries[1].at("content_id") != "fnv1a64:" + trech::fnv1a64Hex(measured.dump()))
      throw std::runtime_error("Catalog identity differs from loaded artifact bytes");
    if (entries[1].at("holdout").at("r2_min") != 0.87 || entries[1].at("holdout").at("samples") != 12 ||
        entries[1].at("domain_measured") != true || entries[1].at("trained_scale_bands") != nlohmann::json::array({"meso"}) ||
        entries[1].at("output_accuracy").at("d_temperature_k_dt").at("rmse") != 0.3)
      throw std::runtime_error("Catalog lost carried validation metadata");
    if (entries[3].at("feature_units") != model.at("feature_units") ||
        entries[2].at("feature_units") != discrete.at("feature_units") || !entries[1].at("feature_units").is_null())
      throw std::runtime_error("Catalog lost carried unit metadata");
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
    report = runtime.dispatchHook("onRunEnd", context, nullptr, false);
    const auto pins = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    if (report.predictCount != 33 || pins.at("mismatch").at("error").at("code") != "artifact_mismatch" ||
        pins.at("success").at("accepted") != true || pins.at("state").at("temperature_k")[0] != 304 ||
        pins.at("success").at("artifacts")[0].at("content_id") != entries[3].at("content_id") ||
        pins.at("discreteMismatch").at("error").at("code") != "artifact_mismatch" ||
        pins.at("exchange").at("accepted") != true)
      throw std::runtime_error("Pinned continuous/discrete execution or preflight accounting failed");
    runtime.dispatchHook("onTrackEnd", context, nullptr, false);
    report = runtime.dispatchHook("onRunEnd", context, nullptr, false);
    const auto withoutMismatch = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    if (report.predictCount != 33 || withoutMismatch != pins)
      throw std::runtime_error("Artifact rejection changed deterministic draws or transition sequence");
    context.determinismMode = "strict";
    report = runtime.dispatchHook("onRunEnd", context, nullptr, false);
    const auto strictPins = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    if (report.predictCount || strictPins.at("success").at("error").at("code") != "strict_disabled" ||
        strictPins.at("state").at("temperature_k")[0] != 300 || strictPins.at("amount").at("source")[0] != 2)
      throw std::runtime_error("Strict pinned operators inferred or mutated state");
    context.determinismMode = "predictive";
    report = runtime.dispatchHook("onStep", context, nullptr, false);
    const auto units = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    if (report.predictCount != 33 || units.at("mismatch").at("error").at("code") != "unit_mismatch" ||
        units.at("discreteMismatch").at("error").at("code") != "unit_mismatch" ||
        units.at("unknown").at("error").at("code") != "unit_metadata_missing" ||
        units.at("success").at("accepted") != true || units.at("state").at("temperature_k")[0] != 304 ||
        units.at("exchange").at("accepted") != true)
      throw std::runtime_error("Unit checks lost continuous/discrete execution or preflight accounting");
    runtime.dispatchHook("onTrackStart", context, nullptr, false);
    report = runtime.dispatchHook("onStep", context, nullptr, false);
    const auto withoutUnitMismatch = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    if (report.predictCount != 33 || withoutUnitMismatch != units)
      throw std::runtime_error("Unit rejection changed deterministic draws or transition sequence");
    context.determinismMode = "strict";
    report = runtime.dispatchHook("onStep", context, nullptr, false);
    const auto strictUnits = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    if (report.predictCount || strictUnits.at("success").at("error").at("code") != "strict_disabled" ||
        strictUnits.at("state").at("temperature_k")[0] != 300 || strictUnits.at("amount").at("source")[0] != 2)
      throw std::runtime_error("Strict unit checks inferred or mutated state");
    trech::JsRuntime fresh;
    (void)fresh.evalExperimentAndGetConfigJson(scriptPath.string());
    fresh.dispatchHook("onInit", context, nullptr, false);
    const auto reloaded = nlohmann::json::parse(fresh.takeEmittedRecords().at(0).payloadJson);
    if (reloaded.at("operators")[3].at("content_id") == entries[3].at("content_id") ||
        reloaded.at("operators")[3].at("content_id") != "fnv1a64:" + trech::fnv1a64Hex(changed.dump()))
      throw std::runtime_error("Fresh runtime did not fingerprint replaced relative-path artifact");
    fs::remove_all(directory);
    std::cout << "Process units, capabilities, rollback, strict gating and engine execution pass\n";
  } catch (const std::exception& error) {
    fs::remove_all(directory);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
