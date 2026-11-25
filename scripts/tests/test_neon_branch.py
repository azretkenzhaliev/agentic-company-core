"""Tests for scripts/hooks/neon_branch.py, through the hook that calls it (guard_marketing_tools.py, on .claude/settings.json's
mcp__.* matcher), run as Claude Code runs it: JSON on stdin, exit 2 plus stderr to block, exit 0 to let through."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_marketing_tools.py"
UPDATE = "mcp__claude_ai_Neon__update_branch"
NEON = "mcp__claude_ai_Neon__"
PROJECT = "demo-project"
MADE = "2026-01-05T09:30:20Z"  # created_at as Neon's reads give it; long past, so the 24-hour floor is behind us
PRODUCTION = {"id": "br-prod", "project_id": PROJECT, "name": "production", "primary": True, "default": True,
              "protected": False, "created_at": "2026-01-01T09:00:00Z"}
BACKUP = {"id": "br-backup", "project_id": PROJECT, "parent_id": "br-prod", "name": "backup-pre-0007",
          "primary": False, "default": False, "protected": False, "created_at": MADE}
GATE = {"id": "br-gate", "project_id": PROJECT, "parent_id": "br-prod", "name": "gate-dd101-t3",
        "primary": False, "default": False, "protected": False, "created_at": MADE}
DEV = {"id": "br-dev", "project_id": PROJECT, "parent_id": "br-prod", "name": "dev-alex", "primary": False,
       "default": False, "protected": False, "created_at": MADE}


def stamp(t):
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


def envelope(result):
    """A branch tool's result as the connector may wrap it: one compact string."""
    return json.dumps({"data": result}, separators=(",", ":"))


DEFAULTS = ["br-demo-main", "br-acme-production"]  # the company's own, as company.json names them


