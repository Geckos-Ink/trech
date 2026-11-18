"""Recursive group-lifting hierarchies: train element -> group -> ... -> observer models.

The engine's `GroupHierarchy` (`ctx.lift`, include/trech/ml/GroupHierarchy.hpp) lifts a
POPULATION scale by scale: each level partitions the current elements into groups (a cubic
lattice of edge `cell_size`, explicit ids, or one group of everything), evaluates a trained
set network (generic_surrogate_v3 + `group_lift`) on each group's members, and the groups
become the next level's elements (position = weight-centroid of the members, weight = sum).

This module owns the Python side of that contract:

* `partition` / `build_structure` replay the engine's grouping EXACTLY (lattice cells ordered
  by (ix, iy, iz), explicit ids ascending, members ascending, centroids accumulated in that
  order, rel_* = (member - centroid) / length). Grouping depends only on positions, weights and
  ids, never on learned values, so the whole hierarchy's structure is computed once.
* `train` fits every level END TO END in torch: level k consumes level k-1's *predictions*
  (never its labels), so a level learns from exactly what the chain will feed it at run time.
  A level may carry supervised outputs (labels per group, keyed like the engine's `keys`),
  learned latent channels (free features a higher level may need, e.g. how charge is
  distributed inside a cell), or both. Every level reuses `set_networks.build_torch`, so the
  exported arithmetic is the v3 arithmetic the C++ evaluator already matches to 1e-9.
* `lift_np` is the NumPy reference evaluator of the exported JSON models with the engine's
  blocking rules (capacity overflow, blocked members); holdout metrics, input domains and the
  parity fixtures are all computed through it, i.e. on the exported artefacts.

Sample files are JSON lines (`trech_group_samples_v1`): one system per line with
`features` (base element arrays), optional `positions {x,y,z}`, `weight`, `context`, `groups`
(explicit ids per level name) and `targets {level: {key: {output: value}}}`. A group key is
`"ix,iy,iz"` for lattice levels, the id for explicit levels and `"all"` for the one-group
level. `run` names the run a sample came from (whole runs never straddle a split).

The plan (`trech_group_hierarchy_plan_v1`) declares the base features and the levels:

    {"schema": "trech_group_hierarchy_plan_v1", "base_features": ["q"],
     "levels": [
       {"name": "cell", "scale": "nano", "grouping": "cell", "cell_size": 1.0,
        "member_features": ["present", "rel_x", "rel_y", "rel_z", "q"],
        "outputs": ["cell_energy"], "latent": 4,
        "network": {"kind": "deepsets", "phi": [32, 32], "rho": [32], "pool": "sum"}},
       {"name": "system", "scale": "micro", "grouping": "all", "length": 4.0,
        "member_features": ["present", "weight", "rel_x", "rel_y", "rel_z", "cell_energy",
                            "cell_h0", "cell_h1", "cell_h2", "cell_h3"],
        "context": ["g"], "outputs": ["energy"]}]}

Latent channels are named `<level>_h<i>` and exported as `group_lift.latent_outputs`, so no
consumer can mistake them for physical quantities.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SYNTHESIZED = ("present", "weight", "rel_x", "rel_y", "rel_z")
GROUPINGS = ("cell", "explicit", "all")
PLAN_SCHEMA = "trech_group_hierarchy_plan_v1"
SAMPLE_SCHEMA = "trech_group_samples_v1"
MEMBER_PREFIX = "m"


# ---------------------------------------------------------------------------- plan

def load_plan(plan: dict) -> dict:
    """Validate a hierarchy plan and fill defaults (raises ValueError)."""
    if plan.get("schema", PLAN_SCHEMA) != PLAN_SCHEMA:
        raise ValueError(f"plan schema must be {PLAN_SCHEMA}")
    base = [str(n) for n in plan.get("base_features") or []]
    levels = plan.get("levels") or []
    if not levels:
        raise ValueError("plan needs at least one level")
    available = set(base)
    names = set()
    out_levels = []
    for index, raw in enumerate(levels):
        level = dict(raw)
        name = str(level.get("name") or "")
        if not name or name in names:
            raise ValueError(f"level {index} needs a unique name")
        names.add(name)
        grouping = level.get("grouping", "all")
        if grouping not in GROUPINGS:
            raise ValueError(f"level {name}: grouping must be one of {GROUPINGS}")
        if grouping == "cell" and not float(level.get("cell_size") or 0) > 0:
            raise ValueError(f"level {name}: cell grouping needs a positive cell_size")
        members = [str(m) for m in level.get("member_features") or []]
        if "present" not in members:
            raise ValueError(f"level {name}: member_features must include 'present' (the set mask)")
        if len(set(members)) != len(members):
            raise ValueError(f"level {name}: duplicate member feature")
        missing = [m for m in members if m not in SYNTHESIZED and m not in available]
        if missing:
            raise ValueError(f"level {name}: member features {missing} are not produced by the level below")
        length = float(level.get("length") or level.get("cell_size") or 0.0)
        if any(m.startswith("rel_") for m in members) and not length > 0:
            raise ValueError(f"level {name}: rel_* member features need a length (cell_size or length)")
        outputs = [str(o) for o in level.get("outputs") or []]
        links = list(level.get("output_transforms", ["identity"] * len(outputs)))
        if len(links) != len(outputs) or any(link not in ("identity", "sigmoid") for link in links):
            raise ValueError(f"level {name}: output_transforms needs one identity or sigmoid per output")
        latent = int(level.get("latent") or 0)
        if latent < 0 or (not outputs and not latent):
            raise ValueError(f"level {name}: needs supervised outputs and/or latent channels")
        latent_names = [f"{name}_h{i}" for i in range(latent)]
        produced = outputs + latent_names
        if len(set(produced)) != len(produced) or set(produced) & set(SYNTHESIZED):
            raise ValueError(f"level {name}: output names must be unique and not reserved")
        network = dict(level.get("network") or {})
        network.setdefault("kind", "deepsets")
        network.setdefault("phi", [32, 32])
        network.setdefault("rho", [32])
        network.setdefault("pool", "sum")
        network.setdefault("activation", "silu")
        level.update({"name": name, "grouping": grouping, "member_features": members,
                      "outputs": outputs, "latent_names": latent_names, "produced": produced,
                      "output_transforms": links,
                      "length": length, "context": [str(c) for c in level.get("context") or []],
                      "scale": str(level.get("scale") or ""), "network": network,
                      "loss_weight": float(level.get("loss_weight", 1.0))})
        out_levels.append(level)
        available = set(produced)
    if not out_levels[-1]["outputs"]:
        raise ValueError("the top level must have supervised outputs")
    return {"schema": PLAN_SCHEMA, "base_features": base, "levels": out_levels,
            "origin": [float(v) for v in plan.get("origin") or [0.0, 0.0, 0.0]]}


# ---------------------------------------------------------------------------- grouping

def partition(count: int, positions: Optional[List[Tuple[float, float, float]]], level: dict,
              origin: Sequence[float], group_ids: Optional[Sequence[int]] = None):
    """Engine-identical partition: list of (key, [member indices]) in engine order."""
    grouping = level["grouping"]
    if grouping == "all":
        return [("all", list(range(count)))] if count else []
    if grouping == "explicit":
        if group_ids is None or len(group_ids) != count:
            raise ValueError(f"level {level['name']}: explicit groups need one id per element")
        by_id: Dict[int, List[int]] = {}
        for i, gid in enumerate(group_ids):
            by_id.setdefault(int(gid), []).append(i)
        return [(str(gid), by_id[gid]) for gid in sorted(by_id)]
    if positions is None:
        raise ValueError(f"level {level['name']}: cell grouping needs positions")
    cell = float(level["cell_size"])
    by_cell: Dict[Tuple[int, int, int], List[int]] = {}
    for i, p in enumerate(positions):
        key = tuple(int(math.floor((p[a] - origin[a]) / cell)) for a in range(3))
        by_cell.setdefault(key, []).append(i)
    return [(",".join(str(v) for v in key), by_cell[key]) for key in sorted(by_cell)]


def centroid(members: Sequence[int], positions, weights) -> Tuple[float, Tuple[float, float, float]]:
    """Sum of weights and weight-centroid, accumulated in ascending member order (as C++)."""
    w = 0.0
    c = [0.0, 0.0, 0.0]
    for m in members:
        w += weights[m]
        if positions is not None:
            for a in range(3):
                c[a] += weights[m] * positions[m][a]
    if positions is None:
        return w, (math.nan, math.nan, math.nan)
    return w, tuple((c[a] / w) if w != 0.0 else math.nan for a in range(3))


def _sample_positions(sample: dict, count: int):
    pos = sample.get("positions")
    if not pos:
        return None
    xs = pos.get("x") or [0.0] * count
    ys = pos.get("y") or [0.0] * count
    zs = pos.get("z") or [0.0] * count
    return [(float(xs[i]), float(ys[i]), float(zs[i])) for i in range(count)]


def sample_count(sample: dict) -> int:
    feats = sample.get("features") or {}
    for values in feats.values():
        return len(values)
    pos = sample.get("positions") or {}
    return len(pos.get("x") or [])


def build_structure(sample: dict, plan: dict) -> List[dict]:
    """Per level: groups (key, members), centroids, weights and raw synthesized features."""
    count = sample_count(sample)
    positions = _sample_positions(sample, count)
    weights = [float(w) for w in sample.get("weight") or [1.0] * count]
    levels = []
    for level in plan["levels"]:
        ids = (sample.get("groups") or {}).get(level["name"])
        groups = partition(count, positions, level, plan["origin"], ids)
        g_pos, g_w, synth = [], [], []
        for _key, members in groups:
            w, c = centroid(members, positions, weights)
            g_pos.append(c)
            g_w.append(w)
            rows = []
            for m in members:
                row = {"present": 1.0, "weight": weights[m]}
                if positions is not None and level["length"] > 0:
                    for a, axis in enumerate(("rel_x", "rel_y", "rel_z")):
                        row[axis] = (positions[m][a] - c[a]) / level["length"]
                rows.append(row)
            synth.append(rows)
        levels.append({"keys": [k for k, _ in groups], "members": [m for _, m in groups],
                       "synth": synth, "weights": g_w})
        count = len(groups)
        positions = g_pos if positions is not None else None
        weights = g_w
    return levels


# ---------------------------------------------------------------------------- NumPy evaluator

def _model_layout(model: dict):
    net = model["network"]
    lift = model["group_lift"]
    return int(net["elements"]), list(lift["member_features"]), list(lift.get("context_features") or [])


def lift_np(sample: dict, plan: dict, models: Sequence[dict], *, collect_rows: bool = False):
    """Evaluate exported level models on one sample with the engine's blocking rules.

    Returns a list per level of {keys, features [G, out] (NaN when blocked), valid, rows?}.
    """
    import numpy as np

    from .set_networks import predict_network_np

    structure = build_structure(sample, plan)
    count = sample_count(sample)
    names = list(plan["base_features"])
    feats = np.array([[float(sample["features"][n][i]) for n in names] for i in range(count)],
                     dtype=float).reshape(count, len(names))
    valid = np.ones(count, dtype=bool)
    context = {k: float(v) for k, v in (sample.get("context") or {}).items()}
    out_levels = []
    for level, model, struct in zip(plan["levels"], models, structure):
        cap, members_f, ctx_f = _model_layout(model)
        n_in = len(model["input_features"])
        mean = np.asarray(model["input_mean"], dtype=float)
        std = np.asarray(model["input_std"], dtype=float)
        std = np.where(np.abs(std) < 1e-12, 1.0, std)
        n_out = len(model["output_features"])
        groups = len(struct["members"])
        out = np.full((groups, n_out), np.nan)
        g_valid = np.zeros(groups, dtype=bool)
        rows, row_index = [], []
        for g, members in enumerate(struct["members"]):
            if len(members) > cap or not all(valid[m] for m in members):
                continue
            raw = np.empty(n_in)
            for slot in range(cap):
                for f, name in enumerate(members_f):
                    j = slot * len(members_f) + f
                    if slot >= len(members):
                        raw[j] = 0.0 if name == "present" else mean[j]
                    elif name in SYNTHESIZED:
                        raw[j] = struct["synth"][g][slot][name]
                    else:
                        raw[j] = feats[members[slot], names.index(name)]
            for c, name in enumerate(ctx_f):
                raw[cap * len(members_f) + c] = context[name]
            rows.append(raw)
            row_index.append(g)
        if rows:
            raw = np.vstack(rows)
            z = (raw - mean) / std
            y = predict_network_np(z, raw, model["network"])
            y = y * np.asarray(model["output_std"], dtype=float) + np.asarray(model["output_mean"], dtype=float)
            finite = np.isfinite(y).all(axis=1)
            for o, link in enumerate(model.get("output_transforms", ())):
                if link == "sigmoid":
                    y[:, o] = 1 / (1 + np.exp(-np.clip(y[:, o], -700, 700)))
            for r, g in enumerate(row_index):
                if finite[r]:
                    out[g] = y[r]
                    g_valid[g] = True
        entry = {"keys": struct["keys"], "features": out, "valid": g_valid}
        if collect_rows:
            entry["rows"] = np.vstack(rows) if rows else np.zeros((0, n_in))
        out_levels.append(entry)
        names = list(model["output_features"])
        feats = out
        valid = g_valid
    return out_levels


# ---------------------------------------------------------------------------- training

def read_samples(paths: Sequence[str]) -> List[dict]:
    samples = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                record = json.loads(line)
                if record.get("schema", SAMPLE_SCHEMA) != SAMPLE_SCHEMA:
                    raise ValueError(f"{path}: sample schema must be {SAMPLE_SCHEMA}")
                samples.append(record)
    return samples


def _flatten(samples: Sequence[dict], plan: dict):
    """Concatenate every sample's structure into flat per-level index arrays."""
    import numpy as np

    base = plan["base_features"]
    x0, offsets = [], []
    total = 0
    structures = []
    for sample in samples:
        n = sample_count(sample)
        offsets.append(total)
        total += n
        x0.extend([[float(sample["features"][f][i]) for f in base] for i in range(n)])
        structures.append(build_structure(sample, plan))
    flat = {"x0": np.asarray(x0, dtype=float).reshape(total, len(base)), "levels": []}
    lower_offsets = offsets
    for k, level in enumerate(plan["levels"]):
        idx, synth, ctx, labels, mask, sample_of = [], [], [], [], [], []
        new_offsets = []
        count = 0
        for s, (sample, struct) in enumerate(zip(samples, structures)):
            new_offsets.append(count)
            st = struct[k]
            targets = (sample.get("targets") or {}).get(level["name"]) or {}
            for g, members in enumerate(st["members"]):
                idx.append([lower_offsets[s] + m for m in members])
                synth.append(st["synth"][g])
                ctx.append([float((sample.get("context") or {})[c]) for c in level["context"]])
                label = targets.get(st["keys"][g])
                if label is not None and all(o in label for o in level["outputs"]):
                    labels.append([float(label[o]) for o in level["outputs"]])
                    mask.append(True)
                else:
                    labels.append([0.0] * len(level["outputs"]))
                    mask.append(False)
                sample_of.append(s)
            count += len(st["members"])
        flat["levels"].append({
            "idx": idx, "synth": synth, "ctx": np.asarray(ctx, dtype=float).reshape(len(idx), len(level["context"])),
            "labels": np.asarray(labels, dtype=float).reshape(len(idx), len(level["outputs"])),
            "mask": np.asarray(mask, dtype=bool), "sample": np.asarray(sample_of, dtype=int)})
        lower_offsets = new_offsets
    return flat


