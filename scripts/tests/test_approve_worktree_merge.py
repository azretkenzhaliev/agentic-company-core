"""Tests for scripts/hooks/approve_worktree_merge.py, run as Claude Code runs it:
JSON on stdin; an allow decision on stdout approves, no output leaves the
call to the normal permission rules. The hook takes its repo from its own
path, so each test runs a copy of it in a temporary repo layout, with a
company.json naming three made-up products. It approves the merge of
origin/main and, for engineering roles, the push of a task or ws branch."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "approve_worktree_merge.py"
MSG = '"D-20260101-x/3.1 RM-101 WS-A #4 DD-901 T-1 L1: merge origin/main for the landing"'
PRODUCTS = {"acme": {"repo": "Example-Co/acme-app", "workspace": "workspaces/acme/acme-app"},
            "demo": {"repo": "example-co/demo-app", "workspace": "workspaces/demo/demo-app"},
            "acme-real": {"repo": "example-co/acme-real", "workspace": "workspaces/acme-real/acme-app"}}
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def run_git(*args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, env=GIT_ENV, timeout=30,
    )


class Layout(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(os.path.realpath(tmp.name))
        (self.repo / "scripts" / "hooks").mkdir(parents=True)
        self.hook = self.repo / "scripts" / "hooks" / HOOK.name
        shutil.copy(HOOK, self.hook)
        shutil.copy(HOOK.parents[1] / "company_config.py", self.repo / "scripts")
        self.company({"products": PRODUCTS})
        product = self.repo / "workspaces" / "acme"
        (product / "acme-app" / ".git").mkdir(parents=True)
        (product / ".worktrees" / "RM-101-WS-A").mkdir(parents=True)
        (product / ".worktrees" / "RM-101-WS-A" / ".git").write_text("gitdir: ../../acme-app/.git/worktrees/RM-101-WS-A\n")
        (product / ".worktrees" / "plain").mkdir()
        (product / ".worktrees" / "to-main").symlink_to(product / "acme-app")
        self.wt = f"{product}/.worktrees/RM-101-WS-A"
        self.main = f"{product}/acme-app"
        self.product = product

    def company(self, settings):
        (self.repo / "company.json").write_text(settings if isinstance(settings, str) else json.dumps(settings))

    def decision(self, command, tool_name="Bash", agent_type=None, cwd="/tmp", env=GIT_ENV):
        payload = {
            "session_id": "test",
            "cwd": cwd,
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
        }
        if agent_type is not None:
            payload["agent_type"] = agent_type
        result = subprocess.run([sys.executable, str(self.hook)], input=json.dumps(payload), capture_output=True, text=True, timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

    def assertApproved(self, command):
        self.assertEqual(self.decision(command), "allow", command)

    def assertNotApproved(self, command):
        self.assertIsNone(self.decision(command), command)


class ApproveWorktreeMerge(Layout):
    def test_approves_the_exact_shape(self):
        self.assertApproved(f"git -C {self.wt} merge --no-edit -m {MSG} origin/main")
        self.assertApproved(f'git -C {self.wt} merge --no-edit -m "x" origin/main')
        self.assertApproved(f'  git -C {self.wt} merge --no-edit -m "x" origin/main  ')

    def test_other_refs_are_not_approved(self):
        for ref in ["origin/develop", "origin/main~1", "main", "HEAD", "FETCH_HEAD", "origin/main origin/x", "origin/mainx"]:
            with self.subTest(ref=ref):
                self.assertNotApproved(f'git -C {self.wt} merge --no-edit -m "x" {ref}')

    def test_extra_flags_are_not_approved(self):
        for extra in [
            "-s ours", "--strategy=ours", "--strategy ours", "-X theirs", "-Xtheirs", "--strategy-option=theirs",
            "--allow-unrelated-histories", "--squash", "--no-verify", "--no-ff", "--ff-only", "--no-commit",
            "-m y", "--into-name main", "-S", "--signoff",
        ]:
            for command in [
                f'git -C {self.wt} merge --no-edit -m "x" {extra} origin/main',
                f'git -C {self.wt} merge --no-edit {extra} -m "x" origin/main',
                f'git -C {self.wt} merge {extra} --no-edit -m "x" origin/main',
            ]:
                with self.subTest(command=command):
                    self.assertNotApproved(command)
        self.assertNotApproved(f'git -C {self.wt} merge -m "x" origin/main')
        self.assertNotApproved(f'git -C {self.wt} merge --no-edit origin/main')
        self.assertNotApproved(f'git -c core.hooksPath=/tmp -C {self.wt} merge --no-edit -m "x" origin/main')
        self.assertNotApproved(f'git -C {self.wt} -c core.hooksPath=/tmp merge --no-edit -m "x" origin/main')

    def test_messages_the_shell_could_change_are_not_approved(self):
        for message in [
            '"a; touch x"', '"a & touch x"', '"a | sh"', '"$(touch x)"', '"`touch x`"', '"$HOME"',
            '"a\ntouch x"', '"a\\"b"', '"a > f"', '"a < f"', '"(a)"', '"a!"', "'x'", "x", '""',
            '"x" "y"', '"x"y',
        ]:
            with self.subTest(message=message):
                self.assertNotApproved(f"git -C {self.wt} merge --no-edit -m {message} origin/main")

    def test_chained_or_redirected_commands_are_not_approved(self):
        merge = f'git -C {self.wt} merge --no-edit -m "x" origin/main'
        for command in [
            f"{merge} && touch x", f"{merge}; touch x", f"{merge} | tail -5", f"{merge} 2>&1", f"{merge} > out",
            f"{merge}\ntouch x", f"touch x; {merge}", f"cd /tmp && {merge}", f"W=x {merge}", f"{merge} &",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_other_paths_are_not_approved(self):
        for path in [
            self.main,
            f"{self.product}/.worktrees/plain",
            f"{self.product}/.worktrees/to-main",
            f"{self.product}/.worktrees/missing",
            f"{self.product}/.worktrees/../acme-app",
            f"{self.product}/.worktrees/..",
            f"{self.wt}/apps",
            f"{self.wt}/",
            f"{self.repo}/workspaces/.worktrees/x",
            "workspaces/acme/.worktrees/RM-101-WS-A",
            "$W",
            f'"{self.wt}"',
            "/home/someone/agentic-company/workspaces/acme/.worktrees/RM-101-WS-A",
        ]:
            with self.subTest(path=path):
                self.assertNotApproved(f'git -C {path} merge --no-edit -m "x" origin/main')

    def test_only_company_jsons_products_are_merged(self):
        merge = f'git -C {self.wt} merge --no-edit -m "x" origin/main'
        for settings in [{}, {"products": {}}, {"products": {"demo": PRODUCTS["demo"]}}, {"products": {"acme": {}}},
                         {"products": {"acme": {"workspace": "workspaces/acme-app"}}},
                         {"products": {"acme": {"workspace": ""}}}, {"products": []}, "not json"]:
            with self.subTest(settings=settings):
                self.company(settings)
                self.assertNotApproved(merge)
        self.company({"products": {"acme": PRODUCTS["acme"]}})
        self.assertApproved(merge)
        (self.repo / "company.json").unlink()
        self.assertNotApproved(merge)

    def test_other_git_writes_are_not_approved(self):
        for command in [
            f"git -C {self.wt} rebase origin/main",
            f"git -C {self.wt} reset --hard origin/main",
            f"git -C {self.wt} push --force origin HEAD",
            f"git -C {self.wt} pull --no-edit origin main",
            f'git -C {self.main} merge --no-edit -m "x" origin/main',
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_other_tools_and_bad_input_get_no_decision(self):
        self.assertIsNone(self.decision(f'git -C {self.wt} merge --no-edit -m "x" origin/main', tool_name="Read"))
        result = subprocess.run([sys.executable, str(self.hook)], input="not json", capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout), (0, ""))


ROLES = ["senior-engineer", "staff-engineer", "cto"]
ORIGIN = "git@github.com:Example-Co/acme-app.git"
WORKTREES = {
    "T-x": "task/x",
    "D-20260101-acme-2-header": "task/D-20260101-acme-2-header",
    "RM-101-WS-A": "ws/RM-101-WS-A-pipeline",
    "nested": "task/a/b.c_d-e",
}


class ApproveTaskPush(Layout):
    """The push half: `git -C <worktree> push [-u] origin <task/ or ws/ branch>`,
    on a real git repo whose worktrees each have their own branch, and whose
    origin is a company repo. No test pushes: the hook only reads git's refs
    and config."""

    def setUp(self):
        super().setUp()
        self.fake = self.wt
        product = self.repo / "workspaces" / "acme-real"
        main = product / "acme-app"
        main.mkdir(parents=True)
        run_git("init", "-q", "-b", "main", str(main))
        run_git("-C", str(main), "commit", "-q", "--allow-empty", "-m", "one")
        run_git("-C", str(main), "remote", "add", "origin", ORIGIN)
        for name, branch in WORKTREES.items():
            run_git("-C", str(main), "worktree", "add", "-q", f"../.worktrees/{name}", "-b", branch)
        (product / ".worktrees" / "plain").mkdir()
        (product / ".worktrees" / "to-main").symlink_to(main)
        self.product, self.main = product, str(main)
        self.wts = {branch: f"{product}/.worktrees/{name}" for name, branch in WORKTREES.items()}
        self.wt = self.wts["task/x"]

    def push(self, command, agent_type="staff-engineer", cwd="/tmp"):
        return self.decision(command, agent_type=agent_type, cwd=cwd)

    def assertPushApproved(self, command, **kw):
        self.assertEqual(self.push(command, **kw), "allow", command)

    def assertPushNotApproved(self, command, **kw):
        self.assertIsNone(self.push(command, **kw), command)

    def test_approves_the_exact_push_forms(self):
        for role in ROLES:
            for branch, wt in self.wts.items():
                for command in [
                    f"git -C {wt} push origin {branch}",
                    f"git -C {wt} push -u origin {branch}",
                    f"git -C {wt} push origin HEAD:{branch}",
                    f"git -C {wt} push -u origin HEAD:{branch}",
                    f"  git -C {wt} push -u origin {branch}\n",
                ]:
                    with self.subTest(role=role, command=command):
                        self.assertPushApproved(command, agent_type=role)

    def test_each_form_is_on_until_the_founder_turns_it_off(self):
        merge = f'git -C {self.wt} merge --no-edit -m "x" origin/main'
        push = f"git -C {self.wt} push origin task/x"
        for auto_approve, merges, pushes in [({}, True, True), ({"merge": True, "push": True}, True, True),
                                             ({"pr_ready": False}, True, True), ({"merge": False}, False, True),
                                             ({"push": False}, True, False), ({"merge": 1, "push": "yes"}, False, False),
                                             (None, False, False), ([], False, False)]:
            self.company({"products": PRODUCTS, "integrations": {"auto_approve": auto_approve}})
            with self.subTest(auto_approve=auto_approve):
                self.assertEqual(self.push(merge) == "allow", merges)
                self.assertEqual(self.push(push) == "allow", pushes)
        for settings in ({"products": PRODUCTS, "integrations": []}, "not json"):
            self.company(settings)
            self.assertEqual((self.push(merge), self.push(push)), (None, None))

    def test_only_the_worktrees_own_branch(self):
        for ref in [
            "task/D-20260101-acme-2-header", "HEAD:task/D-20260101-acme-2-header",
            "ws/RM-101-WS-A-pipeline", "HEAD:ws/RM-101-WS-A-pipeline", "task/missing", "HEAD:task/missing",
        ]:
            with self.subTest(ref=ref):
                self.assertPushNotApproved(f"git -C {self.wt} push -u origin {ref}")
        run_git("-C", self.wt, "checkout", "-q", "--detach")
        self.assertPushNotApproved(f"git -C {self.wt} push origin HEAD:task/x")
        self.assertPushNotApproved(f"git -C {self.wt} push origin task/x")

    def test_a_tag_or_other_ref_of_that_name_is_not_approved(self):
        for ref in ["refs/tags/task/x", "refs/task/x", "refs/remotes/task/x"]:
            with self.subTest(ref=ref):
                run_git("-C", self.main, "update-ref", ref, "HEAD")
                self.assertPushNotApproved(f"git -C {self.wt} push origin task/x")
                # HEAD:<branch> names the source itself, so a local ref of that name doesn't change it.
                self.assertPushApproved(f"git -C {self.wt} push origin HEAD:task/x")
                run_git("-C", self.main, "update-ref", "-d", ref)
        self.assertPushApproved(f"git -C {self.wt} push origin task/x")

    def test_push_remaps_in_git_config_are_not_approved(self):
        for key, value in [
            ("remote.origin.push", "refs/heads/task/x:refs/heads/main"),
            ("remote.origin.push", "+refs/heads/*:refs/heads/*"),
            ("remote.origin.pushurl", str(self.repo / "other.git")),
            ("remote.origin.mirror", "true"),
        ]:
            with self.subTest(key=key, value=value):
                run_git("-C", self.main, "config", key, value)
                self.assertPushNotApproved(f"git -C {self.wt} push origin task/x")
                self.assertPushNotApproved(f"git -C {self.wt} push origin HEAD:task/x")
                run_git("-C", self.main, "config", "--unset-all", key)
        self.assertPushApproved(f"git -C {self.wt} push origin task/x")

    def assertConfigRefused(self, *config, scope=None):
        """Approved before, and no decision for either push form once git's config holds <config>."""
        self.assertPushApproved(f"git -C {self.wt} push -u origin task/x")
        if scope == "global":
            path = self.repo / "global.gitconfig"
            run_git("config", "--file", str(path), *config)
            env = {**GIT_ENV, "GIT_CONFIG_GLOBAL": str(path)}
        else:
            run_git("-C", self.main, "config", *config)
            env = GIT_ENV
        for command in [f"git -C {self.wt} push -u origin task/x", f"git -C {self.wt} push origin HEAD:task/x"]:
            with self.subTest(config=config, scope=scope, command=command):
                self.assertIsNone(self.decision(command, agent_type="staff-engineer", env=env))

    def test_the_company_origins_are_approved(self):
        for url in ["git@github.com:example-co/demo-app.git", ORIGIN]:
            with self.subTest(url=url):
                run_git("-C", self.main, "remote", "set-url", "origin", url)
                self.assertPushApproved(f"git -C {self.wt} push -u origin task/x")

    def test_only_company_jsons_products_are_approved(self):
        push = f"git -C {self.wt} push -u origin task/x"
        self.assertPushApproved(push)
        for settings in [{}, {"products": {}}, {"products": {"demo": PRODUCTS["demo"]}}, {"products": {"acme": {}}},
                         {"products": []}, "not json"]:
            with self.subTest(settings=settings):
                self.company(settings)
                self.assertPushNotApproved(push)
        (self.repo / "company.json").unlink()
        self.assertPushNotApproved(push)

    def test_a_changed_origin_url_is_not_approved(self):
        for url in [
            str(self.repo / "other.git"), "git@github.com:someone/acme-app.git", "git@github.com:example-co/other.git", "https://github.com/Example-Co/acme-app",
            "ssh://git@github.com/Example-Co/acme-app.git", "git@github.com:Example-Co/acme-app.git/", "git@evil.example:Example-Co/acme-app.git",
            "https://github.com/Example-Co/acme-app.git", "https://github.com/example-co/demo-app.git",
        ]:
            with self.subTest(url=url):
                run_git("-C", self.main, "remote", "set-url", "origin", url)
                self.assertPushNotApproved(f"git -C {self.wt} push -u origin task/x")
        run_git("-C", self.main, "config", "--unset-all", "remote.origin.url")
        self.assertPushNotApproved(f"git -C {self.wt} push -u origin task/x")

    def test_a_second_origin_url_is_not_approved(self):
        self.assertConfigRefused("--add", "remote.origin.url", str(self.repo / "other.git"))

    def test_a_second_company_url_is_not_approved_either(self):
        self.assertConfigRefused("--add", "remote.origin.url", "git@github.com:example-co/demo-app.git")

    def legacy_remote(self, kind, text, keep_config):
        """origin also defined in the repo's legacy <common dir>/<kind>/origin file."""
        self.assertPushApproved(f"git -C {self.wt} push -u origin task/x")
        if not keep_config:
            run_git("-C", self.main, "config", "--remove-section", "remote.origin")
        (Path(self.main) / ".git" / kind).mkdir()
        (Path(self.main) / ".git" / kind / "origin").write_text(text)
        if not keep_config:
            urls = subprocess.run(["git", "-C", self.wt, "remote", "get-url", "--push", "--all", "origin"],
                                  capture_output=True, text=True, env=GIT_ENV, timeout=30).stdout.split()
            self.assertEqual(urls, [ORIGIN])
        for command in [f"git -C {self.wt} push -u origin task/x", f"git -C {self.wt} push origin HEAD:task/x"]:
            with self.subTest(kind=kind, keep_config=keep_config, command=command):
                self.assertPushNotApproved(command)

    def test_a_legacy_remotes_file_is_not_approved(self):
        # With no remote.origin.url in config, git takes origin's URL and Push lines from this file;
        # get-url then prints the company URL while the push goes to main.
        self.legacy_remote("remotes", f"URL: {ORIGIN}\nPush: refs/heads/task/x:refs/heads/main\n", keep_config=False)

    def test_a_legacy_remotes_file_beside_the_config_is_not_approved(self):
        self.legacy_remote("remotes", f"URL: {ORIGIN}\nPush: refs/heads/task/x:refs/heads/main\n", keep_config=True)

    def test_a_legacy_branches_file_is_not_approved(self):
        self.legacy_remote("branches", f"{ORIGIN}#main\n", keep_config=False)

    def test_a_legacy_branches_file_beside_the_config_is_not_approved(self):
        self.legacy_remote("branches", f"{ORIGIN}#main\n", keep_config=True)

    def test_insteadof_is_not_approved(self):
        self.assertConfigRefused(f"url.{self.repo}/other.git.insteadOf", ORIGIN)

    def test_insteadof_to_another_company_repo_is_not_approved(self):
        # The rewritten URL is on the allowlist: the key check refuses it, and so does the check
        # that get-url --push (rewritten) equals the config's remote.origin.url (not rewritten).
        self.assertConfigRefused("url.git@github.com:example-co/demo-app.git.insteadOf", ORIGIN)

    def test_insteadof_in_the_global_config_is_not_approved(self):
        self.assertConfigRefused(f"url.{self.repo}/other.git.insteadOf", ORIGIN, scope="global")

    def test_pushinsteadof_is_not_approved(self):
        self.assertConfigRefused(f"url.{self.repo}/other.git.pushInsteadOf", ORIGIN)

    def test_follow_tags_is_not_approved(self):
        self.assertConfigRefused("push.followTags", "true")

    def test_submodule_recursion_is_not_approved(self):
        self.assertConfigRefused("push.recurseSubmodules", "on-demand")

    def test_submodule_recurse_is_not_approved(self):
        self.assertConfigRefused("submodule.recurse", "true")

    def test_an_ssh_command_is_not_approved(self):
        self.assertConfigRefused("core.sshCommand", "ssh -o ProxyCommand=x")

    def test_a_remote_helper_is_not_approved(self):
        self.assertConfigRefused("remote.origin.vcs", "x")

    def test_a_receive_pack_is_not_approved(self):
        self.assertConfigRefused("remote.origin.receivepack", "git-receive-pack")

    def test_a_push_option_is_not_approved(self):
        self.assertConfigRefused("push.pushOption", "x")

    def upstream_worktree(self):
        """A worktree made from origin/main, as cto.md and staff-engineer.md make them: its branch's upstream is main."""
        run_git("-C", self.main, "update-ref", "refs/remotes/origin/main", "HEAD")
        wt = f"{self.product}/.worktrees/up"
        run_git("-C", self.main, "worktree", "add", "-q", wt, "-b", "task/up", "origin/main")
        merge = subprocess.run(["git", "-C", self.main, "config", "--get", "branch.task/up.merge"],
                               capture_output=True, text=True, env=GIT_ENV, timeout=30).stdout.strip()
        self.assertEqual(merge, "refs/heads/main")
        return wt

    def assertPushDefaultRefused(self, value):
        # With push.default=upstream (or its old name, tracking), git sends a bare `task/up` to main.
        wt = self.upstream_worktree()
        bare = [f"git -C {wt} push origin task/up", f"git -C {wt} push -u origin task/up"]
        for command in bare:
            self.assertPushApproved(command)
        run_git("-C", self.main, "config", "push.default", value)
        for command in [*bare, f"git -C {wt} push origin HEAD:task/up"]:
            with self.subTest(value=value, command=command):
                self.assertPushNotApproved(command)

    def test_push_default_upstream_is_not_approved(self):
        self.assertPushDefaultRefused("upstream")

    def test_push_default_tracking_is_not_approved(self):
        self.assertPushDefaultRefused("tracking")

    def test_push_default_at_any_value_or_scope_is_not_approved(self):
        self.assertConfigRefused("push.default", "simple")
        run_git("-C", self.main, "config", "--unset", "push.default")
        self.assertConfigRefused("push.default", "upstream", scope="global")

    def test_a_git_error_gives_no_decision(self):
        fake_product = Path(self.fake).parent.parent
        run_git("-C", self.main, "worktree", "add", "-q", str(fake_product / ".worktrees" / "real"), "-b", "task/real")
        self.assertPushApproved(f"git -C {fake_product}/.worktrees/real push origin task/real")
        self.assertPushNotApproved(f"git -C {self.fake} push origin HEAD:task/x")

    def test_a_separate_git_dir_repo_is_not_approved(self):
        own = self.product / ".worktrees" / "F"
        run_git("init", "-q", "-b", "task/f", "--separate-git-dir", str(self.repo / "fakegit"), str(own))
        run_git("-C", str(own), "commit", "-q", "--allow-empty", "-m", "f")
        run_git("-C", str(own), "remote", "add", "origin", ORIGIN)
        self.assertTrue((own / ".git").is_file())
        self.assertPushNotApproved(f"git -C {own} push -u origin task/f")
        self.assertPushNotApproved(f"git -C {own} push origin HEAD:task/f")

    def test_a_worktree_its_repo_doesnt_list_is_not_approved(self):
        moved = self.product / ".worktrees" / "moved"
        os.rename(self.wt, moved)
        self.assertPushNotApproved(f"git -C {moved} push -u origin task/x")
        run_git("-C", str(moved), "worktree", "repair")
        self.assertPushApproved(f"git -C {moved} push -u origin task/x")

    def test_a_slow_or_missing_git_gives_no_decision(self):
        slow, empty = self.repo / "slow-bin", self.repo / "empty-bin"
        slow.mkdir()
        empty.mkdir()
        (slow / "git").write_text("#!/bin/sh\nexec /bin/sleep 30\n")
        (slow / "git").chmod(0o755)
        for path, least in [(slow, 1), (empty, 0)]:
            with self.subTest(path=path.name):
                start = time.monotonic()
                self.assertIsNone(self.decision(f"git -C {self.wt} push -u origin task/x", agent_type="cto", env={**GIT_ENV, "PATH": str(path)}))
                self.assertGreaterEqual(time.monotonic() - start, least)
                self.assertLess(time.monotonic() - start, 10)

    def test_the_push_without_C_is_not_approved(self):
        for cwd in [self.wt, f"{self.wt}/", self.main, "/tmp"]:
            for command in ["git push origin task/x", "git push -u origin task/x", "git push -u origin HEAD:task/x"]:
                with self.subTest(cwd=cwd, command=command):
                    self.assertPushNotApproved(command, cwd=cwd)

    def test_other_roles_are_not_approved(self):
        for role in [None, "", "ceo", "platform-engineer", "code-reviewer", "senior-engineerx", "content-producer", "claude"]:
            with self.subTest(role=role):
                self.assertPushNotApproved(f"git -C {self.wt} push -u origin task/x", agent_type=role)

    def test_other_branches_and_refspecs_are_not_approved(self):
        for ref in [
            "main", "production", "staging", "HEAD", "HEAD:main", "HEAD:production", "HEAD:refs/heads/main",
            "task/x:main", "task/x main", "task/x task/y", "task/x HEAD:main", "main task/x", "refs/heads/task/x",
            "HEAD:refs/heads/task/x", "task", "task/", "ws", "ws/", "tasks/x", "wsx/x", "Task/x", "feature/x",
            "+task/x", "+HEAD:task/x", ":task/x", "task/x:", "task/*", "task/x*", "task/x^", "task/x~1", "task/@{u}",
            "task/x@{1}", "task/.x", "task/x/.y", "task//x", "task/x/", "HEAD~1:task/x", "HEAD^:task/x",
            "main:task/x", "task/x:task/x", "HEAD:task/x:y", "origin/task/x", "'task/x'", '"task/x"', "task/$X",
            "task/x\\;y",
        ]:
            with self.subTest(ref=ref):
                self.assertPushNotApproved(f"git -C {self.wt} push origin {ref}")

    def test_force_delete_and_other_flags_are_not_approved(self):
        for flag in [
            "--force", "-f", "--force-with-lease", "--force-with-lease=task/x", "--force-if-includes", "--mirror",
            "--all", "--branches", "--tags", "--follow-tags", "--delete", "-d", "--prune", "--no-verify", "--atomic",
            "-o ci.skip", "--push-option=x", "--receive-pack=sh", "--exec=sh", "--repo=upstream", "--set-upstream",
            "-uf", "-fu", "-u -f", "-v", "-q", "--dry-run", "-n", "--signed", "--thin", "--recurse-submodules=no",
        ]:
            for command in [
                f"git -C {self.wt} push {flag} origin task/x",
                f"git -C {self.wt} push -u {flag} origin task/x",
                f"git -C {self.wt} push origin {flag} task/x",
                f"git -C {self.wt} push origin task/x {flag}",
            ]:
                with self.subTest(command=command):
                    self.assertPushNotApproved(command, cwd=self.wt)
        for command in [
            f"git -C {self.wt} push origin :task/x",
            f"git -C {self.wt} push --delete origin task/x",
            f"git -C {self.wt} push origin --delete task/x",
            f"git -C {self.wt} push origin +task/x",
            f"git -C {self.wt} push -u -u origin task/x",
            f"git -C {self.wt} push  origin task/x",
            f"git -C {self.wt} push\torigin task/x",
            f"git -C {self.wt} push origin  task/x",
            f"git  -C {self.wt} push origin task/x",
        ]:
            with self.subTest(command=command):
                self.assertPushNotApproved(command, cwd=self.wt)

    def test_other_remotes_are_not_approved(self):
        for remote in [
            "upstream", "origin2", "Origin", "/tmp/x.git", "../x.git", "file:///tmp/x.git",
            "https://github.com/Example-Co/acme-app.git", "git@github.com:Example-Co/acme-app.git", "origin origin", "",
        ]:
            with self.subTest(remote=remote):
                self.assertPushNotApproved(f"git -C {self.wt} push {remote} task/x")

    def test_other_push_paths_are_not_approved(self):
        for path in [
            self.main,
            f"{self.product}/.worktrees/plain",
            f"{self.product}/.worktrees/to-main",
            f"{self.product}/.worktrees/missing",
            f"{self.product}/.worktrees/../acme-app",
            f"{self.product}/.worktrees/..",
            f"{self.product}/.worktrees/RM-101-WS-A/../RM-101-WS-A",
            f"{self.wt}/apps",
            f"{self.wt}/",
            str(self.repo),
            f"{self.repo}/workspaces/.worktrees/x",
            "workspaces/acme/.worktrees/RM-101-WS-A",
            "$W",
            f'"{self.wt}"',
            "/home/someone/agentic-company/workspaces/acme/.worktrees/RM-101-WS-A",
        ]:
            with self.subTest(path=path):
                self.assertPushNotApproved(f"git -C {path} push -u origin task/x", cwd=self.wt)

    def test_chained_or_wrapped_pushes_are_not_approved(self):
        push = f"git -C {self.wt} push -u origin task/x"
        for command in [
            f"{push} && touch x", f"{push}; touch x", f"{push} | tail -5", f"{push} 2>&1", f"{push} > out",
            f"{push}\ntouch x", f"touch x; {push}", f"cd {self.wt} && git push origin task/x", f"W=x {push}",
            f"{push} &", f"$({push})", f"`{push}`", f"echo $({push})", f"{push} $(touch x)",
            f"GIT_SSH_COMMAND=sh {push}", f"git -c core.sshCommand=sh -C {self.wt} push -u origin task/x",
            f"git -C {self.wt} -c core.hooksPath=/tmp push -u origin task/x",
            f"git --git-dir={self.main}/.git push origin task/x", f"git -C {self.wt} -C {self.main} push origin task/x",
            f"env git -C {self.wt} push origin task/x", f"command {push}", f"sudo {push}",
        ]:
            with self.subTest(command=command):
                self.assertPushNotApproved(command, cwd=self.wt)

    def test_the_merge_still_needs_no_role(self):
        for role in [None, "ceo", "staff-engineer"]:
            with self.subTest(role=role):
                self.assertEqual(self.decision(f'git -C {self.wt} merge --no-edit -m "x" origin/main', agent_type=role), "allow")

    def test_other_tools_get_no_push_decision(self):
        self.assertIsNone(self.decision(f"git -C {self.wt} push -u origin task/x", tool_name="Read", agent_type="cto"))


if __name__ == "__main__":
    unittest.main()
