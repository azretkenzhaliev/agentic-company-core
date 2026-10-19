---
title: Security standards
owner: cto
status: active
updated: 2026-10-12
related: [README.md, review-checklist.md]
---

# Security standards

1. **Secrets never go into code, commits, logs, the KB, reports or PR text.** Secrets live in the platform's secret store or environment. Refer to them by name ("env var `DATABASE_URL` in Vercel"), never by value.
2. **Don't read `.env` or key files.** Read `.env.example` to learn which variables exist.
3. **Validate all input** at the boundary: type, length, format, and allowed values. Use parameterized queries. Encode output for its context (HTML, SQL, shell, URLs).
4. **Check authorization on every request** that reads or changes someone's data, on the server.
5. **Personal data:** collect only what's needed, never log it, and say in the design doc where it's stored, who can read it, and how long it's kept.
6. **Dependencies:** prefer well-maintained packages, pin versions with the lockfile, and don't add packages to save a few lines.
7. **Never disable a security control** (CSRF, CORS, auth middleware, TLS verification, rate limits) to make something work. Escalate instead.
8. **Found a vulnerability?** Report it to your manager as a risk with its severity. Don't publish it in public issues.
