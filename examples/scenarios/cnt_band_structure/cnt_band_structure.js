// Vostok milestone (CNT parallel track): carbon-nanotube ELECTRONIC STRUCTURE.
//
// The existing CNT stubs (config_cnt_stub.js et al.) set up tube-shell geometry
// and push electrons through it with Geant4. This experiment adds the piece the
// ROADMAP calls out -- "electron behaviour differences ... including Fermi gap
// modelling": whether a single-wall nanotube is METALLIC or SEMICONDUCTING, and
// its leading band gap, both of which are fixed by the (n,m) chirality alone.
//
// Honest scope (same contract as the H2O MD ladder): Geant4 transports
// electrons through the carbon geometry but does NOT compute electronic band
// structure. The metallic/semiconducting character and the band gaps here are a
// TIGHT-BINDING ZONE-FOLDING model evaluated in the deterministic hook layer
// (the "physics for comparison"), compared to two textbook, experimentally
// confirmed results:
//   1. metallicity rule: a (n,m) tube is metallic iff (n - m) is divisible by 3
//      (armchair (n,n) always metallic; zigzag (n,0) metallic iff n % 3 == 0),
//      else semiconducting. (Saito, Dresselhaus & Dresselhaus 1998.)
//   2. band-gap law: for a semiconducting tube the leading-order zone-folding
//      gap is E_g = 2 a_cc gamma0 / d, i.e. E_g is inversely proportional to the
//      diameter, with E_g * d = 2 a_cc gamma0 ~ 0.82 eV*nm -- matching the
//      measured scaling (STM, Wildoer/Odom 1998: E_g*d ~ 0.7-0.9 eV*nm).
//
// Geometry: diameter d = a_cc*sqrt(3)/pi * sqrt(n^2 + n m + m^2); chiral angle
// theta = atan2(sqrt(3) m, 2n + m) (0 deg zigzag -> 30 deg armchair).
//
// Next-order correction now folded in: curvature gives nominally-metallic
// non-armchair tubes a tiny secondary gap proportional to cos(3 theta) / d^2.
// Armchair tubes stay symmetry-protected at zero in this model.
//
// Trigonal warping (the Kataura-plot family zigzag) is NOT inserted as a
// formula: each tube's subband edges are found numerically by cutting the FULL
// nearest-neighbour graphene dispersion E(k) = gamma0 |1 + e^{ik.a1} + e^{ik.a2}|
// along the tube's quantized lines near the K point (spacing 2/d, axis
// direction perpendicular to the chiral vector). The leading-order law above is
// the linear (Dirac-cone) limit of the same model; the full cut reproduces the
// metallicity rule on its own, converges to E_g ~ 1/d, and splits the
// semiconducting tubes into the two (n-m) mod 3 families: E22/E11 lies above 2
// for family 1 and below 2 for family 2, the split shrinking with diameter.
// The family ORDERING is compared to approximate photoluminescence assignments
// (Bachilo et al. 2002); absolute optical energies carry excitonic effects that
// this single-particle model does not include, so only the ordering is graded.
//
// Emits a final `cnt_panel` with per-tube (n, m, diameter, chiral angle,
// metallic flag, primary/secondary/effective band gap) plus the validation.
// Fast (no MD); a few Geant4 electron events drive the run.
//
// Run:
//   trech run examples/scenarios/cnt_band_structure/cnt_band_structure.js \
//        --events 5 --output build/dev/out_cnt_band_structure

