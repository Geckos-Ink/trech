"""Model browser: catalog parsing, folder scan, unnamed grouping, run join and the offscreen dialog.

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_model_catalog.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from trech_studio.engine.model_catalog import scan_models  # noqa: E402
from trech_studio.model_catalog import (  # noqa: E402
    attach_run, describe_model, entry_html, group_entries, matches_filter, outcome_decisions,
)
from trech_studio.ui.model_browser import ModelBrowser  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
_APP = QApplication.instance() or QApplication([])


def dense(inputs, outputs, widths=(4,), **extra):
    sizes = [len(inputs), *widths, len(outputs)]
    layers = []
    for i in range(len(sizes) - 1):
        layers.append({"weights": [[0.1] * sizes[i] for _ in range(sizes[i + 1])], "bias": [0.0] * sizes[i + 1],
                       "activation": "silu" if i < len(sizes) - 2 else "none"})
    return {"model": "generic_surrogate_v1", "input_features": inputs, "output_features": outputs,
            "layers": layers, **extra}


def test_dense_entry_counts_stored_weights_and_reads_context():
    data = dense(["a", "b"], ["y"], widths=(3,), scale="meso", trained_scale_bands=["meso"],
                 input_domain={"standardized_radius": [2, 2], "joint": {"centers": [[0, 0]], "radius": 1}},
                 holdout={"r2_min": 0.97, "samples": 40})
    entry = describe_model(data, Path("m.json"), "repository")
    assert entry.format == "dense"
    assert entry.parameters == 2 * 3 + 3 + 3 * 1 + 1
    assert entry.architecture == ["dense 2 → 3, silu", "dense 3 → 1"]
    assert entry.bands == ["meso"] and entry.domain == "measured per-input hull + joint reference"
    assert entry.holdout_r2 == 0.97 and entry.holdout_samples == 40


def test_v2_network_layers_and_structured_note():
    data = dense(["a", "b"], ["y"], widths=(3,))
    data["model"] = "generic_surrogate_v2"
    data["network"] = {"layers": data.pop("layers")}
    data["note"] = {"measured": True, "scope": "water"}
    entry = describe_model(data, Path("v2.json"))
    assert entry.parameters == 13 and entry.architecture[0] == "dense 2 → 3, silu"
    assert entry.note == "measured: true\nscope: water"


def test_routing_domain_is_shown():
    data = dense(["t"], ["y"], routing_domain={"features": ["melt_fraction"], "min": [0.5], "max": [1.0]})
    entry = describe_model(data, Path("melt.json"))
    assert entry.routing == [("melt_fraction", 0.5, 1.0)]
    assert "Routing domain" in entry_html(entry) and "melt_fraction 0.5 … 1" in entry_html(entry)


def test_missing_domain_and_holdout_are_stated_not_zero():
    entry = describe_model(dense(["a"], ["y"]), Path("m.json"))
    assert entry.domain.startswith("not measured")
    assert entry.holdout_r2 is None
    assert "no carried accuracy" in entry_html(entry)


def test_set_network_and_evolved_twin():
    layer = {"weights": [[1.0, 1.0]], "bias": [0.0], "activation": "none"}
    v3 = {"model": "generic_surrogate_v3", "input_features": ["m0_x", "m0_present"], "output_features": ["g"],
          "network": {"kind": "deepsets", "phi": [layer], "rho": [layer]}}
    entry = describe_model(v3, Path("set.json"))
    assert entry.format == "deepsets" and entry.parameters == 6
    assert entry.architecture[0].startswith("phi: dense 2 → 1")
    twin = {"schema": "trech_evolved_arch_v1", "input_features": ["a"], "output_features": ["y"],
            "runtime": "torchscript",
            "trained_from": {"generator": "evolvo_gfsl_nn", "parameter_count": 3368,
                             "architecture": ["v0 = input vec[1]", "out = linear(v0 -> 1)"]}}
    entry = describe_model(twin, Path("job_evolvo.arch.json"))
    assert entry.format == "torchscript" and entry.name == "job_evolvo.pt"
    assert entry.parameters == 3368 and entry.parameters_source == "recorded by generator"
    assert entry.architecture[-1] == "out = linear(v0 -> 1)"


def test_non_model_json_is_refused():
    assert describe_model({"schema": "something_else"}, Path("x.json")).error


def test_context_grouping_is_unnamed_and_shared_spaces_come_first():
    a = describe_model(dense(["t", "p"], ["y"]), Path("a.json"))
    b = describe_model(dense(["p", "t"], ["z"]), Path("b.json"))
    c = describe_model(dense(["q"], ["y"]), Path("c.json"))
    groups = group_entries([c, a, b], "context")
    assert groups[0][0] == "inputs: p, t" and [e.name for e in groups[0][1]] == ["a.json", "b.json"]
    assert groups[1][0] == "inputs: q"
    a.scale, c.trained_bands = "macro", ["nano"]
    assert [label for label, _ in group_entries([a, b, c], "scale")] == ["nano", "macro", "no scale recorded"]
    assert matches_filter(a, "macro t") and not matches_filter(a, "q")


def test_outcome_decisions_and_run_join(tmp_path):
    outcome = {"schema": "trech_arch_outcome_v1", "name": "job",
               "classic": {"model": str(tmp_path / "job.classic.json")},
               "evolvo": {"model": str(tmp_path / "job_evolvo.pt")},
               "decision": {"ok": True, "generator": "evolvo", "model": str(tmp_path / "job_evolvo.pt"),
                            "reason": "the evolved architecture beat the classic reference"}}
    decisions = outcome_decisions(outcome, tmp_path / "job.outcome.json")
    assert decisions[str(tmp_path / "job.classic.json")].role == "classic reference"
    assert decisions[str(tmp_path / "job_evolvo.pt")].role == "chosen"
    entry = describe_model(dense(["a"], ["y"]), Path("m.json"))
    entry.sha256 = "ab" * 32
    manifest = {"schema": "trech_model_artifacts_v1", "models": [
        {"name": "op", "loaded": True, "sha256": "ab" * 32, "operator_role": "thermal",
         "required_context_keys": ["melt_onset_k"]},
        {"name": "failed", "loaded": False, "sha256": None}]}
    assert attach_run([entry], manifest) == 1
    page = entry_html(entry)
    assert "Used by the loaded run" in page and "operator role: thermal" in page and "melt_onset_k" in page
    assert attach_run([entry], None) == 0 and entry.run_context is None


def test_details_escape_file_text():
    entry = describe_model(dense(["<b>x</b>"], ["y"], note="<script>alert(1)</script>"), Path("m.json"))
    page = entry_html(entry)
    assert "<script>" not in page and "&lt;script&gt;" in page and "&lt;b&gt;x&lt;/b&gt;" in page


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True))  # sorted: the schema key is not at the top
    return path


def test_scan_reads_folders_outcomes_and_hashes(tmp_path):
    repo = tmp_path / "repo"
    model = write(repo / "data" / "fam" / "a.json", dense(["t"], ["y"], widths=(64,) * 8))
    write(repo / "data" / "fam" / "notes.json", {"hello": "world"})
    (repo / "data" / "fam" / "broken.json").write_text("{\"model\": \"generic_surrogate_v1\", ")
    arch = repo / "build" / "arch"
    classic = write(arch / "job.classic.json", dense(["a"], ["y"], trained_from={"generator": "classic_native"}))
    write(arch / "job_evolvo.arch.json", {"schema": "trech_evolved_arch_v1", "input_features": ["a"],
                                          "output_features": ["y"], "trained_from": {"parameter_count": 9}})
    (arch / "job_evolvo.pt").write_bytes(b"torchscript")
    write(arch / "job.outcome.json", {"schema": "trech_arch_outcome_v1", "name": "job",
                                      "classic": {"model": str(classic)},
                                      "evolvo": {"model": str(arch / "job_evolvo.pt")},
                                      "decision": {"ok": True, "generator": "classic", "model": str(classic),
                                                   "reason": "the classic reference kept"}})
    extra = write(tmp_path / "elsewhere" / "b.json", dense(["t"], ["z"]))
    scan = scan_models(repo, None, [extra.parent])
    by_name = {e.name: e for e in scan.entries}
    assert set(by_name) == {"a.json", "job.classic.json", "job_evolvo.pt", "b.json"}
    assert scan.outcomes == 1 and len(scan.skipped) == 1 and "broken.json" in scan.skipped[0]
    assert by_name["a.json"].origin == "repository" and by_name["b.json"].origin == "folder"
    assert by_name["job.classic.json"].origin == "generated"
    assert by_name["job.classic.json"].decisions[0].role == "chosen"
    assert by_name["job_evolvo.pt"].decisions[0].role == "evolved, not chosen"
    assert by_name["job_evolvo.pt"].sha256 == hashlib.sha256(b"torchscript").hexdigest()
    assert by_name["a.json"].sha256 == hashlib.sha256(model.read_bytes()).hexdigest()


def test_repository_scan_finds_committed_models():
    scan = scan_models(REPO, None)
    formats = {e.format for e in scan.entries}
    assert len(scan.entries) >= 40 and {"dense", "deepsets"} <= formats
    assert all(e.origin == "repository" or e.origin == "generated" for e in scan.entries)


def test_browser_dialog_groups_filters_and_remembers_folders(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "data" / "a.json", dense(["t", "p"], ["y"], scale="meso"))
    write(repo / "data" / "b.json", dense(["p", "t"], ["z"], scale="nano"))
    extra = write(tmp_path / "more" / "c.json", dense(["q"], ["y"]))
    settings = QSettings(str(tmp_path / "studio.ini"), QSettings.IniFormat)
    browser = ModelBrowser(repo, None, settings=settings, pick_folder=lambda: extra.parent)
    assert browser.tree.topLevelItemCount() == 1  # origin: repository only
    browser.add_folder()
    assert [Path(p) for p in settings.value("model_browser/extra_folders")] == [extra.parent]
    assert browser.tree.topLevelItemCount() == 2
    browser.group_by.setCurrentIndex(browser.group_by.findData("context"))
    top = browser.tree.topLevelItem(0)
    assert top.text(0).startswith("inputs: p, t") and top.childCount() == 2
    browser.filter.setText("nano")
    assert browser.tree.topLevelItemCount() == 1 and browser.tree.topLevelItem(0).childCount() == 1
    browser.filter.setText("")
    assert browser.select(repo / "data" / "a.json")
    assert "dense 2 → 4, silu" in browser.details.toPlainText()
    entry = browser.entry_for(str(repo / "data" / "a.json"))
    browser.set_run_manifest({"schema": "trech_model_artifacts_v1",
                              "models": [{"name": "stage", "loaded": True, "sha256": entry.sha256}]})
    assert "used by loaded run" in browser.tree.topLevelItem(0).child(0).text(0) or any(
        "used by loaded run" in browser.tree.topLevelItem(i).child(j).text(0)
        for i in range(browser.tree.topLevelItemCount())
        for j in range(browser.tree.topLevelItem(i).childCount()))
    reopened = ModelBrowser(repo, None, settings=settings, pick_folder=lambda: None)
    assert reopened.extra_folders == [extra.parent]
    reopened.forget_folders()
    assert reopened.extra_folders == [] and len(reopened.entries()) == 2
