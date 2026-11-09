#include "TemporaryDirectory.hpp"

#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

// Unit-label dimensional analysis and multiplicative conversion for process
// contracts (`TRECH_PROCESS_OPERATORS.units`, opt-in `dimensional_check`). The
// checks read declared labels; they never certify a model's physical units.
int main() {
  namespace fs = std::filesystem;
  const trech::test::TemporaryDirectory fixture;
  const auto& directory = fixture.path();
  try {
    const auto scriptPath = directory / "main.js";
    {
      std::ofstream script(scriptPath);
      for (const auto* file : {"trech_process_runtime.js", "trech_process_operators.js"})
        script << "TRECH_INCLUDE(" << nlohmann::json((fs::path(TRECH_SOURCE_DIR) / "js" / file).string()).dump() << ");\n";
      script << R"JS(
function check(ok, message) { if (!ok) throw new Error(message); }
function rejects(fn, pattern) {
  let caught = null; try { fn(); } catch (error) { caught = String(error.message || error); }
  check(caught !== null, 'Invalid input accepted');
  if (pattern) check(pattern.test(caught), 'Unexpected error: ' + caught);
}
const close = (a, b) => Math.abs(a - b) <= 1e-12 * Math.max(Math.abs(a), Math.abs(b));
const U = TRECH_PROCESS_OPERATORS.units;
// Parsing: SI prefixes, powers, left-to-right division, superscripts, counted nouns.
check(U.parse('K/s').dimension === 's^-1 K', 'K/s dimension');
check(U.parse('mol/L/s').dimension === 'm^-3 s^-1 mol' && close(U.parse('mol/L/s').scale, 1e3), 'mol/L/s');
check(U.parse('kg/m^3').dimension === U.parse('g/cm³').dimension, 'superscript powers');
check(close(U.factor('g/cm³', 'kg/m^3'), 1000), 'density conversion');
check(close(U.convert(2.5, 'MeV', 'J'), 2.5 * 1.602176634e-13), 'MeV to J');
check(close(U.convert(1, 'h', 's'), 3600) && close(U.convert(90, 'deg', 'rad'), Math.PI / 2), 'time/angle');
check(close(U.factor('mM', 'mol/m^3'), 1), 'millimolar');
check(U.parse('1').dimension === '1' && U.parse('parcels').dimension === '1', 'dimensionless/counts');
check(U.parse('mol/parcel').dimension === 'mol', 'amount per counted parcel');
check(U.parse('N m').dimension === U.parse('J').dimension && U.compatible('Pa', 'N/m2'), 'products');
check(!U.compatible('K', 'K/s') && U.compatible('1/ms', 'Hz'), 'compatibility');
rejects(() => U.factor('K', 'K/s'), /Incompatible units/);
rejects(() => U.parse('degC'), /Affine/);
rejects(() => U.parse('furlong'), /Unknown unit symbol/);
rejects(() => U.parse('K//s'), /Malformed/);
rejects(() => U.parse('/s'), /Malformed/);
rejects(() => U.parse(''), /explicit/);
rejects(() => U.convert(NaN, 'm', 'mm'), /finite/);

// Contract audit (opt-in). Labels stay exact for the runtime match; the audit adds
// dimension AND scale consistency because the engine integrates with dt in seconds.
const evolve = {id:'heat', operation:'evolve', operator_role:'thermal', element_kind:'test_material',
  fields:[{name:'temperature_k', unit:'K'}], aux:[{name:'mass_kg', unit:'kg'}],
  context:[{name:'forcing', unit:'K/s'}], provenance:{basis:'Synthetic boundary test only'},
  model_units:{inputs:{forcing:'K/s'}, outputs:{d_temperature_k_dt:'K/s'}}};
const plain = TRECH_PROCESS_OPERATORS.bind(evolve);
check(plain.dimensions === undefined && plain.contract.dimensional_check === undefined, 'Audit ran without opt-in');
const audited = TRECH_PROCESS_OPERATORS.bind({...evolve, dimensional_check:true});
check(audited.dimensions.schema === 'trech_process_dimensions_v1' && audited.dimensions.checks.length === 1 &&
  audited.dimensions.checks[0].ok && audited.dimensions.declared.temperature_k === 'K', 'Audit report');
audited.dimensions.checks[0].ok = false;
rejects(() => TRECH_PROCESS_OPERATORS.bind({...evolve, dimensional_check:'yes'}), /boolean/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...evolve, dimensional_check:true,
  model_units:{inputs:{forcing:'K/s'}, outputs:{d_temperature_k_dt:'K'}}}), /Dimensional mismatch/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...evolve, dimensional_check:true,
  model_units:{inputs:{forcing:'K/s'}, outputs:{d_temperature_k_dt:'K/min'}}}), /Dimensional mismatch/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...evolve, dimensional_check:true,
  model_units:{inputs:{forcing:'K/s'}, outputs:{set_temperature_k:'mK'}}}), /Dimensional mismatch/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...evolve, dimensional_check:true,
  fields:[{name:'temperature_k', unit:'degC'}]}), /Affine/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...evolve, dimensional_check:true,
  model_units:{inputs:{forcing:'K/s', drive:'furlongs'}, outputs:{d_temperature_k_dt:'K/s'}}}), /Unknown unit/);
