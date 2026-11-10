# CNT electronics — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

### CNT electronics — Shipped

Tight-binding zone-folding band structure + curvature gaps + a full nearest-neighbour dispersion
cut near K (trigonal warping: E22/E11 above 2 for (n-m) mod 3 = 1, below 2 for mod 2, the split
shrinking with diameter; family ordering matches approximate PL assignments, ordering only);
CNTFET static-CMOS gate family +
adders confirmed against truth tables; subthreshold swing ~60 mV/dec; a metallic tube breaks the
logic. Sequential logic (NOR SR latch, master-slave NAND D flip-flop, 2-bit synchronous counter)
is solved as feedback netlists of the same divider gates: each node is relaxed Gauss-Seidel to the
DC fixed point from the previous phase's node voltages (the carried state is the memory; a
synchronous update would ring). Hard-threshold switching makes the fixed point exact and a
non-settling netlist is reported (`converged`), never hidden. Geant4 transports electrons through the channel but does not compute band structure.
