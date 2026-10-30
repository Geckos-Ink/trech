#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

int main() {
  namespace fs = std::filesystem;
  const auto directory = fs::temp_directory_path() / ("trech_process_materials_" +
      std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  fs::create_directories(directory);
  try {
    // Synthetic operators exercise material isolation, not physical response.
    auto model = nlohmann::json::parse(R"({"model":"generic_surrogate_v1",
      "input_features":["forcing"],"output_features":["d_temperature_k_dt"],
      "feature_units":{"inputs":{"forcing":"K/s"},"outputs":{"d_temperature_k_dt":"K/s"}},
      "layers":[{"weights":[[1]],"bias":[0]}]})");
    std::ofstream(directory / "alpha.json") << model.dump();
    model["layers"][0]["weights"] = {{2}};
    std::ofstream(directory / "beta.json") << model.dump();
    model["output_features"] = {"hazard_transfer"};
    model["feature_units"] = {{"inputs", {{"forcing", "1/s"}}}, {"outputs", {{"hazard_transfer", "1/s"}}}};
    model["layers"][0]["weights"] = {{0}};
    model["layers"][0]["bias"] = {0.0};
    std::ofstream(directory / "transfer.json") << model.dump();
    model["layers"][0]["bias"] = {0.7};
    std::ofstream(directory / "transfer_beta.json") << model.dump();
    const auto scriptPath = directory / "main.js";
    {
      std::ofstream script(scriptPath);
      for (const auto* file : {"trech_process_runtime.js", "trech_process_operators.js"})
        script << "TRECH_INCLUDE(" << nlohmann::json((fs::path(TRECH_SOURCE_DIR) / "js" / file).string()).dump() << ");\n";
      script << R"JS(
function check(ok,message) {if(!ok) throw new Error(message);}
function rejects(fn) {let caught=false;try{fn();}catch(_){caught=true;}check(caught,'Invalid definition accepted');}
const base={id:'thermal',operation:'evolve',operator_role:'thermal',
  element_kinds:{field:'material_kind',allowed:['alpha','beta']},
  fields:[{name:'temperature_k',unit:'K',min:0,max:500}],aux:[{name:'mass',unit:'kg'}],
  context:[{name:'forcing',unit:'K/s'},{name:'beta_ready',unit:'1'}],
  model_units:{inputs:{forcing:'K/s'},outputs:{d_temperature_k_dt:'K/s'}},
  provenance:{basis:'Synthetic material binding test only'}};
for(const kinds of [null,[],{}, {field:'material_kind',allowed:[]},
    {field:'material_kind',allowed:['alpha','alpha']},{field:'material_kind',allowed:['']},
    {field:'temperature_k',allowed:['alpha']},{field:'constructor',allowed:['alpha']},
    {field:'material_kind',allowed:['alpha\0other']},{field:'material\0kind',allowed:['alpha']}])
  rejects(()=>TRECH_PROCESS_OPERATORS.bind({...base,element_kinds:kinds}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...base,element_kind:'alpha'}));
const checked=TRECH_PROCESS_OPERATORS.bind(base);
base.element_kinds.allowed[0]='tampered';checked.contract.element_kinds.field='tampered';
const initial=()=>({temperature_k:[300,310,320,330],mass:[1,1,1,1],material_kind:['alpha','beta','alpha','beta']});
const fake={runtime:{mode:'predictive'},evolve(spec){
  check(spec.require_complete_selection===true && spec.element_kind[0]==='alpha','Missing selection gate/kinds');
  spec.element_kind[0]='tampered';spec.state.temperature_k[0]=301;return {ran:true};}};
const unchecked=TRECH_PROCESS_OPERATORS.bind({...checked.contract,element_kinds:{field:'material_kind',allowed:['alpha','beta']},model_units:undefined});
const fakeState=initial();
check(unchecked.advance(fake,fakeState,1,{forcing:1,beta_ready:1}).accepted && fakeState.material_kind[0]==='alpha',
  'Kind array aliases engine proposal');
const beforeInvalid=JSON.stringify(fakeState);
const invalid=unchecked.advance({...fake,evolve(spec){spec.state.temperature_k[1]=600;return {ran:true};}},
  fakeState,1,{forcing:1,beta_ready:1});
check(invalid.error.code==='invalid_proposal' && JSON.stringify(fakeState)===beforeInvalid,'Material proposal partially committed');
for(const kinds of [undefined,[],['alpha'],['alpha','beta','alpha','unknown'],['alpha',,'alpha','beta']]){
  const state={...initial(),material_kind:kinds};
  check(unchecked.advance({...fake,evolve(){throw new Error('must not run');}},state,1,{forcing:1,beta_ready:1})
    .error.code==='invalid_binding','Invalid material binding reached inference');
}
const thermal=TRECH_PROCESS_OPERATORS.bind({...unchecked.contract,
  model_units:{inputs:{forcing:'K/s'},outputs:{d_temperature_k_dt:'K/s'}}});
const transfer=TRECH_PROCESS_OPERATORS.bind({id:'transfer',operation:'react',operator_role:'transfer',
  element_kinds:{field:'material_kind',allowed:['alpha','beta']},
  species:[{name:'source',unit:'parcel'},{name:'sink',unit:'parcel'}],
  context:[{name:'forcing',unit:'1/s'},{name:'beta_ready',unit:'1'}],
  channels:[{name:'transfer',delta:{source:-1,sink:1}}],
  conservation:[{name:'amount',coefficients:{source:1,sink:1}}],
  model_units:{inputs:{forcing:'1/s'},outputs:{hazard_transfer:'1/s'}},
  provenance:{basis:'Synthetic material binding test only'}});
globalThis.TRECH_CONFIG={models:[
  {name:'thermal_alpha',path:'alpha.json',scale:'meso',operator_role:'thermal',element_kind:'alpha',required_context_keys:['forcing']},
  {name:'thermal_beta',path:'beta.json',scale:'meso',operator_role:'thermal',element_kind:'beta',required_context_keys:['forcing','beta_ready']},
  {name:'transfer_alpha',path:'transfer.json',scale:'meso',operator_role:'transfer',element_kind:'alpha',required_context_keys:['forcing']},
  {name:'transfer_beta',path:'transfer_beta.json',scale:'meso',operator_role:'transfer',element_kind:'beta',required_context_keys:['forcing','beta_ready']}
]};
let skipFailures=false;
globalThis.TRECH_HOOKS={onRunStart(){skipFailures=true;},onEventEnd(ctx){
  const state=initial(), amount={source:Array(32).fill(2),sink:Array(32).fill(0),
    material_kind:Array.from({length:32},(_,i)=>i%2?'beta':'alpha')};
  const context={forcing:1,beta_ready:1};
  if(ctx.runtime.mode==='strict'){
    const host={...ctx,operatorCatalog(){throw new Error('Strict must not read catalog');}};
    check(thermal.advance(host,state,2,context).error.code==='strict_disabled','Strict thermal ran');
    check(transfer.advance(host,amount,1,context).error.code==='strict_disabled','Strict reaction ran');
    ctx.emit('materials',{strict:true,state,amount});return;
  }
  const catalog=ctx.operatorCatalog();
  const pins=role=>catalog.operators.filter(m=>m.operator_role===role).map(m=>({name:m.name,content_id:m.content_id}));
  const pinnedThermal=TRECH_PROCESS_OPERATORS.bind({...thermal.contract,model_artifacts:pins('thermal')});
  const pinnedTransfer=TRECH_PROCESS_OPERATORS.bind({...transfer.contract,model_artifacts:pins('transfer')});
  if(!skipFailures){
    // Capability checks cover both declared kinds, including currently unused kinds.
    const badPins=TRECH_PROCESS_OPERATORS.bind({...thermal.contract,model_artifacts:pins('thermal').slice(0,1)});
    check(badPins.advance(ctx,state,2,context).error.code==='artifact_mismatch','Incomplete material pins accepted');
    const badUnits={...ctx,operatorCatalog(){const c=ctx.operatorCatalog();
      c.operators.find(m=>m.name==='thermal_beta').feature_units.outputs.d_temperature_k_dt='degC/s';return c;}};
    check(thermal.advance(badUnits,state,2,context).error.code==='unit_mismatch','Second-kind units unchecked');
    const splitUnits=TRECH_PROCESS_OPERATORS.bind({...thermal.contract,
      model_units:{inputs:{forcing:'K/s'},outputs:{d_temperature_k_dt:'K/s',diagnostic:'1'}}});
    const splitHost={...ctx,operatorCatalog(){const c=ctx.operatorCatalog();
      const alpha=c.operators.find(m=>m.name==='thermal_alpha');alpha.outputs.push('diagnostic');
      alpha.feature_units.outputs.diagnostic='1';return c;}};
    check(splitUnits.advance(splitHost,state,2,context).error.code==='unit_mismatch','One kind supplied another kind missing IO');
    const absent={...ctx,operatorCatalog(){const c=ctx.operatorCatalog();c.operators=c.operators.filter(m=>m.name!=='thermal_beta');return c;}};
    const onlyAlpha={...initial(),material_kind:Array(4).fill('alpha')};
    check(thermal.advance(absent,onlyAlpha,2,context).error.code==='unit_metadata_missing','Unused declared kind escaped unit check');
    const incomplete=TRECH_PROCESS_OPERATORS.bind({...unchecked.contract,
      element_kinds:{field:'material_kind',allowed:['alpha','beta','missing']}});
    const machine=TRECH_PROCESS_RUNTIME.create({initial:{...initial(),material_kind:['alpha','beta','missing','alpha']},
      validate(){},stages:[{id:'thermal',complete(){return false;},advance:(host,draft,dt)=>incomplete.advance(host,draft,dt,context)}]});
    const blocked=machine.step(ctx,2);
    check(blocked.status==='blocked' && blocked.elapsed_s===0 && blocked.state.temperature_k[0]===300 &&
      blocked.report.engine.blockedReason==='incomplete_selection' && blocked.report.engine.inferenceCount===0 &&
      blocked.report.engine.selection.status==='partial','Incomplete selection advanced process');
    // A missing required context key blocks the entire raw call under the gate.
    for(const operation of ['evolve','react']){
      const raw=operation==='evolve'?{fields:['temperature_k'],state:{temperature_k:[300,310]}}:
        {species:['source','sink'],state:{source:[2,2],sink:[0,0]},channels:[{name:'transfer',delta:{source:-1,sink:1}}],
          conservation:[{name:'amount',coefficients:{source:1,sink:1}}]};
      const before=JSON.stringify(raw.state);
      const spec={...raw,dt:1,operator_role:operation==='evolve'?'thermal':'transfer',element_kind:['alpha','beta'],
        context:{forcing:1},require_complete_selection:true};
      const report=ctx[operation](spec);
      check(!report.ran && report.blockedReason==='incomplete_selection' && report.selection.status==='partial' &&
        report.inferenceCount===0 && report.drawCount===0 && JSON.stringify(raw.state)===before,'Gate ran partial operator');
      for(const [overrides,status] of [[{element_kind:['missing','missing']},'no_compatible'],
          [{operator_role:undefined,context},'ambiguous']]){
        const blocked=ctx[operation]({...spec,...overrides});
        check(!blocked.ran && blocked.selection.status===status && blocked.inferenceCount===0 &&
          JSON.stringify(raw.state)===before,'Gate ran unavailable or ambiguous operator');
      }
      rejects(()=>ctx[operation]({...spec,require_complete_selection:'yes'}));
    }
  }
  const evolved=pinnedThermal.advance(ctx,state,2,context);
  check(evolved.accepted && JSON.stringify(state.temperature_k)==='[302,314,322,334]' &&
    evolved.engine.inferenceCount===4 && evolved.engine.selection.groups.length===2,'Material thermal laws mixed');
  state.material_kind=['beta','alpha','beta','alpha'];
  const changed=pinnedThermal.advance(ctx,state,2,context);
  check(changed.accepted && JSON.stringify(state.temperature_k)==='[306,316,326,336]','Changed kinds ignored');
  const exchange=pinnedTransfer.advance(ctx,amount,1,context);
  check(exchange.accepted && exchange.engine.inferenceCount===32 && exchange.engine.rngCallIndex===0,'Blocked gates consumed reaction sequence');
  let transferred=0;
  for(let i=0;i<32;i++){
    check(amount.source[i]+amount.sink[i]===2,'Per-element conservation broken');
    if(i%2===0)check(amount.sink[i]===0,'Alpha used beta hazard');else transferred+=amount.sink[i];
  }
  check(transferred>0 && transferred<16,'Beta fixture did not exercise stochastic choices');
  // Existing raw calls still run matched populations and leave unmatched ones unchanged.
  const rawState={temperature_k:[300,310]};
  const partial=ctx.evolve({dt:1,fields:['temperature_k'],state:rawState,context:{forcing:1},
    operator_role:'thermal',element_kind:['alpha','missing']});
  check(partial.ran && partial.selection.status==='partial' && JSON.stringify(rawState.temperature_k)==='[301,310]',
    'Legacy partial selection changed');
  const rawAmount={source:[2,2],sink:[0,0]};
  const partialReaction=ctx.react({dt:1,species:['source','sink'],state:rawAmount,context,
    operator_role:'transfer',element_kind:['beta','missing'],require_complete_selection:false,
    channels:[{name:'transfer',delta:{source:-1,sink:1}}],conservation:[{name:'amount',coefficients:{source:1,sink:1}}]});
  check(partialReaction.ran && partialReaction.selection.status==='partial' && partialReaction.inferenceCount===1 &&
    rawAmount.source[1]===2 && rawAmount.sink[1]===0,'Legacy partial reaction changed');
  ctx.emit('materials',{state,amount,evolved,changed,exchange,partial,rawState,partialReaction,rawAmount,rng:ctx.rng.uniform()});
}};
)JS";
    }
    trech::JsRuntime runtime;
    (void)runtime.evalExperimentAndGetConfigJson(scriptPath.string());
    trech::HookRuntimeContext context;
    context.seed = 42;
    context.determinismMode = "strict";
    auto report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    auto emits = runtime.takeEmittedRecords();
    if (report.predictCount || emits.size() != 1)
      throw std::runtime_error("Strict material bindings inferred or lost emit");
    context.determinismMode = "predictive";
    report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    emits = runtime.takeEmittedRecords();
    if (report.predictCount != 42 || emits.size() != 1)
      throw std::runtime_error("Material bindings lost inference accounting or emit");
    runtime.dispatchHook("onRunStart", context, nullptr, false);
    const auto reference = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto replay = runtime.takeEmittedRecords();
    if (reference.predictCount != 42 || replay.at(0).payloadJson != emits.at(0).payloadJson)
      throw std::runtime_error("Failed material checks changed replay/RNG/sequence");
    fs::remove_all(directory);
    std::cout << "Dynamic material bindings, complete selection gates and exact replay pass\n";
  } catch (const std::exception& error) {
    fs::remove_all(directory);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
