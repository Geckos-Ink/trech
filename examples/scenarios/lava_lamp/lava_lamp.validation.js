// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["lava_lamp"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "lava_lamp",
  "scope": "A parameterized lava-lamp thermofluid scenario. Duration is an input, not an identity.",
  "checks": [
    {
      "file": "trech_scores.jsonl",
      "phase": "run_end",
      "field": "n_events",
      "op": "gt",
      "expected": 0
    },
    {
      "file": "trech_scores.jsonl",
      "phase": "run_end",
      "field": "hook_emit_dropped_count",
      "op": "eq",
      "expected": 0,
      "missing": 0
    }
  ],
  "physics_status": "operator_partial",
  "limitations": "thermal, phase, pair-interface and buoyancy/drag state evolution",
  "reference": "tools/validation/trech_validation/cases.py"
};
globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["lava_lamp"] = {
"expectations0": function(APPARATUS, MAX_SPEED_MM_S, NOMINAL_WAX_VOLUME_MM3, PARCEL_SPACING_MM, Z_MAX_MM, Z_MIN_MM, bitCount, g4Seeded, idChecksum, state) { return {
      geant4_material_and_composition_base_present:
        state.carrierReferenceDensityGcm3 > 0.0 && state.waxColdDensityGcm3 > 0.0 &&
        Number(state.waxProbe.electron_density_per_cm3) > 0.0 &&
        state.geant4Events === APPARATUS.outputTicks && state.geant4Steps > 0,
      cascade_supplies_integrator_coefficients:
        state.cascade.__cascade.stagesRun === 2 && g4Seeded &&
        state.params.meltingTemperatureK > APPARATUS.ambientTemperatureK &&
        state.params.waxThermalExpansionPerK > 0.0 &&
        state.params.waxHeatExchangePerS > 0.0 && state.params.cohesionAccelMmS2 >= 0.0 &&
        state.params.interfaceVelocityCouplingPerS > 0.0 &&
        state.params.carrierCirculationMmS > 0.0 && state.params.carrierAdvectionPerS > 0.0 &&
        state.params.carrierVorticityPerS > 0.0 && state.params.lateralPlumeFraction > 0.0,
      persistent_particle_identity:
        state.ids.length === state.n && idChecksum === state.identityChecksum,
      configured_duration_reached:
        Math.abs(state.lastPhysicalTimeS - APPARATUS.durationS) < 1e-8 &&
        state.lastFrame === APPARATUS.outputTicks,
      one_frame_per_geant4_tick:
        state.geant4Events === APPARATUS.outputTicks && state.lastFrame === state.geant4Events,
      bounded_step_state_integration:
        state.physicsSteps >= Math.floor(APPARATUS.durationS / APPARATUS.physicsStepS) &&
        Math.abs(state.physicsTimeS - APPARATUS.durationS) < 1e-8,
      precision_controls_are_independent:
        Math.abs(state.n * PARCEL_SPACING_MM * PARCEL_SPACING_MM * PARCEL_SPACING_MM -
          NOMINAL_WAX_VOLUME_MM3) < 1e-8 &&
        APPARATUS.physicsStepS > 0.0 && APPARATUS.outputTickIntervalS > 0.0 &&
        APPARATUS.renderSurfaceGridMm > 0.0,
      thermodynamic_phase_response:
        state.maxMeanLiquidFraction - state.minMeanLiquidFraction > 0.10,
      density_crossing_drives_buoyancy:
        state.heavierThanCarrierSteps > 0 && state.lighterThanCarrierSteps > 0,
      bidirectional_motion_emerged:
        state.upwardPhysicsSteps > 0 && state.downwardPhysicsSteps > 0,
      thermally_caused_reversal:
        state.buoyancySignChanges > 0 && state.motionSignChanges > 0 &&
        state.buoyancyAlignedSteps > state.buoyancyOpposedSteps,
      substantial_vertical_transport:
        state.maxParticleZMm > 0.55 * APPARATUS.liquidHeightMm &&
        state.maxMeanZMm - state.minMeanZMm > 0.45 * APPARATUS.liquidHeightMm,
      volumetric_convection_not_axis_locked:
        state.maxMeanXMm - state.minMeanXMm > 0.12 * APPARATUS.innerRadiusMm &&
        state.maxMeanYMm - state.minMeanYMm > 0.12 * APPARATUS.innerRadiusMm &&
        state.centroidXyPathMm > APPARATUS.innerRadiusMm &&
        bitCount(state.centroidAzimuthMask) >= 6 &&
        state.lateralPhysicsSteps > 0.5 * state.physicsSteps,
      velocity_cap_not_driving_motion: state.velocityClampCount === 0,
      bounded_continuous_motion:
        state.minParticleZMm >= Z_MIN_MM - 1e-8 &&
        state.maxParticleZMm <= Z_MAX_MM + 1e-8 &&
        state.maxSpeedMmS <= MAX_SPEED_MM_S + 1e-8 &&
        state.maxFrameDisplacementMm <=
          MAX_SPEED_MM_S * APPARATUS.outputTickIntervalS * 1.05 + 1e-6,
      topology_computed_from_neighbours:
        Number.isFinite(state.minComponents) && Number.isFinite(state.maxComponents) &&
        state.minComponents > 0 && state.maxComponents > 0,
      visible_surface_coalescence_and_fission:
        state.renderMergeEvents > 0 && state.renderSplitEvents > 0 &&
        state.minRenderComponents === 1 && state.maxRenderComponents >= 3 &&
        state.renderMergedFrames >= Math.max(6, Math.floor((state.lastFrame + 1) * 0.15)),
      parcel_surface_lineage_retained:
        state.parcelSurfaceMergeEvents > 0 && state.parcelSurfaceSplitEvents > 0 &&
        state.minParcelSurfaceComponents === 1 && state.maxParcelSurfaceComponents >= 4 &&
        state.parcelSurfaceMergedFrames >= Math.max(6, Math.floor((state.lastFrame + 1) * 0.15)),
      blob_topology_temporally_coherent:
        state.topologyChanges <= Math.ceil(APPARATUS.outputTicks * 0.45) &&
        state.maxRenderComponents <= 10
    }; }
};
