#!/usr/bin/env python3
"""Compare live domain membership with NumPy and paired scenario runs."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np


def hook_rows(run: Path):
    with (run / "trech_hook_emits.jsonl").open() as stream:
        return [(line, json.loads(line)) for line in stream]


def best_split(projections, minimum, best, minimum_fraction=0.12):
    for values in projections:
        order = np.argsort(values, kind="stable")
        spacings = np.diff(values[order])
        span = np.ptp(values)
        if span == 0.0:
            continue
        gaps = spacings / span
        distinct = np.sort(gaps[gaps > 1e-12])
        if not distinct.size:
            continue
        threshold = max(minimum_fraction, 2 * np.log(order.size) / (order.size - 1))
        if distinct.size > 1:
            threshold = max(threshold, 3 * distinct[(distinct.size - 1) // 2])
        candidates = gaps[minimum - 1 : order.size - minimum]
        for cut in np.flatnonzero(candidates > max(threshold, best[0] + 1e-12)):
            if candidates[cut] > best[0] + 1e-12:
                best = candidates[cut], order, int(cut) + minimum
    return best


def numpy_domains(values, parents, minimum=16, depth=3):
    """Reference implementation using NumPy covariance, eigensolver and sorting."""
    assignment = np.full(len(values), -1, dtype=int)
    groups = []

    def walk(rows, parent, path):
        if len(path) < depth and len(rows) >= 2 * minimum:
            data = values[rows]
            lo, hi = data.min(axis=0), data.max(axis=0)
            varied = data[:, lo != hi]
            best = (0.0, None, 0)
            if varied.shape[1]:
                best = best_split(varied.T, minimum, best)
            if varied.shape[1] >= 2:
                centered = varied - varied.mean(axis=0)
                scaled = centered / centered.std(axis=0)
                strengths, directions = np.linalg.eigh(scaled.T @ scaled / len(rows))
                tolerance = strengths[-1] * 1e-10
                components = []
                for i in range(len(strengths) - 1, -1, -1):
                    strength = strengths[i]
                    if strength <= tolerance or np.count_nonzero(abs(strengths - strength) <= tolerance) > 1:
                        continue
                    direction = directions[:, i]
                    sign = np.sign(direction[np.flatnonzero(abs(direction) > 1e-10)[0]])
                    components.append(scaled @ (sign * direction))
                best = best_split(components, minimum, best)
                if best[1] is None:
                    diagonals = (scaled[:, i] + sign * scaled[:, j]
                                 for i in range(scaled.shape[1])
                                 for j in range(i + 1, scaled.shape[1]) for sign in (1, -1))
                    best = best_split(diagonals, minimum, best, minimum_fraction=0.20)
            _, order, cut = best
            if order is not None:
                walk(rows[order[:cut]], parent, path + "0")
                walk(rows[order[cut:]], parent, path + "1")
                return
        assignment[rows] = len(groups)
        groups.append(dict(parent=parent, path=path, elements=len(rows)))

    finite = np.isfinite(values).all(axis=1)
    parents = np.asarray(parents)
    for parent in sorted(set(parents[finite])):
        rows = np.flatnonzero(finite & (parents == parent))
        walk(rows[np.lexsort(values[rows].T[::-1])], parent, "")
    return groups, assignment


def verify(live: Path, baseline: Path, family: str) -> dict:
    recorded = hook_rows(live)
    paired = hook_rows(baseline)
    comparison = [line for line, event in recorded if event["tag"] != "domain_discovery"]
    if comparison != [line for line, _ in paired]:
        raise ValueError(f"{family}: ordinary hook emits differ from the paired run")
    frames = [event["payload"] for _, event in recorded if event["tag"] == "material_frame"]
    reports = [event["payload"] for _, event in recorded if event["tag"] == "domain_discovery"]
    first_frame = int(family == "glass")
    if not frames or [row["frame"] for row in reports] != list(range(first_frame, len(frames) + first_frame)):
        raise ValueError(f"{family}: missing, duplicate, or out-of-order reports")
    group_counts = Counter()
    element_count = 0
    subdivided_frames = 0
    component_count_matches = 0
    initial_droplets_recovered = None
    for row, frame in zip(reports, frames):
        if family == "glass":
            facts = row["features"]
            data = np.column_stack([facts[name] for name in sorted(facts)])
            parents = row["parents"]
        else:
            data = np.asarray(frame["positions_mm"])
            parents = [""] * len(data)
        groups, reference = numpy_domains(data, parents)
        actual = np.asarray(row["report"]["elementGroups"])
        if row["report"]["groups"] != groups or not np.array_equal(actual, reference):
            raise ValueError(f"{family}: NumPy membership or groups differ at frame {row['frame']}")
        group_counts[len(groups)] += 1
        element_count += len(data)
        subdivided_frames += len(groups) > len(set(parents))
        if family == "lava":
            component_count_matches += len(groups) == frame["counts"]["connected_components"]
        if family == "lava" and row["frame"] == 0:
            # The standard scenario starts with four equally populated droplets.
            expected = [set(chunk) for chunk in np.array_split(actual, 4)]
            initial_droplets_recovered = len(groups) == 4 and all(len(chunk) == 1 for chunk in expected)
            if not initial_droplets_recovered:
                raise ValueError("lava: failed to recover the four starting droplets")
    if subdivided_frames == 0 or len(group_counts) < 2:
        raise ValueError(f"{family}: expected changing statistical subdivisions")
    return {
        "frames": len(reports), "elements": element_count, "subdivided_frames": subdivided_frames,
        "domain_counts": dict(sorted(group_counts.items())),
        "ordinary_hook_emits_byte_identical": True,
        **({"initial_droplets_recovered": initial_droplets_recovered,
            "spatial_component_count_matches": component_count_matches} if family == "lava" else {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glass", type=Path, nargs=2, metavar=("LIVE", "BASELINE"), required=True)
    parser.add_argument("--lava", type=Path, nargs=2, metavar=("LIVE", "BASELINE"), required=True)
    args = parser.parse_args()
    print(json.dumps({family: verify(*getattr(args, family), family) for family in ("glass", "lava")},
                     indent=2))


if __name__ == "__main__":
    main()
