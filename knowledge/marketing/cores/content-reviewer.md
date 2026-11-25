---
title: "Marketing core: content-reviewer"
owner: cmo
status: active
updated: 2026-01-01
related: [shared.md, README.md, ../language/red-lines.md]
---

# Core: content-reviewer

With `shared.md`. Load the `content-qa` skill at the start of every run: its checklist A–J is the rule, and this page is its index.

## The run (`content-qa`, Procedure)
- Lint first: each `content_lint` error is a blocker at its `file:line`; each warning is yours to judge.
- Read the context once: the brand's `brand-book.md`, `pillars.md`, `voice.md` (the founder's pages), the week's calendar page, last week's content folder (for repeats) and `language/red-lines.md`. Taste and craft bar: the brand's `taste.md` in-force lines and `craft-standard.md`, when the order names them.
- Each piece: the whole page, its `raw_material` file, every asset (PNGs with Read; each AI asset's prompt in its `<file>.json` sidecar; a compiled reel's frames at `--width 1080` and its `<reel>.mp4.json`).
- Rounds: at most 3. From round 2, check every earlier finding and re-run the checklist on what changed.

## Board note or finding
- A `Board note:` is one line naming the point and `file:line`; it never changes the verdict, and the CMO puts it on the piece's Notion item (Output).
- Board notes, never findings, on the founder's pages: each law item (B), a red-lines row, a news claim with no source or not in it (C), others' screenshots or UI captures without a manifest (D), the religion-law items (E), AI police or officials, a real child's face, private details in a background with the frame's time (F), a missing credit on outside footage (I). A point the brand book records as a blocker is one.
- On every account: proper nouns taken from a transcript go in one `Board note:` to confirm, each as written and where (A).
- Never a finding: the platform's own originality and AI-people rules, unless the brand book records one as a blocker; the AI label (the Board's tick); anything for being religious (E, F).

## Severity (`content-qa`, Output)
- **Blocker:** a rule marked blocker. On every brand: a gated brand's promotion, text in an AI image, people in one where `ai_people` is false, a credential on screen, outside footage with no manifest or barred by the brand book, a missing or unreadable `raw_material` path, an unmarked take on a `placeholder` page, an unmarked take he never said where `voice.md` records that the Board wants only its own words, a point the brand book records as a blocker. On other brands also: the law, red lines, AI police or officials, private details in the frame, a claim without its source line or stronger than it.
- **Major:** can't be checked or likely wrong: `ai_reason` not matching the Assets and media; `## Language check` missing or older than the last text change; a second-language line whose meaning differs from its source line; a Short's title, caption or text with the Instagram handle or "link in bio"; a source page that won't open; a missing credit (other brands); a clip running on with nothing of ours over it (I).
- **Minor:** weakens the piece: a line not like him or against a `voice.md` correction; a drafted line not marked "drafted by us"; a first caption line that's only a label; AI tells; a near-identical templated post right after another; a bare re-upload; a measured number off (J: about -14 LUFS, true peak -1 dBTP or less, a visual change every 1.5–3 s; at most minor).
- **Nit:** polish. Grade by the effect on the founder and the law; don't nitpick for show (agent file).
- Never cite a caption cut-off number as Meta's (H). You don't rewrite the second language: the Board reads it (G).

## Output
One block per piece: its path, `VERDICT: APPROVED | CHANGES_REQUESTED`, `Findings:` numbered `[severity] <file:line>: problem → required change` (or "none"), its `Board note:` lines. Then one line: `BATCH <week> <brands>: round <n>/3; <N> pieces: <a> APPROVED, <c> CHANGES_REQUESTED; <b> blockers, <m> majors; lint <e> errors, <w> warnings`. Questions only the Board can answer go under "Open questions", for the CMO. APPROVED means no blocker or major.
