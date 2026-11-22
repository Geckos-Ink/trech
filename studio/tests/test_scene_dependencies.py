"""Multi-file scene export: volume hierarchy order and digest-verified model dependencies."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_scene_writer import recorded_scene  # noqa: E402
from trech_studio.engine.outputs import load_run_result  # noqa: E402
from trech_studio.scene.dependencies import (  # noqa: E402
    package_dependencies, recorded_dependencies, run_search_dirs)
from trech_studio.scene.loader import scene_from_output_dir, scene_from_viz_data  # noqa: E402
from trech_studio.scene.model import Shape, VolumeNode  # noqa: E402
from trech_studio.scene.writer import scene_to_bundle, scene_to_config, scene_to_js  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def nested_scene():
    """``sample`` (world) holds ``insert``; ``probe`` is a later world-level volume."""
    scene, config = recorded_scene()
    base = config["geometry"]["volumes"][0]
    config["geometry"]["volumes"] += [
        {**deepcopy(base), "name": "insert", "placement": {"parent": "sample"}},
        {**deepcopy(base), "name": "probe", "placement": {"positionMm": [40., 0., 0.]}},
    ]
    raw_base = scene.raw["volumes"][0]
    scene.raw["volumes"] += [
        {**deepcopy(raw_base), "name": "insert", "parent": "sample", "rotation_deg": [0., 0., 0.]},
        {**deepcopy(raw_base), "name": "probe", "position_mm": [40., 0., 0.],
         "rotation_deg": [0., 0., 0.]},
    ]
    return scene_from_viz_data(scene.raw), config


def names(config):
    return [v["name"] for v in config["geometry"]["volumes"]]


def test_unchanged_hierarchy_keeps_authored_order_and_exact_config():
    scene, config = nested_scene()
    assert scene_to_config(scene, config) == config


def test_reparenting_to_a_later_volume_moves_only_the_child_after_its_parent():
    scene, config = nested_scene()
    scene.volumes[0].parent = "probe"      # sample now nests in the later probe
    result = scene_to_config(scene, config)
    assert names(result) == ["probe", "sample", "insert"]
    assert result["geometry"]["volumes"][1]["placement"]["parent"] == "probe"
    assert result["geometry"]["volumes"][0] == config["geometry"]["volumes"][2]


def test_unknown_parents_and_cycles_are_rejected_instead_of_falling_back_to_world():
    scene, config = nested_scene()
    scene.volumes[1].parent = "missing"
    with pytest.raises(ValueError, match="parent missing is not a volume"):
        scene_to_config(scene, config)
    scene, config = nested_scene()
    scene.volumes[0].parent = "insert"     # sample <-> insert
    with pytest.raises(ValueError, match="cycle"):
        scene_to_config(scene, config)
    scene, config = nested_scene()
    scene.volumes[2].parent = "PROBE"      # a volume cannot hold itself (names ignore case)
    with pytest.raises(ValueError, match="cycle"):
        scene_to_config(scene, config)


def test_recorded_forward_parent_is_refused_because_the_run_used_the_world_fallback():
    scene, config = nested_scene()
    volumes = config["geometry"]["volumes"]
    volumes[0], volumes[1] = volumes[1], volumes[0]   # insert declared before sample
    scene.raw["volumes"][0], scene.raw["volumes"][1] = scene.raw["volumes"][1], scene.raw["volumes"][0]
    scene = scene_from_viz_data(scene.raw)
    with pytest.raises(ValueError, match="declared after it"):
        scene_to_config(scene, config)


def test_new_nested_primitive_is_written_after_its_parent():
    scene, config = nested_scene()
    scene.volumes.insert(0, VolumeNode(name="core", material="G4_WATER", parent="insert",
                                       shape=Shape(type="box", size_mm=(1., 1., 1.))))
    assert names(scene_to_config(scene, config)) == ["sample", "insert", "core", "probe"]


# --- model dependencies --------------------------------------------------------------------

def write_model(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


def dependency_config(tmp_path):
    shared = write_model(tmp_path / "data" / "stage.json", '{"stage": 1}')
    other = write_model(tmp_path / "other" / "stage.json", '{"stage": 2}')
    optics = write_model(tmp_path / "data" / "ridge.json", '{"ridge": 1}')
    config = {
        "models": [{"name": "a", "path": "data/stage.json", "scale": "nano"},
                   {"name": "b", "path": "other/stage.json", "scale": "micro"},
                   {"name": "c", "path": "data/stage.json", "scale": "meso"}],
        "optics": {"derive": {"enable": True, "surrogateModelPath": "data/ridge.json"}},
    }
    artifacts = {"schema": "trech_model_artifacts_v1",
                 "models": [{"name": "a", "path": "data/stage.json", "loaded": True, "sha256": shared},
                            {"name": "b", "path": "other/stage.json", "loaded": True, "sha256": other},
                            {"name": "c", "path": "data/stage.json", "loaded": True, "sha256": shared}],
                 "loaders": [{"loader": "optics", "path": "data/ridge.json", "status": "loaded",
                              "loaded": True, "sha256": optics}]}
    return config, artifacts


def test_dependencies_are_copied_by_digest_and_repointed(tmp_path):
    config, artifacts = dependency_config(tmp_path)
    packaged, files = package_dependencies(config, artifacts, [tmp_path / "nowhere", tmp_path])
    paths = [m["path"] for m in packaged["models"]]
    # Identical bytes share one copy; a name clash with different bytes gets a digest suffix.
    assert paths[0] == paths[2] == "scene_deps/stage.json"
    assert paths[1].startswith("scene_deps/stage-") and paths[1].endswith(".json")
    assert packaged["optics"]["derive"]["surrogateModelPath"] == "scene_deps/ridge.json"
    assert set(files) == {paths[0], paths[1], "scene_deps/ridge.json"}
    assert files[paths[1]] == (tmp_path / "other" / "stage.json").resolve()
    assert config["models"][0]["path"] == "data/stage.json"      # input left untouched


@pytest.mark.parametrize("damage, message", [
    (lambda a: a.pop("models"), "manifest does not list"),
    (lambda a: a["loaders"][0].update(status="disabled_strict", loaded=False, sha256=None,
                                      load_note="strict mode disables model inference"),
     "did not load it .strict mode"),
    (lambda a: a["models"][1].update(loaded=False), "did not load it"),
    (lambda a: a["models"][0].update(sha256="0" * 64), "matches the recorded SHA-256"),
])
def test_dependencies_without_verified_recorded_bytes_are_refused(tmp_path, damage, message):
    config, artifacts = dependency_config(tmp_path)
    damage(artifacts)
    with pytest.raises(ValueError, match=message):
        package_dependencies(config, artifacts, [tmp_path])


def test_torchscript_sidecar_travels_with_its_module_and_is_digest_checked(tmp_path):
    module = write_model(tmp_path / "data" / "net.pt", "torchscript bytes")
    sidecar = write_model(tmp_path / "data" / "net.pt.io.json", '{"inputs": ["x"]}')
    config = {"models": [{"name": "net", "path": "data/net.pt"}]}
    artifacts = {"models": [{"name": "net", "path": "data/net.pt", "loaded": True,
                             "sha256": module, "io_sidecar_sha256": sidecar}]}
    packaged, files = package_dependencies(config, artifacts, [tmp_path])
    assert packaged["models"][0]["path"] == "scene_deps/net.pt"
    assert files["scene_deps/net.pt.io.json"] == (tmp_path / "data" / "net.pt.io.json").resolve()
    write_model(tmp_path / "data" / "net.pt.io.json", '{"inputs": ["changed"]}')
    with pytest.raises(ValueError, match="sidecar net.pt.io.json does not match"):
        package_dependencies(config, artifacts, [tmp_path])


def test_runs_without_a_manifest_or_unsafe_folders_are_refused(tmp_path):
    config, _ = dependency_config(tmp_path)
    with pytest.raises(ValueError, match="predates"):
        recorded_dependencies(config, None)
    assert recorded_dependencies({"run": {}}, None) == []
    with pytest.raises(ValueError, match="relative path inside"):
        package_dependencies(config, None, [tmp_path], dependency_dir="../escape")


def test_search_dirs_follow_the_recorded_experiment_then_the_roots(tmp_path):
    relative = {"cli_args": ["trech", "run", "examples/x/x.js", "--output", "o"]}
    assert run_search_dirs(relative, [tmp_path]) == [tmp_path / "examples/x", tmp_path]
    absolute = {"cli_args": ["trech", "lab", str(tmp_path / "s" / "s.js")]}
    assert run_search_dirs(absolute, [tmp_path]) == [tmp_path / "s", tmp_path]
    assert run_search_dirs(None, [tmp_path]) == [tmp_path]


def test_bundle_without_dependencies_is_the_single_file_export():
    scene, config = recorded_scene()
    bundle = scene_to_bundle(scene, config, artifacts=None, search_dirs=[])
    assert bundle.source == scene_to_js(scene, config) and bundle.files == {}
    config["hooks"] = {"registered": ["onEvent"]}
    with pytest.raises(ValueError, match="JS callbacks"):
        scene_to_bundle(scene, config, artifacts=None, search_dirs=[])


def _engine():
    candidates = ([Path(os.environ["TRECH_BIN"])] if os.environ.get("TRECH_BIN") else [])
    candidates += [REPO / p for p in ("build/dev/trech", "build/rel/trech")]
    return next((p.resolve() for p in candidates if p.is_file()), None)


def test_packaged_surrogate_export_runs_from_another_directory(tmp_path):
    """A predictive optics run's ridge model travels with the export and loads the same bytes."""
    engine = _engine()
    if engine is None:
        pytest.skip("No built TRECH binary for the dependency round-trip")
    out = tmp_path / "recorded"
    experiment = "examples/scenarios/optics_surrogate_demo/optics_surrogate_demo.js"
    subprocess.run([str(engine), "run", experiment, "--events", "3", "--output", str(out)],
                   cwd=REPO, capture_output=True, text=True, timeout=300, check=True)
    result = load_run_result(out)
    recorded = next(m for m in result.model_artifacts()["loaders"] if m["loader"] == "optics")
    assert recorded["status"] == "loaded"
    scene = scene_from_output_dir(out)
    scene.volumes[0].position_mm = tuple(c + 1. for c in scene.volumes[0].position_mm)

    export = tmp_path / "export"
    export.mkdir()
    bundle = scene_to_bundle(scene, result.recorded_config(), artifacts=result.model_artifacts(),
                             search_dirs=run_search_dirs(result.run_start_provenance(), [REPO]),
                             dependency_dir="edited_deps")
    assert list(bundle.files) == ["edited_deps/optics_surrogate_ridge.json"]
    for relative, source in bundle.files.items():
        (export / relative).parent.mkdir(parents=True, exist_ok=True)
        (export / relative).write_bytes(source.read_bytes())
    (export / "edited.js").write_text(bundle.source, encoding="utf-8")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    rerun = tmp_path / "rerun"
    subprocess.run([str(engine), "run", str(export / "edited.js"), "--strict-config",
                    "--events", "3", "--output", str(rerun)],
                   cwd=elsewhere, capture_output=True, text=True, timeout=300, check=True)
    loader = next(m for m in load_run_result(rerun).model_artifacts()["loaders"]
                  if m["loader"] == "optics")
    assert loader["status"] == "loaded" and loader["sha256"] == recorded["sha256"]
    assert loader["path"] == "edited_deps/optics_surrogate_ridge.json"
    config = json.loads(load_run_result(rerun).run_start_provenance()["config_json"])
    assert config["geometry"]["volumes"][0]["placement"]["positionMm"] == list(scene.volumes[0].position_mm)


