#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

int main() {
  namespace fs = std::filesystem;
  const auto directory = fs::temp_directory_path() / ("trech_process_spatial_" +
      std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  fs::create_directories(directory);
  try {
    // Deliberately synthetic maps. These validate spatial execution, not heat transport.
    auto model = nlohmann::json::parse(R"({"model":"generic_surrogate_v1",
      "input_features":["dz","r","a_energy_j","b_energy_j","a_mass","b_mass"],
      "output_features":["d_energy_j_dt"],
      "feature_units":{"inputs":{"dz":"m","r":"m","a_energy_j":"J","b_energy_j":"J",
        "a_mass":"kg","b_mass":"kg"},"outputs":{"d_energy_j_dt":"J/s"}},
      "layers":[{"weights":[[1,0,0,0,0,0]],"bias":[0]}]})");
    for (int factor = 1; factor <= 3; ++factor) {
      model["layers"][0]["weights"][0][0] = factor;
      std::ofstream(directory / (std::to_string(factor) + ".json")) << model.dump();
    }
    const auto scriptPath = directory / "main.js";
    {
      std::ofstream script(scriptPath);
      for (const auto* file : {"trech_process_runtime.js", "trech_process_operators.js"})
        script << "TRECH_INCLUDE(" << nlohmann::json((fs::path(TRECH_SOURCE_DIR) / "js" / file).string()).dump() << ");\n";
      script << R"JS(
function check(ok,message){if(!ok)throw new Error(message);}
function rejects(fn){let caught=false;try{fn();}catch(_){caught=true;}check(caught,'Invalid spatial definition accepted');}
const definition={id:'exchange',operation:'interact',operator_role:'exchange',
  element_kinds:{field:'kind',allowed:['beta','alpha']},
  fields:[{name:'energy_j',unit:'J',symmetry:'antisymmetric'}],aux:[{name:'mass',unit:'kg'}],
  spatial:{axes:{x:'x_m',y:'y_m',z:'z_m'},unit:'m',cutoff:1.1},
  model_units:{inputs:{dz:'m',r:'m',a_energy_j:'J',b_energy_j:'J',a_mass:'kg',b_mass:'kg'},
    outputs:{d_energy_j_dt:'J/s'}},provenance:{basis:'Synthetic spatial boundary test only'}};
const binding=TRECH_PROCESS_OPERATORS.bind(definition);
definition.spatial.cutoff=100;binding.contract.spatial.axes.z='tampered';
const base={...binding.contract,spatial:{axes:{x:'x_m',y:'y_m',z:'z_m'},unit:'m',cutoff:1.1}};
for(const spatial of [null,{}, {...base.spatial,axes:{x:'x_m',y:'y_m'}},
    {...base.spatial,axes:{x:'x_m',y:'y_m',z:'x_m'}}, {...base.spatial,unit:''},
    {...base.spatial,cutoff:0}, {...base.spatial,max_pairs:-1},{...base.spatial,max_pairs:1.5},
    {...base.spatial,axes:{x:'energy_j',y:'y_m',z:'z_m'}}])
  rejects(()=>TRECH_PROCESS_OPERATORS.bind({...base,spatial}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...base,fields:[{name:'energy_j',unit:'J'}]}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...base,links:{a:[0],b:[1]}}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...base,element_kinds:{field:'kind',allowed:['a|b','c']}}));
rejects(()=>TRECH_PROCESS_OPERATORS.bind({...base,element_kinds:{field:'kind',allowed:['\ud800','alpha']}}));
for(const inputs of [{...base.model_units.inputs,dz:'cm'}, {...base.model_units.inputs,a_energy_j:'K'},
    {...base.model_units.inputs,b_mass:'g'}, {...base.model_units.inputs,ux:'m'}])
  rejects(()=>TRECH_PROCESS_OPERATORS.bind({...base,model_units:{...base.model_units,inputs}}));
