"""Engine discovery checks the inspection bridge and preserves explicit choices."""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.engine.locator import EngineLocation, locate_engine
from trech_studio.engine.parameters import inspect_scenario


def _engine(path, *, compatible=True, modified=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n" + '''
import json, pathlib, sys
assert sys.argv[1] == 'inspect'
experiment = pathlib.Path(sys.argv[2])
assert experiment.is_absolute()
assert pathlib.Path.cwd() == experiment.parent
raw = {'config': {'detector': {'worldSizeMm': 124}},
       'parameters': [{'id': 'studio_probe', 'type': 'integer', 'value': 124}],
       'authoring': {'sources': [str(experiment), str(experiment.with_suffix('.ui.js'))],
                     'studio': {'schema': 'trech_studio_v1', 'title': 'Studio engine probe'}}}
''' + ("del raw['authoring']\n" if not compatible else "") +
        "print(json.dumps(raw))\n", encoding="utf-8")
    path.chmod(0o755)
    os.utime(path, (modified, modified))
    return path


def _isolate(monkeypatch):
    monkeypatch.delenv("TRECH_BIN", raising=False)
    monkeypatch.setenv("PATH", "")


def test_newest_compatible_build_wins_over_dev_prefix(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    _engine(tmp_path / "build/dev/trech", modified=10)
    release = _engine(tmp_path / "build/rel/trech", modified=20)
    location = locate_engine(tmp_path)
    assert location.path == release
    assert location.source == "build" and location.available


def test_newer_incompatible_build_falls_back_to_working_bridge(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    _engine(tmp_path / "build/dev/trech", compatible=False, modified=20)
    release = _engine(tmp_path / "build/rel/trech", modified=10)
    assert locate_engine(tmp_path).path == release


def test_all_failed_probes_report_paths_and_rebuild_advice(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    dev = _engine(tmp_path / "build/dev/trech", compatible=False)
    location = locate_engine(tmp_path)
    assert not location.available
    assert str(dev) in location.describe()
    assert "inspection protocol" in location.describe()
    assert "Rebuild" in location.describe()


def test_probe_timeout_is_bounded_and_reported(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    _engine(tmp_path / "build/dev/trech")

    def timeout(args, **kwargs):
        assert kwargs["timeout"] == 3
        raise subprocess.TimeoutExpired(args, 3)

    monkeypatch.setattr("trech_studio.engine.locator.subprocess.run", timeout)
    location = locate_engine(tmp_path)
    assert not location.available
    assert "timed out after 3 seconds" in location.describe()


def test_explicit_and_environment_choices_are_not_replaced(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    dev = _engine(tmp_path / "build/dev/trech")
    explicit = _engine(tmp_path / "explicit", compatible=False)
    assert locate_engine(tmp_path, explicit).path == explicit
    monkeypatch.setenv("TRECH_BIN", str(explicit))
    assert locate_engine(tmp_path).path == explicit
    missing = tmp_path / "missing"
    monkeypatch.setenv("TRECH_BIN", str(missing))
    location = locate_engine(tmp_path)
    assert not location.available and location.path == missing
    assert str(missing) in location.describe()
    assert dev.is_file()


def test_nonexecutable_override_is_unavailable_without_fallback(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    _engine(tmp_path / "build/dev/trech")
    invalid = tmp_path / "not-executable"
    invalid.write_text("not a binary", encoding="utf-8")
    location = locate_engine(tmp_path, invalid)
    assert not location.available
    assert "not an executable file" in location.describe()


def test_direct_relative_location_survives_inspection_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    binary = _engine(tmp_path / "bin/trech")
    experiment = tmp_path / "scenario/probe.js"
    experiment.parent.mkdir()
    experiment.write_text("", encoding="utf-8")
    location = EngineLocation(Path("bin/trech"), "test")
    assert location.path == binary
    inspection = inspect_scenario(location, experiment)
    assert inspection.config["detector"]["worldSizeMm"] == 124


def test_path_fallback_is_probed(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    binary = _engine(tmp_path / "bin/trech")
    monkeypatch.setenv("PATH", str(binary.parent))
    location = locate_engine(tmp_path)
    assert location.path == binary and location.source == "path"


def test_equal_timestamps_keep_conventional_dev_preference(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    dev = _engine(tmp_path / "build/dev/trech")
    _engine(tmp_path / "build/rel/trech")
    assert locate_engine(tmp_path).path == dev


def test_missing_engine_remains_optional(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    location = locate_engine(tmp_path)
    assert not location.available and location.path is None
    assert "not found" in location.describe()


def test_disappearing_build_metadata_does_not_block_other_candidates(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    vanished = _engine(tmp_path / "build/dev/trech", modified=20)
    release = _engine(tmp_path / "build/rel/trech", modified=10)
    original_stat = Path.stat

    def stat_during_rebuild(path, *args, **kwargs):
        if path == vanished:
            raise FileNotFoundError("candidate replaced by concurrent rebuild")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_during_rebuild)
    location = locate_engine(tmp_path)
    assert location.available and location.path == release


def test_unwritable_probe_directory_keeps_viewer_usable(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    _engine(tmp_path / "build/dev/trech")

    def unavailable_temporary_directory(*args, **kwargs):
        raise PermissionError("temporary directory is read-only")

    monkeypatch.setattr("trech_studio.engine.locator.tempfile.TemporaryDirectory",
                        unavailable_temporary_directory)
    location = locate_engine(tmp_path)
    assert not location.available
    assert "temporary directory is read-only" in location.describe()


def test_symlink_loop_override_reports_error_without_fallback(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    _engine(tmp_path / "build/dev/trech")
    loop = tmp_path / "loop"
    loop.symlink_to("loop")
    location = locate_engine(tmp_path, loop)
    assert not location.available and location.source == "override"
    assert "could not resolve engine binary" in location.describe()


def test_build_directory_read_error_still_allows_path_engine(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    build = tmp_path / "build"
    build.mkdir()
    binary = _engine(tmp_path / "bin/trech")
    monkeypatch.setenv("PATH", str(binary.parent))
    original_iterdir = Path.iterdir

    def unreadable_build(path):
        if path == build:
            raise PermissionError("build directory is unreadable")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", unreadable_build)
    location = locate_engine(tmp_path)
    assert location.available and location.path == binary and location.source == "path"
