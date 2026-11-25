# tools/ux

The ux-expert's browser check, used by its skill (`.claude/skills/ux-checklist/SKILL.md`) and by Seniors meeting the component acceptance checklist. It runs on your machine against a local build or a public page and sends nothing anywhere.

## Install, once

```
npm ci --prefix tools/ux
npx --prefix tools/ux playwright install chromium
```

The founder runs these (Node 20 or later); they download from npm and from Playwright's own server. The lockfile pins axe-core 4.12.1 and playwright 1.64.1; `npm ci` can also install from the npm cache with `--offline` when they're there. The browser is Playwright's Chromium in its own cache folder (`~/Library/Caches/ms-playwright` on macOS, `~/.cache/ms-playwright` on Linux; on Linux it may need system libraries: `npx playwright install-deps chromium`). The ux-expert may run the first line itself (the lockfile's packages, nothing new). The browser missing: an agent reports BLOCKED; it doesn't download it.

## Run

```
node tools/ux/check.mjs <url> <out-dir> [--widths 375,768,1440] [--dark] [--tabs 60] [--steps <file.mjs>]
```

- `<url>`: `http://localhost:…` for a local build, a public page, or `file://` for a static page.
- `<out-dir>`: the ux-expert's `workspaces/ux/expert/<product>/<YYYY-MM-DD>-<slug>/`, a Senior's `workspaces/ux/senior/<product>/<task-id>/` (gitignored). It refuses one outside this repo's `workspaces/ux/`.
- `--widths 320` checks reflow; `--dark` adds a dark-scheme pass; `--tabs` caps the Tab walk.
- `--steps <file.mjs>`: a module whose default export, `async (page, { width, scheme }) => {}`, runs after the page settles and before the checks (open a menu, submit an empty form, `page.clock` for timers). A finding it reproduces is `step:<file>`. A module with no default function is refused.

For each width (and scheme) it waits 2 s after `load`, then:
- saves `<width>[-dark].png`, full page;
- runs axe-core twice: with its defaults, recording which WCAG 2.2 rules ran, then with every rule tagged `wcag22a` or `wcag22aa` switched on, recording violations and incomplete results;
- measures `clsLab` (largest session window) and `lcpLabMs` from this one load, `overflowX` (horizontal scroll in px), `lang`, `viewportMeta`, `cyrillicShare` and `mixedScriptWords` (words mixing Latin and Cyrillic letters: lookalikes such as a Latin `T` in a Cyrillic word; they say nothing on a page without Cyrillic);
- walks the page with Tab: each stop's element, size, and which styles changed on focus (`indicator: "none"` means focus changed nothing);
- lists `notReachable`: elements that look clickable (an `onclick`, a widget role, a pointer cursor) that Tab can't reach.

It writes `<out-dir>/report.json` and prints a summary. Lab values are one load on one machine: say "lab", never "p75".

## axe-core's WCAG 2.2 rules are off by default

Measured with axe-core 4.12.1 on the calibration pages: `axe.getRules(['wcag22a', 'wcag22aa'])` returns one rule, `target-size` (2.5.8). A default `axe.run` doesn't run it (it appears in no result list); switched on, it runs. That's why `check.mjs` switches the rules on, and why a repo's own axe setup must too (`rules: { 'target-size': { enabled: true } }`, or `runOnly` with the `wcag22aa` tag). The other WCAG 2.2 criteria (2.4.11, 2.5.7, 3.2.6, 3.3.7, 3.3.8) have no axe rule: check them by hand or with a step.

## calibration/

The calibration set the CEO runs to score the ux-expert (`calibration/README.md`). The ux-expert never opens it.
