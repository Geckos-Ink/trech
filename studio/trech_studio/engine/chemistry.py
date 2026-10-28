"""JSON scene import/export; all filesystem access stays in the engine bridge."""
import json
import hashlib
from pathlib import Path


def scene_text(value, depth=0):
    """Readable JSON with bounded numeric rows; avoid a Qt text block per voxel."""
    indent = "  " * depth
    if isinstance(value, dict):
        return "{\n" + ",\n".join(indent+"  "+json.dumps(k)+": "+scene_text(v, depth+1)
                                     for k, v in value.items()) + "\n"+indent+"}"
    if isinstance(value, list) and value:
        if all(isinstance(x, (int, float)) for x in value):
            rows = [", ".join(json.dumps(x, allow_nan=False) for x in value[i:i+16]) for i in range(0, len(value), 16)]
            return "[" + (",\n"+indent+"  ").join(rows) + "]"
        return "[\n" + ",\n".join(indent+"  "+scene_text(v, depth+1) for v in value) + "\n"+indent+"]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def read_scene(path: Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != "trech_chemistry_scene_v1":
        raise ValueError("Expected trech_chemistry_scene_v1; TRECH validates molecules/fields on inspection")
    return raw


def write_scene(path: Path, scene: dict) -> None:
    if scene.get("schema") != "trech_chemistry_scene_v1":
        raise ValueError("Expected trech_chemistry_scene_v1")
    Path(path).write_text(scene_text(scene) + "\n", encoding="utf-8")


def stage_scene_parameters(args: list[str], directory: Path) -> list[str]:
    """Large density grids exceed OS argument limits; use immutable content-addressed JSON."""
    staged = list(args)
    for i, arg in enumerate(staged):
        if not arg.startswith("scene_json="):
            continue
        text = json.loads(arg.split("=", 1)[1])
        if len(text.encode("utf-8")) <= 32768:
            continue
        payload = text.encode("utf-8")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (hashlib.sha256(payload).hexdigest() + ".json")
        if not path.exists():
            path.write_bytes(payload)
        staged[i] = 'scene_json=""'
        # Replace any explicit clear of the file parameter instead of duplicating it.
        staged = [a for j, a in enumerate(staged) if not (a == "--param" and j + 1 < len(staged) and staged[j + 1].startswith("scene_file=")) and not a.startswith("scene_file=")]
        staged += ["--param", "scene_file=" + json.dumps(str(path.resolve()))]
        break
    return staged