// A millikelvin field takes a mK/s rate; a different but equivalent spelling also passes.
check(TRECH_PROCESS_OPERATORS.bind({...evolve, dimensional_check:true, fields:[{name:'temperature_k', unit:'mK'}],
  model_units:{inputs:{forcing:'K/s'}, outputs:{d_temperature_k_dt:'mK s^-1'}}}).dimensions.checks[0].ok, 'Scaled rate');
// Without opt-in, the legacy label-only binding still accepts a dimensionally wrong label.
TRECH_PROCESS_OPERATORS.bind({...evolve, model_units:{inputs:{forcing:'K/s'}, outputs:{d_temperature_k_dt:'K'}}});

const react = {id:'exchange', operation:'react', operator_role:'transfer', element_kind:'other_material',
  species:[{name:'source', unit:'parcel'}, {name:'sink', unit:'parcel'}], context:[{name:'forcing', unit:'1/s'}],
  channels:[{name:'transfer', delta:{source:-1, sink:1}}], conservation:[{name:'amount', coefficients:{source:1, sink:1}}],
  provenance:{basis:'Synthetic boundary test only'},
  model_units:{inputs:{forcing:'1/s'}, outputs:{hazard_transfer:'1/s'}}, dimensional_check:true};
check(TRECH_PROCESS_OPERATORS.bind(react).dimensions.checks[0].rule === 'hazard = 1/s', 'Hazard audit');
check(TRECH_PROCESS_OPERATORS.bind({...react, model_units:{inputs:{forcing:'1/s'}, outputs:{hazard_transfer:'Hz'}}})
  .dimensions.checks[0].ok, 'Hz hazard');
rejects(() => TRECH_PROCESS_OPERATORS.bind({...react, model_units:{inputs:{forcing:'1/s'}, outputs:{hazard_transfer:'1/ms'}}}),
  /Dimensional mismatch/);
rejects(() => TRECH_PROCESS_OPERATORS.bind({...react, model_units:{inputs:{forcing:'1/s'}, outputs:{hazard_other:'1/s'}}}),
  /no declared channel/);
check(Object.isFrozen(U), 'Unit API mutable');
globalThis.TRECH_CONFIG = {};
)JS";
    }
    trech::JsRuntime runtime;
    (void)runtime.evalExperimentAndGetConfigJson(scriptPath.string());
    if (runtime.totalPredictCount() != 0) throw std::runtime_error("Unit checks invoked inference");
    std::cout << "Process unit parsing, conversion and dimensional contract audit pass\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
