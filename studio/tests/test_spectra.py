"""Spectrum-prediction Studio extension: pure workspace model, job helpers and offscreen dock.

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_spectra.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from trech_studio.engine.parameters import ScenarioParameter  # noqa: E402
from trech_studio.engine.spectra import describe_event, parse_progress, training_arguments  # noqa: E402
from trech_studio.spectra import build_spectrum_workspace, format_stage, is_spectrum_mode, plot_bounds  # noqa: E402
from trech_studio.ui.scenario_options import ScenarioOptions  # noqa: E402
from trech_studio.ui.spectra import SpectraPanel  # noqa: E402

_APP = QApplication.instance() or QApplication([])
CENTERS = [185.0, 195.0, 205.0, 215.0]


def _stage(**overrides):
    stage = {"model": "spectrum_molecular", "scale": "nano", "ran": True, "inDomain": True, "extrapolation": 0,
             "outOfDomainInputs": [], "starvedInputs": [], "jointStarved": False, "jointMeasured": True,
             "holdoutR2": -0.4, "holdoutSamples": 33}
    stage.update(overrides)
    return stage


def _record(**overrides):
    payload = {"kind": "molecule", "id": "CID931", "label": "naphthalene", "split": "test",
               "grid": {"unit": "nm", "start": 180, "stop": 220, "bins": 4, "centers": CENTERS, "kind": "uv_absorption_envelope_v1"},
               "measured": [0.1, 0.8, 0.6, 0.2], "predicted": [0.2, 0.6, 0.5, 0.3], "inference": "predicted",
               "metrics": {"rmse": 0.13, "cosine": 0.97, "measured_peak_nm": 195, "predicted_peak_nm": 195, "peak_error_nm": 0},
               "stages": [_stage(element=None)], "measured_bands": [{"wavelength_nm": 221, "log_epsilon": 5.04}],
               "sources": {"uv_text": "MAX ABSORPTION (ALCOHOL): 221 NM (LOG E= 5.04)", "uv_url": "https://pubchem"},
               "display": {"title": "naphthalene · held-out"},
               "honesty": {"statement": "Learned prediction from measured spectra (comparison only); not a Geant4 result."}}
    payload.update(overrides)
    return SimpleNamespace(tag="spectrum_prediction", payload=payload)


def _report():
    arch = lambda name, task, cv, exported=None: {"name": name, "task": task, "family": "mlp", "note": "n",
        "exported": exported, "cv_rmse": {"mean": cv, "std": 0.01}, "cv_cosine": {"mean": 0.8, "std": 0.01},
        "family_cv_rmse": None, "test": {"n": 3, "rmse": cv + 0.01, "r2": 0.3, "cosine": 0.7, "peak_error_nm": 40}}
    return SimpleNamespace(tag="spectrum_model_report", payload={
        "ranking": {"atomic": ["atomic_mlp_tanh"], "molecular": ["molecular_mlp_cascade", "molecular_mean"]},
        "architectures": [arch("molecular_mean", "molecular", 0.25), arch("atomic_mlp_tanh", "atomic", 0.30, "spectrum_atomic"),
                          arch("molecular_mlp_cascade", "molecular", 0.23, "spectrum_molecular")],
        "ablation": [{"with": "molecular_mlp_cascade", "without": "molecular_mlp", "cv_rmse_delta": -0.001, "test_rmse_delta": 0.003}]})


def test_workspace_keeps_engine_values_and_null_predictions():
    strict = _record(id="Z011_Na", kind="atom", label="Na I", split="train", predicted=None, metrics=None,
                     inference="disabled_strict", measured_bands=[])
    ws = build_spectrum_workspace([_record(), strict, SimpleNamespace(tag="other", payload={})])
    assert len(ws.records) == 2
    assert ws.records[0].predicted == (0.2, 0.6, 0.5, 0.3)
    assert ws.records[0].held_out and not ws.records[1].held_out
    assert ws.records[1].predicted is None  # never filled in by Studio
    assert "no prediction (disabled_strict)" in ws.records[1].summary_line()
    assert "1 held-out" in ws.header() and "not a Geant4 result" in ws.header()
    assert plot_bounds(ws.records[0])[:2] == (185.0, 215.0)


def test_interval_is_engine_reported_and_validated():
    interval = {"lower": [0.0, 0.4, 0.3, 0.1], "upper": [0.4, 0.8, 0.7, 0.5], "half_width": [0.2] * 4, "nominal_coverage": 0.9}
    ws = build_spectrum_workspace([_record(interval=interval, interval_covered_fraction=0.75),
                                   _record(id="strict", predicted=None, metrics=None, inference="disabled_strict", interval=None)])
    first = ws.records[0].interval
    assert first.upper == (0.4, 0.8, 0.7, 0.5) and first.nominal_coverage == 0.9
    assert "90% per-bin" in first.describe() and "75% of bins" in first.describe()
    assert ws.records[1].interval is None
    assert plot_bounds(ws.records[0])[3] >= 0.8  # the band's top stays on the plot
    with pytest.raises(ValueError):
        build_spectrum_workspace([_record(interval=dict(interval, nominal_coverage=1.0))])
    with pytest.raises(ValueError):
        build_spectrum_workspace([_record(interval=dict(interval, lower=[0.5, 0.4, 0.3, 0.1], upper=[0.4, 0.8, 0.7, 0.5]))])


def test_workspace_rejects_malformed_vectors():
    with pytest.raises(ValueError):
        build_spectrum_workspace([_record(predicted=[0.1, 0.2])])
    with pytest.raises(ValueError):
        build_spectrum_workspace([_record(measured=[0.1, float("nan"), 0.2, 0.3])])


def test_stage_badges_are_engine_flags_only():
    ws = build_spectrum_workspace([_record(stages=[
        _stage(element="H", model="spectrum_atomic", inDomain=False, outOfDomainInputs=["z"], jointStarved=True),
        _stage(jointMeasured=False, holdoutR2=None)])])
    first, second = ws.records[0].stages
    assert first.badges == ("EXTRAPOLATING", "STARVED REGION (JOINT)")
    assert second.badges == ("JOINT NOT CHECKED", "NO MEASURED ACCURACY")
    assert "out-of-domain inputs: z" in format_stage(first)
    assert "held-out R² unmeasured" in format_stage(second)


def test_leaderboard_follows_emitted_ranking():
    ws = build_spectrum_workspace([_record(), _report()])
    assert [r.name for r in ws.leaderboard] == ["atomic_mlp_tanh", "molecular_mlp_cascade", "molecular_mean"]
    assert ws.leaderboard[1].exported == "spectrum_molecular" and ws.leaderboard[1].family_cv_rmse is None
    assert ws.ablation[0]["with"] == "molecular_mlp_cascade"


def test_mode_detection_uses_declared_schema_or_extension():
    assert is_spectrum_mode({"hooks": {"inputs": {"schema": "trech_spectrum_inputs_v1"}}}, {})
    assert is_spectrum_mode({}, {"extensions": ["spectrum_prediction"]})
    assert not is_spectrum_mode({"hooks": {"inputs": {"schema": "trech_chemistry_inputs_v1"}}}, {"extensions": []})


def test_training_job_helpers(tmp_path):
    args = training_arguments(Path("/repo"), tmp_path, offline=True, family_cv=False)
    assert args[0].endswith("projects/spectrum_prediction/bin/spectra.cjs")
    assert args[1:5] == ["all", "--studio", "--out", str(tmp_path)] and "--offline" in args and "--no-family-cv" in args
    with pytest.raises(ValueError):
        training_arguments(Path("/repo"), tmp_path, offline=True, command="rm")
    event = parse_progress('{"event":"architecture","task":"molecular","name":"m","cv_rmse":0.2,"test_rmse":0.25}')
    assert "CV RMSE 0.2000" in describe_event(event)
    assert parse_progress("plain log text") is None and parse_progress("{broken") is None


def test_spectra_panel_shows_records_and_leaderboard():
    panel = SpectraPanel()
    result = SimpleNamespace(emits=[_record(), _report(),
                                    SimpleNamespace(tag="spectrum_geant4_context", payload={"available": True,
                                        "density_g_per_cm3": 1, "mean_excitation_energy_ev": 68.4})])
    panel.show_run(result)
    assert panel.targets.count() == 1
    assert panel.leaderboard.rowCount() == 3
    assert panel.plot.record is not None and panel.plot.record.label == "naphthalene"
    text = panel.details.toPlainText()
    assert "held out from training" in text and "not a model input" in text and "PubChem statement" in text
    assert "cascade ablation" in panel.ablation.text()
    panel.plot.resize(400, 260)
    panel.plot.grab()  # paints without error, including measured-band ticks
    panel.training_finished("/tmp/run")
    assert panel.use_button.isEnabled()


def test_scenario_options_set_value_only_for_declared_controls():
    options = ScenarioOptions()
    options.set_parameters([ScenarioParameter(id="studio_mode", type="boolean", label="Studio", default=False, value=False)])
    assert options.set_value("studio_mode", True)
    assert options.values()["studio_mode"] is True
    assert not options.set_value("missing", 1)


def test_window_spectra_mode_declares_runs_and_loads_engine_output(tmp_path):
    # Real engine inspection and run; stub viewport and launcher (no GPU, no source edits).
    import json
    import subprocess
    from PySide6.QtWidgets import QWidget
    from trech_studio.ui import main_window as module
    from trech_studio.settings import StudioSettings
    root = Path(__file__).resolve().parents[2]
    binary = next((root / p for p in ("build/dev/trech", "build/rel/trech") if (root / p).is_file()), None)
    if binary is None:
        pytest.skip("built engine unavailable")

    class Viewport(QWidget):
        def set_scene(self, *_): pass
        def set_playback(self, *_): pass
        def set_render_budget(self, *_): pass
        def set_playback_time(self, *_): pass
        def set_density_display(self, *_): pass

    original = module.create_viewport
    module.create_viewport = lambda **kwargs: Viewport()
    window = None
    try:
        window = module.StudioWindow(StudioSettings(repo_root=root, engine_bin=binary))
        assert window._spectra_dock.isHidden()
        assert window._open_spectra()
        assert not window._spectra_dock.isHidden() and window.spectra.run_button.isEnabled()
        assert window.scenario_options.values()["studio_mode"] is True
        launches = []
        window._runner.run = lambda *a, **kw: launches.append((a, kw))
        window.code_editor.save = lambda: window.code_editor.current_path()
        window._run_spectra()
        assert len(launches) == 1 and "studio_mode=true" in launches[0][1]["extra_args"]
        # Leaving the scenario hides the extension again.
        window.open_scenario(root / "examples/scenarios/hello_world/hello_world.js")
        assert window._spectra_dock.isHidden()
        out = tmp_path / "run"
        subprocess.run([str(binary), "run", str(root / module.SPECTRUM_SCENARIO), "--param", "studio_mode=true",
                        "--param", 'molecule="benzene"', "--output", str(out)], cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        window.open_output_dir(out)
        assert not window._spectra_dock.isHidden()
        assert window.spectra.targets.count() == 1 and window.spectra.leaderboard.rowCount() > 5
        record = window.spectra.workspace.records[0]
        emitted = [json.loads(line) for line in (out / "trech_hook_emits.jsonl").read_text().splitlines()]
        payload = next(e["payload"] for e in emitted if e["tag"] == "spectrum_prediction")
        assert record.label == "benzene" and list(record.predicted) == payload["predicted"]
        assert "Geant4 context" in window.spectra.details.toPlainText()
        assert window._open_spectra()
        window._use_spectrum_run(str(tmp_path / "missing"))
        assert "not a complete spectrum run" in window.spectra.status.text()
        assert window.scenario_options.values()["data_dir"] == ""
        import shutil
        shutil.copytree(root / "data/spectrum_prediction", tmp_path / "alt")
        window._use_spectrum_run(str(tmp_path / "alt"))
        assert window.scenario_options.values()["data_dir"] == str(tmp_path / "alt")
        assert window.scenario_options.values()["studio_mode"] is True
    finally:
        if window:
            window.close()
        module.create_viewport = original
