"""Tests for scripts/second_opinion.py (reviewers from other model families).

Providers are injected, so no test reaches Google or OpenAI.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import second_opinion  # noqa: E402
from second_opinion import Provider, Reply, choose_deepseek, choose_gemini, choose_openai  # noqa: E402

FAKE_KEY_BLOCK = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow\n"


class FakeApi:
    """Stands in for one provider's model list and generate call."""

    def __init__(self, models=("model-a",), reply="VERDICT: APPROVED\nFindings: none", error=None, list_error=None,
                 capped=False):
        self.models, self.reply, self.error, self.list_error = list(models), reply, error, list_error
        self.capped = capped
        self.sent, self.listed = [], 0

    def list_models(self, api_key):
        self.listed += 1
        if self.list_error:
            raise self.list_error
        return self.models

    def send(self, packet, instruction, model, api_key):
        self.sent.append({"packet": packet, "instruction": instruction, "model": model, "api_key": api_key})
        if self.error:
            raise self.error
        return Reply(self.reply, in_tokens=1200, out_tokens=900, thinking_tokens=700, capped=self.capped)


def provider(label, key_env, model_env, api, fallback=None):
    return Provider(label, key_env, model_env, api.list_models, api.send, lambda ids: ids[0] if ids else None, fallback)


