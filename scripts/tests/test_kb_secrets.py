"""Tests for scripts/kb_secrets.py.

Fake secrets are assembled at runtime so no literal token appears in this
file (keeps secret scanners and push protection quiet).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb_secrets import find_secrets  # noqa: E402

A36 = "a1B2c3D4e5" * 3 + "f6G7h8"  # 36 alphanumerics


def fake(*parts: str) -> str:
    return "".join(parts)


class FindsEachSecretKind(unittest.TestCase):
    def assert_kind(self, text: str, kind_fragment: str) -> None:
        hits = find_secrets(text)
        self.assertEqual(len(hits), 1, f"expected one hit, got {hits}")
        self.assertIn(kind_fragment, hits[0][1])

    def test_rsa_private_key_block(self):
        self.assert_kind(fake("-----BEGIN RSA ", "PRIVATE KEY-----\nMIIE...\n"), "private key")

    def test_plain_private_key_block(self):
        self.assert_kind(fake("-----BEGIN ", "PRIVATE KEY-----"), "private key")

    def test_openssh_private_key_block(self):
        self.assert_kind(fake("-----BEGIN OPENSSH ", "PRIVATE KEY-----"), "private key")

    def test_pgp_private_key_block(self):
        self.assert_kind(fake("-----BEGIN PGP ", "PRIVATE KEY BLOCK-----"), "private key")

    def test_anthropic_key(self):
        self.assert_kind(fake("key: sk-", "ant-api03-", "x" * 40), "Anthropic")

    def test_openai_project_key(self):
        self.assert_kind(fake("sk-", "proj-", "Ab1" * 10), "OpenAI")

    def test_github_classic_token(self):
        self.assert_kind(fake("token gh", "p_", A36), "GitHub")

    def test_github_oauth_token(self):
        self.assert_kind(fake("gh", "o_", A36), "GitHub")

    def test_github_fine_grained_token(self):
        self.assert_kind(fake("github", "_pat_", "11ABCDEFG0" * 2, "AB_", "x1" * 30), "GitHub")

    def test_aws_access_key_id(self):
        self.assert_kind(fake("AKI", "A", "Z2QX7W3MN4PL8KJ5"), "AWS")

    def test_slack_bot_token(self):
        self.assert_kind(fake("xox", "b-", "123456789012-1234567890123-", "AbCdEfGhIjKlMnOpQrStUvWx"), "Slack")

    def test_stripe_live_secret_key(self):
        self.assert_kind(fake("sk", "_live_", "51H" + "a" * 30), "Stripe")

    def test_google_api_key(self):
        self.assert_kind(fake("AI", "za", "SyA-" + "b" * 31), "Google")


class IgnoresLookalikes(unittest.TestCase):
    def assert_clean(self, text: str) -> None:
        self.assertEqual(find_secrets(text), [])

    def test_public_key_block(self):
        self.assert_clean("-----BEGIN PUBLIC KEY-----")

    def test_prose_mentioning_key_prefixes(self):
        self.assert_clean("Anthropic keys start with sk-ant- and GitHub tokens with ghp_ or github_pat_.")

    def test_short_github_like_word(self):
        self.assert_clean("ghp_short")

    def test_word_containing_sk_ant(self):
        self.assert_clean("the risk-ant-colony-model-of-everything-here is fine")

    def test_slack_placeholder(self):
        self.assert_clean("Set SLACK_TOKEN to xoxb-your-token-here")

    def test_aws_like_lowercase(self):
        self.assert_clean("akiaz2qx7w3mn4pl8kj5")

    def test_env_var_names(self):
        self.assert_clean("Vercel env var `DATABASE_URL`; `STRIPE_SECRET_KEY` lives in the dashboard.")

    def test_stripe_test_key_is_not_live(self):
        self.assert_clean(fake("sk", "_test_", "a" * 30))


class ReportsLinesNotValues(unittest.TestCase):
    def test_line_numbers_are_one_based(self):
        text = "line one\nline two\n" + fake("gh", "p_", A36) + "\n"
        self.assertEqual(find_secrets(text), [(3, "GitHub token")])

    def test_result_never_contains_the_secret(self):
        token = fake("gh", "p_", A36)
        hits = find_secrets(token)
        self.assertNotIn(token, repr(hits))


if __name__ == "__main__":
    unittest.main()
