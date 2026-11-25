---
name: kb-check
description: Use when checking the knowledge base for broken links, missing or invalid front matter, duplicate IDs, stale pages or leaked secrets, before committing KB changes, or when the Board asks about KB health.
allowed-tools: Bash(python3 scripts/kb_lint.py *)
---

# Check the knowledge base

Run the linter from the repo root:

```bash
python3 scripts/kb_lint.py
```

It checks every page under `knowledge/`, skipping `knowledge/_templates/`:
- required front matter (`title`, `owner`, `status`, `updated`, `related`) and valid `owner`, `status` and date values;
- broken relative links and `related:` paths;
- duplicate IDs (two files claiming the same `RM-001`, `DD-001`, …);
- leaked secrets (keys, tokens, private keys). It shows the kind of secret and the line, never the value;
- pages over their size limit (`SIZE_LIMITS` in the linter: about 25 KB for a current-state page, more for designs, roadmaps, runbooks, standards, directives and research; none for `status: archived`). Pages named in `knowledge/oversize-pages.txt` pass;
- **warnings** for pages whose `updated` date is 90 or more days old, for orphan pages that no other page links to, for lines of `oversize-pages.txt` that no longer apply, for a `ceo-questions.md` or `board-steps.md` in `workspaces/<product>/content/` over about 30 or 20 KB, naming what to archive, and `sweep due` for a page within 10% of its limit, an owner whose last sweep is 14 days old or more, or a "Past, in short" older than its cold text.

It exits non-zero on any error. Warnings don't fail it.

## Then

1. **Errors in pages you own:** fix them, then re-run until there are no errors.
2. **Errors in pages someone else owns:** don't edit them. List them, with the owner, in your report or in your next order to that owner.
3. **A secret finding:** remove the value from the page right away (if you own it), name where the secret should live instead, and tell the Board that the secret may need rotating. It was on disk, and possibly in git history.
4. **`sweep due`:** the CEO and the CTO run `python3 scripts/kb_sweep.py`, which shows what would move and changes nothing, and each moves its own pages with `--apply --owner ceo` or `--owner cto`. A `ceo-questions.md`'s line names `python3 <repo>/scripts/cq_archive.py <repo>/workspaces/<product>/content/ceo-questions.md` instead (`--dry-run` first; both paths absolute, no `cd`: `cto.md`, "Logs"), and a `board-steps.md`'s says what to move by hand. Anyone else lists the line in their report, with the owner.
5. **Stale warnings:** re-check the page's facts. Bump `updated` only if you actually re-checked them. Otherwise leave the warning, or mark the page `archived` if it no longer matters.
6. **Orphan warnings:** link the page from its folder README (or `INDEX.md`), or archive it if nobody needs it.
7. **A size error:** move the page's history, whole, to a sibling page with `status: archived`, linked from it. Don't add the page to `oversize-pages.txt`; that list only shrinks.
8. Summarize in one or two lines: errors fixed, errors left (with owners), and warnings.

## Deep check (only when asked, e.g. `/kb-check deep`)

The linter checks structure. A deep check reads for meaning. Read the pages in scope (a folder, or the whole KB), then report:
- **contradictions** between pages, quoting both;
- **facts without a source**, against the "Every fact has a source" rule in `knowledge/README.md`;
- **stale claims** that newer pages, Board answers or research notes have overtaken;
- **missing pages:** concepts mentioned often but without a page of their own.

Fix what's in your own pages. List the rest by owner. Don't rewrite pages you don't own.
