"""Tests for scripts/hooks/guard_full_suite.py.

Real git in a temporary repo, under a temporary company root with its own company.json; `gh` and `docker` faked, so no
test reads a live slot or lock, or writes the live error log."""

import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import guard_full_suite as guard  # noqa: E402

HOOK = Path(guard.__file__)
COMPANY = {"products": {"acme": {"repo": "example-co/acme-app", "workspace": "acme/acme-app"}},
           "integrations": {"full_suite": {"product": "acme", "database_env": "ACME_TEST_DATABASE_URL",
                                           "database_name": "acme_test", "container_prefix": "acme-pg",
                                           "workflow": "ci"}}}
URL = "postgres://postgres:postgres@127.0.0.1:15432/acme_test"
LANE, SENIOR, REVIEWER = "acme-pg-ws1", "acme-pg-ws1-sr", "acme-pg-ws1-cr"
STOPPED = "acme-pg-ws9"  # not in DOCKER_PS
DOCKER_PS = (f"{LANE}|127.0.0.1:15431->5432/tcp\n{SENIOR}|127.0.0.1:15432->5432/tcp\n"
             f"{REVIEWER}|127.0.0.1:15433->5432/tcp\nother|\n")
ON_THE_CHARGER = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t12%; charging; 2:00 remaining present: true\n"
ON_BATTERY = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t{}%; discharging; 3:00 remaining present: true\n"
BIG = "apps/web/test/big"
SMALL = "apps/web/test/small"
# More than HEAVY_FILES files, each named: a heavy run that waits for a slot. A clear full suite (no files, a shard, a
# folder or glob over the line, a hidden list) is refused instead.
NAMED = " ".join(f"{BIG}/f{n}.test.ts" for n in range(guard.HEAVY_FILES + 1))
HEAVY = f"bun test {NAMED}"
SELECT = "bun scripts/select-tests.ts --base origin/main --list"


def build(path: Path) -> None:
    """A checkout shaped like the product's: one folder over the heavy line, one under it, and test files that don't count."""
    for folder, count in ((BIG, guard.HEAVY_FILES + 1), (SMALL, 2), ("node_modules/x", 50), ("packages/core/dist", 50),
                          ("packages/core/node_modules/x", 50), ("packages/core/.cache", 50)):
        (path / folder).mkdir(parents=True)
        for n in range(count):
            (path / folder / f"f{n}.test.ts").write_text("")
    (path / "packages/log/test/deep").mkdir(parents=True)
    (path / "packages/log/src").mkdir()
    for n in range(11):
        (path / "packages/log/test/deep" / f"f{n}.test.ts").write_text("")
    for n in range(guard.HEAVY_FILES + 1):
        (path / "packages/log/src" / f"m{n}.ts").write_text("")
    (path / "package.json").write_text("{}\n")


def git(path: Path, *args: str) -> str:
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.com"]
    return subprocess.run(["git", "-C", str(path), *identity, *args], capture_output=True, text=True, check=True).stdout


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.company = Path(os.path.realpath(self.tmp.name))
        (self.company / "company.json").write_text(json.dumps(COMPANY))
        self.assertTrue(guard.configure(self.company))
        self.root = guard.FOLDER
        self.assertEqual(self.root, self.company / "acme")
        self.clone = self.root / guard.MAIN_CLONE
        self.worktree = self.root / ".worktrees" / "RM-1-WS-A"
        build(self.clone)
        build(self.worktree)
        (self.worktree / ".gitignore").write_text("node_modules\ndist\n")
        git(self.worktree, "init", "-q")
        git(self.worktree, "add", ".")
        git(self.worktree, "commit", "-q", "-m", "one")
        self.head = git(self.worktree, "rev-parse", "HEAD").strip()
        self.green_runs = []  # what `gh run list --status success` answers
        self.jobs = {}  # run id -> what `gh run view` answers
        self.gh_error = self.docker_error = self.pmset_error = None
        self.pmset = ON_THE_CHARGER
        self.calls = []
        self.git_calls = []
        real = guard.run

        def run(args, seconds, stdin=None):
            self.calls.append(args[0])
            if args[0] == "git":
                self.git_calls.append(args)
            if args[0] == "pmset" and self.pmset is not None:
                if self.pmset_error:
                    raise self.pmset_error
                return self.pmset
            if args[0] == "docker":
                if self.docker_error:
                    raise self.docker_error
                return DOCKER_PS
            if args[0] == "gh":
                if self.gh_error:
                    raise self.gh_error
                if args[2] == "list":
                    self.assertIn("success", args)
                    return json.dumps(self.green_runs)
                return json.dumps({"jobs": self.jobs[int(args[3])]})
            return real(args, seconds, stdin)

        patcher = mock.patch.object(guard, "run", run)
        patcher.start()
        self.addCleanup(patcher.stop)
        for patcher in (mock.patch.object(guard, "ON_MACOS", True), mock.patch.object(guard, "LOAD_LIMIT", 25)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def refusal(self, command, cwd=None, agent="senior-engineer"):
        event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd or self.worktree),
                 "hook_event_name": "PreToolUse", "session_id": "s"}
        if agent:
            event["agent_type"] = agent
        return guard.refusal(event, self.root)

    def suite(self, tail=HEAVY):
        return f"cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} {tail} > /tmp/o/log 2>&1; echo $? > /tmp/o/rc"

    def take_slot(self, slot="slot-1", container=SENIOR):
        folder = self.root / guard.SLOT_FOLDER / slot
        folder.mkdir(parents=True)
        (folder / "owner").write_text(f"senior-engineer /2.1 {container} 10:20Z\n")

    def green(self, sha=None, run_id=7, legs=None):
        self.green_runs.append({"databaseId": run_id, "headSha": sha or self.head})
        self.jobs[run_id] = [{"name": f"full-suite tests {k}/4", "conclusion": c}
                             for k, c in enumerate(legs or ["success"] * 4, 1)] + [
            {"name": "full-suite", "conclusion": "success"}, {"name": "gitleaks", "conclusion": "success"}]

    def errors(self):
        log = self.root / guard.ERROR_LOG
        return log.read_text() if log.exists() else ""


