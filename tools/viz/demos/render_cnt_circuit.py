"""Render a data-driven carbon-nanotube logic-gate animation.

``cnt_logic_gates.js`` emits the static-CMOS topology for each gate alongside the
validated truth tables. This renderer consumes that emit and draws the actual
pull-up / pull-down CNTFET networks for the gate currently on screen: NOT,
BUFFER, AND, OR, NAND, NOR, XOR, and XNOR no longer share a fixed inverter-chain
shape. Electrons are animated only through the conducting network selected by
the current truth-table row.

Honest scope: the topology and truth rows come from the deterministic CNT hook
model. Geant4 transports electrons through the representative CNT channel and
provides event-drive metrics; PubChem is not used for CNT chirality/device
structure.

Run::

    cd tools/viz
    source .venv/bin/activate
    python demos/render_cnt_circuit.py

Input:  ``build/dev/out_cnt_logic_gates/trech_hook_emits.jsonl``.
Output: ``tools/viz/demos/cnt_circuit.gif``.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_cnt_logic_gates"
OUT = Path(__file__).resolve().parent / "cnt_circuit.gif"

BG = "#0e1014"
FG = "#e8e8e8"
MUTED = "#9aa3ad"
CARBON = "#aab4c2"
BOND = "#4a525f"
WIRE = "#d2d8df"
HIGH = "#7fdc7f"
LOW = "#ff6b6b"
GATE = "#c89bff"
ACTIVE = "#5fe3ff"
ACC = 0.142


def load_emit(run_dir: Path, tag: str) -> Dict:
    path = run_dir / "trech_hook_emits.jsonl"
    if not path.exists():
        raise SystemExit(f"error: {path} not found; run cnt_logic_gates.js first")
    found = None
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("tag") == tag:
                found = rec.get("payload")
    if not found:
        raise SystemExit(f"error: no {tag} emit found in {path}")
    return found


def tube_circumference_cells(device: Dict) -> int:
    n = int(round(device.get("n", 16)))
    m = int(round(device.get("m", 0)))
    root = math.sqrt(n * n + n * m + m * m)
    return max(6, int(round(root)))


def build_tube_between(x0: float, x1: float, y0: float, z0: float, ncirc: int, nz: int = 4):
    """Lightweight CNT glyph along x between x0 and x1.

    The detailed atom-by-atom honeycomb is shown in cnt_structure.gif. Here each
    CNTFET is one small device in a larger gate network, so a sparse rolled-tube
    mesh keeps the full gate-family animation practical while still preserving
    the chirality-derived diameter.
    """
    a = math.sqrt(3.0) * ACC
    width = ncirc * a
    radius = width / (2.0 * math.pi)
    pts: List[List[float]] = []
    n_theta = 8
    n_axial = 4
    for j in range(n_axial):
        x = x0 + (x1 - x0) * j / (n_axial - 1)
        phase = (j % 2) * math.pi / n_theta
        for i in range(n_theta):
            theta = 2.0 * math.pi * i / n_theta + phase
            pts.append([x, y0 + radius * math.cos(theta), z0 + radius * math.sin(theta)])
    p = np.array(pts)
    segs = []
    for j in range(n_axial):
        row = j * n_theta
        for i in range(n_theta):
            segs.append([p[row + i], p[row + ((i + 1) % n_theta)]])
    for j in range(n_axial - 1):
        row = j * n_theta
        nxt = (j + 1) * n_theta
        for i in range(n_theta):
            segs.append([p[row + i], p[nxt + i]])
            segs.append([p[row + i], p[nxt + ((i + 1) % n_theta)]])
    return p, segs, radius


def path_offsets(count: int) -> List[float]:
    if count <= 1:
        return [0.0]
    span = 0.64
    return [(-span / 2.0) + span * i / (count - 1) for i in range(count)]


def find_gate_panel(summary: Dict, name: str) -> Dict:
    for gate in summary["semiconducting_gates"]["gates"]:
        if gate["name"] == name:
            return gate
    raise KeyError(name)


def row_inputs(row: Dict) -> Dict[str, int]:
    vals = row.get("in", [])
    env = {}
    if vals:
        env["A"] = int(vals[0])
    if len(vals) > 1:
        env["B"] = int(vals[1])
    return env


def fet_on(fet: Dict, env: Dict[str, int]) -> bool:
    value = int(env.get(fet["gate"], 0))
    return value == 0 if fet["type"] == "p" else value == 1


def path_on(path: Iterable[Dict], env: Dict[str, int]) -> bool:
    return all(fet_on(fet, env) for fet in path)


def eval_topology(topology: Dict, row: Dict) -> Tuple[Dict[str, int], List[Dict]]:
    env = row_inputs(row)
    traces = []
    for stage in topology["stages"]:
        pu_on = [path_on(path, env) for path in stage["pull_up"]]
        pd_on = [path_on(path, env) for path in stage["pull_down"]]
        if any(pu_on) and not any(pd_on):
            out = 1
        elif any(pd_on) and not any(pu_on):
            out = 0
        else:
            out = int(row.get("out", 0))
        env[stage["output"]] = out
        traces.append({"stage": stage, "pull_up_on": pu_on, "pull_down_on": pd_on, "out": out})
    env[topology["output"]] = int(row.get("out", env.get(topology["output"], 0)))
    return env, traces


def build_layout(topology: Dict, ncirc: int) -> Tuple[List[Dict], float]:
    stage_pitch = 1.65
    stage_w = 1.18
    tubes: List[Dict] = []
    for si, stage in enumerate(topology["stages"]):
        base_x = si * stage_pitch
        for net_name, zc, paths in (
            ("pull_up", 0.58, stage["pull_up"]),
            ("pull_down", -0.58, stage["pull_down"]),
        ):
            offsets = path_offsets(len(paths))
            for pi, path in enumerate(paths):
                lane_y = offsets[pi]
                fet_w = stage_w / len(path)
                for fi, fet in enumerate(path):
                    x0 = base_x + fi * fet_w + 0.10
                    x1 = base_x + (fi + 1) * fet_w - 0.10
                    p, segs, radius = build_tube_between(x0, x1, lane_y, zc, ncirc)
                    tubes.append({
                        "stage_index": si,
                        "stage_name": stage["name"],
                        "net": net_name,
                        "path_index": pi,
                        "fet_index": fi,
                        "fet": fet,
                        "points": p,
                        "segments": segs,
                        "radius": radius,
                        "x0": x0,
                        "x1": x1,
                        "y": lane_y,
                        "z": zc,
                    })
    extent = max(1.0, (len(topology["stages"]) - 1) * stage_pitch + stage_w)
    return tubes, extent


def active_paths_for_trace(trace: List[Dict], tube: Dict) -> bool:
    st = trace[tube["stage_index"]]
    net_key = "pull_up_on" if tube["net"] == "pull_up" else "pull_down_on"
    return bool(st[net_key][tube["path_index"]])


def draw_network_wires(ax, topology: Dict, extent: float) -> None:
    stage_pitch = 1.65
    stage_w = 1.18
    rail_x0 = -0.24
    rail_x1 = extent + 0.36
    ax.plot([rail_x0, rail_x1], [0, 0], [1.12, 1.12], color=HIGH, lw=2.0, alpha=0.78)
    ax.plot([rail_x0, rail_x1], [0, 0], [-1.12, -1.12], color=LOW, lw=2.0, alpha=0.78)
    for si, stage in enumerate(topology["stages"]):
        base_x = si * stage_pitch
        out_x = base_x + stage_w + 0.12
        ax.plot([out_x, out_x], [0, 0], [-0.84, 0.84], color=WIRE, lw=1.3, alpha=0.45)
        ax.scatter([out_x], [0], [0], c=WIRE, s=28, depthshade=False)
        for paths, rail_z, net_z in ((stage["pull_up"], 1.12, 0.58), (stage["pull_down"], -1.12, -0.58)):
            for lane_y in path_offsets(len(paths)):
                ax.plot([base_x, base_x + 0.08], [lane_y, lane_y], [net_z, net_z],
                        color=WIRE, lw=1.0, alpha=0.45)
                ax.plot([base_x, base_x], [0, lane_y], [rail_z, net_z],
                        color=WIRE, lw=1.0, alpha=0.35)
                ax.plot([base_x + stage_w - 0.08, out_x], [lane_y, 0], [net_z, 0],
                        color=WIRE, lw=1.0, alpha=0.45)


def draw_electrons(ax, tube: Dict, t: float, color: str) -> None:
    xs, ys, zs = [], [], []
    radius = tube["radius"] * 0.52
    for k in range(3):
        phase = (0.29 * k + t * 1.9 + tube["stage_index"] * 0.13) % 1.0
        x = tube["x0"] + phase * (tube["x1"] - tube["x0"])
        ang = 2.0 * math.pi * phase + k * 2.1
        xs.append(x)
        ys.append(tube["y"] + radius * math.cos(ang))
        zs.append(tube["z"] + radius * math.sin(ang))
    ax.scatter(xs, ys, zs, c=color, s=64, depthshade=False, edgecolors="white", linewidths=0.45, zorder=12)


def gate_names_from_arg(arg: str, topologies: Dict[str, Dict]) -> List[str]:
    if arg.strip().lower() == "all":
        return [name for name in ["NOT", "BUFFER", "AND", "OR", "NAND", "NOR", "XOR", "XNOR"] if name in topologies]
    names = [x.strip().upper() for x in arg.split(",") if x.strip()]
    missing = [name for name in names if name not in topologies]
    if missing:
        raise SystemExit(f"error: no topology emitted for gates: {', '.join(missing)}")
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN_DIR)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--frames", type=int, default=64)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--gates", default="all", help="comma-separated gate names, or 'all'")
    args = ap.parse_args()

    summary = load_emit(args.run, "cnt_gates_summary")
    topo_list = summary.get("visual_topologies") or []
    if not topo_list:
        raise SystemExit("error: cnt_gates_summary has no visual_topologies; rerun cnt_logic_gates.js")
    topologies = {t["name"]: t for t in topo_list}
    gate_names = gate_names_from_arg(args.gates, topologies)
    device = summary["working_device"]
    ncirc = tube_circumference_cells(device)
    layouts = {name: build_layout(topologies[name], ncirc) for name in gate_names}

    fig = plt.figure(figsize=(8.4, 4.8), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111, projection="3d")

    def draw(frame: int):
        t_abs = frame / max(1, args.frames)
        gate_pos = min(len(gate_names) - 1, int(t_abs * len(gate_names)))
        gate_t = (t_abs * len(gate_names)) - gate_pos
        gate_name = gate_names[gate_pos]
        topology = topologies[gate_name]
        panel = find_gate_panel(summary, gate_name)
        rows = panel["rows"]
        row_idx = min(len(rows) - 1, int(gate_t * len(rows)))
        row = rows[row_idx]
        env, trace = eval_topology(topology, row)
        tubes, extent = layouts[gate_name]

        fig.texts.clear()
        ax.cla()
        ax.set_facecolor(BG)
        ax.set_axis_off()
        ax.set_box_aspect((max(2.2, extent), 1.25, 1.35))
        draw_network_wires(ax, topology, extent)

        for tube in tubes:
            active = active_paths_for_trace(trace, tube)
            col = ACTIVE if active else BOND
            alpha = 1.0 if active else 0.38
            ax.add_collection3d(Line3DCollection(tube["segments"], colors=col, linewidths=0.82, alpha=alpha))
            ax.scatter(tube["points"][:, 0], tube["points"][:, 1], tube["points"][:, 2],
                       c=CARBON, s=8 if active else 6, depthshade=True, edgecolors="none", alpha=0.92 if active else 0.45)
            if active:
                draw_electrons(ax, tube, gate_t, HIGH if tube["net"] == "pull_up" else LOW)
            mid = 0.5 * (tube["x0"] + tube["x1"])
            th = np.linspace(0, 2 * math.pi, 32)
            gr = tube["radius"] * 1.45
            gval = env.get(tube["fet"]["gate"], 0)
            gcol = HIGH if gval else LOW
            ax.plot(mid * np.ones_like(th), tube["y"] + gr * np.cos(th), tube["z"] + gr * np.sin(th),
                    color=gcol if active else GATE, lw=1.35, alpha=0.9 if active else 0.38)
            if tube["fet"]["gate"] in topology["inputs"]:
                ax.text(mid, tube["y"], tube["z"] + 0.22, tube["fet"]["gate"], color=FG, fontsize=6.5, ha="center")

        orbit = math.sin(2.0 * math.pi * gate_t)
        ax.view_init(elev=18 + 4 * orbit, azim=-64 + 12 * orbit)
        ax.set_xlim(-0.35, extent + 0.45)
        ax.set_ylim(-1.02, 1.02)
        ax.set_zlim(-1.38, 1.38)

        inputs = " ".join(f"{k}={env[k]}" for k in topology["inputs"])
        fig.text(0.5, 0.952, "Carbon-nanotube logic gates - emitted CMOS topology",
                 color=FG, fontsize=12.5, ha="center", fontweight="bold")
        fig.text(0.5, 0.91,
                 f"{gate_name}   {inputs}   Y={row.get('out')} ref={row.get('ref')}   "
                 f"row {row_idx + 1}/{len(rows)}",
                 color=HIGH if row.get("ok") else LOW, fontsize=9.2, ha="center", family="monospace")
        fig.text(0.5, 0.872,
                 f"CNTFET channel ({device['n']},{device['m']})  d={device['diameter_nm']:.2f} nm  "
                 f"E_g={device['band_gap_eV']:.2f} eV  on/off={device['on_off_ratio']:.2e}",
                 color=MUTED, fontsize=7.9, ha="center", family="monospace")
        fig.text(0.5, 0.838,
                 "stages: " + " -> ".join(st["stage"]["primitive"] for st in trace),
                 color=MUTED, fontsize=7.2, ha="center", family="monospace")
        fig.text(0.5, 0.085,
                 "topology is read from cnt_gates_summary.visual_topologies; active electrons follow the truth-table row",
                 color=MUTED, fontsize=7.5, ha="center", family="monospace")
        fig.text(0.075, 0.82, "VDD", color=HIGH, fontsize=8.0, family="monospace")
        fig.text(0.075, 0.175, "GND", color=LOW, fontsize=8.0, family="monospace")
        return []

    total = max(args.frames, len(gate_names) * 8)
    anim = FuncAnimation(fig, draw, frames=total, interval=1000 / args.fps, blit=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    anim.save(args.out, writer=PillowWriter(fps=args.fps))
    plt.close(fig)
    print(f"wrote {args.out}  ({len(gate_names)} emitted gate topologies, CNT cells={ncirc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
