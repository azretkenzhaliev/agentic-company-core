"""Tests for scripts/second_opinion.py (reviewers from other model families).

Providers are injected, or urllib's urlopen is replaced, so no test reaches any provider.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import second_opinion  # noqa: E402
from second_opinion import Provider, Reply, choose_gemini, choose_openai  # noqa: E402

FAKE_KEY_BLOCK = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow\n"
REAL_WORKSPACES = second_opinion.WORKSPACES  # read before any test patches it
NAMED = {"products": {"acme": {}, "demo": {}}, "integrations": {"second_opinion": {"providers": ["openai", "google"]}}}


class FakeApi:
    """Stands in for one provider's model list and generate call."""

    def __init__(self, models=("model-a",), reply="VERDICT: APPROVED\nFindings: none", error=None, list_error=None,
                 capped=False, cached=None):
        self.models, self.reply, self.error, self.list_error = list(models), reply, error, list_error
        self.capped, self.cached = capped, cached
        self.sent, self.listed = [], 0
        self.errors = []  # per send, taken first: an exception to raise, or None to answer

    def list_models(self, api_key):
        self.listed += 1
        if self.list_error:
            raise self.list_error
        return self.models

    def send(self, packet, instruction, model, api_key, *tier):
        self.sent.append({"packet": packet, "instruction": instruction, "model": model, "api_key": api_key,
                          "tier": tier})  # () when no tier was passed
        error = self.errors.pop(0) if self.errors else self.error
        if error:
            raise error
        return Reply(self.reply, in_tokens=1200, out_tokens=900, thinking_tokens=700, capped=self.capped,
                     cached_tokens=self.cached, service_tier=tier[0] if tier else None)


def provider(label, key_env, model_env, api, kinds=("design", "code", "plan"), tier_env=None):
    return Provider(label, key_env, model_env, api.list_models, api.send, lambda ids: ids[0] if ids else None, kinds,
                    tier_env)