class WhatCountsAsAFullSuite(Guard):
    def test_real_forms_of_a_full_run_are_stopped(self):
        worktree, copy = self.worktree, self.root.parent / "copy-1a2b3c4d"
        build(copy)
        for command in [
            self.suite("bun test --shard=1/4"),
            self.suite("bun run test"),
            self.suite("bun test"),
            self.suite(f"bun test ./{BIG}"),
            self.suite("bun test ./apps/web/test/{big,small}"),
            self.suite("bun test ./apps/web/test/*"),
            self.suite("bun test --bail --timeout 60000"),
            self.suite("bun test --shard 1/4"),
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; bun test --shard=1/4 # one note",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; bun test --shard=1/4 # don't stop",
            f"cd {worktree} # go there\nexport ACME_TEST_DATABASE_URL={URL}\nbun test --shard=1/4",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; echo x#y; bun test --shard=1/4",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; echo \"a # b\"; bun test --shard=1/4",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; echo 'a # b'; bun test --shard=1/4",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; echo it\\'s; bun test --shard=1/4 # don't stop",
            self.suite("bun test \\\n  --shard=1/4"),
            self.suite("bun test apps/**/*.test.ts"),
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; 2>/dev/null bun test --shard=1/4",
            f"bash -c 'cd {worktree} && ACME_TEST_DATABASE_URL={URL} bun test --shard=1/4'",
            f"sh -c 'cd {worktree} && ACME_TEST_DATABASE_URL={URL} bun test --shard=1/4'",
            f"zsh -c 'cd {worktree} && ACME_TEST_DATABASE_URL={URL} bun test --shard=1/4'",
            f"/bin/bash -lc 'cd {worktree} && ACME_TEST_DATABASE_URL={URL} bun test --shard=1/4'",
            f"timeout 900 bash -c 'cd {worktree} && ACME_TEST_DATABASE_URL={URL} bun test'",
            f"$S/locked.sh {SENIOR} $S/shard1.log $S/rc1 bash -c \"cd {worktree} && "
            f"ACME_TEST_DATABASE_URL={URL} bun test --shard=1/4\"",
            f"bash -c \"bash -c 'cd {worktree} && ACME_TEST_DATABASE_URL={URL} bun test'\"",
            self.suite(f"bun test --cwd {BIG}"),
            self.suite(f"bun test --cwd={BIG}"),
            self.suite("bun test --cwd $W"),
            self.suite("bun test --cwd"),
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; if bun test --shard=1/4; then echo ok; fi",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; if false; then :; elif bun test; then :; fi",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; while bun test; do sleep 1; done",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; until bun test --shard=1/4; do sleep 1; done",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL} && bun test apps > /tmp/o/log 2>&1",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; bun test --shard=2/4 2>&1 | tail -3",
            f"mkdir /tmp/x && echo \"code-reviewer, order 2 $(date -u +%FT%TZ)\" > /tmp/x/owner; cd {copy} && "
            f"ACME_TEST_DATABASE_URL={URL} bun test > /tmp/o/log 2>&1",
            f"S=/tmp/o; cd $S/copy-1 && ACME_TEST_DATABASE_URL={URL} bun test ./{BIG} > $S/log 2>&1",
            f"cd {worktree} && env -u DATABASE_URL ACME_TEST_DATABASE_URL={URL} bun test --shard=3/4",
            f"cd {worktree} && ACME_TEST_DATABASE_URL={URL} timeout 900 bun test",
            f"cd {worktree} && (ACME_TEST_DATABASE_URL={URL} bun test > /tmp/o/log 2>&1; echo $? > /tmp/o/rc)",
            f"cd {worktree}\nexport ACME_TEST_DATABASE_URL={URL}\n# don't stop here\nbun test --shard=4/4",
            f"cd {worktree} && export ACME_TEST_DATABASE_URL={URL}; for k in 1 2; do bun test --shard=$k/4; done",
            f"cat > /tmp/o/x <<'EOF'\nnot a test\nEOF\ncd {worktree} && ACME_TEST_DATABASE_URL={URL} bun test",
        ]:
            with self.subTest(command=command):
                self.assertIn("Essential tier", self.refusal(command) or "")  # a clear full suite: refused, final

    def test_its_refusal_spells_out_the_named_file_form_and_that_form_runs(self):
        self.assertIn("plus the files your change touches, each by its path", self.refusal(self.suite("bun test")))
        self.assertIsNone(self.refusal(self.suite(f"bun test {SMALL}/f1.test.ts")))

    def test_a_folder_under_the_mains_clone_is_counted_when_a_variable_hides_the_cd(self):
        self.assertIn("Not started", self.refusal(self.suite(f"bun test {BIG}").replace(str(self.worktree), "$WT")))
        self.assertIsNone(self.refusal(self.suite(f"bun test {SMALL}").replace(str(self.worktree), "$WT")))

    def test_a_cwd_flag_counts_from_its_folder_when_a_variable_hides_the_cd(self):
        self.assertIsNone(self.refusal(self.suite(f"bun test --cwd {SMALL}").replace(str(self.worktree), "$WT")))
        self.assertIn("Not started", self.refusal(self.suite(f"bun test --cwd {BIG}").replace(str(self.worktree), "$WT")))

    def test_each_test_file_counts_once(self):
        count = lambda *paths: guard.test_files(str(self.worktree), list(paths))  # noqa: E731
        self.assertEqual(count("packages/log/**"), 11)
        self.assertEqual(count("packages/log/test/**/*.test.ts"), 11)
        self.assertEqual(count("packages/core/**"), 0)  # only node_modules, dist and .cache hold tests there
        self.assertEqual(count("apps/**"), guard.HEAVY_FILES + 3)
        self.assertEqual(count(BIG, BIG, f"./{BIG}"), guard.HEAVY_FILES + 1)
        self.assertEqual(count(f"{SMALL}/f1.test.ts", f"./{SMALL}/f1.test.ts"), 1)
        self.assertEqual(count("package.json"), 1)  # named by hand, so it runs whatever it's called
        self.assertEqual(count("packages/*"), 11)
        self.assertEqual(count("*.json"), 0)  # a glob's own files count only as test files

    def test_a_run_of_named_files_is_never_refused_or_delayed(self):
        many = " ".join(f"{BIG}/f{n}.test.ts" for n in range(guard.HEAVY_FILES))
        for command in [
            self.suite(f"bun test {BIG}/f1.test.ts"),
            self.suite(f"bun test '#x' {BIG}/f1.test.ts"),
            self.suite(f"bun test ./{SMALL}"),
            self.suite("bun test ./packages/core"),  # over the line only through node_modules, dist and .cache
            self.suite(f"bun test {many}"),
            self.suite("bun test some-word-that-is-no-path"),
            self.suite("bun test -t 'one test'"),
            self.suite("bun test --changed"),
            self.suite("bun test --changed origin/main"),
            self.suite("bun test --changed=origin/main"),
            self.suite(f"bun test --cwd . {SMALL}/f1.test.ts"),
            self.suite(f"bun test --cwd {SMALL}"),
            self.suite(f"bun test --cwd={SMALL}"),
            self.suite("bun test packages/log/**"),
            self.suite("bun test packages/core/**"),
            self.suite(f"bun test --config {BIG} {SMALL}/f1.test.ts"),
            self.suite(f"bun test -c {BIG} {SMALL}/f1.test.ts"),
            self.suite(f"bun test --tsconfig-override {BIG} {SMALL}/f1.test.ts"),
            self.suite(f"bun test --path-ignore-patterns {BIG} {SMALL}/f1.test.ts"),
            f"cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test 2>&1 {SMALL}/f1.test.ts",
            f"cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test > /tmp/o/log {SMALL}/f1.test.ts",
            f"bash -c 'cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test {SMALL}/f1.test.ts'",
            self.suite("bun test --help"),
            self.suite("bun test $F"),
        ]:
            with self.subTest(command=command):
                self.calls.clear()
                self.assertIsNone(self.refusal(command))
                self.assertEqual(self.calls, [])  # no git, gh or docker call: nothing that takes time

    def test_other_commands_get_no_decision(self):
        for command in [
            "bun run test:db:up acme-pg-ws1-sr 15432",
            "bun run test:e2e",
            "bun run build",
            "bun run typecheck",
            "bun install --frozen-lockfile",
            "grep -n \"bun test\" apps/web/x.ts",
            "echo bun test",
            "echo 'bun test --shard=1/4'",
            "echo bash -c 'bun test --shard=1/4'",
            "printf '%s' bash -c 'bun test --shard=1/4'",
            f"docker run --rm -v {self.worktree}:/work:ro -w /work oven/bun:1 sh -c 'bun test'",
            "bash script-file.sh bun test",
            f"bun test {SMALL}/f1.test.ts # why; bun test",
            "git commit -m 'bun test'",
            "pgrep -f \"bun test ./apps/web/test/big\"",
            "cat > /tmp/o/x <<'EOF'\nbun test\nEOF",
            "# bun test\nls",
        ]:
            with self.subTest(command=command):
                self.calls.clear()
                self.assertIsNone(self.refusal(command))
                self.assertEqual(self.calls, [])

    def test_only_this_product(self):
        demo = self.root.parent / "demo"
        build(demo)
        self.assertIsNone(self.refusal(f"cd {demo} && bun run test", cwd="/"))
        self.assertIsNone(self.refusal("bun run test", cwd=demo))
        self.assertIsNone(self.refusal("bun test", cwd="/"))
        self.assertIsNone(self.refusal(f"bash -c 'cd {demo} && bun run test'", cwd="/"))
        self.assertIsNone(self.refusal(f"bun test --cwd {demo}", cwd="/"))
        self.assertIn("Not started", self.refusal(f"bun test --cwd {self.worktree}", cwd="/"))
        next_door = self.root.parent / f"{self.root.name}-2"  # shares ROOT's first letters, but isn't under it
        build(next_door)
        self.assertIsNone(self.refusal("bun run test", cwd=next_door))
        self.assertIn("Not started", self.refusal("bun test --shard=1/4 > /tmp/o/log"))  # cwd is the worktree

    def test_another_tool_gets_no_decision(self):
        event = {"tool_name": "Monitor", "tool_input": {"command": self.suite()}, "cwd": str(self.worktree)}
        self.assertIsNone(guard.refusal(event, self.root))


