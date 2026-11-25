"""Tests for scripts/hooks/guard_agent_spawn.py, run as Claude Code runs it:
JSON on stdin, exit 2 plus stderr to block, exit 0 to allow. The load and CPU count are set in the hook's own
process (PATCHED), so the real load never decides a test."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_agent_spawn.py"
ACCOUNTS = [None, str(Path.home() / ".claude"), str(Path.home() / ".claude-other"), "/tmp/other"]
IDLE = (1.0, 1.0, 1.0)  # a quiet machine: the org-chart tests never meet the load hold
# Runs the hook as __main__ with os.getloadavg and os.cpu_count set from argv: a load of null raises OSError.
PATCHED = (
    "import json, os, runpy, sys\n"
    "hook, load, cpus = sys.argv[1], json.loads(sys.argv[2]), int(sys.argv[3])\n"
    "def getloadavg():\n"
    "    if load is None:\n"
    "        raise OSError('load unavailable')\n"
    "    return tuple(load)\n"
    "os.getloadavg, os.cpu_count = getloadavg, lambda: cpus\n"
    "sys.argv = [hook]\n"
    "runpy.run_path(hook, run_name='__main__')\n"
)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HookCase(unittest.TestCase):
    def setUp(self):  # the project root the hook logs under: never the real checkout
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def run_hook(self, subagent_type, agent_type=None, tool_name="Agent", config_dir=None, load=IDLE, cpus=10,
                 prompt="y", root=None):
        tool_input = {"description": "x", "prompt": prompt}
        if subagent_type is not None:
            tool_input["subagent_type"] = subagent_type
        payload = {
            "session_id": "test",
            "cwd": "/tmp",
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
        }
        if agent_type:
            payload["agent_type"] = agent_type
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        env["CLAUDE_PROJECT_DIR"] = str(root or self.root)
        if config_dir:
            env["CLAUDE_CONFIG_DIR"] = config_dir
        return subprocess.run(
            [sys.executable, "-c", PATCHED, str(HOOK), json.dumps(load), str(cpus)],
            input=json.dumps(payload),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def assertAllowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertBlocked(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertIn("Blocked", result.stderr)


class GuardAgentSpawn(HookCase):
    # The CEO spawns the CTO, the analyst, the critic, the CMO, the platform engineer, and its own
    # code-reviewer for the gate on guardrail files (D-20260101-self-maintenance).

    def test_ceo_may_spawn_its_reports_and_the_gate_reviewer(self):
        for target in ["cto", "analyst", "critic", "cmo", "platform-engineer", "code-reviewer", "trend-researcher"]:
            with self.subTest(target=target):
                self.assertAllowed(self.run_hook(target, "ceo"))

    def test_ceo_may_not_spawn_agents_off_its_list(self):
        for target in ["staff-engineer", "senior-engineer", "design-reviewer", "general-purpose",
                       "content-producer", "content-reviewer"]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "ceo"))

    def test_ceo_may_not_spawn_the_default_agent(self):
        result = self.run_hook(None, "ceo")
        self.assertBlocked(result)
        self.assertIn("cto, analyst, critic, cmo, platform-engineer, code-reviewer", result.stderr)

    # The platform engineer spawns only its code-reviewer.

    def test_platform_engineer_spawns_only_the_code_reviewer(self):
        self.assertAllowed(self.run_hook("code-reviewer", "platform-engineer"))
        for target in ["cto", "senior-engineer", "staff-engineer", "analyst", "critic", "platform-engineer",
                       "general-purpose"]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "platform-engineer"))

    # The CMO spawns its team and the analyst; the producer, reviewer and performance-analyst spawn nothing.

    def test_cmo_spawns_its_team_and_the_analyst(self):
        for target in ["content-producer", "content-reviewer", "performance-analyst", "analyst", "trend-researcher"]:
            with self.subTest(target=target):
                self.assertAllowed(self.run_hook(target, "cmo"))

    def test_cmo_may_not_spawn_outside_marketing(self):
        for target in ["cto", "staff-engineer", "critic", "cmo", "general-purpose", None]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "cmo"))

    def test_producer_and_reviewer_spawn_nothing(self):
        for caller in ["content-producer", "content-reviewer", "performance-analyst"]:
            for target in ["content-reviewer", "content-producer", "analyst", "general-purpose"]:
                with self.subTest(caller=caller, target=target):
                    result = self.run_hook(target, caller)
                    self.assertBlocked(result)
                    self.assertIn("no agents", result.stderr)

    # Marketing runs on any Claude account (CLAUDE_CONFIG_DIR).

    def test_a_marketing_agent_passes_on_a_session_with_no_claude_config_dir(self):
        self.assertAllowed(self.run_hook("cmo", "ceo", config_dir=None))

    def test_marketing_agents_start_on_any_account(self):
        for config_dir in ACCOUNTS:
            for target, caller in [("cmo", "ceo"), ("content-producer", "cmo"), ("content-reviewer", "cmo"),
                                   ("performance-analyst", "cmo"), ("cmo", None)]:
                with self.subTest(config_dir=config_dir, target=target, caller=caller):
                    self.assertAllowed(self.run_hook(target, caller, config_dir=config_dir))

    def test_the_org_chart_holds_marketing_on_any_account(self):
        for config_dir in ACCOUNTS:
            for target, caller in [("content-producer", "ceo"), ("content-reviewer", "ceo"), ("cmo", "cto"),
                                   ("content-reviewer", "content-producer"), ("cmo", "cmo")]:
                with self.subTest(config_dir=config_dir, target=target, caller=caller):
                    self.assertBlocked(self.run_hook(target, caller, config_dir=config_dir))

    def test_ceo_and_cmo_start_the_trend_researcher_on_either_account(self):
        for config_dir in ACCOUNTS:
            for caller in ["ceo", "cmo"]:
                with self.subTest(config_dir=config_dir, caller=caller):
                    self.assertAllowed(self.run_hook("trend-researcher", caller, config_dir=config_dir))

    def test_only_the_ceo_and_cmo_start_the_trend_researcher(self):
        for caller in ["cto", "staff-engineer", "platform-engineer", "critic", "content-producer",
                       "content-reviewer", "performance-analyst"]:
            with self.subTest(caller=caller):
                self.assertBlocked(self.run_hook("trend-researcher", caller))

    def test_the_trend_researcher_spawns_nothing(self):
        for target in ["analyst", "code-reviewer", "general-purpose", None]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "trend-researcher"))

    # The reel-analyst has the same two managers.

    def test_ceo_and_cmo_start_the_reel_analyst_on_either_account(self):
        for config_dir in [None, str(Path.home() / ".claude"), str(Path.home() / ".claude-other")]:
            for caller in ["ceo", "cmo"]:
                with self.subTest(config_dir=config_dir, caller=caller):
                    self.assertAllowed(self.run_hook("reel-analyst", caller, config_dir=config_dir))

    def test_only_the_ceo_and_cmo_start_the_reel_analyst(self):
        for caller in ["cto", "staff-engineer", "platform-engineer", "critic", "content-producer",
                       "content-reviewer", "performance-analyst", "trend-researcher"]:
            with self.subTest(caller=caller):
                self.assertBlocked(self.run_hook("reel-analyst", caller))

    def test_the_reel_analyst_spawns_nothing(self):
        for target in ["analyst", "code-reviewer", "trend-researcher", "general-purpose", None]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "reel-analyst"))

    # The ux-expert: started by the CEO, the CTO, a Staff engineer (at depth 3) or the CMO; it spawns
    # nothing.

    def test_ceo_cto_staff_and_cmo_start_the_ux_expert(self):
        for caller in ["ceo", "cto", "staff-engineer", "cmo"]:
            with self.subTest(caller=caller):
                self.assertAllowed(self.run_hook("ux-expert", caller))

    def test_no_one_else_on_the_chart_starts_the_ux_expert(self):
        for caller in ["platform-engineer", "critic", "content-producer", "content-reviewer",
                       "performance-analyst", "trend-researcher", "reel-analyst", "ux-expert"]:
            with self.subTest(caller=caller):
                self.assertBlocked(self.run_hook("ux-expert", caller))

    def test_the_ux_expert_spawns_nothing(self):
        for target in ["analyst", "code-reviewer", "senior-engineer", "general-purpose", None]:
            with self.subTest(target=target):
                result = self.run_hook(target, "ux-expert")
                self.assertBlocked(result)
                self.assertIn("no agents", result.stderr)

    def test_old_tool_name_task_is_guarded_too(self):
        self.assertBlocked(self.run_hook("staff-engineer", "ceo", tool_name="Task"))

    def test_case_and_spaces_are_ignored(self):
        self.assertAllowed(self.run_hook(" CTO ", "ceo"))

    # The CTO and Staff spawn their own reports, whoever started the session.

    def test_cto_may_spawn_its_reports(self):
        for target in ["staff-engineer", "senior-engineer", "code-reviewer"]:
            with self.subTest(target=target):
                self.assertAllowed(self.run_hook(target, "cto"))

    def test_cto_may_not_spawn_outside_its_reports(self):
        for target in ["design-reviewer", "cto", "analyst", "general-purpose", "fork"]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "cto"))

    def test_staff_may_spawn_its_reports(self):
        for target in ["design-reviewer", "senior-engineer", "code-reviewer"]:
            with self.subTest(target=target):
                self.assertAllowed(self.run_hook(target, "staff-engineer"))

    def test_staff_may_not_spawn_another_staff_or_upward(self):
        for target in ["staff-engineer", "cto", "general-purpose"]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "staff-engineer"))

    def test_critic_spawns_nothing(self):
        for target in ["analyst", "cto", "critic", "general-purpose", None]:
            with self.subTest(target=target):
                result = self.run_hook(target, "critic")
                self.assertBlocked(result)
                self.assertIn("no agents", result.stderr)

    # Everyone else is not limited by this hook.

    def test_plain_session_is_not_limited(self):
        self.assertAllowed(self.run_hook("staff-engineer"))
        self.assertAllowed(self.run_hook("general-purpose"))

    def test_other_tools_are_ignored(self):
        self.assertAllowed(self.run_hook("staff-engineer", "ceo", tool_name="Read"))

    def test_what_it_cant_read_is_refused(self):
        for text in ("not json", "[]", '{"tool_name": "Agent", "agent_type": "cto", "tool_input": [1]}'):
            with self.subTest(text=text):
                result = subprocess.run([sys.executable, str(HOOK)], input=text, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 2)
                self.assertIn("couldn't check", result.stderr)


class LoadHold(HookCase):
    """A new agent that runs tests or builds waits while the 5-minute load is 2.5 per CPU or more, or unreadable."""

    # Each heavy type with each held caller the org chart lets start it.
    HEAVY_SPAWNS = [("senior-engineer", "cto"), ("senior-engineer", "staff-engineer"), ("code-reviewer", "ceo"),
                    ("code-reviewer", "cto"), ("code-reviewer", "staff-engineer"),
                    ("code-reviewer", "platform-engineer"), ("staff-engineer", "cto"), ("platform-engineer", "ceo"),
                    ("ux-expert", "ceo"), ("ux-expert", "cto"), ("ux-expert", "staff-engineer"),
                    ("content-producer", "cmo"), ("ux-expert", "cmo")]
    # Each type that runs no tests or builds, with a caller that may start it.
    LIGHT_SPAWNS = [("cto", "ceo"), ("analyst", "ceo"), ("critic", "ceo"), ("cmo", "ceo"), ("trend-researcher", "ceo"),
                    ("reel-analyst", "ceo"), ("design-reviewer", "staff-engineer"), ("content-reviewer", "cmo"),
                    ("performance-analyst", "cmo"), ("analyst", "cmo"), ("trend-researcher", "cmo"),
                    ("reel-analyst", "cmo")]

    def test_the_heavy_list(self):
        guard = load_module(HOOK, "guard_agent_spawn")
        self.assertEqual(set(guard.HEAVY), {"senior-engineer", "code-reviewer", "staff-engineer", "platform-engineer",
                                            "ux-expert", "content-producer"})
        agents = {path.stem for path in (HOOK.parents[2] / ".claude" / "agents").glob("*/*.md")}
        self.assertLessEqual(set(guard.HEAVY), agents)
        self.assertEqual({target for target, _ in self.HEAVY_SPAWNS}, set(guard.HEAVY))
        self.assertFalse({target for target, _ in self.LIGHT_SPAWNS} & set(guard.HEAVY))

    def test_the_held_callers_are_those_whose_files_carry_the_hold(self):
        guard = load_module(HOOK, "guard_agent_spawn")
        self.assertEqual(guard.HELD_CALLERS, {"ceo", "cto", "staff-engineer", "platform-engineer", "cmo"})
        self.assertEqual({caller for _, caller in self.HEAVY_SPAWNS}, guard.HELD_CALLERS)
        for caller in guard.HELD_CALLERS:
            with self.subTest(caller=caller):
                [path] = (HOOK.parents[2] / ".claude" / "agents").glob(f"*/{caller}.md")
                self.assertIn("python3 scripts/capacity_scan.py --mac", path.read_text(encoding="utf-8"))
        cmo = (HOOK.parents[2] / ".claude" / "agents" / "marketing" / "cmo.md").read_text(encoding="utf-8")
        self.assertIn("- **The load hold**", cmo)  # the section the hook's message names for the cmo

    def test_at_the_threshold_each_heavy_spawn_waits(self):
        for target, caller in self.HEAVY_SPAWNS:
            with self.subTest(target=target, caller=caller):
                result = self.run_hook(target, caller, load=(30.0, 25.0, 20.0))
                self.assertBlocked(result)
                self.assertIn("5-minute load is 25.00", result.stderr)
                self.assertIn("while it is 25 or more (2.5 per CPU on 10 CPUs)", result.stderr)
                self.assertIn("Running work goes on: nothing is stopped.", result.stderr)

    def test_just_under_the_threshold_each_heavy_spawn_starts(self):
        for target, caller in self.HEAVY_SPAWNS:
            with self.subTest(target=target, caller=caller):
                self.assertAllowed(self.run_hook(target, caller, load=(30.0, 24.99, 30.0)))

    def test_over_the_threshold_the_gates_reviewer_waits(self):
        result = self.run_hook("code-reviewer", "ceo", load=(40.5, 40.5, 40.5))
        self.assertBlocked(result)
        self.assertIn("is 40.50", result.stderr)
        self.assertIn("runs the tests the diff touches", result.stderr)

    def test_only_the_5_minute_load_counts(self):
        self.assertAllowed(self.run_hook("senior-engineer", "cto", load=(99.0, 1.0, 99.0)))
        self.assertBlocked(self.run_hook("senior-engineer", "cto", load=(1.0, 25.0, 1.0)))

    def test_the_limit_is_per_cpu(self):
        self.assertAllowed(self.run_hook("senior-engineer", "cto", load=(0, 9.99, 0), cpus=4))
        result = self.run_hook("senior-engineer", "cto", load=(0, 10.0, 0), cpus=4)
        self.assertBlocked(result)
        self.assertIn("while it is 10 or more (2.5 per CPU on 4 CPUs)", result.stderr)

    def test_an_unreadable_load_holds_each_heavy_spawn(self):
        for target, caller in self.HEAVY_SPAWNS:
            with self.subTest(target=target, caller=caller):
                result = self.run_hook(target, caller, load=None)
                self.assertBlocked(result)
                self.assertIn("5-minute load can't be read", result.stderr)

    def test_light_spawns_start_at_any_load(self):
        for target, caller in self.LIGHT_SPAWNS:
            for load in [(99.0, 99.0, 99.0), None]:
                with self.subTest(target=target, caller=caller, load=load):
                    self.assertAllowed(self.run_hook(target, caller, load=load))

    def test_the_org_chart_refuses_first(self):
        result = self.run_hook("senior-engineer", "ceo", load=(99.0, 99.0, 99.0))
        self.assertBlocked(result)
        self.assertIn("the org chart", result.stderr)
        self.assertNotIn("load", result.stderr)

    def test_the_cmo_holds_its_producer_and_ux_expert(self):
        for target in ["content-producer", "ux-expert"]:
            with self.subTest(target=target):
                result = self.run_hook(target, "cmo", load=(0, 25.0, 0), cpus=10)
                self.assertBlocked(result)
                self.assertIn("5-minute load is 25.00", result.stderr)
                self.assertIn("while it is 25 or more (2.5 per CPU on 10 CPUs)", result.stderr)
                self.assertIn("(wait and re-check as cmo.md, \"The load hold\", says)", result.stderr)
                result = self.run_hook(target, "cmo", load=None, cpus=10)
                self.assertBlocked(result)
                self.assertIn("5-minute load can't be read", result.stderr)
                self.assertAllowed(self.run_hook(target, "cmo", load=(99.0, 24.99, 99.0), cpus=10))

    def test_callers_off_the_chart_are_not_held(self):
        for target in ["senior-engineer", "code-reviewer", "content-producer"]:
            for load in [(99.0, 99.0, 99.0), None]:
                with self.subTest(target=target, load=load):
                    self.assertAllowed(self.run_hook(target, None, load=load))

    FIX_PROMPT = "ORDER D-20260101-x/1   from: cto   to: senior-engineer\nPRODUCTION FIX: sign-in returns 500\nObjective: y"

    def fix_log(self, root=None):
        path = (root or self.root) / "workspaces" / "system" / "production-fix-spawns.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def test_a_production_fix_is_not_held(self):
        for load in [(40.5, 40.5, 40.5), None]:
            with self.subTest(load=load):
                self.assertAllowed(self.run_hook("senior-engineer", "cto", load=load, prompt=self.FIX_PROMPT))
                self.assertAllowed(self.run_hook("code-reviewer", "cto", load=load, prompt=self.FIX_PROMPT))
                self.assertAllowed(self.run_hook("content-producer", "cmo", load=load, prompt=self.FIX_PROMPT))
                self.assertAllowed(self.run_hook("ux-expert", "cmo", load=load, prompt=self.FIX_PROMPT))

    def test_each_spawn_the_production_fix_line_lets_through_is_logged(self):
        before = datetime.now(timezone.utc).replace(microsecond=0)
        self.assertAllowed(self.run_hook("senior-engineer", "cto", load=(0, 40.5, 0), prompt=self.FIX_PROMPT))
        self.assertAllowed(self.run_hook("code-reviewer", "staff-engineer", load=None, prompt=self.FIX_PROMPT))
        self.assertAllowed(self.run_hook("content-producer", "cmo", load=(0, 25.0, 0), prompt=self.FIX_PROMPT))
        self.assertAllowed(self.run_hook("ux-expert", "cmo", load=None, prompt=self.FIX_PROMPT))
        after = datetime.now(timezone.utc)
        records = self.fix_log()
        self.assertEqual([(r["caller"], r["agent_type"], r["line"]) for r in records],
                         [("cto", "senior-engineer", "PRODUCTION FIX: sign-in returns 500"),
                          ("staff-engineer", "code-reviewer", "PRODUCTION FIX: sign-in returns 500"),
                          ("cmo", "content-producer", "PRODUCTION FIX: sign-in returns 500"),
                          ("cmo", "ux-expert", "PRODUCTION FIX: sign-in returns 500")])
        for record in records:
            self.assertRegex(record["time"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            moment = datetime.strptime(record["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            self.assertTrue(before <= moment <= after, record["time"])

    def test_a_spawn_the_line_doesnt_let_through_isnt_logged(self):
        self.assertAllowed(self.run_hook("senior-engineer", "cto", load=(0, 24.99, 0), prompt=self.FIX_PROMPT))
        self.assertAllowed(self.run_hook("analyst", "ceo", load=(0, 99.0, 0), prompt=self.FIX_PROMPT))
        self.assertAllowed(self.run_hook("content-reviewer", "cmo", load=(0, 99.0, 0), prompt=self.FIX_PROMPT))
        self.assertAllowed(self.run_hook("content-producer", "cmo", load=(0, 24.99, 0), prompt=self.FIX_PROMPT))
        self.assertBlocked(self.run_hook("senior-engineer", "ceo", load=(0, 99.0, 0), prompt=self.FIX_PROMPT))
        self.assertBlocked(self.run_hook("senior-engineer", "cto", load=(0, 99.0, 0), prompt="not a PRODUCTION FIX: x"))
        self.assertEqual(self.fix_log(), [])

    def test_a_log_it_cant_write_doesnt_hold_the_fix(self):
        blocker = self.root / "a-file"
        blocker.write_text("x", encoding="utf-8")  # the project root is a file: the log's folder can't be made
        self.assertAllowed(self.run_hook("senior-engineer", "cto", load=(0, 40.5, 0), prompt=self.FIX_PROMPT,
                                         root=blocker))

    def test_the_log_is_gitignored(self):
        guard = load_module(HOOK, "guard_agent_spawn")
        self.assertEqual(guard.PRODUCTION_FIX_LOG.parts[:2], ("workspaces", "system"))
        lines = (HOOK.parents[2] / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("workspaces/", lines)

    def test_the_production_fix_line_must_start_a_line_and_name_the_fault(self):
        for prompt in ["not a PRODUCTION FIX: sign-in", "PRODUCTION FIX:", "PRODUCTION FIX:   \nObjective: y",
                       "production fix: sign-in", " PRODUCTION FIX: sign-in", "PRODUCTION FIX sign-in"]:
            with self.subTest(prompt=prompt):
                self.assertBlocked(self.run_hook("senior-engineer", "cto", load=(0, 25.0, 0), prompt=prompt))

    def test_the_message_names_the_only_forms_that_end_the_wait(self):
        result = self.run_hook("senior-engineer", "cto", load=(0, 25.0, 0))
        self.assertIn("This stop is a wait, and only these forms end it: this same spawn, unchanged, once that scan "
                      "prints `room: yes`", result.stderr)
        self.assertIn("or, for a production fix only (a fault live in production now), this same spawn "
                      "with a line in its prompt starting `PRODUCTION FIX:` and naming the fault.", result.stderr)

    def test_the_message_names_the_callers_own_wait(self):  # the cmo has no foreground wait (cmo.md, "The load hold")
        for target, caller in self.HEAVY_SPAWNS:
            with self.subTest(target=target, caller=caller):
                result = self.run_hook(target, caller, load=(0, 25.0, 0))
                rules = "cmo.md" if caller == "cmo" else "cto.md"
                self.assertIn(f"(wait and re-check as {rules}, \"The load hold\", says)", result.stderr)

    def test_the_limit_and_the_reading_are_the_scans(self):
        guard = load_module(HOOK, "guard_agent_spawn")
        scan = load_module(HOOK.parents[1] / "capacity_scan.py", "capacity_scan")
        self.assertEqual(guard.LOAD_PER_CPU, scan.LOAD_PER_CPU)

        def run(args, **kwargs):  # sysctl: pressure normal; memory_pressure: 80% free
            return subprocess.CompletedProcess(args, 0, stdout="1" if args[0] == "sysctl" else
                                               "System-wide memory free percentage: 80%", stderr="")

        def unreadable():
            raise OSError("load unavailable")

        disk = SimpleNamespace(free=900e9)
        for cpus in [10, 4]:
            for five in [0.0, 9.99, 10.0, 24.99, 25.0, 40.5, None]:
                getloadavg = unreadable if five is None else (lambda five=five: (0.0, five, 0.0))
                with self.subTest(cpus=cpus, five=five), \
                        mock.patch.object(os, "getloadavg", getloadavg), \
                        mock.patch.object(os, "cpu_count", lambda cpus=cpus: cpus), \
                        mock.patch.object(scan.shutil, "disk_usage", return_value=disk), \
                        mock.patch.object(scan.subprocess, "run", run):
                    room, line = scan.mac_room()
                    self.assertEqual(guard.load_hold("code-reviewer", "y") is None, room, line)


if __name__ == "__main__":
    unittest.main()
