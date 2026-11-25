"""Tests for scripts/hooks/board_email.py: the CEO's email to the Board."""

import fcntl
import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import board_email  # noqa: E402

SEND = "mcp__claude_ai_Gmail__send_message"
BOARD = "board@example.com"


def email(**changes):
    tool_input = {"to": [BOARD], "subject": "[CEO] Q-7: its best time is now",
                  "body": "Needed: Q-7. Recommended: yes. Open the CEO session."}
    tool_input.update(changes)
    return tool_input


def event(tool_input, agent_type="ceo", agent_id=None, tool_name=SEND):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    if agent_type:
        payload["agent_type"] = agent_type
    if agent_id:
        payload["agent_id"] = agent_id
    return payload


class BoardEmail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".git").mkdir()  # a main checkout
        self.company({"board_email": BOARD})
        self.log = self.root / "workspaces" / "system" / "notify-log.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def company(self, settings, root=None):
        ((root or self.root) / "company.json").write_text(settings if isinstance(settings, str) else json.dumps(settings))

    def reason(self, payload):
        return board_email.email_reason(payload, self.root)

    def logged(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def write_log(self, day, count, log=None):
        log = log or self.log
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as handle:
            for n in range(count):
                handle.write(json.dumps({"time": f"{day}T0{n}:00:00Z", "subject": f"[CEO] {n}"}) + "\n")

    def assertRefused(self, payload, why):
        self.assertIn(why, self.reason(payload) or "allowed")

    def test_the_ceo_main_session_emails_the_board(self):
        self.assertIsNone(self.reason(event(email())))
        [entry] = self.logged()
        self.assertEqual(set(entry), {"time", "subject"})  # time and subject, never the body
        self.assertEqual(entry["subject"], "[CEO] Q-7: its best time is now")
        self.assertTrue(entry["time"].startswith(datetime.now(timezone.utc).strftime("%Y-%m-%d")))

    def test_a_body_of_4000_characters_passes_and_no_body_passes(self):
        self.assertIsNone(self.reason(event(email(body="x" * 4000))))
        no_body = email()
        del no_body["body"]
        self.assertIsNone(self.reason(event(no_body)))

    def test_another_recipient_is_refused(self):
        for to in (["someone@example.com"], [BOARD, "someone@example.com"], ["someone@example.com", BOARD],
                   [f"The Board <{BOARD}>"], [BOARD.upper()], BOARD, [], None):
            with self.subTest(to=to):
                self.assertRefused(event(email(to=to)), "must be exactly")

    def test_cc_bcc_and_attachments_are_refused(self):
        for key, value in (("cc", [BOARD]), ("cc", ["someone@example.com"]), ("cc", []),
                           ("bcc", ["someone@example.com"]), ("bcc", [BOARD]),
                           ("attachments", [{"filename": "a.txt", "content": "aGk="}])):
            with self.subTest(key=key, value=value):
                self.assertRefused(event(email(**{key: value})), f"not {key}")

    def test_html_drafts_threads_and_unknown_keys_are_refused(self):
        for key in ("htmlBody", "draftId", "replyThreadId", "replyToMessageId", "from", "some_future_field"):
            with self.subTest(key=key):
                self.assertRefused(event(email(**{key: "x"})), f"not {key}")

    def test_a_subject_without_the_prefix_is_refused(self):
        for subject in ("Q-7: its best time is now", " [CEO] Q-7", "[ceo] Q-7", "CEO: Q-7", "", None,
                        "[CEO] Q-7\nBcc: someone@example.com", "[CEO] Q-7\r"):
            with self.subTest(subject=subject):
                self.assertRefused(event(email(subject=subject)), 'starting "[CEO]"')

    def test_a_subject_over_200_characters_or_with_a_control_character_is_refused(self):
        self.assertIsNone(self.reason(event(email(subject="[CEO] " + "x" * 194))))  # 200 characters
        self.assertRefused(event(email(subject="[CEO] " + "x" * 195)), "at most 200 characters")
        for char in ("\t", "\x00", "\x1b", "\x1f", "\x7f", "\x80", "\x85", "\x9f", "\u2028", "\u2029"):
            with self.subTest(char=repr(char)):
                self.assertRefused(event(email(subject=f"[CEO] Q-7{char}x")), "one line")
        self.assertIsNone(self.reason(event(email(subject="[CEO] Q-7\xa0x"))))  # U+00A0, just past the range

    def test_a_long_or_non_text_body_is_refused(self):
        for body in ("x" * 4001, ["a list"], {"html": "x"}):
            with self.subTest(body=str(body)[:20]):
                self.assertRefused(event(email(body=body)), "at most 4,000")

    def test_a_secret_in_the_body_or_subject_is_refused(self):
        key = "AKIA" + "ABCDEFGHIJKLMNOP"  # built here so this file holds no key-shaped string
        self.assertRefused(event(email(body=f"the key is {key}")), "holds a secret")
        self.assertRefused(event(email(subject=f"[CEO] {key}")), "holds a secret")

    def test_a_subagent_or_another_caller_is_refused(self):
        callers = [("ceo", "a1234567890abcdef"), ("analyst", None), ("cmo", None), ("cto", None),
                   ("platform-engineer", None), ("analyst", "a1234567890abcdef"), (None, None)]
        for agent_type, agent_id in callers:
            with self.subTest(agent_type=agent_type, agent_id=agent_id):
                self.assertRefused(event(email(), agent_type, agent_id), "only the CEO's main session")

    def test_only_the_claude_ai_connectors_send_message(self):
        for tool_name in ("mcp__plugin_small-business_gmail__send_message", "mcp__claude_ai_Gmail__reply",
                          "mcp__claude_ai_Gmail__create_draft", "mcp__claude_ai_Gmail__send_draft"):
            with self.subTest(tool_name=tool_name):
                self.assertRefused(event(email(), tool_name=tool_name), f"only {SEND}")

    def test_there_is_no_daily_cap_until_the_founder_sets_one(self):
        self.write_log(datetime.now(timezone.utc).strftime("%Y-%m-%d"), 9)
        for settings in ({}, {"integrations": {"email": {}}}, {"integrations": {"email": {"per_day": None}}}):
            self.company({"board_email": BOARD, **settings})
            for n in range(5):
                self.assertIsNone(self.reason(event(email(subject=f"[CEO] {n}"))))

    def test_past_the_founders_cap_an_email_is_refused(self):
        self.company({"board_email": BOARD, "integrations": {"email": {"per_day": 6}}})
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.write_log(today, 5)
        self.assertIsNone(self.reason(event(email())))
        self.assertRefused(event(email()), "6 emails to the Board already today")
        self.assertEqual(len(self.logged()), 6)  # the refused one isn't logged

    def test_yesterdays_emails_dont_count(self):
        self.company({"board_email": BOARD, "integrations": {"email": {"per_day": 6}}})
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        self.write_log(yesterday, 6)
        self.assertIsNone(self.reason(event(email())))

    def test_a_cap_that_isnt_a_whole_number_refuses(self):
        for bad in ("6", 1.5, True, [], {}):
            with self.subTest(per_day=bad):
                self.company({"board_email": BOARD, "integrations": {"email": {"per_day": bad}}})
                self.assertRefused(event(email()), "must be a whole number")

    def test_without_an_address_every_email_is_refused(self):
        for settings in ({}, {"board_email": ""}, {"board_email": None}, {"board_email": [BOARD]}):
            for to in ([BOARD], [""], [], [None], None):
                with self.subTest(settings=settings, to=to):
                    self.company(settings)
                    self.assertRefused(event(email(to=to)), "names no board_email")
        (self.root / "company.json").unlink()
        self.assertRefused(event(email()), "names no board_email")
        self.assertEqual(self.logged(), [])

    def test_a_broken_company_json_raises_so_the_guard_fails_closed(self):
        for broken in ("not json", "[]", "5", '{"integrations": [], "board_email": "board@example.com"}',
                       '{"integrations": {"email": []}, "board_email": "board@example.com"}'):
            with self.subTest(broken=broken):
                self.company(broken)
                with self.assertRaises((ValueError, TypeError, AttributeError)):
                    self.reason(event(email()))
        self.assertEqual(self.logged(), [])

    def test_an_unreadable_log_under_a_cap_raises_so_the_guard_fails_closed(self):
        self.company({"board_email": BOARD, "integrations": {"email": {"per_day": 6}}})
        self.log.parent.mkdir(parents=True)
        self.log.write_text("not json\n")
        with self.assertRaises(ValueError):
            self.reason(event(email()))

    def test_log_lines_of_the_wrong_shape_under_a_cap_raise_so_the_guard_fails_closed(self):
        self.company({"board_email": BOARD, "integrations": {"email": {"per_day": 6}}})
        self.log.parent.mkdir(parents=True)
        for line in ("[]", "5", '"x"', "{}", '{"time": 5}', '{"time": null}', '{"subject": "[CEO] x"}'):
            with self.subTest(line=line):
                self.log.write_text(line + "\n")
                with self.assertRaises((TypeError, KeyError, AttributeError)):
                    self.reason(event(email()))

    def test_a_refused_email_isnt_logged(self):
        self.assertIsNotNone(self.reason(event(email(cc=[BOARD]))))
        self.assertIsNotNone(self.reason(event(email(), "ceo", "a1234567890abcdef")))
        self.assertEqual(self.logged(), [])

    def test_a_non_object_input_is_refused(self):
        for tool_input in (None, "to the Board", ["to"], 5):
            with self.subTest(tool_input=tool_input):
                self.assertRefused(event(tool_input), "isn't an object")
        self.assertEqual(self.logged(), [])

    def test_a_send_waits_for_the_log_lock(self):
        self.log.parent.mkdir(parents=True)
        results = []
        with self.log.open("a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            worker = threading.Thread(target=lambda: results.append(self.reason(event(email()))))
            worker.start()
            worker.join(timeout=0.5)
            self.assertTrue(worker.is_alive(), "the send didn't wait for the lock")
            self.assertEqual(self.log.read_text(), "")
            fcntl.flock(held, fcntl.LOCK_UN)
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results, [None])
        self.assertEqual(len(self.logged()), 1)

    def linked_worktree(self, pointer="gitdir: {gitdir}\n", commondir="../..\n"):
        """main/ and worktree/, as `git worktree add` lays them out, with this .git text and commondir."""
        main, worktree = self.root / "main", self.root / "worktree"
        gitdir = main / ".git" / "worktrees" / "worktree"
        gitdir.mkdir(parents=True)
        (gitdir / "commondir").write_text(commondir)
        worktree.mkdir()
        for checkout in (main, worktree):
            self.company({"board_email": BOARD, "integrations": {"email": {"per_day": 6}}}, checkout)
        (worktree / ".git").write_text(pointer.format(gitdir=gitdir))
        return main, worktree

    def test_every_checkout_counts_in_the_main_checkouts_log(self):
        main, worktree = self.linked_worktree()
        main_log = main / "workspaces" / "system" / "notify-log.jsonl"
        self.assertIsNone(board_email.email_reason(event(email()), worktree))
        self.assertIsNone(board_email.email_reason(event(email()), main))
        self.assertEqual(len(main_log.read_text().splitlines()), 2)
        self.assertFalse((worktree / "workspaces").exists())
        self.write_log(datetime.now(timezone.utc).strftime("%Y-%m-%d"), 4, main_log)
        for checkout in (worktree, main):
            with self.subTest(checkout=checkout.name):
                self.assertIn("6 emails to the Board already today",
                              board_email.email_reason(event(email()), checkout) or "allowed")

    def test_a_relative_gitdir_finds_the_main_checkouts_log(self):
        main, worktree = self.linked_worktree(pointer="gitdir: ../main/.git/worktrees/worktree\n")
        self.assertIsNone(board_email.email_reason(event(email()), worktree))
        self.assertEqual(len((main / "workspaces" / "system" / "notify-log.jsonl").read_text().splitlines()), 1)
        self.assertFalse((worktree / "workspaces").exists())

    def test_a_pointer_without_the_gitdir_prefix_raises_so_the_guard_fails_closed(self):
        main, worktree = self.linked_worktree(pointer="{gitdir}\n")  # a real gitdir, but not git's form
        with self.assertRaises(ValueError):
            board_email.email_reason(event(email()), worktree)
        self.assertFalse((main / "workspaces").exists())

    def test_an_empty_commondir_raises_so_the_guard_fails_closed(self):
        main, worktree = self.linked_worktree(commondir="\n")
        with self.assertRaises(ValueError):
            board_email.email_reason(event(email()), worktree)
        self.assertEqual(list(self.root.rglob("notify-log.jsonl")), [])  # not even in .git/worktrees/

    def test_outside_a_git_checkout_it_raises_so_the_guard_fails_closed(self):
        (self.root / ".git").rmdir()
        with self.assertRaises(OSError):
            self.reason(event(email()))
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
