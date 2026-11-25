"""The reel-analyst's compaction window, and its batch sizes, which are set to fit in it."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REEL = ROOT / ".claude" / "agents" / "marketing" / "reel-analyst.md"
SKILL = ROOT / ".claude" / "skills" / "content-calendar" / "SKILL.md"


class ReelAnalystContext(unittest.TestCase):
    TEXT = REEL.read_text(encoding="utf-8")

    def test_it_compacts_at_250k(self):
        self.assertRegex(self.TEXT, r"(?m)^autoCompactWindow: 250000$")

    def test_its_batch_is_12_everywhere(self):
        self.assertIn("One batch of 12 reels", self.TEXT)
        self.assertIn("then `--count 6`, then `--count 9`, then `--count 12`.", self.TEXT)
        self.assertIn("watch.py next --week <W> --count 12`", self.TEXT)
        self.assertIn("It does a batch of 12,", SKILL.read_text(encoding="utf-8"))
        self.assertNotRegex(self.TEXT, r"--count 7\b|batch of 7\b")

    def test_its_week_file_rereads_36_a_run(self):
        self.assertIn("**Rereads, 36 breakdowns a run at most.**", self.TEXT)
        self.assertIn("stop before a row that would take you past 36.", self.TEXT)


if __name__ == "__main__":
    unittest.main()