class Slots(Guard):
    def test_no_slot_stops_a_full_suite_in_one_line_that_says_what_to_do(self):
        refusal = self.refusal(self.suite())
        self.assertIn(f"no slot names {SENIOR}", refusal)
        self.assertIn("Machine load: a heavy run takes a slot", refusal)
        self.assertIn("same command", refusal)
        self.assertIn("a wait for a slot", refusal)
        self.assertNotIn("permission refusal", refusal)
        self.assertNotIn("\n", refusal)

    def test_a_slot_naming_this_container_lets_it_start(self):
        self.take_slot()
        self.assertIsNone(self.refusal(self.suite()))

    def test_another_containers_slots_dont_count(self):
        self.take_slot("slot-1", REVIEWER)
        self.take_slot("slot-2", REVIEWER)
        self.assertIn("no slot names", self.refusal(self.suite()))

    def test_a_longer_container_name_doesnt_match(self):
        self.take_slot("slot-1", SENIOR + "2")
        self.assertIn("no slot names", self.refusal(self.suite()))

    def test_a_senior_slot_isnt_its_lanes(self):
        """The runbook's containers are prefixes of each other."""
        self.take_slot("slot-1", SENIOR)
        self.assertIn(f"no slot names {LANE},", self.refusal(self.suite().replace("15432", "15431")))
        self.take_slot("slot-2", "old-" + LANE)
        self.assertIn(f"no slot names {LANE},", self.refusal(self.suite().replace("15432", "15431")))

    def test_only_the_runbooks_slots_count(self):
        self.take_slot("slot-9")
        self.assertIn("no slot names", self.refusal(self.suite()))

    def test_a_slot_taken_but_with_no_owner_yet_doesnt_count(self):
        (self.root / guard.SLOT_FOLDER / "slot-1").mkdir(parents=True)
        self.assertIn("no slot names", self.refusal(self.suite()))

    def test_slot_l_is_only_for_a_landing(self):
        self.take_slot(guard.LANDING_SLOT)
        with mock.patch.object(guard.os, "getloadavg", return_value=(0, 25, 0)):  # at the limit: under the lock only
            self.assertIn("Not started", self.refusal(self.suite()))  # below 25 and the refusal: test_slot_l.py
        (self.root / guard.LANDING_LOCK).mkdir()
        self.assertIsNone(self.refusal(self.suite()))

    def test_there_is_no_run_anyway(self):
        """No timer: however old the wait or the slots are, no slot means no run."""
        self.take_slot("slot-1", REVIEWER)
        owner = self.root / guard.SLOT_FOLDER / "slot-1" / "owner"
        os.utime(owner, (0, 0))
        self.assertIn("no slot names", self.refusal(self.suite()))

    def test_a_heavy_run_with_no_port_is_stopped_with_what_to_do(self):
        refusal = self.refusal(f"cd {self.worktree} && {HEAVY} > /tmp/o/log 2>&1")
        self.assertIn("names no test database", refusal)
        self.assertIn("a wait for a slot", refusal)
        self.assertNotIn("permission refusal", refusal)
        self.assertNotIn("\n", refusal)
        self.assertNotIn("docker", self.calls)

    def test_a_port_with_no_container_lets_the_run_go_and_logs_it(self):
        self.assertIsNone(self.refusal(self.suite().replace("15432", "15499")))
        self.assertIn("no container on port 15499", self.errors())

    def test_docker_failing_lets_the_run_go_and_logs_it(self):
        self.docker_error = subprocess.TimeoutExpired("docker", 5)
        self.assertIsNone(self.refusal(self.suite()))
        self.assertIn("slot check skipped", self.errors())


class ThroughTestDbRun(Guard):
    """`sh scripts/test-db.sh run <container> <port> -- <command>`. It exports the URL and starts the
    container itself, so the command names neither and the container is usually stopped when the hook reads it."""

    def through(self, tail=HEAVY, container=STOPPED, script="sh scripts/test-db.sh"):
        return f"cd {self.worktree} && {script} run {container} 15439 -- {tail} > /tmp/o/log 2>&1"

    def test_every_form_of_it_needs_a_slot(self):
        for command in [
            self.through(),
            self.through(f"bun run test {NAMED}"),
            self.through(f"timeout 900 {HEAVY}"),
            self.through(f"env -u DATABASE_URL {HEAVY}"),
            self.through(f"sh -c 'cd {self.worktree} && {HEAVY}'"),
            self.through(script="bash scripts/test-db.sh"),
            self.through(script="/bin/sh scripts/test-db.sh"),
            self.through(script="./scripts/test-db.sh"),
            self.through(script=f"sh {self.worktree}/scripts/test-db.sh"),
            self.through(script="sh \"$W/scripts/test-db.sh\""),
            self.through(script="ACME_TEST_RUN_OWNER='senior /2.1' sh scripts/test-db.sh"),
            self.through(script="timeout 900 sh scripts/test-db.sh"),
            self.through(script="env X=1 sh scripts/test-db.sh"),
            self.through(script="nohup sh scripts/test-db.sh"),
            self.through(script="sh -x scripts/test-db.sh"),
            self.through(script="bash -eu scripts/test-db.sh"),
            f"bash -c 'cd {self.worktree} && sh scripts/test-db.sh run {STOPPED} 15439 -- {HEAVY}'",
            f"bash -c \"cd {self.worktree} && sh scripts/test-db.sh run {STOPPED} 15439 -- sh -c '{HEAVY}'\"",
        ]:
            with self.subTest(command=command):
                self.assertIn(f"no slot names {STOPPED}", self.refusal(command) or "")

    def test_a_stopped_container_is_checked_by_its_name_with_no_docker_call(self):
        self.assertIn(f"no slot names {STOPPED}", self.refusal(self.through()))
        self.assertNotIn("docker", self.calls)
        self.assertEqual(self.errors(), "")

    def test_a_slot_naming_it_lets_it_start(self):
        self.take_slot(container=STOPPED)
        self.assertIsNone(self.refusal(self.through()))
        self.assertIsNone(self.refusal(self.through(f"sh -c 'cd {self.worktree} && {HEAVY}'")))

    def test_another_containers_slot_doesnt_count(self):
        self.take_slot(container=SENIOR)
        self.assertIn(f"no slot names {STOPPED}", self.refusal(self.through()))

    def test_docker_failing_doesnt_lift_the_limit(self):
        self.docker_error = subprocess.TimeoutExpired("docker", 5)
        self.assertIn(f"no slot names {STOPPED}", self.refusal(self.through()))

    def test_its_container_wins_over_a_url_in_the_command(self):
        command = self.through(script=f"ACME_TEST_DATABASE_URL={URL} sh scripts/test-db.sh")
        self.assertIn(f"no slot names {STOPPED}", self.refusal(command))

    def test_a_running_container_on_its_port_isnt_what_it_runs_in(self):
        """An existing container keeps its own binding, so the script runs <container> whatever <port> says."""
        self.take_slot(container=SENIOR)
        command = self.through().replace("15439", "15432")
        self.assertIn(f"no slot names {STOPPED}", self.refusal(command))

    def test_a_container_in_a_variable_is_refused_by_that_word(self):
        self.assertIn("no slot names $C", self.refusal(self.through(container="$C")))

    def test_two_runs_check_the_heavy_ones_container(self):
        self.take_slot(container=STOPPED)
        small = self.through(f"bun test {SMALL}/f1.test.ts")
        heavy = self.through(container=REVIEWER)
        self.assertIn(f"no slot names {REVIEWER}", self.refusal(f"{small}; {heavy}"))

    def test_every_heavy_run_needs_its_own_slot(self):
        self.take_slot(container=STOPPED)
        first, second = self.through(), self.through(container=REVIEWER)
        for command in (f"{first}; {second}", f"{first} && {second}", f"{first} & {second} & wait"):
            with self.subTest(command=command):
                self.assertIn(f"no slot names {REVIEWER}", self.refusal(command))
        self.take_slot("slot-2", REVIEWER)
        self.assertIsNone(self.refusal(f"{first}; {second}"))

    def test_a_run_on_the_urls_port_and_a_run_through_it_each_need_a_slot(self):
        self.take_slot(container=STOPPED)
        self.assertIn(f"no slot names {SENIOR}", self.refusal(f"{self.through()}; {self.suite()}"))
        self.take_slot("slot-2", SENIOR)
        self.assertIsNone(self.refusal(f"{self.through()}; {self.suite()}"))

    def test_docker_failing_on_the_urls_port_doesnt_lift_the_next_runs_slot(self):
        self.docker_error = subprocess.TimeoutExpired("docker", 5)
        self.assertIn(f"no slot names {STOPPED}", self.refusal(f"{self.suite()}; {self.through()}"))

    def test_several_runs_on_the_urls_port_make_one_docker_call(self):
        """Each call can take DOCKER_SECONDS, and a hook timeout lets the run go."""
        self.take_slot()  # a refusal would end the walk at the first run and prove nothing
        command = f"{self.suite()}; {self.suite(HEAVY + ' --bail')}; {self.suite(HEAVY + ' --timeout 60000')}"
        self.assertIsNone(self.refusal(command))
        self.assertEqual(self.calls.count("docker"), 1)

    def test_a_shell_string_it_cant_read_doesnt_undo_the_heavy_run_before_it(self):
        broken = "sh -c \"echo it's\""
        self.assertIn(f"no slot names {STOPPED}", self.refusal(f"{self.through()}; {broken}"))
        self.assertIn(f"no slot names {SENIOR}", self.refusal(f"{self.suite()}; {broken}"))

    def test_a_tree_that_passed_stops_it_before_the_slot_question(self):
        self.green()
        self.assertIn("already passed in full", self.refusal(self.through()))

    def test_the_battery_stops_it(self):
        self.pmset = ON_BATTERY.format(20)
        self.assertIn("on battery at 20%", self.refusal(self.through()))

    def test_a_run_of_named_files_through_it_gets_no_decision(self):
        for command in [
            self.through(f"bun test {SMALL}/f1.test.ts"),
            self.through(f"bun test ./{SMALL}"),
            self.through("bun test --changed"),
            self.through(f"sh -c 'cd {self.worktree} && bun test {SMALL}/f1.test.ts'"),
        ]:
            with self.subTest(command=command):
                self.calls.clear()
                self.assertIsNone(self.refusal(command))
                self.assertEqual(self.calls, [])

    def test_what_isnt_the_form_gets_no_decision(self):
        for command in [
            f"sh scripts/test-db.sh up {STOPPED} 15439 && echo bun test",
            f"sh scripts/test-db.sh down {STOPPED}",
            f"sh scripts/test-db.sh run {STOPPED} 15439 bun test",  # no `--`: the script refuses it
            f"sh scripts/test-db.sh run {STOPPED} 15439 --",  # no command: the script refuses it
            f"sh scripts/test-db.sh run {STOPPED} 15439 x -- bun test",  # a word before `--`: the script refuses it
            f"sh scripts/test-db.sh run {STOPPED} 15439 x bun test",  # no `--`: the script refuses it
            f"sh scripts/test-db.sh up {STOPPED} 15439 -- bun test",  # not `run`
            f"sh -c scripts/test-db.sh run {STOPPED} 15439 -- bun test",  # the shell runs the script with no arguments
            f"sh scripts/other.sh run {STOPPED} 15439 -- bun test",
            f"echo sh scripts/test-db.sh run {STOPPED} 15439 -- bun test",
            f"git commit -m 'sh scripts/test-db.sh run {STOPPED} 15439 -- bun test'",
            self.through("bun run typecheck"),
            self.through("bun run test:e2e"),
        ]:
            with self.subTest(command=command):
                self.calls.clear()
                self.assertIsNone(self.refusal(command))
                self.assertEqual(self.calls, [])

    def test_a_copy_outside_the_workspace_counts_by_its_container(self):
        copy = self.root.parent / "copy-1a2b3c4d"
        build(copy)
        command = self.through().replace(str(self.worktree), str(copy))
        self.assertIn(f"no slot names {STOPPED}", self.refusal(command, cwd="/"))

    def test_only_this_product(self):
        demo = self.root.parent / "demo"
        build(demo)
        command = self.through(container="demo-pg-x").replace(str(self.worktree), str(demo))
        self.assertIsNone(self.refusal(command, cwd="/"))


