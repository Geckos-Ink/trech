// Procedural geometry generators for TRECH scenarios.
//
// Pure JS -> JSON authoring: every generator returns plain `geometry.volumes`
// entries in the exact nested form DetectorConstruction reads
// ({ name, material, shape: { type, ... }, placement: { parent, positionMm,
// rotationDeg }, scoreEdep, tags }). Nothing here touches Geant4 or decides
// physics; the engine still resolves materials, parents and substitutions (and
// records them in provenance `geometry_resolution`).
//
// `audit()` is a read-only pre-flight check. Geant4 places overlapping
// siblings without complaint and DetectorConstruction does not run overlap
// checks, so a generated assembly that collides is otherwise silent. The audit
// is conservative: unrotated (or quarter-turned) boxes/tubes/spheres use exact
// axis-aligned extents and report a hard `overlap`; other rotations use the
// rotated solid's axis-aligned bounding box, which can over-cover it, so such a
// pair is reported as `possible` without necessarily intersecting.
(function () {
  "use strict";

  if (globalThis.TRECH_GEOMETRY) {
    return;
  }

  const ROUND = 1e12;

  function finite(value, label) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      throw new Error(label + " must be a finite number");
    }
    return number;
  }

  function positive(value, label) {
    const number = finite(value, label);
    if (!(number > 0)) {
      throw new Error(label + " must be > 0");
    }
    return number;
  }

  function count(value, label) {
    const number = finite(value, label);
    if (!Number.isInteger(number) || number < 1) {
      throw new Error(label + " must be an integer >= 1");
    }
    return number;
  }

  // Trim binary noise (0.1 * 3 = 0.30000000000000004) so generated JSON and
  // config hashes stay readable and stable across equivalent authoring.
  function clean(value) {
    const rounded = Math.round(value * ROUND) / ROUND;
    return Object.is(rounded, -0) ? 0 : rounded;
  }

  function vec3(value, fallback, label) {
    if (value === undefined || value === null) {
      return fallback.slice();
    }
    if (typeof value === "number") {
      return [value, value, value].map((v) => finite(v, label));
    }
    if (!Array.isArray(value) || value.length < 3) {
      throw new Error(label + " must be a number or [x, y, z]");
    }
    return [finite(value[0], label), finite(value[1], label), finite(value[2], label)];
  }

  function tagsOf(value) {
    if (value === undefined || value === null) return [];
    return (Array.isArray(value) ? value : [value]).map(String);
  }

  function normalizeShape(shape, label) {
    if (!shape || typeof shape !== "object") {
      throw new Error(label + " requires a shape");
    }
    const type = String(shape.type || "").toLowerCase();
    if (type === "box" || type === "cube") {
      return { type: "box", sizeMm: vec3(shape.sizeMm, [0, 0, 0], label + ".sizeMm")
        .map((v) => positive(v, label + ".sizeMm")) };
    }
    if (type === "tube" || type === "cylinder" || type === "cyl") {
      const inner = shape.innerRadiusMm === undefined ? 0 : finite(shape.innerRadiusMm,
                                                                   label + ".innerRadiusMm");
      const outer = positive(shape.outerRadiusMm, label + ".outerRadiusMm");
      if (inner < 0 || inner >= outer) {
        throw new Error(label + " needs 0 <= innerRadiusMm < outerRadiusMm");
      }
      return { type: "tube", innerRadiusMm: inner, outerRadiusMm: outer,
               lengthMm: positive(shape.lengthMm, label + ".lengthMm") };
    }
    if (type === "sphere") {
      return { type: "sphere", outerRadiusMm: positive(shape.outerRadiusMm,
                                                        label + ".outerRadiusMm") };
    }
    throw new Error(label + " shape.type must be box, tube or sphere (got '" +
                    shape.type + "')");
  }

  function volume(options) {
    if (!options || !options.name) {
      throw new Error("volume requires name");
    }
    const label = "volume '" + options.name + "'";
    return {
      name: String(options.name),
      material: options.material || "",
      shape: normalizeShape(options.shape, label),
      placement: {
        parent: options.parent || "world",
        positionMm: vec3(options.positionMm, [0, 0, 0], label + ".positionMm").map(clean),
        rotationDeg: vec3(options.rotationDeg, [0, 0, 0], label + ".rotationDeg").map(clean)
      },
      scoreEdep: !!options.scoreEdep,
      tags: tagsOf(options.tags)
    };
  }

  function sphereVolume(options) {
    return volume(Object.assign({}, options, {
      shape: { type: "sphere", outerRadiusMm: options && options.outerRadiusMm }
    }));
  }

  function axisIndex(axis, label) {
    const index = { x: 0, y: 1, z: 2 }[String(axis || "z").toLowerCase()];
    if (index === undefined) {
      throw new Error(label + " axis must be x, y or z");
    }
    return index;
  }

  // Rectangular lattice of identical cells centred on `centerMm`.
  // Names are `${name}_${i}_${j}_${k}` (zero-based; k, the z index, varies fastest).
  function grid(options) {
    if (!options || !options.name) throw new Error("grid requires name");
    const label = "grid '" + options.name + "'";
    const counts = vec3(options.count, [1, 1, 1], label + ".count")
      .map((v) => count(v, label + ".count"));
    const pitch = vec3(options.pitchMm, [0, 0, 0], label + ".pitchMm");
    const center = vec3(options.centerMm, [0, 0, 0], label + ".centerMm");
    for (let a = 0; a < 3; a += 1) {
      if (counts[a] > 1 && !(pitch[a] > 0)) {
        throw new Error(label + ".pitchMm must be > 0 along every axis with count > 1");
      }
    }
    const out = [];
    for (let i = 0; i < counts[0]; i += 1) {
      for (let j = 0; j < counts[1]; j += 1) {
        for (let k = 0; k < counts[2]; k += 1) {
          const index = [i, j, k];
          const position = index.map((n, a) =>
            center[a] + (n - 0.5 * (counts[a] - 1)) * pitch[a]);
          out.push(volume({
            name: options.name + "_" + i + "_" + j + "_" + k,
            material: options.material,
            shape: options.shape,
            parent: options.parent,
            positionMm: position,
            rotationDeg: options.rotationDeg,
            scoreEdep: options.scoreEdep,
            tags: ["grid:" + options.name].concat(tagsOf(options.tags))
          }));
        }
      }
    }
    return out;
  }

  // `count` copies evenly spaced on a circle of `radiusMm` in the plane normal
  // to `axis`, starting at `phaseDeg` from the first in-plane axis.
  // `orient: true` rotates each copy about `axis` by its angle (Geant4 frame
  // rotation, so the copy's local +first-axis points radially outward).
  function ring(options) {
    if (!options || !options.name) throw new Error("ring requires name");
    const label = "ring '" + options.name + "'";
    const n = count(options.count, label + ".count");
    const radius = positive(options.radiusMm, label + ".radiusMm");
    const a = axisIndex(options.axis, label);
    const u = (a + 1) % 3;
    const v = (a + 2) % 3;
    const center = vec3(options.centerMm, [0, 0, 0], label + ".centerMm");
    const phase = options.phaseDeg === undefined ? 0 : finite(options.phaseDeg, label + ".phaseDeg");
    const base = vec3(options.rotationDeg, [0, 0, 0], label + ".rotationDeg");
    const out = [];
    for (let i = 0; i < n; i += 1) {
      const angleDeg = phase + (360 * i) / n;
      const angle = (angleDeg * Math.PI) / 180;
      const position = center.slice();
      position[u] += radius * Math.cos(angle);
      position[v] += radius * Math.sin(angle);
      const rotation = base.slice();
      if (options.orient) {
        // G4PVPlacement takes the frame rotation (inverse of the active one).
        rotation[a] = base[a] - angleDeg;
      }
      out.push(volume({
        name: options.name + "_" + i,
        material: options.material,
        shape: options.shape,
        parent: options.parent,
        positionMm: position,
        rotationDeg: rotation,
        scoreEdep: options.scoreEdep,
        tags: ["ring:" + options.name].concat(tagsOf(options.tags))
      }));
    }
    return out;
  }

  // Planar multilayer: boxes of `sizeMm` = [w, h] transverse to `axis`, each
  // `layers[i].thicknessMm` thick, stacked from `startMm` along `axis`
  // (centred on `centerMm` when `startMm` is omitted). Optional `gapMm`.
  function layerStack(options) {
    if (!options || !options.name) throw new Error("layerStack requires name");
    const label = "layerStack '" + options.name + "'";
    const layers = Array.isArray(options.layers) ? options.layers : [];
    if (layers.length === 0) throw new Error(label + " requires layers");
    const a = axisIndex(options.axis, label);
    const transverse = Array.isArray(options.sizeMm) && options.sizeMm.length >= 2
      ? [positive(options.sizeMm[0], label + ".sizeMm"), positive(options.sizeMm[1], label + ".sizeMm")]
      : null;
    if (!transverse) throw new Error(label + ".sizeMm must be [width, height]");
    const gap = options.gapMm === undefined ? 0 : finite(options.gapMm, label + ".gapMm");
    if (gap < 0) throw new Error(label + ".gapMm must be >= 0");
    const thickness = layers.map((layer, i) => positive(layer && layer.thicknessMm,
                                                         label + ".layers[" + i + "].thicknessMm"));
    const total = thickness.reduce((s, t) => s + t, 0) + gap * (layers.length - 1);
    const center = vec3(options.centerMm, [0, 0, 0], label + ".centerMm");
    let cursor = options.startMm === undefined ? center[a] - 0.5 * total
                                               : finite(options.startMm, label + ".startMm");
    const out = [];
    layers.forEach((layer, i) => {
      const size = [0, 0, 0];
      size[a] = thickness[i];
      size[(a + 1) % 3] = transverse[0];
      size[(a + 2) % 3] = transverse[1];
      const position = center.slice();
      position[a] = cursor + 0.5 * thickness[i];
      cursor += thickness[i] + gap;
      out.push(volume({
        name: layer.name || options.name + "_" + i,
        material: layer.material || options.material,
        shape: { type: "box", sizeMm: size },
        parent: options.parent,
        positionMm: position,
        scoreEdep: layer.scoreEdep === undefined ? options.scoreEdep : layer.scoreEdep,
        tags: ["layerStack:" + options.name].concat(tagsOf(options.tags), tagsOf(layer.tags))
      }));
    });
    return out;
  }

  // Concentric cylindrical shells (sibling annular tubes) from `innerRadiusMm`
  // outward, all `lengthMm` long and coaxial along local z of `parent`.
  function concentricShells(options) {
    if (!options || !options.name) throw new Error("concentricShells requires name");
    const label = "concentricShells '" + options.name + "'";
    const layers = Array.isArray(options.layers) ? options.layers : [];
    if (layers.length === 0) throw new Error(label + " requires layers");
    let radius = options.innerRadiusMm === undefined ? 0
      : finite(options.innerRadiusMm, label + ".innerRadiusMm");
    if (radius < 0) throw new Error(label + ".innerRadiusMm must be >= 0");
    const length = positive(options.lengthMm, label + ".lengthMm");
    return layers.map((layer, i) => {
      const t = positive(layer && layer.thicknessMm, label + ".layers[" + i + "].thicknessMm");
      const inner = radius;
      radius += t;
      return volume({
        name: layer.name || options.name + "_" + i,
        material: layer.material || options.material,
        shape: { type: "tube", innerRadiusMm: clean(inner), outerRadiusMm: clean(radius),
                 lengthMm: length },
        parent: options.parent,
        positionMm: options.centerMm,
        rotationDeg: options.rotationDeg,
        scoreEdep: layer.scoreEdep === undefined ? options.scoreEdep : layer.scoreEdep,
        tags: ["concentricShells:" + options.name].concat(tagsOf(options.tags), tagsOf(layer.tags))
      });
    });
  }

  // ---- audit -------------------------------------------------------------

  function halfExtents(shape) {
    if (shape.type === "box" || shape.type === "cube") {
      return shape.sizeMm.map((v) => 0.5 * v);
    }
    if (shape.type === "tube" || shape.type === "cylinder" || shape.type === "cyl") {
      return [shape.outerRadiusMm, shape.outerRadiusMm, 0.5 * shape.lengthMm];
    }
    if (shape.type === "sphere") {
      return [shape.outerRadiusMm, shape.outerRadiusMm, shape.outerRadiusMm];
    }
    return null;
  }

  function rotationOf(v) {
    const r = (v.placement && v.placement.rotationDeg) || [0, 0, 0];
    return [Number(r[0]) || 0, Number(r[1]) || 0, Number(r[2]) || 0];
  }

  function isRotated(v) {
    return rotationOf(v).some((x) => Math.abs(x % 360) > 1e-12);
  }

  function isTubeOrSphere(shape) {
    return shape.type === "sphere" || shape.type === "tube" || shape.type === "cylinder" ||
      shape.type === "cyl";
  }

  // Spinning a sphere, or a tube about its own (local z) axis, leaves its
  // extent unchanged, so the exact unrotated test still applies.
  function effectivelyUnrotated(v) {
    if (!isRotated(v)) return true;
    if (v.shape.type === "sphere") return true;
    const r = rotationOf(v);
    return isTubeOrSphere(v.shape) && Math.abs(r[0] % 360) < 1e-12 &&
      Math.abs(r[1] % 360) < 1e-12;
  }

  // Quarter-turn rotations permute axes, so the rotated AABB is exact.
  function quarterTurns(v) {
    return rotationOf(v).every((x) => Math.abs(x / 90 - Math.round(x / 90)) < 1e-12);
  }

  // Axis-aligned half extents of a placed volume. DetectorConstruction builds
  // the frame rotation R = Rz * Ry * Rx (G4RotationMatrix rotateX, rotateY,
  // rotateZ) and the solid is turned by R^T, so half_i = sum_j |R_ji| h_j.
  function placedHalfExtents(v) {
    const h = halfExtents(v.shape);
    if (!h || effectivelyUnrotated(v)) return h;
    const [ax, ay, az] = rotationOf(v).map((d) => (d * Math.PI) / 180);
    const cx = Math.cos(ax), sx = Math.sin(ax);
    const cy = Math.cos(ay), sy = Math.sin(ay);
    const cz = Math.cos(az), sz = Math.sin(az);
    const Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]];
    const Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]];
    const Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]];
    const mul = (A, B) => A.map((row, i) => B[0].map((_, j) =>
      row[0] * B[0][j] + row[1] * B[1][j] + row[2] * B[2][j]));
    const R = mul(Rz, mul(Ry, Rx));
    return [0, 1, 2].map((i) =>
      Math.abs(R[0][i]) * h[0] + Math.abs(R[1][i]) * h[1] + Math.abs(R[2][i]) * h[2]);
  }

  // "overlap" when the extents are exact (unrotated, own-axis spins or quarter
  // turns), "possible" when a rotated AABB over-covers the true solid.
  function extentsExact(v) {
    return effectivelyUnrotated(v) || quarterTurns(v);
  }

  // Coaxial unrotated tubes whose radial ranges do not intersect never
  // overlap, whatever their AABBs say (concentric shells, nested sleeves).
  function radiallyDisjointTubes(a, b) {
    const tube = (s) => s.type === "tube" || s.type === "cylinder" || s.type === "cyl";
    if (!tube(a.shape) || !tube(b.shape)) return false;
    const pa = a.placement.positionMm;
    const pb = b.placement.positionMm;
    if (Math.abs(pa[0] - pb[0]) > 1e-9 || Math.abs(pa[1] - pb[1]) > 1e-9) return false;
    const ia = a.shape.innerRadiusMm || 0;
    const ib = b.shape.innerRadiusMm || 0;
    return a.shape.outerRadiusMm <= ib + 1e-9 || b.shape.outerRadiusMm <= ia + 1e-9;
  }

  // Read-only pre-flight check of a volumes list (and optional world/medium
  // size, full edge lengths in mm as in detector.worldSizeMm/mediumBoxMm).
  // Returns { ok, duplicates, unknownParents, overlaps, outside }.
  //   overlaps[]: { a, b, parent, kind: "overlap" | "possible" }
  //   outside[]:  { name, parent, kind: "outside" | "possible" }
  // Parent names are matched case-insensitively like DetectorConstruction.
  function audit(volumes, options) {
    const opts = options || {};
    const list = Array.isArray(volumes) ? volumes : [];
    const seen = new Map();
    const duplicates = [];
    list.forEach((v) => {
      const key = String(v.name || "").toLowerCase();
      if (seen.has(key)) duplicates.push(v.name);
      else seen.set(key, v);
    });
    const parentKey = (v) => {
      const p = String((v.placement && v.placement.parent) || "").toLowerCase();
      if (p === "") return opts.mediumBoxMm > 0 ? "medium" : "world";
      if (p === "mediumbox" || p === "medium_box") return "medium";
      return p;
    };
    const unknownParents = [];
    const groups = new Map();
    list.forEach((v) => {
      const p = parentKey(v);
      if (p !== "world" && p !== "medium" && !seen.has(p)) {
        unknownParents.push({ name: v.name, parent: v.placement.parent });
      }
      if (!groups.has(p)) groups.set(p, []);
      groups.get(p).push(v);
    });

    const overlaps = [];
    groups.forEach((members, parent) => {
      for (let i = 0; i < members.length; i += 1) {
        for (let j = i + 1; j < members.length; j += 1) {
          const a = members[i];
          const b = members[j];
          const ha = a.shape ? placedHalfExtents(a) : null;
          const hb = b.shape ? placedHalfExtents(b) : null;
          if (!ha || !hb) continue;
          const pa = (a.placement && a.placement.positionMm) || [0, 0, 0];
          const pb = (b.placement && b.placement.positionMm) || [0, 0, 0];
          if (effectivelyUnrotated(a) && effectivelyUnrotated(b) && radiallyDisjointTubes(a, b)) {
            continue;
          }
          let separated = false;
          for (let k = 0; k < 3; k += 1) {
            if (Math.abs(pa[k] - pb[k]) >= ha[k] + hb[k] - 1e-9) separated = true;
          }
          if (!separated) {
            overlaps.push({ a: a.name, b: b.name, parent,
                            kind: extentsExact(a) && extentsExact(b) ? "overlap" : "possible" });
          }
        }
      }
    });

    const containerHalf = (parent) => {
      if (parent === "world") {
        return opts.worldSizeMm > 0 ? [0.5 * opts.worldSizeMm, 0.5 * opts.worldSizeMm,
                                       0.5 * opts.worldSizeMm] : null;
      }
      if (parent === "medium") {
        if (!(opts.mediumBoxMm > 0)) return null;
        const m = 0.5 * Math.min(opts.mediumBoxMm, opts.worldSizeMm > 0 ? opts.worldSizeMm
                                                                         : opts.mediumBoxMm);
        return [m, m, m];
      }
      const p = seen.get(parent);
      if (!p || !p.shape || p.shape.type !== "box" || !effectivelyUnrotated(p)) return null;
      return halfExtents(p.shape);
    };
    const outside = [];
    list.forEach((v) => {
      const parent = parentKey(v);
      const limit = containerHalf(parent);
      const reach = v.shape ? placedHalfExtents(v) : null;
      if (!limit || !reach) return;
      const pos = (v.placement && v.placement.positionMm) || [0, 0, 0];
      let out = false;
      for (let k = 0; k < 3; k += 1) {
        if (Math.abs(pos[k]) + reach[k] > limit[k] + 1e-9) out = true;
      }
      if (out) outside.push({ name: v.name, parent, kind: extentsExact(v) ? "outside" : "possible" });
    });

    const hard = overlaps.some((o) => o.kind === "overlap") ||
      outside.some((o) => o.kind === "outside");
    return {
      ok: duplicates.length === 0 && unknownParents.length === 0 && !hard,
      duplicates,
      unknownParents,
      overlaps,
      outside
    };
  }

  // Throw with a readable summary when audit() finds a hard problem.
  function assertClean(volumes, options) {
    const report = audit(volumes, options);
    if (report.ok) return report;
    const lines = [];
    report.duplicates.forEach((n) => lines.push("duplicate name " + n));
    report.unknownParents.forEach((u) => lines.push(u.name + " has unknown parent " + u.parent));
    report.overlaps.filter((o) => o.kind === "overlap")
      .forEach((o) => lines.push(o.a + " overlaps " + o.b + " in " + o.parent));
    report.outside.filter((o) => o.kind === "outside")
      .forEach((o) => lines.push(o.name + " extends outside " + o.parent));
    throw new Error("TRECH_GEOMETRY audit: " + lines.join("; "));
  }

  globalThis.TRECH_GEOMETRY = Object.freeze({
    volume,
    sphereVolume,
    grid,
    ring,
    layerStack,
    concentricShells,
    audit,
    assertClean
  });
})();
