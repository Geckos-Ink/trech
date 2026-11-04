"""Byte identity for future observer-harvest cache reuse (standard library only)."""
import hashlib
import json
from pathlib import Path


def capture_identity(script_bytes, engine_path, lower_model_paths, feature_source_paths=None):
    """Describe the actual files before execution, without inferring old identity."""
    return {"schema": "trech_particle_observer_cache_v1",
            "script_sha256": hashlib.sha256(script_bytes).hexdigest(),
            "engine_sha256": hashlib.sha256(Path(engine_path).read_bytes()).hexdigest(),
            "lower_model_sha256": {name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                                   for name, path in sorted(lower_model_paths.items())},
            "feature_source_sha256": {name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                                      for name, path in sorted((feature_source_paths or {}).items())}}


def cache_matches(manifest_path, expected_identity):
    """Legacy rows without an execution-time identity manifest are cache misses."""
    try:
        return json.loads(Path(manifest_path).read_text()) == expected_identity
    except (OSError, ValueError):
        return False


def write_identity(manifest_path, identity):
    """Persist before launching the engine; never backfill historical rows."""
    path = Path(manifest_path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(identity, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)
