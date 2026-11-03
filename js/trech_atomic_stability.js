// Independent quantum research reference; never a Geant4 tally or learned model.
// Atomic units: lengths a0, masses me, energies Eh. No host/Node dependencies.
(function (root) {
  'use strict';
  const CONSTANTS = Object.freeze({
    edition: 'CODATA 2022',
    source: 'https://physics.nist.gov/cuu/Constants/',
    hartreeEv: 27.211386245981,
    bohrRadiusFm: 52917.7210544,
    protonMassElectron: 1836.152673426,
    protonChargeRadiusFm: 0.84075
  });

  function object(value, name) {
    if (!value || typeof value !== 'object' || Array.isArray(value))
      throw new Error(name + ' must be an object');
  }
  function keys(value, allowed, name) {
    object(value, name);
    for (const key of Object.keys(value))
      if (!allowed.includes(key)) throw new Error('Unsupported ' + name + ' field: ' + key);
  }
  function finite(value, lo, hi, name) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < lo || value > hi)
      throw new Error(name + ' must be finite in [' + lo + ', ' + hi + ']');
    return value;
  }
  function integer(value, lo, hi, name) {
    finite(value, lo, hi, name);
    if (!Number.isInteger(value)) throw new Error(name + ' must be an integer');
    return value;
  }
  function normalize(input) {
    keys(input, ['atomicNumber', 'neutronCount', 'electronCount', 'nuclearMassElectron',
      'chargeRadiusFm', 'state', 'grid', 'accuracyGoalEv'], 'request');
    const z = integer(input.atomicNumber === undefined ? 1 : input.atomicNumber, 1, 10, 'atomicNumber');
    const neutrons = integer(input.neutronCount === undefined ? 0 : input.neutronCount, 0, 30, 'neutronCount');
    const electrons = integer(input.electronCount === undefined ? 1 : input.electronCount, 1, 1, 'electronCount');
    const hydrogen = z === 1 && neutrons === 0;
    if (!hydrogen && input.nuclearMassElectron === undefined)
      throw new Error('An explicit nuclearMassElectron (nuclear, not neutral-atom mass) is required for this isotope');
    const mass = finite(input.nuclearMassElectron === undefined ? CONSTANTS.protonMassElectron : input.nuclearMassElectron,
      1, 1e7, 'nuclearMassElectron');
    const radius = input.chargeRadiusFm === undefined ?
      (hydrogen ? CONSTANTS.protonChargeRadiusFm : null) : input.chargeRadiusFm;
    if (radius !== null) finite(radius, 0, 10, 'chargeRadiusFm');
    const state = input.state === undefined ? {} : input.state;
    keys(state, ['n', 'l'], 'state');
    const n = integer(state.n === undefined ? 1 : state.n, 1, 4, 'state.n');
    const l = integer(state.l === undefined ? 0 : state.l, 0, n - 1, 'state.l');
    const grid = input.grid === undefined ? {} : input.grid;
    keys(grid, ['points', 'radius'], 'grid');
    const points = grid.points === undefined ? [1023, 2047, 4095] : grid.points;
    if (!Array.isArray(points) || points.length < 2 || points.length > 6)
      throw new Error('grid.points must contain 2 to 6 increasing interior grid sizes');
    points.forEach((p, i) => {
      integer(p, 127, 8191, 'grid.points');
      if (i && p + 1 < 2 * (points[i - 1] + 1))
        throw new Error('Each grid must at least double the previous interval count');
    });
    return {
      atomicNumber: z, neutronCount: neutrons, electronCount: electrons,
      nuclearMassElectron: mass, chargeRadiusFm: radius,
      state: {n, l}, grid: {points: points.slice(), radius: finite(grid.radius === undefined ? 40 * n : grid.radius, 4, 640, 'grid.radius')},
      accuracyGoalEv: finite(input.accuracyGoalEv === undefined ? 0.002 : input.accuracyGoalEv, 1e-12, 1, 'accuracyGoalEv')
    };
  }

  // Relative coordinate x = (mu/me) Z r/a0 removes mass/charge from the
  // dimensionless radial operator. Dirichlet endpoints are 0 and radius.
  // No analytic eigenvalue is used to assemble, bracket, or solve the matrix.
  function radialEigenvalue(points, radius, l, rank) {
    const h = radius / (points + 1);
    const kinetic = 1 / (h * h);
    const offSquared = kinetic * kinetic / 4;
    const diagonal = new Float64Array(points);
    let lower = Infinity, upper = -Infinity;
    for (let i = 0; i < points; ++i) {
      const x = (i + 1) * h;
      diagonal[i] = kinetic + l * (l + 1) / (2 * x * x) - 1 / x;
      const rowRadius = (i === 0 || i === points - 1) ? kinetic / 2 : kinetic;
      lower = Math.min(lower, diagonal[i] - rowRadius);
      upper = Math.max(upper, diagonal[i] + rowRadius);
    }
    function below(energy) {
      let pivot = diagonal[0] - energy;
      // Count the same negative infinitesimal used in the next recurrence.
      if (Math.abs(pivot) < 1e-200) pivot = -1e-200;
      let count = pivot < 0 ? 1 : 0;
      for (let i = 1; i < points; ++i) {
        // The negative infinitesimal specifies the Sturm zero-pivot convention.
        pivot = diagonal[i] - energy - offSquared / pivot;
        if (Math.abs(pivot) < 1e-200) pivot = -1e-200;
        if (pivot < 0) ++count;
      }
      return count;
    }
    let iterations = 0;
    while (iterations++ < 100) {
      const midpoint = lower + (upper - lower) / 2;
      if (midpoint === lower || midpoint === upper || upper - lower < 1e-13) break;
      if (below(midpoint) < rank) lower = midpoint;
      else upper = midpoint;
    }
    return {value: lower + (upper - lower) / 2, bracketWidth: upper - lower, iterations, spacing: h};
  }

  function solve(input) {
    const request = normalize(input);
    const {atomicNumber: z, nuclearMassElectron: mass, state: {n, l}, grid} = request;
    const reducedMass = 1 / (1 + 1 / mass);
    const energyScale = reducedMass * z * z * CONSTANTS.hartreeEv;
    const trace = grid.points.map(points => {
      const eigen = radialEigenvalue(points, grid.radius, l, n - l);
      return {points, scaledRadius: grid.radius, scaledSpacing: eigen.spacing,
        energyEv: eigen.value * energyScale, eigenvalueBracketEv: eigen.bracketWidth * energyScale};
    });
    const finest = trace[trace.length - 1];
    // Double the domain AND interval count: box change is measured at fixed h.
    const boxEigen = radialEigenvalue(2 * (finest.points + 1) - 1, 2 * grid.radius, l, n - l);
    const boxEnergy = boxEigen.value * energyScale;
    const gridChange = Math.abs(finest.energyEv - trace[trace.length - 2].energyEv);
    const boxChange = Math.abs(boxEnergy - finest.energyEv);
    const analytic = -energyScale / (2 * n * n);
    const infiniteMass = -z * z * CONSTANTS.hartreeEv / (2 * n * n);
    const radius = request.chargeRadiusFm;
    const sizeShift = radius === null ? null : (l === 0 ?
      (2 / 3) * Math.pow(reducedMass, 3) * Math.pow(z, 4) *
        Math.pow(radius / CONSTANTS.bohrRadiusFm, 2) * CONSTANTS.hartreeEv / Math.pow(n, 3) : 0);
    const corrected = sizeShift === null ? null : finest.energyEv + sizeShift;
    const bound = finest.energyEv < 0 && boxEnergy < 0;
    const omitted = ['relativistic and bound-state QED operators', 'nuclear structure beyond the leading charge-radius contact term',
      'nuclear strong interactions and nuclear binding', 'nuclear polarization', 'weak decay and radiative transition matrix elements',
      'external fields and collisions', 'multi-electron correlations and molecules'];
    return {
      request,
      origin: 'independent_quantum_reference',
      model: 'one_electron_nonrelativistic_coulomb_relative_coordinate',
      units: {energy: 'eV', mass: 'electron_mass', scaledRadius: 'x=(mu/me)*Z*r/a0'},
      energy: {pointNucleusEv: finest.energyEv, leadingFiniteSizeShiftEv: sizeShift,
        withLeadingFiniteSizeEv: corrected, reducedMassElectron: reducedMass,
        referenceZero: 'separated electron and declared nucleus at rest; rest masses excluded'},
      comparison: {analyticReducedMassEv: analytic, infiniteMassEv: infiniteMass,
        analyticRecoilShiftEv: analytic - infiniteMass, numericMinusAnalyticEv: finest.energyEv - analytic,
        role: 'validation_only; analytic levels do not drive the numerical eigenproblem'},
      convergence: {trace, box: {points: 2 * (finest.points + 1) - 1, scaledRadius: 2 * grid.radius,
        energyEv: boxEnergy, fixedSpacing: true}, lastGridChangeEv: gridChange, boxChangeEv: boxChange,
        requestedNumericalChangeEv: request.accuracyGoalEv,
        numericalChangeGoalMet: gridChange <= request.accuracyGoalEv && boxChange <= request.accuracyGoalEv,
        interpretation: 'empirical mesh/box changes, not a rigorous error bound or physical accuracy'},
      stability: {state: {n, l}, electronicBinding: bound ? 'bound_in_declared_model' : 'unresolved',
        channels: [{name: 'electron_ionization', thresholdEv: 0,
          pointNucleusSeparationEv: -finest.energyEv,
          withLeadingFiniteSizeSeparationEv: corrected === null ? null : -corrected,
          widthEv: null, widthStatus: 'not_computed'}],
        nuclearStability: 'not_computed', radiativeWidthEv: null, weakWidthEv: null,
        lifetimeSeconds: null, survivalProbability: null, overallStability: 'undetermined'},
      uncertainty: {totalTheoryEv: null, inputConstantsPropagated: false,
        finiteSizeNumericallyResolved: null,
        finiteSizeExceedsObservedChanges: sizeShift === null ? null : Math.abs(sizeShift) > Math.max(gridChange, boxChange),
        finiteSizeResolutionStatus: 'not_established_by_an_error_bound',
        omitted},
      approximationLedger: [
        'one electron and a supplied structureless nuclear mass/charge; no nuclear solution',
        'center-of-mass removed using reduced mass; recoil is already included once',
        'finite-size shift is first-order perturbation on the analytic point-Coulomb density',
        'for l>0 zero denotes only the leading contact correction',
        'no Geant4 input, ML inference, decay prediction, or universal stability claim'
      ]
    };
  }
  const api = Object.freeze({constants: CONSTANTS, normalize, solve});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.TRECH_ATOMIC_STABILITY = api;
})(globalThis);
