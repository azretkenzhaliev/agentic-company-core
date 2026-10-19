---
name: onboard-company
description: Use when the Board asks to onboard the company, to run the onboarding interview, or to fill in the company and product facts still marked TODO(board) in knowledge/company/ and knowledge/products/.
disable-model-invocation: true
---

# Onboard the company: the Board interview

You are the CEO. In about 30 minutes, replace the `TODO(board)` facts in `knowledge/company/` and `knowledge/products/` with the Board's own answers, and collect what engineering needs to deploy safely (SA-001). **Write each round's answers into the KB before you ask the next round.**

## 1. Prepare (no questions yet)

1. File this as a directive, following the `directive` skill's filing step: `D-<YYYYMMDD>-onboard-company`. Use the Board's words that started it, or "/onboard-company".
2. Read `knowledge/INDEX.md`, every page in `knowledge/company/`, and every `knowledge/products/*/README.md`.
3. Read `knowledge/engineering/architecture/*.md` and `knowledge/engineering/runbooks/*.md` if they exist. **Facts the code already shows become confirm-style questions**, e.g. "The repo deploys to Vercel from `main` via GitHub Actions. Is that how production works today?". That's faster for the Board than open questions.
4. List the open facts: `grep -rn "TODO(board)" knowledge/ --include=*.md`.
5. Tell the Board the agenda in a few lines: the rounds below, about 30 minutes, and that it can say "skip", "later" or "stop" at any time. Mention that nothing leaves the company, and that secrets mustn't be pasted, only where they live.

## 2. Interview rounds

Ask **3–5 numbered questions per message**, then wait for the answers. Skip anything the KB already answers. Give a recommendation or a guess-to-confirm only where the code or KB supports it, and label it as such.

| Round | Ask about | Write to |
|---|---|---|
| 1. Company | Legal entity (name, country). Mission and vision, in the Board's words. Human team and roles. Markets and working languages. Budget limits (monthly, and per directive). Current priorities and goals or OKRs. What we're not doing | `company/overview.md`, `company/strategy.md` |
| 2. Each product, one at a time | What it is. Users and their problem. Value proposition. Stage. Website. Main features. Pricing and business model. Traction and metrics. Languages and markets. Competitors. Current marketing and sales channels | `products/<product>/README.md` (create it from `_templates/product.md` if missing), `company/portfolio.md` |
| 3. Deploys, per product | Hosting provider. CI/CD. Environments and production URL. How to tell production is healthy (the smoke check). How rollback works today. Where credentials live (never their values). Who else deploys | the product page's "How deploys work today" |
| 4. Accounts and limits | Accounts agents may use (`gh` is logged in already; hosting CLIs; analytics). No-go areas. Data needing extra care (personal data, payments) | the product page's "Accounts agents may use, and no-go areas"; company-wide limits in `company/overview.md` |
| 5. Ideas not started yet | Name, thesis, target customers, timeline, next step | `products/<id>/README.md` (status `draft`) |
| 6. Working style | How often and how the Board wants reports, the report language, and anything the CEO should always or never do | `company/overview.md`, "Working with the Board" section |

## 3. Rules while recording

- **Quote the Board** where wording matters: mission, vision, claims about the product. Paraphrase only plain facts.
- **Unanswered stays `TODO(board)`.** Sharpen the question so next time it's quick to answer. Never fill a gap with a guess.
- **If the Board pastes a secret,** don't write it anywhere. Record only where it lives, and tell the Board you didn't store the value.
- **A new standing authorization or a change to one**, in the Board's words, goes into `knowledge/board/standing-authorizations.md` as a new or amended `SA-NNN` section, with the date.
- Update `updated:` on every page you change. Set a page's status to `active` once its main sections are filled. Leave it `draft` while most of it is still `TODO(board)`.

## 4. After the interview

1. **For each product whose deploy facts are now known,** send the CTO an ORDER (size S, logged in this directive). It asks the CTO to update `knowledge/engineering/runbooks/<product>.md` with the confirmed facts, verify every non-destructive step it can (build, test, smoke check against production), and report which steps remain unverified. The runbook becomes `active` only when the CTO reports the steps verified.
2. Run `python3 scripts/kb_lint.py` and fix any errors in your pages.
3. Commit (`kb(D-<id>): record onboarding answers`) and push.
4. Report to the Board: the rows for `CLAUDE.md`'s product table (a maintenance session adds them), what's filled, what's still `TODO(board)` (grouped), the orders sent, and **a proposed first S-size directive** for one product, with your reason for choosing it.