class SecondOpinion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.google = FakeApi(models=["g-model"], reply="VERDICT: APPROVED\nFindings: none")
        self.openai = FakeApi(models=["o-model"], reply="VERDICT: CHANGES_REQUESTED\nFindings:\n1. [major] a.ts:3: x -> y")
        self.workspaces = self.dir / "workspaces"  # never the real logs
        self.company = NAMED  # what company.json says, or the error reading it raises
        for target, name, value in [(second_opinion, "WORKSPACES", self.workspaces),
                                    (second_opinion.company_config, "load", self.load)]:
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.log = self.workspaces / "second-opinions" / "content" / "sa003-calls.jsonl"  # where no --product logs

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, root=None):
        if isinstance(self.company, Exception):
            raise self.company
        return {**second_opinion.company_config.DEFAULTS, **self.company}

    def logged(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def providers(self):
        return [  # the real slots' kinds: Gemini gets plans only
            provider("Google", "GEMINI_API_KEY", "SECOND_OPINION_GEMINI_MODEL", self.google, kinds=("plan",)),
            provider("OpenAI", "OPENAI_API_KEY", "SECOND_OPINION_OPENAI_MODEL", self.openai,
                     tier_env=second_opinion.OPENAI_TIER_ENV),
        ]

    def run_main(self, args, keys=("GEMINI_API_KEY", "OPENAI_API_KEY"), extra_env=None, providers="fake"):
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and not k.startswith("SECOND_OPINION")}
        env.update({k: f"key-for-{k}" for k in keys})
        env.update(extra_env or {})
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(out):
            code = second_opinion.main(args, providers=self.providers() if providers == "fake" else providers)
        return code, out.getvalue()

    def file(self, name, content):
        path = self.dir / name
        path.write_text(content)
        return str(path)

    # Which providers run

    def test_off_until_company_json_names_a_provider(self):
        """Keys alone send nothing, with the real providers too: company.json must name them (SA-003)."""
        for company in [{}, {"integrations": {}}, {"integrations": {"second_opinion": None}}]:
            for kind in ["design", "code", "plan"]:
                for fake in ["fake", None]:
                    with self.subTest(company=company, kind=kind, fake=fake):
                        self.company, urls = company, []
                        with self.urlopen(urls):
                            code, out = self.run_main(["--kind", kind, "--brief", "T-1"], providers=fake)
                        self.assertEqual(code, 0)
                        self.assertTrue(out.startswith("SECOND OPINION: OFF (in force once the founder sets a key and "
                                                       "names the provider in company.json"), out)
                        self.assertEqual((urls, self.google.listed, self.openai.listed), ([], 0, 0))
        self.assertEqual(self.logged(), [])

    def test_help_prints_the_usage_while_off(self):
        self.company, out = {}, io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            second_opinion.main(["--help"])
        self.assertTrue(out.getvalue().startswith("usage:"), out.getvalue())

    def test_only_the_providers_the_founder_named_run(self):
        for named, sent in [(["openai"], ["OpenAI"]), (["google"], ["Google"]), ([], [])]:
            with self.subTest(named=named):
                self.log.unlink(missing_ok=True)
                self.company = {"integrations": {"second_opinion": {"providers": named}}}
                code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
                self.assertEqual(code, 0)
                self.assertEqual([call["provider"] for call in self.logged()], sent)
                if not sent:
                    self.assertTrue(out.startswith("SECOND OPINION: OFF (no provider company.json names"), out)

    def test_a_company_json_that_cant_be_read_sends_nothing(self):
        for company in [ValueError("Expecting value"), OSError("no access"), {"integrations": []},
                        {"integrations": {"second_opinion": True}}, {"integrations": {"second_opinion": {}}},
                        {"integrations": {"second_opinion": {"providers": "openai"}}}, {**NAMED, "products": None}]:
            with self.subTest(company=company):
                self.company, urls = company, []
                with self.urlopen(urls):
                    code, out = self.run_main(["--kind", "plan", "--brief", "T-1"], providers=None)
                self.assertEqual(code, 0)
                self.assertTrue(out.startswith("SECOND OPINION: NOT SENT (company.json can't be read"), out)
                self.assertEqual(urls, [])
        self.assertEqual(self.logged(), [])

    def test_off_without_any_key(self):
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"], keys=())
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("SECOND OPINION: OFF"), out)
        self.assertEqual(self.google.sent + self.openai.sent, [])

    def test_code_and_design_go_to_gpt_alone(self):
        path = self.file("timer.ts", "export const limit = 100;\n")
        for kind in ["design", "code"]:
            with self.subTest(kind=kind):
                self.google.sent, self.openai.sent = [], []
                code, out = self.run_main(["--kind", kind, "--brief", "DD-001 WS-1: order timer", "--file", path])
                self.assertEqual(code, 0)
                self.assertNotIn("Google", out)
                self.assertIn("SECOND OPINION (OpenAI o-model", out)
                self.assertIn("[major] a.ts:3", out)
                self.assertEqual((self.google.listed, self.google.sent), (0, []))
                packet = self.openai.sent[0]["packet"]
                self.assertIn("DD-001 WS-1: order timer", packet)
                self.assertIn("export const limit = 100;", packet)
                self.assertIn("Review checklists", packet)  # the company's rubric travels with the packet
        self.assertEqual([call["provider"] for call in self.logged()], ["OpenAI", "OpenAI"])

    def test_both_families_check_the_same_plan(self):
        path = self.file("packet.md", "Goal: fewer late orders.\n")
        code, out = self.run_main(["--kind", "plan", "--brief", "D-20260101-x", "--file", path])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION (Google g-model", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)
        packet = self.google.sent[0]["packet"]
        self.assertEqual(packet, self.openai.sent[0]["packet"])
        self.assertIn("Goal: fewer late orders.", packet)
        self.assertEqual(self.google.sent[0]["api_key"], "key-for-GEMINI_API_KEY")

    def test_missing_key_reports_that_provider_off(self):
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"], keys=("OPENAI_API_KEY",))
        self.assertIn("SECOND OPINION (Google): OFF", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)
        self.assertEqual(self.google.sent, [])

    def test_gemini_failure_leaves_gpt_the_only_other_opinion(self):
        self.google.error = RuntimeError("RESOURCE_EXHAUSTED: quota")
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)
        self.assertNotIn("fallback", out)
        self.assertEqual([call["provider"] for call in self.logged()], ["Google", "OpenAI"])

    def urlopen(self, urls):
        """A stand-in for urllib's urlopen: Gemini fails on quota, GPT answers, every URL is recorded."""
        import urllib.error

        def fake(request, timeout=None):
            url = request.full_url
            urls.append(url)
            if url.startswith(second_opinion.GEMINI_API):
                body = io.BytesIO(b'{"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}}')
                raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, body)
            if url == f"{second_opinion.OPENAI_API}/models":
                return io.BytesIO(b'{"data": [{"id": "gpt-6.1-sol"}]}')
            if url == f"{second_opinion.OPENAI_API}/chat/completions":
                return io.BytesIO(json.dumps({"choices": [{"message": {"content": "VERDICT: APPROVED"}, "finish_reason": "stop"}],
                                              "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode())
            raise AssertionError(f"request to an unexpected host: {url}")

        return mock.patch.object(second_opinion.urllib.request, "urlopen", fake)

    def test_no_route_reaches_another_host(self):
        """The real providers, another provider's key set and Gemini failing: every product, kind and --only."""
        keys = ("GEMINI_API_KEY", "OPENAI_API_KEY", "OTHER_API_KEY")
        for product in [None, "acme", "demo"]:
            for kind in ["design", "code", "plan"]:
                for only in [[], ["--only", "gemini"]]:
                    with self.subTest(product=product, kind=kind, only=only):
                        urls = []
                        args = ["--kind", kind, "--brief", "T-1", *only] + (["--product", product] if product else [])
                        with self.urlopen(urls):
                            code, out = self.run_main(args, keys=keys, providers=None)
                        self.assertEqual(code, 0)
                        for url in urls:
                            self.assertTrue(url.startswith((second_opinion.GEMINI_API, second_opinion.OPENAI_API)), url)
                        if kind == "plan":
                            self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)
                        if not only:
                            self.assertIn("SECOND OPINION (OpenAI gpt-6.1-sol", out)

    def test_gemini_is_never_called_for_code_or_design(self):
        """The real providers, both keys set."""
        for kind in ["design", "code"]:
            for only in [[], ["--only", "gemini"]]:
                with self.subTest(kind=kind, only=only):
                    urls = []
                    with self.urlopen(urls):
                        code, out = self.run_main(["--kind", kind, "--brief", "T-1", *only], providers=None)
                    self.assertEqual(code, 0)
                    self.assertFalse([url for url in urls if url.startswith(second_opinion.GEMINI_API)], urls)
                    self.assertNotIn("SECOND OPINION (Google", out)
                    if only:
                        self.assertEqual(urls, [])
                        self.assertTrue(out.startswith(f"SECOND OPINION: OFF (no provider company.json names is asked for {kind} reviews"), out)
                    else:
                        self.assertIn("SECOND OPINION (OpenAI gpt-6.1-sol", out)
        self.assertEqual([call["provider"] for call in self.logged()], ["OpenAI", "OpenAI"])

    def test_only_another_providers_key_is_off(self):
        for kind, keys in [("plan", "GEMINI_API_KEY, OPENAI_API_KEY"), ("code", "OPENAI_API_KEY")]:
            with self.subTest(kind=kind):
                urls = []
                with self.urlopen(urls):
                    code, out = self.run_main(["--kind", kind, "--brief", "T-1"], keys=("OTHER_API_KEY",), providers=None)
                self.assertTrue(out.startswith(f"SECOND OPINION: OFF (no {keys} set"), out)
                self.assertEqual(urls, [])

    def test_the_two_providers(self):
        self.assertEqual([p.label for p in second_opinion.default_providers()], ["Google", "OpenAI"])

    def test_plan_gets_its_own_instruction_and_no_engineering_checklist(self):
        path = self.file("packet.md", "Goal: fewer late orders. Plan: show two dates.\n")
        self.run_main(["--kind", "plan", "--brief", "D-20260101-x", "--file", path])
        sent = self.openai.sent[0]
        self.assertIn("SUPPORT | REVISE | RETHINK", sent["instruction"])
        self.assertIn("Plan: show two dates.", sent["packet"])
        self.assertNotIn("Review checklists", sent["packet"])

    # What a packet carries, and in which order

    def packet(self, kind, brief="T-1", files=(), diff=None):
        self.openai.sent = []
        args = ["--kind", kind, "--brief", brief]
        for path in files:
            args += ["--file", path]
        if diff:
            args += ["--diff", *diff]
        self.run_main(args)
        return self.openai.sent[0]["packet"]

    def test_code_packet_leaves_out_only_the_design_review_section(self):
        code, design = self.packet("code"), self.packet("design")
        for kind, packet in [("code", code), ("design", design)]:
            with self.subTest(kind=kind):
                self.assertIn("Rank every finding", packet)  # the grades
                self.assertIn("## Code review (code reviewer)", packet)
                self.assertIn("# Security standards", packet)  # security.md, whole
        self.assertNotIn("## Design review", code)
        self.assertIn("its design review section left out: this is a code review", code)
        self.assertIn("## Design review (design reviewer)", design)
        self.assertNotIn("design review section left out", design)

    def test_checklist_without_a_design_review_section_is_sent_whole(self):
        root = self.dir / "root"
        for rel, text in [(second_opinion.RUBRIC_FILES[0], "# Checklist\n\n## Reviews\n1. Tests.\n"),
                          (second_opinion.RUBRIC_FILES[1], "# Security\n\n## Design review notes\nnone\n")]:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        with mock.patch.object(second_opinion, "ROOT", root):
            packet = self.packet("code")
        self.assertIn("# Checklist\n\n## Reviews\n1. Tests.\n", packet)
        self.assertIn("## Design review notes\nnone\n", packet)  # only an exact "## Design review" section goes
        self.assertNotIn("design review section left out", packet)

    def test_the_checklist_is_a_shared_prefix_and_the_diff_comes_last(self):
        repo = self.dir / "repo"
        repo.mkdir()
        git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (repo / "app.py").write_text("print(1)\n")
        git("add", ".")
        git("commit", "-qm", "base")
        (repo / "app.py").write_text("print(2)\n")
        git("commit", "-qam", "change")
        one = self.packet("code", "T-1: timer", [self.file("spec.md", "Spec one.\n")], [str(repo), "HEAD~1..HEAD"])
        two = self.packet("code", "T-2: other", [self.file("other.md", "Spec two.\n")])
        shared = one[:one.index("\n\nBRIEF: ")]  # everything before the brief: the same in every code packet
        self.assertEqual(two[:len(shared)], shared)
        self.assertTrue(shared.startswith("REVIEW KIND: code\n\n=== COMPANY CHECKLIST"), shared[:80])
        self.assertIn("## Code review (code reviewer)", shared)
        self.assertIn("# Security standards", shared)  # every checklist part is in the shared prefix
        places = [one.index(part) for part in ["=== COMPANY CHECKLIST", "BRIEF: T-1", "=== FILE:", "Spec one.", "=== DIFF:"]]
        self.assertEqual(places, sorted(places))
        self.assertTrue(one.rstrip().endswith("+print(2)"), one[-80:])

    def test_only_gemini_sends_nothing_to_gpt(self):
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1", "--only", "gemini"])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION (Google g-model", out)
        self.assertNotIn("OpenAI", out)
        self.assertEqual(len(self.google.sent), 1)
        self.assertEqual(self.openai.sent, [])
        self.assertEqual([call["provider"] for call in self.logged()], ["Google"])

    def test_only_gemini_failing_sends_nothing_else(self):
        self.google.error = RuntimeError("quota")
        _, out = self.run_main(["--kind", "plan", "--brief", "T-1", "--only", "gemini"])
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)
        self.assertEqual(self.openai.sent, [])
        self.assertEqual([call["provider"] for call in self.logged()], ["Google"])

    def test_only_gemini_with_no_gemini_slot_key_says_so(self):
        _, out = self.run_main(["--kind", "plan", "--brief", "T-1", "--only", "gemini"], keys=("OPENAI_API_KEY",))
        self.assertTrue(out.startswith("SECOND OPINION: OFF (no GEMINI_API_KEY set"), out)
        self.assertEqual(self.openai.sent, [])

    def test_only_takes_no_other_provider(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.run_main(["--kind", "code", "--brief", "T-1", "--only", "openai"])

    def test_model_env_override_skips_listing(self):
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"], extra_env={"SECOND_OPINION_GEMINI_MODEL": "pinned-model"})
        self.assertEqual(self.google.listed, 0)
        self.assertEqual(self.google.sent[0]["model"], "pinned-model")

    def test_one_provider_failing_doesnt_stop_the_other(self):
        self.google.error = RuntimeError("quota exceeded")
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)
        self.assertIn("quota exceeded", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)

    def test_http_error_shows_the_providers_reason(self):
        import urllib.error
        body = b'{"error": {"status": "RESOURCE_EXHAUSTED", "message": "You exceeded your current quota, please check your plan."}}'
        self.google.error = urllib.error.HTTPError("https://example.invalid", 429, "Too Many Requests", {}, io.BytesIO(body))
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
        self.assertIn("RESOURCE_EXHAUSTED", out)
        self.assertIn("You exceeded your current quota", out)

    def test_model_listing_failure_is_unavailable(self):
        self.openai.list_error = RuntimeError("401 bad key")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertIn("SECOND OPINION (OpenAI): UNAVAILABLE", out)
        self.assertIn("401 bad key", out)

    def test_no_suitable_model_is_unavailable(self):
        self.google.models = []
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)

    # Output cap and call log

    def test_each_answered_call_logs_its_usage(self):
        path = self.file("timer.ts", "export const limit = 100;\n")
        self.run_main(["--kind", "plan", "--brief", "DD-001", "--file", path])
        lines = self.logged()
        self.assertEqual([(l["provider"], l["model"]) for l in lines], [("Google", "g-model"), ("OpenAI", "o-model")])
        packet = self.google.sent[0]["packet"]
        for line in lines:
            self.assertEqual(set(line), {"id", "at", "provider", "model", "max_out_tokens", "answered", "in_tokens",
                                         "cached_tokens", "out_tokens", "thinking_tokens", "kind", "packet_bytes",
                                         "requested_tier", "service_tier", "fallback"})
            self.assertTrue(line["answered"])
            self.assertEqual((line["requested_tier"], line["service_tier"], line["fallback"]), (None, None, False))
            self.assertEqual((line["in_tokens"], line["out_tokens"], line["thinking_tokens"]), (1200, 900, 700))
            self.assertIsNone(line["cached_tokens"])  # not reported: null, never 0
            self.assertEqual(line["max_out_tokens"], second_opinion.MAX_OUT_TOKENS)
            self.assertEqual(line["kind"], "plan")
            self.assertEqual(line["packet_bytes"], len(packet.encode("utf-8")))
            self.assertRegex(line["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")
        self.assertNotEqual(lines[0]["id"], lines[1]["id"])

    def test_failed_call_is_logged_unanswered(self):
        self.google.error = TimeoutError("timed out")
        self.run_main(["--kind", "plan", "--brief", "T-1"])
        google, openai = self.logged()
        self.assertEqual((google["provider"], google["answered"]), ("Google", False))
        self.assertEqual((google["in_tokens"], google["out_tokens"], google["thinking_tokens"]), (None, None, None))
        self.assertIsNone(google["cached_tokens"])
        self.assertGreater(google["packet_bytes"], 0)
        self.assertEqual((openai["provider"], openai["answered"]), ("OpenAI", True))

    def test_cached_input_is_logged(self):
        self.openai.cached = 1024
        self.run_main(["--kind", "code", "--brief", "T-1"])
        [line] = self.logged()
        self.assertEqual((line["in_tokens"], line["cached_tokens"]), (1200, 1024))

    def test_slots_that_never_send_arent_logged(self):
        self.openai.list_error = RuntimeError("401 bad key")
        self.google.models = []
        self.run_main(["--kind", "plan", "--brief", "T-1"], keys=("GEMINI_API_KEY", "OPENAI_API_KEY"))
        self.assertEqual(self.logged(), [])

    def test_unwritable_log_still_returns_the_review(self):
        self.log.parent.parent.mkdir(parents=True)
        self.log.parent.write_text("a file where the log's directory should be")
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION: CALL NOT LOGGED (Google g-model", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)
        self.assertIn("[major] a.ts:3", out)

    def answers(self):
        folder = self.log.parent / "sa003-answers"
        return {p.stem: p.read_text() for p in folder.iterdir()} if folder.exists() else {}

    def test_each_answer_is_saved_by_its_call_id(self):
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
        google, openai = self.logged()
        self.assertEqual(self.answers(), {google["id"]: self.google.reply, openai["id"]: self.openai.reply})
        self.assertIn(f"SECOND OPINION (Google g-model, another model family; call {google['id']}):", out)
        self.assertIn(f"SECOND OPINION (OpenAI o-model, another model family; call {openai['id']}):", out)

    def test_each_products_calls_and_answers_land_under_its_own_path(self):
        """Under the packet's product, workspaces/<product>/content/; with no --product, the company's own."""
        self.assertEqual(REAL_WORKSPACES, second_opinion.ROOT / "workspaces")
        for product in NAMED["products"]:
            with self.subTest(product=product):
                shutil.rmtree(self.workspaces, ignore_errors=True)
                code, out = self.run_main(["--kind", "plan", "--brief", "T-1", "--product", product])
                self.assertEqual(code, 0)
                content = self.workspaces / product / "content"
                lines = [json.loads(line) for line in (content / "sa003-calls.jsonl").read_text().splitlines()]
                self.assertEqual([line["provider"] for line in lines], ["Google", "OpenAI"])
                self.assertEqual({p.stem: p.read_text() for p in (content / "sa003-answers").iterdir()},
                                 {lines[0]["id"]: self.google.reply, lines[1]["id"]: self.openai.reply})
                self.assertEqual([p.name for p in self.workspaces.iterdir()], [product])  # no other product's
        shutil.rmtree(self.workspaces)
        self.run_main(["--kind", "code", "--brief", "T-1"])
        [line] = self.logged()
        self.assertEqual(list(self.answers()), [line["id"]])
        self.assertEqual([p.name for p in self.workspaces.iterdir()], ["second-opinions"])

    def test_unanswered_calls_save_nothing(self):
        self.google.error = TimeoutError("timed out")
        self.openai.reply, self.openai.capped = "", True
        self.run_main(["--kind", "plan", "--brief", "T-1"])
        self.assertEqual(len(self.logged()), 2)
        self.assertEqual(self.answers(), {})

    def test_cut_off_answer_is_saved_with_its_note(self):
        self.openai.capped = True
        self.run_main(["--kind", "code", "--brief", "T-1"])
        openai = self.logged()[-1]
        self.assertIn("Cut off at the output cap", self.answers()[openai["id"]])

    def test_unsavable_answer_still_returns_the_review(self):
        self.log.parent.mkdir(parents=True)
        (self.log.parent / "sa003-answers").write_text("a file where the answers' directory should be")
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION: ANSWER NOT SAVED (OpenAI o-model", out)
        self.assertIn("[major] a.ts:3", out)
        self.assertEqual(len(self.logged()), 2)

    def test_reply_cut_off_at_the_cap_says_so(self):
        self.openai.capped = True
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertIn("[major] a.ts:3", out)
        self.assertIn(f"Cut off at the output cap of {second_opinion.MAX_OUT_TOKENS:,} tokens", out)

    def test_empty_reply_at_the_cap_is_unavailable(self):
        self.google.reply, self.google.capped = "", True
        code, out = self.run_main(["--kind", "plan", "--brief", "T-1"])
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE (g-model: stopped at the output cap", out)
        self.assertEqual([l["answered"] for l in self.logged()], [True, True])  # the empty reply was billed

    # GPT's service tier, a run-time value

    TIER = second_opinion.OPENAI_TIER_ENV

    def http_error(self, code):
        import urllib.error
        body = io.BytesIO(b'{"error": {"message": "Resource Unavailable"}}')
        return urllib.error.HTTPError("https://example.invalid", code, "x", {}, body)

    def tiers(self):
        return [(l["requested_tier"], l["answered"], l["service_tier"], l["fallback"]) for l in self.logged()]

    def test_unset_or_empty_tier_sends_none(self):
        for value in [None, "", "  "]:
            with self.subTest(value=value):
                self.openai.sent = []
                _, out = self.run_main(["--kind", "code", "--brief", "T-1"], extra_env={} if value is None else {self.TIER: value})
                self.assertEqual([s["tier"] for s in self.openai.sent], [()])  # no tier argument at all
                self.assertIn("SECOND OPINION (OpenAI o-model", out)
                self.assertNotIn("FLEX", out)
        self.assertEqual(self.tiers(), [(None, True, None, False)] * 3)

    def test_flex_is_sent_and_its_served_tier_logged(self):
        _, out = self.run_main(["--kind", "plan", "--brief", "T-1"], extra_env={self.TIER: "flex"})
        self.assertEqual([s["tier"] for s in self.openai.sent], [("flex",)])
        self.assertEqual([s["tier"] for s in self.google.sent], [()])  # Gemini has no tier
        self.assertIn("SECOND OPINION (OpenAI o-model", out)
        self.assertEqual(self.tiers(), [(None, True, None, False), ("flex", True, "flex", False)])

    def test_any_other_tier_is_refused_without_sending(self):
        for value in ["FLEX", "Flex", "default", "auto", "priority", "scale", "flex,default", "1"]:
            with self.subTest(value=value):
                self.openai.sent, self.openai.listed = [], 0
                code, out = self.run_main(["--kind", "code", "--brief", "T-1"], extra_env={self.TIER: value})
                self.assertEqual(code, 0)
                self.assertIn(f"SECOND OPINION (OpenAI): NOT SENT ({self.TIER} is {value!r}; it takes 'flex'", out)
                self.assertEqual((self.openai.listed, self.openai.sent), (0, []))
        self.assertEqual(self.logged(), [])

    def test_a_refused_tier_leaves_geminis_plan_opinion(self):
        _, out = self.run_main(["--kind", "plan", "--brief", "T-1"], extra_env={self.TIER: "auto"})
        self.assertIn("SECOND OPINION (Google g-model", out)
        self.assertIn("SECOND OPINION (OpenAI): NOT SENT", out)
        self.assertEqual(self.openai.sent, [])
        self.assertEqual([l["provider"] for l in self.logged()], ["Google"])

    def test_flex_busy_or_slow_is_sent_once_more_at_standard(self):
        import urllib.error
        for error in [self.http_error(429), self.http_error(408), TimeoutError("timed out"),
                      urllib.error.URLError(TimeoutError("timed out"))]:
            with self.subTest(error=error):
                self.openai.sent, self.openai.errors = [], [error]
                self.log.unlink(missing_ok=True)
                _, out = self.run_main(["--kind", "code", "--brief", "T-1"], extra_env={self.TIER: "flex"})
                first, second = self.openai.sent
                self.assertEqual((first["tier"], second["tier"]), (("flex",), ("default",)))
                self.assertEqual((first["packet"], first["instruction"]), (second["packet"], second["instruction"]))
                self.assertIn("SECOND OPINION (OpenAI): FLEX FAILED (o-model: ", out)
                self.assertIn("sent once more at the standard tier.", out)
                self.assertIn("[major] a.ts:3", out)
                self.assertEqual(self.tiers(), [("flex", False, None, False), ("default", True, "default", True)])
                flex, resend = self.logged()
                self.assertIn(f"call {resend['id']}):", out)
                self.assertIn(resend["id"], self.answers())
                self.assertNotIn(flex["id"], self.answers())

    def test_never_a_second_resend(self):
        for again in [self.http_error(429), TimeoutError("timed out")]:
            with self.subTest(again=again):
                self.openai.sent, self.openai.errors = [], [self.http_error(429), again]
                self.log.unlink(missing_ok=True)
                code, out = self.run_main(["--kind", "code", "--brief", "T-1"], extra_env={self.TIER: "flex"})
                self.assertEqual(code, 0)
                self.assertEqual([s["tier"] for s in self.openai.sent], [("flex",), ("default",)])
                self.assertIn("FLEX FAILED", out)
                self.assertIn("SECOND OPINION (OpenAI): UNAVAILABLE (o-model: ", out)
                self.assertEqual(self.tiers(), [("flex", False, None, False), ("default", False, None, True)])

    def test_other_flex_failures_get_no_resend(self):
        import urllib.error
        for error in [self.http_error(400), self.http_error(401), self.http_error(500), self.http_error(503),
                      RuntimeError("no answer"), urllib.error.URLError(ConnectionRefusedError())]:
            with self.subTest(error=error):
                self.openai.sent, self.openai.errors = [], [error]
                _, out = self.run_main(["--kind", "code", "--brief", "T-1"], extra_env={self.TIER: "flex"})
                self.assertEqual([s["tier"] for s in self.openai.sent], [("flex",)])
                self.assertIn("SECOND OPINION (OpenAI): UNAVAILABLE (o-model: ", out)
                self.assertNotIn("FLEX FAILED", out)

    def test_standard_calls_are_never_resent(self):
        for error in [self.http_error(429), self.http_error(408), TimeoutError("timed out")]:
            with self.subTest(error=error):
                self.openai.sent, self.openai.errors = [], [error]
                _, out = self.run_main(["--kind", "code", "--brief", "T-1"])
                self.assertEqual([s["tier"] for s in self.openai.sent], [()])
                self.assertIn("SECOND OPINION (OpenAI): UNAVAILABLE (o-model: ", out)

    def test_the_secret_check_runs_once_on_the_packet_both_sends_carry(self):
        checked, real = [], second_opinion.find_secrets

        def spy(packet):
            checked.append(packet)
            return real(packet)

        self.openai.errors = [self.http_error(429)]
        with mock.patch.object(second_opinion, "find_secrets", spy):
            self.run_main(["--kind", "code", "--brief", "T-1", "--file", self.file("a.py", "x = 1\n")],
                          extra_env={self.TIER: "flex"})
        self.assertEqual(len(checked), 1)
        self.assertEqual([s["packet"] for s in self.openai.sent], checked * 2)

    def test_flex_changes_no_refusal(self):
        for args in [["--file", self.file("notes.md", "config:\n" + FAKE_KEY_BLOCK)], ["--file", self.file(".env.prod", "A=1\n")],
                     ["--file", self.file("big.txt", "x" * (second_opinion.MAX_PACKET_CHARS + 1))]]:
            with self.subTest(args=args):
                _, out = self.run_main(["--kind", "code", "--brief", "T-1", *args], extra_env={self.TIER: "flex"})
                self.assertTrue(out.startswith("SECOND OPINION: NOT SENT"), out)
        self.assertEqual((self.openai.listed, self.openai.sent), (0, []))

    def chat_bodies(self, env, statuses=()):
        """The real providers on a code review, urlopen faked: each chat request body as sent, in bytes.
        `statuses` fail the first chat calls with those HTTP codes; a reply reports the tier asked, or "default"."""
        import urllib.error
        bodies, statuses = [], list(statuses)

        def fake(request, timeout=None):
            if request.full_url == f"{second_opinion.OPENAI_API}/models":
                return io.BytesIO(b'{"data": [{"id": "gpt-6.1-sol"}]}')
            self.assertEqual(request.full_url, f"{second_opinion.OPENAI_API}/chat/completions")
            self.assertEqual(timeout, 600)
            bodies.append(request.data)
            if statuses:
                raise urllib.error.HTTPError(request.full_url, statuses.pop(0), "x", {},
                                             io.BytesIO(b'{"error": {"message": "Resource Unavailable"}}'))
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": "VERDICT: APPROVED"}, "finish_reason": "stop"}],
                                          "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                                          "service_tier": json.loads(request.data).get("service_tier", "default")}).encode())

        with mock.patch.object(second_opinion.urllib.request, "urlopen", fake):
            _, out = self.run_main(["--kind", "code", "--brief", "T-1"], keys=("OPENAI_API_KEY",), extra_env=env, providers=None)
        return bodies, out

    def todays_body(self, **tier):
        """The chat request as the script sent it before the tier existed, plus `tier`."""
        return json.dumps({
            "model": "gpt-6.1-sol",
            "messages": [{"role": "system", "content": second_opinion.INSTRUCTION.format(kind="code")},
                         {"role": "user", "content": second_opinion.build_packet("code", "T-1", [], None)}],
            "max_completion_tokens": second_opinion.MAX_OUT_TOKENS, **tier}).encode()

    def test_no_tier_sends_todays_request_byte_for_byte(self):
        for env in [{}, {self.TIER: ""}]:
            with self.subTest(env=env):
                bodies, out = self.chat_bodies(env)
                self.assertEqual(bodies, [self.todays_body()])
                self.assertIn("SECOND OPINION (OpenAI gpt-6.1-sol", out)
        self.assertEqual(self.tiers(), [(None, True, "default", False)] * 2)

    def test_flex_on_the_wire_and_its_resend_at_default(self):
        bodies, _ = self.chat_bodies({self.TIER: "flex"})
        self.assertEqual(bodies, [self.todays_body(service_tier="flex")])
        bodies, out = self.chat_bodies({self.TIER: "flex"}, statuses=[429])
        self.assertEqual(bodies, [self.todays_body(service_tier="flex"), self.todays_body(service_tier="default")])
        self.assertIn("FLEX FAILED (gpt-6.1-sol: HTTPError: HTTP Error 429", out)
        self.assertIn("Resource Unavailable); sent once more at the standard tier.", out)
        self.assertIn("SECOND OPINION (OpenAI gpt-6.1-sol", out)
        self.assertEqual(self.tiers(), [("flex", True, "flex", False), ("flex", False, None, False),
                                        ("default", True, "default", True)])

    def test_gemini_gets_no_tier_and_no_resend(self):
        """The real providers on a plan with flex on: Gemini's request has no tier, and its 429 is not resent."""
        import urllib.error
        gemini = []

        def fake(request, timeout=None):
            url = request.full_url
            if url.startswith(f"{second_opinion.GEMINI_API}/models?"):
                return io.BytesIO(b'{"models": [{"name": "models/gemini-4-carbon", "supportedGenerationMethods": ["generateContent"]}]}')
            if url.startswith(second_opinion.GEMINI_API):
                gemini.append(json.loads(request.data))
                raise urllib.error.HTTPError(url, 429, "x", {}, io.BytesIO(b'{"error": {"status": "RESOURCE_EXHAUSTED"}}'))
            if url == f"{second_opinion.OPENAI_API}/models":
                return io.BytesIO(b'{"data": [{"id": "gpt-6.1-sol"}]}')
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": "VERDICT: SUPPORT"}, "finish_reason": "stop"}],
                                          "usage": {}, "service_tier": "flex"}).encode())

        with mock.patch.object(second_opinion.urllib.request, "urlopen", fake):
            _, out = self.run_main(["--kind", "plan", "--brief", "T-1"], extra_env={self.TIER: "flex"}, providers=None)
        self.assertEqual(len(gemini), 1)
        self.assertNotIn("service_tier", json.dumps(gemini[0]))
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE (gemini-4-carbon: HTTPError: HTTP Error 429", out)
        self.assertIn("SECOND OPINION (OpenAI gpt-6.1-sol", out)
        self.assertEqual([(l["provider"], l["requested_tier"]) for l in self.logged()], [("Google", None), ("OpenAI", "flex")])

    # What never gets sent

    def test_refuses_secrets_file_by_name(self):
        path = self.file(".env.prod", "HARMLESS=1\n")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1", "--file", path])
        self.assertTrue(out.startswith("SECOND OPINION: NOT SENT"), out)
        self.assertEqual(self.google.sent + self.openai.sent, [])

    def test_refuses_packet_containing_a_secret(self):
        path = self.file("notes.md", "config:\n" + FAKE_KEY_BLOCK)
        code, out = self.run_main(["--kind", "code", "--brief", "T-1", "--file", path])
        self.assertTrue(out.startswith("SECOND OPINION: NOT SENT"), out)
        self.assertIn("private key", out)
        self.assertNotIn("MIIEow", out)
        self.assertEqual(self.google.sent + self.openai.sent, [])

    def test_refuses_oversized_packet(self):
        path = self.file("big.txt", "x" * (second_opinion.MAX_PACKET_CHARS + 1))
        code, out = self.run_main(["--kind", "code", "--brief", "T-1", "--file", path])
        self.assertTrue(out.startswith("SECOND OPINION: NOT SENT"), out)
        self.assertEqual(self.google.sent + self.openai.sent, [])

    def test_diff_leaves_out_secret_files(self):
        repo = self.dir / "repo"
        repo.mkdir()
        git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (repo / "app.py").write_text("print(1)\n")
        git("add", ".")
        git("commit", "-qm", "base")
        (repo / "app.py").write_text("print(2)\n")
        (repo / ".env.prod").write_text("TOKEN=do-not-send-123\n")
        (repo / "svc_private_key.json").write_text('{"note": "do-not-send-456"}\n')
        git("add", ".")
        git("commit", "-qm", "change")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1", "--diff", str(repo), "HEAD~1..HEAD"])
        packet = self.openai.sent[0]["packet"]
        self.assertIn("print(2)", packet)
        self.assertNotIn("do-not-send-123", packet)
        self.assertNotIn("do-not-send-456", packet)


class ModelChoice(unittest.TestCase):
    """The default models, found in the key's model list; never guessed IDs."""

    def test_gemini_prefers_carbon_when_listed(self):
        ids = ["gemini-3.8-flash", "gemini-4-argon", "gemini-4-carbon-preview", "gemini-4-carbon", "gemini-3.1-pro-preview"]
        self.assertEqual(choose_gemini(ids), "gemini-4-carbon")

    def test_gemini_never_falls_back_to_argon(self):
        self.assertEqual(choose_gemini(["gemini-4-argon", "gemini-4-argon-preview", "gemini-3.8-flash"]), "gemini-3.8-flash")
        self.assertIsNone(choose_gemini(["gemini-4-argon", "gemini-4-argon-preview"]))

    def test_gemini_takes_only_the_exact_carbon_id(self):
        ids = ["gemini-4-carbon-preview", "gemini-4-carbon-tts", "gemini-4-carbon-image", "gemini-3.8-flash"]
        self.assertEqual(choose_gemini(ids), "gemini-3.8-flash")

    def test_gemini_otherwise_uses_3_8_flash(self):
        ids = ["gemini-3.1-pro-preview", "gemini-3.8-flash-tts", "gemini-3.8-flash", "gemini-3.7-flash"]
        self.assertEqual(choose_gemini(ids), "gemini-3.8-flash")

    def test_gemini_none_when_neither_listed(self):
        self.assertIsNone(choose_gemini(["gemini-3.1-pro-preview", "gemini-3.7-flash"]))

    def test_openai_uses_6_1_sol(self):
        self.assertEqual(choose_openai(["gpt-6-astra", "gpt-6-sol", "gpt-6.1-sol"]), "gpt-6.1-sol")

    def test_openai_none_without_6_1_sol(self):
        self.assertIsNone(choose_openai(["gpt-6-astra", "gpt-6-sol"]))


class Requests(unittest.TestCase):
    """What each provider is sent, and how its reply's usage is read."""

    def post(self, response):
        captured = {}

        def fake_post(url, body, headers):
            captured["body"] = body
            return response

        return captured, mock.patch.object(second_opinion, "_post_json", fake_post)

    def test_cap_is_one_every_model_accepts(self):
        self.assertLessEqual(second_opinion.MAX_OUT_TOKENS, 65_536)

    def test_gemini_thinks_high_under_the_cap(self):
        captured, patch = self.post({
            "candidates": [{"content": {"parts": [{"text": "VERDICT: APPROVED"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 5000, "candidatesTokenCount": 300, "thoughtsTokenCount": 4000},
        })
        with patch:
            reply = second_opinion.gemini_send("packet", "instruction", "gemini-3.8-flash", "key")
        config = captured["body"]["generationConfig"]
        self.assertEqual(config["thinkingConfig"]["thinkingLevel"], "high")
        self.assertEqual(config["maxOutputTokens"], second_opinion.MAX_OUT_TOKENS)
        self.assertEqual(reply, Reply("VERDICT: APPROVED", 5000, 4300, 4000, False))

    def test_gemini_stopped_while_thinking(self):
        _, patch = self.post({
            "candidates": [{"content": {"role": "model"}, "finishReason": "MAX_TOKENS"}],
            "usageMetadata": {"promptTokenCount": 5000, "thoughtsTokenCount": 65536},
        })
        with patch:
            reply = second_opinion.gemini_send("packet", "instruction", "gemini-4-carbon", "key")
        self.assertEqual(reply, Reply("", 5000, 65536, 65536, True))

    def test_gemini_unreported_counts_are_none_not_zero(self):
        for usage, expected in [
            (None, (None, None, None)),
            ({"promptTokenCount": 5000}, (5000, None, None)),  # no output count: priced at worst case, never 0
            ({"promptTokenCount": 5000, "candidatesTokenCount": 300}, (5000, 300, None)),
        ]:
            response = {"candidates": [{"content": {"parts": [{"text": "VERDICT: APPROVED"}]}}]}
            if usage:
                response["usageMetadata"] = usage
            _, patch = self.post(response)
            with patch:
                reply = second_opinion.gemini_send("packet", "instruction", "gemini-4-carbon", "key")
            self.assertEqual((reply.in_tokens, reply.out_tokens, reply.thinking_tokens), expected, usage)

    def test_openai_names_the_cap_its_own_way(self):
        response = {
            "choices": [{"message": {"content": "VERDICT: APPROVED"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5000, "completion_tokens": 2500, "completion_tokens_details": {"reasoning_tokens": 2000}},
        }
        [chat] = [p for p in second_opinion.default_providers() if p.label == "OpenAI"]
        captured, patch = self.post(response)
        with patch:
            reply = chat.send("packet", "instruction", "model", "key")
        self.assertEqual(captured["body"]["max_completion_tokens"], second_opinion.MAX_OUT_TOKENS)
        self.assertEqual(reply, Reply("VERDICT: APPROVED", 5000, 2500, 2000, False))

    def test_openai_cached_input_is_read(self):
        [chat] = [p for p in second_opinion.default_providers() if p.label == "OpenAI"]
        for usage, expected in [({"prompt_tokens": 5000, "prompt_tokens_details": {"cached_tokens": 3072}}, 3072),
                                ({"prompt_tokens": 5000, "prompt_tokens_details": {"cached_tokens": 0}}, 0),
                                ({"prompt_tokens": 5000}, None)]:  # not reported: null, never 0
            _, patch = self.post({"choices": [{"message": {"content": "VERDICT: APPROVED"}, "finish_reason": "stop"}],
                                  "usage": usage})
            with patch:
                reply = chat.send("packet", "instruction", "model", "key")
            self.assertEqual(reply.cached_tokens, expected, usage)

    def test_openai_reasoning_effort_is_a_run_time_value(self):
        """Unset or empty sends none (the model's default); a value is sent as reasoning_effort."""
        response = {"choices": [{"message": {"content": "VERDICT: APPROVED"}, "finish_reason": "stop"}], "usage": {}}
        [chat] = [p for p in second_opinion.default_providers() if p.label == "OpenAI"]
        for value, expected in [(None, None), ("", None), (" low ", "low"), ("medium", "medium")]:
            env = {k: v for k, v in os.environ.items() if k != second_opinion.OPENAI_EFFORT_ENV}
            if value is not None:
                env[second_opinion.OPENAI_EFFORT_ENV] = value
            captured, patch = self.post(response)
            with patch, mock.patch.dict(os.environ, env, clear=True):
                chat.send("packet", "instruction", "model", "key")
            self.assertEqual(captured["body"].get("reasoning_effort"), expected, value)

    def test_openai_tier_is_sent_and_the_served_tier_read(self):
        """A tier goes out as service_tier, none without one; the reply's own service_tier is what's read."""
        [chat] = [p for p in second_opinion.default_providers() if p.label == "OpenAI"]
        for tier, served in [(None, None), (None, "default"), ("flex", "flex"), ("flex", "default"), ("default", "default")]:
            response = {"choices": [{"message": {"content": "VERDICT: APPROVED"}, "finish_reason": "stop"}], "usage": {}}
            if served:
                response["service_tier"] = served
            captured, patch = self.post(response)
            with patch:
                reply = chat.send("packet", "instruction", "model", "key", *([tier] if tier else []))
            self.assertEqual(("service_tier" in captured["body"], captured["body"].get("service_tier")), (tier is not None, tier))
            self.assertEqual(reply.service_tier, served)

    def test_only_gpt_has_a_tier(self):
        self.assertEqual({p.label: p.tier_env for p in second_opinion.default_providers()},
                         {"Google": None, "OpenAI": "SECOND_OPINION_OPENAI_TIER"})

    def test_chat_stopped_at_the_cap(self):
        _, patch = self.post({"choices": [{"message": {"content": None}, "finish_reason": "length"}],
                              "usage": {"prompt_tokens": 5000, "completion_tokens": 65536}})
        with patch:
            reply = second_opinion.chat_send(second_opinion.OPENAI_API, "max_completion_tokens")("p", "i", "m", "k")
        self.assertEqual(reply, Reply("", 5000, 65536, None, True))


if __name__ == "__main__":
    unittest.main()
