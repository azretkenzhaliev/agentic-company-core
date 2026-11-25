---
title: Engineering standards
owner: cto
status: active
updated: 2026-11-25
related: [../README.md]
---

# Engineering standards

These apply in every product repo, **unless the repo's own `CLAUDE.md`, README or tooling says otherwise**. Inside a repo, its rules win. Product-specific conventions are in `../architecture/<product>.md`.

| Page | Used by |
|---|---|
| [coding.md](coding.md) | Seniors writing code; code reviewers |
| [testing.md](testing.md) | Seniors; code reviewers; Staff writing testing strategies |
| [security.md](security.md) | everyone; both reviewers check it |
| [review-checklist.md](review-checklist.md) | design reviewer and code reviewer |
| [definition-of-done.md](definition-of-done.md) | everyone, before reporting DONE |
| [lessons-learned.md](lessons-learned.md) | everyone reads its digest; the CTO appends after each directive that went wrong. Older rows move to `lessons-learned-archive.md`, searched, not read |
| [runtime-settings.md](runtime-settings.md) | Staff and Seniors writing any value someone may tune (sizes, budgets, timeouts, thresholds, rates, floors, retries, models); code reviewers; whoever changes a setting |
| [board-steps.md](board-steps.md) | the CTO and Staff before adding a Board step; the CEO for reaching, pausing and stopping running agents; the one-way doors hooks enforce |
