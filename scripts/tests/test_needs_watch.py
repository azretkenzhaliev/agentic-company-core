"""Tests for scripts/needs_watch.py, the CEO's NEEDS-CEO-NOW watcher."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import needs_watch  # noqa: E402


class Watch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name) / "workspaces"
        self.content = self.ws / "acme" / "content"
        self.content.mkdir(parents=True)
        (self.content / "ceo-questions.md").write_text("NEEDS-CEO-NOW /1.CTO 2026-01-18T08:00Z (CTO). old\n")
        self.globs = [str(self.ws / "*" / "content" / "ceo-questions.md"),
                      str(self.ws / "*" / "content" / "orders" / "*" / "*" / "ceo-questions.md")]

    def test_a_file_created_after_it_started_is_read(self):
        """A new order's file, made after the watcher read the old one: its NEEDS-CEO-NOW line is new, printed once;
        the old file's line, its other lines and a later poll with nothing new print nothing."""
        polls = []

        def sleep(seconds):
            polls.append(seconds)
            if len(polls) == 2:
                folder = self.content / "orders" / "D-20260118-x" / "2"
                folder.mkdir(parents=True)
                (folder / "ceo-questions.md").write_text(
                    "# ORDER D-20260118-x/2 (cto, 2026-01-18)\nQUESTION /2.CTO 2026-01-18T09:00Z (CTO). x\n"
                    "**NEEDS-CEO-NOW /2.CTO 2026-01-18T09:01Z (CTO). new\n")

        new = needs_watch.watch(self.globs, sleep=sleep)
        self.assertEqual(polls, [60, 60])
        self.assertEqual(new, {"**NEEDS-CEO-NOW /2.CTO 2026-01-18T09:01Z (CTO). new"})
        out = io.StringIO()
        with mock.patch.object(needs_watch, "watch", return_value=new), contextlib.redirect_stdout(out):
            self.assertEqual(needs_watch.main(self.globs), 0)
        self.assertEqual(out.getvalue(), "**NEEDS-CEO-NOW /2.CTO 2026-01-18T09:01Z (CTO). new\n")

    def test_only_the_order_glob_sees_order_files(self):
        """Started with the product file's glob alone, it never sees an order's file."""
        folder = self.content / "orders" / "D-20260118-x" / "2"
        folder.mkdir(parents=True)
        (folder / "ceo-questions.md").write_text("NEEDS-CEO-NOW /2.CTO 2026-01-18T09:01Z (CTO). x\n")
        self.assertEqual(needs_watch.lines(self.globs[:1]), {"NEEDS-CEO-NOW /1.CTO 2026-01-18T08:00Z (CTO). old"})
        self.assertEqual(len(needs_watch.lines(self.globs)), 2)

    def test_it_reads_the_scan_s_forms(self):
        """A list item's or a writer's NEEDS-CEO-NOW counts, as in the capacity scan (CQ_LEAD); one in a line's middle
        doesn't."""
        heads = ["- NEEDS-CEO-NOW /2.CTO 2026-01-18T09:01Z (CTO). a", "CTO NEEDS-CEO-NOW /2.CTO 2026-01-18T09:02Z. b",
                 "**NEEDS-CEO-NOW /2.CTO 2026-01-18T09:03Z (CTO). c"]
        (self.content / "ceo-questions.md").write_text("\n".join(heads + ["HANDLED NEEDS-CEO-NOW /2.CTO 09:01Z (CEO)"])
                                                        + "\n")
        self.assertEqual(needs_watch.lines(self.globs[:1]), set(heads))


if __name__ == "__main__":
    unittest.main()