class SecondOpinion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.google = FakeApi(models=["g-model"], reply="VERDICT: APPROVED\nFindings: none")
        self.openai = FakeApi(models=["o-model"], reply="VERDICT: CHANGES_REQUESTED\nFindings:\n1. [major] a.ts:3: x -> y")
        self.deepseek = FakeApi(models=["d-model"], reply="VERDICT: APPROVED\nFindings: none")
        self.log = self.dir / "logs" / "calls.jsonl"  # never the real log
        patcher = mock.patch.object(second_opinion, "CALL_LOG", self.log)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def logged(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def providers(self):
        deepseek = provider("DeepSeek", "DEEPSEEK_API_KEY", "SECOND_OPINION_DEEPSEEK_MODEL", self.deepseek)
        return [
            provider("Google", "GEMINI_API_KEY", "SECOND_OPINION_GEMINI_MODEL", self.google, fallback=deepseek),
            provider("OpenAI", "OPENAI_API_KEY", "SECOND_OPINION_OPENAI_MODEL", self.openai),
        ]

    def run_main(self, args, keys=("GEMINI_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"), extra_env=None):
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and not k.startswith("SECOND_OPINION")}
        env.update({k: f"key-for-{k}" for k in keys})
        env.update(extra_env or {})
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(out):
            code = second_opinion.main(args, providers=self.providers())
        return code, out.getvalue()

    def file(self, name, content):
        path = self.dir / name
        path.write_text(content)
        return str(path)

    # Which providers run

    def test_off_without_any_key(self):
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"], keys=())
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("SECOND OPINION: OFF"), out)
        self.assertEqual(self.google.sent + self.openai.sent + self.deepseek.sent, [])

    def test_both_families_review_the_same_packet(self):
        path = self.file("timer.ts", "export const limit = 100;\n")
        code, out = self.run_main(["--kind", "design", "--brief", "DD-007 WS-1: exam timer", "--file", path])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION (Google g-model", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)
        self.assertIn("[major] a.ts:3", out)
        packet = self.google.sent[0]["packet"]
        self.assertEqual(packet, self.openai.sent[0]["packet"])
        self.assertIn("DD-007 WS-1: exam timer", packet)
        self.assertIn("export const limit = 100;", packet)
        self.assertIn("Review checklists", packet)  # the company's rubric travels with the packet
        self.assertEqual(self.google.sent[0]["api_key"], "key-for-GEMINI_API_KEY")

    def test_missing_key_reports_that_provider_off(self):
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"], keys=("OPENAI_API_KEY",))
        self.assertIn("SECOND OPINION (Google): OFF", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)
        self.assertEqual(self.google.sent, [])

    def test_gemini_failure_falls_back_to_deepseek(self):
        self.google.error = RuntimeError("RESOURCE_EXHAUSTED: quota")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)
        self.assertIn("SECOND OPINION (DeepSeek d-model, fallback for Google", out)
        self.assertEqual(self.deepseek.sent[0]["packet"], self.google.sent[0]["packet"])

    def test_working_gemini_means_no_deepseek(self):
        self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertEqual(self.deepseek.sent, [])

    def test_no_gemini_key_uses_deepseek(self):
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"], keys=("OPENAI_API_KEY", "DEEPSEEK_API_KEY"))
        self.assertIn("SECOND OPINION (Google): OFF", out)
        self.assertIn("SECOND OPINION (DeepSeek d-model, fallback for Google", out)

    def test_no_deepseek_key_leaves_gemini_unavailable(self):
        self.google.error = RuntimeError("RESOURCE_EXHAUSTED: quota")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"], keys=("GEMINI_API_KEY", "OPENAI_API_KEY"))
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)
        self.assertIn("SECOND OPINION (DeepSeek): OFF", out)
        self.assertEqual(self.deepseek.sent, [])

    def test_model_env_override_skips_listing(self):
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"], extra_env={"SECOND_OPINION_GEMINI_MODEL": "pinned-model"})
        self.assertEqual(self.google.listed, 0)
        self.assertEqual(self.google.sent[0]["model"], "pinned-model")

    def test_one_provider_failing_doesnt_stop_the_other(self):
        self.google.error = RuntimeError("quota exceeded")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)
        self.assertIn("quota exceeded", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)

    def test_http_error_shows_the_providers_reason(self):
        import urllib.error
        body = b'{"error": {"status": "RESOURCE_EXHAUSTED", "message": "You exceeded your current quota, please check your plan."}}'
        self.google.error = urllib.error.HTTPError("https://example.invalid", 429, "Too Many Requests", {}, io.BytesIO(body))
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertIn("RESOURCE_EXHAUSTED", out)
        self.assertIn("You exceeded your current quota", out)

    def test_model_listing_failure_is_unavailable(self):
        self.openai.list_error = RuntimeError("401 bad key")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertIn("SECOND OPINION (OpenAI): UNAVAILABLE", out)
        self.assertIn("401 bad key", out)

    def test_no_suitable_model_is_unavailable(self):
        self.google.models = []
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE", out)

    # Output cap and call log

    def test_each_answered_call_logs_its_usage(self):
        path = self.file("timer.ts", "export const limit = 100;\n")
        self.run_main(["--kind", "design", "--brief", "DD-007", "--file", path])
        lines = self.logged()
        self.assertEqual([(l["provider"], l["model"]) for l in lines], [("Google", "g-model"), ("OpenAI", "o-model")])
        packet = self.google.sent[0]["packet"]
        for line in lines:
            self.assertEqual(set(line), {"id", "at", "provider", "model", "max_out_tokens", "answered", "in_tokens",
                                         "out_tokens", "thinking_tokens", "kind", "packet_bytes"})
            self.assertTrue(line["answered"])
            self.assertEqual((line["in_tokens"], line["out_tokens"], line["thinking_tokens"]), (1200, 900, 700))
            self.assertEqual(line["max_out_tokens"], second_opinion.MAX_OUT_TOKENS)
            self.assertEqual(line["kind"], "design")
            self.assertEqual(line["packet_bytes"], len(packet.encode("utf-8")))
            self.assertRegex(line["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")
        self.assertNotEqual(lines[0]["id"], lines[1]["id"])

    def test_failed_call_is_logged_unanswered(self):
        self.google.error = TimeoutError("timed out")
        self.run_main(["--kind", "code", "--brief", "T-1"])
        google, deepseek, openai = self.logged()
        self.assertEqual((google["provider"], google["answered"]), ("Google", False))
        self.assertEqual((google["in_tokens"], google["out_tokens"], google["thinking_tokens"]), (None, None, None))
        self.assertGreater(google["packet_bytes"], 0)
        self.assertEqual((deepseek["provider"], deepseek["answered"]), ("DeepSeek", True))
        self.assertEqual(openai["provider"], "OpenAI")

    def test_slots_that_never_send_arent_logged(self):
        self.openai.list_error = RuntimeError("401 bad key")
        self.google.models = []
        self.run_main(["--kind", "code", "--brief", "T-1"], keys=("GEMINI_API_KEY", "OPENAI_API_KEY"))
        self.assertEqual(self.logged(), [])

    def test_unwritable_log_still_returns_the_review(self):
        self.log.parent.write_text("a file where the log's directory should be")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION: CALL NOT LOGGED (Google g-model", out)
        self.assertIn("SECOND OPINION (OpenAI o-model", out)
        self.assertIn("[major] a.ts:3", out)

    def answers(self):
        folder = self.log.parent / "answers"
        return {p.stem: p.read_text() for p in folder.iterdir()} if folder.exists() else {}

    def test_each_answer_is_saved_by_its_call_id(self):
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        google, openai = self.logged()
        self.assertEqual(self.answers(), {google["id"]: self.google.reply, openai["id"]: self.openai.reply})
        self.assertIn(f"SECOND OPINION (Google g-model, another model family; call {google['id']}):", out)
        self.assertIn(f"SECOND OPINION (OpenAI o-model, another model family; call {openai['id']}):", out)

    def test_unanswered_calls_save_nothing(self):
        self.google.error = TimeoutError("timed out")
        self.deepseek.reply, self.deepseek.capped = "", True
        self.run_main(["--kind", "code", "--brief", "T-1"])
        google, deepseek, openai = self.logged()
        self.assertEqual(list(self.answers()), [openai["id"]])

    def test_cut_off_answer_is_saved_with_its_note(self):
        self.openai.capped = True
        self.run_main(["--kind", "code", "--brief", "T-1"])
        openai = self.logged()[-1]
        self.assertIn("Cut off at the output cap", self.answers()[openai["id"]])

    def test_unsavable_answer_still_returns_the_review(self):
        self.log.parent.mkdir(parents=True)
        (self.log.parent / "answers").write_text("a file where the answers' directory should be")
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertEqual(code, 0)
        self.assertIn("SECOND OPINION: ANSWER NOT SAVED (OpenAI o-model", out)
        self.assertIn("[major] a.ts:3", out)
        self.assertEqual(len(self.logged()), 2)

    def test_reply_cut_off_at_the_cap_says_so(self):
        self.openai.capped = True
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertIn("[major] a.ts:3", out)
        self.assertIn(f"Cut off at the output cap of {second_opinion.MAX_OUT_TOKENS:,} tokens", out)

    def test_empty_reply_at_the_cap_is_unavailable_and_falls_back(self):
        self.google.reply, self.google.capped = "", True
        code, out = self.run_main(["--kind", "code", "--brief", "T-1"])
        self.assertIn("SECOND OPINION (Google): UNAVAILABLE (g-model: stopped at the output cap", out)
        self.assertIn("SECOND OPINION (DeepSeek d-model, fallback for Google", out)
        self.assertEqual([l["answered"] for l in self.logged()], [True, True, True])  # the empty reply was billed

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
        packet = self.google.sent[0]["packet"]
        self.assertIn("print(2)", packet)
        self.assertNotIn("do-not-send-123", packet)
        self.assertNotIn("do-not-send-456", packet)


class ModelChoice(unittest.TestCase):
    """The default models, found in the key's model list; never guessed IDs."""

    def test_gemini_prefers_argon_when_listed(self):
        ids = ["gemini-3.8-flash", "gemini-4-argon-preview", "gemini-4-argon", "gemini-3.1-pro-preview"]
        self.assertEqual(choose_gemini(ids), "gemini-4-argon")

    def test_gemini_otherwise_uses_3_8_flash(self):
        ids = ["gemini-3.1-pro-preview", "gemini-3.8-flash-tts", "gemini-3.8-flash", "gemini-3.7-flash"]
        self.assertEqual(choose_gemini(ids), "gemini-3.8-flash")

    def test_gemini_none_when_neither_listed(self):
        self.assertIsNone(choose_gemini(["gemini-3.1-pro-preview", "gemini-3.7-flash"]))

    def test_openai_uses_6_1_sol(self):
        self.assertEqual(choose_openai(["gpt-6-astra", "gpt-6-sol", "gpt-6.1-sol"]), "gpt-6.1-sol")

    def test_openai_none_without_6_1_sol(self):
        self.assertIsNone(choose_openai(["gpt-6-astra", "gpt-6-sol"]))

    def test_deepseek_uses_flash(self):
        self.assertEqual(choose_deepseek(["deepseek-v4-pro", "deepseek-flash"]), "deepseek-flash")

    def test_deepseek_none_without_flash(self):
        self.assertIsNone(choose_deepseek(["deepseek-v4-pro"]))


class Requests(unittest.TestCase):
    """What each provider is sent, and how its reply's usage is read."""

    def post(self, response):
        captured = {}

        def fake_post(url, body, headers):
            captured["body"] = body
            return response

        return captured, mock.patch.object(second_opinion, "_post_json", fake_post)

    def test_cap_is_within_every_documented_maximum(self):
        self.assertLessEqual(second_opinion.MAX_OUT_TOKENS, 65_536)  # the smallest: Argon synchronous, Flash

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
            reply = second_opinion.gemini_send("packet", "instruction", "gemini-4-argon", "key")
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
                reply = second_opinion.gemini_send("packet", "instruction", "gemini-4-argon", "key")
            self.assertEqual((reply.in_tokens, reply.out_tokens, reply.thinking_tokens), expected, usage)

    def test_openai_and_deepseek_name_the_cap_their_own_way(self):
        response = {
            "choices": [{"message": {"content": "VERDICT: APPROVED"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5000, "completion_tokens": 2500, "completion_tokens_details": {"reasoning_tokens": 2000}},
        }
        for provider in second_opinion.default_providers():
            chat = provider if provider.label == "OpenAI" else provider.fallback
            field = {"OpenAI": "max_completion_tokens", "DeepSeek": "max_tokens"}[chat.label]
            captured, patch = self.post(response)
            with patch:
                reply = chat.send("packet", "instruction", "model", "key")
            self.assertEqual(captured["body"][field], second_opinion.MAX_OUT_TOKENS, chat.label)
            self.assertEqual(reply, Reply("VERDICT: APPROVED", 5000, 2500, 2000, False))

    def test_chat_stopped_at_the_cap(self):
        _, patch = self.post({"choices": [{"message": {"content": None}, "finish_reason": "length"}],
                              "usage": {"prompt_tokens": 5000, "completion_tokens": 65536}})
        with patch:
            reply = second_opinion.chat_send(second_opinion.OPENAI_API, "max_completion_tokens")("p", "i", "m", "k")
        self.assertEqual(reply, Reply("", 5000, 65536, None, True))


if __name__ == "__main__":
    unittest.main()
