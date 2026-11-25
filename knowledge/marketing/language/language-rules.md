---
title: Language rules and glossary
owner: cmo
status: draft
updated: 2026-01-01
related: [README.md, captions-and-ctas.md, red-lines.md]
---

# Language rules and glossary

## Our decision

- TODO(board): which language or languages each account posts in, which comes first, what the founder speaks on camera, and which language its subtitles are in. The brand book holds the answer per account.
- **The default caption layout:** the first language's block, then a full block in the second. "Full" means the same content, not a summary. A brand book may change the order or drop a language.
- **Ads and paid placements:** the languages your market's law asks for ([red-lines.md](red-lines.md)).
- **Literary norm or spoken:** ad text follows the literary norm; the founder's own posts follow his voice.
- **Slang:** none of ours. Slang and catchphrases appear only where his raw material uses them; agents never add them.

## Who uses which language

Fill from the analyst's note: what creators, brands and institutions in your market post in, with examples and a confidence (H, M, L). Observed, not prescribed.

| Situation | Language seen | Examples | Conf. |
|---|---|---|---|

## Mixing two languages

Fill from the analyst's note: how people mix them, and what reads as mockery. Mocking how anyone speaks is a one-line `Board note:` on the founder's pages; other brands never do it ([red-lines.md](red-lines.md), row 16).

## Brand names and loan words

How a brand name, a trademark or a loan word is written and takes endings in the second language, with real examples and their source.

| Seen | What it shows | Source |
|---|---|---|

## On-image text: fonts

- Only the vetted fonts, Montserrat and Golos Text (both cover Latin and Cyrillic), and Scheherazade New for Arabic script. `content_lint` checks HTML assets.
- Before the first render in a new language, check that each font holds every letter of it (`letters` in `company.json`). A language none of them covers needs a new vetted font, with its licence, as a system order.
- Never let an image model draw text.

## Checking every text

The loop is the `second-language-copy` skill's. `scripts/language_check.py` checks the second language (SA-004), unless the Board turned it off; the Board reads every text either way.

## Glossary

A word's form comes from here. A word that isn't here is listed as "not in the glossary" in the piece, for the check and the Board; never invent one. Each row names its source and confidence.

| Second language | First language | English | For | Source | Conf. |
|---|---|---|---|---|---|
