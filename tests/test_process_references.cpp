#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
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
      for (const auto* name : {"trech_crystallization_reference.js", "trech_euler_reference.js"})
        script << "TRECH_INCLUDE(" << nlohmann::json((root / "examples/experiments" / name).string()).dump() << ");\n";
      script << R"JS(
function check(ok, message) { if (!ok) throw new Error(message); }
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
    if (authoring.at("sources").size() != 3 || authoring.at("studio").at("title") != "Live authoring test" ||
        nlohmann::json::parse(config).contains("studio"))
      throw std::runtime_error("Inspection metadata changed simulation config or lost sources");
    for (const auto* name : {"nacl_dehydration_reference.js", "aerodynamics_reference.js"}) {
      trech::JsRuntime scenario;
      const auto cfg = nlohmann::json::parse(scenario.evalExperimentAndGetConfigJson(
          (root / "examples/experiments" / name).string()));
      if (cfg.at("run").at("threads") != 1 || cfg.at("hooks").at("inputs").at("scope").empty())
        throw std::runtime_error("Reference lost serial execution or scope");
    }
    std::filesystem::remove(path);
    std::cout << "Conservation, uniform flow, perturbation, replay and authoring metadata pass\n";
  } catch (const std::exception& error) {
    std::filesystem::remove(path);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