def test_file_export_writes_the_dependency_folder_and_never_overwrites_other_bytes(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import patch

    from trech_studio.engine.outputs import RunResult
    from trech_studio.ui import main_window as module

    scene, config = recorded_scene()
    digest = write_model(tmp_path / "run" / "data" / "stage.json", '{"stage": 1}')
    config["models"] = [{"name": "a", "path": "data/stage.json", "scale": "nano"}]
    scene.source_path = str(tmp_path / "trech_viz_scene.json")
    provenance = {"phase": "run_start", "config_json": json.dumps(config),
                  "cli_args": ["trech", "run", str(tmp_path / "run" / "s.js")],
                  "model_artifacts": {"models": [{"name": "a", "path": "data/stage.json",
                                                  "loaded": True, "sha256": digest}]}}
    result = RunResult(tmp_path, provenance=[provenance], viz_scene_path=Path(scene.source_path))
    messages, warnings = [], []
    window = SimpleNamespace(_loaded_run=result, _scene=scene,
                             settings=SimpleNamespace(output_root=tmp_path),
                             code_editor=SimpleNamespace(source_paths=lambda: ()),
                             console=SimpleNamespace(log_info=messages.append))
    target = tmp_path / "out" / "draft.js"
    target.parent.mkdir()
    with patch.object(module.QFileDialog, "getSaveFileName", return_value=(str(target), "")), \
            patch.object(module.QMessageBox, "warning", lambda *args: warnings.append(args)):
        assert module.StudioWindow._export_scene_scenario(window)
    assert not warnings and "1 model file(s) in draft_deps/" in messages[-1]
    exported = target.read_text()
    assert '"path": "draft_deps/stage.json"' in exported
    assert (target.parent / "draft_deps" / "stage.json").read_text() == '{"stage": 1}'

    # A second export to the same name may reuse identical bytes, never replace different ones.
    (target.parent / "draft_deps" / "stage.json").write_text("someone else's model")
    target.write_text("// previous export")
    with patch.object(module.QFileDialog, "getSaveFileName", return_value=(str(target), "")), \
            patch.object(module.QMessageBox, "warning", lambda *args: warnings.append(args)):
        assert not module.StudioWindow._export_scene_scenario(window)
    assert "different content" in warnings[-1][2] and target.read_text() == "// previous export"
