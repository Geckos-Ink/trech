"""CLI entry point: ``python -m trech_studio`` (and the ``trech-studio`` console script)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .settings import StudioSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trech-studio",
        description="TRECH Studio — 3D scenario editor, simulation viewer, and code editor.",
    )
    parser.add_argument(
        "--open",
        dest="open_dir",
        default=None,
        metavar="OUTPUT_DIR",
        help="Load an existing run output directory on startup (scene + trajectories + emits).",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        metavar="EXPERIMENT.js",
        help="Open a scenario .js in the code editor on startup.",
    )
    parser.add_argument(
        "--engine-bin",
        default=None,
        metavar="PATH",
        help="Path to the trech engine binary (default: $TRECH_BIN or build/**/trech).",
    )
    parser.add_argument(
        "--background",
        choices=["dark", "light"],
        default="dark",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    settings = StudioSettings(background=args.background)
    if args.engine_bin:
        settings.engine_bin = Path(args.engine_bin).expanduser()

    # Import the Qt app lazily so `--help` works even without PySide6 installed.
    try:
        from .app import run_app
    except ImportError as exc:  # pragma: no cover - environment dependent
        print(
            "TRECH Studio needs PySide6 (and wgpu for the 3D viewport).\n"
            "  pip install -e .   # from the studio/ directory\n"
            f"import error: {exc}",
            file=sys.stderr,
        )
        return 1

    return run_app(
        settings,
        open_dir=args.open_dir,
        scenario=args.scenario,
    )


if __name__ == "__main__":
    sys.exit(main())
