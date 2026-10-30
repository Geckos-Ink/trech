#!/usr/bin/env bash
# Refresh every runnable experiment's engine/Studio media; slow runs are included.
# Usage: scripts/update_experiment_media.sh [--list] [--only NAME ...] [--resume DIR]
# Requires a built Geant4 engine, render Python (PyVista/Pillow), Studio Python, ffmpeg.
# This command intentionally refreshes committed media, including gated Studio GIFs.
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${TASK_ROOT}"
TASK_RENDER_PY="${RENDER_PY:-build/render-venv/bin/python}"
if [[ ! -x "${TASK_RENDER_PY}" ]]; then TASK_RENDER_PY=python3; fi
export TRECH_BIN="${TRECH_BIN:-${TASK_ROOT}/build/rel/trech}"
export STUDIO_PY="${STUDIO_PY:-${TASK_ROOT}/build/studio-venv/bin/python}"
export PYTHONUNBUFFERED=1
exec "${TASK_RENDER_PY}" scripts/update_experiment_media.py "$@"
