"""Every agent's `model:` is on SA-002's list for its role.

SA-002's usage discipline (knowledge/board/standing-authorizations.md): "Opus for design review, the critic, the
platform engineer, the CEO, the CTO, Staff engineers, the CMO, the content reviewer, the UX expert, the analyst and
reviews of sensitive code; Sonnet for everything else". The Opus agents take `opus[1m]` and compact at 300k. The
code-reviewer stays on Sonnet in its file: a review of sensitive code gets Opus by the spawn's `model: opus`, since the
Agent tool's override takes no [1m]. Every agent thinks at `xhigh`. A company on a smaller plan changes SA-002, the
agent files and this test together."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / ".claude" / "agents"
SA = ROOT / "knowledge" / "board" / "standing-authorizations.md"
SA_002 = ("Opus for design review, the critic, the platform engineer, the CEO, the CTO, Staff engineers, the CMO, the "
          "content reviewer, the UX expert, the analyst and reviews of sensitive code; Sonnet for everything else")
ON_OPUS = {"opus", "opus[1m]"}
OPUS = {"ceo": {"inherit"} | ON_OPUS, **{name: ON_OPUS for name in (
    "critic", "platform-engineer", "design-reviewer", "cto", "staff-engineer", "cmo", "content-reviewer", "ux-expert",
    "analyst")}}


def frontmatter(path):
    found = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    return dict(re.findall(r"^([A-Za-z-]+): *(.*?) *$", found.group(1), re.M)) if found else {}


class AgentModels(unittest.TestCase):
    def test_sa_002_still_says_this(self):
        """If the Board changes SA-002, this list changes with it."""
        text = SA.read_text(encoding="utf-8")
        self.assertIn(SA_002, text)

    def test_every_agent_is_on_its_sa_002_model(self):
        files = sorted(AGENTS.rglob("*.md"))
        self.assertGreater(len(files), 10)
        names = set()
        for path in files:
            fields = frontmatter(path)
            with self.subTest(agent=path.name):
                self.assertIn("name", fields)
                self.assertIn("model", fields)  # no model means the session's, which may be Opus
                self.assertIn(fields["model"], OPUS.get(fields["name"], {"sonnet"}))
                names.add(fields["name"])
        self.assertLessEqual(set(OPUS), names)  # a renamed Opus role fails here, not silently

    def test_every_agent_thinks_xhigh(self):
        """No `effort` means the session's level, which may be lower; a new agent without the line fails here."""
        files = sorted(AGENTS.rglob("*.md"))
        self.assertGreater(len(files), 10)
        for path in files:
            with self.subTest(agent=path.name):
                self.assertEqual(frontmatter(path).get("effort"), "xhigh")

    def test_every_opus_agent_compacts_at_300k(self):
        """Opus runs with a 1M window; an agent that compacts at 100-150k gets nothing from it."""
        opus = [p for p in sorted(AGENTS.rglob("*.md")) if frontmatter(p).get("model") in ON_OPUS]
        self.assertGreaterEqual(len(opus), 9)
        for path in opus:
            with self.subTest(agent=path.name):
                self.assertEqual(frontmatter(path).get("autoCompactWindow"), "300000")

    def test_the_senior_compacts_at_200k(self):
        """At 100000 a Senior compacts at about two thirds of it and may die of autocompact thrash."""
        path = AGENTS / "engineering" / "senior-engineer.md"
        self.assertEqual(frontmatter(path).get("autoCompactWindow"), "200000")

    def test_the_code_reviewer_compacts_at_350k(self):
        """At 100000 most reviews compact, some several times. At 350000 a reviewer compacts at about 280k of context,
        which most reviews stay under; a higher number changed nothing."""
        path = AGENTS / "engineering" / "code-reviewer.md"
        self.assertEqual(frontmatter(path).get("autoCompactWindow"), "350000")

    def test_the_senior_doesnt_call_a_shared_run_failure_a_flake(self):
        """A Senior may call its own regression a flake (lessons learned, "Tests")."""
        text = (AGENTS / "engineering" / "senior-engineer.md").read_text(encoding="utf-8")
        self.assertIn("**A file that fails in the shared run and passes alone is the diff's, not a flake, until the "
                      "same command passes on the base commit**; the report names that base run", text)

    def test_the_forms_it_catches(self):
        for name, model, ok in (("ux-expert", "opus[1m]", True), ("cmo", "opus", True), ("cto", "opus[1m]", True),
                                ("code-reviewer", "opus", False), ("code-reviewer", "opus[1m]", False),
                                ("senior-engineer", "opus[1m]", False), ("cmo", "inherit", False),
                                ("critic", "opus[1m]", True), ("ceo", "inherit", True), ("analyst", "sonnet", False),
                                ("content-producer", "sonnet", True), ("critic", "sonnet", False),
                                ("cto", "sonnet[1m]", False)):
            self.assertEqual(model in OPUS.get(name, {"sonnet"}), ok, (name, model))


class ModelChangeArrivesAfterMinutes(unittest.TestCase):
    """A changed `model` or `effort` reaches a running session only after some minutes, even partway through a run.
    So the CEO checks one new spawn's transcript for both fields, and asks for a restart only if they haven't
    arrived."""

    def step_6(self):
        text = (AGENTS / "executive" / "ceo.md").read_text(encoding="utf-8")
        section = text.split("## System changes", 1)[1].split("\n## ", 1)[0]
        return re.search(r"^6\. \*\*Restart:\*\*.*$", section, re.M).group(0)

    def test_step_6_says_the_change_arrives_after_minutes(self):
        step = self.step_6()
        for words in ("`model` or `effort`", "only after some minutes, even partway through a run",
                      "the Agent tool's `model` override", "only if the new values haven't arrived in about 15 minutes"):
            self.assertIn(words, step)
        self.assertNotIn("doesn't reach agents spawned", step)

    def test_step_6_names_the_transcript_check(self):
        """The check covers both fields: `model` alone misses an effort change."""
        self.assertIn("""`grep -o '"model":"[^"]*"\\|"effort":"[^"]*"' <output-file> | sort | uniq -c`""", self.step_6())


if __name__ == "__main__":
    unittest.main()