class OneTreeOneFullRun(Guard):
    def test_a_tree_with_a_green_full_run_is_refused_in_one_line(self):
        self.take_slot()
        self.green()
        refusal = self.refusal(self.suite())
        self.assertIn("already passed in full (CI run 7, commit " + self.head[:8], refusal)
        self.assertIn("final for this tree", refusal)
        self.assertIn("release your slot", refusal)
        self.assertNotIn("a wait", refusal)
        self.assertNotIn("same command", refusal)
        self.assertNotIn("\n", refusal)

    def test_no_slot_is_needed_to_hear_it(self):
        self.green()
        self.assertIn("already passed in full", self.refusal(self.suite()))
        self.assertNotIn("docker", self.calls)

    def test_a_green_run_on_another_commit_with_the_same_tree_counts(self):
        git(self.worktree, "commit", "-q", "--allow-empty", "-m", "same tree")
        self.green(self.head)  # self.head is now HEAD~1, with the same tree
        self.assertIn("already passed in full", self.refusal(self.suite()))

    def test_a_cwd_flag_or_a_later_cd_is_the_checkout_that_is_checked(self):
        self.green()
        command = f"ACME_TEST_DATABASE_URL={URL} {HEAVY}"
        self.assertIn("already passed in full", self.refusal(f"{command} --cwd {self.worktree}", cwd="/"))
        self.assertIn("already passed in full", self.refusal(f"cd $X; cd {self.worktree} && {command}", cwd="/"))

    def test_a_cd_into_a_variable_skips_this_check_and_the_slot_still_binds(self):
        """The rule binds this run all the same; the hook can't see it."""
        self.green()
        command = f"cd $X && ACME_TEST_DATABASE_URL={URL} {HEAVY}"
        self.assertIn("no slot names", self.refusal(command))
        self.assertNotIn("gh", self.calls)

    def test_a_green_run_on_another_tree_doesnt_count(self):
        self.take_slot()
        (self.worktree / "new.ts").write_text("x")
        git(self.worktree, "add", ".")
        git(self.worktree, "commit", "-q", "-m", "two")
        self.green(self.head)  # the tree before the commit above
        self.assertIsNone(self.refusal(self.suite()))

    def test_a_dirty_tree_isnt_the_tree_that_passed(self):
        self.take_slot()
        self.green()
        (self.worktree / "package.json").write_text("{\"changed\": true}\n")
        self.assertIsNone(self.refusal(self.suite()))
        self.assertNotIn("gh", self.calls)

    def test_an_untracked_file_isnt_the_tree_that_passed(self):
        self.take_slot()
        self.green()
        (self.worktree / "new.test.ts").write_text("")
        self.assertIsNone(self.refusal(self.suite()))

    def test_a_green_run_that_didnt_run_every_leg_doesnt_count(self):
        """A pull request's green run may hold only the affected tests."""
        self.take_slot()
        for legs in [["success", "skipped", "success", "success"], ["success", "cancelled"] + ["success"] * 2,
                     ["success", "failure"] + ["success"] * 2, ["neutral"] * 4,
                     ["success", "success"]]:  # 1/4 and 2/4 alone are a run of two legs out of four
            with self.subTest(legs=legs):
                self.green_runs.clear()
                self.green(legs=legs)
                self.assertIsNone(self.refusal(self.suite()))

    def test_a_run_missing_a_leg_or_with_no_legs_doesnt_count(self):
        self.take_slot()
        self.green()
        self.jobs[7] = [job for job in self.jobs[7] if job["name"] != "full-suite tests 3/4"]
        self.assertIsNone(self.refusal(self.suite()))
        self.jobs[7] = [{"name": "full-suite", "conclusion": "success"}]
        self.assertIsNone(self.refusal(self.suite()))

    def test_only_jobs_named_exactly_like_a_leg_prove_a_full_run(self):
        self.take_slot()
        self.green()
        for name in ("full-suite tests {}/4 (affected)", "affected full-suite tests {}/4"):
            with self.subTest(name=name):
                self.jobs[7] = [{"name": name.format(k), "conclusion": "success"} for k in range(1, 5)]
                self.assertIsNone(self.refusal(self.suite()))

    def test_the_check_takes_no_lock_in_anothers_worktree(self):
        self.green()
        self.refusal(self.suite())
        self.assertTrue(self.git_calls)
        for args in self.git_calls:
            self.assertIn("--no-optional-locks", args)

    def test_an_earlier_run_on_the_tree_can_be_the_proof(self):
        """A merge commit's run can skip the legs, its tree's earlier run having run them."""
        git(self.worktree, "commit", "-q", "--allow-empty", "-m", "merge, same tree")
        head = git(self.worktree, "rev-parse", "HEAD").strip()
        self.green(head, run_id=8, legs=["skipped"] * 4)
        self.green(self.head, run_id=7)
        self.assertIn("CI run 7", self.refusal(self.suite()))

    def test_a_copy_outside_the_workspace_isnt_checked(self):
        copy = self.root.parent / "copy-1"
        git(self.worktree, "clone", "-q", str(self.worktree), str(copy))  # the same tree, clean, but not under ROOT
        self.take_slot()
        self.green()
        self.assertIsNone(self.refusal(f"cd {copy} && ACME_TEST_DATABASE_URL={URL} {HEAVY}"))
        self.assertNotIn("gh", self.calls)

    def test_every_heavy_runs_checkout_is_checked_not_only_the_first(self):
        """A heavy named run outside any checkout, put first, doesn't take this check off a later heavy run in a checkout
        that passed in full."""
        outside = self.root.parent / "outside"
        build(outside)
        self.take_slot()
        self.green()
        first = f"cd {outside} && ACME_TEST_DATABASE_URL={URL} {HEAVY}; "
        self.assertIn("already passed in full (CI run 7", self.refusal(first + self.suite()))
        not_a_repo = f"cd {self.clone} && ACME_TEST_DATABASE_URL={URL} {HEAVY}; "  # its check fails, and is logged
        self.assertIn("already passed in full (CI run 7", self.refusal(not_a_repo + self.suite()))
        self.assertIn("CI check skipped", self.errors())

    def test_the_checkouts_after_the_first_share_one_checkouts_seconds(self):
        """So the hook's timeout still holds: the first checkout's calls get their own seconds, and the
        later ones only what's left of CI_SECONDS, counted from the first's start."""
        self.take_slot()
        self.green()
        command = f"cd {self.clone} && ACME_TEST_DATABASE_URL={URL} {HEAVY}; " + self.suite()
        with mock.patch.object(guard, "CI_SECONDS", 0):
            self.assertIsNone(self.refusal(command))
        self.assertIn("no time left for this checkout's CI check", self.errors())
        self.assertFalse([args for args in self.git_calls if str(self.worktree) in args])
        seconds = []
        with mock.patch.object(guard, "run", lambda args, s, stdin=None: seconds.append(s) or " M x"):
            self.assertIsNone(guard.passed_run(str(self.worktree), time.monotonic() + 1))
        self.assertTrue(len(seconds) == 1 and 0 < seconds[0] <= 1)
        self.assertEqual(guard.CI_SECONDS, 3 * guard.GIT_SECONDS + (1 + guard.PROOFS) * guard.GH_SECONDS)

    def test_github_down_skips_only_this_check_and_logs_it(self):
        self.gh_error = subprocess.CalledProcessError(1, "gh")
        self.assertIn("no slot names", self.refusal(self.suite()))  # the limit still holds
        self.assertIn("CI check skipped", self.errors())
        self.take_slot()
        self.assertIsNone(self.refusal(self.suite()))


