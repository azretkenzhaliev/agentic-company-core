"""Tests for scripts/hooks/guard_vercel_cli.py, run as Claude Code runs it:
JSON on stdin, exit 2 plus stderr to block, exit 0 to allow."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_vercel_cli.py"
DEMO = "--scope demo-team"  # rolls back with the CLI
ACME = "--scope acme-team"  # production and aliases only through Git
SETTINGS = {"promote_scopes": ["demo-team"], "git_only_scopes": ["acme-team"]}


class GuardVercelCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.company(SETTINGS)

    def tearDown(self):
        self.tmp.cleanup()

    def company(self, vercel, text=None):
        """Writes the company.json the hook reads, with these "vercel" settings (None: without any)."""
        (self.root / "company.json").write_text(
            text if text is not None else json.dumps({"integrations": {} if vercel is None else {"vercel": vercel}}), encoding="utf-8")

    def run_hook(self, command, agent_type="cto", tool_name="Bash"):
        payload = {
            "session_id": "test",
            "cwd": "/tmp",
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
        }
        if agent_type:
            payload["agent_type"] = agent_type
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)), timeout=30)

    def assertAllowed(self, command, **kwargs):
        result = self.run_hook(command, **kwargs)
        self.assertEqual(result.returncode, 0, f"{command}: {result.stderr}")

    def assertBlocked(self, command, **kwargs):
        result = self.run_hook(command, **kwargs)
        self.assertEqual(result.returncode, 2, command)
        self.assertIn("Blocked", result.stderr)

    # Deploys from the CLI are refused for every agent, whatever is configured.

    def test_deploys_are_refused(self):
        for command in [
            "vercel deploy",
            "vercel",
            "vercel --prod",
            "vercel --yes",
            "vercel deploy --prod --scope acme-team",
            "vercel deploy --cwd /tmp/export --scope acme-team",
            "vercel --scope acme-team deploy",
            "vercel -S acme-team --prod",
            "vercel -e NODE_ENV=production",
            "vercel .",
            "vercel ./apps/web",
            f"vercel deploy {DEMO}",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_redeploy_and_link_are_refused(self):
        for command in [
            "vercel redeploy https://acme-app-abc.vercel.app --scope acme-team",
            f"vercel redeploy dpl_123 {DEMO}",
            "vercel link --yes --project acme-app --scope acme-team",
            "vercel --scope=acme-team link",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_promote_is_refused_except_where_the_runbook_rolls_back_with_it(self):
        for command in [
            "vercel promote https://acme-app-abc.vercel.app --scope acme-team",
            "vercel promote dpl_123",
            "vercel promote dpl_123 --scope=acme-team",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)
        for command in [
            f"vercel promote dpl_123 {DEMO} --yes",
            "vercel promote dpl_123 --scope=demo-team",
            "vercel -S demo-team promote dpl_123",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    # A Git-only product: rollback, alias writes and rolling releases are refused with its scope, or with none. Without a
    # "vercel" in company.json they all are.

    CHANGES = ["vercel rollback dpl_123", "vercel alias set a.vercel.app b.example.com", "vercel alias rm b.example.com",
               "vercel ln set a.vercel.app b.example.com", "vercel rolling-release start --dpl dpl_123", "vercel rr configure"]

    def test_git_only_rollback_alias_and_rolling_release_are_refused(self):
        for command in [
            "vercel rollback dpl_123 --scope acme-team --yes",
            "vercel rollback --scope=acme-team",
            "vercel -S ACME-TEAM rollback dpl_123",
            "vercel alias set https://acme-app-abc.vercel.app staging.example.com --scope acme-team",
            "vercel alias rm staging.example.com --scope acme-team --yes",
            "vercel ln set https://acme-app-abc.vercel.app staging.example.com --scope acme-team",
            "vercel rolling-release start --dpl dpl_123 --scope acme-team",
            "vercel rr configure --scope acme-team",
            "vercel rollback dpl_123",
            "vercel alias set a.vercel.app b.example.com",
            "vercel rr start",
            "cd workspaces/acme/acme-app && vercel rollback dpl_123",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_without_an_entry_rollback_alias_and_rolling_release_are_refused(self):
        for text in [None, "{}"]:  # no "vercel", and no integrations at all
            self.company(None, text)
            for command in self.CHANGES:
                for scope in ["", f" {DEMO}", f" {ACME}"]:
                    with self.subTest(text=text, command=command + scope):
                        self.assertBlocked(command + scope)
                        self.assertIn('until company.json\'s integrations has a "vercel"', self.run_hook(command + scope).stderr)
            for command in ["vercel rollback status demo", "vercel alias ls", f"vercel ln list {DEMO}"]:
                with self.subTest(text=text, command=command):
                    self.assertAllowed(command)
        (self.root / "company.json").unlink()
        self.assertBlocked(f"vercel rollback dpl_123 {DEMO}")

    def test_with_no_git_only_scopes_they_need_a_scope(self):
        for vercel in [{}, {"git_only_scopes": []}, {"promote_scopes": ["demo-team"], "value_scopes": []}]:
            self.company(vercel)
            for command in self.CHANGES:
                with self.subTest(vercel=vercel, command=command):
                    self.assertBlocked(command)
                    self.assertIn('"git_only_scopes"', self.run_hook(command).stderr)
                    self.assertBlocked(f"{command} --scope=")  # an empty scope is none
                    self.assertAllowed(f"{command} {DEMO}")
            for command in ["vercel rollback status demo", "vercel alias ls"]:
                with self.subTest(vercel=vercel, command=command):
                    self.assertAllowed(command)

    def test_rollbacks_and_reads_still_run(self):
        for command in [
            f"vercel rollback dpl_123 {DEMO} --yes",
            f"vercel rollback status demo {DEMO}",
            f"vercel promote dpl_123 {DEMO} --yes",
            f"vercel alias set a.vercel.app b.example.com {DEMO}",
            "vercel alias ls --scope acme-team",
            "vercel alias ls",
            "vercel rollback status acme-app --scope acme-team",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_without_settings_promote_and_value_reads_are_refused(self):
        reads = ["vercel env pull", f"vercel env pull {ACME}", f"vercel pull {DEMO}", f"vercel env run {ACME} -- ls"]
        for vercel, reads_run in [(None, False), ({}, True), ({"value_scopes": []}, False),
                                  ({"promote_scopes": [], "git_only_scopes": []}, True)]:
            self.company(vercel)
            for command in ["vercel deploy", f"vercel promote dpl_123 {DEMO}", f"vercel env ls --json {DEMO}",
                            f"vercel api /v10/projects/acme-app/env {ACME}", f"vercel redeploy dpl_123 {DEMO}",
                            f"vercel env pull --environment production {ACME}"]:
                with self.subTest(vercel=vercel, command=command):
                    self.assertBlocked(command)
            for command in ["vercel ls", "vercel env ls"]:
                with self.subTest(vercel=vercel, command=command):
                    self.assertAllowed(command)
            for command in reads:
                with self.subTest(vercel=vercel, command=command):
                    (self.assertAllowed if reads_run else self.assertBlocked)(command)
        (self.root / "company.json").unlink()
        self.assertBlocked("vercel deploy")
        self.assertBlocked(f"vercel env pull {ACME}")

    def test_a_broken_company_json_refuses_every_vercel_call(self):
        for text in ["{", "[]", '{"integrations": []}', '{"integrations": {"vercel": true}}', '{"integrations": {"vercel": []}}',
                     '{"integrations": {"vercel": {"value_scopes": null}}}',
                     '{"integrations": {"vercel": {"promote_scopes": "demo-team"}}}',
                     '{"integrations": {"vercel": {"value_scopes": [1]}}}']:
            self.company(None, text)
            for command in [f"vercel promote dpl_123 {DEMO}", f"vercel env pull {ACME}", "vercel ls"]:
                with self.subTest(text=text, command=command):
                    self.assertBlocked(command)
            self.assertAllowed("git status")

    # Values of environment variables: agents write them, read the non-production ones, and never read production's.

    def test_env_writes_run(self):
        for command in [
            "vercel env add DB_PASS production --scope acme-team",
            "vercel env add API_URL Production -S acme-team",
            "printf '%s' \"$V\" | vercel env add API_URL production --scope acme-team",
            "vercel env rm API_URL production --scope acme-team --yes",
            "vercel env update API_URL production --value x --scope acme-team --yes",
            "vercel env add APP_ENV preview --git-branch main --type config --project acme-app --scope acme-team --yes",
            f"vercel env add API_URL production {DEMO}",
            "vercel env rm API_URL --yes",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_non_production_reads_run(self):
        for command in [
            "vercel env pull",
            "vercel pull",
            "vercel env run -- printenv",
            f"vercel env pull {DEMO}",
            "vercel env pull --scope acme-team",
            "vercel env pull .env.preview.local --environment preview --git-branch main --scope acme-team --yes",
            "vercel env pull --environment=development --scope acme-team",
            "vercel pull --scope acme-team",
            "vercel pull --yes --environment preview --scope acme-team",
            "vercel env run --scope acme-team -- bun test",
            "vercel env run -e preview --git-branch main --scope acme-team -- printenv APP_ENV",
            "nonprod=1 vercel env pull --scope acme-team",  # `prod` inside a word
            "vercel env pull --environment 'preview' --scope acme-team",
            "vercel env ls --scope acme-team",
            "vercel env add --help 2>&1 | sed -n 1,70p",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_value_scopes_limits_the_reads_to_its_teams(self):
        self.company({**SETTINGS, "value_scopes": ["Acme-Team"]})
        self.assertAllowed("vercel env pull --scope acme-team")
        self.assertBlocked("vercel env pull --environment production --scope acme-team")
        for command in ["vercel env pull", "vercel pull", "vercel env run -- printenv", f"vercel env pull {DEMO}",
                        f"vercel pull --environment preview {DEMO}", f"vercel env run {DEMO} -- bun test",
                        "vercel env pull --environment $(cat f) --scope acme-team"]:  # `$(` ends the words the hook reads
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_reads_that_could_name_production_are_refused(self):
        for read in ["vercel env pull", "vercel pull", "vercel env run -- printenv"]:
            for fragment in [
                "--environment production",
                "--environment=production",
                "--environment PRODUCTION",
                "--environment=prod",
                "-e production",
                "-eproduction",
                "-e\"prod\"",
                "--prod",
                "--git-branch production",
                "--environment pro\"\"duction",
                "--environment pro''duction",
                "--environment pro\\duction",
                "--environment pr\\\nod",
                "--environment '$V'",
                "--environment \"$V\"",
                "--environment $(cat f)",
                "--environment `cat f`",
                "--environment pro*",
                "--environment pr?d",
                "--environment pr[o]d",
                "--environment pro{d,}",
                "{--environment=x,--yes}",
                "--environment pro(d)uction",
            ]:
                command = f"{read.replace(' -- printenv', '')} {fragment} --scope acme-team"
                command += " -- printenv" if "run" in read else ""
                with self.subTest(command=command):
                    self.assertBlocked(command)
        for command in [
            "vercel env pull --id dpl_123 --scope acme-team",
            "vercel env pull --id=dpl_123 --scope acme-team",
            "vercel env pull --scope acme-team -- --environment=production",
            "vercel pull --scope acme-team .env.production",
            "vercel env run --scope acme-team -- bun run prod-check",
            "vercel env pull --scope acme-team 'x' \\; --environment production",
            "vercel env pull --scope acme-team >(cat) --yes --environment preview",
            "vercel env pull --scope acme-team x(N) --environment preview",
            "vercel env pull --scope acme-team && echo production",  # the whole text counts
            "vercel env pull --scope acme-team; echo $?",
            "npx vercel env pull --environment production --scope acme-team",
            "VERCEL_PROJECT_ID=y vercel pull --prod --scope acme-team",
            "sudo vercel env pull --environment production --scope acme-team",
            "sh -c 'vercel env pull --environment production --scope acme-team'",
            "eval vercel pull --prod --scope acme-team",
            "bash -c \"vercel env pull --environment=pro''duction --scope acme-team\"",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_env_run_never_runs_vercel(self):
        for command in [
            "vercel env run --scope acme-team -- vercel deploy",
            "vercel env run --scope acme-team -- npx vercel ls",
            "vercel env run --scope acme-team -- /x/bin/vc alias set a b",
            "vercel env run --scope acme-team -- sh -c 'vercel redeploy dpl_123'",
            "vercel env run --scope acme-team -- sh -c 'v\"er\"cel link'",
            "vercel env run --scope acme-team -- VERCEL deploy",  # some file systems find it in any case
            # The call's args don't hold what feeds a shell, so the rule reads the text.
            "vercel env run --scope acme-team -- sh <<'EOF'\nvercel deploy\nEOF",
            "cat <<'EOF' | vercel env run --scope acme-team -- sh\nvercel deploy\nEOF",
            "vercel env run --scope acme-team -- sh <<< 'v\"er\"cel deploy' > /tmp/x",
            "echo vercel deploy | vercel env run --scope acme-team -- sh",
            "vercel env ls --scope acme-team && vercel env run --scope acme-team -- bun test",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)
        self.assertAllowed("VERCEL_ENV=preview vercel env run --scope acme-team -- bun test")

    def test_value_dumps_are_refused(self):
        for command in [
            "vercel env ls --json --scope acme-team",
            "vercel env ls --format=json --scope acme-team",
            "vercel env ls -F json --scope acme-team",
            "vercel env list --json",
            "vercel env --format json ls --scope acme-team",
            "vercel --json env ls --scope acme-team",
            "vercel env $S --json --scope acme-team",  # a subcommand it can't name counts as a list
            "vercel api /v10/projects/acme-app/env --scope acme-team",
            "vercel api \"/v9/projects/acme-app/env\" --scope acme-team | jq '.envs[].key'",
            "vercel api /v3/env --scope acme-team",
            "vercel api '/v1/projects/prj_1/env/env_1?decrypt=true' --scope acme-team",
            "vercel api -X GET /v10/projects/acme-app/env",
            "VERCEL_ORG_ID=x npx vercel api /v10/projects/acme-app/env",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)
        for command in [
            "vercel env ls production --scope acme-team",
            "vercel env ls preview",
            "vercel env add X preview --format json --scope acme-team",  # the flag is a list's alone
            "vercel env run -e preview --scope acme-team -- grep -F x .env",
            "vercel env run -e preview --scope acme-team -- bun test --json",
            "vercel api /v9/projects/acme-app --scope acme-team",
            "vercel api /v2/teams/acme-team --scope acme-team",
            "vercel api /v9/projects/acme-app/custom-environments --scope acme-team",
            "vercel api '/v6/deployments?projectId=prj_1&since=1' --scope acme-team",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_a_failure_in_the_check_refuses(self):
        deep = 'vercel ls "' + '$(echo "' * 1500 + "x" + '")' * 1500 + '"'
        result = self.run_hook(deep)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("couldn't check the command", result.stderr)

    # However vercel is started.

    def test_wrappers_and_chains_are_seen_through(self):
        for command in [
            "npx vercel deploy",
            "npx --yes vercel@62.1.0 --prod",
            "bunx vercel deploy",
            "pnpm dlx vercel deploy",
            "vc deploy",
            "/home/me/.bun/bin/vercel deploy",
            "VERCEL_ORG_ID=x VERCEL_PROJECT_ID=y vercel deploy",
            "env FOO=1 vercel --prod",
            "cd apps/web && vercel deploy",
            "vercel ls --scope acme-team; vercel --prod",
            "git status\nvercel deploy",
            "bash -c 'vercel deploy --prod'",
            "echo $(vercel deploy)",
            "time vercel deploy",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_substitutions_in_double_quotes_and_heredocs_are_checked(self):
        for command in [
            'echo "$(vercel deploy)"',
            'echo "deployed: `vercel --prod`"',
            'url="$(npx vercel deploy --prod)"',
            'echo "$(echo "$(vercel deploy)")"',
            'git commit -m "release $(vercel deploy)" && git log --oneline -1',
            "cat <<EOF\n'$(vercel deploy)'\nEOF",
            'cat <<EOF\n"`vercel --prod`"\nEOF',
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)
        self.assertBlocked('cd workspaces/acme/acme-app && echo "$(vercel env pull)"')
        for command in [
            'echo "$(git rev-parse HEAD): vercel deploy is refused"',
            "echo '$(vercel deploy)'",
            "cat <<'EOF'\n\"$(vercel deploy)\"\nEOF",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    # A redirection's file descriptor isn't an argument.

    def test_redirections_are_not_arguments(self):
        for command in [
            "vercel --version 2>&1 | tail -1",
            "vercel env add --help 2>&1 | grep -i sensitive",
            "vercel whoami 2>/dev/null",
            "vercel ls --scope acme-team 2>&1 | head -5",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)
        for command in [
            "vercel deploy 2>&1 | tail -1",
            "vercel 2>&1",
            "vercel --prod 2>/dev/null",
            "vercel 2 > out.txt",
            "vercel promote dpl_123 2>&1 --scope acme-team",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    # What the runbooks allow still runs.

    def test_runbook_reads_and_rollbacks_are_allowed(self):
        for command in [
            "vercel ls acme-app --scope acme-team",
            f"vercel ls demo {DEMO} | head -8",
            "vercel inspect https://acme-app-abc.vercel.app --scope acme-team",
            "vercel env ls --scope acme-team",
            "vercel env add CRON_SECRET preview --git-branch main --sensitive --project acme-app --scope acme-team --yes",
            "vercel api /v9/projects/acme-app --scope acme-team",
            "vercel project ls --scope acme-team",
            f"vercel rollback dpl_123 {DEMO} --yes",
            f"vercel rollback status demo {DEMO}",
            "vercel alias ls --scope acme-team",
            "vercel build --prod",
            "vercel --version",
            "vercel whoami",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_mentions_that_dont_run_vercel_are_allowed(self):
        for command in [
            'grep -rn "vercel deploy" knowledge/',
            "rg vercel apps/web",
            'git commit -m "no vercel deploy"',
            "echo vercel deploy",
            "cat vercel.json",
            "git commit -m 'kb: `vercel` is blocked for agents\n\nvercel deploy stays refused'",
            "python3 -c 'print(\"(vercel deploy)\")'",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    # Text the shell never runs: the body of a heredoc with a quoted delimiter, and comments.

    def test_text_in_quoted_heredocs_and_comments_is_allowed(self):
        for command in [
            "python3 - <<'EOF'\nimport pathlib\nq = 'I don\\'t know its name yet'\n"
            "p = pathlib.Path('knowledge/board/directives/D-1.md')\n"
            "s = p.read_text()\ns = s.replace(old, \"| Owner | its name isn't known yet |\")\n"
            "s = s.replace(old, old + \"| Task 1 done. Not read back (`vercel` is blocked for agents). "
            "Read it back with `vercel env ls` |\\n\")\np.write_text(s)\nEOF\n"
            "python3 scripts/kb_lint.py | tail -1 && git commit -q -m \"kb(D-1): done\" && git log --oneline -1",
            "cat > notes.md <<\"EOF\"\n- `vercel deploy --prod` is refused\nvercel promote dpl_123\nEOF",
            "cat > notes.md <<\\EOF\nIt doesn't run (vercel deploy).\nEOF\ngit status",
            "cat <<-'EOF' | tee notes.md\n\tvercel --prod\n\tEOF",
            "cat <<'A' <<'B'\nvercel deploy\nA\n$(vercel deploy)\nB",
            "# vercel deploy is refused\ngit status",
            "git status  # not vercel deploy",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_commands_around_heredocs_and_comments_are_still_checked(self):
        for command in [
            "cat <<'EOF' > notes.md\ntext\nEOF\nvercel deploy",
            "cat <<'EOF' > notes.md && vercel deploy\ntext\nEOF",
            "cat <<EOF\n$(vercel deploy)\nEOF",
            "cat <<EOF\n`vercel --prod`\nEOF",
            "cat <<A <<'B'\n$(vercel deploy)\nA\ntext\nB",
            "echo \"<<'EOF'\"\nvercel deploy\nEOF",
            "echo ok # <<'EOF'\nvercel deploy\nEOF",
            "cat <<<'EOF'\nvercel deploy\nEOF",
            "echo ok # note\nvercel deploy",
            "echo ${#x}; vercel deploy",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    # A quoted heredoc's body is commands when a shell runs it: fed to a shell, piped into one, or used by eval,
    # source or `.`, also through a substitution.

    def test_quoted_heredocs_a_shell_runs_are_checked(self):
        for command in [
            "bash <<'EOF'\nvercel deploy\nEOF",
            "sh <<'EOF'\nvercel --prod\nEOF",
            "zsh -s <<\"EOF\"\nvercel deploy\nEOF",
            "/bin/dash <<\\EOF\nvercel deploy\nEOF",
            "ksh <<-'EOF'\n\tvercel deploy\n\tEOF",
            "/usr/bin/env bash <<'EOF'\nvercel deploy\nEOF",
            "env FOO=1 bash -s -- arg <<'EOF'\nvercel deploy\nEOF",
            "sudo bash <<'EOF'\nvercel deploy\nEOF",
            "sudo -u root bash <<'EOF'\nvercel deploy\nEOF",
            "bash <<'EOF'\n# a comment\necho start\nvercel deploy --prod\nEOF",
            "cat <<'EOF' | bash\nvercel deploy\nEOF",
            "cat <<'EOF' | sed 's/x/y/' | sudo sh -s\nvercel deploy\nEOF",
            "cat <<'EOF' |\nvercel deploy\nEOF\nbash",
            "eval \"$(cat <<'EOF'\nvercel deploy\nEOF\n)\"",
            "eval $(cat <<'EOF'\nvercel deploy\nEOF\n)",
            "source /dev/stdin <<'EOF'\nvercel deploy\nEOF",
            ". /dev/stdin <<'EOF'\nvercel deploy\nEOF",
            "source <(cat <<'EOF'\nvercel deploy\nEOF\n)",
            "bash -c \"$(cat <<'EOF'\nvercel deploy\nEOF\n)\"",
            "echo \"$(cat <<'EOF'\nvercel deploy\nEOF\n)\" | bash",
            "sudo bash -c 'vercel deploy'",
            "dash -c 'vercel deploy'",
            "eval 'vercel deploy'",
            "eval vercel --prod",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)
        self.assertBlocked("cd workspaces/acme/acme-app && bash <<'EOF'\nvercel pull --prod\nEOF")

    def test_quoted_heredocs_other_programs_read_are_text(self):
        for command in [
            "cat <<'EOF' | tee notes.md\nvercel deploy\nEOF",
            "python3 - <<'EOF'\nimport subprocess  # vercel deploy\nEOF",
            "node <<'EOF'\nconsole.log('vercel deploy')\nEOF",
            "git commit -q -F - <<'EOF'\nvercel deploy is refused\nEOF",
            "gh pr create --title t --body \"$(cat <<'EOF'\n- `vercel deploy` is refused\nEOF\n)\"",
            "git commit -m \"$(cat <<'EOF'\nvercel --prod stays refused\nEOF\n)\"",
            "cat <<'EOF' > run.sh\nvercel deploy\nEOF\nbash scripts/check.sh",
            "cat <<'EOF' | grep -c bash\nvercel deploy\nEOF",
            "bash <<'EOF'\ncat <<'X' > notes.md\nvercel deploy\nX\nEOF",
            "bash <<'EOF'\necho 'vercel deploy is refused'\nEOF",
            "cat >> notes.md <<EOF <<'X'\n| Order 1 | $T (CTO). Staff D4 ended |\nEOF\n`vercel deploy` is refused\nX",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    # Only agent sessions are limited.

    def test_every_agent_is_limited(self):
        for agent in ["ceo", "cto", "staff-engineer", "senior-engineer", "general-purpose"]:
            with self.subTest(agent=agent):
                self.assertBlocked("vercel deploy --prod", agent_type=agent)

    def test_plain_session_is_not_limited(self):
        self.assertAllowed("vercel deploy --prod", agent_type=None)

    def test_other_tools_are_ignored(self):
        self.assertAllowed("vercel deploy", tool_name="Read")

    def test_what_it_cant_read_is_refused(self):
        for text in ("not json", "[]", '{"tool_name": "Bash", "agent_type": "cto", "tool_input": [1]}'):
            with self.subTest(text=text):
                result = subprocess.run([sys.executable, str(HOOK)], input=text, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 2)
                self.assertIn("couldn't check", result.stderr)


if __name__ == "__main__":
    unittest.main()