const initial=()=>({energy_j:[10,20,30],mass:[1,1,1],x_m:[0,0,0],y_m:[0,0,1],z_m:[0,1,0],kind:['alpha','beta','alpha']});
const unchecked=TRECH_PROCESS_OPERATORS.bind({...base,model_units:undefined});
let calls=0;
const fake={runtime:{mode:'predictive'},interact(spec){calls++;
  check(spec.require_complete_selection && spec.positions.z[1]===1 && spec.cutoff===1.1 &&
    spec.fields[0].symmetry==='antisymmetric','Spatial spec lost geometry/gate/symmetry');
  spec.positions.z[1]=999;spec.aux.mass[0]=999;spec.element_kind[0]='tampered';
  spec.state.energy_j[0]=11;return {ran:true,inferenceCount:2};}};
for(const z_m of [undefined,[],[0],[0,1,0,1],[0,,0],[0,NaN,0],[0,Infinity,0]])
  check(unchecked.advance(fake,{...initial(),z_m},1).error.code==='invalid_binding','Invalid coordinates reached engine');
check(calls===0,'Invalid coordinates inferred');
const fakeState=initial();
check(unchecked.advance(fake,fakeState,1).accepted && fakeState.energy_j[0]===11 &&
  fakeState.z_m[1]===1 && fakeState.mass[0]===1 && fakeState.kind[0]==='alpha','Read-only geometry/aux/kinds aliased');
const before=JSON.stringify(fakeState);
const invalid=unchecked.advance({...fake,interact(spec){spec.state.energy_j[0]=NaN;return {ran:true,inferenceCount:2};}},fakeState,1);
check(invalid.error.code==='invalid_proposal' && invalid.engine.inferenceCount===2 && JSON.stringify(fakeState)===before,
  'Invalid proposal committed or hid accounting');
// C++ sorts UTF-8 bytes, whereas default JS sort puts this astral name before the BMP name.
const bmp='\ue000',astral='\ud800\udc00';
const unicode=TRECH_PROCESS_OPERATORS.bind({...base,element_kinds:{field:'kind',allowed:[astral,bmp]}});
const unicodeHost={...fake,operatorCatalog(){return {schema:'trech_operator_catalog_v1',operators:
  [bmp+'|'+bmp,bmp+'|'+astral,astral+'|'+astral].map((kind,i)=>({name:'unicode'+i,loaded:true,
    operator_role:'exchange',element_kind:kind,inputs:Object.keys(base.model_units.inputs),
    outputs:Object.keys(base.model_units.outputs),feature_units:base.model_units}))};}};