def _stats(values, fallback_mean=0.0):
    import numpy as np

    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return fallback_mean, 1.0
    std = float(a.std())
    return float(a.mean()), (std if std > 1e-9 else 1.0)


def _scalers(plan: dict, flat: dict, capacities: List[int]):
    """Per-level member-feature (mean, std), context stats and output stats."""
    import numpy as np

    base = plan["base_features"]
    lower_stats = {f: _stats(flat["x0"][:, i]) for i, f in enumerate(base)}
    out = []
    for k, level in enumerate(plan["levels"]):
        lv = flat["levels"][k]
        cap = capacities[k]
        member = {}
        for name in level["member_features"]:
            if name == "present":
                present = [1.0] * sum(len(i) for i in lv["idx"])
                present += [0.0] * (len(lv["idx"]) * cap - len(present))
                member[name] = _stats(present)
            elif name in SYNTHESIZED:
                member[name] = _stats([row[name] for rows in lv["synth"] for row in rows])
            else:
                member[name] = lower_stats[name]
        context = [_stats(lv["ctx"][:, c]) for c in range(len(level["context"]))]
        labelled = lv["labels"][lv["mask"]]
        if level["outputs"] and not len(labelled):
            raise ValueError(f"level {level['name']}: no labelled training groups for its outputs")
        produced, encoded = {}, {}
        for o, name in enumerate(level["outputs"]):
            values = labelled[:, o]
            produced[name] = encoded[name] = _stats(values)
            if level["output_transforms"][o] == "sigmoid":
                if not np.all(np.isfinite(values) & (values >= 0) & (values <= 1)):
                    raise ValueError(f"level {level['name']}: sigmoid targets must be fractions in [0, 1]")
                clipped = values.clip(1e-6, 1 - 1e-6)
                encoded[name] = _stats(np.log(clipped) - np.log1p(-clipped))
        for name in level["latent_names"]:
            produced[name] = encoded[name] = (0.0, 1.0)
        out.append({"member": member, "context": context, "produced": produced, "encoded": encoded})
        lower_stats = produced
    return out


