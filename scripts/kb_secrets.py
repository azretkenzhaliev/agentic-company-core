"""Secret patterns shared by the KB write hook and the KB linter.

Patterns are deliberately precise: each matches a real credential format,
not prose that mentions one. Results carry the line and the kind of secret,
never the matched value, so callers can't leak it into logs.
"""

import re

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    ("GitHub token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-\d{6,}-[A-Za-z0-9-]{10,}")),
    ("Stripe live secret key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{24,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
]


def find_secrets(text: str) -> list[tuple[int, str]]:
    """Return (line number, kind) for each secret found in text."""
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                hits.append((line_no, kind))
    return hits
