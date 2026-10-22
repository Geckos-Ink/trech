"""Exercise the real pinned Evolvo, with no physics or Torch dependency."""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "torch"))
from trech_torch.evolve_structure import Structure, search_structure


class StructureSearchTests(unittest.TestCase):
    def test_determinism_bounds_and_rng_isolation(self):
        before = random.getstate()
        seen = []
        def score(shape):
            seen.append(shape)
            return (shape.width - 16)**2 + (shape.depth - 5)**2
        a = search_structure(score, generations=2, population=5, max_depth=8, max_width=32)
        b = search_structure(score, generations=2, population=5, max_depth=8, max_width=32)
        self.assertEqual(a, b)
        self.assertEqual(before, random.getstate())
        self.assertTrue(seen)
        self.assertTrue(all(1 <= s.depth <= 8 and 1 <= s.width <= 32 for s in seen))
        self.assertGreater(a["evaluated_structures"], 1)
        self.assertEqual(Structure(8, 5).parameter_count(2, 1), 321)

    def test_time_budget_and_invalid_limits(self):
        report = search_structure(lambda _: 1, generations=20, population=4, seconds=1e-9)
        self.assertEqual(report["stop_reason"], "time_budget")
        self.assertEqual(report["evaluated_structures"], 1)
        with self.assertRaises(ValueError):
            search_structure(lambda _: 0, max_depth=0)


if __name__ == "__main__":
    unittest.main()