class ClearFullSuitesAreRefused(Guard):
    """A clear full suite is refused whatever slot it holds, a production deploy's run too."""

    def through(self, tail, container=STOPPED):
        return f"cd {self.worktree} && sh scripts/test-db.sh run {container} 15439 -- {tail} > /tmp/o/log 2>&1"

    def deploy(self, container=STOPPED):
        """What a production deploy holds: the landing lock, and slot-L naming its container."""
        (self.root / guard.LANDING_LOCK).mkdir()
        folder = self.root / guard.SLOT_FOLDER / guard.LANDING_SLOT
        folder.mkdir(parents=True)
        (folder / "owner").write_text(f"staff-engineer /2 {container} 10:20Z\n")

    def assert_final(self, refusal):
        self.assertIn("Essential tier", refusal or "")
        self.assertIn("That's final", refusal)
        self.assertNotIn("a wait", refusal)
        self.assertNotIn("\n", refusal)

    def test_a_hidden_list_under_the_name_essential_is_refused_whatever_slots_it_holds(self):
        """A landing that names its run "essential tier" while a `$(...)` hides the files it runs."""
        container = "acme-pg-ws1-t2"
        essential = ("packages/db/test/a.test.ts packages/db/test/b.test.ts "
                     "apps/web/test/c.test.ts apps/web/test/d.test.ts")
        command = (f'cd {self.worktree}; ESS="{essential}"; '
                   "ACME_TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:15440/acme_test "
                   'ACME_TEST_RUN_OWNER="senior-engineer, order D-20260101-acme-launch/2" '
                   f"sh scripts/test-db.sh run {container} 15440 -- bun test --timeout 30000 $({SELECT}) $ESS "
                   "> /tmp/o/gate.log 2>&1; echo exit=$? >> /tmp/o/gate.log")
        self.take_slot("slot-1", container)
        self.take_slot("slot-2", container)
        self.assert_final(self.refusal(command))
        self.deploy(container)  # under the lock in slot-L too: no run is exempt
        self.assert_final(self.refusal(command))
        self.assertEqual(self.calls, [])

    def test_every_clear_form_is_refused_with_slots_held(self):
        self.take_slot("slot-1", SENIOR)
        self.take_slot("slot-2", STOPPED)
        for command in [
            self.suite("bun test --shard=1/4"),
            self.suite("bun test"),
            self.suite("bun run test"),
            self.suite(f"bun test ./{BIG}"),
            self.suite("bun test ./apps/web/test/*"),
            self.suite(f"bun test {BIG}/f[0-9].test.ts {BIG}/f[0-9][0-9].test.ts"),  # a bracket glob, 31 files
            self.suite("bun run test ./apps/web/test/{big,small}"),  # a brace list, in this checkout
            self.suite(f"bun run test ./{BIG} ./apps/web/test/*.test.ts"),
            self.suite("bun run test packages apps"),
            self.suite(f"bun test {SMALL}/f1.test.ts ./{BIG}"),  # over the line with a folder among the paths
            self.suite(f"bun test $({SELECT})"),
            self.suite(f"bun test \"$({SELECT})\""),
            self.suite(f"bun test `{SELECT}`"),
            self.suite(f"bun test {SMALL}/f1.test.ts $({SELECT})"),
            self.suite("bun test apps/$(echo web)/test/big/f1.test.ts"),
            f"SEL=$({SELECT}); {self.suite('bun test $SEL')}",
            f"export SEL=\"$({SELECT})\"; {self.suite('bun test ${SEL}')}",
            f"SEL=`{SELECT}`; {self.suite('bun test $SEL')}",
            f"D={BIG}; {self.suite('bun test $D')}",
            self.through("bun test --shard=1/4"),
            self.through("bun test"),
            self.through("bun run test"),
            self.through(f"bun test ./{BIG}"),
            self.through(f"bun test --timeout 30000 $({SELECT})"),
            self.through(f"sh -c 'cd {self.worktree} && bun test'"),
            f"bash -c 'cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test $({SELECT})'",
        ]:
            with self.subTest(command=command):
                self.calls.clear()
                self.assert_final(self.refusal(command))
                self.assertEqual(self.calls, [])  # refused before any outside call

    def test_a_bracket_is_a_glob_unless_a_path_has_that_very_name(self):
        """Next.js names folders `[id]`: a path that exists is that path; a bracket that names none is a glob."""
        folder = self.worktree / "apps/web/app/[id]"
        folder.mkdir(parents=True)
        for n in range(guard.HEAVY_FILES + 1):
            (folder / f"f{n}.test.ts").write_text("")
        self.assert_final(self.refusal(self.suite("bun test 'apps/web/app/[id]'")))  # the folder, walked
        self.assertIsNone(self.refusal(self.suite("bun test 'apps/web/app/[id]/f1.test.ts'")))

    def test_a_quoted_path_with_a_space_stays_one_path(self):
        """Split, its words would reach nothing."""
        folder = self.worktree / "apps/web/test/big suite"
        folder.mkdir(parents=True)
        for n in range(40):
            (folder / f"f{n}.test.ts").write_text("")
        self.assert_final(self.refusal(self.suite("bun test 'apps/web/test/big suite'")))
        self.assertIsNone(self.refusal(self.suite("bun test 'apps/web/test/big suite/f1.test.ts'")))
        refusal = self.refusal(self.through(f"{HEAVY} 'apps/web/test/big suite/f1.test.ts'"))
        self.assertIn("a wait for a slot", refusal or "")

    def test_a_production_deploys_run_is_refused_too(self):
        """Whoever holds the lock and slot-L."""
        self.deploy()
        for agent in ("cto", "staff-engineer", "senior-engineer", None):
            for tail in ("bun test --shard=1/4", "bun test", "bun run test"):
                with self.subTest(agent=agent, tail=tail):
                    self.calls.clear()
                    self.assert_final(self.refusal(self.through(tail), agent=agent))
                    self.assertEqual(self.calls, [])

    def test_a_deploys_run_is_refused_before_the_passed_tree_and_the_battery(self):
        self.deploy()
        self.green()
        self.pmset = ON_BATTERY.format(3)
        self.assert_final(self.refusal(self.through("bun test"), agent="cto"))
        self.assertEqual(self.calls, [])

    def test_the_essential_tier_and_the_touched_files_get_no_decision(self):
        essential = " ".join(f"packages/log/test/deep/f{n}.test.ts" for n in range(11))
        touched = f"{SMALL}/f0.test.ts {SMALL}/f1.test.ts"
        for command in [
            self.through(f"bun test --timeout 30000 {essential} {touched}"),
            f'ESS="{essential}"; ' + self.through(f"bun test --timeout 30000 {touched} $ESS"),
            "T=$(date -u +%FT%TZ); " + self.through(f"bun test {touched}"),
            self.suite(f"bun test {essential} {touched}"),
        ]:
            with self.subTest(command=command):
                self.calls.clear()
                self.assertIsNone(self.refusal(command))
                self.assertEqual(self.calls, [])

    def test_more_named_files_than_the_line_stay_a_slot_wait(self):
        (self.worktree / SMALL / "f[1].test.ts").write_text("")  # a file named with brackets is a file, not a glob
        for command in (self.through(HEAVY), f'F="{NAMED}"; ' + self.through("bun test $F"),
                        self.through(f"{HEAVY} '{SMALL}/f[1].test.ts'"),
                        self.through(f"{HEAVY} 'apps/web/app/[gone]/f1.test.ts'")):  # a [ that matches nothing
            with self.subTest(command=command):
                refusal = self.refusal(command)
                self.assertIn(f"no slot names {STOPPED}", refusal)
                self.assertIn("a wait for a slot", refusal)
                self.assertNotIn("Essential tier", refusal)
        self.take_slot(container=STOPPED)
        self.assertIsNone(self.refusal(self.through(HEAVY)))

    def test_the_off_switch_lets_a_clear_one_go_too(self):
        (self.root / guard.OFF_SWITCH).touch()
        self.assertIsNone(self.refusal(self.suite("bun test --shard=1/4")))
        self.assertEqual(self.calls, [])


