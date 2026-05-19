This experiment and its scenario should be implemented and used for validation test

### The Experiment: Osmotic Dehydration via Dimensional Exclusion

The objective is to validate TRECH physics/chemistry engine by placing a simplified "cell" in a hypertonic environment. The engine must naturally simulate the spontaneous efflux of water driven entirely by microscopic kinetic collisions and dimensional exclusion, without relying on hardcoded macroscopic forces.

**1. Test Substance (The Dynamic Variable)**

* **Water ($H_2O$):** This acts as the solvent and the primary dynamic particle that will cross the membrane.

**2. Intracellular Composition (The Cytoplasm)**

* **Membrane:** A circular perimeter made of fixed or spring-constrained segments. Between segments are "pores" with a fixed diameter ($d_{pore}$).
* **Content:** A high-concentration solvent with a low-concentration solute.
* *Solvent:* **$H_2O$** particles. Radius is strictly smaller than the pore ($r_{H_2O} < \frac{d_{pore}}{2}$).
* *Solute:* Macromolecules, representing sugars like **Glucose ($C_6H_{12}O_6$)** or simplified proteins. Radius is strictly larger than the pore ($r_{solute} > \frac{d_{pore}}{2}$).
* *Initial Ratio:* e.g., 90% $H_2O$, 10% $C_6H_{12}O_6$.



**3. Extracellular Environment**

* **Hypertonic Fluid:** An inverted ratio compared to the inside. A massive concentration of large $C_6H_{12}O_6$ particles and a very low concentration of small $H_2O$ particles.

---

### Physical Parameters for the Engine

To ensure stability and realistic behavior in your simulator, use these relative scales:

* **Temperature ($T$):** Set to **$310\text{ K}$** (approx. $37^\circ\text{C}$). In the simulation, temperature translates to the mean kinetic energy of the particles via the formula $E_k = \frac{3}{2}k_B T$. You will apply random force vectors (Brownian motion) every frame to maintain this average energy.
* **Relative Masses:** $H_2O = 1\text{ u}$, $C_6H_{12}O_6 = 10\text{ u}$. This mass difference ensures water particles move with higher velocity and scatter realistically off the heavier solute particles.
* **Relative Diameters:** Pore = **2.0 units**, $H_2O$ = **1.0 unit**, $C_6H_{12}O_6$ = **3.5 units**.
* **Pressure:** Target $\sim1\text{ atm}$ ($101.3\text{ kPa}$). This must remain an *emergent* property, calculated continuously as Force/Area based on the sum of elastic collision impulses against the membrane walls over time.

---

### Expected Results (Validation Criteria)

If your collision detection, elastic response, and thermodynamic randomness are functioning correctly, you should observe the following emergent behaviors:

1. **Initial Chaos:** $H_2O$ and $C_6H_{12}O_6$ will bounce randomly. Both internal and external $H_2O$ molecules will occasionally perfectly align with the pores and pass through. $C_6H_{12}O_6$ will constantly collide with the membrane but bounce back due to dimensional exclusion.
2. **Net Flux:** Because there are significantly fewer $H_2O$ molecules on the outside, the probability of an internal $H_2O$ molecule hitting a pore and exiting is mathematically higher than an external $H_2O$ molecule entering.
3. **Osmotic Shift:** Over time, the absolute count of internal $H_2O$ will drop, and external $H_2O$ will rise.
4. **Membrane Reaction:**
* *If the membrane is rigid:* You will measure a severe drop in internal pressure and a spike in external pressure.
* *If the membrane is flexible (springs):* You will visibly see the cell **crenate** (shrink and crumple inward) as the internal pressure drops, perfectly mimicking real-world cellular dehydration.

## Simulation Timescale

A true physics/chemistry simulator uses a decoupled, variable time integration method (like an adaptive Verlet or Runge-Kutta integrator) where the time step ($\Delta t$) expands or shrinks based on the required precision—such as preventing particles from "tunneling" through the membrane during high-speed collisions.

Instead of screen frames, we should measure the expected results in **Simulation Time Units ($t$)**. If we assume a standard coarse-grained molecular dynamics scale (where $1t$ represents the average time it takes a water molecule to travel its own diameter), here is the physical timeline of events you should look for to validate your engine.

### The Physical Timeline of Osmosis

**1. Thermalization and Energy Distribution ($t = 0 \to t = 50$)**

* **What happens:** You initialize the particles with a specific temperature ($310\text{ K}$). In these first moments, particles exchange momentum through initial collisions. The kinetic energy distributes until it follows a Maxwell-Boltzmann distribution.
* **Engine observation:** Your adaptive $\Delta t$ will likely need to be very small here to resolve initial dense clusters of particles pushing away from each other without mathematical instability.
* **Expected result:** The localized pressure against the membrane stabilizes. The system "wakes up."

**2. Local Diffusion and Barrier Probing ($t = 50 \to t = 500$)**

* **What happens:** Particles explore their immediate local volume. Both water ($H_2O$) and solute ($C_6H_{12}O_6$) begin repeatedly striking the membrane.
* **Engine observation:** You will see the dimensional exclusion rule validated. Solute molecules will strike the pore boundaries and perfectly rebound. A few water molecules that happen to perfectly align their velocity vectors with the pores will cross the boundary.
* **Expected result:** You will register the first few crossover events, but the macroscopic concentration hasn't noticeably changed yet.

**3. Macroscopic Osmotic Flux ($t = 500 \to t = 5,000$)**

* **What happens:** Statistical probability takes over. Because the internal volume has a vastly higher concentration of water, the frequency of internal water hitting the pores is much higher than external water hitting the pores.
* **Engine observation:** As the system enters a stable flow state, your engine can likely expand its $\Delta t$ (taking larger time steps) because you are now tracking statistical averages rather than resolving highly volatile initial energy spikes. However, the engine must dynamically shrink $\Delta t$ at the exact moment particles enter the narrow pore spaces to ensure high-precision collision detection.
* **Expected result:** You will see a steady, observable trend. The counter for "Internal $H_2O$" will drop consistently, while "External $H_2O$" rises. If your membrane has flexible spring constraints, the cell will begin to noticeably shrink or deform (crenation).

**4. Osmotic Equilibrium ($t = 5,000 \to t_{eq}$)**

* **What happens:** The concentration of water inside the cell drops, and the volume of the cell shrinks (increasing the internal concentration of the trapped solute). Eventually, the ratio of water-to-volume inside matches the ratio outside.
* **Engine observation:** The system is highly stable. You can run large time steps for maximum performance, only slowing down for boundary collisions.
* **Expected result:** The net flux reaches zero. Water molecules are still crossing the membrane in both directions, but the *rate* of entry exactly equals the *rate* of exit. The cell stops shrinking.

### Why this is the ultimate test for TRECH engine

By running this timeline, you validate three completely different scales of engine simultaneously:

1. **Microscopic:** Collision detection perfectly handles the size difference (Solutes are blocked, Water passes).
2. **Thermodynamic:** The kinetic energy (Temperature) drives the movement without the simulation "freezing" or exploding over time.
3. **Macroscopic:** The purely random, chaotic movements naturally generate the mathematical law of osmosis, moving the system from high concentration to equilibrium entirely on its own.