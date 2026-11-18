"""NumPy reference for the live LibTorch projected-gap detector."""
import numpy as np


def best_split(projections, minimum, best, minimum_fraction=0.12):
    for values, normal, origin in projections:
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
        for index in np.flatnonzero(candidates > max(threshold, best[0] + 1e-12)):
            if candidates[index] > best[0] + 1e-12:
                cut = int(index) + minimum
                midpoint = values[order[cut - 1]] + spacings[cut - 1] / 2
                best = candidates[index], order, cut, (normal, origin, midpoint)
    return best


def numpy_domains(values, parents, minimum=16, depth=3, *, leaf_rules=None):
    """Partition finite rows; optionally retain each leaf's fit-time decision planes."""
    assignment = np.full(len(values), -1, dtype=int)
    groups = []

    def walk(rows, parent, path, rules):
        if len(path) < depth and len(rows) >= 2 * minimum:
            data = values[rows]
            active = np.flatnonzero(data.min(axis=0) != data.max(axis=0))
            varied = data[:, active]
            best = (0.0, None, 0, None)
            axes = np.eye(values.shape[1])[active]
            if len(active):
                best = best_split(zip(varied.T, axes, [np.zeros(values.shape[1])] * len(active)),
                                  minimum, best)
            if len(active) >= 2:
                origin = data.mean(axis=0)
                std = varied.std(axis=0)
                scaled = (varied - origin[active]) / std
                strengths, directions = np.linalg.eigh(scaled.T @ scaled / len(rows))
                tolerance = strengths[-1] * 1e-10
                def projection(direction):
                    return scaled @ direction, (direction / std) @ axes, origin
                components = []
                for i in range(len(strengths) - 1, -1, -1):
                    strength = strengths[i]
                    if strength <= tolerance or np.count_nonzero(abs(strengths - strength) <= tolerance) > 1:
                        continue
                    direction = directions[:, i]
                    sign = np.sign(direction[np.flatnonzero(abs(direction) > 1e-10)[0]])
                    components.append(projection(sign * direction))
                best = best_split(components, minimum, best)
                if best[1] is None:
                    unit = np.eye(len(active))
                    diagonals = (projection(unit[i] + sign * unit[j])
                                 for i in range(len(active)) for j in range(i + 1, len(active))
                                 for sign in (1, -1))
                    best = best_split(diagonals, minimum, best, minimum_fraction=0.20)
            _, order, cut, rule = best
            if order is not None:
                walk(rows[order[:cut]], parent, path + "0", [*rules, (*rule, False)])
                walk(rows[order[cut:]], parent, path + "1", [*rules, (*rule, True)])
                return
        assignment[rows] = len(groups)
        groups.append(dict(parent=parent, path=path, elements=len(rows)))
        if leaf_rules is not None:
            leaf_rules.append(rules)

    finite = np.isfinite(values).all(axis=1)
    parents = np.asarray(parents)
    for parent in sorted(set(parents[finite])):
        rows = np.flatnonzero(finite & (parents == parent))
        walk(rows[np.lexsort(values[rows].T[::-1])], parent, "", [])
    return groups, assignment


def numpy_density_domains(values, parents, minimum=16, depth=3, *, shared_distance_scale=False):
    """Replay the exact symmetric neighborhood graph independently of LibTorch."""
    assignment = np.full(len(values), -1, dtype=int)
    groups = []
    finite = np.isfinite(values).all(axis=1)
    parents = np.asarray(parents)
    for parent in sorted(set(parents[finite])):
        rows = np.flatnonzero(finite & (parents == parent))
        rows = rows[np.lexsort(values[rows].T[::-1])]
        components = [(rows, "")]
        if depth and len(rows) >= 2 * minimum:
            data = values[rows]
            magnitude = np.abs(data).max(0)
            if shared_distance_scale:
                magnitude = magnitude.max()
            data = data / np.where(magnitude > 0, magnitude, 1)
            centered = data - data.mean(0)
            spread = centered.std(0)
            if shared_distance_scale:
                spread = spread.max()
            z = centered / np.where(spread > 0, spread, 1)
            distances = np.empty((len(rows), len(rows)))
            for start in range(0, len(rows), 64):
                distances[start:start + 64] = np.linalg.norm(
                    z[start:start + 64, None, :] - z[None, :, :], axis=-1)
            k = min(6, minimum - 1)
            radius = np.partition(distances, k, axis=1)[:, k]
            edges = distances <= 1.15 * np.minimum(radius[:, None], radius[None, :]) + 1e-12
            seen = np.zeros(len(rows), dtype=bool)
            accepted, residual = [], []
            for start in range(len(rows)):
                if seen[start]:
                    continue
                queue = [start]
                seen[start] = True
                for node in queue:
                    neighbors = np.flatnonzero(edges[node] & ~seen)
                    seen[neighbors] = True
                    queue.extend(neighbors.tolist())
                if len(queue) >= minimum:
                    accepted.append((rows[queue], f"n{len(accepted)}"))
                else:
                    residual.extend(queue)
            if 2 <= len(accepted) <= 2**depth and len(residual) <= len(rows) // 10:
                components = accepted + ([(rows[residual], "u")] if residual else [])
        for members, path in components:
            assignment[members] = len(groups)
            groups.append(dict(parent=parent, path=path, elements=len(members)))
    return groups, assignment
