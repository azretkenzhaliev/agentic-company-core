# The trial session file

The schema for the Board's taste-defining sittings: a few hours, once a page, that define the Board's taste for every type
of content. The worked example is `example-trial.json`, Day 1 for a page called `demo`.

    python3 tools/marketing/taste/build.py --page <page> --session <folder>/session.json            # writes picker.html
    python3 tools/marketing/taste/build.py --page <page> --session <folder>/session.json --design   # writes nothing

## Where

One file per page and sitting: `workspaces/marketing/media/taste/<page>/session-<YYYY-MM-DD>[-<word>]/session.json`.
The word tells two sittings of one day apart (`session-2026-01-07-pilot`, `session-2026-01-07`). Media sit beside it,
by file name only: `ref/<file>` for what others posted, `ours/<file>` for our renders. No sub-folders, no links, nothing
outside the session folder. `picker.html` is written beside `session.json`; it reads the media in place.

- **Media:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.mp4`, `.webm`, checked by their first bytes, at most 50 MB each and
  900 files a sitting. Keep clips short: the Board's minutes per part come from them. Chrome plays H.264 `.mp4`.
- **`ref/` needs a code:** every `ref/` file names the saved item it came from, `"reel": "<code>"` (intelligence
  `reels/<code>/`) or `"post": "<code>"` (`posts/<code>/`). That folder needs its `style.md`, or the build refuses.
  `ours/` files name no code.

## The file

    {"mode": "trial", "page": "demo", "title": "Day 1: demo", "intro": "One or two lines.",
     "seed": 12345, "break_minutes": 22, "parts": [<part>, ...]}

- `mode` is `"trial"`; without it the file is a weekly session (build.py's header).
- `seed`: a whole number from 1 to 2147483647. Every side, order and design is drawn from it; it's recorded in the page
  and in the answers. A new seed is a new design: render after fixing it.
- `break_minutes`: 20 to 25. After that many minutes of judging, the next screen is a break.

## A part

    {"id": "p3a", "type": "cbc", "title": "Reels", "minutes": 20, "question": "Pick the one you'd post.",
     "intro": [{"name": "Pacing", "line": "A cut about every 7, 3.5 or 1.75 seconds."}], ...}

Parts run in the file's order. Each opens with an intro screen, skippable (`intro` may be empty: no screen): the title
and one neutral line per dimension, saying what varies and, where it helps, its options (only those the part shows);
never which is better, no research claim. Trade-offs live on the page's taste-library
(`knowledge/marketing/founder/<page>/taste-library.md`), never on screen. A part of whole directions also says how to judge, as
the example's p1 does. `--design` warns, and still passes, on an intro line with a merit word: better, suits, avoids,
signals, calm, helps, hurts, study ("best" isn't one: a sequence asks for the best step). `minutes` (1 to 60) is the
plan the part's timer shows. `question` is optional; each type has a default. `id` is lower-case letters, digits,
dashes and underscores.

| `type` | What the Board does | Its fields |
|---|---|---|
| `pairwise` | picks one of two | `items` (an even number, 4 to 40), `rounds` (each item's comparisons, 1 to 2×(items−1)); `"scored": false` for practice pairs |
| `maxdiff` | picks the best and the worst of 4 | `items` (4 to 30), `appearances` (each item's sets, 2 to 6; items × appearances divisible by 4) |
| `cbc` | picks one of 3 options | `attributes` (1 to 8, each 2 to 5 levels), `tasks` (2 to 30), `holdouts` (0 to 4), `media`, `show_levels` |
| `sequence` | picks the best of 7 steps and the range he'd accept, ascending then descending | `dimensions` (1 to 16), each with 7 `steps` and optional `labels` |
| `range` | "anything from X to Y is fine", and the best if there is one | `dimensions` (1 to 16), each with 2 to 12 `values`; `"ordered": false` for values with no order |
| `notes` | types what he notices, one piece at a time | `items` (1 to 12) |
| `redlines` | ticks the hard NOs and adds his own | `candidates` (0 to 30 lines) |
| `checklist` | ticks the lines that apply and adds his own; not red lines (a carry-over list, say) | `candidates` (1 to 30 lines, kept in order), `mark` (the button, at most 40 characters; default "Tick") |

Unknown fields are refused, at every level. `intro` has at most 16 lines; `holdouts` defaults to 0.

**An item** (pairwise, maxdiff, notes): `{"id": "b1", "src": "ours/board-calm.jpg", "label": "optional"}`, or
`{"id": "r1", "src": "ref/DemoCode00H.mp4", "reel": "DemoCode00H"}`, or `"post": "<code>"` for a saved post. A
`ref/` file is named for its code: `ref/<code>.<suffix>`. A label is shown under the item; leave it out to judge the
piece alone.

**A cbc part:**

    "attributes": [{"id": "hook", "name": "Hook type", "levels": [{"id": "question", "label": "Bold question"}, ...]}, ...],
    "tasks": 16, "holdouts": 2, "media": "ours/reel-{hook}-{pacing}-{face}-{captions}-{grade}-{language}.mp4",
    "show_levels": false

`media` names one render per option: each `{attribute}` is filled with that option's level id, and every attribute
appears once. `--design` lists the files the seed needs. `show_levels` prints the level labels under each option.
Options in a task differ as much as the levels allow, no two alike; levels are balanced; the design is the most
efficient of a few hundred drawn from the seed. Holdouts are extra tasks the analysis keeps out of the fit.

**A sequence dimension:** `{"id": "text-area", "name": "Text area", "steps": ["ours/fine-text-area-1.jpg", ... 7],
"labels": ["10%", ... 7]}`, step 1 the least; steps are `ours/` files only. Every dimension runs once ascending, then,
after all of them, once descending.

**A range dimension:** `{"id": "reel-length", "name": "Reel length", "values": ["15 s", "20 s", "30 s", ...]}`,
lowest first: he picks the lowest and the highest that's fine. With `"ordered": false` (an ending, a call to action)
he ticks every value that's fine instead. Either way the best is optional.

## What the tool adds

- **No pre-selected answers.** Nothing starts chosen; nothing is labelled current.
- **Sides and order** come from the seed: items are shuffled, sides balanced, no item twice in a row where avoidable.
- **Designs are fixed and balanced:** pairwise is a round robin (every item `rounds` times; past items − 1 rounds the
  pairs come again, sides swapped); maxdiff shows every item `appearances` times, pairs as evenly as it can; cbc as
  above. Nothing adapts to answers.
- **Hidden repeats:** about 10% of each scored pairwise, maxdiff and cbc part (at least one, never of a holdout),
  with at least 5 trials between it and its source, sides swapped (cbc and maxdiff options rotated). A part too short for that
  gap puts its repeat last. Sequences are their own repeat: ascending against descending.
- **The page:** one trial a screen; a timer per part against its `minutes`; a break screen after `break_minutes` of
  judging (time counts only while the page is in front and in use); autosave after every trial; a parts menu to
  resume or redo anywhere; Back; and an export of every answer, with the design and seed, as one JSON file. Videos
  start muted.
- **The design id** (`design_id`, 12 hex characters) is a hash of the design without its display text (titles,
  minutes, questions, intros, names, labels, marks), its display settings (`show_levels`, `break_minutes`) and the
  folder's name: fixing a typo keeps it, and keeps the renders. Saved answers are kept per page, folder and design id.

## The answers

The page's Export writes `answers-<page>-<session>.json`: `{"format": "taste-trial-answers-1", "page", "session",
"seed", "design_id", "design", "answers", "intros", "part_seconds", "breaks", "total_seconds", "judging_seconds",
"exported_at"}`. `answers` maps each trial id to its answer, with `ms` (time on the screen), `at`, and `revised` when
redone:

| `type` | The answer |
|---|---|
| `pairwise` | `{"pick": "<item id>"}` |
| `maxdiff` | `{"best": "<item id>", "worst": "<item id>"}` |
| `cbc` | `{"pick": 1}`: the option's place, 1 to 3, in the order shown |
| `sequence` | `{"best": 4, "from": 3, "to": 5}`: step numbers, 1 the least, whatever order they were shown in |
| `range` | `{"from": "20 s", "to": "45 s", "best": "30 s"}` (`null`s for none fine); unordered: `{"fine": [...], "best": ...}` |
| `notes` | `{"note": "..."}` |
| `redlines`, `checklist` | `{"checked": [...lines], "own": [...lines]}` |

## The analysis

    python3 tools/marketing/taste/analyze.py --page <page> --session <folder>/session.json --answers <folder>/<export>.json
    python3 tools/marketing/taste/analyze.py --page <page> --session <folder>/session.json --recover

With the export in the session's folder, `analyze.py` writes `profile-<page>-<session>.json` beside it:
each part's weights with standard errors, the red lines, the checklist lines as ticked, the uncertain dimensions and
the restart check (hidden repeats' agreement against 80%, split near tie against clear). A sequence's
`best` is its fitted best step: when up and down differ, the two tie and are averaged (bests of 2 and 6 give 4), so
read it with `up` and `down`, which keep each run's answer; bests over a step apart mark the dimension uncertain. It
refuses an export whose `design_id` isn't the rebuilt design's. `--recover` runs a synthetic respondent through the
design and prints whether its known profile comes back, writing nothing. The estimator and the bounds are in the
script's header.

## Caps

At most 16 parts, 700 trials with repeats, 900 media files of 50 MB, 300 characters a text. The design is built in
before anything is written: a refusal names the part and writes nothing.
