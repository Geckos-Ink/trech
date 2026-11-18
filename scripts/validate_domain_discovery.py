#!/usr/bin/env python3
"""Compare live domain membership with NumPy and paired scenario runs."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/torch"))
from trech_torch.domain_partition import numpy_density_domains, numpy_domains


def hook_rows(run: Path):
    with (run / "trech_hook_emits.jsonl").open() as stream:
        return [(line, json.loads(line)) for line in stream]


def lineage(groups, assignment, previous, next_id):
    """Reconcile real parcel memberships from successive diagnostic frames."""
    current = np.full(len(assignment), -1, dtype=int)
    before, prior_ids = previous
    known = {group["id"]: group for group in before}
    tracked = []
    for j, group in enumerate(groups):
        mask = assignment == j
        contributors = Counter(prior_ids[mask & (prior_ids >= 0)]) if group["path"] != "u" else {}
        domain_id = None
        if group["path"] != "u":
            for old, count in contributors.items():
                source = known[old]
                if source["parent"] == group["parent"] and 2 * count > max(group["elements"], source["elements"]):
                    domain_id = int(old)
            if domain_id is None:
                domain_id, next_id = next_id, next_id + 1
            current[mask] = domain_id
        tracked.append(dict(group, id=domain_id,
                            predecessors=[{"id": int(k), "elements": int(count)}
                                          for k, count in sorted(contributors.items())]))
    return (tracked, current), next_id


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
    component_count_matches = supported_component_count_matches = 0
    initial_droplets_recovered = None
    tracked = None
    next_id = continued_domains = merges = splits = 0
    methods = {row.get("method", "projected") for row in reports}
    if len(methods) != 1 or not methods <= {"projected", "density"}:
        raise ValueError(f"{family}: unknown or inconsistent detection methods")
    method = methods.pop()
    detect = numpy_density_domains if method == "density" else numpy_domains
    for row, frame in zip(reports, frames):
        if family == "glass":
            facts = row["features"]
            data = np.column_stack([facts[name] for name in sorted(facts)])
            parents = row["parents"]
        else:
            data = np.asarray(frame["positions_mm"])
            parents = [""] * len(data)
        kwargs = {"shared_distance_scale": row.get("shared_distance_scale", False)} if method == "density" else {}
        groups, reference = detect(data, parents, **kwargs)
        actual = np.asarray(row["report"]["elementGroups"])
        if row["report"]["groups"] != groups or not np.array_equal(actual, reference):
            raise ValueError(f"{family}: NumPy membership or groups differ at frame {row['frame']}")
        if "lineage" in row:
            if tracked is None:
                tracked = [], np.full(len(actual), -1, dtype=int)
            tracked, next_id = lineage(groups, actual, tracked, next_id)
            expected = [{k: g[k] for k in ("id", "predecessors")} for g in tracked[0]]
            if row["lineage"] != expected:
                raise ValueError(f"{family}: lineage differs at frame {row['frame']}")
            links = Counter(edge["id"] for domain in expected for edge in domain["predecessors"])
            continued_domains += sum(domain["id"] in {p["id"] for p in domain["predecessors"]}
                                     for domain in expected)
            merges += sum(len(domain["predecessors"]) > 1 for domain in expected)
            splits += sum(count > 1 for count in links.values())
        group_counts[len(groups)] += 1
        element_count += len(data)
        subdivided_frames += len(groups) > len(set(parents))
        if family == "lava":
            expected = frame["counts"]["connected_components"]
            component_count_matches += len(groups) == expected
            supported_component_count_matches += sum(g["path"] != "u" for g in groups) == expected
        if family == "lava" and row["frame"] == 0:
            # The standard scenario starts with four equally populated droplets.
            expected = [set(chunk) for chunk in np.array_split(actual, 4)]
            initial_droplets_recovered = len(groups) == 4 and all(len(chunk) == 1 for chunk in expected)
            if not initial_droplets_recovered:
                raise ValueError("lava: failed to recover the four starting droplets")
    if subdivided_frames == 0 or len(group_counts) < 2:
        raise ValueError(f"{family}: expected changing statistical subdivisions")
    return {
        "method": method, "frames": len(reports), "elements": element_count, "subdivided_frames": subdivided_frames,
        "domain_counts": dict(sorted(group_counts.items())),
        "ordinary_hook_emits_byte_identical": True,
        **({"lineage": {"ids_assigned": next_id, "continued_across_frames": continued_domains,
                        "merge_groups": merges, "split_groups": splits}} if tracked is not None else {}),
        **({"initial_droplets_recovered": initial_droplets_recovered,
            "spatial_component_count_matches": component_count_matches,
            "spatial_supported_count_matches": supported_component_count_matches} if family == "lava" else {}),
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
