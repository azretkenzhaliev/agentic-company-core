---
title: How the Board likes to work (preferences, in its own words)
owner: ceo
status: active
updated: 2026-11-25
related: [executive-summaries.md, ../board/charter.md, ../board/standing-authorizations.md]
---

# How the Board likes to work

The Board's preferences, so nobody asks it twice. Read this before you decide anything the Board might care about, or ask it anything. **If a line here answers your question, decide that way, cite its number, and don't ask.** Each line: the rule (its strongest wording, numbers, scope and exceptions), the date, its strongest quote, kept short; only repeats, context and history are cut, and move word for word to an archive page beside this one. Overlapping lines sit together; "N. See M." means M covers N. Numbers never change.

The CEO adds a line whenever the Board states a preference, overrides a recommendation or corrects our work, beside the lines it overlaps, and lists it in its next report, so the Board can undo it. A line's scope is what the Board said, no wider. A CEO reading that widens it goes only in the directive's `Decided:` row, with its undo, never into the line or a standing authorization. **A line never replaces the Board's yes on a one-way door; only a standing authorization does.** **Conflicting words go to the Board** (b8), both quoted with dates; nobody picks. **Except** when its new words clearly replace the old (they name them, or plainly re-decide the same thing): delete the old words wherever written and write the new in their place; list it under "Decided". Unsure: ask.

A line looks like this: `1. **<the rule>.** <scope and exceptions>. "<the Board's words>" (<YYYY-MM-DD>)`.

## Decisions and approvals

### Deciding and asking

Legal timing goes here if the Board makes the stricter choice (legal, privacy and consent items settled before a change reaches customers). The default is legal later (`ceo.md`, "Challenge before you plan"). (Design sign-off is in [charter.md](../board/charter.md): by default only one-way designs come to the Board.)

### Research and second opinions

## Speed, caution and quality

(Test scope is SA-001's condition 2, in [standing-authorizations.md](../board/standing-authorizations.md): by default the affected and essential tests; the stricter choice, the full suite before a deploy, goes there.)

## Engineering and the system

A stricter choice on database writes, merges and pushes, or the one retry in a named form, goes here (and where `/onboard-company` says). The defaults: SQL on a connected Neon project without a prompt, bulk changes only after a fresh backup branch, merges and pushes of reviewed work without a prompt ([docs/guards.md](../../docs/guards.md)). (Reading the company's own secrets is SA-008.)

## Usage, money and AI vendors

The plan size, the model choices and, if the Board sets one, a usage line from `/onboard-company` go here. The default: agents run until the account stops them (`CLAUDE.md`, "Every lane busy"). (Second opinions are SA-003.)

## Reporting and the desk

## <product>

One section per product.

## Marketing

Content limits from `/onboard-company` go here. The default: the brand books' limits and `content-qa` as they ship, drafted takes included.

## Corrections log

Each correction of our work by the Board: what it said, and the rule changed because of it, never only the instance (`CLAUDE.md`, "Fix the rule, not only the case").

| Date | The Board's words | What was wrong | Fix (the rule changed) |
|---|---|---|---|
