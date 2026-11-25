"""Caption numbers: length, lines, emoji, hashtags, mentions, links, and the language.

Standard library only. Language is a rule on letters and common words, not a model, over company.json's languages
("integrations"."marketing"."languages"): each language's "letters" are the ones only it has among them, its "words" a
few of its most common. A short text says nothing (None), and so does a company that names no languages.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from company_config import integration  # noqa: E402

FLAG = "[\U0001F1E6-\U0001F1FF]{2}"
KEYCAP = "[0-9#*]️?⃣"
PICTO = "[\U0001F000-\U0001FAFF☀-➿⬅-⭕⌚⌛⏩-⏺]"
TEXTY = "[©®‼⁉™ℹ↔-↙↩↪Ⓜ▪-◾〰〽㊗㊙]️"
MODIFIER = "[\U0001F3FB-\U0001F3FF]?️?[\U000E0020-\U000E007F]*"
ONE = f"(?:{PICTO}|{TEXTY}){MODIFIER}"
EMOJI = re.compile(f"{FLAG}|{KEYCAP}|{ONE}(?:‍{ONE})*")
HASHTAG = re.compile(r"(?<![\w#])#\w+")
MENTION = re.compile(r"(?<![\w@])@[\w.]+")
URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.I)
WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")

MIN_LETTERS = 10


def letters(text: str) -> list:
    return [char for char in text if char.isalpha()]


def latin_share(text: str) -> float | None:
    found = letters(text)
    return round(sum(char.isascii() for char in found) / len(found), 4) if found else None


def known_languages(root: Path = ROOT) -> dict:
    """{code: (its own letters, its common words)} for company.json's languages that name any."""
    found = (integration("marketing", root) or {}).get("languages") or {}
    return {code: (set(language.get("letters") or ""), set(language.get("words") or []))
            for code, language in found.items() if language.get("letters") or language.get("words")}


def language_of(text: str) -> str | None:
    """A language's code, mixed, unknown (none of the languages' marks), or None under MIN_LETTERS letters."""
    known = known_languages()
    if not known or len(letters(text)) < MIN_LETTERS:
        return None
    words = [word.lower() for word in WORD.findall(text)]
    scores = {code: sum(word in common for word in words) + sum(any(char in own for char in word) for word in words)
              for code, (own, common) in known.items()}
    best = max(scores, key=scores.get)
    if not scores[best]:
        return "unknown"
    return best if all(scores[best] >= 2 * score for code, score in scores.items() if code != best) else "mixed"


def features(text: str | None) -> dict:
    if text is None:
        return {"status": "none"}
    lines = text.splitlines()
    first = next((line for line in lines if line.strip()), "")
    return {
        "status": "ok",
        "chars": len(text),
        "words": len(WORD.findall(text)),
        "lines": len(lines),
        "first_line_chars": len(first.strip()),
        "emoji": len(EMOJI.findall(text)),
        "hashtags": len(HASHTAG.findall(text)),
        "mentions": len(MENTION.findall(text)),
        "links": len(URL.findall(text)),
        "latin_share": latin_share(text),
        "language": language_of(text),
    }
