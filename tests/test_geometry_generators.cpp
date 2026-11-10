// js/trech_geometry.js: procedural generators emit the nested volume form
// DetectorConstruction reads, round-trip through the C++ config parser, and
// the read-only audit reports overlaps, containment and naming problems.
#include "TemporaryDirectory.hpp"

#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"

#include <nlohmann/json.hpp>

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>

namespace {
int expect(bool ok, const char* message) {
  if (!ok) std::cerr << "FAIL: " << message << '\n';
  return ok ? 0 : 1;
}
}  // namespace

int main() {
  const trech::test::TemporaryDirectory fixture;
  const auto path = fixture.path() / "geometry.js";
  int failures = 0;
  try {
    {
      std::ofstream script(path);
      const auto source = std::filesystem::path(TRECH_SOURCE_DIR) / "js" / "trech_geometry.js";
      script << "TRECH_INCLUDE(" << nlohmann::json(source.string()).dump() << ");\n";
      script << "TRECH_INCLUDE(" << nlohmann::json(source.string()).dump() << ");\n";
      script << R"JS(
function check(value, message) { if (!value) throw new Error(message); }
function throws(action, fragment) {
  let caught = '';
  try { action(); } catch (error) { caught = error.message; }
  check(caught.indexOf(fragment) >= 0, 'Expected error containing: ' + fragment + ' got: ' + caught);
}
const G = globalThis.TRECH_GEOMETRY;
check(Object.isFrozen(G), 'Library must be frozen');

const cells = G.grid({ name: 'cell', count: [3, 2, 1], pitchMm: [10, 0.1 * 3, 1],
                       centerMm: [0, 0, 3], material: 'G4_WATER',
                       shape: { type: 'box', sizeMm: [8, 0.2, 2] }, scoreEdep: true });
check(cells.length === 6 && cells[0].name === 'cell_0_0_0' && cells[5].name === 'cell_2_1_0',
      'Grid naming/order changed');
check(JSON.stringify(cells[0].placement.positionMm) === '[-10,-0.15,3]' &&
      JSON.stringify(cells[5].placement.positionMm) === '[10,0.15,3]',
      'Grid positions not centred or not cleaned: ' + JSON.stringify(cells[0].placement));
check(cells[0].tags[0] === 'grid:cell' && cells[0].scoreEdep === true, 'Grid tags/score lost');
throws(() => G.grid({ name: 'g', count: [2, 1, 1], shape: { type: 'box', sizeMm: 1 } }), 'pitchMm');
throws(() => G.grid({ name: 'g', count: [1.5, 1, 1], shape: { type: 'box', sizeMm: 1 } }), 'integer');

const ring = G.ring({ name: 'pmt', count: 4, radiusMm: 50, axis: 'z', orient: true,
                      shape: { type: 'tube', outerRadiusMm: 5, lengthMm: 10 } });
check(JSON.stringify(ring.map((v) => v.placement.positionMm)) ===
      '[[50,0,0],[0,50,0],[-50,0,0],[0,-50,0]]', 'Ring positions changed');
check(JSON.stringify(ring[1].placement.rotationDeg) === '[0,0,-90]', 'Ring orientation changed');

const stack = G.layerStack({ name: 'det', axis: 'z', sizeMm: [20, 30], centerMm: [0, 0, 0],
  layers: [{ material: 'G4_Pb', thicknessMm: 2 }, { material: 'G4_WATER', thicknessMm: 6, scoreEdep: true }] });
check(JSON.stringify(stack[0].shape.sizeMm) === '[20,30,2]' &&
      JSON.stringify(stack.map((v) => v.placement.positionMm[2])) === '[-3,1]' &&
      stack[1].scoreEdep === true && stack[0].scoreEdep === false, 'Layer stack geometry changed');
const xStack = G.layerStack({ name: 'x', axis: 'x', sizeMm: [5, 6], startMm: 0,
  layers: [{ thicknessMm: 1 }, { thicknessMm: 1 }], gapMm: 0.5 });
check(JSON.stringify(xStack[0].shape.sizeMm) === '[1,5,6]' &&
      xStack[1].placement.positionMm[0] === 2, 'Axis/gap handling changed');

const shells = G.concentricShells({ name: 'pipe', lengthMm: 40, innerRadiusMm: 1,
  layers: [{ material: 'G4_WATER', thicknessMm: 0.5 }, { material: 'G4_Al', thicknessMm: 0.25 }] });
check(shells[0].shape.innerRadiusMm === 1 && shells[0].shape.outerRadiusMm === 1.5 &&
      shells[1].shape.innerRadiusMm === 1.5 && shells[1].shape.outerRadiusMm === 1.75,
      'Shell radii changed');
check(G.audit(shells, { worldSizeMm: 100 }).ok, 'Coaxial disjoint shells must not overlap');

throws(() => G.volume({ name: 'bad', shape: { type: 'cone' } }), 'box, tube or sphere');
throws(() => G.volume({ name: 'bad', shape: { type: 'tube', innerRadiusMm: 2, outerRadiusMm: 1, lengthMm: 1 } }),
       'innerRadiusMm < outerRadiusMm');

const clean = G.audit(cells.concat(stack.map((v) => Object.assign({}, v, {
  placement: Object.assign({}, v.placement, { positionMm: [0, 0, -20 + v.placement.positionMm[2]] }) }))),
  { worldSizeMm: 100 });
check(clean.ok && clean.overlaps.length === 0, 'Separated assembly flagged: ' + JSON.stringify(clean));

const collide = G.audit(cells.concat(stack), { worldSizeMm: 100 });
check(!collide.ok && collide.overlaps.some((o) => o.kind === 'overlap'), 'Overlap missed');
const outside = G.audit([G.volume({ name: 'big', shape: { type: 'box', sizeMm: 80 }, positionMm: [30, 0, 0] })],
                        { worldSizeMm: 100 });
check(!outside.ok && outside.outside[0].name === 'big', 'World containment missed');
const nested = G.audit([
  G.volume({ name: 'Tank', shape: { type: 'box', sizeMm: 10 } }),
  G.volume({ name: 'probe', parent: 'tank', shape: { type: 'sphere', outerRadiusMm: 6 } })]);
check(!nested.ok && nested.outside[0].parent === 'tank', 'Case-insensitive parent containment missed');
const rotated = G.audit([
  G.volume({ name: 'r1', shape: { type: 'box', sizeMm: 2 }, rotationDeg: [0, 0, 45] }),
  G.volume({ name: 'r2', shape: { type: 'box', sizeMm: 2 }, positionMm: [2.3, 0, 0] })]);
check(rotated.ok && rotated.overlaps.length === 1 && rotated.overlaps[0].kind === 'possible',
      'Rotated pair must be possible, not hard: ' + JSON.stringify(rotated));
check(G.audit([G.volume({ name: 'r1', shape: { type: 'box', sizeMm: 2 }, rotationDeg: [0, 0, 45] }),
  G.volume({ name: 'r2', shape: { type: 'box', sizeMm: 2 }, positionMm: [2.5, 0, 0] })]).overlaps.length === 0,
      'Rotated AABB (sqrt 2 half extent) must clear a box 2.5 mm away');
const slab = G.audit([G.volume({ name: 's1', shape: { type: 'box', sizeMm: [10, 1, 1] }, rotationDeg: [0, 0, 90] }),
  G.volume({ name: 's2', shape: { type: 'box', sizeMm: 1 }, positionMm: [0, 4, 0] })]);
check(!slab.ok && slab.overlaps[0].kind === 'overlap', 'Quarter turn must swap extents exactly');
const spun = G.audit(ring.concat([G.volume({ name: 'core', shape: { type: 'box', sizeMm: 80 } })]),
                     { worldSizeMm: 200 });
check(spun.ok && spun.overlaps.length === 0, 'Own-axis tube spins must audit exactly: ' + JSON.stringify(spun));
const naming = G.audit([G.volume({ name: 'a', shape: { type: 'sphere', outerRadiusMm: 1 } }),
  G.volume({ name: 'A', shape: { type: 'sphere', outerRadiusMm: 1 }, positionMm: [5, 0, 0] }),
  G.volume({ name: 'b', parent: 'nowhere', shape: { type: 'sphere', outerRadiusMm: 1 } })]);
check(!naming.ok && naming.duplicates[0] === 'A' && naming.unknownParents[0].parent === 'nowhere',
      'Duplicate/unknown parent missed');
throws(() => G.assertClean(cells.concat(stack), { worldSizeMm: 100 }), 'overlaps');

globalThis.TRECH_CONFIG = {
  detector: { worldSizeMm: 100, worldMaterial: 'G4_AIR' },
  geometry: { volumes: cells.concat(ring.map((v) => Object.assign({}, v, {
    placement: Object.assign({}, v.placement, { positionMm: [v.placement.positionMm[0] * 0.8,
      v.placement.positionMm[1] * 0.8, 30] }) })), shells) }
};
)JS";
    }
    trech::JsRuntime runtime;
    const auto json = runtime.evalExperimentAndGetConfigJson(path.string());
    const auto cfg = trech::configFromJsonString(json);
    failures += expect(cfg.geometry.volumes.size() == 12, "Expected 12 parsed volumes.");
    if (cfg.geometry.volumes.size() == 12) {
      const auto& cell = cfg.geometry.volumes[0];
      failures += expect(cell.shape.type == "box" && cell.shape.sizeXmm == 8.0 &&
                             cell.placement.positionMm.x == -10.0 && cell.scoreEdep,
                         "Grid cell did not round-trip through the C++ parser.");
      const auto& pmt = cfg.geometry.volumes[7];
      failures += expect(pmt.shape.type == "tube" && pmt.shape.outerRadiusMm == 5.0 &&
                             pmt.shape.lengthMm == 10.0 && pmt.placement.rotationDeg.z == -90.0,
                         "Ring tube did not round-trip through the C++ parser.");
      const auto& shell = cfg.geometry.volumes[11];
      failures += expect(shell.shape.innerRadiusMm == 1.5 && shell.shape.outerRadiusMm == 1.75 &&
                             shell.material == "G4_Al",
                         "Concentric shell did not round-trip through the C++ parser.");
    }
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  if (failures == 0) {
    std::cout << "procedural geometry generators, config round-trip and audit pass\n";
  }
  return failures == 0 ? 0 : 1;
}
