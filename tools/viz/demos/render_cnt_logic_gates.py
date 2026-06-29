"""Render the TRECH carbon-nanotube LOGIC-GATE comparison.

``cnt_logic_gates.js`` builds carbon-nanotube field-effect transistors (CNTFETs)
from the tight-binding band gap, assembles the full static-CMOS gate family and a
few circuits, and confirms the truth table the electrons produce at the output.
This script plots the four headline stories side by side:

* **transfer characteristic** (top-left) — the simulated drain current
  I_d(V_gs) from Fermi-Dirac band-edge occupation, on a log axis. The
  subthreshold slope recovered from it is the textbook ~60 mV/decade
  room-temperature Fermi limit (SS = ln(10) kT/q).
* **on/off ratio + swing vs temperature** (top-right) — Fermi smearing makes the
  on/off ratio fall and the swing rise as kT grows (the statistical signature of
  the Fermi level).
* **gate truth tables** (bottom-left) — every two-input gate's simulated output
  vs its canonical boolean value (all confirmed); the half/full/2-bit adders are
  confirmed too.
* **metallic tube shorts the gates** (bottom-right) — the working semiconducting
  tube drives outputs cleanly to the rails (0 or Vdd); a metallic tube dropped
  into the same topology collapses every output to ~Vdd/2 (the forbidden region),
  destroying the logic -- the metallic-short manufacturing problem of
  ``docs/CNT/BackToTheCarbon.md``.

Honest scope (same as the rest of the CNT track): Geant4 transports electrons
through the CNT channel geometry but does not compute band structure, the Fermi
level, or CNTFET switching; those are the hook-layer physics for comparison.

Run::

    cd tools/viz
    source .venv/bin/activate
    python demos/render_cnt_logic_gates.py

Input:  ``build/dev/out_cnt_logic_gates/trech_hook_emits.jsonl``.
Output: ``tools/viz/demos/cnt_logic_gates.png``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_cnt_logic_gates"
DEFAULT_OUT = Path(__file__).resolve().parent / "cnt_logic_gates.png"

BG_COLOR = "#16181d"
FG_COLOR = "#e8e8e8"
EXP_COLOR = "#ffb347"     # amber — theory / reference
SEMI_COLOR = "#7fdc7f"    # green — semiconducting (works)
METAL_COLOR = "#ff6b6b"   # red   — metallic (breaks)
GRID_COLOR = "#555c66"
PANEL_BG = "#23272e"


def load_emit(run_dir: Path, tag: str) -> Optional[Dict]:
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
    return found


def _style_ax(ax) -> None:
    ax.set_facecolor(BG_COLOR)
    for s in ax.spines.values():
        s.set_color(GRID_COLOR)
    ax.tick_params(colors=FG_COLOR, labelsize=8.5)


def plot_transfer(ax, summary: Dict) -> None:
    _style_ax(ax)
    fermi = summary["fermi"]
    transfer = fermi["transfer"]
    pts = transfer["points"]
    vgs = np.array([p["vgs"] for p in pts])
    log10_id = np.array([p["log10_id"] for p in pts])
    ax.plot(vgs, log10_id, "-", color=SEMI_COLOR, lw=2.0,
            label=f"({summary['working_device']['n']},{summary['working_device']['m']}) "
                  f"CNTFET  I$_d$(V$_{{gs}}$)")
    vth = float(summary["v_th_V"])
    ax.axvline(vth, color=GRID_COLOR, lw=0.9, ls=":")
    ax.annotate("V$_{th}$", (vth, log10_id.min()), color=FG_COLOR, fontsize=8.5,
                textcoords="offset points", xytext=(3, 2))
    ss = float(transfer["subthreshold_swing_mV_per_dec"])
    ideal = float(fermi["ideal_swing_mV_per_dec"])
    ax.set_xlabel("gate voltage  V$_{gs}$  [V]", color=FG_COLOR, fontsize=9.5)
    ax.set_ylabel("log$_{10}$ I$_d$  (relative)", color=FG_COLOR, fontsize=9.5)
    ax.set_title("CNTFET transfer characteristic (Fermi-Dirac turn-on)",
                 color=FG_COLOR, fontsize=10.5)
    txt = (f"subthreshold swing\n  SS = {ss:.1f} mV/dec\n"
           f"  (ideal ln10·kT/q = {ideal:.1f})\n"
           f"on/off ~ exp(E$_g$/2kT) = {fermi['semiconducting_on_off_ratio']:.2e}")
    ax.text(0.04, 0.96, txt, transform=ax.transAxes, va="top", ha="left",
            color=FG_COLOR, fontsize=8.5, family="monospace",
            bbox=dict(facecolor=PANEL_BG, edgecolor=EXP_COLOR,
                      boxstyle="round,pad=0.4", alpha=0.92))


def plot_temperature(ax, summary: Dict) -> None:
    _style_ax(ax)
    sweep = summary["fermi"]["temperature_sweep"]
    T = np.array([s["temperature_K"] for s in sweep])
    onoff = np.array([s["on_off_ratio"] for s in sweep])
    swing = np.array([s["swing_mV_per_dec"] for s in sweep])
    ax.semilogy(T, onoff, "o-", color=SEMI_COLOR, lw=2.0, ms=7,
                markeredgecolor="white", markeredgewidth=0.6, label="on/off ratio")
    ax.set_xlabel("temperature  T  [K]", color=FG_COLOR, fontsize=9.5)
    ax.set_ylabel("on/off ratio  (log)", color=SEMI_COLOR, fontsize=9.5)
    ax.set_title("Fermi smearing: on/off falls, swing rises with T",
                 color=FG_COLOR, fontsize=10.5)
    ax2 = ax.twinx()
    ax2.tick_params(colors=FG_COLOR, labelsize=8.5)
    for s in ax2.spines.values():
        s.set_color(GRID_COLOR)
    ax2.plot(T, swing, "s--", color=EXP_COLOR, lw=1.8, ms=6,
             markeredgecolor="white", markeredgewidth=0.5, label="swing")
    ax2.set_ylabel("subthreshold swing  [mV/dec]", color=EXP_COLOR, fontsize=9.5)
    ax2.axhline(60.0, color=GRID_COLOR, lw=0.8, ls=":")
    ax2.annotate("~60 mV/dec (300 K)", (T[0], 60.0), color=FG_COLOR, fontsize=8,
                 textcoords="offset points", xytext=(2, 3))
    lines = ax.get_lines() + ax2.get_lines()[:1]
    leg = ax.legend(lines, [ln.get_label() for ln in lines], loc="upper right",
                    fontsize=8.0, facecolor=BG_COLOR, edgecolor=GRID_COLOR)
    for t in leg.get_texts():
        t.set_color(FG_COLOR)


def _two_input_gates(panel: Dict) -> List[Dict]:
    return [g for g in panel["gates"] if g["arity"] == 2]


def plot_truth_tables(ax, summary: Dict) -> None:
    ax.set_facecolor(BG_COLOR)
    ax.axis("off")
    semi = summary["semiconducting_gates"]
    gates = _two_input_gates(semi)
    names = [g["name"] for g in gates]
    # rows = (A,B) input combos in the same order JS emits (c bit b -> input b)
    combos = [(0, 0), (1, 0), (0, 1), (1, 1)]
    col_labels = ["A", "B"] + names
    cell_text = []
    cell_colors = []
    for (a, b) in combos:
        row = [str(a), str(b)]
        colors = [PANEL_BG, PANEL_BG]
        for g in gates:
            match = next((r for r in g["rows"] if r["in"] == [a, b]), None)
            out = match["out"] if match else "?"
            ok = bool(match and match["ok"])
            row.append(str(out))
            colors.append("#1f3a23" if ok else "#3a1f1f")
        cell_text.append(row)
        cell_colors.append(colors)
    table = ax.table(cellText=cell_text, colLabels=col_labels,
                     cellColours=cell_colors, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.45)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(GRID_COLOR)
        cell.get_text().set_color(FG_COLOR)
        if r == 0:
            cell.set_facecolor("#2c313a")
            cell.get_text().set_fontweight("bold")
            cell.get_text().set_color(SEMI_COLOR if c >= 2 else FG_COLOR)
    val = summary["validation"]
    circ = summary["circuits"]
    status = (f"all 8 gate truth tables: "
              f"{'CONFIRMED' if val['all_gate_truth_tables_correct'] else 'FAIL'}\n"
              f"half / full / 2-bit ripple adder: "
              f"{'OK' if val['half_adder_correct'] else 'X'} / "
              f"{'OK' if val['full_adder_correct'] else 'X'} / "
              f"{'OK' if val['ripple_carry_adder_2bit_correct'] else 'X'}    "
              f"(full-adder rows: {len(circ['full_adder']['rows'])}, "
              f"2-bit: {len(circ['ripple_carry_adder_2bit']['rows'])})")
    ax.set_title("logic-gate truth tables (semiconducting (16,0) CNTFET)",
                 color=FG_COLOR, fontsize=10.5)
    ax.text(0.5, -0.02, status, transform=ax.transAxes, va="top", ha="center",
            color=FG_COLOR, fontsize=8.5, family="monospace")


def plot_failure(ax, summary: Dict) -> None:
    _style_ax(ax)

    def all_voltages(panel: Dict) -> np.ndarray:
        vs = []
        for g in panel["gates"]:
            for r in g["rows"]:
                vs.append(float(r["out_voltage"]))
        return np.array(vs)

    semi_v = all_voltages(summary["semiconducting_gates"])
    metal_v = all_voltages(summary["metallic_gates"])
    # forbidden region (ambiguous logic level) shaded
    ax.axvspan(0.3, 0.7, color=METAL_COLOR, alpha=0.12)
    ax.text(0.5, 2.62, "forbidden\n(~V$_{dd}$/2)", color=METAL_COLOR, fontsize=8,
            ha="center", va="center")
    rng = np.random.default_rng(7)
    ax.scatter(semi_v, 2.0 + 0.12 * rng.standard_normal(semi_v.size),
               s=26, color=SEMI_COLOR, edgecolor="white", linewidth=0.4, zorder=3,
               label="semiconducting (16,0): clean rails")
    ax.scatter(metal_v, 1.0 + 0.12 * rng.standard_normal(metal_v.size),
               s=26, color=METAL_COLOR, edgecolor="white", linewidth=0.4, zorder=3,
               label="metallic (5,5): stuck at V$_{dd}$/2")
    ax.set_yticks([1.0, 2.0])
    ax.set_yticklabels(["metallic\n(5,5)", "semicond.\n(16,0)"], fontsize=8.5)
    ax.set_ylim(0.5, 2.9)
    ax.set_xlim(-0.08, 1.08)
    ax.set_xlabel("gate output voltage  V$_{out}$ / V$_{dd}$", color=FG_COLOR, fontsize=9.5)
    ax.set_title("metallic CNT shorts the gates (output → V$_{dd}$/2)",
                 color=FG_COLOR, fontsize=10.5)
    fermi = summary["fermi"]
    txt = (f"on/off  semi {fermi['semiconducting_on_off_ratio']:.2e}\n"
           f"        metal {fermi['metallic_on_off_ratio']:.2f}\n"
           f"logic destroyed: "
           f"{'YES' if summary['validation']['metallic_tube_breaks_logic'] else 'no'}")
    ax.text(0.5, 0.60, txt, transform=ax.transAxes, va="top", ha="center",
            color=FG_COLOR, fontsize=8.0, family="monospace",
            bbox=dict(facecolor=PANEL_BG, edgecolor=METAL_COLOR,
                      boxstyle="round,pad=0.4", alpha=0.92))
    leg = ax.legend(loc="lower center", fontsize=7.8, facecolor=BG_COLOR,
                    edgecolor=GRID_COLOR, ncol=1)
    for t in leg.get_texts():
        t.set_color(FG_COLOR)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    summary = load_emit(args.run, "cnt_gates_summary")
    if not summary or "validation" not in summary:
        raise SystemExit("error: no cnt_gates_summary emit found")

    fig, axes = plt.subplots(2, 2, figsize=(12.4, 8.4), dpi=110, facecolor=BG_COLOR)
    plot_transfer(axes[0][0], summary)
    plot_temperature(axes[0][1], summary)
    plot_truth_tables(axes[1][0], summary)
    plot_failure(axes[1][1], summary)

    dev = summary["working_device"]
    val = summary["validation"]
    fig.suptitle(
        f"TRECH carbon-nanotube logic gates — CNTFET channel ({dev['n']},{dev['m']}), "
        f"d={dev['diameter_nm']:.2f} nm, E$_g$={dev['band_gap_eV']:.2f} eV   ·   "
        f"all checks {'PASS' if val['cnt_logic_gates_ok'] else 'FAIL'}",
        color=FG_COLOR, fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(args.out, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"wrote {args.out}")
    print(f"  gates_ok={val['cnt_logic_gates_ok']} "
          f"SS={summary['fermi']['transfer']['subthreshold_swing_mV_per_dec']:.1f}mV/dec "
          f"on/off semi={summary['fermi']['semiconducting_on_off_ratio']:.2e} "
          f"metal={summary['fermi']['metallic_on_off_ratio']:.2f} "
          f"metallic_breaks={val['metallic_tube_breaks_logic']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
