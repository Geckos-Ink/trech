#include "TemporaryDirectory.hpp"

#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

// Coupled sensible/latent energy accounting for process bindings (`energy_balance`).
// Synthetic constant-rate maps test the contract, not a physical phase-change response:
// a proposal is committed only when the declared energy terms balance the declared source.
namespace {
void writeModel(const std::filesystem::path& path, double dTdt, double dfdt) {
  const nlohmann::json model = {
      {"model", "generic_surrogate_v1"}, {"input_features", {"forcing"}},
      {"output_features", {"d_temperature_k_dt", "d_melt_fraction_dt"}},
      {"layers", {{{"weights", {{0.0}, {0.0}}}, {"bias", {dTdt, dfdt}}, {"activation", "none"}}}}};
  std::ofstream(path) << model.dump();
}
}  // namespace

int main() {
  namespace fs = std::filesystem;
  const trech::test::TemporaryDirectory fixture;
  const auto& directory = fixture.path();
  try {
    // Balanced: C dT + L df = 50 J/K * (-2 K/s) + 1e4 J * 0.01 /s = 0 W per element.
    writeModel(directory / "balanced.json", -2.0, 0.01);
    // Unbalanced: the melt costs 200 W but only 100 W of sensible heat is released.
    writeModel(directory / "unbalanced.json", -2.0, 0.02);
    const auto scriptPath = directory / "main.js";
    {
      std::ofstream script(scriptPath);
      for (const auto* file : {"trech_process_runtime.js", "trech_process_operators.js"})
        script << "TRECH_INCLUDE(" << nlohmann::json((fs::path(TRECH_SOURCE_DIR) / "js" / file).string()).dump() << ");\n";
      script << R"JS(
function check(ok, message) { if (!ok) throw new Error(message); }
function rejects(fn, pattern) {
  let caught = null; try { fn(); } catch (error) { caught = String(error.message || error); }
  check(caught !== null, 'Invalid contract accepted');
  if (pattern) check(pattern.test(caught), 'Unexpected error: ' + caught);
}
globalThis.TRECH_CONFIG = {models: [
  {name:'balanced', path:'balanced.json', scale:'meso', operator_role:'melt_ok', element_kind:'wax', required_context_keys:['forcing']},
  {name:'unbalanced', path:'unbalanced.json', scale:'meso', operator_role:'melt_bad', element_kind:'wax', required_context_keys:['forcing']}
]};
const base = {id:'melt', operation:'evolve', operator_role:'melt_ok', element_kind:'wax',
  fields:[{name:'temperature_k', unit:'K', min:0}, {name:'melt_fraction', unit:'1', min:0, max:1}],
  aux:[{name:'heat_capacity', unit:'J/K', min:0}, {name:'latent_heat', unit:'J', min:0}],
  context:[{name:'forcing', unit:'1'}, {name:'heating_w', unit:'W'}],
  provenance:{basis:'Synthetic boundary test only'}};
const energy = {unit:'J', terms:[{field:'temperature_k', per_unit:'heat_capacity'},
                                 {field:'melt_fraction', per_unit:'latent_heat'}]};
// Bind-time declaration checks.
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:{...energy, unit:'K'}}), /not an energy/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:{...energy,
  terms:[{field:'pressure', per_unit:'heat_capacity'}]}}), /not a state field/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:{...energy,
  terms:[{field:'temperature_k', per_unit:'mass_kg'}]}}), /declared aux/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, aux:[{name:'heat_capacity', unit:'kg'}, {name:'latent_heat', unit:'J'}],
  energy_balance:energy}), /not energy/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:{...energy, source:'forcing'}}), /not a power/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:{...energy, source:'missing'}}), /declared context/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:{...energy, scope:'pairs'}}), /scope/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:{...energy, relative_tolerance:-1}}), />= 0/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:{...energy,
  terms:[energy.terms[0], energy.terms[0]]}}), /Duplicate/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({id:'swap', operation:'react', operator_role:'r', element_kind:'wax',
  species:[{name:'a', unit:'parcel'}], channels:[{name:'c', delta:{a:0}}], conservation:[{name:'n', coefficients:{a:1}}],
  provenance:{basis:'Synthetic boundary test only'}, energy_balance:energy}), /evolve\/interact/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({id:'pairs', operation:'interact', operator_role:'melt_ok', element_kind:'wax',
  fields:[{name:'temperature_k', unit:'K', symmetry:'antisymmetric'}], aux:[{name:'heat_capacity', unit:'J/K'}],
  spatial:{axes:{x:'x', y:'y', z:'z'}, unit:'m', cutoff:1}, provenance:{basis:'Synthetic boundary test only'},
  energy_balance:{unit:'J', scope:'element', terms:[{field:'temperature_k', per_unit:'heat_capacity'}]}}), /scope total/);
