"""Tests for scripts/status_log.py, the CEO's row helper."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "status_log.py"
sys.path.insert(0, str(SCRIPT.parent))

import status_log  # noqa: E402

PAGE = "---\ntitle: x\n---\n\n## Status log\n\n| When | What |\n|---|---|\n| a | b |\n\n## Next\n\n| c | d |\n"


class StatusLog(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.page = self.dir / "D-x.md"
        self.page.write_text(PAGE)

    def test_rows_go_after_the_status_log_s_last_row(self):
        text, after = status_log.add_rows(PAGE, ["| e | f |"])
        self.assertEqual(after, 9)
        self.assertIn("| a | b |\n| e | f |\n\n## Next\n\n| c | d |", text)

    def test_rows_from_a_file_and_from_standard_input(self):
        rows = self.dir / "rows.txt"
        rows.write_text("| e | knowledge/board/answers/2026-W03.md, $(date) |\n\n")
        run = subprocess.run([sys.executable, str(SCRIPT), str(self.page), str(rows)], capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stdout), (0, "1 row(s) after line 9\n"))
        run = subprocess.run([sys.executable, str(SCRIPT), str(self.page), "-"], input="| g | h |\n",
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        self.assertIn("| a | b |\n| e | knowledge/board/answers/2026-W03.md, $(date) |\n| g | h |\n\n## Next",
                      self.page.read_text())

    def test_a_page_without_the_table_is_left_as_it_is(self):
        self.page.write_text("## Status log\n\nnone yet\n")
        run = subprocess.run([sys.executable, str(SCRIPT), str(self.page), "-"], input="| e | f |\n",
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(self.page.read_text(), "## Status log\n\nnone yet\n")
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT)], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
