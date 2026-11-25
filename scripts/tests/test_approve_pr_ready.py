"""Tests for scripts/hooks/approve_pr_ready.py, run as Claude Code runs it:
JSON on stdin; an allow decision on stdout approves, no output leaves the
call to the normal permission rules. The hook reads the products from its own
repo's company.json, so each test runs a copy of it in a temporary repo."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "approve_pr_ready.py"
EXACT = "gh pr ready 12 --repo Example-Co/acme-app"


class ApprovePrReady(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        (self.repo / "scripts" / "hooks").mkdir(parents=True)
        self.hook = self.repo / "scripts" / "hooks" / HOOK.name
        shutil.copy(HOOK, self.hook)
        shutil.copy(HOOK.parents[1] / "company_config.py", self.repo / "scripts")
        self.company({"products": {"acme": {"repo": "Example-Co/acme-app", "workspace": "workspaces/acme/acme-app"}}})

    def company(self, settings):
        (self.repo / "company.json").write_text(settings if isinstance(settings, str) else json.dumps(settings))

    def run_hook(self, payload_text):
        return subprocess.run([sys.executable, str(self.hook)], input=payload_text, capture_output=True, text=True, timeout=30)

    def decision(self, command, agent_type="staff-engineer", agent_id=None, tool_name="Bash"):
        payload = {
            "session_id": "test",
            "cwd": "/tmp",
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
        }
        if agent_type is not None:
            payload["agent_type"] = agent_type
        if agent_id is not None:
            payload["agent_id"] = agent_id
        result = self.run_hook(json.dumps(payload))
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

    def assertApproved(self, command, **kwargs):
        self.assertEqual(self.decision(command, **kwargs), "allow", command)

    def assertNotApproved(self, command, **kwargs):
        self.assertIsNone(self.decision(command, **kwargs), command)

    def test_approves_the_exact_form_for_the_roles_that_land(self):
        for number in ["1", "9", "10", "12", "1000000"]:
            with self.subTest(number=number):
                self.assertApproved(f"gh pr ready {number} --repo Example-Co/acme-app")
        self.assertApproved(EXACT, agent_type="staff-engineer", agent_id="abc123")  # a subagent
        self.assertApproved(EXACT, agent_type="staff-engineer")  # a --agent session
        self.assertApproved(EXACT, agent_type="cto", agent_id="abc123")
        self.assertApproved(EXACT, agent_type="cto")

    def test_other_roles_get_no_decision(self):
        for role in [
            None, "", "ceo", "senior-engineer", "code-reviewer", "design-reviewer", "platform-engineer", "critic",
            "analyst", "cmo", "content-producer", "general-purpose", "claude", "Explore", "fork",
            "Staff-Engineer", "CTO", "staff-engineer ", " cto", "staff_engineer", "plugin:cto", "plugin:staff-engineer",
        ]:
            with self.subTest(role=role):
                self.assertNotApproved(EXACT, agent_type=role)
        self.assertNotApproved(EXACT, agent_type="senior-engineer", agent_id="abc123")

    def test_anything_but_a_bare_integer_is_not_approved(self):
        for number in [
            "", "0", "00", "01", "007", "-1", "+1", "1.0", "1e3", "0x10", "1_000", "1,2", "#12", "12a", "a12",
            "1 2", "12*", "1?", "[1]2", "{1,2}", '"12"', "'12'", "\\12", "$N", "${N}", "$(echo 12)", "`echo 12`",
            "١٢", "１２", "²", "١2", "1２", "1٢",
            "ws/RM-101-WS-A-x", "https://github.com/Example-Co/acme-app/pull/12", "Example-Co/acme-app#12",
        ]:
            with self.subTest(number=number):
                self.assertNotApproved(f"gh pr ready {number} --repo Example-Co/acme-app")

    def test_undo_and_every_other_flag_are_not_approved(self):
        for flag in ["--undo", "--help", "-h", "--repo Example-Co/acme-app", "--repo other/repo", "-R other/repo", "--", "--json number"]:
            for command in [
                f"gh pr ready 12 --repo Example-Co/acme-app {flag}",
                f"gh pr ready 12 {flag} --repo Example-Co/acme-app",
                f"gh pr ready {flag} 12 --repo Example-Co/acme-app",
                f"gh pr {flag} ready 12 --repo Example-Co/acme-app",
                f"gh {flag} pr ready 12 --repo Example-Co/acme-app",
            ]:
                with self.subTest(command=command):
                    self.assertNotApproved(command)

    def test_another_order_of_the_words_is_not_approved(self):
        for command in [
            "gh pr ready --repo Example-Co/acme-app 12",
            "gh pr ready -R Example-Co/acme-app 12",
            "gh pr ready 12 -R Example-Co/acme-app",
            "gh pr ready 12 --repo=Example-Co/acme-app",
            "gh pr ready 12 --rep Example-Co/acme-app",
            "gh pr ready 12",
            "gh pr ready",
            "gh pr ready --repo Example-Co/acme-app",
            "gh pr ready 12 --repo",
            "gh ready 12 --repo Example-Co/acme-app",
            "pr ready 12 --repo Example-Co/acme-app",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_other_repos_are_not_approved(self):
        for repo in [
            "example-co/acme-app", "Example-Co/Acme-app", "EXAMPLE-CO/ACME-APP", "Example-Co/acme-app.git", "Example-Co/acme-app/",
            "Example-Co/acme-app2", "Example-Co/other", "example-co/demo-app", "github.com/Example-Co/acme-app", "https://github.com/Example-Co/acme-app",
            "evil.example/Example-Co/acme-app", '"Example-Co/acme-app"', "'Example-Co/acme-app'", "$REPO",
        ]:
            with self.subTest(repo=repo):
                self.assertNotApproved(f"gh pr ready 12 --repo {repo}")

    def test_only_company_jsons_products_are_approved(self):
        self.assertApproved(EXACT)
        demo = {"demo": {"repo": "example-co/demo-app"}}
        for settings in [{}, {"products": {}}, {"products": demo}, {"products": {"acme": {}}}, {"products": []}, "not json"]:
            with self.subTest(settings=settings):
                self.company(settings)
                self.assertNotApproved(EXACT)
        self.company({"products": demo})
        self.assertApproved("gh pr ready 12 --repo example-co/demo-app")
        (self.repo / "company.json").unlink()
        self.assertNotApproved(EXACT)

    def test_it_is_on_until_the_founder_turns_it_off(self):
        products = {"products": {"acme": {"repo": "Example-Co/acme-app"}}}
        for auto_approve, approved in [({}, True), ({"pr_ready": True}, True), ({"merge": False, "push": False}, True),
                                       ({"pr_ready": False}, False), ({"pr_ready": "yes"}, False),
                                       ({"pr_ready": None}, False), (None, False), ([], False), ("x", False)]:
            with self.subTest(auto_approve=auto_approve):
                self.company({**products, "integrations": {"auto_approve": auto_approve}})
                self.assertEqual(self.decision(EXACT), "allow" if approved else None)
        self.company({**products, "integrations": []})
        self.assertNotApproved(EXACT)

    def test_chained_redirected_or_prefixed_commands_are_not_approved(self):
        for command in [
            f"{EXACT} && touch x", f"{EXACT}; touch x", f"{EXACT};", f"{EXACT} || touch x", f"{EXACT} | tail -5",
            f"{EXACT} &", f"{EXACT} 2>&1", f"{EXACT} > out", f"{EXACT} >> out", f"{EXACT} < in", f"{EXACT} # note",
            f"{EXACT}\ntouch x", f"touch x\n{EXACT}", f"touch x; {EXACT}", f"cd /tmp && {EXACT}", f"gh pr view 12 && {EXACT}",
            f"({EXACT})", f"{{ {EXACT}; }}", f"$({EXACT})", f"`{EXACT}`", f"bash -c '{EXACT}'", f"sh -c \"{EXACT}\"",
            f"eval {EXACT}", f"env {EXACT}", f"sudo {EXACT}", f"time {EXACT}", f"timeout 60 {EXACT}", f"command {EXACT}",
            f"GH_HOST=evil.example {EXACT}", f"GH_REPO=other/repo {EXACT}", f"GH_TOKEN=x {EXACT}", f"N=12 {EXACT}",
            f"/opt/homebrew/bin/{EXACT}", f"./{EXACT}", f"\\{EXACT}",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_spacing_must_be_exact(self):
        for command in [
            f" {EXACT}", f"{EXACT} ", f"{EXACT}\n", f"\n{EXACT}", f"{EXACT}\r\n", f"{EXACT}\x00", f"\t{EXACT}",
            "gh  pr ready 12 --repo Example-Co/acme-app", "gh pr  ready 12 --repo Example-Co/acme-app",
            "gh pr ready  12 --repo Example-Co/acme-app", "gh pr ready 12  --repo Example-Co/acme-app",
            "gh pr ready 12 --repo  Example-Co/acme-app", "gh pr ready\t12 --repo Example-Co/acme-app",
            "gh pr ready 12\t--repo Example-Co/acme-app", "gh pr ready\n12 --repo Example-Co/acme-app",
            "gh pr ready 12 \\\n--repo Example-Co/acme-app", "gh\xa0pr ready 12 --repo Example-Co/acme-app",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_other_commands_are_not_approved(self):
        for command in [
            "gh pr merge 12 --repo Example-Co/acme-app --merge", "gh pr close 12 --repo Example-Co/acme-app",
            "gh pr reopen 12 --repo Example-Co/acme-app", "gh pr edit 12 --repo Example-Co/acme-app",
            "gh pr review 12 --approve --repo Example-Co/acme-app", "gh pr comment 12 --repo Example-Co/acme-app",
            "gh pr view 12 --repo Example-Co/acme-app", "gh api repos/Example-Co/acme-app/pulls/12",
            "GH PR READY 12 --repo Example-Co/acme-app", "gh pr Ready 12 --repo Example-Co/acme-app",
            "gh pr ready-up 12 --repo Example-Co/acme-app", "git pr ready 12 --repo Example-Co/acme-app",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_other_tools_and_bad_input_get_no_decision(self):
        self.assertIsNone(self.decision(EXACT, tool_name="Read"))
        self.assertIsNone(self.decision(EXACT, tool_name="Task"))
        for bad in [None, 12, ["gh", "pr", "ready"], {"command": EXACT}]:
            with self.subTest(command=bad):
                self.assertNotApproved(bad)
        result = self.run_hook(json.dumps({"tool_name": "Bash", "agent_type": "cto"}))
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        result = self.run_hook("not json")
        self.assertEqual((result.returncode, result.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