check(TRECH_PROCESS_OPERATORS.bind(base).energy === undefined, 'energy audit without the declaration');
const bound = TRECH_PROCESS_OPERATORS.bind({...base, energy_balance:energy});
check(bound.energy.scope === 'element' && bound.energy.terms.length === 2 && bound.energy.terms[1].factor === 1,
  'bound energy audit');
// kJ latent heat is converted by the unit factor, not reinterpreted.
const scaled = TRECH_PROCESS_OPERATORS.bind({...base, aux:[{name:'heat_capacity', unit:'J/K'}, {name:'latent_heat', unit:'kJ'}],
  energy_balance:energy});
check(Math.abs(scaled.energy.terms[1].factor - 1000) < 1e-9, 'kJ factor');
const unbalanced = TRECH_PROCESS_OPERATORS.bind({...base, operator_role:'melt_bad', energy_balance:energy});
const powered = TRECH_PROCESS_OPERATORS.bind({...base, operator_role:'melt_bad', energy_balance:{...energy, source:'heating_w'}});
const total = TRECH_PROCESS_OPERATORS.bind({...base, operator_role:'melt_bad', energy_balance:{...energy, scope:'total',
  source:'heating_w'}});
const unchecked = TRECH_PROCESS_OPERATORS.bind({...base, operator_role:'melt_bad'});
globalThis.TRECH_HOOKS = {onEventEnd(ctx) {
  const parcels = (latent) => ({temperature_k:[320, 330], melt_fraction:[0.2, 0.5],
    heat_capacity:[50, 50], latent_heat:[latent, latent]});
  const ok = parcels(1e4), kj = parcels(10), bad = parcels(1e4), fed = parcels(1e4), sum = parcels(1e4), raw = parcels(1e4);
  ctx.emit('energy', {
    ok: bound.advance(ctx, ok, 1, {forcing:0, heating_w:0}), okState: ok,
    kj: scaled.advance(ctx, kj, 1, {forcing:0, heating_w:0}), kjState: kj,
    bad: unbalanced.advance(ctx, bad, 1, {forcing:0, heating_w:0}), badState: bad,
    fed: powered.advance(ctx, fed, 1, {forcing:0, heating_w:100}), fedState: fed,
    // 100 W per element is 200 W for the two parcels: a total-scope source of 100 W leaves 100 W.
    sum: total.advance(ctx, sum, 1, {forcing:0, heating_w:100}), sumState: sum,
    sumOk: total.advance(ctx, parcels(1e4), 1, {forcing:0, heating_w:200}),
    raw: unchecked.advance(ctx, raw, 1, {forcing:0, heating_w:0}), rawState: raw});
}};
)JS";
    }
    trech::JsRuntime runtime;
    (void)runtime.evalExperimentAndGetConfigJson(scriptPath.string());
    trech::HookRuntimeContext context;
    context.seed = 3;
    context.determinismMode = "predictive";
    runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto emits = runtime.takeEmittedRecords();
    if (emits.size() != 1) throw std::runtime_error("Missing energy emit");
    const auto out = nlohmann::json::parse(emits[0].payloadJson);
    auto require = [](bool ok, const char* what) { if (!ok) throw std::runtime_error(what); };
    const auto& ok = out.at("ok");
    require(ok.at("accepted") == true && ok.at("energy").at("scope") == "element" &&
                ok.at("energy").at("max_residual").get<double>() < 1e-9 &&
                std::abs(ok.at("energy").at("gross_exchange").get<double>() - 400.0) < 1e-9,
            "a balanced sensible/latent proposal is committed with its residual");
    require(out.at("okState").at("temperature_k")[0] == 318 &&
                std::abs(out.at("okState").at("melt_fraction")[0].get<double>() - 0.21) < 1e-12,
            "the balanced proposal changed the state");
    require(out.at("kj").at("accepted") == true, "a kJ latent heat balances through its unit factor");
    const auto& bad = out.at("bad");
    require(bad.at("accepted") == false && bad.at("ran") == true &&
                bad.at("error").at("code") == "energy_imbalance",
            "an unbalanced proposal is refused as energy_imbalance");
    require(out.at("badState").at("temperature_k")[0] == 320 && out.at("badState").at("melt_fraction")[1] == 0.5,
            "a refused proposal leaves the state untouched");
    require(out.at("fed").at("accepted") == true && out.at("fedState").at("temperature_k")[0] == 318,
            "a declared 100 W source pays for the extra melt");
    require(out.at("sum").at("error").at("code") == "energy_imbalance" && out.at("sumOk").at("accepted") == true,
            "total scope balances the population against the total source");
    require(out.at("raw").at("accepted") == true && !out.at("raw").contains("energy"),
            "a contract without energy_balance is unchanged");
    context.determinismMode = "strict";
    runtime.dispatchHook("onEventEnd", context, nullptr, false);
    const auto strict = nlohmann::json::parse(runtime.takeEmittedRecords().at(0).payloadJson);
    require(strict.at("ok").at("error").at("code") == "strict_disabled", "strict mode does not advance");
    std::cout << "Process energy balance: declarations, sensible/latent balance, sources, scopes and refusal pass\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
