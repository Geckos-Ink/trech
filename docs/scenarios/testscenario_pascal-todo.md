# TRECH Engine Test Scenario: Pascal's Principle & Material Deformation

**Objective:**
To validate the TRECH engine's calculation of fluid mechanics, specifically testing if macroscopic hydrostatic pressure correctly emerges from microscopic statistical collisions (kinetic theory). The test will verify Pascal's Principle in an ideal rigid vessel and observe pressure dampening in a deformable vessel.

**Substance Used:** Water (H2O) particles simulated at high density (liquid phase).

---

## Scenario A: The Ideal Rigid Vessel (Perfect Pascal)

**Setup:**

* **Vessel:** A closed container made of an "ideal ultra-strong material" (infinite mass/stiffness, meaning boundary particles or segments do not move when struck).
* **Fluid:** The vessel is completely filled with H2O particles, leaving zero macroscopic empty space (high packing fraction).
* **Input (Syringe):** A mechanical piston with surface area $A_{syr}$ that pushes inward with a continuous force $F_{in}$.
* **Output (Sensor):** A specific section of the vessel wall with surface area $A_{sen}$ configured to measure the total impulse of particle collisions over time (Pressure).

**Execution:**

1. Let the system thermalize so the resting pressure $P_0$ is stable and equal across all walls.
2. Apply force $F_{in}$ to the syringe piston, decreasing the volume slightly and instantly increasing the collision frequency of the H2O particles.

**Expected Results (Validation):**
Because the liquid is virtually incompressible and the walls are perfectly rigid, the kinetic energy added by the syringe must transfer through the fluid via particle-to-particle collisions. According to Pascal's Principle, the pressure change $\Delta P$ should be transmitted equally and undiminished to all points of the fluid.

The TRECH engine must output a sensor reading that perfectly satisfies this equation:


$$ \Delta P_{sen} = \frac{F_{in}}{A_{syr}} $$

---

## Scenario B: The Deformable Vessel (Elastoplastic Damping)

**Setup:**

* **Vessel:** A closed container made of "strong plastic." The boundary is constructed of dynamic segments linked by elastic constraints (springs with a specific stiffness coefficient $k$).
* **Fluid:** Filled with H2O particles exactly as in Scenario A.
* **Input / Output:** Identical syringe ($A_{syr}$) and sensor ($A_{sen}$) placement.

**Execution:**

1. Let the system thermalize.
2. Apply the exact same force $F_{in}$ to the syringe piston.

**Expected Results (Validation):**
In this scenario, as the syringe introduces kinetic energy and pushes the H2O particles, the particles strike the plastic walls. Because the walls are deformable, they will yield and stretch outward.

The TRECH engine must successfully simulate the following emergent behaviors:

1. **Volume Expansion:** The overall area/volume of the vessel must visibly increase.
2. **Pressure Damping:** Because the volume increases, the H2O particle density drops slightly compared to Scenario A. Therefore, the frequency of collisions against the sensor will be lower.
3. **Sensor Output:** The pressure measured at the sensor must be strictly **less** than the theoretical ideal pressure applied by the syringe, proving that the engine correctly translates kinetic energy into mechanical work (deforming the plastic).

$$ \Delta P_{sen} < \frac{F_{in}}{A_{syr}} $$



---

Evaluate to implement the deformable plastic walls in the TRECH engine both using standard Hookean springs (1D constraints) and then through micro and then macro statistical prediction starting from GEANT4 basics for a more complex structural mesh to simulate the plastic's elasticity.