class Battery(Guard):
    def setUp(self):
        super().setUp()
        self.take_slot()

    def test_a_heavy_run_doesnt_start_on_battery_under_the_floor(self):
        self.pmset = ON_BATTERY.format(guard.BATTERY_FLOOR - 1)
        refusal = self.refusal(self.suite())
        self.assertIn("on battery at 24%, under the 25%", refusal)
        self.assertIn("a wait for the charger", refusal)
        self.assertIn("no run-anyway", refusal)
        self.assertIn("say so in your report", refusal)
        self.assertIn("release your slot", refusal)
        self.assertNotIn("\n", refusal)

    def test_it_stops_before_the_slot_question(self):
        self.pmset = ON_BATTERY.format(3)
        self.assertIn("on battery at 3%", self.refusal(f"cd {self.worktree} && {HEAVY}"))

    def test_the_floor_itself_is_enough(self):
        self.pmset = ON_BATTERY.format(guard.BATTERY_FLOOR)
        self.assertIsNone(self.refusal(self.suite()))

    def test_the_charger_lets_it_go_at_any_charge(self):
        self.assertIsNone(self.refusal(self.suite()))

    def test_a_mac_with_no_battery_lets_it_go(self):
        self.pmset = "Now drawing from 'AC Power'\n"
        self.assertIsNone(self.refusal(self.suite()))

    def test_named_files_are_never_asked_about(self):
        self.pmset = ON_BATTERY.format(3)
        self.assertIsNone(self.refusal(f"cd {self.worktree} && bun test {SMALL}/f0.test.ts"))
        self.assertNotIn("pmset", self.calls)

    def test_the_passed_tree_line_comes_first(self):
        self.pmset = ON_BATTERY.format(3)
        self.green()
        self.assertIn("final for this tree", self.refusal(self.suite()))

    def test_an_error_in_the_check_lets_the_run_go_and_logs_it(self):
        for error in (subprocess.TimeoutExpired("pmset", 1), FileNotFoundError("pmset"),
                      subprocess.CalledProcessError(1, "pmset")):
            self.pmset_error = error
            self.assertIsNone(self.refusal(self.suite()))
        self.assertEqual(self.errors().count("battery check skipped"), 3)

    def test_an_answer_it_cant_read_lets_the_run_go_and_logs_it(self):
        self.pmset = "Now drawing from 'Battery Power'\n"
        self.assertIsNone(self.refusal(self.suite()))
        self.assertIn("battery check skipped", self.errors())

    def test_an_error_there_doesnt_lift_the_slot_limit(self):
        self.pmset_error = subprocess.TimeoutExpired("pmset", 1)
        self.assertIn("no slot names", self.refusal(self.suite().replace("15432", "15433")))

    def test_the_real_call_reads_a_real_process(self):
        """Through subprocess, as the hook does, with a stand-in `pmset` first on PATH."""
        folder = Path(self.tmp.name) / "bin"
        folder.mkdir()
        stand_in = folder / "pmset"
        stand_in.write_text(f"#!/bin/sh\ncat <<'EOF'\n{ON_BATTERY.format(20)}EOF\n")
        stand_in.chmod(0o755)
        self.pmset = None
        with mock.patch.dict(os.environ, {"PATH": f"{folder}{os.pathsep}{os.environ['PATH']}"}), \
                mock.patch.object(guard, "PMSET_SECONDS", 30):
            self.assertIn("on battery at 20%", self.refusal(self.suite()))

    def test_every_check_fits_the_hooks_timeout(self):
        settings = json.loads((Path(__file__).resolve().parents[2] / ".claude" / "settings.json").read_text())
        timeout = [hook["timeout"] for group in settings["hooks"]["PreToolUse"] if group["matcher"] == "Bash"
                   for hook in group["hooks"] if hook["command"].endswith("/guard_full_suite.py")][0]
        worst = 3 * guard.GIT_SECONDS + (1 + guard.PROOFS) * guard.GH_SECONDS + guard.DOCKER_SECONDS + guard.PMSET_SECONDS
        start_up = 0.5  # the hook's start and parse, with room to spare
        self.assertLess(worst + guard.WALK_SECONDS + start_up, timeout)  # counts that end in time, then every call


class CantBlockEngineering(Guard):
    def main(self, stdin):
        """The hook's main() on stdin, with the company here: (exit code, stderr)."""
        stderr = io.StringIO()
        with mock.patch.object(guard, "ROOT", self.company), mock.patch("sys.stdin", io.StringIO(stdin)), \
                redirect_stderr(stderr):
            try:
                guard.main()
            except SystemExit as stop:
                return stop.code, stderr.getvalue()
        return 0, stderr.getvalue()

    def event(self, command):
        return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.worktree)})

    def test_a_refusal_exits_2_with_its_one_line_on_stderr(self):
        code, stderr = self.main(self.event(self.suite()))
        self.assertEqual(code, 2)
        self.assertEqual(len(stderr.strip().splitlines()), 1)

    def test_a_full_suite_exits_2_with_one_ascii_line(self):
        """print() sits outside main()'s try: a character stderr can't encode would crash it."""
        code, stderr = self.main(self.event(self.suite("bun test --shard=1/4")))
        self.assertEqual(code, 2)
        self.assertEqual(len(stderr.strip().splitlines()), 1)
        self.assertIn("Essential tier", stderr)
        self.assertTrue(stderr.isascii())

    def test_the_off_switch_lets_everything_go_without_a_call(self):
        (self.root / guard.OFF_SWITCH).touch()
        self.green()
        self.assertEqual(self.main(self.event(self.suite())), (0, ""))
        self.assertEqual(self.calls, [])
        (self.root / guard.OFF_SWITCH).unlink()
        self.assertEqual(self.main(self.event(self.suite()))[0], 2)

    def test_unreadable_input_lets_the_run_go(self):
        self.assertEqual(self.main("not json"), (0, ""))

    def test_a_bug_lets_the_run_go_and_logs_it(self):
        with mock.patch.object(guard, "full_suites", side_effect=KeyError("a bug")):
            self.assertEqual(self.main(self.event(self.suite())), (0, ""))
        self.assertIn("run let go: KeyError", self.errors())

    def test_a_command_it_cant_parse_lets_the_run_go_and_logs_it(self):
        self.assertEqual(self.main(self.event("bun test 'never closed")), (0, ""))
        self.assertIn("run let go: ValueError", self.errors())

    def test_a_log_that_cant_be_written_changes_nothing(self):
        with mock.patch.object(guard, "ERROR_LOG", "no/such/folder/log"):
            self.assertEqual(self.main(self.event("bun test 'never closed")), (0, ""))

    def test_it_runs_as_a_script_and_stays_quiet_on_other_commands(self):
        event = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/tmp"}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                                timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    # the product is company.json's: with none set up nothing is held, and what can't be read is refused
    def write(self, text):
        (self.company / "company.json").write_text(text if isinstance(text, str) else json.dumps(text))

    def test_with_no_product_set_up_every_run_goes(self):
        for company in ({}, {"integrations": {}}, {**COMPANY, "integrations": {"neon": {}}}):
            with self.subTest(company=company):
                self.write(company)
                self.assertEqual(self.main(self.event(self.suite("bun test"))), (0, ""))
        (self.company / "company.json").unlink()
        self.assertEqual(self.main(self.event(self.suite("bun test"))), (0, ""))
        self.assertEqual(self.calls, [])

    def test_settings_it_cant_read_refuse_the_run(self):
        own = COMPANY["integrations"]["full_suite"]
        for company in ("", "{", "[]", {**COMPANY, "integrations": []}, {**COMPANY, "products": {}},
                        {**COMPANY, "integrations": {"full_suite": {}}},
                        {**COMPANY, "integrations": {"full_suite": {**own, "product": "demo"}}},
                        {**COMPANY, "integrations": {"full_suite": {**own, "container_prefix": ""}}},
                        {**COMPANY, "integrations": {"full_suite": {**own, "database_env": ["X"]}}}):
            with self.subTest(company=company):
                self.write(company)
                code, stderr = self.main(self.event("bun test a.test.ts"))
                self.assertEqual(code, 2)
                self.assertIn("company.json", stderr)
                self.assertEqual(len(stderr.strip().splitlines()), 1)
                self.assertTrue(stderr.isascii())
                self.assertEqual(self.main(self.event("ls")), (0, ""))  # what isn't a test run isn't held

    def test_the_workspace_is_the_main_checkouts_from_a_worktree_too(self):
        worktree = self.company / ".claude" / "worktrees" / "agent-1"
        worktree.mkdir(parents=True)
        (worktree / "company.json").write_text(json.dumps(COMPANY))
        self.assertTrue(guard.configure(worktree))
        self.assertEqual(guard.FOLDER, self.root)