TRECH_INCLUDE("../../../js/trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const constants = helpers.constants;
const geometry = helpers.geometry;

// ---- tight-binding parameters ----
const A_CC = constants.carbonBondLengthNm;   // 0.142 nm
const GAMMA0 = 2.9;                           // eV, nn transfer integral (Saito)
const DIAM_PREFACTOR = A_CC * Math.sqrt(3) / Math.PI;   // d = prefactor*sqrt(...)
const GAP_SCALING_EV_NM = 2 * A_CC * GAMMA0;  // E_g * d for semiconducting tubes
// Bare curvature gap for nominally metallic tubes:
// E_g,bare ~= (50 meV nm^2 / d^2) * |cos(3 theta)|. This captures the observed
// 10-100 meV small-gap scale; armchair theta=30 deg gives cos(90)=0.
const CURVATURE_GAP_COEFF_EV_NM2 = 0.050;

// A panel spanning metallic + semiconducting tubes over a range of diameters
// (armchair / zigzag / chiral). [n, m] with n >= m >= 0.
const TUBES = [
  [5, 5], [6, 6], [7, 7], [8, 8], [10, 10],          // armchair (metallic)
  [9, 0], [12, 0], [15, 0], [18, 0],                  // zigzag, n%3==0 (metallic)
  [10, 0], [11, 0], [13, 0], [14, 0], [16, 0], [17, 0], [19, 0], [20, 0],  // zigzag semiconducting
  [6, 3], [9, 3], [12, 6],                            // chiral metallic ((n-m)%3==0)
  [7, 3], [8, 4], [10, 5], [11, 4], [12, 5], [14, 7]  // chiral semiconducting
];

// A few STM/optically measured semiconducting gaps for the comparison anchors
// (eV; ~0.1 eV experimental scatter). Keyed "n,m".
const MEASURED_GAP_EV = { "10,0": 1.05, "13,0": 0.80, "17,0": 0.62 };

// Approximate photoluminescence assignments (Bachilo et al., Science 298, 2361,
// 2002): first/second optical transition wavelengths in nm. Only the family
// ORDERING of lambda11/lambda22 (= E22/E11) is graded; excitonic shifts make the
// measured ratios sit well below the single-particle value of ~2.
const KATAURA_ANCHORS_NM = [
  { n: 6, m: 5, lambda11_nm: 976, lambda22_nm: 566 },
  { n: 7, m: 6, lambda11_nm: 1120, lambda22_nm: 648 },
  { n: 7, m: 5, lambda11_nm: 1024, lambda22_nm: 645 },
  { n: 8, m: 3, lambda11_nm: 952, lambda22_nm: 665 },
  { n: 9, m: 4, lambda11_nm: 1101, lambda22_nm: 722 }
];

// ---- full nearest-neighbour tight-binding cut (trigonal warping included) ----
const A_LATTICE = Math.sqrt(3) * A_CC;                       // graphene lattice constant
const LAT_A1 = [A_LATTICE * Math.sqrt(3) / 2, A_LATTICE / 2];
const LAT_A2 = [A_LATTICE * Math.sqrt(3) / 2, -A_LATTICE / 2];
const REC_SCALE = 2 * Math.PI / A_LATTICE;
const REC_B1 = [REC_SCALE / Math.sqrt(3), REC_SCALE];
const REC_B2 = [REC_SCALE / Math.sqrt(3), -REC_SCALE];
const K_POINT = [(2 * REC_B1[0] + REC_B2[0]) / 3, (2 * REC_B1[1] + REC_B2[1]) / 3];
const TB_SAMPLES = 400;           // coarse samples per cutting-line window
const TB_REFINE_STEPS = 80;       // ternary refinement around the coarse minimum
const TB_LINE_HALF_COUNT = 4;     // cutting lines on each side of the K point
// |f| is the square root of a cosine sum, so a line through K bottoms out at
// ~sqrt(machine epsilon) (~1e-7 eV), not zero; semiconducting gaps are >0.5 eV.
const TB_METALLIC_TOL_EV = 1e-6;

function grapheneStructureFactor(kx, ky) {
  const p1 = kx * LAT_A1[0] + ky * LAT_A1[1];
  const p2 = kx * LAT_A2[0] + ky * LAT_A2[1];
  const v = 3 + 2 * Math.cos(p1) + 2 * Math.cos(p2) + 2 * Math.cos(p1 - p2);
  return Math.sqrt(Math.max(v, 0));
}

// Subband edges (conduction-band minima, eV) of the cutting lines nearest K.
// Returns lines sorted by energy, each with its signed offset from K in units
// of the line spacing (+-1/3, -+2/3, ... for semiconducting tubes).
function cuttingLineEdges(n, m, diameterNm) {
  const cx = n * LAT_A1[0] + m * LAT_A2[0];
  const cy = n * LAT_A1[1] + m * LAT_A2[1];
  const cl = Math.hypot(cx, cy);
  const ec = [cx / cl, cy / cl];            // circumferential (quantized) direction
  const et = [-ec[1], ec[0]];               // tube-axis (continuous) direction
  const cK = K_POINT[0] * ec[0] + K_POINT[1] * ec[1];
  const tK = K_POINT[0] * et[0] + K_POINT[1] * et[1];
  const spacing = 2 / diameterNm;
  const mu0 = Math.round(cK / spacing);
  const halfWindow = 0.3 * Math.hypot(REC_B1[0], REC_B1[1]);
  const lines = [];
  for (let mu = mu0 - TB_LINE_HALF_COUNT; mu <= mu0 + TB_LINE_HALF_COUNT; ++mu) {
    const c = mu * spacing;
    const e = (t) => grapheneStructureFactor(c * ec[0] + t * et[0], c * ec[1] + t * et[1]);
    const step = 2 * halfWindow / TB_SAMPLES;
    let best = 0, bestValue = Infinity;
    for (let i = 0; i <= TB_SAMPLES; ++i) {
      const v = e(tK - halfWindow + i * step);
      if (v < bestValue) { bestValue = v; best = i; }
    }
    let lo = tK - halfWindow + Math.max(best - 1, 0) * step;
    let hi = tK - halfWindow + Math.min(best + 1, TB_SAMPLES) * step;
    for (let k = 0; k < TB_REFINE_STEPS; ++k) {
      const x1 = lo + (hi - lo) / 3, x2 = hi - (hi - lo) / 3;
      if (e(x1) < e(x2)) hi = x2; else lo = x1;
    }
    lines.push({ edge_eV: GAMMA0 * e(0.5 * (lo + hi)), offset: (c - cK) / spacing });
  }
  lines.sort((a, b) => a.edge_eV - b.edge_eV);
  return lines;
}

function fullTightBinding(n, m, diameterNm) {
  const lines = cuttingLineEdges(n, m, diameterNm);
  const e11 = lines[0].edge_eV, e22 = lines[1].edge_eV;
  return {
    tb_full_gap_eV: 2 * e11,
    tb_e11_edge_eV: e11,
    tb_e22_edge_eV: e22,
    tb_e22_over_e11: 2 * e11 >= TB_METALLIC_TOL_EV ? e22 / e11 : null,
    tb_e11_line_offset: lines[0].offset,
    tb_e22_line_offset: lines[1].offset
  };
}

function tubeProps(n, m) {
  const root = Math.sqrt(n * n + n * m + m * m);
  const d = DIAM_PREFACTOR * root;                       // nm
  const thetaDeg = Math.atan2(Math.sqrt(3) * m, 2 * n + m) * 180 / Math.PI;
  const nu = (((n - m) % 3) + 3) % 3;
  const metallic = nu === 0;
  const cos3theta = Math.cos(3 * thetaDeg * Math.PI / 180);
  const primaryGap = metallic ? 0.0 : GAP_SCALING_EV_NM / d;    // eV
  const curvatureGap = metallic ? CURVATURE_GAP_COEFF_EV_NM2 * Math.abs(cos3theta) / (d * d) : 0.0;
  const gap = primaryGap + curvatureGap;
  const tb = fullTightBinding(n, m, d);
  const tbMetallic = tb.tb_full_gap_eV < TB_METALLIC_TOL_EV;
  return Object.assign({
    n, m, diameter_nm: d, chiral_angle_deg: thetaDeg,
    family: nu, metallic, band_gap_eV: gap,
    primary_gap_eV: primaryGap,
    curvature_secondary_gap_eV: curvatureGap,
    curvature_cos3theta: cos3theta,
    measured_gap_eV: MEASURED_GAP_EV[n + "," + m] || null,
    kataura_branch: metallic ? "metallic" : ("family" + nu)
  }, tb, {
    tb_metallicity_consistent: tbMetallic === metallic,
    tb_full_rel_dev_from_leading: metallic ? null : tb.tb_full_gap_eV / primaryGap - 1
  });
}

// Zigzag tubes of one family, sorted by diameter: |E22/E11 - 2| must shrink.
function warpingShrinksWithDiameter(tubes, family) {
  const row = tubes.filter((t) => !t.metallic && t.m === 0 && t.family === family)
    .sort((a, b) => a.diameter_nm - b.diameter_nm);
  if (row.length < 2) return false;
  for (let i = 1; i < row.length; ++i) {
    if (Math.abs(row[i].tb_e22_over_e11 - 2) >= Math.abs(row[i - 1].tb_e22_over_e11 - 2)) return false;
  }
  return true;
}

// min(family-1 ratio) - max(family-2 ratio); positive means family 1 lies above.
function familyRatioMargin(rows, ratioOf) {
  const f1 = rows.filter((r) => r.family === 1).map(ratioOf);
  const f2 = rows.filter((r) => r.family === 2).map(ratioOf);
  if (!f1.length || !f2.length) return null;
  return Math.min(...f1) - Math.max(...f2);
}

function katauraAnchors() {
  const HC_EV_NM = 1239.84198;
  return KATAURA_ANCHORS_NM.map((a) => {
    const d = DIAM_PREFACTOR * Math.sqrt(a.n * a.n + a.n * a.m + a.m * a.m);
    const tb = fullTightBinding(a.n, a.m, d);
    return {
      n: a.n, m: a.m, family: (((a.n - a.m) % 3) + 3) % 3, diameter_nm: d,
      measured_e11_eV: HC_EV_NM / a.lambda11_nm,
      measured_e22_eV: HC_EV_NM / a.lambda22_nm,
      measured_e22_over_e11: a.lambda11_nm / a.lambda22_nm,
      tb_e22_over_e11: tb.tb_e22_over_e11,
      tb_full_gap_eV: tb.tb_full_gap_eV
    };
  });
}

// Least-squares slope through the origin (E_g = slope * (1/d)).
function slopeThroughOrigin(pts) {
  let sxx = 0, sxy = 0;
  for (const p of pts) { sxx += p.x * p.x; sxy += p.x * p.y; }
  return sxx > 0 ? sxy / sxx : 0;
}

// 3D observer frame: the whole panel, each tube rolled atom-by-atom from its own
// (n,m) (helpers.cnt), laid out by diameter (x) and electronic family (rows),
// coloured by the band gap this model computed (gold = metallic, blue deepening
// with the gap). The panel is static; any motion in a capture is the camera.
function gapRgba(t) {
  if (t.metallic) {
    const q = Math.min(1.0, t.curvature_secondary_gap_eV / 0.1);   // quasi-metal tint
    return [1.0, 0.78 - 0.25 * q, 0.25 + 0.2 * q, 1.0];
  }
  const g = Math.min(1.0, t.band_gap_eV / 1.2);
  return [0.25 + 0.2 * (1 - g), 0.55 + 0.3 * (1 - g), 1.0, 1.0];
}
function emitPanelFrame(ctx, tubes, fitSlope) {
  return TRECH_VIEWS["cnt_band_structure"]["emitPanelFrame"](ctx, tubes, fitSlope, TRECH_VIEWS, gapRgba, helpers);
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    const tubes = TUBES.map(([n, m]) => tubeProps(n, m));
    const semi = tubes.filter((t) => !t.metallic);
    const metal = tubes.filter((t) => t.metallic);

    // (1) metallicity rule -- spot-check known textbook cases.
    const byKey = {};
    for (const t of tubes) byKey[t.n + "," + t.m] = t;
    const knownMetallic = ["5,5", "10,10", "9,0", "12,0", "6,3", "9,3"];
    const knownSemi = ["10,0", "11,0", "13,0", "17,0", "8,4", "10,5"];
    const metalRuleOk =
      knownMetallic.every((k) => byKey[k] && byKey[k].metallic) &&
      knownSemi.every((k) => byKey[k] && !byKey[k].metallic);

    // (2) gap law: E_g * d is a constant (= 2 a_cc gamma0) across semiconducting
    // tubes, and the (1/d, E_g) fit recovers that slope.
    const products = semi.map((t) => t.band_gap_eV * t.diameter_nm);
    const meanProduct = products.reduce((a, b) => a + b, 0) / products.length;
    const maxProductDev = Math.max(...products.map((p) => Math.abs(p - meanProduct)));
    const fitSlope = slopeThroughOrigin(semi.map((t) => ({ x: 1 / t.diameter_nm, y: t.band_gap_eV })));
    const gapLawOk = maxProductDev < 1e-6 &&
      Math.abs(fitSlope - GAP_SCALING_EV_NM) < 1e-6 &&
      meanProduct > 0.7 && meanProduct < 0.95;   // measured E_g*d ~ 0.7-0.9 eV*nm

    // (3) curvature secondary gap for nominally metallic tubes: armchair stays
    // exactly zero, zigzag/chiral non-armchair follows |cos(3 theta)|/d^2.
    const armchair = metal.filter((t) => t.n === t.m);
    const quasiMetal = metal.filter((t) => t.n !== t.m);
    const armchairProtected = armchair.every((t) => t.curvature_secondary_gap_eV < 1e-12);
    const nonArmchairSmallGaps = quasiMetal.every((t) =>
      t.curvature_secondary_gap_eV > 0.0 &&
      t.curvature_secondary_gap_eV >= 0.005 &&
      t.curvature_secondary_gap_eV <= 0.20);
    const zigzagMetal = quasiMetal.filter((t) => t.m === 0);
    const zigzagProducts = zigzagMetal.map((t) => t.curvature_secondary_gap_eV * t.diameter_nm * t.diameter_nm);
    const meanZigzagCurvProduct = zigzagProducts.reduce((a, b) => a + b, 0) / zigzagProducts.length;
    const maxZigzagCurvProductDev = Math.max(...zigzagProducts.map((p) => Math.abs(p - meanZigzagCurvProduct)));
    const curvatureLawOk =
      armchairProtected &&
      nonArmchairSmallGaps &&
      Math.abs(meanZigzagCurvProduct - CURVATURE_GAP_COEFF_EV_NM2) < 1e-9 &&
      maxZigzagCurvProductDev < 1e-9;

    // (4) absolute semiconducting gaps vs the measured anchors.
    let anchorsOk = true, maxAnchorRelErr = 0;
    for (const t of tubes) {
      if (t.measured_gap_eV) {
        const rel = Math.abs(t.primary_gap_eV - t.measured_gap_eV) / t.measured_gap_eV;
        if (rel > maxAnchorRelErr) maxAnchorRelErr = rel;
        if (rel > 0.15) anchorsOk = false;        // within 15% of measured
      }
    }

    // (5) full tight-binding cut: independent metallicity, leading-order limit
    // and the trigonal-warping (Kataura) family split.
    const tbMetallicityOk = tubes.every((t) => t.tb_metallicity_consistent);
    const maxTbLeadingDev = Math.max(...semi.map((t) => Math.abs(t.tb_full_rel_dev_from_leading)));
    const family1 = semi.filter((t) => t.family === 1);
    const family2 = semi.filter((t) => t.family === 2);
    const warpingSignOk = family1.every((t) => t.tb_e22_over_e11 > 2) &&
      family2.every((t) => t.tb_e22_over_e11 < 2);
    const warpingShrinkOk = warpingShrinksWithDiameter(tubes, 1) && warpingShrinksWithDiameter(tubes, 2);
    const anchors = katauraAnchors();
    const tbAnchorMargin = familyRatioMargin(anchors, (a) => a.tb_e22_over_e11);
    const measuredAnchorMargin = familyRatioMargin(anchors, (a) => a.measured_e22_over_e11);
    const katauraOrderingOk = tbAnchorMargin !== null && measuredAnchorMargin !== null &&
      tbAnchorMargin > 0 && measuredAnchorMargin > 0;
    let maxTbAnchorRelErr = 0;
    for (const t of tubes) {
      if (t.measured_gap_eV) {
        maxTbAnchorRelErr = Math.max(maxTbAnchorRelErr,
          Math.abs(t.tb_full_gap_eV - t.measured_gap_eV) / t.measured_gap_eV);
      }
    }

    emitPanelFrame(ctx, tubes, fitSlope);

    ctx.emit("cnt_panel", {
      kind: "cnt_band_structure",
      model: "tight-binding zone-folding (leading order), hook-layer; Geant4 transports electrons but does not compute band structure",
      a_cc_nm: A_CC, gamma0_eV: GAMMA0,
      gap_scaling_eV_nm: GAP_SCALING_EV_NM,
      curvature_gap_coeff_eV_nm2: CURVATURE_GAP_COEFF_EV_NM2,
      tube_count: tubes.length,
      metallic_count: metal.length, semiconducting_count: semi.length,
      quasi_metallic_count: quasiMetal.length,
      gap_law_fit_slope_eV_nm: fitSlope,
      mean_gap_times_diameter_eV_nm: meanProduct,
      mean_zigzag_curvature_gap_times_diameter2_eV_nm2: meanZigzagCurvProduct,
      max_zigzag_curvature_gap_times_diameter2_dev: maxZigzagCurvProductDev,
      max_curvature_secondary_gap_eV: Math.max(...metal.map((t) => t.curvature_secondary_gap_eV)),
      max_anchor_rel_err: maxAnchorRelErr,
      tb_full_model: "nearest-neighbour graphene dispersion cut along quantized lines near K (trigonal warping included)",
      max_tb_full_rel_dev_from_leading: maxTbLeadingDev,
      max_tb_full_anchor_rel_err: maxTbAnchorRelErr,
      zigzag_family1_e22_over_e11: family1.filter((t) => t.m === 0).map((t) => [t.n, t.tb_e22_over_e11]),
      zigzag_family2_e22_over_e11: family2.filter((t) => t.m === 0).map((t) => [t.n, t.tb_e22_over_e11]),
      kataura_anchors: anchors,
      kataura_tb_family_ratio_margin: tbAnchorMargin,
      kataura_measured_family_ratio_margin: measuredAnchorMargin,
      tubes,
      references: {
        metallicity_rule: "(n-m) mod 3 == 0 => metallic (Saito/Dresselhaus 1998)",
        gap_scaling_eV_nm_measured: "0.7-0.9 (STM, Wildoer/Odom 1998)",
        curvature_secondary_gap: "bare small gap ~ (50 meV nm^2 / d^2) cos(3 theta) for nominally metallic non-armchair tubes",
        kataura_family_ordering: "approximate PL assignments, Bachilo et al. Science 298, 2361 (2002); ordering only"
      },
      validation: Object.assign(
        TRECH_CHECKS["cnt_band_structure"]["checks0"](anchorsOk, armchairProtected, curvatureLawOk, gapLawOk, metalRuleOk, nonArmchairSmallGaps),
        TRECH_CHECKS["cnt_band_structure"]["checks1"](katauraOrderingOk, maxTbLeadingDev, tbMetallicityOk, warpingShrinkOk, warpingSignOk))
    });
  }
};