class NeonBranch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.log = self.root / "workspaces" / "neon-sql-audit.log"
        self.company({"default_branches": DEFAULTS})
        self.main = self.root / "projects" / "session-1.jsonl"
        (self.root / "projects" / "session-1" / "subagents").mkdir(parents=True)
        self.now = datetime.now(timezone.utc)
        self.calls = 0

    def tearDown(self):
        self.tmp.cleanup()

    def company(self, neon, text=None):
        """Writes the company.json the hook reads, with these "neon" settings (None: without any)."""
        (self.root / "company.json").write_text(
            text if text is not None else json.dumps({"integrations": {} if neon is None else {"neon": neon}}), encoding="utf-8")

    def transcript(self, agent_id="a1"):
        return self.main if agent_id is None else self.root / "projects" / "session-1" / "subagents" / f"agent-{agent_id}.jsonl"

    def read(self, result, tool="list_branches", agent_id="a1", ago=timedelta(minutes=1), is_error=False, wrapped=False):
        """Append a Neon read and its result to the caller's transcript, as Claude Code writes them; its tool_use id.
        wrapped: in the connector's envelope."""
        self.calls += 1
        use_id = f"toolu_{self.calls}"
        when = (self.now - ago).isoformat(timespec="milliseconds").replace("+00:00", "Z")  # Claude Code's form
        lines = [
            {"type": "assistant", "timestamp": when, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": use_id, "name": NEON + tool, "input": {"project_id": PROJECT}}]}},
            {"type": "user", "timestamp": when, "message": {"role": "user", "content": [
                {"tool_use_id": use_id, "type": "tool_result", "is_error": is_error,
                 "content": envelope(result) if wrapped else [{"type": "text", "text": json.dumps(result, indent=2)}]}]}},
        ]
        self.append(*lines, agent_id=agent_id)
        return use_id

    def append(self, *lines, agent_id="a1"):
        with self.transcript(agent_id).open("a", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")

    def compacted(self, use_id, result, agent_id="a1", wrapped=False, **fields):
        """Append what a context compaction writes: an api-request-blob entry with no
        timestamp, carrying a result for an earlier tool_use id."""
        entry = {"type": "api-request-blob", "sessionId": "session-1", "agentId": agent_id, "hash": "h", **fields,
                 "message": {"role": "user", "content": [
                     {"tool_use_id": use_id, "type": "tool_result",
                      "content": envelope(result) if wrapped else [{"type": "text", "text": json.dumps(result, indent=2)}]}]}}
        self.append(entry, agent_id=agent_id)

    def run_hook(self, tool_input, tool_name=UPDATE, agent_type="cto", agent_id="a1", raw=None, transcript=None):
        payload = {
            "session_id": "session-1",
            "transcript_path": str(transcript or self.main),
            "cwd": str(self.root),
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "agent_type": agent_type,
        }
        if agent_id is not None:
            payload["agent_id"] = agent_id
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=raw if raw is not None else json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def expire(self, branch_id="br-backup", ahead=timedelta(days=7), **kw):
        return self.run_hook({"project_id": PROJECT, "branch_id": branch_id, "expires_at": stamp(self.now + ahead)}, **kw)

    def log_lines(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def assertPassed(self, result):
        """Let through, and not approved: Claude Code's own permission check still decides."""
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def assertBlocked(self, result, reason):
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(reason, result.stderr)
        self.assertEqual(result.stdout, "")

    # Let through: an expiry, and nothing else, on a backup- or gate- branch the caller read.

    def test_passes_an_expiry_on_a_backup_from_list_branches(self):
        self.read([PRODUCTION, BACKUP, GATE])
        self.assertPassed(self.expire())
        self.assertPassed(self.expire("br-gate"))

    def test_passes_a_branch_read_with_get_branch_or_just_created(self):
        self.read(GATE, tool="get_branch")
        self.assertPassed(self.expire("br-gate"))
        self.read(BACKUP, tool="create_branch")
        self.assertPassed(self.expire())

    def test_passes_from_30_seconds_to_30_days_ahead_in_any_zone(self):
        self.read([PRODUCTION, BACKUP])
        self.assertPassed(self.expire(ahead=timedelta(seconds=30)))
        self.assertPassed(self.expire(ahead=timedelta(days=30, minutes=-1)))
        offset = (self.now + timedelta(days=7)).astimezone(timezone(timedelta(hours=6))).isoformat(timespec="seconds")
        self.assertPassed(self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "expires_at": offset}))

    def test_passes_a_staff_engineer_and_a_main_session_cto(self):
        self.read([PRODUCTION, BACKUP], agent_id="b2")
        self.assertPassed(self.expire(agent_type="staff-engineer", agent_id="b2"))
        self.read([PRODUCTION, BACKUP], agent_id=None)  # `claude --agent cto`: no agent_id, the main transcript
        self.assertPassed(self.expire(agent_id=None))

    # Refused: anything but an expiry.

    def test_refuses_any_other_change(self):
        self.read([PRODUCTION, BACKUP])
        until = stamp(self.now + timedelta(days=7))
        for extra, value in [("name", "backup-renamed"), ("name", None), ("protected", True), ("protected", False),
                             ("parent_id", "br-prod"), ("compute", True), ("no_compute", True)]:
            with self.subTest(extra=extra, value=value):
                result = self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "expires_at": until, extra: value})
                self.assertBlocked(result, f"changes more than the expiry ({extra})")

    def test_refuses_a_rename_or_protection_without_an_expiry(self):
        self.read([PRODUCTION, BACKUP])
        self.assertBlocked(self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "name": "x"}), "(name)")
        self.assertBlocked(self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "protected": True}),
                           "(protected)")

    def test_refuses_removing_or_a_bad_expiry(self):
        self.read([PRODUCTION, BACKUP])
        for value in [None, "", "2026-01-18", "2026-01-18T12:00:00", "next week", 1768737600, ["2026-01-18T12:00:00Z"]]:
            with self.subTest(expires_at=value):
                result = self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "expires_at": value})
                self.assertBlocked(result, "a time with a zone")
        self.assertBlocked(self.run_hook({"project_id": PROJECT, "branch_id": "br-backup"}), "a time with a zone")

    def test_refuses_an_expiry_now_past_or_beyond_30_days(self):
        self.read([PRODUCTION, BACKUP])
        for ahead in [timedelta(0), timedelta(minutes=-5), timedelta(days=-3), timedelta(days=30, minutes=5),
                      timedelta(days=365)]:
            with self.subTest(ahead=ahead):
                self.assertBlocked(self.expire(ahead=ahead), "after now and at most 30 days ahead")

    # Refused: an expiry earlier than a day after the branch was made.

    def test_refuses_an_expiry_earlier_than_24_hours_after_created_at(self):
        made = (self.now - timedelta(hours=1)).replace(microsecond=0)
        self.read([PRODUCTION, BACKUP], ago=timedelta(minutes=5))  # created_at MADE, long past
        self.read(dict(BACKUP, created_at=stamp(made)), tool="create_branch")  # the latest read decides

        def until(t):
            return self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "expires_at": stamp(t)})

        floor = "at least 24 hours after br-backup was made"
        for at in [made + timedelta(minutes=90), made + timedelta(hours=7), made + timedelta(hours=24, seconds=-1)]:
            with self.subTest(at=at):  # a 6-hour restore window, and a second short of the day
                self.assertBlocked(until(at), floor)
        self.assertPassed(until(made + timedelta(hours=24)))
        self.assertPassed(until(made + timedelta(days=7)))
        self.read([PRODUCTION, dict(GATE, created_at=stamp(self.now - timedelta(minutes=2)))])  # another session's
        self.assertBlocked(self.expire("br-gate", ahead=timedelta(hours=12)), "at least 24 hours after br-gate")
        self.read([PRODUCTION, dict(BACKUP, created_at=stamp(self.now + timedelta(hours=1)))])  # dated after now
        self.assertBlocked(self.expire(ahead=timedelta(hours=12)), floor)
        self.assertBlocked(self.expire(ahead=timedelta(hours=24, minutes=30)), floor)  # the floor counts from created_at

    def test_refuses_an_expiry_one_hour_after_created_at(self):
        # created_at + 1 h is refused by the floor, wherever created_at falls.
        floor = "at least 24 hours after br-backup was made"
        for made in [self.now - timedelta(minutes=30), self.now - timedelta(hours=1), self.now + timedelta(hours=1)]:
            made = made.replace(microsecond=0)
            with self.subTest(made=made):
                self.read([PRODUCTION, dict(BACKUP, created_at=stamp(made))])
                at = stamp(made + timedelta(hours=1))
                self.assertBlocked(self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "expires_at": at}), floor)

    def test_refuses_a_read_without_a_parseable_created_at(self):
        for created in [None, "", "2026-01-05T09:30:20", "yesterday", 1767605420, [MADE]]:
            with self.subTest(created_at=created):
                self.read([PRODUCTION, dict(BACKUP, created_at=created)])
                self.assertBlocked(self.expire(), "no created_at")
        self.read([PRODUCTION, {k: v for k, v in BACKUP.items() if k != "created_at"}])
        self.assertBlocked(self.expire(), "no created_at")
        self.read([PRODUCTION, dict(BACKUP, created_at="9999-12-31T23:59:59Z")])  # the floor overflows
        self.assertBlocked(self.expire(), "couldn't check the call")
        self.read([PRODUCTION, BACKUP])
        self.assertPassed(self.expire())

    # Refused: the default branch, other names, a branch with children.

    def test_refuses_the_default_branch_whatever_its_name(self):
        self.read([PRODUCTION, BACKUP])
        self.assertBlocked(self.expire("br-prod"), "default branch")
        self.read([dict(PRODUCTION, name="backup-production")])
        self.assertBlocked(self.expire("br-prod"), "default branch")
        for fields in [{"default": False, "primary": True}, {"default": None}, {"default": "false"}]:
            with self.subTest(fields=fields):
                self.read([dict(BACKUP, **fields)])
                self.assertBlocked(self.expire(), "default branch")
        self.read([{k: v for k, v in BACKUP.items() if k != "default"}])
        self.assertBlocked(self.expire(), "default branch")

    def test_refuses_a_company_default_branch_whatever_the_transcript_says(self):
        for branch_id in DEFAULTS:
            with self.subTest(branch_id=branch_id):
                self.read([dict(BACKUP, id=branch_id)])  # a read that says backup-, not default, no children
                reason = f"{branch_id} is a default branch of the company's Neon projects"
                self.assertBlocked(self.expire(branch_id), reason)
                missing = self.root / "projects" / "no-such-session.jsonl"  # refused before any transcript is read
                self.assertBlocked(self.expire(branch_id, transcript=missing, agent_id=None), reason)
                self.assertEqual(self.log_lines()[-1]["branch_id"], branch_id)

    def test_without_the_default_branches_every_call_is_refused(self):
        self.read([PRODUCTION, BACKUP])
        self.assertPassed(self.expire())
        for neon in [None, {}, {"default_branches": []}, {"default_branches": None}]:
            with self.subTest(neon=neon):
                self.company(neon)
                self.assertBlocked(self.expire(), "names no default_branches")
        (self.root / "company.json").unlink()
        self.assertBlocked(self.expire(), "names no default_branches")

    def test_a_broken_company_json_refuses_every_call(self):
        self.read([PRODUCTION, BACKUP])
        for text in ["{", "[]", '{"integrations": []}', '{"integrations": {"neon": true}}',
                     '{"integrations": {"neon": {"default_branches": "br-demo-main"}}}',
                     '{"integrations": {"neon": {"default_branches": ["production"]}}}']:
            with self.subTest(text=text):
                self.company(None, text)
                self.assertBlocked(self.expire(), "couldn't check the call")

    def test_refuses_a_branch_id_that_isnt_a_br_id(self):
        for branch_id in ["production", "main", "BR-DEMO-MAIN", " br-backup", "br-backup\n", "br-"]:
            with self.subTest(branch_id=branch_id):
                self.read([dict(BACKUP, id=branch_id)])
                self.assertBlocked(self.expire(branch_id), "must be a br- id")

    def test_refuses_a_protected_branch(self):
        for protected in [True, "true", 1]:
            with self.subTest(protected=protected):
                self.read([PRODUCTION, dict(BACKUP, protected=protected)])
                self.assertBlocked(self.expire(), "protected; a protected branch never gets an expiry")
        self.read([PRODUCTION, BACKUP])  # the latest read decides
        self.assertPassed(self.expire())

    def test_refuses_other_names(self):
        for name in ["dev-alex", "production", "Backup-x", "my-backup-x", "gate", "backup", None, 7]:
            with self.subTest(name=name):
                self.read([PRODUCTION, dict(DEV, name=name)])
                self.assertBlocked(self.expire("br-dev"), "only backup- and gate- branches")

    def test_refuses_a_branch_with_a_child_the_caller_read(self):
        self.read([PRODUCTION, BACKUP, dict(DEV, id="br-child", parent_id="br-backup")])
        self.assertBlocked(self.expire(), "has br-backup as its parent")
        self.read(BACKUP, tool="get_branch")  # a later read without the child still sees it
        self.assertBlocked(self.expire(), "has br-backup as its parent")

    # Refused: no fresh read of the branch by the caller.

    def test_refuses_a_branch_the_caller_never_read(self):
        self.read([PRODUCTION, GATE])
        self.assertBlocked(self.expire(), "read it first")
        self.read([PRODUCTION, BACKUP], agent_id="other")  # another agent's read isn't the caller's
        self.assertBlocked(self.expire(), "read it first")

    def test_refuses_a_read_older_than_30_minutes_or_dated_after_now(self):
        self.read([PRODUCTION, BACKUP], ago=timedelta(minutes=31))
        self.assertBlocked(self.expire(), "more than 30 minutes old")
        self.read([PRODUCTION, BACKUP], ago=timedelta(minutes=-5))  # dated after now
        self.assertBlocked(self.expire(), "dated after now")
        self.read([PRODUCTION, BACKUP], ago=timedelta(minutes=2))
        self.assertPassed(self.expire())

    def test_the_latest_read_decides(self):
        self.read([PRODUCTION, BACKUP], ago=timedelta(minutes=5))
        self.read([PRODUCTION, dict(BACKUP, name="feature-x")], ago=timedelta(minutes=1))
        self.assertBlocked(self.expire(), "named 'feature-x'")

    # A context compaction: an entry with no timestamp copying an earlier result.

    def test_a_compacted_copy_of_a_fresh_read_doesnt_refuse(self):
        use_id = self.read([PRODUCTION, BACKUP], ago=timedelta(minutes=5))
        self.compacted(use_id, [PRODUCTION, BACKUP])
        self.assertPassed(self.expire())

    def test_the_latest_timestamped_read_decides_with_every_check(self):
        good = [PRODUCTION, BACKUP]
        made = stamp((self.now - timedelta(hours=1)).replace(microsecond=0))
        for branch, ago, ahead, reason in [
            (BACKUP, timedelta(minutes=31), timedelta(days=7), "more than 30 minutes old"),
            (BACKUP, timedelta(minutes=-5), timedelta(days=7), "dated after now"),
            (dict(BACKUP, created_at=made), timedelta(minutes=1), timedelta(hours=12),
             "at least 24 hours after br-backup was made"),
            ({k: v for k, v in BACKUP.items() if k != "created_at"}, timedelta(minutes=1), timedelta(days=7),
             "no created_at"),
            (dict(BACKUP, name="dev-alex"), timedelta(minutes=1), timedelta(days=7), "only backup- and gate-"),
            (dict(BACKUP, default=True), timedelta(minutes=1), timedelta(days=7), "is, or may be, the default branch"),
            (dict(BACKUP, protected=True), timedelta(minutes=1), timedelta(days=7), "is, or may be, protected"),
            (dict(BACKUP, project_id="other"), timedelta(minutes=1), timedelta(days=7), "read in project other"),
        ]:
            with self.subTest(reason=reason):
                use_id = self.read([PRODUCTION, branch], ago=ago)
                self.compacted(use_id, good)  # an untimed entry showing a good branch doesn't decide
                self.assertBlocked(self.expire(ahead=ahead), reason)
        use_id = self.read(good)
        self.compacted(use_id, good)
        self.assertBlocked(self.expire(agent_type="senior-engineer"), "only the cto and staff-engineer")
        self.assertBlocked(self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "name": "backup-x",
                                          "expires_at": stamp(self.now + timedelta(days=7))}), "(name)")
        self.assertBlocked(self.expire(ahead=timedelta(days=31)), "after now and at most 30 days ahead")
        self.assertPassed(self.expire())

    def test_a_child_in_any_read_refuses_timestamped_or_not(self):
        use_id = self.read([PRODUCTION, BACKUP], ago=timedelta(minutes=5))
        self.compacted(use_id, [PRODUCTION, BACKUP, dict(DEV, id="br-child", parent_id="br-backup")])
        self.assertBlocked(self.expire(), "has br-backup as its parent")
        self.read(BACKUP, tool="get_branch")  # the latest timestamped read shows no child
        self.assertBlocked(self.expire(), "has br-backup as its parent")

    def test_refuses_when_only_reads_without_a_timestamp_show_the_branch(self):
        for fields in [{}, {"timestamp": None}, {"timestamp": ""}, {"timestamp": "yesterday"},
                       {"timestamp": "2026-01-16T15:20:40"}, {"timestamp": 1768576840}]:
            with self.subTest(fields=fields):
                use_id = self.read([PRODUCTION, GATE])  # its timestamped result doesn't show br-backup
                self.compacted(use_id, [PRODUCTION, BACKUP], **fields)
                self.assertBlocked(self.expire(), "read it again")

    def test_refuses_a_read_from_another_project(self):
        self.read([PRODUCTION, BACKUP])
        result = self.run_hook({"project_id": "other-project", "branch_id": "br-backup",
                                "expires_at": stamp(self.now + timedelta(days=7))})
        self.assertBlocked(result, "not other-project")

    def test_only_neon_branch_reads_count(self):
        self.read([PRODUCTION, BACKUP], tool="run_sql")
        self.assertBlocked(self.expire(), "read it first")
        self.read([PRODUCTION, BACKUP], is_error=True)
        self.assertBlocked(self.expire(), "read it first")
        with self.transcript().open("a", encoding="utf-8") as f:  # a Bash result that prints a branch
            f.write(json.dumps({"type": "user", "timestamp": stamp(self.now), "message": {"role": "user", "content": [
                {"tool_use_id": "toolu_bash", "type": "tool_result", "content": json.dumps(BACKUP)}]}}) + "\n")
        self.assertBlocked(self.expire(), "read it first")

    # The connector's envelope: {"data": …}.

    def test_passes_a_read_in_the_envelope(self):
        self.read([PRODUCTION, BACKUP, GATE], wrapped=True)
        self.assertPassed(self.expire())
        self.assertPassed(self.expire("br-gate"))
        self.read(BACKUP, tool="get_branch", agent_id="b2", wrapped=True)
        self.assertPassed(self.expire(agent_type="staff-engineer", agent_id="b2"))
        self.read(GATE, tool="create_branch", agent_id="b3", wrapped=True)
        self.assertPassed(self.expire("br-gate", agent_type="staff-engineer", agent_id="b3"))

    def test_every_check_holds_for_a_read_in_the_envelope(self):
        made = stamp((self.now - timedelta(hours=1)).replace(microsecond=0))
        for branch, ago, ahead, reason in [
            (BACKUP, timedelta(minutes=31), timedelta(days=7), "more than 30 minutes old"),
            (BACKUP, timedelta(minutes=-5), timedelta(days=7), "dated after now"),
            (dict(BACKUP, created_at=made), timedelta(minutes=1), timedelta(hours=12),
             "at least 24 hours after br-backup was made"),
            ({k: v for k, v in BACKUP.items() if k != "created_at"}, timedelta(minutes=1), timedelta(days=7),
             "no created_at"),
            (dict(BACKUP, name="dev-alex"), timedelta(minutes=1), timedelta(days=7), "only backup- and gate-"),
            (dict(BACKUP, default=True), timedelta(minutes=1), timedelta(days=7), "is, or may be, the default branch"),
            (dict(BACKUP, primary=True), timedelta(minutes=1), timedelta(days=7), "is, or may be, the default branch"),
            (dict(BACKUP, protected=True), timedelta(minutes=1), timedelta(days=7), "is, or may be, protected"),
            (dict(BACKUP, project_id="other"), timedelta(minutes=1), timedelta(days=7), "read in project other"),
            (BACKUP, timedelta(minutes=1), timedelta(days=31), "after now and at most 30 days ahead"),
        ]:
            for tool, result in [("list_branches", [PRODUCTION, branch]), ("get_branch", branch), ("create_branch", branch)]:
                with self.subTest(reason=reason, tool=tool):
                    self.read(result, tool=tool, ago=ago, wrapped=True)
                    self.assertBlocked(self.expire(ahead=ahead), reason)
        self.read([PRODUCTION, BACKUP], wrapped=True)
        self.assertBlocked(self.expire(agent_type="senior-engineer"), "only the cto and staff-engineer")
        self.assertBlocked(self.run_hook({"project_id": PROJECT, "branch_id": "br-backup", "name": "backup-x",
                                          "expires_at": stamp(self.now + timedelta(days=7))}), "(name)")
        self.read([PRODUCTION, BACKUP], is_error=True, agent_id="b2", wrapped=True)
        self.assertBlocked(self.expire(agent_id="b2"), "read it first")
        self.read([PRODUCTION, BACKUP], tool="run_sql", agent_id="b2", wrapped=True)
        self.assertBlocked(self.expire(agent_id="b2"), "read it first")

    def test_the_envelope_and_the_plain_shape_are_read_together(self):
        self.read([PRODUCTION, BACKUP], ago=timedelta(minutes=5), wrapped=True)
        self.read(dict(BACKUP, name="feature-x"), tool="get_branch")
        self.assertBlocked(self.expire(), "named 'feature-x'")  # the latest decides, whichever its shape
        self.read(dict(BACKUP, name="feature-y"), tool="get_branch", wrapped=True)
        self.assertBlocked(self.expire(), "named 'feature-y'")
        use_id = self.read(BACKUP, tool="get_branch", wrapped=True)
        self.compacted(use_id, dict(BACKUP, name="feature-z"), wrapped=True)  # an untimed copy still doesn't decide
        self.assertPassed(self.expire())
        self.compacted(use_id, [PRODUCTION, BACKUP, dict(DEV, id="br-child", parent_id="br-backup")], wrapped=True)
        self.read(BACKUP, tool="get_branch")
        self.assertBlocked(self.expire(), "has br-backup as its parent")  # any read's children count
        self.read(GATE, agent_id="b2", wrapped=True)
        self.compacted(self.read(GATE, agent_id="b2", wrapped=True), BACKUP, agent_id="b2", wrapped=True)
        self.assertBlocked(self.expire(agent_id="b2"), "read it again")  # only an untimed copy shows it

    def test_only_the_exact_envelope_is_opened(self):
        for result in [{"data": [PRODUCTION, BACKUP], "next": None}, {"data": BACKUP, "id": "br-backup-2"},
                       {"data": {"data": BACKUP}}, {"data": {"branch": BACKUP}}, {"data": [[BACKUP]]},
                       {"data": json.dumps(BACKUP)}, {"data": None}, {"Data": BACKUP}, {"branches": [BACKUP]},
                       [{"data": BACKUP}]]:
            with self.subTest(result=result):
                self.read(result)
                self.assertBlocked(self.expire(), "read it first")
        self.read([PRODUCTION, BACKUP], wrapped=True)
        self.assertPassed(self.expire())

    # Not the caller's own read, though it shows the same envelope.

    def test_another_agents_read_isnt_the_callers(self):
        self.read(GATE, wrapped=True)
        for other in ["other", "a1-child", None]:  # another agent's, its own child's, the main session's
            with self.subTest(other=other):
                self.read([PRODUCTION, BACKUP], agent_id=other, wrapped=True)
                self.assertBlocked(self.expire(), "read it first")

    def test_a_message_isnt_a_read(self):
        use_id = self.read(GATE, wrapped=True)
        text, when = envelope([PRODUCTION, BACKUP]), stamp(self.now)

        def entry(role, content):
            return {"type": role, "timestamp": when, "message": {"role": role, "content": content}}

        def call(name, n):
            return entry("assistant", [{"type": "tool_use", "id": f"toolu_{name}_{n}", "name": name, "input": {"prompt": text}}])

        for n, lines in enumerate([
            [entry("user", text)],  # a manager's message, an order
            [entry("user", [{"type": "text", "text": text}])],
            [entry("assistant", [{"type": "text", "text": text}])],  # the caller's own words
            [call("Agent", 1), entry("user", [{"type": "tool_result", "tool_use_id": "toolu_Agent_1", "content": text}])],
            [call("SendMessage", 2),
             entry("user", [{"type": "tool_result", "tool_use_id": "toolu_SendMessage_2", "content": text}])],
            [entry("user", [{"type": "text", "tool_use_id": use_id, "content": text, "text": text}])],  # not a tool_result
            [entry("user", [{"type": "tool_use", "id": "toolu_said", "name": NEON + "list_branches", "input": {}}]),
             entry("user", [{"type": "tool_result", "tool_use_id": "toolu_said", "content": text}])],  # not the caller's call
            [entry("user", [{"type": "tool_result", "tool_use_id": "toolu_unknown", "content": text}])],
            [{"type": "attachment", "timestamp": when, "attachment": {"type": "queued_command", "prompt": text}}],
        ]):
            with self.subTest(n=n):
                self.append(*lines)
                self.assertBlocked(self.expire(), "read it first")

    def test_a_file_the_caller_could_have_written_isnt_a_read(self):
        self.read(GATE, wrapped=True)
        text, when = envelope([PRODUCTION, BACKUP]), stamp(self.now)
        for name in ["Read", "Bash", "Write", "Grep"]:
            with self.subTest(name=name):
                self.append(
                    {"type": "assistant", "timestamp": when, "message": {"role": "assistant", "content": [
                        {"type": "tool_use", "id": f"toolu_{name}", "name": name,
                         "input": {"file_path": f"/x/{NEON}list_branches.txt", "content": text}}]}},
                    {"type": "user", "timestamp": when, "message": {"role": "user", "content": [
                        {"tool_use_id": f"toolu_{name}", "type": "tool_result", "content": text}]},
                     "toolUseResult": text})
                self.assertBlocked(self.expire(), "read it first")
        # A read whose result only names a file it was saved to, though the file holds the envelope.
        saved = self.root / "list_branches.txt"
        saved.write_text(text, encoding="utf-8")
        for note in [f"Output has been saved to {saved}", f"<persisted-output>\nFull output saved to: {saved}\n{text}\n"]:
            with self.subTest(note=note[:20]):
                self.append(
                    {"type": "assistant", "timestamp": when, "message": {"role": "assistant", "content": [
                        {"type": "tool_use", "id": "toolu_long", "name": NEON + "list_branches", "input": {}}]}},
                    {"type": "user", "timestamp": when, "message": {"role": "user", "content": [
                        {"tool_use_id": "toolu_long", "type": "tool_result", "content": note}]}})
                self.assertBlocked(self.expire(), "read it first")

    # Refused: other callers, unreadable input (fail closed).

    def test_refuses_other_callers(self):
        self.read([PRODUCTION, BACKUP])
        for agent_type in ["senior-engineer", "ceo", "general-purpose", "cmo", None]:
            with self.subTest(agent_type=agent_type):
                self.assertBlocked(self.expire(agent_type=agent_type), "only the cto and staff-engineer")

    def test_refuses_unreadable_input(self):
        self.read([PRODUCTION, BACKUP])
        self.assertBlocked(self.run_hook({}, raw="not json"), "fail closed")
        self.assertBlocked(self.run_hook("br-backup"), "isn't an object")
        until = stamp(self.now + timedelta(days=7))
        self.assertBlocked(self.run_hook({"branch_id": "br-backup", "expires_at": until}), "give both")
        self.assertBlocked(self.run_hook({"project_id": PROJECT, "expires_at": until}), "give both")
        self.assertBlocked(self.run_hook({"project_id": PROJECT, "branch_id": 7, "expires_at": until}), "give both")

    def test_refuses_when_the_transcript_cant_be_read(self):
        self.read([PRODUCTION, BACKUP])
        self.assertBlocked(self.expire(agent_id="../../x"), "couldn't check the call")
        self.assertBlocked(self.expire(agent_id="nobody"), "couldn't check the call")
        self.assertBlocked(self.expire(agent_id=None, transcript=self.root / "missing.jsonl"), "couldn't check the call")
        payload = {"tool_name": UPDATE, "agent_type": "cto",
                   "tool_input": {"project_id": PROJECT, "branch_id": "br-backup",
                                  "expires_at": stamp(self.now + timedelta(days=7))}}
        self.assertBlocked(self.run_hook({}, raw=json.dumps(payload)), "couldn't check the call")  # no transcript_path

    def test_other_neon_tools_are_left_to_their_rules(self):
        result = self.run_hook({"project_id": PROJECT, "branch_id": "br-prod", "name": "x"},
                               tool_name=NEON + "create_branch")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertFalse(self.log.exists())

    # The audit log.

    def test_every_call_is_logged_with_agent_and_verdict(self):
        self.read([PRODUCTION, BACKUP])
        self.expire()
        self.run_hook({"project_id": PROJECT, "branch_id": "br-prod", "name": "x"})
        self.expire(agent_type=None, agent_id=None)
        passed, renamed, plain = self.log_lines()
        self.assertEqual(passed["tool"], UPDATE)
        self.assertEqual((passed["agent"], passed["agent_id"]), ("cto", "a1"))
        self.assertEqual((passed["project_id"], passed["branch_id"]), (PROJECT, "br-backup"))
        self.assertEqual(passed["branch_name"], BACKUP["name"])
        self.assertEqual(passed["blocked"], [])
        self.assertIn("expires_at", passed["input"])
        self.assertTrue(passed["time"].endswith("+00:00"))
        self.assertEqual(renamed["input"]["name"], "x")
        self.assertEqual(renamed["branch_name"], "production")
        self.assertTrue(any("changes more than the expiry" in r for r in renamed["blocked"]))
        self.assertEqual(plain["agent"], "main")
        self.assertTrue(plain["blocked"])

    def test_unwritable_log_blocks_the_call(self):
        self.read([PRODUCTION, BACKUP])
        self.log.parent.parent.mkdir(parents=True, exist_ok=True)
        self.log.parent.write_text("a file where the folder should be")
        self.assertBlocked(self.expire(), "can't be written")


if __name__ == "__main__":
    unittest.main()
