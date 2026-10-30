// Common scenario entry point. TRECH_INCLUDE resolves dependencies relative to
// this file, so callers can import it from any experiment directory.
if (!globalThis.TRECH_MATH) TRECH_INCLUDE("trech_math.js");
if (!globalThis.TRECH_RANDOM) TRECH_INCLUDE("trech_random.js");
if (!globalThis.TRECH_MATERIAL_FACTS) TRECH_INCLUDE("trech_material_facts.js");
globalThis.TRECH_HELPERS = (function() {
  function toArray(value) {
    if (value === undefined || value === null) {
      return [];
    }
    return Array.isArray(value) ? value : [value];
  }

  const units = {
    eV: (value) => value * 1e-6,
    keV: (value) => value * 1e-3,
    MeV: (value) => value,
    GeV: (value) => value * 1e3,
    mm: (value) => value,
    cm: (value) => value * 10.0,
    m: (value) => value * 1000.0,
    nm: (value) => value * 1e-6
  };

  const constants = {
    avogadro: 6.02214076e23,
    boltzmannEvK: 8.617333262e-5,
    carbonWallThicknessNm: 0.34,
    carbonBondLengthNm: 0.142     // graphene/CNT C-C bond length a_cc
  };

  function clamp01(value) {
    if (value < 0.0) {
      return 0.0;
    }
    if (value > 1.0) {
      return 1.0;
    }
    return value;
  }

  function cloneMaterialPreset(preset, overrides) {
    const base = Object.assign({}, preset);
    if (preset.components) {
      base.components = preset.components.map((component) => Object.assign({}, component));
    }
    return Object.assign(base, overrides || {});
  }

  const materialPresets = {
    water: {
      name: "water",
      smiles: "O",
      densityGcm3: 1.0,
      components: [{ material: "G4_WATER", fraction: 1.0 }]
    },
    air: {
      name: "air",
      smiles: "[N]#[N].[O]=[O]",
      densityGcm3: 0.001225,
      components: [{ material: "G4_AIR", fraction: 1.0 }]
    },
    glass: {
      name: "glass",
      smiles: "O=[Si]=O",
      densityGcm3: 2.5,
      components: [{ material: "G4_SILICON_DIOXIDE", fraction: 1.0 }]
    },
    carbon: {
      name: "carbon",
      smiles: "C",
      densityGcm3: 2.2,
      components: [{ material: "G4_C", fraction: 1.0 }]
    },
    vacuum: {
      name: "vacuum",
      smiles: "",
      densityGcm3: 1e-25,
      components: [{ material: "G4_Galactic", fraction: 1.0 }]
    },
    brine: (salinityFraction) => {
      const salt = clamp01(typeof salinityFraction === "number" ? salinityFraction : 0.02);
      const water = clamp01(1.0 - salt);
      // Geant4 has no G4_SODIUM_CHLORIDE compound, so the dissolved salt is
      // expressed as its elements by mass: NaCl is 39.34% Na / 60.66% Cl
      // (22.99 / 35.45 of the 58.44 g/mol molar mass).
      const naMassFraction = 0.3934;
      const clMassFraction = 0.6066;
      return {
        name: "brine",
        smiles: "O.[Na+].[Cl-]",
        densityGcm3: 1.02,
        components: [
          { material: "G4_WATER", fraction: water },
          { element: "Na", fraction: salt * naMassFraction },
          { element: "Cl", fraction: salt * clMassFraction }
        ]
      };
    }
  };

  const materialAliases = {
    air: "G4_AIR",
    water: "G4_WATER",
    glass: "G4_SILICON_DIOXIDE",
    carbon: "G4_C",
    vacuum: "G4_Galactic"
  };

  const materialRegistry = {
    presets: materialPresets,
    fromPreset: (key, overrides) => {
      const preset = materialPresets[key];
      if (!preset) {
        throw new Error("Unknown material preset: " + key);
      }
      if (typeof preset === "function") {
        return cloneMaterialPreset(preset(), overrides);
      }
      return cloneMaterialPreset(preset, overrides);
    }
  };

  function normalizeVector(value, fallback) {
    if (Array.isArray(value) && value.length >= 3) {
      return [value[0], value[1], value[2]];
    }
    return fallback || [0, 0, 0];
  }

  function boxVolume(options) {
    if (!options || !options.name) {
      throw new Error("boxVolume requires name");
    }
    return {
      name: options.name,
      material: options.material || "",
      shape: { type: "box", sizeMm: normalizeVector(options.sizeMm, [1, 1, 1]) },
      placement: {
        parent: options.parent || "world",
        positionMm: normalizeVector(options.positionMm, [0, 0, 0]),
        rotationDeg: normalizeVector(options.rotationDeg, [0, 0, 0])
      },
      scoreEdep: !!options.scoreEdep,
      tags: toArray(options.tags)
    };
  }

  function tubeVolume(options) {
    if (!options || !options.name) {
      throw new Error("tubeVolume requires name");
    }
    return {
      name: options.name,
      material: options.material || "",
      shape: {
        type: "tube",
        innerRadiusMm: options.innerRadiusMm || 0.0,
        outerRadiusMm: options.outerRadiusMm || 0.0,
        lengthMm: options.lengthMm || 0.0
      },
      placement: {
        parent: options.parent || "world",
        positionMm: normalizeVector(options.positionMm, [0, 0, 0]),
        rotationDeg: normalizeVector(options.rotationDeg, [0, 0, 0])
      },
      scoreEdep: !!options.scoreEdep,
      tags: toArray(options.tags)
    };
  }

  function containerBox(options) {
    const volume = boxVolume(
      Object.assign({}, options, {
        material: options.material || materialAliases.vacuum,
        scoreEdep: false,
        tags: ["container"].concat(toArray(options.tags))
      })
    );
    return volume;
  }

  function composeBeams(base, variants) {
    return toArray(variants).map((variant) => {
      return Object.assign({}, base, variant);
    });
  }

  function pickBeam(beams, name) {
    const list = toArray(beams);
    if (name) {
      const match = list.find((beam) => beam && beam.name === name);
      if (match) {
        return match;
      }
    }
    const active = list.find((beam) => beam && beam.active);
    return active || list[0];
  }

  // Emission-spectrum generators. Each returns an array of
  // { wavelengthNm, weight } usable directly as a beam's `spectrum`; the engine
  // samples one line per event with probability proportional to weight. The
  // C++ side stays physics-agnostic — the shape of the source lives here.
  const spectra = {
    // Sample the visible band uniformly in wavelength and weight each line by
    // the Planck spectral radiance B(lambda, T) (relative units). c2 is the
    // second radiation constant hc/k = 1.438777e7 nm*K.
    blackbody: (temperatureK, options) => {
      const opts = options || {};
      const bins = Math.max(2, opts.bins || 24);
      const minNm = opts.minNm || 380.0;
      const maxNm = opts.maxNm || 750.0;
      const c2 = 1.438777e7; // nm*K
      const T = temperatureK > 0 ? temperatureK : 5778.0;
      const out = [];
      for (let i = 0; i < bins; i++) {
        const lambda = minNm + (maxNm - minNm) * (i + 0.5) / bins;
        const weight =
          (1.0 / Math.pow(lambda, 5)) / (Math.exp(c2 / (lambda * T)) - 1.0);
        out.push({ wavelengthNm: lambda, weight: weight });
      }
      return out;
    },
    // Equal-weight (flat) sampling across the visible band — an idealized white
    // source for showing dispersion without a temperature bias.
    whiteVisible: (options) => {
      const opts = options || {};
      const bins = Math.max(2, opts.bins || 24);
      const minNm = opts.minNm || 380.0;
      const maxNm = opts.maxNm || 750.0;
      const out = [];
      for (let i = 0; i < bins; i++) {
        const lambda = minNm + (maxNm - minNm) * (i + 0.5) / bins;
        out.push({ wavelengthNm: lambda, weight: 1.0 });
      }
      return out;
    },
    // Pass an explicit list of { wavelengthNm | energyEv, weight? } lines
    // (named line sets, lasers, etc.); fills a default weight of 1.
    lines: (list) =>
      toArray(list).map((line) => ({
        wavelengthNm: line.wavelengthNm,
        energyEv: line.energyEv,
        weight: typeof line.weight === "number" ? line.weight : 1.0
      }))
  };

  // Beam-profile presets (anti-degeneration workstream): named source-variety
  // bundles for `beam.spread`, so a scenario samples a real distribution of
  // primaries instead of N identical ones. These are descriptive starting
  // points for common bench sources, not metrological calibrations — pass
  // `overrides` to tune any field. Pair with `spectra` for the energy axis
  // (e.g. sunbeam + spectra.blackbody(5778)).
  const beamProfiles = (() => {
    const presets = {
      // perfectly degenerate point/parallel/monochrome source — the baseline
      // the degeneration metrics call out (1 exit point / 0 deg / 0 nm).
      pencil:     { spotRadiusMm: 0.0,  divergenceDeg: 0.0,  energySpreadFractional: 0.0 },
      // collimated lab laser: sub-mm waist, ~1 mrad fan, narrow line
      laser:      { spotRadiusMm: 0.4,  divergenceDeg: 0.06, energySpreadFractional: 1e-3 },
      // diffuse bench LED: mm-scale emitting disk, gentle fan, ~4% band
      ledLamp:    { spotRadiusMm: 6.0,  divergenceDeg: 1.5,  energySpreadFractional: 0.04 },
      // handheld flashlight: cm-scale aperture, wide fan, broad-ish band
      flashlight: { spotRadiusMm: 12.0, divergenceDeg: 8.0,  energySpreadFractional: 0.05 },
      // parallel daylight through an aperture: broad spot, the 0.27 deg solar
      // half-angle, monochrome here (give it a blackbody `spectrum` instead)
      sunbeam:    { spotRadiusMm: 25.0, divergenceDeg: 0.27, energySpreadFractional: 0.0 }
    };
    return {
      names: () => Object.keys(presets),
      spread: (name, overrides) => {
        const base = presets[name];
        if (!base) {
          throw new Error("unknown beam profile: " + name +
                          " (have: " + Object.keys(presets).join(", ") + ")");
        }
        return Object.assign({}, base, overrides || {});
      }
    };
  })();

  // Precision profiles: one named rung a user can move, mapped by the SCENARIO
  // onto its own axes. There is deliberately no global "quality" number — a
  // Geant4 event, an MD step, a PBF particle, a chemistry tick and a replay
  // frame are not the same knob — so a scenario declares which of its controls
  // moves, in which role, and the ladder only scales them.
  //
  //   const p = helpers.precision.resolve({
  //     profile: profileValue,                       // a TRECH_VALUE.choice
  //     axes: [
  //       { name: "parcels", role: "spatial", control: "wax_representatives",
  //         unit: "parcels", balanced: 240, min: 120, max: 480,
  //         direction: "higher_is_finer", integer: true, override: parcelsParam },
  //       { name: "physics_step", role: "temporal", control: "max_physics_step_s",
  //         unit: "s", balanced: 0.4, min: 0.1, max: 1.0,
  //         direction: "lower_is_finer" }
  //     ]
  //   });
  //   p.value("parcels")   // resolved number at the active rung
  //   p.config             // -> cfg.precision (profile + resolved axes)
  //
  // `balanced` is the reference rung, so a scenario adopting profiles with its
  // historical defaults as `balanced` keeps byte-identical config at the default
  // profile. An explicit `override` (a user-set control) wins over the ladder,
  // marks that axis `overridden`, and turns the reported profile into `custom` —
  // the run says what it actually ran, never a rung it only half-followed.
  const precision = (() => {
    // Refinement factor per rung. `higher_is_finer` axes multiply by it;
    // `lower_is_finer` axes (a step, a grid spacing) divide by it.
    const ladder = {
      preview:     0.5,
      balanced:    1.0,
      high:        2.0,
      convergence: 4.0
    };
    const roles = ["spatial", "temporal", "output", "statistical", "representation"];

    function resolve(spec) {
      const requested = String((spec && spec.profile) || "balanced").toLowerCase();
      if (!Object.prototype.hasOwnProperty.call(ladder, requested)) {
        throw new Error("unknown precision profile: " + requested +
                        " (have: " + Object.keys(ladder).join(", ") + ")");
      }
      const explicitFactor = spec && spec.factor !== undefined ? spec.factor :
        (typeof TRECH_REFINEMENT === "number" ? TRECH_REFINEMENT : undefined);
      const factor = explicitFactor === undefined ? ladder[requested] : Number(explicitFactor);
      if (!isFinite(factor) || factor <= 0) {
        throw new Error("precision factor must be finite and positive");
      }
      if (typeof TRECH_REFINEMENT === "number") globalThis.__TRECH_REFINEMENT_USED = true;
      const axes = [];
      const byName = {};
      let anyOverridden = false;
      for (const declared of (spec && spec.axes) || []) {
        if (!declared || !declared.name) {
          throw new Error("precision axis needs a name");
        }
        if (roles.indexOf(declared.role) < 0) {
          throw new Error("precision axis " + declared.name + " needs a role of " +
                          roles.join("|"));
        }
        const baseline = Number(declared.balanced);
        if (!isFinite(baseline) || baseline <= 0.0) {
          throw new Error("precision axis " + declared.name +
                          " needs a positive `balanced` reference value");
        }
        const lowerIsFiner = declared.direction === "lower_is_finer";
        let value = lowerIsFiner ? baseline / factor : baseline * factor;
        const overridden = declared.override !== undefined &&
                           declared.override !== null &&
                           Number(declared.override) !== 0 &&
                           isFinite(Number(declared.override));
        if (overridden) {
          value = Number(declared.override);
        }
        if (declared.min !== undefined && value < declared.min) {
          value = declared.min;
        }
        if (declared.max !== undefined && value > declared.max) {
          value = declared.max;
        }
        if (declared.integer) {
          value = Math.round(value);
        }
        anyOverridden = anyOverridden || overridden;
        const axis = {
          name: declared.name,
          role: declared.role,
          control: declared.control || "",
          unit: declared.unit || "",
          value,
          baselineValue: baseline,
          representationOnly: declared.role === "representation",
          overridden
        };
        axes.push(axis);
        byName[axis.name] = axis;
      }
      // A rung only half-followed is not that rung.
      const profile = anyOverridden || factor !== ladder[requested] ? "custom" : requested;
      return {
        profile,
        requested,
        factor,
        axes,
        value(name) {
          if (!Object.prototype.hasOwnProperty.call(byName, name)) {
            throw new Error("undeclared precision axis: " + name);
          }
          return byName[name].value;
        },
        axis(name) { return byName[name]; },
        config: {
          profile,
          note: ((spec && spec.note) || "") +
            (explicitFactor === undefined ? "" : " · continuous refinement " + factor),
          axes
        }
      };
    }

    return {
      names: () => Object.keys(ladder),
      roles: () => roles.slice(),
      factor: (name) => ladder[String(name).toLowerCase()],
      resolve
    };
  })();

  // Observer-frame emission for the classic 3D viewer and Studio (`material_frame`, see
  // docs/output_schema.md). A scenario hands over its OWN solver state — atom/parcel positions,
  // bonds, vectors, moving apparatus — and this only packages it with the clock fields, so no
  // renderer ever has to invent motion. Colours, display radii and legend are representation.
  const observer = (function() {
    // Uniform output-frame mapping with both clocks retained. Capture the
    // apparatus, not derived constants, so authored updates remain visible.
    function linearClock(apparatus) {
      return (frameIndex) => {
        const fraction = frameIndex / apparatus.outputTicks;
        return {
          physicalTimeS: fraction * apparatus.durationS,
          playbackTimeS: fraction * apparatus.playbackDurationS,
          timeScale: apparatus.durationS / apparatus.playbackDurationS
        };
      };
    }
    // CPK-style display colours + ball-and-stick radii (Å). Representation only.
    const elementRgba = {
      H: [0.93, 0.93, 0.96, 1.0], O: [0.94, 0.2, 0.18, 1.0], C: [0.36, 0.37, 0.4, 1.0],
      N: [0.28, 0.45, 1.0, 1.0], Na: [0.67, 0.36, 0.95, 1.0], Cl: [0.16, 0.9, 0.2, 1.0],
      I: [0.58, 0.0, 0.58, 1.0], K: [0.56, 0.25, 0.83, 1.0], Mn: [0.61, 0.48, 0.78, 1.0]
    };
    const elementRadiusA = { H: 0.25, O: 0.42, C: 0.4, N: 0.4, Na: 0.6, Cl: 0.6, I: 0.7, K: 0.7 };
    const round = (value, digits) => {
      const f = Math.pow(10, digits);
      return Math.round(value * f) / f;
    };
    function point(p, digits) {
      return Array.isArray(p) ? [round(p[0], digits), round(p[1], digits), round(p[2] || 0, digits)]
        : [round(p.x, digits), round(p.y, digits), round(p.z || 0, digits)];
    }
    // o: { physicalTimeS, playbackTimeS?, timeScale?, phase?, lengthUnit? ("mm"), upAxis? ("z"),
    //      positions: [[x,y,z]|{x,y,z}], colors: [[r,g,b,a]], radii?, bonds?, vectors?,
    //      apparatus?, legend?, hud?, counts?, motionScope, digits?,
    //      samples?, charts?, curves?, labels?, grid? }
    // samples: {name: number} observables of this frame; charts: side-panel declarations
    // (usually on the first frame only); curves: per-frame curve snapshots for a chart; labels:
    // [{position, text, color_rgba}] 3D text; grid: a solver cell grid with class ids.
    function frame(o) {
      const unit = o.lengthUnit || "mm";
      const digits = o.digits === undefined ? 4 : o.digits;
      const payload = {
        time_s: o.physicalTimeS,
        physical_time_s: o.physicalTimeS,
        playback_time_s: o.playbackTimeS === undefined ? o.physicalTimeS : o.playbackTimeS,
        time_scale: o.timeScale === undefined ? 1.0 : o.timeScale,
        phase: o.phase || "",
        length_unit: unit,
        up_axis: o.upAxis || "z",
        colors_rgba: o.colors,
        motion_scope: o.motionScope || "scenario solver state, replayed verbatim"
      };
      payload[unit === "mm" ? "positions_mm" : "positions"] =
        o.positions.map((p) => point(p, digits));
      if (o.radii) payload.radii = o.radii.map((r) => round(r, 4));
      if (o.bonds && o.bonds.length) payload.bonds = o.bonds;
      if (o.vectors) payload.vectors = o.vectors.map((p) => point(p, digits));
      if (o.apparatus && o.apparatus.length) payload.apparatus = o.apparatus;
      if (o.legend && o.legend.length) payload.legend = o.legend;
      if (o.hud && o.hud.length) payload.hud_lines = o.hud;
      if (o.counts) payload.counts = o.counts;
      if (o.clockText) payload.clock_text = o.clockText;
      if (o.renderSurface) payload.render_surface = o.renderSurface;
      if (o.samples) payload.samples = o.samples;
      if (o.charts && o.charts.length) payload.charts = o.charts;
      if (o.curves && o.curves.length) payload.curves = o.curves;
      if (o.labels && o.labels.length) {
        payload.labels = o.labels.map((l) => ({ position: point(l.position, digits), text: l.text,
                                                color_rgba: l.color_rgba || [1, 1, 1, 1] }));
      }
      if (o.grid) payload.grid = o.grid;
      payload.representation_override = {
        colors: "display palette (representation only)",
        radii: o.radii ? "display radii (representation only)" : undefined,
        positions_unmodified: true
      };
      return payload;
    }
    // Atoms of molecules as CPK spheres + intramolecular bonds. `molecules` is a list of
    // {atoms: [{el, pos}], bonds: [[i, j]]} with local atom indices.
    function atoms(molecules, options) {
      const opts = options || {};
      const positions = [], colors = [], radii = [], bonds = [];
      for (const molecule of molecules) {
        const base = positions.length;
        for (const atom of molecule.atoms) {
          positions.push(atom.pos);
          colors.push(atom.rgba || elementRgba[atom.el] || [0.8, 0.8, 0.8, 1.0]);
          radii.push((elementRadiusA[atom.el] || 0.4) * (opts.radiusScale || 1.0));
        }
        for (const bond of molecule.bonds || []) bonds.push([base + bond[0], base + bond[1]]);
      }
      return { positions, colors, radii, bonds };
    }
    function legend(entries) {
      return entries.map(([label, rgba]) => ({ label, color_rgba: rgba.slice(0, 3) }));
    }
    return { elementRgba, elementRadiusA, frame, atoms, legend, round, linearClock };
  })();

  // Carbon-nanotube geometry from its chirality: the (n,m) graphene sheet rolled along the
  // chiral vector C = n a1 + m a2 (pure geometry — the atoms the band-structure model reasons
  // about; no electronic law here). Positions in nm, tube axis along +z from 0 to lengthNm.
  const cnt = (function() {
    const gcd = (a, b) => (b === 0 ? Math.abs(a) : gcd(b, a % b));
    function roll(n, m, lengthNm, options) {
      const opts = options || {};
      const acc = constants.carbonBondLengthNm;
      const a = Math.sqrt(3) * acc;
      const a1 = [a, 0], a2 = [a / 2, a * Math.sqrt(3) / 2];
      const C = [n * a1[0] + m * a2[0], n * a1[1] + m * a2[1]];
      const cLen = Math.hypot(C[0], C[1]);
      const radius = cLen / (2 * Math.PI);
      const dR = gcd(2 * m + n, 2 * n + m);
      const T = [((2 * m + n) / dR) * a1[0] - ((2 * n + m) / dR) * a2[0],
                 ((2 * m + n) / dR) * a1[1] - ((2 * n + m) / dR) * a2[1]];
      const tLen = Math.hypot(T[0], T[1]);
      const cHat = [C[0] / cLen, C[1] / cLen], tHat = [T[0] / tLen, T[1] / tLen];
      const basis = [[0, 0], [(a1[0] + a2[0]) / 3, (a1[1] + a2[1]) / 3]];
      const span = Math.ceil((cLen + lengthNm) / a) + 2;
      const atoms = [];
      for (let i = -span; i <= span; i += 1) {
        for (let j = -span; j <= span; j += 1) {
          for (const b of basis) {
            const px = i * a1[0] + j * a2[0] + b[0], py = i * a1[1] + j * a2[1] + b[1];
            const u = px * cHat[0] + py * cHat[1];
            const v = px * tHat[0] + py * tHat[1];
            if (u < -1e-9 || u >= cLen - 1e-9 || v < -1e-9 || v >= lengthNm - 1e-9) continue;
            const phi = 2 * Math.PI * u / cLen;
            atoms.push([radius * Math.cos(phi), radius * Math.sin(phi), v]);
          }
        }
      }
      const bonds = [];
      const cut2 = Math.pow(1.15 * acc, 2);
      for (let p = 0; p < atoms.length; p += 1) {
        for (let q = p + 1; q < atoms.length; q += 1) {
          const dx = atoms[p][0] - atoms[q][0], dy = atoms[p][1] - atoms[q][1];
          const dz = atoms[p][2] - atoms[q][2];
          if (dx * dx + dy * dy + dz * dz < cut2) bonds.push([p, q]);
        }
      }
      const place = opts.place || ((p) => p);
      return { n, m, radiusNm: radius, lengthNm, atoms: atoms.map(place), bonds };
    }
    return { roll };
  })();

  return {
    math: globalThis.TRECH_MATH,
    random: globalThis.TRECH_RANDOM,
    materialFacts: globalThis.TRECH_MATERIAL_FACTS,
    units,
    constants,
    toArray,
    composeBeams,
    pickBeam,
    spectra,
    beamProfiles,
    precision,
    observer,
    cnt,
    materialPresets,
    materialRegistry,
    materialAliases,
    geometry: {
      boxVolume,
      tubeVolume,
      containerBox
    }
  };
})();