check(unicode.advance(unicodeHost,{...initial(),kind:[bmp,astral,bmp]},1).accepted,'Pair kind order differs from C++ UTF-8');
globalThis.TRECH_CONFIG={models:[
  {name:'aa',path:'1.json',scale:'meso',operator_role:'exchange',element_kind:'alpha|alpha'},
  {name:'ab',path:'2.json',scale:'meso',operator_role:'exchange',element_kind:'alpha|beta'},
  {name:'bb',path:'3.json',scale:'meso',operator_role:'exchange',element_kind:'beta|beta'},
  {name:'partial',path:'1.json',scale:'meso',operator_role:'partial',element_kind:'alpha|alpha'}
]};
let skipFailures=false;
globalThis.TRECH_HOOKS={onRunStart(){skipFailures=true;},onEventEnd(ctx){
  const state=initial();
  if(ctx.runtime.mode==='strict'){
    check(binding.advance({...ctx,operatorCatalog(){throw new Error('Strict read catalog');}},state,1).error.code==='strict_disabled',
      'Strict spatial binding ran');
    check(ctx.interact({positions:{x:[NaN]}})===null,'Strict raw spatial call parsed/inferred');
    ctx.emit('spatial',{strict:true,state});return;
  }
  const catalog=ctx.operatorCatalog(), pins=catalog.operators.filter(m=>m.operator_role==='exchange')
    .map(m=>({name:m.name,content_id:'sha256:'+m.sha256}));
  const pinned=TRECH_PROCESS_OPERATORS.bind({...base,model_artifacts:pins});
  if(!skipFailures){
    const badPins=TRECH_PROCESS_OPERATORS.bind({...base,model_artifacts:pins.slice(0,2)});
    check(badPins.advance(ctx,state,1).error.code==='artifact_mismatch','Pair group omitted by pin check');
    const missingUnits={...ctx,operatorCatalog(){const c=ctx.operatorCatalog();
      c.operators=c.operators.filter(m=>m.name!=='bb');return c;}};
    check(binding.advance(missingUnits,state,1).error.code==='unit_metadata_missing','Inactive pair kind omitted by unit check');
    const badUnits={...ctx,operatorCatalog(){const c=ctx.operatorCatalog();
      c.operators.find(m=>m.name==='ab').feature_units.inputs.dz='cm';return c;}};
    check(binding.advance(badUnits,state,1).error.code==='unit_mismatch','Cross-material geometry units unchecked');
    const raw={dt:1,fields:[{name:'energy_j',symmetry:'antisymmetric'}],state:{energy_j:[10,20,30]},
      aux:{mass:[1,1,1]},positions:{x:[0,0,0],y:[0,0,1],z:[0,1,0]},cutoff:1.1,
      links:{a:[0],b:[2]},pair_fields:[{name:'bond'}],pair_state:{bond:[7]},
      element_kind:['alpha','beta','alpha'],operator_role:'partial',require_complete_selection:true};
    const rawBefore=JSON.stringify(raw);
    const gate=ctx.interact(raw);
    check(!gate.ran && gate.blockedReason==='incomplete_selection' && gate.inferenceCount===0 &&
      gate.selection.status==='partial' && JSON.stringify(raw)===rawBefore,'Pair gate ran or mutated element/pair state');
    rejects(()=>ctx.interact({...raw,require_complete_selection:'yes'}));
    const none=ctx.interact({...raw,operator_role:'absent'});
    check(!none.ran && none.selection.status==='no_compatible' && none.inferenceCount===0,'Missing operator gate failed');
    const ambiguous=ctx.interact({...raw,operator_role:undefined,element_kind:'alpha|alpha'});
    check(!ambiguous.ran && ambiguous.selection.status==='ambiguous' && ambiguous.inferenceCount===0,'Ambiguous pair gate failed');
    for(const positions of [null,{}, {x:[0,0,0],y:[0,0,1]},
        {...raw.positions,z:[0,NaN,0]}, {...raw.positions,z:[0,Infinity,0]},
        {...raw.positions,z:[0,,0]}, {...raw.positions,z:[0,null,0]}, {...raw.positions,z:[0,'1',0]},
        {...raw.positions,z:[0,1]}, {...raw.positions,z:[0,1,0,2]}])
      rejects(()=>ctx.interact({...raw,positions}));
    check(JSON.stringify(raw)===rawBefore,'Rejected raw geometry changed state');
    const partialBinding=TRECH_PROCESS_OPERATORS.bind({...unchecked.contract,operator_role:'partial'});
    const machine=TRECH_PROCESS_RUNTIME.create({initial:initial(),validate(){},
      stages:[{id:'exchange',complete(){return false;},advance:(host,draft,dt)=>partialBinding.advance(host,draft,dt)}]});
    const blocked=machine.step(ctx,1);
    check(blocked.status==='blocked' && blocked.elapsed_s===0 && JSON.stringify(blocked.state)===JSON.stringify(initial()),
      'Blocked spatial process advanced clock/state');
  }
  const report=pinned.advance(ctx,state,1);
  check(report.accepted && report.engine.pairCount===2 && report.engine.inferenceCount===2 && report.artifacts.length===3 &&
    JSON.stringify(state.energy_j)==='[12,18,30]','Wrong neighbour exchange or pair-kind selection');
  state.kind=['beta','beta','alpha'];state.energy_j=[10,20,30];
  const changed=pinned.advance(ctx,state,1);
  check(changed.accepted && JSON.stringify(state.energy_j)==='[13,17,30]','Dynamic pair kind unchanged');
  const moved=initial();moved.z_m[1]=2;
  const distance=pinned.advance(ctx,moved,1);
  check(distance.accepted && distance.engine.pairCount===1 && distance.engine.inferenceCount===1 &&
    JSON.stringify(moved.energy_j)==='[10,20,30]','Z coordinate not used in 3D neighbour search');
  const capped=TRECH_PROCESS_OPERATORS.bind({...base,spatial:{...base.spatial,max_pairs:1}});
  const cappedMachine=TRECH_PROCESS_RUNTIME.create({initial:initial(),validate(){},
    stages:[{id:'capped',complete(){return false;},advance:(host,draft,dt)=>capped.advance(host,draft,dt)}]});
  const cappedStep=cappedMachine.step(ctx,1), truncated=cappedStep.report;
  check(truncated.ran && !truncated.accepted && truncated.error.code==='invalid_proposal' &&
    truncated.engine.neighborPairsTruncated && truncated.engine.inferenceCount===1 &&
    cappedStep.status==='rejected' && cappedStep.elapsed_s===0 &&
    JSON.stringify(cappedStep.state)===JSON.stringify(initial()),'Truncated spatial proposal committed or hid inference');
  const scalar=TRECH_PROCESS_OPERATORS.bind({...base,element_kinds:undefined,element_kind:'alpha|beta',
    fields:[{name:'energy_j',unit:'J',symmetry:'symmetric'}]}), symmetricState=initial();
  const symmetric=scalar.advance(ctx,symmetricState,1);
  check(symmetric.accepted && symmetric.engine.inferenceCount===2 && symmetric.artifacts.length===1 &&
    JSON.stringify(symmetricState.energy_j)==='[12,22,30]','Scalar operator kind or symmetric contributions broken');
  const isolated=initial();isolated.z_m=[0,10,20];
  const empty=pinned.advance(ctx,isolated,1);
  check(!empty.ran && !empty.accepted && empty.engine.pairCount===0 && empty.engine.inferenceCount===0 &&
    JSON.stringify(isolated.energy_j)==='[10,20,30]','Empty neighbourhood fabricated exchange');
  // Raw calls retain their documented partial execution unless the gate is requested.
  const rawState={energy_j:[10,20,30]};
  const partial=ctx.interact({dt:1,fields:[{name:'energy_j',symmetry:'antisymmetric'}],state:rawState,
    aux:{mass:[1,1,1]},positions:{x:new Float64Array([0,0,0]),y:new Float64Array([0,0,0]),
      z:new Float64Array([0,1,2])},cutoff:1.1,
    element_kind:['alpha','alpha','beta'],operator_role:'partial'});
  check(partial.ran && partial.selection.status==='partial' && partial.inferenceCount===1 &&
    JSON.stringify(rawState.energy_j)==='[11,19,30]','Raw partial pair behavior changed');
  ctx.emit('spatial',{state,report,changed,moved,distance,truncated,symmetric,symmetricState,empty,partial,rawState,rng:ctx.rng.uniform()});
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
      throw std::runtime_error("Strict spatial binding inferred or lost emit");
    context.determinismMode = "predictive";
    report = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    emits = runtime.takeEmittedRecords();
    if (report.predictCount != 9 || emits.size() != 1)
      throw std::runtime_error("Spatial binding lost inference accounting or emit");
    runtime.dispatchHook("onRunStart", context, nullptr, false);
    const auto replay = runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto replayEmits = runtime.takeEmittedRecords();
    if (replay.predictCount != 9 || replayEmits.at(0).payloadJson != emits.at(0).payloadJson)
      throw std::runtime_error("Rejected spatial preflight changed replay/RNG");
    fs::remove_all(directory);
    std::cout << "Spatial neighbour bindings, complete selection and exact replay pass\n";
  } catch (const std::exception& error) {
    fs::remove_all(directory);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
