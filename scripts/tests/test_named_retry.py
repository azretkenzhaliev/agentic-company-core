"""The rule "a refusal is final" keeps one retry: an agent may redo a blocked command once, in exactly the form the
block message names. Each file that states the rule says so, and that a permission prompt's refusal and the auto-mode
classifier's stay final."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / ".claude" / "agents"
STATED = [  # the files that state the rule in full
    AGENTS / "engineering" / "cto.md",
    AGENTS / "executive" / "platform-engineer.md",
    AGENTS / "executive" / "analyst.md",
    AGENTS / "executive" / "critic.md",
    AGENTS / "marketing" / "cmo.md",
    AGENTS / "marketing" / "content-producer.md",
    AGENTS / "marketing" / "content-reviewer.md",
    AGENTS / "marketing" / "performance-analyst.md",
]
POINTERS = [AGENTS / "engineering" / "senior-engineer.md", AGENTS / "engineering" / "staff-engineer.md"]


def rule(path: Path, marker: str = "") -> str:
    """The first bullet of path that starts with the rule and holds marker."""
    text = path.read_text(encoding="utf-8")
    return next(line for line in text.splitlines()
                if re.match(r"- (\*\*)?A permission refusal is final", line) and marker in line)


class NamedRetry(unittest.TestCase):
    def test_each_statement_keeps_the_named_form_retry_and_what_stays_final(self):
        for path in STATED:
            with self.subTest(path=path.relative_to(ROOT)):
                line = rule(path)
                self.assertIn("spells out the plain form it allows", line)
                self.assertIn("exactly that form", line)
                self.assertIn("A permission prompt's refusal and the auto-mode classifier's stay final", line)

    def test_the_engineers_pointers_count_it(self):
        for path in POINTERS:
            with self.subTest(path=path.relative_to(ROOT)):
                line = rule(path, "(`cto.md`, Working rules, with its")
                self.assertIn("with its three retries, one the form a block message spells out", line)
        # the shared Core, within build_cores' cap: its source, cto.md's Working rules, holds the rest
        line = rule(ROOT / "knowledge" / "engineering" / "cores" / "shared.md")
        # the named-form retry in full: once, final if refused, and a prompt's and the classifier's refusals stay final
        self.assertIn("Three retries only, once each, final if refused:", line)
        self.assertIn("; exactly the form a block message names.", line)
        self.assertIn("Every other hook's stop, a permission prompt's and the classifier's stay final.", line)
        self.assertIn("(WR \"A permission refusal is final\"", line)

    def test_the_four_agents_that_state_it_elsewhere_say_it_too(self):
        """Each says the one named-form retry where it states that a refusal is final."""
        for path in (AGENTS / "marketing" / "reel-analyst.md", AGENTS / "marketing" / "trend-researcher.md",
                     AGENTS / "engineering" / "code-reviewer.md", AGENTS / "engineering" / "ux-expert.md"):
            with self.subTest(path=path.relative_to(ROOT)):
                line = next(line for line in path.read_text(encoding="utf-8").splitlines()
                            if "refusal" in line and "final" in line and "spells out the plain form it allows" in line
                            and not line.startswith("- A permission refusal is final: stop that line"))  # not the Core
                self.assertIn("in exactly that form, nothing else changed", line)
                self.assertIn("never a variant, never a second retry, and a refusal of that form is final", line)
                self.assertIn("A permission prompt's refusal and the auto-mode classifier's stay final", line)

    def test_the_ceo_rules_no_redo_by_another_tool_form_or_agent(self):
        """A ruling may not let a refused change be made another way."""
        text = (AGENTS / "executive" / "ceo.md").read_text(encoding="utf-8")
        self.assertIn("A ruling that a refused command's change may be made by another tool, form or agent (the Edit "
                      "tool after a refused shell or heredoc edit, a fresh agent) first reads `cto.md`, Working rules, "
                      "and `platform-engineer.md`'s refusal rule: such a change is a variant and final, unless the "
                      "block message itself names that tool or form; a waiver is the Board's (b9).", text)

    def test_cto_md_names_the_worktree_checks_form(self):
        # Claude Code's worktree check refuses a compound command and names the plain form
        line = rule(AGENTS / "engineering" / "cto.md")
        self.assertIn("never a variant, never a second retry", line)
        self.assertIn("\"Split it into plain, separate commands and run them from <worktree>\"", line)
        self.assertIn("`<command> > <log> 2>&1; echo $? > <rc>`", line)


if __name__ == "__main__":
    unittest.main()
