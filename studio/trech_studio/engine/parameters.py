"""Typed JavaScript scenario parameters exposed by ``trech inspect``.

Scenario evaluation remains owned by the engine: Studio never regex-parses JavaScript. The
inspect command runs the same QuickJS loader as a real run and returns the TRECH_VALUE metadata
plus the resolved config, without initializing Geant4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

from .locator import EngineLocation


@dataclass(frozen=True)
class ScenarioParameter:
    id: str
    type: str
    label: str
    default: Any
    value: Any
    description: str = ""
    group: str = "Scenario"
    unit: str = ""
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    choices: tuple[Any, ...] = ()

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ScenarioParameter":
        return cls(
            id=str(raw["id"]),
            type=str(raw["type"]),
            label=str(raw.get("label", raw["id"])),
            default=raw.get("default"),
            value=raw.get("value", raw.get("default")),
            description=str(raw.get("description", "")),
            group=str(raw.get("group", "Scenario")),
            unit=str(raw.get("unit", "")),
            minimum=float(raw["min"]) if "min" in raw else None,
            maximum=float(raw["max"]) if "max" in raw else None,
            step=float(raw["step"]) if "step" in raw else None,
            choices=tuple(raw.get("choices", ())),
        )


@dataclass(frozen=True)
class ScenarioInspection:
    config: Dict[str, Any]
    parameters: tuple[ScenarioParameter, ...]
    sources: tuple[Path, ...] = ()
    studio: Dict[str, Any] = field(default_factory=dict)


def inspection_from_json(text: str) -> ScenarioInspection:
    raw = json.loads(text)
    if not isinstance(raw, dict) or not isinstance(raw.get("config"), dict):
        raise ValueError("engine inspection did not contain a config object")
    params = raw.get("parameters", [])
    if not isinstance(params, list):
        raise ValueError("engine inspection parameters must be an array")
    authoring = raw.get("authoring", {})
    if not isinstance(authoring, dict):
        raise ValueError("engine authoring metadata must be an object")
    sources = authoring.get("sources", [])
    if not isinstance(sources, list) or not all(isinstance(p, str) for p in sources):
        raise ValueError("engine authoring sources must be path strings")
    studio = authoring.get("studio", {})
    if not isinstance(studio, dict) or (studio and studio.get("schema") != "trech_studio_v1"):
        raise ValueError("TRECH_STUDIO must declare schema trech_studio_v1")
    for key in ("title", "description"):
        if key in studio and not isinstance(studio[key], str):
            raise ValueError(f"TRECH_STUDIO {key} must be text")
    processes = studio.get("processes", [])
    if (not isinstance(processes, list) or len(processes) > 64 or
            any(not isinstance(p, dict) or not all(isinstance(p.get(k, ""), str)
                for k in ("id", "label", "kind", "description")) for p in processes)):
        raise ValueError("TRECH_STUDIO processes must be at most 64 text descriptors")
    panels = studio.get("panels", {})
    if not isinstance(panels, dict) or any(not isinstance(v, bool) for v in panels.values()):
        raise ValueError("TRECH_STUDIO panels must map dock identifiers to booleans")
    return ScenarioInspection(
        config=raw["config"],
        parameters=tuple(ScenarioParameter.from_dict(item) for item in params),
        sources=tuple(Path(p) for p in sources), studio=studio,
    )


def inspect_scenario(
    engine: EngineLocation,
    experiment: Path,
    parameter_args: Optional[List[str]] = None,
) -> ScenarioInspection:
    if not engine.available or engine.path is None:
        raise RuntimeError(engine.describe())
    experiment = Path(experiment).resolve()
    args = [str(engine.path), "inspect", str(experiment)]
    if parameter_args:
        args.extend(parameter_args)
    completed = subprocess.run(
        args,
        cwd=str(experiment.parent),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "scenario inspection failed"
        )
        raise RuntimeError(detail)
    return inspection_from_json(completed.stdout)
