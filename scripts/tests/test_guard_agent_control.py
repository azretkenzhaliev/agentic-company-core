"""Tests for scripts/hooks/guard_agent_control.py, run as Claude Code runs it:
JSON on stdin, exit 2 plus stderr to block, exit 0 to allow.

The session layout matches Claude Code's: the main
transcript is <project>/<session>.jsonl, subagents live flat in <project>/<session>/subagents/ as
agent-<id>.jsonl plus agent-<id>.meta.json ({"toolUseId", "parentAgentId" when nested}), and the
hook's transcript_path is the main transcript for subagent calls too."""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_agent_control.py"

CTO, STAFF, SENIOR, ANALYST = "a1111111111111111", "a2222222222222222", "a3333333333333333", "a4444444444444444"


def spawn_line(tool_use_id, name="Agent"):
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_use_id, "name": name, "input": {"subagent_type": "x", "prompt": "y"}}]}})


class GuardAgentControl(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        project = Path(self.tmp.name)
        self.transcript = project / "sess.jsonl"
        sub = project / "sess" / "subagents"
        sub.mkdir(parents=True)
        # The CEO (main session) spawned the CTO and the analyst; the CTO spawned Staff; Staff spawned a Senior.
        self.transcript.write_text("\n".join([spawn_line("toolu_cto"), spawn_line("toolu_analyst", "Task")]) + "\n")
        (sub / f"agent-{CTO}.jsonl").write_text(spawn_line("toolu_staff") + "\n")
        (sub / f"agent-{STAFF}.jsonl").write_text(spawn_line("toolu_senior") + "\n")
        (sub / f"agent-{SENIOR}.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "quoting toolu_cto in text is not a spawn"}}) + "\n")
        (sub / f"agent-{ANALYST}.jsonl").write_text("")
        for agent, tool_use, parent in [(CTO, "toolu_cto", None), (ANALYST, "toolu_analyst", None),
                                        (STAFF, "toolu_staff", CTO), (SENIOR, "toolu_senior", STAFF)]:
            meta = {"agentType": "x", "toolUseId": tool_use, **({"parentAgentId": parent} if parent else {})}
            (sub / f"agent-{agent}.meta.json").write_text(json.dumps(meta))

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, tool_input, agent_type="ceo", agent_id=None, tool_name="SendMessage", raw=None):
        payload = {"session_id": "sess", "hook_event_name": "PreToolUse", "tool_name": tool_name,
                   "tool_input": tool_input, "transcript_path": str(self.transcript)}
        if agent_type:
            payload["agent_type"] = agent_type
        if agent_id:
            payload["agent_id"] = agent_id
        return subprocess.run([sys.executable, str(HOOK)], input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, timeout=30)

    def msg(self, to, kind="agent", **extra):
        return {"to": to, "message": "PAUSE: test", "recipient": to, "recipient_kind": kind, **extra}

    def assertAllowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertBlocked(self, result, fragment=""):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(fragment, result.stderr)

    def test_main_session_reaches_its_own_children(self):
        self.assertAllowed(self.run_hook(self.msg(CTO)))
        self.assertAllowed(self.run_hook(self.msg(ANALYST)))  # spawned with the older name, Task
        self.assertAllowed(self.run_hook({"task_id": CTO}, tool_name="TaskStop"))

    def test_subagent_reaches_its_own_children(self):
        self.assertAllowed(self.run_hook(self.msg(STAFF), agent_type="cto", agent_id=CTO))
        self.assertAllowed(self.run_hook({"task_id": SENIOR}, agent_type="staff-engineer", agent_id=STAFF, tool_name="TaskStop"))

    def test_messages_go_one_level_and_never_to_a_sibling(self):
        self.assertBlocked(self.run_hook(self.msg(STAFF)), "wasn't spawned by you")  # the CEO to a grandchild
        self.assertBlocked(self.run_hook(self.msg(ANALYST), agent_type="cto", agent_id=CTO))
        self.assertBlocked(self.run_hook(self.msg(CTO), agent_type="staff-engineer", agent_id=STAFF))  # its launcher, by ID

    def test_a_child_wakes_its_own_launcher_with_one_urgent_line(self):
        for text in ["QUESTION /2.WS-1: which host lands first?", "NEEDS-CTO: the lock is held", "BLOCKED: CI red",
                     "  QUESTION padded  ", "QUESTION " + "x" * 991]:
            with self.subTest(text=text[:30]):
                self.assertAllowed(self.run_hook(self.msg(CTO, message=text), agent_type="staff-engineer", agent_id=STAFF))
        self.assertAllowed(self.run_hook(self.msg(STAFF, message="QUESTION"), agent_type="senior-engineer", agent_id=SENIOR))
        for summary in ["Needs a host", "s" * 100]:
            with self.subTest(summary=summary[:30]):
                self.assertAllowed(self.run_hook(self.msg(CTO, message="NEEDS a host", type="message", summary=summary),
                                                 agent_type="staff-engineer", agent_id=STAFF))
        # Claude Code's own `content`: the message cut to about 50 characters and "…", or all of it.
        line = "NEEDS a host: the upward urgent line, sent after 10:00:00."
        for content in [line[:49] + "…", line]:
            with self.subTest(content=content):
                self.assertAllowed(self.run_hook(self.msg(CTO, message=line, type="message", content=content),
                                                 agent_type="staff-engineer", agent_id=STAFF))

    def test_only_an_urgent_line_and_only_to_the_launcher(self):
        for text in ["PAUSE: test", "REPORT /2: done", "QUESTION one\nsecond line", "QUESTION one\u2028second",
                     "QUESTION " + "x" * 992, "QUESTION x" + " " * 991, "NEEDSX nothing", "question lower case", "",
                     {"type": "QUESTION"}, "\nQUESTION x", "\n\nQUESTION x", " \n QUESTION x", "\tQUESTION x",
                     "\u00a0QUESTION x"]:
            with self.subTest(text=str(text)[:30]):
                self.assertBlocked(self.run_hook(self.msg(CTO, message=text), agent_type="staff-engineer", agent_id=STAFF),
                                   "wasn't spawned by you")
        for kind in ["shutdown_request", "broadcast"]:
            with self.subTest(type=kind):
                self.assertBlocked(self.run_hook(self.msg(CTO, message="QUESTION", type=kind), agent_type="staff-engineer",
                                                 agent_id=STAFF), "wasn't spawned by you")
        self.assertBlocked(self.run_hook(self.msg(CTO, message="QUESTION", recipient=SENIOR), agent_type="staff-engineer",
                                         agent_id=STAFF), "exactly one target")
        # `summary` doesn't reach the recipient today; a build that shows it gets one short line.
        for summary in ["s" * 101, "QUESTION one\nsecond line", "one\u2028two", {"text": "x"}, ["x"], 5]:
            with self.subTest(summary=str(summary)[:30]):
                self.assertBlocked(self.run_hook(self.msg(CTO, message="QUESTION one", summary=summary),
                                                 agent_type="staff-engineer", agent_id=STAFF), "wasn't spawned by you")
        # Another text in `content`, or any other field, could carry more than the one line.
        for extra in [{"content": "PAUSE: other text"}, {"content": "QUESTION one\nsecond line…"},
                      {"content": {"text": "QUESTION"}}, {"body": "more text"}, {"attachments": ["/tmp/x"]}]:
            with self.subTest(extra=str(extra)[:30]):
                self.assertBlocked(self.run_hook(self.msg(CTO, message="QUESTION one", **extra),
                                                 agent_type="staff-engineer", agent_id=STAFF), "wasn't spawned by you")
        self.assertBlocked(self.run_hook(self.msg(CTO, message="QUESTION"), agent_type="senior-engineer", agent_id=SENIOR))
        self.assertBlocked(self.run_hook(self.msg(ANALYST, message="QUESTION"), agent_type="cto", agent_id=CTO))
        self.assertBlocked(self.run_hook(self.msg(CTO, "teammate", message="QUESTION"), agent_type="staff-engineer",
                                         agent_id=STAFF))
        self.assertBlocked(self.run_hook({"task_id": CTO, "message": "QUESTION"}, agent_type="staff-engineer",
                                         agent_id=STAFF, tool_name="TaskStop"))

    def test_an_urgent_line_to_a_sibling_under_a_nested_launcher_is_refused(self):
        sub = self.transcript.with_suffix("") / "subagents"
        sibling = "a5555555555555555"
        (sub / f"agent-{sibling}.meta.json").write_text(json.dumps(
            {"agentType": "x", "toolUseId": "toolu_senior2", "parentAgentId": STAFF}))
        (sub / f"agent-{sibling}.jsonl").write_text("")
        with (sub / f"agent-{STAFF}.jsonl").open("a") as staff:
            staff.write(spawn_line("toolu_senior2") + "\n")
        self.assertBlocked(self.run_hook(self.msg(sibling, message="QUESTION"), agent_type="senior-engineer",
                                         agent_id=SENIOR), "wasn't spawned by you")
        self.assertAllowed(self.run_hook(self.msg(STAFF, message="QUESTION"), agent_type="senior-engineer",
                                         agent_id=sibling))

    def test_an_urgent_line_goes_only_to_a_launcher_whose_transcript_holds_the_spawn(self):
        # Meta files are plain files: a parentAgentId alone doesn't make the named agent the launcher.
        sub = self.transcript.with_suffix("") / "subagents"
        stray = "a9999999999999999"  # an agent with a meta file but no transcript
        (sub / f"agent-{stray}.meta.json").write_text(json.dumps({"agentType": "x", "toolUseId": "toolu_stray"}))
        for launcher in [CTO, ANALYST, stray]:  # CTO started Staff, not this Senior; the analyst started nobody
            with self.subTest(launcher=launcher):
                (sub / f"agent-{SENIOR}.meta.json").write_text(json.dumps(
                    {"agentType": "x", "toolUseId": "toolu_senior", "parentAgentId": launcher}))
                self.assertBlocked(self.run_hook(self.msg(launcher, message="QUESTION"), agent_type="senior-engineer",
                                                 agent_id=SENIOR), "wasn't spawned by you")

    def test_a_senior_or_producer_started_by_a_main_session_sends_it_only_the_urgent_line(self):
        # `claude --agent cto` (or staff-engineer, or cmo) starts a Senior or producer as a child of the main session:
        # it holds SendMessage only for the urgent line.
        for role in ["senior-engineer", "content-producer"]:
            for to in [self.msg("main", "main", message="QUESTION /2.T-3: which host?"),
                       {"to": "main", "message": "BLOCKED: CI red", "summary": "CI red"}]:
                with self.subTest(role=role, to=to):
                    self.assertAllowed(self.run_hook(to, agent_type=role, agent_id=CTO))
            for extra in [{"message": "PAUSE: test"}, {"message": "QUESTION one\nsecond line"},
                          {"message": "\nQUESTION x"}, {"message": "QUESTION " + "x" * 992},
                          {"message": "QUESTION x", "summary": "s" * 101}, {"message": "QUESTION x", "type": "broadcast"},
                          {"message": "QUESTION x", "content": "PAUSE: other text"}]:
                with self.subTest(role=role, extra=str(extra)[:30]):
                    self.assertBlocked(self.run_hook(self.msg("main", "main", **extra), agent_type=role, agent_id=CTO),
                                       "messages its launcher only with one line")
            self.assertBlocked(self.run_hook(self.msg("main", "main", message="QUESTION"), agent_type=role,
                                             agent_id=SENIOR), "'main'")  # not a child of the main session
        self.assertAllowed(self.run_hook(self.msg("main", "main"), agent_type="cto", agent_id=CTO))  # other roles as before

    def test_a_caller_with_no_meta_file_is_checked_as_before(self):
        # An urgent-shaped line from a caller with no record goes through the child check, as on base.
        sub = self.transcript.with_suffix("") / "subagents"
        caller, child = "a6666666666666666", "a7777777777777777"
        (sub / f"agent-{caller}.jsonl").write_text(spawn_line("toolu_child7") + "\n")
        (sub / f"agent-{child}.meta.json").write_text(json.dumps(
            {"agentType": "x", "toolUseId": "toolu_child7", "parentAgentId": caller}))
        self.assertAllowed(self.run_hook(self.msg(child, message="QUESTION down"), agent_type="cto", agent_id=caller))
        self.assertBlocked(self.run_hook(self.msg(CTO, message="QUESTION up"), agent_type="cto", agent_id=caller),
                           "wasn't spawned by you")

    def test_stops_reach_the_callers_own_tree_only(self):
        # Stopping a parent leaves its background children running, so "stop now" goes leaves first.
        self.assertAllowed(self.run_hook({"task_id": SENIOR}, tool_name="TaskStop"))  # the CEO, a great-grandchild
        self.assertAllowed(self.run_hook({"task_id": SENIOR}, agent_type="cto", agent_id=CTO, tool_name="TaskStop"))
        self.assertBlocked(self.run_hook({"task_id": ANALYST}, agent_type="cto", agent_id=CTO, tool_name="TaskStop"))
        self.assertBlocked(self.run_hook({"task_id": CTO}, agent_type="staff-engineer", agent_id=STAFF, tool_name="TaskStop"))
        self.assertBlocked(self.run_hook({"task_id": STAFF}, agent_type="analyst", agent_id=ANALYST, tool_name="TaskStop"))

    def test_an_id_quoted_in_text_is_not_a_spawn(self):
        self.assertBlocked(self.run_hook(self.msg(CTO), agent_type="senior-engineer", agent_id=SENIOR))

    def test_main_only_from_a_child_of_the_main_session(self):
        self.assertAllowed(self.run_hook(self.msg("main", "main"), agent_type="cto", agent_id=CTO))
        self.assertBlocked(self.run_hook(self.msg("main", "main"), agent_type="staff-engineer", agent_id=STAFF), "'main'")
        self.assertBlocked(self.run_hook(self.msg("main", "main")), "'main'")  # the main session itself
        self.assertBlocked(self.run_hook({"task_id": "main"}, agent_type="cto", agent_id=CTO, tool_name="TaskStop"))

    def test_names_sessions_and_teammates_are_refused(self):
        for to, kind in [("my-session", "session"), ("example-co-1 [abc123]", None), ("cto", None),
                         (CTO, "teammate"), ("../sess", "agent")]:
            with self.subTest(to=to):
                self.assertBlocked(self.run_hook(self.msg(to, kind)))

    def test_a_refused_stop_lists_the_callers_tree_leaves_first(self):
        result = self.run_hook({"task_id": "no-such-task"}, tool_name="TaskStop")
        self.assertBlocked(result, "leaves first")
        order = [result.stderr.index(a) for a in (SENIOR, STAFF, CTO)]
        self.assertEqual(order, sorted(order), result.stderr)
        result = self.run_hook({"task_id": "no-such-task"}, agent_type="cto", agent_id=CTO, tool_name="TaskStop")
        self.assertNotIn(ANALYST, result.stderr)
        self.assertNotIn(CTO, result.stderr.split("leaves first")[1])

    def test_a_refused_stop_lists_at_most_20_unfinished_agents_most_recently_active_first(self):
        # a long session holds well over a thousand agents
        sub = self.transcript.with_suffix("") / "subagents"
        with self.transcript.open("a", encoding="utf-8") as transcript:
            for i in range(40):
                transcript.write(spawn_line(f"toolu_c{i}") + "\n")
                meta = {"agentType": "x", "toolUseId": f"toolu_c{i}", "description": "é" * 500,  # 2 bytes each
                        **({"finished": True} if i % 2 else {})}
                (sub / f"agent-c{i:016d}.meta.json").write_text(json.dumps(meta))
                (sub / f"agent-c{i:016d}.jsonl").write_text("")
                os.utime(sub / f"agent-c{i:016d}.jsonl", (2e9 + i, 2e9 + i))  # newer than the fixture's four
        result = self.run_hook({"task_id": "no-such-task"}, tool_name="TaskStop")
        self.assertBlocked(result, "leaves first")
        self.assertLess(len(result.stderr.encode()), 4096)
        self.assertEqual(re.findall(r"c\d{16}", result.stderr), [f"c{i:016d}" for i in range(38, -1, -2)])
        self.assertIn("; and 4 less recently active.", result.stderr)  # the fixture's CTO, analyst, Staff and Senior
        self.assertNotIn(SENIOR, result.stderr)

    def test_a_refusal_cuts_a_long_target_so_it_stays_under_4096_bytes(self):
        sub = self.transcript.with_suffix("") / "subagents"
        with self.transcript.open("a", encoding="utf-8") as transcript:
            for i in range(25):  # past SHOWN, each label at its longest
                transcript.write(spawn_line(f"toolu_l{i}") + "\n")
                (sub / f"agent-l{i:016d}.meta.json").write_text(json.dumps(
                    {"agentType": "x", "toolUseId": f"toolu_l{i}", "description": "é" * 500}))
        for target, tool_name in [("x" * 100_000, "TaskStop"), ("é" * 100_000, "TaskStop"),
                                  ("x" * 100_000, "SendMessage")]:
            with self.subTest(target=target[:3], tool_name=tool_name):
                tool_input = {"task_id": target} if tool_name == "TaskStop" else self.msg(target)
                result = self.run_hook(tool_input, tool_name=tool_name)
                self.assertBlocked(result, "isn't an agent ID")
                self.assertIn(f"'{target.encode()[:120].decode('utf-8', 'ignore')}…'", result.stderr)  # LABEL bytes
                self.assertLess(len(result.stderr.encode()), 4096)

    def test_a_spawn_on_a_line_with_a_unicode_line_separator_counts(self):
        # Transcript lines end only at \n; str.splitlines() also splits at U+2028, and would miss this spawn.
        line = json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_sep", "name": "Agent", "input": {"prompt": "a b"}}]}},
            ensure_ascii=False)
        with self.transcript.open("a", encoding="utf-8") as transcript:
            transcript.write(line + "\n")
        sub = self.transcript.with_suffix("") / "subagents"
        (sub / "agent-a5555555555555555.meta.json").write_text(json.dumps({"agentType": "x", "toolUseId": "toolu_sep"}))
        self.assertAllowed(self.run_hook({"task_id": "a5555555555555555"}, tool_name="TaskStop"))

    def test_a_refused_stop_reads_the_callers_transcript_once(self):
        # one read per agent of a long session's transcript would time the hook out
        sub = self.transcript.with_suffix("") / "subagents"
        for i in range(200):
            (sub / f"agent-b{i:016d}.meta.json").write_text(json.dumps({"agentType": "x", "toolUseId": f"toolu_{i}"}))
        spec = importlib.util.spec_from_file_location("guard_agent_control_under_test", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        reads, real_open = [], open

        def counting_open(path, *args, **kwargs):
            reads.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", counting_open), mock.patch("io.open", counting_open):  # Path.read_text too
            tree = hook.own_tree(self.transcript.with_suffix(""), self.transcript, None)
        self.assertEqual(reads.count(str(self.transcript)), 1)
        self.assertEqual(len(tree), 4, tree)  # the CTO, the analyst, Staff and the Senior; none of the 200 others

    def test_the_target_fields_must_agree(self):
        self.assertBlocked(self.run_hook({**self.msg(CTO), "recipient": ANALYST}), "exactly one target")
        self.assertBlocked(self.run_hook({"task_id": CTO, "shell_id": ANALYST}, tool_name="TaskStop"), "exactly one target")
        self.assertBlocked(self.run_hook(self.msg(CTO), agent_type="cto", agent_id="../x"), "malformed")

    def test_main_needs_the_main_kind_and_a_real_spawn(self):
        self.assertBlocked(self.run_hook(self.msg("main", "session"), agent_type="cto", agent_id=CTO))
        sub = self.transcript.with_suffix("") / "subagents"
        (sub / "agent-a5555555555555555.meta.json").write_text("{}")  # no spawn behind it
        self.assertBlocked(self.run_hook(self.msg("main", "main"), agent_type="x", agent_id="a5555555555555555"))

    def test_a_spawn_counts_only_from_the_assistant(self):
        sub = self.transcript.with_suffix("") / "subagents"
        fake = json.loads(spawn_line("toolu_staff")); fake["message"]["role"] = "user"
        (sub / f"agent-{ANALYST}.jsonl").write_text(json.dumps(fake) + "\n")
        self.assertBlocked(self.run_hook(self.msg(STAFF), agent_type="analyst", agent_id=ANALYST))

    def test_notify_when_idle_is_refused(self):
        self.assertBlocked(self.run_hook(self.msg(CTO, notify_when_idle=True)), "notify_when_idle")

    def test_plain_session_is_not_limited(self):
        self.assertAllowed(self.run_hook(self.msg("my-session", "session", notify_when_idle=True), agent_type=None))
        self.assertAllowed(self.run_hook({"task_id": "b1234567a"}, agent_type=None, tool_name="TaskStop"))

    def test_fails_closed(self):
        self.assertBlocked(self.run_hook({}, raw="not json"))
        self.assertBlocked(self.run_hook(self.msg("a9999999999999999")), "isn't an agent of this session")
        self.transcript.unlink()
        self.assertBlocked(self.run_hook(self.msg(CTO)))

    def test_other_tools_pass(self):
        self.assertAllowed(self.run_hook({"command": "ls"}, tool_name="Bash"))


if __name__ == "__main__":
    unittest.main()
