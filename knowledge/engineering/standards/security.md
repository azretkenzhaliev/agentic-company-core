---
title: Security standards
owner: cto
status: active
updated: 2026-11-25
related: [README.md, review-checklist.md]
---

# Security standards

1. **Secrets never go into code, commits, logs, the KB, reports or PR text.** Secrets live in the platform's secret store or environment. Refer to them by name ("env var `DATABASE_URL` in the host's settings"), never by value. Nobody prints a value.
2. **`.env` files, keys and passwords.** Agents may read and manage the company's own when a task needs them; customers' credentials stay out of reach (`CLAUDE.md`, "Git, code and safety"). Rule 1 still binds, and nobody prints a value. To learn which variables exist, `.env.example` is enough.
3. **Validate all input** at the boundary: type, length, format, and allowed values. Use parameterized queries. Encode output for its context (HTML, SQL, shell, URLs).
4. **Check authorization on every request** that reads or changes someone's data, on the server.
5. **Personal data:** collect only what's needed, never log it, and say in the design doc where it's stored, who can read it, and how long it's kept.
6. **Dependencies:** prefer well-maintained packages, pin versions with the lockfile, and don't add packages to save a few lines.
7. **Never disable a security control** (CSRF, CORS, auth middleware, TLS verification, rate limits) to make something work. Escalate instead.
8. **Found a vulnerability?** Report it to your manager as a risk with its severity. Don't publish it in public issues.
9. **Production databases, through a connector or by hand.** Where a database connector is configured (Neon's, for example: `docs/optional-integrations.md`), agents use it only as their own file and the product's runbook allow, and only once the Board has named the account (SA-006):
   - **Reads** are for a task's facts. The sign-in tables (`account`, `session`, `verification`) and the password catalog (`pg_authid`) are never read, and a connection string is never printed or stored.
   - **Schema changes go only through the repo's migrations.**
   - **A backup branch before any production statement that can change many rows at once** (an UPDATE or DELETE without WHERE, a TRUNCATE, a DROP of anything): one `create_branch` call named `backup-pre-<what>-<UTC stamp>` (seconds), named in your report. A setting upsert or a single-row change needs none. A migration that rewrites rows is preceded by a backup branch too. The SQL guard refuses the bulk changes it knows until the same session has made a backup branch in the last 60 minutes, and some statements whatever the backup (`docs/guards.md`). The product runbook names the restore window it backs up.
   - **Every backup gets an expiry** (7 days by default): where `create_branch` takes none, `update_branch` with `expires_at` right after it, as UTC to the second (Neon allows at most 30 days, and refuses it on the default branch, a protected one or one with children). `update_branch` is for expiries alone, from the CTO or a Staff engineer, on a branch your own fresh read (at most 30 minutes old) shows isn't the default, primary, protected or another's parent, and never less than 24 hours after the branch was made, so nobody expires another session's fresh backup. Read the branch (`get_branch`), then call `update_branch` alone in its own message. A backup a running order still needs past its date gets a later `expires_at` from that order's owner.
   - **Agents delete or reset no branch, project, role or database.**
