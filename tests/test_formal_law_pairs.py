#!/usr/bin/env python3
"""Guard the classic/Lean law pairs listed in formal/laws.json (no Lean toolchain needed).

For every pair: the Lean file declares each listed theorem inside its namespace and cites its
classic sources; each classic source exists and cites the Lean namespace; the conformance test
exists and names each listed check. formal/lean-toolchain must match the toolchain the
thirds/mathlib4 checkout expects, when that checkout is present.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "formal" / "laws.json"
ROLES = {"reference", "validation", "method_property", "invariant"}


def main() -> int:
    errors: list[str] = []
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if document.get("schema") != "trech_formal_laws_v1":
        errors.append("formal/laws.json: unexpected schema")
    ids = set()
    for law in document.get("laws", []):
        law_id = law.get("id", "?")
        if law_id in ids:
            errors.append(f"{law_id}: duplicate id")
        ids.add(law_id)
        if law.get("role") not in ROLES:
            errors.append(f"{law_id}: role {law.get('role')!r} is not one of {sorted(ROLES)}")
        lean = law.get("lean", {})
        lean_path = ROOT / lean.get("file", "")
        if not lean_path.is_file():
            errors.append(f"{law_id}: Lean file {lean.get('file')} missing")
            continue
        lean_text = lean_path.read_text(encoding="utf-8")
        for declaration in lean.get("declarations", []):
            namespace, _, name = declaration.rpartition(".")
            if f"namespace {namespace}" not in lean_text:
                errors.append(f"{law_id}: {lean['file']} has no namespace {namespace}")
            if not re.search(rf"^(theorem|lemma|def|noncomputable def)\s+{re.escape(name)}\b", lean_text, re.M):
                errors.append(f"{law_id}: {lean['file']} does not declare {name}")
            if "sorry" in lean_text:
                errors.append(f"{law_id}: {lean['file']} contains sorry")
        classic = law.get("classic", [])
        if not classic:
            errors.append(f"{law_id}: no classic implementation (Lean is optional; the classic one runs)")
        for entry in classic:
            path = ROOT / entry["path"]
            if not path.is_file():
                errors.append(f"{law_id}: classic source {entry['path']} missing")
                continue
            if entry["cites"] not in path.read_text(encoding="utf-8"):
                errors.append(f"{law_id}: {entry['path']} does not cite {entry['cites']}")
            if entry["path"] not in lean_text:
                errors.append(f"{law_id}: {lean['file']} does not cite {entry['path']}")
        conformance = law.get("conformance", {})
        test = ROOT / conformance.get("test", "")
        if not test.is_file():
            errors.append(f"{law_id}: conformance test {conformance.get('test')} missing")
        else:
            test_text = test.read_text(encoding="utf-8")
            for check in conformance.get("checks", []):
                if f'"{check}"' not in test_text:
                    errors.append(f"{law_id}: {conformance['test']} has no check {check}")

    ours = (ROOT / "formal" / "lean-toolchain").read_text(encoding="utf-8").strip()
    mathlib = ROOT / "thirds" / "mathlib4" / "lean-toolchain"
    if mathlib.is_file():
        expected = mathlib.read_text(encoding="utf-8").strip()
        if ours != expected:
            errors.append(f"formal/lean-toolchain is {ours} but thirds/mathlib4 expects {expected}; "
                          "copy it after scripts/pull_lean.sh")
    else:
        print("thirds/mathlib4 not checked out: toolchain match skipped")

    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print(f"{len(ids)} law pairs consistent")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
