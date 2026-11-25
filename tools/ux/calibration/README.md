# UX calibration set

For the CEO: it measures how well the ux-expert finds known defects before its findings drive product work. The ux-expert must never see this folder (its agent file says so): check its transcript's file reads before you trust a score.

## What's here

- `site/dashboard.html`: a made-up dashboard page (English).
- `site/booking.html`: a made-up ticket booking page in a Cyrillic script (Bulgarian), with words in both cases and under `text-transform: uppercase`; it's there for the language and mixed-script defects.
- `answer-key.json`: the 16 planted defects (8 and 8), each with its WCAG or heuristic criteria, the words that locate it, and its kind: `axe` (an axe rule finds it), `measured` (a value `check.mjs` reports), `playwright` (a step reproduces it) or `judgement` (only a reviewer sees it).
- `score.py`: counts found, missed and invented findings by evidence level.

The pages hold no comments or ids that name a defect. Keep them unchanged between runs, so scores stay comparable across versions of the agent.

## Run it

1. Copy the pages where the ux-expert can work: `mkdir -p workspaces/ux/expert/calibration` and `cp -R tools/ux/calibration/site workspaces/ux/expert/calibration/site`.
2. Order an audit (mode audit, product "calibration") of `file://<repo>/workspaces/ux/expert/calibration/site/dashboard.html` and `…/booking.html`, with these user jobs: on the dashboard, "find the late order, then clear the finished rows"; on the booking page, "enter your name, choose the seats and how you get the tickets, and book". Ask for the findings table in `workspaces/ux/expert/calibration/<YYYY-MM-DD>/findings.md` (not the KB), and the skill's columns.
3. Score it: `python3 tools/ux/calibration/score.py workspaces/ux/expert/calibration/<YYYY-MM-DD>/findings.md`.

A row finds a defect when its page, a criterion id and one locator word match. The scorer prints, by evidence level, the defects found (and how many of those rows were confirmed), the invented rows and the missed defects, each counted at the level its kind calls for (`axe`, `measured` and `playwright` at L2, `judgement` at L3); then the missed defects by kind, and duplicates. An empty findings table scores 0 found. Read every invented row yourself: some will be real defects nobody planted (add them to the key if so), some will be wrong criteria for a real defect (the scorer is strict), and the rest are what the confirmation filter is for. What to expect: every `axe` and `measured` defect found and confirmed at L2; `judgement` defects found as L3 hypotheses; invented rows that are confirmed are the ones to worry about.

## How axe-core runs here

`check.mjs` uses axe-core 4.12.1, pinned by `tools/ux/package-lock.json`. Its WCAG 2.2 rules are off by default: `axe.getRules(['wcag22a', 'wcag22aa'])` returns only `target-size`, a default `axe.run` doesn't run it, and `check.mjs` switches it on (`tools/ux/README.md`). Defect D3 (16×16 px pager buttons) is the check: an audit that misses it ran axe with its defaults.

What `check.mjs` reports on these pages: axe finds D1, D2, D3, D8, E3 and E7; `clsLab` is over 0.1 (D7); the four filter chips show `indicator: "none"` (D4), and the other tab stops `outline`; the first tab stop is `#refresh` (D8), which is also the check of the Tab walk itself: a walk that pairs focused and unfocused styles in document order, not Tab order, shows two of the chips as changed; `lang` is `en` with `cyrillicShare` 1 (E1); `mixedScriptWords` is `["Tеатър"]` (E2); the three seat choices are in `notReachable` (E4); `overflowX` is above 0 at 375 and 320 px (E8). `scripts/tests/test_ux_calibration.py` re-runs `check.mjs` at 375 px and checks these values; it skips when Chromium or `tools/ux/node_modules` is missing.
