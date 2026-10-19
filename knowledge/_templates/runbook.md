---
title: Runbook for <product>
owner: cto
status: draft
updated: <YYYY-MM-DD>
related: []
---

# Runbook: <product>

> **SA-001 gate:** autonomous production deploys are allowed only while this page is `status: active`. It becomes active after the deploy facts are confirmed by the Board and every step below has been verified.

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
