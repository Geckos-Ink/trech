"""Full media inventory, fresh engine runs, both viewers, atomic promotion and audit report."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/viz/demos"))
sys.path.insert(0, str(ROOT / "studio"))
import render_readme_3d as classic
from trech_studio.engine.outputs import load_run_result
from PIL import Image


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(args, log, env=None):
    with Path(log).open("w") as handle:
        completed = subprocess.run([str(a) for a in args], cwd=ROOT, env=env,
                                   stdout=handle, stderr=subprocess.STDOUT)
    if completed.returncode:
        raise RuntimeError(f"exit {completed.returncode}; see {log}")


def promote(source, target):
    source = Path(source)
    if source.suffix.lower() in (".gif", ".png"):
        with Image.open(source) as rendered:
            for frame in range(getattr(rendered, "n_frames", 1)):
                rendered.seek(frame)
                rendered.load()
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".refresh_tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(target)
    return {"path": str(target.relative_to(ROOT)), "sha256": sha(target), "bytes": target.stat().st_size}


def portable(value):
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [portable(v) for v in value]
    if isinstance(value, str):
        return value.replace(str(ROOT) + "/", "")
    return value


def intact(entry):
    return entry.get("status") in ("ok", "static_geometry") and bool(entry.get("assets")) and all(
        (ROOT / item["path"]).is_file() and sha(ROOT / item["path"]) == item["sha256"]
        for item in entry["assets"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--only", nargs="+", help="scenario stems or classic capture keys")
    parser.add_argument("--resume", type=Path, help="reuse this refresh session, with matching source identity")
    args = parser.parse_args()
    scenarios = [p for p in sorted((ROOT / "examples/scenarios").glob("*/*.js"))
                 if p.stem == p.parent.name]
    wanted = set(args.only or [])
    available = {p.stem for p in scenarios} | {c.key for c in classic.CAPTURES}
    if wanted - available:
        parser.error("Unknown names: " + ", ".join(sorted(wanted - available)))
    if args.list:
        print("Classic authored captures:")
        for cap in classic.CAPTURES:
            print(f"  {cap.key}: {cap.gif}" + (" [slow]" if cap.slow else ""))
        print("Studio scenario inventory (helpers and intentional syntax-error fixtures excluded):")
        print("\n".join("  " + p.stem for p in scenarios))
        return 0
    engine = Path(os.environ["TRECH_BIN"]).resolve()
    # Preserve venv symlinks: resolving bin/python to its base interpreter loses packages.
    studio_python = Path(os.path.abspath(os.environ["STUDIO_PY"]))
    if not engine.is_file() or not studio_python.is_file():
        parser.error("TRECH_BIN and STUDIO_PY must name installed executables")
    command([studio_python, "-c", "import PySide6, wgpu, rendercanvas"], ROOT / "build/media_preflight.log")
    command([shutil.which("ffmpeg") or "ffmpeg", "-version"], ROOT / "build/media_ffmpeg.log")
    sessions = ROOT / "build/media_refresh"
    sessions.mkdir(parents=True, exist_ok=True)
    session = args.resume.resolve() if args.resume else Path(tempfile.mkdtemp(prefix=time.strftime("%Y%m%d_%H%M%S_"), dir=sessions))
    session.mkdir(parents=True, exist_ok=True)
    run_root = session / "runs"
    run_root.mkdir(exist_ok=True)
    stage = session / "stage"
    stage.mkdir(exist_ok=True)
    source_files = sorted((ROOT / "examples/scenarios").glob("*/*.js")) + sorted((ROOT / "js").glob("*.js")) + [engine]
    identity = hashlib.sha256("".join(sha(p) for p in source_files).encode()).hexdigest()
    report_path = session / "manifest.json"
    report = json.loads(report_path.read_text()) if args.resume and report_path.exists() else {
        "schema": "trech_media_refresh_v1", "source_identity": identity,
        "engine_sha256": sha(engine), "classic": {}, "studio": {}, "exclusions":
        "trech_*.js are libraries; include_error_*.js are intentional failure fixtures; native window screenshots are historical captures and are never synthesized"}
    if report["source_identity"] != identity:
        parser.error("Resume source identity differs; start a fresh refresh")
    data_identity = hashlib.sha256("".join(sha(p) for p in sorted((ROOT / "data").rglob("*")) if p.is_file()).encode()).hexdigest()
    if report.get("data_identity", data_identity) != data_identity:
        parser.error("Model/data identity differs; start a fresh refresh")
    report["data_identity"] = data_identity
    report["inventory"] = {"classic_capture_keys": [c.key for c in classic.CAPTURES],
                           "studio_scenarios": [p.stem for p in scenarios],
                           "selection": sorted(wanted) if wanted else "all"}
    def save():
        for group in ("classic", "studio"):
            for entry in report[group].values():
                entry.setdefault("source_identity", identity)
                entry.setdefault("refresh_session", str(session.relative_to(ROOT)) if session.is_relative_to(ROOT) else str(session))
        pending = report_path.with_suffix(".pending")
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.replace(report_path)
    report["renderer_source_sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in
        [ROOT / "tools/viz/demos/render_readme_3d.py", ROOT / "studio/trech_studio/capture.py", Path(__file__)]}
    save()
    print(f"Refresh session: {session}", flush=True)
    classic.DEMOS = stage / "classic"
    classic.DEMOS.mkdir(exist_ok=True)
    ctx = classic.Context(engine, sys.executable, run_root, ROOT / "build/pubchem_cache", bool(args.resume))
    done_runs, by_scenario = set(), {}
    for cap in classic.CAPTURES:
        for run in cap.runs:
            by_scenario.setdefault(run[1], run_root / run[0])
        if wanted and cap.key not in wanted and not any(Path(r[1]).stem in wanted for r in cap.runs):
            continue
        if intact(report["classic"].get(cap.key, {})):
            print(f"[classic] {cap.key}: resumed", flush=True)
            continue
        print(f"[classic] {cap.key}: run + render (slow={cap.slow})", flush=True)
        try:
            if cap.custom:
                cap.custom(ctx, cap)
            else:
                for run in cap.runs:
                    if run[0] not in done_runs:
                        classic.run_scenario(ctx, run[0], run[1], run[2:])
                        done_runs.add(run[0])
                classic.render(ctx, cap, classic.expand(cap.render, ctx))
            gif = classic.DEMOS / cap.gif
            image = Image.open(gif)
            image.seek(image.n_frames - 1)
            png = gif.with_suffix(".png")
            image.convert("RGB").save(png)
            assets = [promote(p, ROOT / "tools/viz/demos" / p.name) for p in (gif, png)]
            report["classic"][cap.key] = {"status": "ok", "assets": assets,
                "source_runs": cap.runs, "render_log": str(run_root / (cap.key + ".render.log"))}
        except (Exception, SystemExit) as error:
            report["classic"][cap.key] = {"status": "failed", "error": str(error)}
            print(f"  FAILED: {error}", flush=True)
        save()
    # Generic Studio capture consumes the same fresh runs where available; never rerun slow MD twice.
    env = dict(os.environ, PYTHONPATH=str(ROOT / "studio"), QT_QPA_PLATFORM="offscreen",
               TRECH_PUBCHEM_CACHE_DIR=str(ROOT / "build/pubchem_cache"))
    refs = {"viz_refraction_demo": "viz_refraction", "validation_glass_of_water": "validation_gow",
            "glass_of_water_shaken": "glass_shaken", "beaker_water_n_pentane_studio": "beaker_water_pentane",
            "lava_lamp": "lava_lamp", "nacl_dehydration_reference": "nacl_dehydration", "aerodynamics_reference": "aerodynamics"}
    output = ROOT / "studio/previews"
    for script in scenarios:
        key = script.stem
        if wanted and key not in wanted and not any(c.key in wanted and any(r[1] == script.name for r in c.runs) for c in classic.CAPTURES):
            continue
        if intact(report["studio"].get(key, {})):
            continue
        print(f"[studio] {key}: inspect / run / render", flush=True)
        try:
            inspection_file = session / (key + ".inspect.log")
            command([engine, "inspect", script], inspection_file, env)
            inspection = json.loads(inspection_file.read_text())
            run = by_scenario.get(script.name)
            if not run or not (run / "trech_scores.jsonl").is_file():
                run = run_root / ("studio_" + key)
                if not args.resume or not (run / "trech_scores.jsonl").is_file():
                    # A unique session avoids append-mode JSONL contamination.
                    if run.exists(): shutil.rmtree(run)
                    command([engine, "run", script, "--viz", "--output", run], session / (key + ".run.log"), env)
            result = load_run_result(run)
            scores = result.run_end_scores()
            if not scores:
                raise RuntimeError("Run has no completed run_end scores; refusing incomplete media")
            if scores.get("hook_emit_dropped_count", 0):
                raise RuntimeError("Run dropped emits; refusing to promote an incomplete animation")
            has_frames = any(e.tag in ("material_frame", "fluid_frame", "quantum_frame", "chemistry_nuclear_ensemble") for e in result.emits)
            has_tracks = bool(result.load_trajectories(limit=1))
            if not has_frames and not has_tracks:
                blocked = [e.payload for e in result.emits if e.tag == "process_recipe_state"]
                assets = []
                if not blocked:
                    prefix = stage / key
                    command([studio_python, "-m", "trech_studio.capture", "--run", run, "--out", prefix,
                             "--width", "360", "--height", "240", "--still", "--supersample", "1"],
                            session / (key + ".capture.log"), env)
                    assets = [promote(prefix.with_suffix(s), output / (key + s)) for s in (".png", ".json")]
                report["studio"][key] = {"status": "blocked_no_models" if blocked else "static_geometry", "run": str(run),
                    "reason": "Missing process models; no spatial output fabricated" if blocked else "Static recorded Geant4 geometry; no motion/GIF fabricated",
                    "assets": assets, "emit_tags": result.emit_tags()}
                save()
                continue
            prefix = stage / key
            command([studio_python, "-m", "trech_studio.capture", "--run", run, "--out", prefix,
                     "--width", "360", "--height", "240", "--seconds", "4", "--fps", "10",
                     "--orbit", "0", "--supersample", "1", "--annotations", "--label", key],
                    session / (key + ".capture.log"), env)
            if not prefix.with_suffix(".gif").is_file():
                raise RuntimeError("Capture did not create GIF")
            metadata_file = prefix.with_suffix(".json")
            metadata_file.write_text(json.dumps(portable(json.loads(metadata_file.read_text())), indent=2) + "\n")
            assets = [promote(prefix.with_suffix(s), output / (key + s)) for s in (".png", ".gif", ".json")]
            report["studio"][key] = {"status": "ok", "run": str(run), "assets": assets,
                                      "config_hash": (result.run_start_provenance() or {}).get("config_hash")}
        except (Exception, SystemExit) as error:
            report["studio"][key] = {"status": "failed", "error": str(error)}
            print(f"  FAILED: {error}", flush=True)
        save()
    # Curated references retain their authored aspect ratio and timeline cadence.
    report.setdefault("references", {})
    for key, name in refs.items():
        entry = report["studio"].get(key, {})
        if entry.get("status") != "ok":
            continue
        if wanted and key not in wanted and not any(c.key in wanted and any(r[1] == key + ".js" for r in c.runs) for c in classic.CAPTURES):
            continue
        if intact(report["references"].get(name, {})):
            continue
        print(f"[reference] {name}: preserve authored cadence", flush=True)
        try:
            run = Path(entry["run"])
            if name == "lava_lamp":
                run = run_root / "lava_lamp"
                classic.run_scenario(ctx, "lava_lamp", "lava_lamp.js", ("--param", "duration_s=600", "--param", "simulation_ticks=100"))
            diagnostic = name in ("nacl_dehydration", "aerodynamics")
            width, height, seconds, fps = ((260, 360, 10, 10) if name == "lava_lamp" else
                (360, 240, 4, 10) if diagnostic else (360, 260, 4, 12))
            target = stage / (name + "_reference.gif")
            command([studio_python, "-m", "trech_studio.capture", "--run", run, "--reference", target,
                     "--width", str(width), "--height", str(height), "--seconds", str(seconds), "--fps", str(fps),
                     "--orbit", "0" if diagnostic else "30", "--supersample", "1" if diagnostic else "2"]
                    + (["--annotations"] if diagnostic else []), session / (name + ".reference.log"), env)
            metadata = json.loads(target.with_suffix(".json").read_text())
            metadata["artifacts"] = [name + ".gif"]
            target.with_suffix(".json").write_text(json.dumps(portable(metadata), indent=2) + "\n")
            assets = [promote(target.with_suffix(suffix), ROOT / "studio/tests/reference" / (name + suffix))
                      for suffix in (".gif", ".json")]
            report["references"][name] = {"status": "ok", "run": str(run), "assets": assets}
        except (Exception, SystemExit) as error:
            report["references"][name] = {"status": "failed", "error": str(error)}
            print(f"  FAILED: {error}", flush=True)
        save()
    # Metadata uses repository-relative paths so committed previews are portable.
    for group in ("studio", "references"):
        for entry in report[group].values():
            for item in entry.get("assets", []):
                asset = ROOT / item["path"]
                if asset.suffix == ".json":
                    asset.write_text(json.dumps(portable(json.loads(asset.read_text())), indent=2) + "\n")
                    item.update(sha256=sha(asset), bytes=asset.stat().st_size)
    # Preserve historical native screenshots, updating only explicitly refreshed reference assets.
    linked_path = ROOT / "docs/images/studio-processes/manifest.json"
    linked = json.loads(linked_path.read_text())
    for path, item in linked["media"].items():
        if not path.startswith("studio/tests/reference/"):
            continue
        asset = ROOT / path
        item.update(sha256=sha(asset), bytes=asset.stat().st_size)
        item["refresh_manifest"] = "studio/previews/manifest.json"
        if asset.suffix == ".gif":
            with Image.open(asset) as image:
                duration = 0
                for frame in range(image.n_frames):
                    image.seek(frame)
                    duration += image.info.get("duration", 0)
                item.update(dimensions=list(image.size), frames=image.n_frames, duration_ms=duration)
    linked_path.write_text(json.dumps(linked, indent=2) + "\n")
    output.mkdir(exist_ok=True)
    report["summary"] = {group: {status: sum(e["status"] == status for e in report[group].values())
        for status in sorted({e["status"] for e in report[group].values()})} for group in ("classic", "studio")}
    save()
    published = json.loads((output / "manifest.json").read_text()) if (output / "manifest.json").exists() else {}
    # Scoped refreshes must not hide previously published experiment previews.
    for group in ("classic", "studio"):
        previous = published.get(group, {})
        previous.update(report[group])
        published[group] = previous
    published.update({key: portable(value) for key, value in report.items() if key not in ("classic", "studio")})
    rows = ["# Studio experiment previews", "", "Generated by `scripts/update_experiment_media.sh`. Recorded data only; unsupported motion is listed explicitly.", "",
            "These are viewer replays, not new physical validation. NaCl trays are inventory diagnostics; the airflow reference is a 2D Euler slice. Process recipes with missing models have no fabricated spatial animation.", "",
            "| Experiment | State | Preview |", "| --- | --- | --- |"]
    for key, entry in sorted(published["studio"].items()):
        preview = f"[image]({key}.png) · [GIF]({key}.gif)" if entry["status"] == "ok" else (
            f"[static image]({key}.png)" if entry["status"] == "static_geometry" else entry.get("reason", entry.get("error", "")))
        rows.append(f"| {key} | {entry['status']} | {preview.replace('|', '/')} |")
    (output / "README.md").write_text("\n".join(rows) + "\n")
    (output / "manifest.json").write_text(json.dumps(portable(published), indent=2) + "\n")
    engine_rows = ["# Engine media refresh index", "", "Generated by `scripts/update_experiment_media.sh`; PNGs are final frames of the same recorded-data GIFs.", "",
                   "| Capture | Status | Media |", "| --- | --- | --- |"]
    for key, entry in sorted(published["classic"].items()):
        links = " · ".join(f"[{Path(a['path']).suffix[1:]}]({Path(a['path']).name})" for a in entry.get("assets", []))
        engine_rows.append(f"| {key} | {entry['status']} | {links or entry.get('error', '').replace('|', '/')} |")
    (ROOT / "tools/viz/demos/media_index.md").write_text("\n".join(engine_rows) + "\n")
    (ROOT / "tools/viz/demos/media_manifest.json").write_text(json.dumps(portable({
        "schema": report["schema"], "source_identity": identity,
        "classic": published["classic"]}), indent=2) + "\n")
    failed = [(group, key) for group in ("classic", "studio", "references") for key, e in report[group].items() if e["status"] == "failed"]
    print(f"Finished: {report_path}; failures={failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
