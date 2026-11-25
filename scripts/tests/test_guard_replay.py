"""Tests for scripts/guard_replay.py: which calls it reads, how it counts
the desk guard's false refusals, and that the corpus stays private and no secret is printed."""

import contextlib
import datetime
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import guard_replay as gr  # noqa: E402

TOKEN = "gh" + "p_" + "a1B2" * 9  # the secrets lint's GitHub token pattern, built here so no file holds one


def stamp(hours_ago):
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def bash(command, cwd, key, hours_ago=1):
    return json.dumps({"type": "assistant", "timestamp": stamp(hours_ago), "cwd": cwd, "message": {"content": [
        {"type": "tool_use", "id": key, "name": "Bash", "input": {"command": command}}]}})


class Replay(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "checkout"
        for folder in ("knowledge/board/answers", "knowledge/company", "workspaces/board-desk", ".git"):
            (self.root / folder).mkdir(parents=True)
        project = self.tmp / "projects" / f"-home-x-{gr.NAME}"
        (project / "s1" / "subagents").mkdir(parents=True)
        root = str(self.root)
        false = "f=$(ls knowledge/company | head -1); grep -c x knowledge"  # refused, writing nothing
        (project / "s1.jsonl").write_text("\n".join([
            json.dumps({"type": "agent-setting", "agentSetting": "ceo"}),
            bash("ls knowledge/company", root, "t1"),
            bash("rm -rf knowledge/board/answers/a.md", root, "t2"),
            bash(f"echo {TOKEN} > /dev/null; {false}", root, "t3"),
            bash(false, root, "t3"),  # the same tool_use id: read once
            bash(false, root, "t4", hours_ago=30)]) + "\n")  # before the window
        (project / "s1" / "subagents" / "agent-a1.jsonl").write_text(bash(false, root, "t5") + "\n")
        (project / "s1" / "subagents" / "agent-a1.meta.json").write_text(json.dumps({"agentType": "senior-engineer"}))
        (project / "plain.jsonl").write_text(bash(false, root, "t6") + "\n")  # the Board's own session: never held
        self.projects, self.corpus = self.tmp / "projects", self.tmp / "corpus"

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gr.main(["--projects", str(self.projects), "--corpus-dir", str(self.corpus)])
        return code, out.getvalue()

    def test_it_counts_the_held_calls_and_their_false_refusals(self):
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("guard replay: 4 agents' Bash calls", out)
        self.assertIn("1 plain sessions' calls skipped", out)
        self.assertIn("allowed: 1\nrefused: 3\n", out)
        self.assertIn("false refusals (refused, naming no held folder, desk script or token): 2\n", out)
        self.assertIn("refused naming a held folder, the desk script or the token: 1 ", out)
        self.assertIn(" senior-engineer [", out)
        self.assertIn(" ceo [", out)

    def test_a_run_that_reads_no_call_is_no_pass(self):
        shutil.rmtree(self.projects / f"-home-x-{gr.NAME}")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.run_main()[0], 2)

    def test_the_corpus_is_private_and_no_secret_is_printed_or_kept(self):
        self.corpus.mkdir(mode=0o755)  # an earlier run's folder, opened wider, with its corpus: made 0700, the old gone
        os.chmod(self.corpus, 0o755)
        (self.corpus / "corpus-20260101T000000Z.jsonl").write_text("{}\n")
        _, out = self.run_main()
        self.assertNotIn(TOKEN, out)
        self.assertIn(gr.MASK, out)
        self.assertIn("1 secrets masked", out)
        files = list(self.corpus.glob("corpus-*.jsonl"))
        self.assertEqual(len(files), 1)
        self.assertNotIn(TOKEN, files[0].read_text())
        self.assertEqual(stat.S_IMODE(os.stat(self.corpus).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(files[0]).st_mode), 0o600)
        for line in out.splitlines():  # a listed command shows its first 120 characters at most
            if line.startswith("  20"):
                self.assertLessEqual(len(line.split("]: ", 1)[1]), gr.SHOWN)

    def test_a_call_after_a_move_into_a_folder_gone_since_is_apart(self):
        gr.desk = gr.load(gr.GUARD)
        gone = str(self.tmp / "gone")
        self.assertTrue(gr.gone("ls", gone))
        self.assertTrue(gr.gone(f"cd {gone} && ls", str(self.root)))
        self.assertFalse(gr.gone("cd knowledge && ls", str(self.root)))


if __name__ == "__main__":
    unittest.main()
