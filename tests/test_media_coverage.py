"""Committed-media coverage: every tracked image/animation is shown by some Markdown page."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_media_coverage as cov  # noqa: E402


def _tree(files: dict[str, str]) -> tuple[Path, list[str], tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root, sorted(files), tmp


class MediaCoverage(unittest.TestCase):
    def test_repository_media_are_all_shown(self):
        report = cov.coverage(ROOT)
        self.assertGreater(report["media"], 0)
        self.assertEqual(report["missing"], [], "embed these in their owning page or docs/previews.md")

    def test_reference_forms_resolve_relative_to_the_page(self):
        root, files, tmp = _tree({
            "README.md": "![a](media/a.gif) [b](media/b.png \"title\")\n[c]: media/c.jpg\n",
            "docs/page.md": '<img src="../media/d.gif" width="10"> <a href=\'img/e.svg\'>e</a>'
                            " [f](/media/f%20x.png#frag)",
            "docs/img/e.svg": "", "media/a.gif": "", "media/b.png": "", "media/c.jpg": "",
            "media/d.gif": "", "media/f x.png": "",
        })
        with tmp:
            report = cov.coverage(root, files)
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["shown"], 6)

    def test_unreferenced_media_are_reported_and_posters_are_exempt(self):
        root, files, tmp = _tree({
            "docs/previews.md": "![run](../previews/run.gif) [web](https://example.org/x.png)",
            "previews/run.gif": "", "previews/run.png": "",
            "previews/new.gif": "", "previews/new.png": "", "previews/lone.png": "",
            "docs/reference/geant4/_static/logo.png": "",
        })
        with tmp:
            report = cov.coverage(root, files)
        self.assertEqual(report["posters"], 1)  # run.png is run.gif's poster
        # new.png is not exempt: its GIF is not shown either; the vendored tree is.
        self.assertEqual(report["missing"],
                         ["previews/lone.png", "previews/new.gif", "previews/new.png"])
        self.assertFalse(report["pass"])

    def test_targets_outside_the_repository_are_ignored(self):
        self.assertIsNone(cov.resolve("README.md", "../outside.png"))
        self.assertIsNone(cov.resolve("a/b.md", "data:image/png;base64,AAAA"))
        self.assertEqual(cov.resolve("a/b.md", "./c/../d.gif?raw=1"), "a/d.gif")


if __name__ == "__main__":
    unittest.main()
