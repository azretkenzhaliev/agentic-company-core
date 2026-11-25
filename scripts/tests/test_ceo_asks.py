"""The CEO asks the Board on the Asks page and by email (as plain text in the chat while the desk is off or its Notion
side isn't set up), never by an interactive question in the chat, which stops the session until it is answered, and a
declined chat question is not a stop."""

import unittest
from pathlib import Path

CEO = Path(__file__).resolve().parents[2] / ".claude" / "agents" / "executive" / "ceo.md"


def body() -> str:
    """ceo.md below its front matter (whose tools line isn't a use)."""
    return CEO.read_text(encoding="utf-8").split("\n---\n", 1)[1]


class Asks(unittest.TestCase):
    def test_no_ask_by_ask_user_question(self):
        named = [line for line in body().splitlines() if "AskUserQuestion" in line]
        self.assertTrue(named, "ceo.md says the Board gets no AskUserQuestion")
        for line in named:
            with self.subTest(line=line[:80]):
                self.assertIn("never AskUserQuestion to the Board", line)
        self.assertIn("never as an interactive question in the chat", body())
        self.assertIn("With the desk on and its Notion side set up, it goes only there and by email. While the desk is "
                      "off or its Notion side isn't set up, also quote it whole in the chat as plain text, where the "
                      "Board answers", body())

    def test_the_report_lists_the_asks_and_never_asks_them(self):
        needs = next(line for line in body().splitlines() if line.startswith("Needs you:"))
        self.assertIn("to answer on the Asks page, never here", needs)

    def test_the_batch_cap_binds_an_email_batch_and_no_batch_goes_in_the_chat(self):
        self.assertNotIn("one chat or email batch", body())
        self.assertIn("The cap binds what one email batch asks at once, not the Asks page; with the desk on and its "
                      "Notion side set up, no batch goes in the chat.", body())

    def test_a_declined_chat_question_is_not_a_stop(self):
        self.assertIn("A declined or rejected chat question is not a stop: read the answers ledger "
                      "(`knowledge/board/answers/`) and the Asks page for the Board's answer first, then go on with "
                      "every lane", body())


if __name__ == "__main__":
    unittest.main()
