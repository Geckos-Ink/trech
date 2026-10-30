// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["cnt_logic_gates"] = {
"frame0": function(CARBON_OFF, OBS, VDD, apparatus, bonds, charts, colors, hud, i, names, positions, radii, samples, tubes, vgs) { return Object.assign(OBS.frame({
      physicalTimeS: i, playbackTimeS: i,
      clockText: "V_gs " + vgs.toFixed(3) + " / " + VDD.toFixed(2) + " V",
      phase: "tight-binding gap -> Fermi-Dirac drain current (hook layer)",
      lengthUnit: "nm", upAxis: "y", digits: 4,
      positions, colors, radii, bonds, apparatus,
      samples, charts,
      labels: tubes.map(({ dev, geo }, k) => ({ position: [(k - 1) * 3.2, -2.95, 1.2],
                                                text: names[k], color_rgba: [0.85, 0.9, 1, 1] })),
      legend: OBS.legend([["carbon lattice (n,m)", CARBON_OFF.concat([1])],
                          ["electrons: count ∝ I_d (representation)", [0.45, 0.85, 1.0, 1]],
                          ["source/drain (repr.)", [0.95, 0.78, 0.35, 1]]]),
      hud,
      motionScope: "static geometry; electron count/drift = model drain current at this V_gs (representation)"
    }), { stream: "cnt_transfer_sweep" }); },
"frame1": function(CARBON_OFF, CARBON_ON, OBS, SEMI, VDD, apparatus, bonds, c, colors, combos, def, frame, ins, level, ok, positions, radii, topo, voltRgba, vout) { return Object.assign(OBS.frame({
        physicalTimeS: frame, playbackTimeS: frame,
        clockText: def.name + " gate, truth row " + (c + 1) + "/" + combos,
        phase: "static CMOS from (" + SEMI.n + "," + SEMI.m + ") CNTFETs (resistive-divider model)",
        lengthUnit: "nm", upAxis: "y", digits: 3,
        positions, colors, radii, bonds, apparatus,
        legend: OBS.legend([["FET off", CARBON_OFF.concat([1])], ["FET on", CARBON_ON.concat([1])],
                            ["node 0 V", voltRgba(0)], ["node Vdd", voltRgba(1)]]),
        hud: [
          topo.inputs.map((label, index) => label + "=" + ins[index]).join("  ") + "  ->  " +
            topo.output + " = " + level(vout) + "   (V_out = " + (vout * VDD).toFixed(3) + " V)",
          (ok ? "matches" : "DOES NOT match") + " the canonical " + def.name + " truth table   " +
            topo.stages.length + " stage(s), on/off " + SEMI.on_off_ratio.toExponential(1)
        ],
        motionScope: "static netlist; glow = FET conductance, node colour = evaluated voltage"
      }), { stream: "cnt_cmos_gates" }); }
};
