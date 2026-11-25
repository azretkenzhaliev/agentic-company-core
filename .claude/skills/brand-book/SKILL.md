---
name: brand-book
description: Use when the CMO drafts or updates a brand's brand book, pillars or grid, and whenever any marketing agent (cmo, content-producer, content-reviewer) starts work on a brand, to load that brand's rules first.
---

# Brand book

A brand's rules live in the KB, not in this skill: `knowledge/marketing/<brand>/brand-book.md`, `pillars.md` and `grid.md` (the founder's accounts are `founder/<account>`; the templates are in `knowledge/marketing/_brand/`). The CMO writes them as **drafts**; the Board approves them (the CMO's escalation list in `CLAUDE.md`). Until the Board approves, they stay `status: draft`, and every piece built on them goes to the Board as a draft too.

**One recommended draft, never a menu.** The brand book, pillars and grid go to the Board as one complete recommended draft, with at most one alternative per contested point: pre-select, so the Board doesn't tire itself choosing.

## Before any piece

Every agent reads, in order:
1. `<brand>/brand-book.md`, and on the founder's pages `<brand>/voice.md`: his corrections to our drafted takes, which come before the brand book's "Voice";
2. `<brand>/pillars.md`;
3. `<brand>/grid.md`;
4. the last two `approvals/` pages, to see what the Board changed or rejected and why.

A rule in the brand book beats a general skill. A `TODO(board)` in the brand book means the matter is undecided: don't decide it in a piece. Ask the CMO, and the CMO asks the CEO.

## What a brand book holds

| Section | What | Source |
|---|---|---|
| The account | Handle, whether it exists, followers, the date counted | The Board (dated) |
| Goal | What the Board wants it to achieve, and any gate it set | The Board; the directive |
| Audience | Who, where, which languages they read | The Board; research notes for the market |
| Languages | One or two; the default layout (first language, then a full block in the second); spoken versus subtitle language in reels | The Board; `language/language-rules.md` |
| Voice | How the founder sounds, from his own posts and voice notes: quoted examples; his corrections to drafts are in `voice.md` | The founder's material; `TODO(board)` until there is some |
| Pillars | Link to `pillars.md` | – |
| Never post | The Board's list. Other brands add the law and red lines (`language/red-lines.md`); on the founder's pages, `content-qa` B and E say which law points are only Board notes, and the Board's recorded words name any it wants as blockers | The Board; red lines |
| Claims | Approved factual claims with sources; for founder accounts, mostly none | Sources |
| Visual rules | Colours (as CSS variables for `tools/marketing/templates/`), fonts (the vetted ones), imagery rules, cover style | The Board approves |
| Posting | Times, in the brand's `timezone`; cadence | The Board approves |
| AI use | What may be AI-made on this account (`content-qa` F) | SA-005 |
| Comments and DMs | Who answers them (the Board, unless it names someone) | The Board |
| Exemplars | Posts that show the target, with why | The Board picks |

## Pillars and grid

- **`pillars.md`:**
  - 3–5 pillars or rubrics, each with its purpose (reach, saves, trust, community), its formats and an example topic;
  - which rubrics start from the founder's raw material (opinions and reflections, where he has some); the rest are drafted in his voice for him to correct;
  - the target mix per week, within the Board's cadence.
- **`grid.md`:**
  - how the 3×3 feed reads, with cover styles per rubric;
  - pinned posts (3);
  - highlights.

## The interview (when a brand starts)

Before writing a brand book, the CMO asks the CEO to ask the Board, per account:
- does it exist, and how many followers;
- its language or languages;
- its audience;
- what the Board wants it to achieve;
- what the Board won't post;
- whether it wants its takes drafted for it to correct (the default), or only its own words;
- which law points, if any, it wants as blockers rather than notes on its own page (the default: none);
- its weekly minutes cap (the default: 2 h across all accounts).

Ask only what the founder's material, the KB and `knowledge/company/board-preferences.md` don't already answer, and pre-fill a proposed answer for each, with its source, so "yes" settles it. Record each answer verbatim with its date.

## Rules

- **His views are drafted in his voice, his facts are asked.** Pieces draft his takes for the Board to correct, unless `voice.md` records that the Board wants only its own words. A brand book describes the account; his biography and experiences come from him or the KB, else `TODO(board)` (`CLAUDE.md`, b7).
- **`voice.md`** (the founder's pages): after each Board review, the CMO adds each correction from the approvals page's "Board comment" column (`cmo.md`, "After the Board's review", step 3).
- Every fact names its source: the Board with the date, a research note, or a KB page.
- Changes to pillars, audience, voice or "never post" go to the Board as a draft change, with the reason, for example a learning from `learnings.md` once it exists.
