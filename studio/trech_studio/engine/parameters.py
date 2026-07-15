"""Typed JavaScript scenario parameters exposed by ``trech inspect``.

Scenario evaluation remains owned by the engine: Studio never regex-parses JavaScript. The
inspect command runs the same QuickJS loader as a real run and returns the TRECH_VALUE metadata
plus the resolved config, without initializing Geant4.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def inspection_from_json(text: str) -> ScenarioInspection:
    raw = json.loads(text)
    if not isinstance(raw, dict) or not isinstance(raw.get("config"), dict):
        raise ValueError("engine inspection did not contain a config object")
    params = raw.get("parameters", [])
    if not isinstance(params, list):
        raise ValueError("engine inspection parameters must be an array")
    return ScenarioInspection(
        config=raw["config"],
        parameters=tuple(ScenarioParameter.from_dict(item) for item in params),
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
