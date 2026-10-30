#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>

int main() {
  const auto path = std::filesystem::temp_directory_path() /
      ("trech_scenario_helpers_" + std::to_string(
          std::chrono::steady_clock::now().time_since_epoch().count()) + ".js");
  try {
    {
      std::ofstream script(path);
      const auto include = [&](const char* name) {
        const auto source = std::filesystem::path(TRECH_SOURCE_DIR) /
            "js" / name;
        script << "TRECH_INCLUDE(" << nlohmann::json(source.string()).dump() << ");\n";
      };
      // Solver modules must load independently and share their dependency
      // instances when the ordinary scenario-helper entry point loads later.
      include("trech_water_md.js");
      script << "const originalRandom = globalThis.TRECH_RANDOM;\n";
      include("trech_foam_solver.js");
      script << "const originalMath = globalThis.TRECH_MATH;\n";
      include("trech_material_facts.js");
      script << "const originalFacts = globalThis.TRECH_MATERIAL_FACTS;\n";
      include("trech_helpers.js");
      script << R"JS(
function check(value, message) { if (!value) throw new Error(message); }
function throws(action, message) {
  let caught = false;
  try { action(); } catch (error) { caught = error.message === message; }
  check(caught, 'Expected error: ' + message);
}
const helpers = globalThis.TRECH_HELPERS;
check(helpers.random === originalRandom && helpers.math === originalMath &&
      helpers.materialFacts === originalFacts, 'Shared imports recreated dependencies');
check(typeof TRECH_WATER_MD.create === 'function' && typeof TRECH_FOAM.create === 'function',
      'Standalone solver imports failed');

const { math, random, materialFacts: facts } = helpers;
check(math.clamp('2.5', 0, 1) === 1 && math.clamp01(-2) === 0 &&
      Object.is(math.clamp01(-0), 0) && Number.isNaN(math.clamp(NaN, 0, 1)),
      'Numeric coercion/bounds changed');
check(math.round3(1.23456) === 1.235 && math.round4(1.23456) === 1.2346 &&
      math.smoothstep(0.5) === 0.5 && math.smoothstep(2) === 1, 'Rounding/easing changed');
check(math.finite('4', 'test') === 4, 'Finite input coercion changed');
throws(() => math.finite(Infinity, 'test'), 'non-finite inferred test');
const a = [1, 2, 3], b = [3, 4, 5];
check(JSON.stringify(math.mix3(a, b, 0.25)) === '[1.5,2.5,3.5]' &&
      JSON.stringify(a) === '[1,2,3]', 'Vector interpolation mutated its input');

const uniform = random.mulberry32(1);
const sequence = [0.6270739405881613, 0.002735721180215478,
                  0.5274470399599522, 0.9810509674716741];
for (const expected of sequence) check(uniform() === expected, 'Seeded RNG sequence changed');
check(uniform.uniform === uniform, 'Local RNG does not support the hook sampler protocol');
const rng = { draws: 0, uniform() {
  check(this === rng, 'RNG receiver was lost');
  return this.draws++ % 2 === 0 ? 0.5 : 0;
}};
check(random.gaussian(rng) === 1.1774100225154747 && rng.draws === 2,
      'Gaussian must consume exactly two draws');
random.gaussian(rng);
check(rng.draws === 4, 'Gaussian unexpectedly cached a spare draw');
check(Number.isFinite(random.gaussian({ uniform() { return 0; } })),
      'Zero uniform input must retain the existing finite Gaussian floor');
const noise = random.parcelNoise01(7, 3);
check(noise >= 0 && noise < 1 && noise === random.parcelNoise01(7, 3),
      'Parcel noise is not a stable identity/stream function');

const apparatus = { outputTicks: 8, durationS: 60, playbackDurationS: 12 };
const clock = helpers.observer.linearClock(apparatus);
check(JSON.stringify(clock(3)) === '{"physicalTimeS":22.5,"playbackTimeS":4.5,"timeScale":5}',
      'Frame clock changed its arithmetic or property order');
apparatus.durationS = 120;
check(clock(3).physicalTimeS === 45 && clock(3).timeScale === 10,
      'Clock lost an authored apparatus update');

const ctx = { optics: { sample: { display_rgb: [-1, 0.5, 2, 0.75],
  mean_refractive_index: '1.3', mean_absorption_length_mm: '10',
  mean_scatter_length_mm: '20', note: 'recorded source' } } };
check(JSON.stringify(facts.optics(ctx, 'sample')) ===
      '{"rgb":[0,0.5,1],"refractiveIndex":1.3,"absorptionLengthMm":10,"scatterLengthMm":20}',
      'Recorded optics changed shape, coercion or property order');
check(facts.optics(ctx, 'sample', true).note === 'recorded source', 'Optional note lost');
facts.opticsRgb(ctx, 'sample')[1] = 0;
check(ctx.optics.sample.display_rgb[1] === 0.5, 'Optics reader mutated recorded facts');
throws(() => facts.optics({}, 'missing'), 'ctx.optics missing Geant4-derived colour for missing');

globalThis.TRECH_PUBCHEM = () => ({ cid: '962', smiles: 'O', molecular_formula: 'H2O',
                                  density: 999, boiling_point: 999 });
check(JSON.stringify(facts.pubchemStructure('water')) === '{"cid":962,"smiles":"O","formula":"H2O"}',
      'Structure reader included properties beyond identity');
check(JSON.stringify(facts.formulaElements('C6H12O6')) === '["C","H","O"]',
      'Lexical element inventory changed');
check(facts.structureConsistent({ water: { formula: 'H2O' } }, ['H', 'O']) &&
      !facts.structureConsistent({ water: { formula: 'H2O' } }, ['H']),
      'Identity check ignored the scenario-declared element inventory');
globalThis.TRECH_PUBCHEM = () => ({ cid: 962 });
throws(() => facts.pubchemStructure('water'), 'PubChem structure cache for water must contain cid + smiles');
globalThis.TRECH_CONFIG = {};
)JS";
    }
    trech::JsRuntime runtime;
    runtime.evalExperimentAndGetConfigJson(path.string());
    std::filesystem::remove(path);
    std::cout << "shared JS imports, numerical helpers, seeded sampling and fact readers pass\n";
  } catch (const std::exception& error) {
    std::filesystem::remove(path);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
