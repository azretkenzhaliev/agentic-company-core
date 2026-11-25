---
name: ux-checklist
description: Use when the ux-expert audits, specs or accepts a UI, or when a Senior builds or changes a UI (a screen, a component or a style) and must meet the component acceptance checklist before reporting.
---

# UX checklist

The ux-expert's procedure, and the checklist Seniors meet on UI tasks. Owner: the ux-expert; it proposes changes in its report, and the platform engineer makes them. Why each rule exists, and the sources: `knowledge/engineering/ux/README.md`.

## 1. Set up

1. A local production build with a synthetic seed, from the product's runbook; or public pages, logged out. Never a signed-in production session.
2. A screenshot folder: `workspaces/ux/expert/<product>/<YYYY-MM-DD>-<slug>/` (gitignored).
3. The browser check on each screen: `node tools/ux/check.mjs <url> <folder>` (`tools/ux/README.md`). It screenshots 375, 768 and 1440 px, runs axe-core with its WCAG 2.2 rules switched on, and measures CLS, LCP, horizontal overflow, the Tab order with each stop's focus indicator, clickable elements Tab never reaches, the page's `lang` and words that mix Latin and Cyrillic letters. `--widths 320` checks reflow (1.4.10); `--dark` adds dark mode; `--steps <file.mjs>` runs your own Playwright steps first (open a menu, show an error), which is how a reproduced step becomes evidence.

## 2. Heuristic evaluation (audit mode)

Walk every named screen with each lens below. One finding per problem, in the table in section 4.

**Nielsen's 10** (Nielsen, 1994; NN/g's 2020 wording). Criterion ids H1–H10:
H1 visibility of system status · H2 match between the system and the real world · H3 user control and freedom · H4 consistency and standards · H5 error prevention · H6 recognition rather than recall · H7 flexibility and efficiency of use · H8 aesthetic and minimalist design · H9 help users recognize, diagnose and recover from errors · H10 help and documentation.

**Cognitive walkthrough** of each named user job (Wharton, Rieman, Lewis and Polson, 1994). Write the job's steps first, then ask at each step: will the user try to do the right thing? Will they notice the control is there? Will they connect it with what they want? After acting, will they see that it worked? A "no" is a finding, at the step it fails.

**WCAG 2.2 AA** (criterion ids as numbers, e.g. `1.4.3`). axe checks part of it; check these by hand or with a step:
- Perceivable: 1.1.1 text alternatives (meaning, not presence) · 1.3.1 info and relationships · 1.3.2 meaningful sequence · 1.4.1 colour not the only cue · 1.4.3 contrast 4.5:1 (3:1 large text) · 1.4.4 resize text to 200% · 1.4.10 reflow at 320 px · 1.4.11 non-text contrast 3:1 · 1.4.12 text spacing · 1.4.13 content on hover or focus.
- Operable: 2.1.1 keyboard · 2.1.2 no keyboard trap · 2.2.1 timing adjustable · 2.4.3 focus order · 2.4.4 link purpose · 2.4.6 headings and labels · 2.4.7 focus visible · 2.4.11 focus not obscured · 2.5.3 label in name · 2.5.7 dragging has a single-pointer way · 2.5.8 target size at least 24×24 px.
- Understandable: 3.1.1 page language · 3.1.2 language of parts · 3.2.6 consistent help · 3.3.1 error identification · 3.3.2 labels or instructions · 3.3.3 error suggestion · 3.3.4 error prevention (legal, money, data) · 3.3.7 redundant entry · 3.3.8 accessible authentication.
- Robust: 4.1.2 name, role, value · 4.1.3 status messages. (4.1.1 Parsing is gone in 2.2.)

**Core Web Vitals** (criterion ids `LCP`, `INP`, `CLS`): good is LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at the 75th percentile of real visits (web.dev). `check.mjs` measures lab values on one local load: say "lab", never "p75"; INP needs a real interaction, so measure it in a step or leave it out.

**Task flow:** for each job, the count of steps, decisions, fields and page loads; dead ends; whether the user can go back without losing work.

**Design-system consistency:** colours, type scale, spacing and radius against the product's tokens; the same thing with the same name, look and place on every screen.

**Content and i18n** (criterion id `i18n`): each of the product's languages as its users read it; every letter of its alphabet renders in the product's font, in both cases and under `text-transform: uppercase`; no lookalike letters from another script (`check.mjs` lists mixed words); `lang` is the text's own language; dates, numbers and plurals in the locale; the longest string fits.

**Screen types with their own guidance:** forms, data tables and alerts: read Baymard's guidance on each before judging one (`knowledge/engineering/ux/README.md`, sources).

**Teardowns** of best-in-class products: public pages, logged out, the date you checked. A pattern from a teardown is a hypothesis (grade C) until research or a test backs it. Never copy their text, images or code.