class LongWalks(Guard):
    """A run whose count is still walking after WALK_SECONDS, a command's counts together, or finds them spent, is a
    clear full suite: a walk from `/` outlasts the hook's timeout."""

    @staticmethod
    def endless_walk(top, *args, **kwargs):
        """A walk that lasts 5 s (as good as endless here), so a broken cap fails the test, not hangs the suite."""
        stop = time.monotonic() + 5
        while time.monotonic() < stop:
            time.sleep(0.01)
            yield top, [], []

    def test_a_walk_that_doesnt_end_is_a_full_suite_refused_without_a_call(self):
        for tail in ("bun test", f"bun test {SMALL}", "bun test --shard=1/4"):
            with self.subTest(tail=tail), mock.patch.object(guard, "WALK_SECONDS", 0.3), \
                    mock.patch.object(guard.os, "walk", self.endless_walk):
                start = time.monotonic()
                reason = self.refusal(self.suite(tail))
                self.assertLess(time.monotonic() - start, 3)
                self.assertIn("too many to count in 0.3 s", reason)
        self.assertEqual(self.calls, [])

    def test_a_glob_that_doesnt_end_is_a_full_suite(self):
        with mock.patch.object(guard, "WALK_SECONDS", 0.3), mock.patch.object(guard.glob, "glob",
                                                                             lambda *a, **k: time.sleep(5)):
            self.assertIn("too many to count", self.refusal(self.suite("bun test 'apps/**/*.test.ts'")))

    def test_the_commands_counts_share_the_seconds(self):
        def slow(base, paths):
            time.sleep(0.6)
            return 1

        with mock.patch.object(guard, "WALK_SECONDS", 1.0), mock.patch.object(guard, "test_files", slow):
            self.assertIsNone(self.refusal(self.suite(f"bun test {SMALL}")))
            twice = f"cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test {SMALL}; bun test {SMALL}"
            self.assertIn("too many to count", self.refusal(twice))

    def test_a_count_that_ends_keeps_its_result(self):
        budget = [guard.WALK_SECONDS]
        self.assertTrue(guard.heavy(str(self.worktree), [BIG], budget))
        self.assertFalse(guard.heavy(str(self.worktree), [SMALL], budget))
        self.assertTrue(0 < budget[0] < guard.WALK_SECONDS)
        self.assertIsNone(guard.heavy(str(self.worktree), [SMALL], [0]))  # no seconds left: not counted

    def test_a_count_ending_as_the_seconds_run_out_never_escapes_or_undercounts(self):
        """At any budget, a count over HEAVY_FILES is heavy or not counted, and nothing escapes."""
        for n in range(2000):
            budget = 10 ** -(4 + n % 4)  # 1e-4 down to 1e-7 s
            self.assertIn(guard.heavy(str(self.worktree), [BIG], [budget]), (True, None))
            self.assertIn(guard.heavy(str(self.worktree), [SMALL], [budget]), (False, None))

    def test_an_error_in_the_count_is_raised(self):
        with mock.patch.object(guard, "test_files", side_effect=KeyError("a bug")):
            with self.assertRaises(KeyError):
                guard.heavy(str(self.worktree), [SMALL], [guard.WALK_SECONDS])

    def test_with_no_thread_to_be_had_the_run_isnt_counted_and_is_refused(self):
        for error in (RuntimeError("can't start new thread"), MemoryError()):
            with self.subTest(error=error), mock.patch.object(guard.threading.Thread, "start", side_effect=error):
                self.assertIsNone(guard.heavy(str(self.worktree), [SMALL], [guard.WALK_SECONDS]))
                self.assertIn("too many to count", self.refusal(self.suite(f"bun test {SMALL}")))
        self.assertEqual(self.calls, [])

    def two_runs(self, first):
        """A first run outside any checkout, then a heavy named run in a checkout whose tree passed CI in full, with a
        slot held."""
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "x.test.ts").write_text("")
        self.green()
        self.take_slot()
        self.assertIn("already passed in full", self.refusal(self.suite()))
        self.calls.clear()
        before = set(threading.enumerate())  # a count left walking ends before the next test, which times its own
        self.addCleanup(lambda: [thread.join(10) for thread in threading.enumerate() if thread not in before])
        return (f"cd {outside} && ACME_TEST_DATABASE_URL={URL} bun test {first}; "
                f"cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} {HEAVY}")

    def test_a_first_run_whose_count_passes_the_seconds_is_refused_before_any_call(self):
        braces = "x{" + ",".join(str(n) for n in range(10)) + "}"
        command = self.two_runs(braces * 5 + "{a,b}.test.ts")  # 200,000 paths
        with mock.patch.object(guard, "WALK_SECONDS", 0.1):
            self.assertIn("too many to count in 0.1 s", self.refusal(command))
        self.assertEqual(self.calls, [])

    def test_a_one_file_first_run_slowed_past_the_seconds_is_refused_with_no_is_glob_after_it(self):
        command, real = self.two_runs("x.test.ts"), guard.test_files

        def slow_outside(base, paths):
            if "outside" in base:
                time.sleep(1)
            return real(base, paths)

        with mock.patch.object(guard, "WALK_SECONDS", 0.2), mock.patch.object(guard, "test_files", slow_outside), \
                mock.patch.object(guard, "is_glob", wraps=guard.is_glob) as is_glob:
            self.assertIn("too many to count in 0.2 s", self.refusal(command))
            self.assertEqual(is_glob.call_count, 0)
        self.assertEqual(self.calls, [])

    def test_the_hook_exits_2_at_once_while_a_count_still_walks(self):
        """In its own process, as Claude Code runs it: the thread left walking doesn't hold the exit or change it."""
        script = (
            "import io, json, sys, time\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(HOOK.parent)!r})\n"
            "import guard_full_suite as g\n"
            "def walk(top, *a, **k):\n"
            "    stop = time.monotonic() + 5\n"
            "    while time.monotonic() < stop:\n"
            "        time.sleep(0.01)\n"
            "        yield top, [], []\n"
            "g.os.walk, g.WALK_SECONDS, g.ROOT = walk, 0.3, Path(sys.argv[1])\n"
            "g.main()\n")
        event = {"tool_name": "Bash", "tool_input": {"command": self.suite("bun test")}, "cwd": str(self.worktree)}
        start = time.monotonic()
        result = subprocess.run([sys.executable, "-c", script, str(self.company)], input=json.dumps(event),
                                capture_output=True, text=True, timeout=30,
                                env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.company)})
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("too many to count in 0.3 s", result.stderr)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)

    def test_a_folder_run_in_a_real_checkout_is_counted_inside_the_seconds(self):
        start = time.monotonic()
        self.assertIsNone(self.refusal(self.suite(f"bun test {SMALL}")))
        self.assertIn("Not started", self.refusal(self.suite(f"bun test {BIG}")))
        self.assertLess(time.monotonic() - start, guard.WALK_SECONDS)


