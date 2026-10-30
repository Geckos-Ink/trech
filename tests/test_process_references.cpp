#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

int main() {
  const auto root = std::filesystem::path(TRECH_SOURCE_DIR);
  const auto path = std::filesystem::temp_directory_path() /
      ("trech_process_references_" + std::to_string(
          std::chrono::steady_clock::now().time_since_epoch().count()) + ".js");
  try {
    {
      std::ofstream script(path);
      for (const auto* name : {"trech_crystallization_reference.js", "trech_euler_reference.js", "trech_euler3d_reference.js"})
        script << "TRECH_INCLUDE(" << nlohmann::json((root / "js" / name).string()).dump() << ");\n";
      script << "TRECH_INCLUDE(" << nlohmann::json((root / "js/trech_solution_processes.js").string()).dump() << ");\n";
      script << R"JS(
function check(ok, message) { if (!ok) throw new Error(message); }
const recipe = TRECH_SOLUTION_PROCESSES.solution({water:{parcels:2},salt:{formula:'NaCl',parcels:2},
  parcelAmountMol:1e-6,temperatureK:293}).mix().heat({bathTemperatureK:373})
  .evaporate({remainingFraction:0}).crystallize({solidFraction:1}).compile();
recipe.plan.steps[0].role = 'tampered'; // returned metadata cannot change the executable plan
const machine = recipe.create();
let operatorCalls = 0;
const testEngine = {runtime:{mode:'predictive'}, react(spec) {
  operatorCalls++;
  check(spec.operator_role !== 'tampered', 'Recipe metadata mutated execution');
  if (spec.operator_role === 'solution_dissolution')
    check(spec.context.bath_temperature_k === undefined, 'Future heating boundary leaked into mixing');
  check(spec.conservation.length === 4, 'Missing atom conservation vectors');
  for (const [key,delta] of Object.entries(spec.channels[0].delta)) spec.state[key][0] += delta;
  return {ran:true};
}, evolve(spec) {operatorCalls++;spec.state.temperature_k[0]=spec.context.bath_temperature_k;return {ran:true};}};
check(machine.step({runtime:{mode:'strict'}},0.1).status === 'strict_disabled' && operatorCalls === 0,
  'Strict recipe invoked an operator');
for (let i=0;i<7;++i) machine.step(testEngine,0.1);
check(machine.snapshot().completed && machine.snapshot().state.salt_crystal[0]===2 &&
      machine.snapshot().state.water_vapour[0]===2, 'Process sequencing lost material');
const blocked = recipe.create(), before = JSON.stringify(blocked.snapshot().state);
check(blocked.step({runtime:{mode:'predictive'},react(){return {ran:false};}},0.1).status==='blocked' &&
      JSON.stringify(blocked.snapshot().state)===before, 'Blocked process mutated state');
const rejectedProcess = recipe.create();
check(rejectedProcess.step({runtime:{mode:'predictive'},react(spec){spec.state.salt_solid[0]=-1;return {ran:true};}},0.1).status==='rejected' &&
      JSON.stringify(rejectedProcess.snapshot().state)===before, 'Invalid model proposal committed');
const options = {side: 4, water: 256, solubility: 0.45, attachmentProbability: 1};
const crystal = TRECH_CRYSTALLIZATION_REFERENCE.create(options);
let draws = 0;
const rng = {uniform() {draws++; return 0.25;}};
let state = crystal.step(0, rng);
check(state.salt_crystal === 0 && draws === 0, 'Unsaturated solution crystallized');
for (let i = 1; i <= 80; ++i) {
  state = crystal.step(Math.min(256, 4 * i), rng);
  check(state.salt_dissolved + state.salt_crystal === 64 &&
    state.sodium_total === 64 && state.chlorine_total === 64 &&
    state.water_liquid + state.water_vapour === 256, 'Parcel inventory changed');
}
check(state.salt_crystal === 64 && state.water_liquid === 0, 'Dry charge did not crystallize');
const noGrowth = TRECH_CRYSTALLIZATION_REFERENCE.create({...options, attachmentProbability: 0});
check(noGrowth.step(256, rng).salt_crystal === 0, 'Attachment control ignored');
let rejected = false;
try { crystal.step(0, rng); } catch (_) { rejected = true; }
check(rejected, 'Solvent inventory allowed to run backwards');

const gas = {nx: 24, ny: 16, dx: 0.01, gamma: 1.4, gasConstant: 287.05,
             rho: 1.225, pressure: 101325, mach: 1.5};
const uniform = TRECH_EULER_REFERENCE.create({...gas, body: false});
const original = JSON.stringify(uniform.snapshot().cells);
for (let i = 0; i < 50; ++i) uniform.advance();
check(JSON.stringify(uniform.snapshot().cells) === original, 'Uniform open flow was not preserved');
function flow(mach) {
  const solver = TRECH_EULER_REFERENCE.create({...gas, mach});
  for (let i = 0; i < 80; ++i) solver.advance();
  const s = solver.snapshot();
  check(s.cells.every(c => c.rho > 0 && c.p > 0 && c.temperature > 0), 'Nonpositive flow state');
  check(s.balance_residual.every((v, k) => Math.abs(v) < 1e-10 * Math.max(1, Math.abs(s.integral[k]))), 'Flux balance lost');
  return s;
}
const gas3 = {...gas,nx:16,ny:12,nz:10};
const uniform3=TRECH_EULER3D_REFERENCE.create({...gas3,body:false,velocity:[100,3,7]});
const initial3=JSON.stringify(uniform3.snapshot().cells);
for(let i=0;i<15;i++)uniform3.advance();
check(JSON.stringify(uniform3.snapshot().cells)===initial3,'3D uniform transverse flow changed');
function flow3() {
  const solver=TRECH_EULER3D_REFERENCE.create(gas3);
  for(let i=0;i<30;i++)solver.advance();
  const s=solver.snapshot();
  check(s.integral.length===5 && s.cells.every(c=>c.rho>0&&c.p>0),'Invalid 3D state');
  check(s.balance_residual.every((v,k)=>Math.abs(v)<1e-10*Math.max(1,Math.abs(s.integral[k]))),'3D flux balance lost');
  check(s.cells.some(c=>Math.abs(c.vz)>1e-3)&&s.cells.some(c=>Math.abs(c.vy)>1e-3),'Transverse momentum missing');
  const line=s.cells.filter(c=>Math.abs(c.y-.065)<1e-8&&Math.abs(c.x-.045)<1e-8);
  check(new Set(line.map(c=>c.p)).size>1,'Pressure is extruded along z');
  return s;
}
check(JSON.stringify(flow3())===JSON.stringify(flow3()),'3D comparison replay differs');
const recording={schema:'trech_interface_sequence_v1',source:{kind:'independent_measurement',
  citation:'Synthetic parser fixture; not microscopy',method:'Synthetic mesh',license:'test only'},
  calibration:{length_unit:'um',spatial_uncertainty_um:0.1,time_uncertainty_s:0.01},
  validation:{method:'Synthetic parser check',reference:'test fixture',metrics:{error:0}},
  frames:[{time_s:0,vertices:[[0,0,0],[1,0,0],[0,1,0]],triangles:[[0,1,2]]}]};
const inspected=TRECH_INTERFACE_SEQUENCE(recording);
check(inspected.inspection.format_validated&&!inspected.inspection.physical_accuracy_verified,'Format inspection certified physical accuracy');
function rejectsInterface(change) {
  const data=JSON.parse(JSON.stringify(recording));change(data);
  let caught=false;try{TRECH_INTERFACE_SEQUENCE(data);}catch(_){caught=true;}
  check(caught,'Malformed interface recording accepted');
}
rejectsInterface(d=>delete d.calibration);
rejectsInterface(d=>d.frames.push(d.frames[0]));
rejectsInterface(d=>d.frames[0].vertices[0][0]=NaN);
rejectsInterface(d=>d.frames[0].triangles[0]=[0,1,3]);
rejectsInterface(d=>d.frames[0].triangles[0]=[0,0,1]);
rejectsInterface(d=>d.source.kind='inferred');
rejectsInterface(d=>d.validation.metrics={});
const flowA = flow(1.5), flowB = flow(1.5), slow = flow(0.5);
check(JSON.stringify(flowA) === JSON.stringify(flowB), 'Euler replay differs');
check(Math.max(...flowA.cells.map(c => c.p)) > gas.pressure * 1.2, 'No obstacle compression');
check(Math.max(...flowA.cells.map(c => c.temperature)) > Math.max(...slow.cells.map(c => c.temperature)),
      'Temperature is insensitive to inlet speed');
globalThis.TRECH_CONFIG = {};
globalThis.TRECH_STUDIO = {schema: 'trech_studio_v1', title: 'Live authoring test', processes: []};
)JS";
    }
    trech::JsRuntime runtime;
    const auto config = runtime.evalExperimentAndGetConfigJson(path.string());
    const auto authoring = nlohmann::json::parse(runtime.authoringMetadataJson());
    if (authoring.at("sources").size() != 7 || authoring.at("studio").at("title") != "Live authoring test" ||
        nlohmann::json::parse(config).contains("studio"))
      throw std::runtime_error("Inspection metadata changed simulation config or lost sources");
    for (const auto* name : {"nacl_dehydration_reference.js", "aerodynamics_reference.js"}) {
      trech::JsRuntime scenario;
      const auto cfg = nlohmann::json::parse(scenario.evalExperimentAndGetConfigJson(
          (root / "examples/scenarios" / std::filesystem::path(name).stem() / name).string()));
      if (cfg.at("run").at("threads") != 1 || cfg.at("hooks").at("inputs").at("scope").empty())
        throw std::runtime_error("Reference lost serial execution or scope");
      trech::HookRuntimeContext context;
      context.determinismMode = "strict";
      context.eventId = 0;
      context.materialsJson = "[]";
      context.maxEmitsPerCallback = 4;
      context.maxEmitPayloadBytes = 8388608;
      const auto report = scenario.dispatchHook("onEventEnd", context, nullptr, false);
      const auto records = scenario.takeEmittedRecords();
      if (report.emitDroppedCount || report.predictCount || records.empty())
        throw std::runtime_error("Reference hook lost data or performed inference");
      const bool salt = std::string(name).find("nacl") == 0;
      for (const auto& record : records)
        if (salt && record.tag == "material_frame")
          throw std::runtime_error("Inventories fabricated a microscope frame");
      // Optional debugging artifact is explicitly a host fixture, never Geant4 provenance.
      if (const char* output = std::getenv("TRECH_REFERENCE_EMITS_DIR")) {
        const auto directory = std::filesystem::path(output) / std::filesystem::path(name).stem();
        std::filesystem::create_directories(directory);
        std::ofstream file(directory / "trech_hook_emits.jsonl");
        for (const auto& record : records)
          file << nlohmann::json({{"tag",record.tag},{"payload",nlohmann::json::parse(record.payloadJson)},
            {"hook",record.hook},{"event_id",record.eventId},{"scope","C++ host fixture; no Geant4 transport"}}).dump() << '\n';
      }
    }
    const auto recordingPath = path.string() + ".json";
    const auto recording = nlohmann::json::parse(R"({"schema":"trech_interface_sequence_v1",
      "source":{"kind":"independent_measurement","citation":"Synthetic parser fixture","method":"Synthetic mesh","license":"test only"},
      "calibration":{"length_unit":"um","spatial_uncertainty_um":0.1,"time_uncertainty_s":0.01},
      "validation":{"method":"Synthetic boundary check","reference":"test only","metrics":{"error":0}},
      "frames":[{"time_s":0,"vertices":[[0,0,0],[1,0,0],[0,1,0]],"triangles":[[0,1,2]]}]})");
    std::ofstream(recordingPath) << recording.dump();
    try {
      trech::JsRuntime measured;
      measured.setScriptParameterOverrides({"interface_file=" + nlohmann::json(recordingPath).dump()});
      const auto config = nlohmann::json::parse(measured.evalExperimentAndGetConfigJson(
          (root / "examples/scenarios/nacl_dehydration_reference/nacl_dehydration_reference.js").string()));
      if (config.at("run").at("nEvents") != 1) throw std::runtime_error("Recording clock replaced by inventory ticks");
      trech::HookRuntimeContext context; context.eventId = 0; context.determinismMode = "strict";
      const auto report = measured.dispatchHook("onEventEnd",context,nullptr,false);
      const auto emits = measured.takeEmittedRecords();
      const auto payload = nlohmann::json::parse(emits.at(0).payloadJson);
      if (report.predictCount || report.emitDroppedCount || emits.size()!=1 || emits[0].tag!="material_frame" ||
          payload.at("length_unit")!="um" || payload.at("positions")!=recording.at("frames")[0].at("vertices"))
        throw std::runtime_error("Measured interface geometry/units changed");
    } catch (...) {std::filesystem::remove(recordingPath); throw;}
    std::filesystem::remove(recordingPath);
    std::filesystem::remove(path);
    std::cout << "Conservation, uniform flow, perturbation, replay and authoring metadata pass\n";
  } catch (const std::exception& error) {
    std::filesystem::remove(path);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
