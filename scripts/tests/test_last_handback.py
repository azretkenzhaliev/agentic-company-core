"""Tests for scripts/last_handback.py.

Every transcript is made up in a temporary folder: nothing here reads a real session log."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import last_handback  # noqa: E402

CANARY = "CANARY-text-the-agent-read"


def call(use_id, message):
    return {"type": "assistant", "message": {"content": [
        {"type": "text", "text": CANARY},
        {"type": "tool_use", "id": use_id, "name": "SubagentHandback", "input": {"message": message}},
    ]}}


def answer(use_id, success):
    text = json.dumps({"success": success, "message": "harness text"})
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": use_id, "content": [{"type": "text", "text": text}]},
    ]}}


def other(use_id):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": use_id, "name": "Bash", "input": {"command": "echo " + CANARY}},
    ]}}


class LastHandback(unittest.TestCase):
    def run_on(self, records, raw_lines=()):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "agent.jsonl")
            with open(path, "w") as f:
                for line in raw_lines:
                    f.write(line + "\n")
                for record in records:
                    f.write(json.dumps(record) + "\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = last_handback.main(["last_handback.py", path])
        return code, out.getvalue()

    def test_refused_second_report_is_printed(self):
        code, out = self.run_on([call("u1", "REPORT first"), answer("u1", True), other("b1"),
                                 call("u2", "REPORT second"), answer("u2", False)])
        self.assertEqual(code, 0)
        self.assertEqual(out, "last hand-back: refused\nREPORT second\n")

    def test_call_repeated_after_its_answer_stays_refused(self):
        # A real transcript repeats earlier calls in api-request-blob records.
        blob = {"type": "api-request-blob", "message": call("u2", "REPORT second")["message"]}
        code, out = self.run_on([call("u1", "REPORT first"), answer("u1", True), call("u2", "REPORT second"),
                                 answer("u2", False), blob, call("u2", "REPORT second")])
        self.assertEqual(code, 0)
        self.assertEqual(out, "last hand-back: refused\nREPORT second\n")

    def test_delivered(self):
        code, out = self.run_on([call("u1", "REPORT only"), answer("u1", True)])
        self.assertEqual(code, 0)
        self.assertEqual(out, "last hand-back: delivered\nREPORT only\n")

    def test_no_answer_yet(self):
        code, out = self.run_on([call("u1", "REPORT pending")])
        self.assertEqual(code, 0)
        self.assertEqual(out, "last hand-back: no answer yet\nREPORT pending\n")

    def test_none_and_bad_lines(self):
        code, out = self.run_on([other("b1")], raw_lines=["not json", "[1, 2]"])
        self.assertEqual(code, 1)
        self.assertNotIn(CANARY, out)

    def test_prints_nothing_else_from_the_transcript(self):
        code, out = self.run_on([other("b1"), call("u1", "REPORT"), answer("u1", True)])
        self.assertNotIn(CANARY, out)
        self.assertNotIn("harness text", out)


if __name__ == "__main__":
    unittest.main()