def _input_names(level: dict, capacity: int) -> List[str]:
    return [f"{MEMBER_PREFIX}{e}_{f}" for e in range(capacity) for f in level["member_features"]] + list(level["context"])


def _statics(flat: dict, plan: dict, caps: List[int], scal: List[dict], base_mean, base_std):
    """Gather indices and standardized synthesized/context/label blocks of one dataset."""
    import numpy as np
    import torch

    z0 = torch.tensor((flat["x0"] - base_mean) / base_std, dtype=torch.float32)
    lower_names = list(plan["base_features"])
    lower_count = len(flat["x0"])
    statics = []
    for k, level in enumerate(plan["levels"]):
        lv = flat["levels"][k]
        cap, members = caps[k], level["member_features"]
        groups = len(lv["idx"])
        gather = np.full((groups, cap), lower_count, dtype=np.int64)  # index lower_count = zero row
        synth_z = np.zeros((groups, cap, len(members)))
        sm = scal[k]["member"]
        for g, idx in enumerate(lv["idx"]):
            gather[g, :len(idx)] = idx
            for slot in range(cap):
                for f, name in enumerate(members):
                    if name not in SYNTHESIZED:
                        continue
                    mean, std = sm[name]
                    if slot < len(idx):
                        synth_z[g, slot, f] = (lv["synth"][g][slot][name] - mean) / std
                    elif name == "present":
                        synth_z[g, slot, f] = (0.0 - mean) / std
        lower_cols = [lower_names.index(n) if n not in SYNTHESIZED else -1 for n in members]
        cmean = np.array([m for m, _ in scal[k]["context"]]) if level["context"] else np.zeros(0)
        cstd = np.array([s for _, s in scal[k]["context"]]) if level["context"] else np.zeros(0)
        ctx_z = (lv["ctx"] - cmean) / cstd if level["context"] else np.zeros((groups, 0))
        out_mean = np.array([scal[k]["produced"][n][0] for n in level["outputs"]])
        out_std = np.array([scal[k]["produced"][n][1] for n in level["outputs"]])
        labels_z = (lv["labels"] - out_mean) / out_std if level["outputs"] else np.zeros((groups, 0))
        linked = None
        if "sigmoid" in level["output_transforms"]:
            active = [link == "sigmoid" for link in level["output_transforms"]]
            if not np.all((lv["labels"][lv["mask"]][:, active] >= 0) &
                          (lv["labels"][lv["mask"]][:, active] <= 1)):
                raise ValueError(f"level {level['name']}: sigmoid targets must be fractions in [0, 1]")
            columns = level["produced"]
            e_mean, e_std = zip(*(scal[k]["encoded"][name] for name in columns))
            p_mean, p_std = zip(*(scal[k]["produced"][name] for name in columns))
            mask = torch.tensor(active + [False] * len(level["latent_names"]))
            linked = (mask, *(torch.tensor(v, dtype=torch.float32) for v in (e_mean, e_std, p_mean, p_std)))
        statics.append({
            "linked": linked, "gather": torch.tensor(gather), "synth": torch.tensor(synth_z, dtype=torch.float32),
            "lower_cols": lower_cols, "ctx": torch.tensor(ctx_z, dtype=torch.float32),
            "labels": torch.tensor(labels_z, dtype=torch.float32),
            "mask": torch.tensor(lv["mask"]), "groups": groups})
        lower_names = level["produced"]
        lower_count = groups
    return z0, statics