class Heredocs(unittest.TestCase):
    """without_heredocs reads heredocs as the regex it replaced did, in near-linear time: the regex could outlast the
    hook's timeout."""

    REGEX = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(?:.*?\n)?[ \t]*\2[ \t]*(?=\n|$)", re.S)

    def test_heredocs_are_read_as_the_regex_read_them(self):
        pieces = ["<<", "<<-", "<", "-", " ", "\t", "\n", "\r", "\x0b", "'", '"', "E", "EO", "EOF", "1", "é", "_", ".",
                  "EOF\n", " EOF \n", "<<EOF\n", "<<'EOF'\n", "<<-E\n", "\tE\n", "<< \n E\n", "1\n", "$(", ")"]
        rng = random.Random(40)
        for _ in range(20_000):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 30)))
            self.assertEqual(guard.without_heredocs(text), self.REGEX.sub("", text), repr(text))

    def test_a_crafted_command_is_read_in_near_linear_time(self):
        # k lines of lengths 1..k, then k-character names with no end line; and 25,000 `<<EOF` with none
        k = 500
        lines = "".join("b" * size + "\n" for size in range(1, k + 1))
        for command in ("bun test a.test.ts\n" + lines + ("cat <<" + "a" * k + "\n") * 260,
                        "bun test a.test.ts\n" + "cat <<EOF\n" * 25_600):
            start = time.monotonic()
            self.assertEqual(guard.simple_commands(command)[0], ["bun", "test", "a.test.ts"])
            self.assertLess(time.monotonic() - start, 3)

    def test_the_second_reading_keeps_each_first_lines_rest(self):
        """The shell runs what follows a heredoc's end word on its first line."""
        rest = re.compile(self.REGEX.pattern.replace(r"\1[^\n]*\n", r"\1([^\n]*)\n"), re.S)
        rng = random.Random(41)
        pieces = ["<<", "<<-", "<", " ", "\t", "\n", "'", '"', "E", "EOF", ";", "x", "EOF\n", "<<EOF\n", "<<'EOF'; b\n",
                  "<<E >x; y\n", "\tE\n", "1\n"]
        for _ in range(20_000):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 30)))
            self.assertEqual(guard.without_heredocs(text, keep_rest=True),
                             rest.sub(lambda found: " " + found[3], text), repr(text))


class HeredocsTheShellReadsOtherwise(Guard):
    """Where without_heredocs may take for a body what the shell runs, a command that may start a run is refused
    (cq_write.heredoc_doubt asked of this hook's reading)."""

    def setUp(self):
        super().setUp()
        self.take_slot()  # so a heavy run seen is let go, and only the doubt refuses

    def test_a_run_the_shell_reads_outside_a_heredoc_is_refused(self):
        self.assertIn("reads outside", self.refusal(  # a full suite
            f"cat <<EOF\nEOF\ncd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test\nEOF") or "")
        run = f"cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test {SMALL}/f1.test.ts"
        for command in [
            f"cat <<EOF\nEOF\n{run}\nEOF",  # an empty heredoc whose name comes again
            f"cat <<-EOF\n\tEOF\n{run}\nEOF",
            f"echo '<<EOF'\n{run}\nEOF",  # in quotes
            f"echo \"<<EOF\"\n{run}\nEOF",
            f"echo '<<EOF' && {run}\nEOF",
            f"# <<EOF\n{run}\nEOF",  # in a comment
            f"ls # see <<EOF\n{run}\nEOF",
            f"cat <<<EOF\n{run}\nEOF",  # a here-string
            f"cat <<< EOF\n{run}\nEOF",
            f"echo $((1<<EOF))\n{run}\nEOF",  # arithmetic
            f"cat <<EOF\nx\\\nEOF\n{run}\nEOF",  # an unquoted body that goes on past a backslash
            f"cat <<EOF-X\n{run}\nEOF\nEOF-X",  # an end word that is more than this hook's name
            f"cat <<EOF \"\n{run}\nEOF",  # a first line that leaves a quote open
            f"echo '<<EOF'\nbun test\nEOF",  # under ROOT: the cwd
        ]:
            with self.subTest(command=command):
                refusal = self.refusal(command)
                self.assertIn("reads outside a heredoc", refusal or "")
                self.assertNotIn("\n", refusal)

    def test_a_run_on_a_heredocs_first_line_is_read(self):
        command = f"cat <<'EOF' > /tmp/o/x; cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test\nhi\nEOF"
        self.assertIn("Essential tier", self.refusal(command) or "")
        command = f"cat <<'EOF' > /tmp/o/x; ACME_TEST_DATABASE_URL={URL} {HEAVY}\nhi\nEOF"
        self.assertIsNone(self.refusal(command))  # a heavy run of named files, with its slot
        self.assertIn(f"no slot names {LANE}", self.refusal(command.replace(URL, URL.replace("15432", "15431"))))

    def test_a_clear_full_suite_gets_its_own_line_first(self):
        command = f"cd {self.worktree} && ACME_TEST_DATABASE_URL={URL} bun test # <<EOF\nEOF"
        self.assertIn("reads outside", self.refusal(command.replace("bun test", f"bun test {SMALL}/f1.test.ts")))
        self.assertIn("Essential tier", self.refusal(command))

    def test_heredocs_written_as_usual_get_no_decision(self):
        for command in [
            "cat >> /tmp/o/notes.md <<'EOF'\nran bun test today\nEOF",
            f"cat > /tmp/o/x <<'EOF'\nbun test\nEOF\nACME_TEST_DATABASE_URL={URL} bun test {SMALL}/f1.test.ts",
            "git commit -q -m \"$(cat <<'EOF'\nfix: x\n\nbun test apps/web passes\nEOF\n)\"",
            "git commit -q -F - <<'EOF'\nfix: x\n\nbun test passes\nEOF",
            "cat <<EOF > /tmp/o/x\n$HOME bun test\nEOF",
            "cat <<-'EOF'\n\tbun test\n\tEOF",
            "python3 - <<'PY'\nprint('<<EOF', 'bun test')\nPY",
        ]:
            with self.subTest(command=command):
                self.calls.clear()
                self.assertIsNone(self.refusal(command))
                self.assertEqual(self.calls, [])

    def test_a_command_that_cant_start_a_run_isnt_read_for_this(self):
        for command in ["cat <<EOF\nEOF\nbun test\nEOF", "ls # <<EOF\nbun test\nEOF", "cat <<<EOF\nbun test\nEOF"]:
            with self.subTest(command=command):
                self.assertIsNone(self.refusal(command, cwd="/tmp"))
        self.assertIn("reads outside", self.refusal(f"echo '<<EOF'\ncd {self.worktree} && bun test\nEOF", cwd="/tmp"))
        self.assertIn("reads outside", self.refusal("echo '<<EOF'\nsh scripts/test-db.sh run x 1 -- bun test\nEOF",
                                                    cwd="/tmp"))

    def test_the_off_switch_lets_it_go(self):
        (self.root / guard.OFF_SWITCH).touch()
        self.assertIsNone(self.refusal("echo '<<EOF'\nbun test\nEOF"))

    def test_an_error_in_the_check_lets_the_run_go_and_logs_it(self):
        with mock.patch("cq_write.heredoc_doubt", side_effect=KeyError("a bug")):
            self.assertIsNone(self.refusal("cat <<EOF\nEOF\nbun test\nEOF"))
        self.assertIn("heredoc check skipped: KeyError", self.errors())

    def test_it_exits_2_with_one_ascii_line(self):
        event = json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat <<<EOF\nbun test\nEOF"},
                            "cwd": str(self.worktree)})
        stderr = io.StringIO()
        with mock.patch.object(guard, "ROOT", self.company), mock.patch("sys.stdin", io.StringIO(event)), \
                redirect_stderr(stderr), self.assertRaises(SystemExit) as stop:
            guard.main()
        self.assertEqual(stop.exception.code, 2)
        self.assertEqual(len(stderr.getvalue().strip().splitlines()), 1)
        self.assertTrue(stderr.getvalue().isascii())

    def test_crafted_commands_are_read_in_near_linear_time(self):
        k = 500
        lines = "".join("b" * size + "\n" for size in range(1, k + 1))
        head = f"ACME_TEST_DATABASE_URL={URL} bun test {SMALL}/f1.test.ts\n"
        for command in (head + lines + ("cat <<" + "a" * k + "\n") * 260,
                        head + "cat <<EOF\n" * 25_600,
                        head + lines + ("echo '<<" + "a" * k + "'\n") * 260,
                        head + "cat <<'EOF'\nx\nEOF\n" * 16_000,
                        head + "cat <<'EOF' > x; y\nEOF\n" * 12_000,
                        head + "echo $((1<<2))\n" * 16_000):
            with self.subTest(size=len(command)):
                start = time.monotonic()
                self.refusal(command)
                self.assertLess(time.monotonic() - start, 3)


if __name__ == "__main__":
    unittest.main()
