"""Check the C++/Node research boundary from outside the source directory."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    launcher, node, runner = (str(Path(arg).resolve()) for arg in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="trech atomic host ") as directory:
        cases = (
            (),
            ("--help",),
            ("--trech-unknown-research-flag",),
            ("--input", "missing request ; $(exit 97).json"),
        )
        for arguments in cases:
            direct = subprocess.run(
                [node, runner, *arguments], cwd=directory, capture_output=True,
                text=True, timeout=20, check=False,
            )
            launched = subprocess.run(
                [launcher, *arguments], cwd=directory, capture_output=True,
                text=True, timeout=20, check=False,
            )
            assert launched.returncode == direct.returncode, (
                arguments, launched.returncode, direct.returncode,
            )
            assert launched.stdout == direct.stdout, (arguments, "stdout differs")
            assert launched.stderr == direct.stderr, (arguments, "stderr differs")
            if not arguments:
                assert launched.returncode == 0, launched.stderr
                output = json.loads(launched.stdout)
                assert output["schema"] == "trech.atomic_research.v1"
                provenance = output["provenance"]
                assert provenance["runtime"]["host"] == "Node.js"
                assert provenance["runtime"]["v8"]
                assert int(provenance["runtime"]["node"].split(".")[0]) >= 18
                assert provenance["geant4Derived"] is False
                assert provenance["learned"] is False
                assert provenance["inferenceCount"] == 0
                assert len(output["results"]) == 1
                assert output["results"][0]["origin"] == "independent_quantum_reference"
            elif arguments == ("--help",):
                assert launched.returncode == 0, launched.stderr
            else:
                assert launched.returncode != 0, arguments
        assert not list(Path(directory).iterdir()), "Arguments created unexpected files"
    print("Atomic host forwards literal arguments and preserves Node results/status")


if __name__ == "__main__":
    main()
