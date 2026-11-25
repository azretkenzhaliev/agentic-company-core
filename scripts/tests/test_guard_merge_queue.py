"""Tests for scripts/hooks/guard_merge_queue.py: no agent or session takes a PR out of a merge queue, or cancels a
workflow run. Every form is checked on queue_reason, and the wiring end to end through guard_marketing_tools.py, as Claude
Code runs it: JSON on stdin, exit 2 plus stderr to block.

Re-runs and rerequests run. The forms the whole-text checks match (a mutation's name then `(input`, a run's cancel path under `repos/`, gh,
run and cancel as quoted list items) are built from pieces (D, RUNS, GH), so this file's text holds none of them: a
review packet of it sent inline on stdin isn't refused (test_own_text_passes_the_text_checks)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
GUARD = HOOKS / "guard_marketing_tools.py"
sys.path.insert(0, str(HOOKS))
import guard_merge_queue  # noqa: E402
from guard_merge_queue import INSTEAD, queue_reason  # noqa: E402

D = "dequeue" + "PullRequest"
OFF = "disable" + "PullRequestAutoMerge"
RQ = "rerequest" + "CheckSuite"
RUNS = "actions/" + "runs"
JOBS = "actions/" + "jobs"
GH = "'gh'"
REPO = "repos/Example-Co/acme-app"
DEQUEUE = f"mutation {{ {D}(input: {{id: \"PR_kwDOx\"}}) {{ clientMutationId }} }}"
ORDINARY = '{repository(owner:"Acme",name:"acme-app"){pullRequest(number:18){mergeQueueEntry{position state}}}}'
WITH_VARIABLES = 'query($n:Int!){repository(owner:"Acme",name:"acme-app"){pullRequest(number:$n){state}}}'

REFUSED = [
    # gh run cancel, in any form
    "gh run cancel 1001 --repo Example-Co/acme-app",
    "gh run cancel --force 1001",
    "gh run -R Example-Co/acme-app cancel 1",
    "gh run --repo=Example-Co/acme-app cancel 1",
    "/usr/local/bin/gh run cancel 1",
    "GH_REPO=Example-Co/acme-app gh run cancel 1",
    "env GH_PROMPT_DISABLED=1 gh run cancel 1",
    "command gh run cancel 1 --force",
    "sudo gh run cancel 1",
    "timeout 10 gh run cancel 1",
    "nohup gh run cancel 1 &",
    "xargs -n1 gh run cancel < ids.txt",
    "find . -name x -exec gh run cancel {} \\;",
    "g\"\"h run cancel 1",
    "g\\h run cancel 1",
    "$'gh' run cancel 1",
    "$'\\x67h' run cancel 1",
    "=gh run cancel 1",
    "G=gh; $G run cancel 1",
    "$(which gh) run cancel 1",
    "true && gh run cancel 1",
    "true\ngh run cancel 1",
    "ls | gh run cancel 1",
    "(gh run cancel 1)",
    "{ gh run cancel 1; }",
    "x=$(gh run cancel 1)",
    "echo \"$(gh run cancel 1)\"",
    "echo `gh run cancel 1`",
    "cat <(gh run cancel 1)",
    "echo ${x:-$(gh run cancel 1)}",
    "bash -c 'gh run cancel 1'",
    "zsh -lc \"gh run cancel 1\"",
    "bash -o pipefail -c 'gh run cancel 1'",
    "sh -c 'sh -c \"gh run cancel 1\"'",
    "eval gh run cancel 1",
    "eval \"gh run cancel 1 --force\"",
    "bash <<'EOF'\ngh run cancel 1\nEOF",
    "bash -s <<EOF\ngh run cancel 1\nEOF",
    "bash <<< 'gh run cancel 1'",
    "echo 'gh run cancel 1' | bash",
    "printf 'gh run cancel 1\\n' | sh",
    f"python3 -c \"import subprocess; subprocess.run([{GH}, 'run', 'cancel', '1'])\"",
    f"node -e \"require('child_process').execFileSync({GH}, ['run', 'cancel', '1'])\"",
    # gh pr merge --disable-auto
    "gh pr merge 18 --disable-auto",
    "gh pr merge --disable-auto 18 --repo Example-Co/acme-app",
    "gh pr -R Example-Co/acme-app merge 18 --disable-auto",
    "gh pr merge 18 --disable-auto=true",
    # gh pr close, when the command says it's to leave the queue
    "gh pr close 18 --comment 'Taking it out of the merge queue'",
    "gh pr close 18 -c \"dequeue for now\"",
    "gh pr close 16 --repo Example-Co/acme-app  # out of the queue",
    "gh pr close 18 && echo 'it left the queue'",
    # GraphQL: the mutations, by name, in any quoting
    f"gh api graphql -f query='{DEQUEUE}'",
    f"gh api graphql -f query='mutation($id:ID!){{{D}(input:{{id:$id}}){{clientMutationId}}}}' -f id=PR_kwDOx",
    f"gh api graphql -f query='mutation {{ {D} }}'",
    f"gh api graphql -f query='mutation {{ deq\"\"ueue{D[7:]}(input: {{id: \"x\"}}) {{ x }} }}'",
    f"gh api graphql -f query='mutation {{ {D.upper()}(input: {{id: \"x\"}}) {{ x }} }}'",
    f"gh api graphql -f query='mutation {{ {OFF}(input: {{pullRequestId: \"x\"}}) {{ x }} }}'",
    f"gh api /graphql -f query='{DEQUEUE}'",
    f"gh api https://api.github.com/graphql -f query='{DEQUEUE}'",
    f"gh api graphql --input - <<'EOF'\n{{\"query\": \"{DEQUEUE.replace(chr(34), chr(92) + chr(34))}\"}}\nEOF",
    f"gh api graphql --input - <<'EOF'\n{{\"query\": \"mutation {{ \\u0064equeue{D[7:]}(input: {{}}) {{ x }} }}\"}}\nEOF",
    f"gh api graphql -F query=@- <<'EOF'\n{DEQUEUE}\nEOF",
    f"Q='{DEQUEUE}'; gh api graphql -f query=\"$Q\"",
    f"python3 - <<'EOF'\nimport urllib.request\nbody = '{{\"query\": \"{DEQUEUE.replace(chr(34), '')}\"}}'\nEOF",
    f"curl -s -H \"Authorization: bearer $(gh auth token)\" -d '{{\"query\":\"{D}\"}}' https://api.github.com/graphql",
    f"wget --post-data='{{\"query\":\"{D}\"}}' https://api.github.com/graphql",
    f"http POST https://api.github.com/graphql query='{D}'",
    # REST: a run's cancel paths
    f"gh api -X POST {REPO}/{RUNS}/1001/cancel",
    f"gh api -X POST repos/{{owner}}/{{repo}}/{RUNS}/1/force-cancel",
    f"gh api -X POST \"{REPO}/{RUNS}/$RUN/cancel\"",
    f"gh api -X POST \"$BASE/{RUNS}/1/cancel\"",
    f"curl -X POST -H \"Authorization: bearer $T\" https://api.github.com/{REPO}/{RUNS}/1/cancel",
    f"python3 -c \"import urllib.request as u; u.urlopen(u.Request('https://api.github.com/{REPO}/{RUNS}/1/cancel'))\"",
    # `$'...'` decoded, a shell running stdin, a gh or API path the shell fills in
    f"gh api graphql -f query=$'mutation {{ \\x64{D[1:]}(input: {{id: \"x\"}}) {{ x }} }}'",
    "bash /dev/stdin <<< 'gh run cancel 1'",
    "source /dev/stdin <<< 'gh run cancel 1'",
    ". /dev/stdin <<'EOF'\ngh run cancel 1\nEOF",
    "echo 'gh run cancel 1' | bash -",
    "$GHBIN run cancel 1",
    "\"$GH\" pr merge 18 --disable-auto",
    f"curl -X POST -H \"Authorization: bearer $T\" \"$API/{RUNS}/1/cancel\"",
    # closing a PR through the API, when the command names a queue
    f"gh api -X PATCH {REPO}/pulls/18 -f state=closed  # leave the queue",
    f"gh api {REPO}/pulls/18 -f state=closed  # out of the queue",
    f"curl -X PATCH -d '{{\"state\":\"closed\"}}' https://api.github.com/{REPO}/pulls/18  # queue",
    f"http --ignore-stdin PATCH https://api.github.com/{REPO}/pulls/18 state=closed  # leave the queue",
    # updatePullRequest closing the PR, the state in the query or in a variable
    "gh api graphql -f query='mutation{updatePullRequest(input:{pullRequestId:\"x\",state:CLOSED}){clientMutationId}}'"
    "  # leave the queue",
    "gh api graphql -f query='mutation($s:PullRequestUpdateState!){updatePullRequest(input:{pullRequestId:\"x\","
    "state:$s}){clientMutationId}}' -f s=CLOSED  # out of the queue",
    "gh api graphql -f query='mutation{closePullRequest(input:{pullRequestId:\"x\"}){clientMutationId}}' # dequeue",
]

CANT_READ = [
    # another file descriptor's redirect isn't the call's stdin
    "{ gh api graphql --input - 3< harmless.txt; } < dq.json",
    "{ gh api graphql --input - 2< harmless.txt; } < dq.json",
    "{ gh api graphql --input - 3<<'EOF'\n{\"query\": \"{viewer{login}}\"}\nEOF\n} < dq.json",
    # stdin the call doesn't carry itself (the Bash tool's own stdin is a read-only character device)
    "(gh api graphql --input -) < dq.json",
    "{ gh api graphql --input -; } < dq.json",
    "cat dq.json | (gh api graphql --input -)",
    "cat dq.json | sh -c 'gh api graphql --input -'",
    "exec < dq.json; gh api graphql --input -",
    "gh api graphql --input -",
    "gh api graphql -F query=@-",
    "gh api graphql -F query=@/dev/stdin",
    "http POST https://api.github.com/graphql",
    "gh run \"$ACTION\" 1",
    "gh api graphql -F query=@missing.graphql",
    "gh api graphql --input missing.json",
    "gh api graphql --input=missing.json",
    "gh api graphql -Fquery=@missing.graphql",
    "gh api graphql --field=query=@missing.graphql",
    "gh api graphql -F query=@\"$F\"",
    "gh api graphql -F query=@<(cat q.graphql)",
    "cat q.json | gh api graphql --input -",
    "jq -n '{query: \"{viewer{login}}\"}' | gh api graphql --input -",
    "gh api graphql -F query=@- < /dev/stdin",
    "gh api graphql --input - <&3",
    "gh api graphql --input - <<EOF\n{\"query\": \"$Q\"}\nEOF",
    "gh api graphql --input - <<< \"$BODY\"",
    "gh api graphql -f query=\"$(cat q.graphql)\"",
    "gh api graphql -f query=\"$Q\"",
    "gh api graphql -f query=`cat q.graphql`",
    "gh api graphql -f \"$K=x\"",
    "gh api -X POST \"$URL\"",
    "gh api \"$URL\" -f x=1",
    "curl -d @missing.json https://api.github.com/graphql",
    "curl --data-binary @- https://api.github.com/graphql < /dev/stdin",
    "echo '{}' | curl --data-binary @- https://api.github.com/graphql",
    "curl -d \"{\\\"query\\\": \\\"$Q\\\"}\" https://api.github.com/graphql",
    "curl -K missing.cfg https://api.github.com/graphql",
    "wget --post-file=missing.json https://api.github.com/graphql",
    "http POST https://api.github.com/graphql @missing.json",
    "http POST https://api.github.com/graphql query=@missing.graphql",
    "echo '{}' | http POST https://api.github.com/graphql",
    "http POST https://api.github.com/graphql query=\"$Q\"",
]

RERUNS = [
    # re-runs and rerequests aren't barred: the runbooks direct them
    "gh run rerun 1002 --job 1003 --repo Example-Co/acme-app",
    "gh run rerun 1004 --failed",
    "gh run -R Example-Co/acme-app rerun 1",
    "echo 'gh run rerun 1' | bash",
    f"node -e \"require('child_process').execFileSync({GH}, ['run', 'rerun', '1'])\"",
    f"gh api --method POST {REPO}/{RUNS}/1/rerun",
    f"gh api {REPO}/{RUNS}/1/rerun-failed-jobs -X POST",
    f"gh api -X POST {REPO}/{JOBS}/1003/rerun",
    f"curl -X POST -H \"Authorization: bearer $T\" https://api.github.com/{REPO}/{RUNS}/1/rerun",
    f"gh api -X POST {REPO}/check-suites/1/rerequest",
    f"gh api -X POST {REPO}/check-runs/1003/rerequest",
    f"gh api graphql -f query='mutation {{ {RQ}(input: {{repositoryId: \"x\", checkSuiteId: \"y\"}}) {{ x }} }}'",
]

ALLOWED = [
    # look-alikes
    "gh pr view 18 --repo Example-Co/acme-app --json state,mergeQueueEntry",
    "gh pr merge 18 --squash",
    "gh pr merge 16 --repo Example-Co/acme-app --merge",
    "gh pr merge 18 --auto --squash",  # refused by settings.json's deny list, not by this hook
    "gh run view 1002 --log-failed --repo Example-Co/acme-app",
    "gh run list --limit 5",
    "gh run watch 1",
    "gh run view 1 --json jobs --jq '.jobs[] | select(.conclusion == \"cancelled\")'",
    f"gh api graphql -f query='{ORDINARY}'",
    f"gh api graphql -f query='{WITH_VARIABLES}' -F n=18",
    f"gh api graphql -f query=\"{WITH_VARIABLES.replace('$', chr(92) + '$')}\" -F n=18",
    f"gh api graphql --input - <<'EOF'\n{{\"query\": \"{ORDINARY.replace(chr(34), chr(92) + chr(34))}\"}}\nEOF",
    f"gh api graphql -F query=@- <<'EOF'\n{WITH_VARIABLES}\nEOF\n",
    f"gh api graphql -F query=@/dev/stdin <<< '{ORDINARY}'",
    "gh api graphql -f query='mutation{enqueuePullRequest(input:{pullRequestId:\"x\"}){clientMutationId}}'",
    "gh api graphql -f query='mutation{updatePullRequest(input:{pullRequestId:\"x\",title:\"Fix the queue reader\"})"
    "{clientMutationId}}'",
    # httpie and xh read stdin as the body only for graphql: other calls need no --ignore-stdin
    "http GET https://api.github.com/rate_limit",
    f"xh https://api.github.com/{REPO}/pulls/18",
    # reads that name a closed state and a queue: only a write closes
    "gh api graphql -f query='{repository(owner:\"Acme\",name:\"acme-app\"){pullRequests(states:CLOSED,"
    "first:5){nodes{number state closed mergeQueueEntry{state}}}}}'",
    f"gh api graphql -f query='{ORDINARY}' --jq '.data | select(.state == \"CLOSED\")'",
    f"gh api '{REPO}/pulls?state=closed' --jq '.[].title' | grep -i queue",
    f"gh api -X GET {REPO}/pulls -f state=closed --jq '.[].title' | grep -i queue",
    f"curl -s -H \"Authorization: bearer $T\" 'https://api.github.com/{REPO}/pulls?state=closed' | grep queue",
    f"gh api {REPO}/commits/abc123/check-runs --jq '.check_runs[].name'",
    "http --ignore-stdin GET https://api.github.com/rate_limit",
    f"gh api {REPO}/{RUNS}/1002",
    f"gh api {REPO}/{RUNS}/1002/jobs --jq '.jobs[].name'",
    f"gh api \"{REPO}/pulls/$PR\"",
    "gh api \"$URL\"",
    f"gh api {REPO}/pulls/18 -X PATCH -f title='Fix the queue reader'",
    "gh pr close 10 --repo Example-Co/acme-app --comment 'Superseded by #11' && git push origin --delete task/x",
    "gh pr close 5 --comment \"Abandoned: the design changed\"",
    "gh pr ready 18",
    "gh auth status",
    "curl -s https://example.com/api -d @missing.json",
    "curl -s -H \"Authorization: bearer $(gh auth token)\" https://api.github.com/rate_limit",
    "curl -s -H \"Authorization: bearer $T\" -d '{\"query\":\"{viewer{login}}\"}' https://api.github.com/graphql",
    # text that names the barred calls but runs none of them
    "grep -rn 'gh run cancel' knowledge/engineering/",
    f"grep -rn {D} knowledge/",
    f"git commit -m \"sys: no gh run cancel, no {D}\"",
    "git commit -m \"$(cat <<'EOF'\nsys: refuse gh run cancel\n1) don't take a PR out of the queue\ngh pr close 18 # queue\nEOF\n)\"",
    f"cat >> notes.md <<'EOF'\ngh run cancel 1\ngh api graphql -f query='{D}'\nEOF",
    "cat >> notes.md <<EOF\ngh run rerun 1 is barred\nEOF",
    "printf '%s\\n' \"never gh run cancel\" >> notes.md",
    "echo \"gh pr merge --disable-auto is barred\" >> notes.md",
    f"python3 - <<'EOF'\nprint('took a PR out of the queue with GraphQL {D}')\nEOF",
    f"python3 scripts/second_opinion.py --file /dev/stdin <<'EOF'\ngh run cancel 1\n{D} is barred\nEOF",
    "brew upgrade gh",
    "command -v gh",
    "ls -la",
]


class QueueReason(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.path.realpath(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = Path(self.cwd) / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def assertRefused(self, command):
        reason = queue_reason(command, self.cwd)
        self.assertIsNotNone(reason, command)
        self.assertIn(INSTEAD, reason, command)
        self.assertNotIn("can't read", reason, command)

    def assertCantRead(self, command):
        reason = queue_reason(command, self.cwd)
        self.assertIsNotNone(reason, command)
        self.assertIn("can't read", reason, command)
        self.assertIn(INSTEAD, reason, command)

    def assertAllowed(self, command):
        self.assertIsNone(queue_reason(command, self.cwd), command)

    def test_barred_forms_are_refused(self):
        for command in REFUSED:
            with self.subTest(command=command):
                self.assertRefused(command)

    def test_what_it_cant_read_is_refused(self):
        for command in CANT_READ:
            with self.subTest(command=command):
                self.assertCantRead(command)

    def test_reruns_run(self):
        for command in RERUNS:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_look_alikes_and_text_run(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_the_message_names_the_bar_and_what_to_do_instead(self):
        reason = queue_reason("gh run cancel 1", self.cwd)
        self.assertIn("docs/guards.md", reason)
        self.assertTrue(reason.endswith(
            "a queued PR stays in the queue; tell your manager (a NEEDS-CEO-NOW line for a CTO); a refusal is final."))

    # Files: a query or body the call would send is read; it's refused if it names a barred call or can't be read.

    def test_a_file_that_names_the_mutation_is_refused(self):
        self.write("dq.graphql", DEQUEUE)
        self.write("body.json", json.dumps({"query": DEQUEUE}))
        self.write("escaped.json", json.dumps({"query": DEQUEUE}, ensure_ascii=False).replace("d", "\\u0064", 1))
        self.write("rest.cfg", f"url = \"https://api.github.com/{REPO}/{RUNS}/1/cancel\"\n")
        for command in ["gh api graphql -F query=@dq.graphql", "gh api graphql --input body.json",
                        "gh api 'graphql?x=1' -F query=@dq.graphql", "gh api /graphql/ --input body.json",
                        "gh api graphql --input escaped.json", "gh api graphql -F query=@- < dq.graphql",
                        f"gh api graphql -F query=@{self.cwd}/dq.graphql",
                        "curl -d @body.json https://api.github.com/graphql",
                        "curl -K rest.cfg -H 'Accept: application/vnd.github+json'  # github",
                        "wget --post-file=body.json https://api.github.com/graphql",
                        "http POST https://api.github.com/graphql @body.json",
                        "http POST https://api.github.com/graphql query=@dq.graphql",
                        "http POST https://api.github.com/graphql < body.json"]:
            with self.subTest(command=command):
                self.assertRefused(command)

    def test_an_ordinary_file_runs(self):
        self.write("q.graphql", WITH_VARIABLES)
        self.write("body.json", json.dumps({"query": ORDINARY}))
        for command in ["gh api graphql -F query=@q.graphql -F n=18", "gh api graphql --input body.json",
                        "gh api graphql -F query=@- < q.graphql -F n=18",
                        "gh api graphql --input - 0< body.json", f"cd /tmp && gh api graphql --input "
                        f"{self.cwd}/body.json", "curl -d @body.json https://api.github.com/graphql",
                        "http POST https://api.github.com/graphql < body.json"]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_a_file_it_cant_be_sure_of_is_refused(self):
        self.write("q.graphql", ORDINARY)
        os.mkfifo(os.path.join(self.cwd, "fifo"))
        os.mkdir(os.path.join(self.cwd, "folder"))
        big = os.path.join(self.cwd, "big.json")
        with open(big, "wb") as handle:
            handle.truncate(guard_merge_queue.MAX_FILE + 1)
        for command in ["cd sub && gh api graphql -F query=@q.graphql",  # relative after a cd: which q.graphql?
                        "pushd /tmp; gh api graphql -F query=@q.graphql",
                        "cp /tmp/x q.graphql && gh api graphql -F query=@q.graphql",  # named again: written first?
                        "gh api graphql -F query=@q.graphql > q.graphql.log; cat q.graphql",
                        "gh api graphql -F query=@fifo", "gh api graphql --input folder",
                        "gh api graphql --input big.json"]:
            with self.subTest(command=command):
                self.assertCantRead(command)

    def test_own_text_passes_the_text_checks(self):
        for path in (Path(__file__), HOOKS / "guard_merge_queue.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIsNone(guard_merge_queue.text_reason(guard_merge_queue.flatten(text)))
                self.assertIsNone(guard_merge_queue.text_reason(text))
                self.assertAllowed(f"python3 scripts/second_opinion.py --file /dev/stdin <<'EOF'\n{text}\nEOF")

    # Crashes and size: a command it can't read is refused only when it names gh, github, graphql or the rest.

    def test_a_reading_failure_refuses_only_a_command_that_may_reach_github(self):
        with mock.patch.object(guard_merge_queue, "command_reason", side_effect=ValueError("broken")):
            self.assertCantRead("gh pr view 1")
            self.assertCantRead("curl https://api.github.com/graphql")
            self.assertIsNone(queue_reason("ls -la", self.cwd))
            self.assertIsNone(queue_reason("git status", self.cwd))

    def test_nesting_past_the_limit_is_refused(self):
        self.assertCantRead("echo " + "$(" * 20 + "gh run view 1" + ")" * 20)

    def test_a_long_command_is_read_in_time(self):
        command = "echo github " + "x " * 120_000 + "&& gh run view 1"
        start = time.monotonic()
        self.assertAllowed(command)
        self.assertLess(time.monotonic() - start, 10)


class Wiring(unittest.TestCase):
    """End to end through guard_marketing_tools.py, for every caller: a subagent, the main session (an agent_type
    without agent_id) and a session without agent_type."""

    def run_guard(self, command, agent_type=None, agent_id=None, guard=GUARD, tool_name="Bash"):
        payload = {"session_id": "test", "cwd": "/tmp", "hook_event_name": "PreToolUse", "tool_name": tool_name,
                   "tool_input": {"command": command}}
        if agent_type:
            payload["agent_type"] = agent_type
        if agent_id:
            payload["agent_id"] = agent_id
        return subprocess.run([sys.executable, str(guard)], input=json.dumps(payload), capture_output=True, text=True,
                              timeout=30)

    CALLERS = [("cto", "a1b2c3d4"), ("staff-engineer", "a5e6f7"), ("ceo", None), (None, None), ("cmo", "a9")]

    def test_every_caller_is_refused(self):
        for agent_type, agent_id in self.CALLERS:
            for command in ["gh run cancel 1 --repo Example-Co/acme-app", f"gh api graphql -f query='{DEQUEUE}'"]:
                with self.subTest(agent_type=agent_type, command=command):
                    result = self.run_guard(command, agent_type, agent_id)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(INSTEAD, result.stderr)

    def test_a_look_alike_runs_for_every_engineering_caller(self):
        for agent_type, agent_id in self.CALLERS[:4]:
            with self.subTest(agent_type=agent_type):
                result = self.run_guard("gh pr view 18 --repo Example-Co/acme-app", agent_type, agent_id)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_broken_module_blocks_bash_for_every_caller_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            hooks = Path(tmp) / "hooks"
            shutil.copytree(HOOKS, hooks, ignore=shutil.ignore_patterns("__pycache__"))
            (hooks / "guard_merge_queue.py").write_text("raise RuntimeError('broken')\n", encoding="utf-8")
            for agent_type, agent_id in self.CALLERS[:4]:
                with self.subTest(agent_type=agent_type):
                    result = self.run_guard("ls", agent_type, agent_id, guard=hooks / GUARD.name)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("guard_merge_queue.py", result.stderr)
            result = self.run_guard("", "ceo", None, guard=hooks / GUARD.name, tool_name="mcp__claude-in-chrome__x")
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
