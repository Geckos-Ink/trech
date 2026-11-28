# Single water molecule: thermal ensemble and vibrational spectrum

[Scenario documentation](README.md) · [Documentation index](../README.md)

The [single-water scenario](../../examples/scenarios/h2o_molecule_stability/h2o_molecule_stability.js)
is the first step of the project's north-star "Sputnik" milestone: one H₂O molecule whose bonds
stay stable over time. Its three nuclei are point masses bound by a classical flexible-water
force field: harmonic O–H bonds (r₀ = 0.9572 Å) and a harmonic H–O–H angle (θ₀ = 104.52°). The
molecule is integrated with velocity Verlet in the hook layer. Geant4 cannot form bound molecules,
so this force field is physics for comparison, and Geant4 only clocks the ticks.

Since 2026-11-28 the run also measures the molecule's vibrational spectrum at room temperature
and grades it.

## The thermal ensemble

After the 400 fs stability run, the scenario samples the same force field at 300 K:

1. **Eight replicas** start at the equilibrium geometry. Each nucleus gets a velocity drawn from
   the Maxwell–Boltzmann distribution at 300 K, using the hook's seeded `ctx.rng`.
2. The scenario removes centre-of-mass motion and rigid rotation, which leaves only vibration,
   and scales the velocities to a vibrational energy of 3 kT. That is the canonical mean energy
   of three harmonic modes, so equipartition gives a kinetic temperature of 300 K. The measured
   value is 299.9 K.
3. Each replica runs 8192 steps of 0.2 fs (1.64 ps). The scenario records three internal
   coordinates: the symmetric stretch (r₁ + r₂)/2, the antisymmetric stretch (r₁ − r₂)/2, and
   the bend angle.
4. The power spectrum of each coordinate (Hann window, FFT, summed over replicas) peaks at that
   mode's frequency. A bin is 20.4 cm⁻¹ wide, and a parabola through the peak's neighbours refines
   its position.

The spectrum is emitted as `molecule_spectrum`. The run is deterministic: two runs write
byte-identical emits, and the earlier emits are unchanged.

## How it is graded

The validation companion compares the measured peaks with two references. Neither feeds back into
the simulation.

| Mode | MD peak (cm⁻¹) | Force field's harmonic mode | Measured fundamental |
| --- | --- | --- | --- |
| Symmetric stretch (ν₁) | 3608 | 3604 (+0.11 %) | 3657 (−1.3 %) |
| Bend (ν₂) | 1443 | 1443 (−0.03 %) | 1595 (−9.5 %) |
| Antisymmetric stretch (ν₃) | 3660 | 3657 (+0.10 %) | 3756 (−2.6 %) |

- **The force field's own normal modes** come from a Wilson GF analysis. This is the textbook
  normal-mode calculation for a bent three-atom molecule with only bond and angle force
  constants. If the MD spectrum lands within 1 % of these frequencies, the integrator and the
  spectral analysis are right. They land within 0.11 %.
- **Measured gas-phase fundamentals** (Shimanouchi, NIST CCCBDB) grade the force field itself.
  The stretches are 1.3 % and 2.6 % low and the bend is 9.5 % low. This gap is reported, not
  gated: it is what "bringing the force field closer to measured spectroscopy" has to close. Part
  of it is not the parameters' fault. Real fundamentals include anharmonicity, which a harmonic
  model cannot have; measured harmonic constants are higher (about 3832, 1649 and 3943 cm⁻¹).

The suite case `h2o_molecule_bonds_stable` gates stability, the 1 % match to the harmonic modes,
measured water's mode order (ν₃ > ν₁ > ν₂), the ensemble temperature (within 10 %) and energy
conservation in every replica (drift below 2 %; worst 0.47 %).

## Not yet

The north-star item continues with more atoms and a force field that closes the measured gap,
on the way to a water operator trained from Geant4 particle data; see the
[north-star roadmap](../../AGENTS/project/north-star/ROADMAP.md#priority-queue).