def _forward(plan: dict, nets, z0, statics):
    """Chained forward pass; returns the per-level supervised losses (standardized MSE)."""
    import torch

    lower = z0
    losses = []
    for k, level in enumerate(plan["levels"]):
        st = statics[k]
        padded = torch.cat([lower, torch.zeros(1, lower.shape[1])], dim=0)
        gathered = padded[st["gather"]]  # [G, cap, H]
        cols = [st["synth"][:, :, f] if col < 0 else gathered[:, :, col]
                for f, col in enumerate(st["lower_cols"])]
        members = torch.stack(cols, dim=2)
        flat_in = torch.cat([members.reshape(st["groups"], -1), st["ctx"]], dim=1)
        out = nets[k](flat_in)
        if st["linked"] is not None:
            linked, em, es, pm, ps = st["linked"]
            decoded = torch.sigmoid(out * es + em)
            out = torch.where(linked, (decoded - pm) / ps, out)
        n_sup = len(level["outputs"])
        if n_sup and bool(st["mask"].any()):
            diff = out[:, :n_sup][st["mask"]] - st["labels"][st["mask"]]
            losses.append(level["loss_weight"] * (diff ** 2).mean())
        lower = out
    return losses


def train(plan: dict, samples: Sequence[dict], *, selection_samples: Sequence[dict] = (),
          epochs: int = 1500, lr: float = 3e-3, lr_final_factor: float = 0.05, seed: int = 0,
          weight_decay: float = 0.0, eval_every: int = 25,
          capacities: Optional[List[int]] = None, quiet: bool = False):
    """Fit every level end to end; returns (exported model dicts without trust blocks, report).

    With `selection_samples` (whole runs, disjoint from training and from any holdout) the
    chained selection loss is evaluated every `eval_every` epochs and the weights with the lowest
    one are exported (early stopping); scalers come from the training samples only.
    """
    import copy

    import numpy as np
    import torch

    from .set_networks import build_torch, make_spec, network_json

    flat = _flatten(samples, plan)
    flat_sel = _flatten(selection_samples, plan) if selection_samples else None
    caps = []
    for k, level in enumerate(plan["levels"]):
        largest = max((len(i) for i in flat["levels"][k]["idx"]), default=1)
        if flat_sel is not None:
            largest = max([largest] + [len(i) for i in flat_sel["levels"][k]["idx"]])
        cap = int((capacities or [None] * len(plan["levels"]))[k] or level.get("capacity") or largest)
        if cap < largest:
            raise ValueError(f"level {level['name']}: capacity {cap} < largest fitting group {largest}")
        caps.append(cap)
    scal = _scalers(plan, flat, caps)
    torch.manual_seed(seed)

    base_stats = [_stats(flat["x0"][:, i]) for i in range(len(plan["base_features"]))]
    base_mean = np.array([m for m, _ in base_stats]).reshape(len(base_stats))
    base_std = np.array([s for _, s in base_stats]).reshape(len(base_stats))
    z0, statics = _statics(flat, plan, caps, scal, base_mean, base_std)
    sel = _statics(flat_sel, plan, caps, scal, base_mean, base_std) if flat_sel is not None else None
    nets, specs = [], []
    for k, level in enumerate(plan["levels"]):
        members = level["member_features"]
        net_cfg = level["network"]
        n_in = caps[k] * len(members) + len(level["context"])
        names_rel = net_cfg.get("relative_features") or []
        spec = make_spec(net_cfg["kind"], n_in, elements=caps[k], context=len(level["context"]),
                         pool=net_cfg["pool"], mask_feature=members.index("present"),
                         phi=net_cfg["phi"], rho=net_cfg["rho"], activation=net_cfg["activation"],
                         message=net_cfg.get("message") or [], rounds=int(net_cfg.get("rounds", 1)),
                         relative=[members.index(n) for n in names_rel],
                         aggregate=net_cfg.get("aggregate", "mean"))
        pm, ps = scal[k]["member"]["present"]
        nets.append(build_torch(spec, len(level["produced"]), (0.5 - pm) / ps))
        specs.append(spec)

    params = [p for net in nets for p in net.parameters()]
    optim = (torch.optim.AdamW(params, lr=lr, weight_decay=weight_decay) if weight_decay > 0
             else torch.optim.Adam(params, lr=lr))
    history = []
    best = {"loss": math.inf, "epoch": 0, "state": None, "per_level": []}
    for epoch in range(epochs):
        if lr_final_factor != 1.0:
            for group in optim.param_groups:
                group["lr"] = lr * lr_final_factor ** (epoch / max(1, epochs - 1))
        optim.zero_grad()
        losses = _forward(plan, nets, z0, statics)
        loss = sum(losses)
        loss.backward()
        optim.step()
        record = (epoch + 1) % max(1, epochs // 10) == 0
        if sel is not None and ((epoch + 1) % max(1, eval_every) == 0 or epoch + 1 == epochs):
            with torch.no_grad():
                sel_losses = _forward(plan, nets, *sel)
            sel_loss = float(sum(sel_losses)) if sel_losses else math.inf
            if sel_losses and sel_loss < best["loss"]:
                best = {"loss": sel_loss, "epoch": epoch + 1,
                        "state": [copy.deepcopy(net.state_dict()) for net in nets],
                        "per_level": [float(l) for l in sel_losses]}
        if record:
            entry = {"epoch": epoch + 1, "loss": float(loss.item()),
                     "per_level": [float(l.item()) for l in losses]}
            if sel is not None:
                entry["best_selection_loss"] = best["loss"]
            history.append(entry)
            if not quiet:
                print(f"  epoch {epoch + 1}/{epochs}  loss = {loss.item():.6f}"
                      + (f"  best selection = {best['loss']:.6f} @ {best['epoch']}" if sel is not None else ""))
    if best["state"] is not None:
        for net, state in zip(nets, best["state"]):
            net.load_state_dict(state)

    models = []
    for k, level in enumerate(plan["levels"]):
        cap = caps[k]
        sm = scal[k]["member"]
        xmean = [sm[f][0] for _ in range(cap) for f in level["member_features"]] + [m for m, _ in scal[k]["context"]]
        xstd = [sm[f][1] for _ in range(cap) for f in level["member_features"]] + [s for _, s in scal[k]["context"]]
        model = {
            "model": "generic_surrogate_v3",
            "input_features": _input_names(level, cap),
            "output_features": list(level["produced"]),
            "input_mean": [float(v) for v in xmean],
            "input_std": [float(v) for v in xstd],
            "output_mean": [float(scal[k]["encoded"][n][0]) for n in level["produced"]],
            "output_std": [float(scal[k]["encoded"][n][1]) for n in level["produced"]],
            "network": network_json(nets[k], specs[k]),
            "output_transforms": level["output_transforms"] + ["identity"] * len(level["latent_names"]),
            "group_lift": {
                "member_prefix": MEMBER_PREFIX, "member_features": list(level["member_features"]),
                "context_features": list(level["context"]), "grouping": level["grouping"],
                "latent_outputs": list(level["latent_names"]), "level": level["name"],
                "level_index": k, "levels": len(plan["levels"]),
            },
        }
        if level["grouping"] == "cell":
            model["group_lift"]["cell_size"] = float(level["cell_size"])
        if level["length"] > 0:
            model["group_lift"]["length"] = float(level["length"])
        if level.get("length_unit"):
            model["group_lift"]["length_unit"] = str(level["length_unit"])
        models.append(model)
    report = {"capacities": caps, "history": history, "epochs": epochs, "lr": lr, "seed": seed,
              "weight_decay": weight_decay, "training_samples": len(samples),
              "selection_samples": len(selection_samples),
              "selected_epoch": best["epoch"] if best["state"] is not None else epochs,
              "selection_loss": best["loss"] if best["state"] is not None else None,
              "selection_per_level": best["per_level"],
              "training_groups": [len(lv["idx"]) for lv in flat["levels"]]}
    return models, report


def chained_metrics(plan: dict, models: Sequence[dict], samples: Sequence[dict]):
    """Per-level metrics of the exported chain on `samples` (labels compared with predictions
    computed from the chain's own lower-level predictions), plus blocked-group counts."""
    import numpy as np

    from .train_surrogate import evaluate

    truth = [[] for _ in plan["levels"]]
    pred = [[] for _ in plan["levels"]]
    runs = [[] for _ in plan["levels"]]
    blocked = [0 for _ in plan["levels"]]
    groups = [0 for _ in plan["levels"]]
    for sample in samples:
        result = lift_np(sample, plan, models)
        for k, level in enumerate(plan["levels"]):
            r = result[k]
            groups[k] += len(r["keys"])
            blocked[k] += int((~r["valid"]).sum())
            targets = (sample.get("targets") or {}).get(level["name"]) or {}
            for g, key in enumerate(r["keys"]):
                label = targets.get(key)
                if label is None or not level["outputs"] or not r["valid"][g]:
                    continue
                truth[k].append([float(label[o]) for o in level["outputs"]])
                pred[k].append(r["features"][g, :len(level["outputs"])])
                runs[k].append(str(sample.get("run", "")))
    metrics = []
    for k, level in enumerate(plan["levels"]):
        if not level["outputs"] or not truth[k]:
            metrics.append(None)
            continue
        t, p = np.asarray(truth[k]), np.asarray(pred[k])
        metrics.append({"metrics": evaluate(t, p, level["outputs"]), "n": len(t), "truth": t,
                        "pred": p, "runs": runs[k]})
    return metrics, {"groups": groups, "blocked": blocked}


def finalize(plan: dict, models: List[dict], train_samples, holdout_samples,
             calibration_samples=(), *, coverage: float = 0.9, note: Optional[dict] = None,
             meta: Optional[dict] = None):
    """Attach the trust profile to every level: domain from the chain's own training inputs,
    holdout from held-out samples evaluated through the chain, optional run-level interval."""
    import numpy as np

    from .train_surrogate import calibration_interval, holdout_block, input_domain

    rows = [[] for _ in plan["levels"]]
    for sample in train_samples:
        for k, r in enumerate(lift_np(sample, plan, models, collect_rows=True)):
            if len(r["rows"]):
                rows[k].append(r["rows"])
    for k, model in enumerate(models):
        x = np.vstack(rows[k]) if rows[k] else np.zeros((0, len(model["input_features"])))
        scalers = (np.asarray(model["input_mean"]), np.asarray(model["input_std"]), None, None)
        model["input_domain"] = input_domain(x, scalers)
        if plan["levels"][k]["scale"]:
            model["trained_scale_bands"] = [plan["levels"][k]["scale"]]
    held, counts = chained_metrics(plan, models, holdout_samples)
    for k, model in enumerate(models):
        level = plan["levels"][k]
        model["trained_from"] = dict(meta or {}, level=level["name"],
                                     training_groups_blocked_on_holdout=counts["blocked"][k],
                                     holdout_groups=counts["groups"][k])
        if held[k] is not None:
            block = holdout_block(held[k]["metrics"], held[k]["n"])
            block["input_source"] = "chained_predictions"
            model["holdout"] = block
        if note:
            model["note"] = note
    if calibration_samples:
        cal, _ = chained_metrics(plan, models, calibration_samples)
        for k, model in enumerate(models):
            if cal[k] is None:
                continue
            names = sorted(set(cal[k]["runs"]))
            ids = np.asarray([names.index(r) for r in cal[k]["runs"]])
            model["prediction_interval"] = calibration_interval(
                cal[k]["truth"], cal[k]["pred"], plan["levels"][k]["outputs"], coverage, names, ids)
    return {"holdout": [None if h is None else {"metrics": h["metrics"], "n": h["n"]} for h in held],
            "holdout_groups": counts}


def write_models(models: Sequence[dict], out_dir: Path, plan: dict) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for level, model in zip(plan["levels"], models):
        path = out_dir / f"{level['name']}.json"
        path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plan", required=True, help="trech_group_hierarchy_plan_v1 JSON")
    parser.add_argument("--samples", required=True, nargs="+", help="training sample JSONL files")
    parser.add_argument("--holdout-samples", required=True, nargs="+",
                        help="held-out sample JSONL files (whole runs, never trained on)")
    parser.add_argument("--selection-samples", nargs="*", default=[],
                        help="optional runs for early stopping (disjoint from training and holdout)")
    parser.add_argument("--calibration-samples", nargs="*", default=[],
                        help="optional runs (disjoint from both) for a run-level conformal interval")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--epochs", type=int, default=1500)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--lr-final-factor", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--interval-coverage", type=float, default=0.9)
    parser.add_argument("--note", default="", help="free-form description carried in every model")
    parser.add_argument("--manifest", default="", help="optional report path")
    args = parser.parse_args(argv)

    plan = load_plan(json.loads(Path(args.plan).read_text(encoding="utf-8")))
    train_samples = read_samples(args.samples)
    holdout = read_samples(args.holdout_samples)
    calibration = read_samples(args.calibration_samples) if args.calibration_samples else []
    selection = read_samples(args.selection_samples) if args.selection_samples else []
    roles = {"training": train_samples, "selection": selection, "holdout": holdout, "calibration": calibration}
    seen: Dict[str, str] = {}
    for role, records in roles.items():
        for run in {s.get("run") for s in records} - {None, ""}:
            if run in seen and seen[run] != role:
                print(f"error: run {run!r} appears in {seen[run]} and {role} samples", file=sys.stderr)
                return 2
            seen[run] = role
    models, report = train(plan, train_samples, selection_samples=selection, epochs=args.epochs,
                           lr=args.lr, lr_final_factor=args.lr_final_factor, seed=args.seed,
                           weight_decay=args.weight_decay)
    meta = {"plan": Path(args.plan).name, "samples": [Path(p).name for p in args.samples],
            "holdout_samples": [Path(p).name for p in args.holdout_samples],
            "seed": args.seed, "epochs": args.epochs, "trainer": "trech_torch.hierarchy"}
    note = {"description": args.note} if args.note else None
    summary = finalize(plan, models, train_samples, holdout, calibration,
                       coverage=args.interval_coverage, note=note, meta=meta)
    paths = write_models(models, Path(args.out_dir), plan)
    manifest = {"schema": "trech_group_hierarchy_manifest_v1", "plan": plan,
                "models": [str(p) for p in paths], "training": report, **summary}
    if args.manifest:
        Path(args.manifest).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for level, h in zip(plan["levels"], summary["holdout"]):
        if h is None:
            print(f"  {level['name']}: latent only (no held-out labels)")
        else:
            r2 = min(m["r2"] for m in h["metrics"].values())
            print(f"  {level['name']}: held-out R2min {r2:.4f} over {h['n']} groups (chained inputs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