// A representative semiconducting tube ((10,0), d ~ 0.78 nm) as the Geant4
// geometry; a low-energy electron beam exercises transport. The electronic
// structure above is computed analytically for the whole panel.
const nm = units.nm(1.0);
const repDiameterNm = DIAM_PREFACTOR * 10;          // (10,0)
const outerRadiusMm = 0.5 * repDiameterNm * nm;
const innerRadiusMm = Math.max(0.0, outerRadiusMm - constants.carbonWallThicknessNm * nm);

const cntMaterial = helpers.materialRegistry.fromPreset("carbon", {
  name: "cnt_carbon", densityGcm3: 2.2
});

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: units.mm(2.0), worldMaterial: helpers.materialAliases.air,
    temperatureK: 293.15, pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 0.5, direction: [1, 0, 0] },
  run: { nEvents: 5, seed: 424242, threads: 1 },
  determinism: { mode: "predictive" },
  system: { enable: true, mode: "steady_state", frame: "point_agnostic",
            ensemble: "cnt_band_structure" },
  materials: [cntMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "cnt_container", sizeMm: [units.mm(1.0), units.mm(1.0), units.mm(1.0)],
        tags: ["container", "cnt"]
      }),
      geometry.tubeVolume({
        name: "cnt_10_0", material: "cnt_carbon",
        innerRadiusMm: innerRadiusMm, outerRadiusMm: outerRadiusMm,
        lengthMm: units.nm(50.0), parent: "cnt_container", scoreEdep: true,
        tags: ["carbon_nanotube", "semiconducting"]
      })
    ]
  }
};
