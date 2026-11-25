---
title: Runbook for <product>
owner: cto
status: draft
updated: <YYYY-MM-DD>
related: []
---

# Runbook: <product>

> **SA-001 gate:** autonomous production deploys are allowed only while this page is `status: active`. It becomes active after the deploy facts are confirmed by the Board and every step below has been verified.

## Find your section

Read the section for your task, not this page (engineering README, "What to read"). Find a heading with `grep -n '^##' <this file>`, then read it with an offset and a limit.

| For a task like | Read |
|---|---|
| Implementing or reviewing a task | "Task suite", then "Test (the full suite)" |
| A production deploy | "Deploy to production", "Smoke check", "Rollback" |
| Something looks wrong in the world | "Known hazards" |
| What was verified and when | "Verification record" |

<One row per kind of task, kept current with the headings. History goes to a sibling page, with a row here.>

## Repo and environments

| Environment | URL | How it's deployed | Branch |
|---|---|---|---|

## Prerequisites

<Tools, CLI logins, access. Where credentials live, never their values.>

## Build

```bash
<exact commands>
```

## Test (the full suite)

```bash
<exact commands>
```

<No full suite runs on the machine, on a schedule or before a deploy (SA-001 condition 2), unless the Board chose the full suite for this product; where the repo has CI, a full run is its manual `workflow_dispatch` (engineering README §5). The agents' prompts point here.>

## Task suite (while a task iterates)

```bash
<the exact command for the files a task touches>
```

## Essential tier

```bash
<the exact command for the small always-on set every landing runs (engineering README §4–5); the CTO names it>
```

## CI and landing

<the required checks, the merge command, the time limit, or: no CI>

## Deploy to production

<Numbered, exact steps. Include how to tell the deploy finished.>

## Smoke check

<Exact commands or URLs and the expected result for each. Must finish in under 5 minutes.>

## Rollback

<Numbered, exact steps, and how long rollback takes. Include data rollback if migrations ran.>

## Known hazards

## Verification record

| Date | Step | Verified by | Result |
|---|---|---|---|
