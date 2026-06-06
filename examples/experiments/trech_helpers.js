// Helper module for experiments; load with TRECH_INCLUDE or inline as needed.
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
    carbonWallThicknessNm: 0.34
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

  return {
    units,
    constants,
    toArray,
    composeBeams,
    pickBeam,
    spectra,
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