**Deceptive patterns:** list any you find (deceptive.design's types) as findings, H3 or H5.

## 3. Evidence and severity

- **Level** (agent file, "Evidence"): L0 real users or analytics · L1 a human expert · L2 a deterministic check · L3 a judgement, yours or another model's.
- **confirmed-by:** `axe:<rule id>` · `measured:<what>=<value>` · `step:<file>` (a Playwright step that reproduces it) · `so:<call id>` (an SA-003 second opinion: confirms, stays L3) · `-` (a hypothesis). Only a confirmed finding becomes a proposed task.
- **Severity, proposed** (from Nielsen's severity ratings, 1994: frequency, impact, persistence):
  - **blocker:** a user can't finish a named job; data is lost; a keyboard or screen-reader user is stopped on a core path.
  - **major:** the job finishes only with errors, delay or help; a WCAG A or AA failure on a core path.
  - **minor:** friction off the core path, or with an easy workaround.
  - **nit:** cosmetic.
  Mark every severity "proposed". An unconfirmed finding keeps its severity as a hypothesis; only a confirmed one counts as a blocker or major in an acceptance VERDICT.

## 4. The audit page

`knowledge/engineering/ux/audits/<product>-<YYYY-MM-DD>-<slug>.md`, front matter `owner: ux-expert`, `status: draft`. Sections:

1. **Scope:** the build (commit, seed), the screens and routes, the user jobs, the widths, and what you didn't check.
2. **Findings:** one table, these columns in this order (the calibration scorer reads them):

   | # | page | where | criterion | level | confirmed-by | evidence | severity |
   |---|---|---|---|---|---|---|---|
   | 1 | /dashboard | `button#export` | 1.4.3 | L2 | axe:color-contrast | 2.9:1, `check.mjs` 1440 | major (proposed) |

   `where` is a selector or the visible label; `criterion` is one or more ids (`1.4.3`, `H5`, `CLS`, `i18n`); `evidence` links the screenshot or the tool output.
3. **Proposed tasks:** confirmed findings only, each with the fix, its source and grade (A–D), and the acceptance check a Senior can run.
4. **Hypotheses:** the unconfirmed rest, each marked "unverified; confirm with L0 or L1", with the test that would settle it.
5. **Doors:** anything at b1, b5 or b6, marked.
6. **Not claimed:** no WCAG conformance, no representativeness for our users, no accuracy figure.

## 5. The spec (design mode)

`knowledge/engineering/ux/specs/<product>-<slug>.md`, `owner: ux-expert`. Sections:

1. **Goal and jobs:** who, on which device, in which language, doing what.
2. **Evidence:** what we know (level, grade) and what we assume.
3. **Flow:** each job's steps across the screens.
4. **Screens:** the layout at 375, 768 and 1440 px; components (the design system's first); the copy in each language with the longest string; every state from section 6; the glance (agent file, "The glance"): the first viewport's word budget, the three biggest things in order, the one primary action.
5. **Accessibility:** the WCAG points this screen risks, the Tab order, the names, where focus goes after each action.
6. **Options**, where the look is a choice: 2–3 rendered static pages in `workspaces/ux/expert/`, their screenshots, the evidence for each, each screen's glance check measured (agent file, "The glance"), one recommended. A new visual direction is b6: the Board picks.
7. **Acceptance:** the points of section 6 that apply, plus checks for this screen's jobs.

## 6. Component acceptance checklist

Seniors meet it on every UI task, and list in their report what they checked and where the screenshots are: `workspaces/ux/senior/<product>/<task-id>/` in the company repo (gitignored), never the product repo. The ux-expert's own go in `workspaces/ux/expert/` (section 1). The ux-expert checks it in acceptance mode.

1. **States**, each rendered: default, hover, focus-visible, active, disabled, loading, empty, error, success (those that apply).
2. **Keyboard and focus:** every action reachable with Tab in reading order; Enter and Space work (arrows inside composite widgets, as the ARIA APG says); the focus indicator visible (2.4.7) and not hidden under sticky bars (2.4.11); no trap; Escape closes an overlay and focus returns to where it was.
3. **Names:** every control has an accessible name that contains its visible label (2.5.3); icon-only buttons have one too.
4. **Screenshots at 375, 768 and 1440 px;** at 320 px no horizontal scroll, except a data table.
5. **i18n:** the strings in each of the product's languages, the longest one, and each alphabet's own letters in both cases, rendered in the product font; `lang` set; dates and numbers in the locale.
6. **Dark mode,** where the product has one: every state again, contrast measured again.
7. **Contrast and size:** text 4.5:1 (large 3:1), controls and focus rings 3:1, targets at least 24×24 px.
8. **Errors:** in text, not colour alone, tied to the field (`aria-describedby`); focus goes to the first error or a summary.
9. **Motion:** `prefers-reduced-motion` is honoured.
10. **axe** clean with the WCAG 2.2 rules on (`tools/ux/check.mjs`, or the repo's own Playwright and axe setup with the same rules). Clean is necessary, never proof of accessibility.
11. **Glance,** on a whole screen: the words in its first viewport (the spec's, else 1440x900 and 390x844), counted from the rendered text, within the spec's budget, else the product's taste page's (none: report the count); its three biggest things in the spec's order; one primary action at most.
