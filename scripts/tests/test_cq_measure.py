"""Tests for scripts/cq_measure.py, the question files' measure. Made-up lines."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cq_measure  # noqa: E402

FILE = "ceo-questions.md"


class Measure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name) / "workspaces"
        self.content = self.ws / "acme" / "content"
        self.content.mkdir(parents=True)

    def test_misfiled_boundary_read_and_size(self):
        (self.content / FILE).write_text(
            "# ceo-questions\nCEO broadcast 2026-01-18T08:00Z: x\n## ORDER D-20260118-x/1   from: ceo   to: cto\n"
            "RULING D-20260118-x/2/1 2026-01-18T08:01Z (CEO): /2's, under /1.\nCOORD /2.CTO -> /1.CTO: x\n")
        two = self.content / "orders" / "D-20260118-x" / "2"
        two.mkdir(parents=True)
        (two / FILE).write_text("# ORDER D-20260118-x/2 (cto, 2026-01-18)\nREPORT /2.T-1 status: DONE\n"
                                "NEEDS-CEO-NOW /3.CTO 2026-01-18T08:02Z (CTO): /3's.\nANSWER /3.CTO: x\n")
        three = self.content / "orders-closed" / "D-20260118-x" / "3"
        three.mkdir(parents=True)
        (three / FILE).write_text("RULING /3/1 2026-01-18T08:03Z (CEO): its own.\n")
        rows = cq_measure.measure(self.ws)
        broadcast = len("CEO broadcast 2026-01-18T08:00Z: x\n")
        self.assertEqual(rows, [("acme", 1, 3, 4, 6, [(two / FILE).stat().st_size + broadcast],
                                 (self.content / FILE).stat().st_size)])
        line = cq_measure.format_row(*rows[0])
        self.assertTrue(line.startswith("acme: MISFILED in order files 1 of 3; every kind and file 4 of 6; boundary "
                                        "read median 0.2 KB, largest 0.2 KB, over 1 open order file(s); product file "),
                        line)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cq_measure.main(["--workspaces", str(self.ws)]), 0)
        self.assertEqual(out.getvalue(), line + "\n")


if __name__ == "__main__":
    unittest.main()
