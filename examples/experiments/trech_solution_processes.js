// Aqueous NaCl process vocabulary. This library owns units, topology and conservation,
// not solubility, heating/evaporation rates, nucleation, diffusion or crystal morphology.
TRECH_INCLUDE("trech_process_runtime.js");
(function() {
  if (globalThis.TRECH_SOLUTION_PROCESSES) return;
  const species = ["water_liquid", "water_vapour", "salt_solid", "salt_dissolved", "salt_crystal"];
  const conservation = [
    {name: "H", coefficients: {water_liquid: 2, water_vapour: 2}},
    {name: "O", coefficients: {water_liquid: 1, water_vapour: 1}},
    {name: "Na", coefficients: {salt_solid: 1, salt_dissolved: 1, salt_crystal: 1}},
    {name: "Cl", coefficients: {salt_solid: 1, salt_dissolved: 1, salt_crystal: 1}}
  ];
  const clone = x => JSON.parse(JSON.stringify(x));
  function positive(value, name) {
    if (!Number.isFinite(value) || value <= 0) throw new Error(name + " must be positive");
    return value;
  }
  function fraction(value) {
    if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error("Invalid target fraction");
    return value;
  }
  function solution(o) {
    if (!o || !o.water || !o.salt || o.salt.formula !== "NaCl")
      throw new Error("This process family currently supports explicit H2O + NaCl only");
    const water = o.water.parcels, salt = o.salt.parcels;
    if (![water, salt].every(n => Number.isSafeInteger(n) && n > 0))
      throw new Error("Water/salt parcels must be positive safe integers");
    const initial = {water_liquid: [water], water_vapour: [0], salt_solid: [salt],
      salt_dissolved: [0], salt_crystal: [0], temperature_k: [positive(o.temperatureK, "Temperature")]};
    const parcelMol = positive(o.parcelAmountMol, "Common parcel amount (mol)");
    const steps = [];
    let sealed = false;
    function append(step) {
      if (sealed) throw new Error("Recipe is compiled; build a new recipe to edit it");
      if (steps.some(s => s.id === step.id)) throw new Error("Duplicate process: " + step.id);
      steps.push(step); return api;
    }
    const api = {
      mix() {return append({id: "mix", role: "solution_dissolution", channel: "dissolve",
        delta: {salt_solid: -1, salt_dissolved: 1}, target: {field: "salt_solid", maximum: 0}});},
      heat({bathTemperatureK, toleranceK = 1}) {
        return append({id: "heat", role: "solution_thermal", bath_temperature_k: positive(bathTemperatureK, "Bath temperature"),
          tolerance_k: positive(toleranceK, "Temperature tolerance")});
      },
      evaporate({remainingFraction}) {
        if (!steps.some(s => s.id === "heat")) throw new Error("Declare heating before evaporation");
        return append({id: "evaporate", role: "solution_evaporation", channel: "evaporate",
          delta: {water_liquid: -1, water_vapour: 1}, target: {field: "water_liquid", maximum: Math.floor(water * fraction(remainingFraction))}});
      },
      crystallize({solidFraction}) {
        if (!steps.some(s => s.id === "mix")) throw new Error("Declare mixing before crystallization");
        return append({id: "crystallize", role: "solution_crystallization", channel: "precipitate",
          delta: {salt_dissolved: -1, salt_crystal: 1}, target: {field: "salt_crystal", minimum: Math.ceil(salt * fraction(solidFraction))}});
      },
      compile() {
        if (!steps.length) throw new Error("Recipe has no processes");
        sealed = true;
        const plan = {schema: "trech_solution_recipe_v1", material_kind: "aqueous_nacl",
          initial: clone(initial), parcel_amount_mol: parcelMol, species: species.slice(),
          conservation: clone(conservation), steps: clone(steps),
          spatial_state_available: false,
          thermal_scope: "Sequential thermal preparation; coupled latent heat/energy transport unavailable",
          scope: "Engine operator orchestration; no fallback laws, particle paths or microscopy morphology"};
        function validate(state) {
          for (const key of species)
            if (!Array.isArray(state[key]) || state[key].length !== 1 || !Number.isSafeInteger(state[key][0]) || state[key][0] < 0)
              throw new Error("Invalid conserved inventory: " + key);
          if (state.water_liquid[0] + state.water_vapour[0] !== water ||
              state.salt_solid[0] + state.salt_dissolved[0] + state.salt_crystal[0] !== salt)
            throw new Error("Process violated H/O/Na/Cl conservation");
          if (!Array.isArray(state.temperature_k) || state.temperature_k.length !== 1)
            throw new Error("Missing thermal state");
          positive(state.temperature_k[0], "Temperature");
        }
        const heat = steps.find(s => s.id === "heat");
        const heatIndex = steps.findIndex(s => s.id === "heat");
        const stages = steps.map((s, stageIndex) => ({id: s.id,
          complete(state) {return s.id === "heat" ? Math.abs(state.temperature_k[0] - s.bath_temperature_k) <= s.tolerance_k :
            s.target.maximum !== undefined ? state[s.target.field][0] <= s.target.maximum : state[s.target.field][0] >= s.target.minimum;},
          advance(ctx, state, dt) {
            const context = {parcel_amount_mol: parcelMol};
            if (heat && stageIndex >= heatIndex) context.bath_temperature_k = heat.bath_temperature_k;
            if (s.id === "heat") return ctx.evolve({dt, fields: [{name: "temperature_k", min: 0}],
              state: {temperature_k: state.temperature_k}, aux: Object.fromEntries(species.map(k => [k, state[k]])), context,
              operator_role: s.role, element_kind: plan.material_kind});
            return ctx.react({dt, species, state: Object.fromEntries(species.map(k => [k, state[k]])),
              aux: {temperature_k: state.temperature_k}, context,
              channels: [{name: s.channel, delta: s.delta}], conservation,
              operator_role: s.role, element_kind: plan.material_kind});
          }}));
        return {plan: clone(plan), create: () => TRECH_PROCESS_RUNTIME.create({initial, stages, validate})};
      }
    };
    return api;
  }
  globalThis.TRECH_SOLUTION_PROCESSES = {solution};
})();
