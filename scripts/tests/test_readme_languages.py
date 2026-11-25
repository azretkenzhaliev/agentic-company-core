"""README.md says the same thing in five languages: the same order of sections, the same headings, the same numbered
steps and byte-identical code blocks with no comments, so a fix in one language that misses the others fails here."""

import re
import unittest
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"
IDS = ["ru", "ky", "uz", "kk", "en"]
SECTION = re.compile(r'^<a id="([a-z]+)"></a>\n\n## (.+)\n', re.M)
FENCE = re.compile(r"^( *)```([a-z]*)\n(.*?)^\1```$", re.M | re.S)


def sections(text: str) -> list:
    """[(id, name, body)], in the page's order."""
    found = list(SECTION.finditer(text))
    ends = [m.start() for m in found[1:]] + [len(text)]
    return [(m.group(1), m.group(2), text[m.end():end]) for m, end in zip(found, ends)]


def blocks(body: str) -> list:
    return [m.group(0) for m in FENCE.finditer(body)]


def prose(body: str) -> str:
    return FENCE.sub("", body)


class ReadmeLanguages(unittest.TestCase):
    def setUp(self):
        self.text = README.read_text(encoding="utf-8")
        self.sections = sections(self.text)

    def test_five_sections_in_this_order_and_no_other(self):
        self.assertEqual([id_ for id_, _, _ in self.sections], IDS)
        self.assertEqual(self.sections[-1][1], "English")
        self.assertEqual(len(re.findall(r"^## ", prose(self.text), re.M)), len(IDS))

    def test_the_line_of_links_names_them(self):
        links = re.findall(r"\[([^]]+)\]\(#([a-z]+)\)", self.text[:self.text.index("<a id=")])
        self.assertEqual(links, [(name, id_) for id_, name, _ in self.sections])

    def test_the_same_headings_and_steps(self):
        def shape(body):
            return re.findall(r"^(#{3,6} |\d+\. )", prose(body), re.M)
        english = shape(self.sections[-1][2])
        self.assertGreater(len(english), 50)
        for id_, _, body in self.sections:
            with self.subTest(language=id_):
                self.assertEqual(shape(body), english)

    def test_what_is_on_by_default_is_near_the_start_in_every_language(self):
        def parts(body):
            return re.split(r"^### ", prose(body), flags=re.M)[1:]
        english = parts(self.sections[-1][2])
        self.assertEqual([part.split("\n", 1)[0] for part in english[:4]],
                         ["What this is", "What you need", "What is on by default", "Install"])
        items = re.compile(r"^(\d+)\. \*\*.+\*\*.*$", re.M)
        for id_, _, body in self.sections:
            with self.subTest(language=id_):  # each item: what is on, in bold, and how to switch it off (the same words in each)
                self.assertEqual(items.findall(parts(body)[2]), [str(n) for n in range(1, 15)])
                labels = [set(re.findall(r"\. ([^.:*]+):", m.group(0))) for m in items.finditer(parts(body)[2])]
                self.assertEqual(len(set.intersection(*labels)), 1)
                self.assertEqual(parts(body)[2].count("CEO"), english[2].count("CEO"))
                for other in ("OpenAI", "Google", "Neon", "Instagram", "`/onboard-company`", "`.env`"):
                    self.assertEqual(parts(body)[2].count(other), english[2].count(other))
        guide = (README.parent / "docs" / "guide.md").read_text(encoding="utf-8")
        steps = re.compile(r"^\d+\. .+$", re.M)
        self.assertEqual(steps.findall(guide.split("## What is on by default\n")[1].split("\n## ")[0]),
                         steps.findall(english[2]))
        skill = (README.parent / ".claude" / "skills" / "onboard-company" / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^\| (\d+) \| \*\*", skill, re.M), [str(n) for n in range(1, 15)])

    def test_the_code_blocks_are_byte_identical(self):
        english = blocks(self.sections[-1][2])
        self.assertGreater(len(english), 20)
        for id_, _, body in self.sections:
            with self.subTest(language=id_):
                self.assertEqual(blocks(body), english)

    def test_no_comments_in_the_code_blocks(self):
        for block in blocks(self.text):
            for line in block.splitlines():
                with self.subTest(line=line):
                    self.assertIsNone(re.search(r"(^|\s)#", line))

    def test_the_same_links_out(self):
        def links(body):
            return sorted(re.findall(r"\]\(([^)]+)\)", prose(body)))
        for id_, _, body in self.sections:
            with self.subTest(language=id_):
                self.assertEqual(links(body), links(self.sections[-1][2]))

    def test_each_section_ends_with_the_line_on_which_language_decides(self):
        for id_, _, body in self.sections:
            with self.subTest(language=id_):  # a paragraph of its own, not a step or a fence
                self.assertRegex(body.strip(), r"\n\n[^\W\d][^\n]*\.\Z")
        self.assertTrue(self.text.strip().endswith("If the texts in different languages differ, this English one decides."))

    def test_the_same_commands_inside_the_sentences(self):
        def spans(body):
            return sorted(re.findall(r"`([^`\n]+)`", prose(body)))
        for id_, _, body in self.sections:
            with self.subTest(language=id_):
                self.assertEqual(spans(body), spans(self.sections[-1][2]))

    def test_a_changed_block_is_seen(self):
        changed = self.text.replace("   claude doctor\n", "   claude check\n", 1)
        self.assertNotEqual(blocks(sections(changed)[0][2]), blocks(sections(changed)[-1][2]))


if __name__ == "__main__":
    unittest.main()
