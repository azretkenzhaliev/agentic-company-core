---
title: How the agentic company works
owner: ceo
status: active
updated: 2026-11-25
big_picture: true
related: [org-chart.md, board-preferences.md, portfolio.md, ../INDEX.md, ../README.md, ../board/standing-authorizations.md, ../engineering/README.md]
---

# How the agentic company works

The company in plain words: the big picture, not the rules. Where a line differs from its source, the source wins. You are the Board: the founder.

**Last checked:** 2026-11-25, against the core as published; the CEO checks it again after `/onboard-company`, naming the `main` commit.

## Live, off, being built

Kept by the CEO: what runs today, what is off or paused and why, what is being built, what waits on you. After a fresh clone:

**Live**
- **You and the CEO.** You talk in the chat. The CEO turns your words into work, and asks you only one-way doors.
- **16 agents** work on your Claude subscription (SA-002) in three teams (below), on the products you name.
- **The safety net:** guards on risky actions, reviews of all work, a gate on changes to the company's own system, and a check that stops the CEO's turn while work sits idle (section 4).

**Off until you switch them on** ([docs/optional-integrations.md](../../docs/optional-integrations.md))
- **The Board desk** ([docs/board-desk.md](../../docs/board-desk.md)): your open asks, questions and answers, an hourly progress note and a daily summary in Notion.
- **Email from the CEO,** to your own address only (`board_email` in `company.json`).
- **Marketing** ([docs/marketing.md](../../docs/marketing.md)): drafts for the accounts you name; nothing is posted without your approval, post by post.
- **Second opinions** from other model families (SA-003), once you set a key and its entry in `company.json`; **the language check** of marketing copy (SA-004), once marketing is on and its language and key are set.

**Waiting on you:** `/onboard-company`, then the open items in [board-desk/asks.md](board-desk/asks.md).

## The picture

```
Board (you) -- chat; optionally the Notion desk and email
  |
CEO -- turns your words into orders, asks you only one-way doors, reports
  +-- analyst ........... one research question -> a sourced note
  +-- critic ............ checks the CEO's big plans before you see them
  +-- platform engineer . changes the company's own system -> review -> CEO lands
  +-- CMO (optional) .... plans a week -> producer -> reviewer -> you approve
  +-- CTO ............... sizes the work S / M / L
        S:   Senior builds -> reviewer checks
        M/L: Staff designs -> design review -> Seniors build -> reviewer checks
        -> merge (tests pass) -> deploy behind the gates (SA-001)
```

## 1. Who the agents are

There are 16 agents (`.claude/agents/`). Only the CEO talks to you; the rest send their questions up the chain.

- **Executive:** CEO (the session's model), analyst, critic and platform engineer (Opus).
- **Engineering:**
  - CTO, Staff engineer, design reviewer and UX expert: Opus.
  - Senior engineer and code reviewer: Sonnet. Reviews of sensitive code and of system changes use Opus.
- **Marketing (optional):**
  - CMO and content reviewer: Opus.
  - Content producer, performance analyst, trend researcher and reel analyst: Sonnet.

Chains are at most four deep: CEO, then CTO, then Staff, then Senior. Agents also use skills, which are playbooks for one kind of task (`.claude/skills/`).

## 2. From your message to a deploy

1. **A question** is answered from the knowledge base (KB). **A fact** goes into its page. **Anything bigger** becomes a directive: your words verbatim, the CEO's analysis, the orders and a status log (`knowledge/board/directives/`).
2. **Big or risky work** (money, legal, security, customer data) gets 2–3 options and a recommendation. The critic checks them before you see them.
3. **The orders go out together** where they don't depend on each other: research to the analyst, code to the CTO, the system to the platform engineer, and marketing to the CMO (marketing only on your order).
4. **Engineering:**
   - Medium and large work gets a short design and its review first. A design on the one-way list waits for your yes; the rest start, and you get a short summary.
   - A Senior builds each task with tests, and a reviewer checks it once.
   - The change merges after its tests pass.
   - The CTO or a Staff engineer deploys once every gate passes, with a quick check that the live product works and an immediate rollback on failure (SA-001).
5. **While it runs,** the CEO answers the engineers' questions in each order's question file. Only hard blocks wait: your yes on a one-way door, money beyond a budget, an outside party, or a review's verdict (`CLAUDE.md`, "Every lane busy").
6. **Back to you:** you are asked only one-way doors, with one recommended answer, at most 5 at once. Everything else is listed under "Decided", with how to undo it.

## 3. What you decide

**You decide:** mission, new or killed products, real money and new paid services, contracts, public statements in your name, anything sent outside the company, hiring, and standing authorizations. Agents decide everything else within your direction, record it and tell you (`CLAUDE.md`, "Decision rights").

**One-way doors** always come to you (`CLAUDE.md`, "The Board's attention" b):
- the items above, plus sign-ups and new accounts;
- customer data going to a new outside party;
- doing more to a live customer's data or systems than you approved, or lowering their protection;
- who can reach customer data;
- promises to customers;
- brand and product look;
- facts only you know;
- a conflict with your earlier words;
- loosening an agent's guardrail.

**Standing authorizations** pre-approve a whole kind of action. Five are in force by default: deploys behind the gates (SA-001), your subscription (SA-002), second opinions (SA-003) and the language check (SA-004) once you set their keys and entries, and the company's own keys and passwords (SA-008). Only you grant, narrow or end them ([standing-authorizations.md](../board/standing-authorizations.md)); the [README](../../README.md), "What is on by default", says how.

**[board-preferences.md](board-preferences.md)** holds your standing preferences in your own words, and a log of your corrections. Each correction fixes the rule behind it, not only that one case.

## 4. The guards

They stop mistakes; they aren't a sandbox. [docs/guards.md](../../docs/guards.md) says what each one does.

- **Permission rules** in `.claude/settings.json`: deny rules (force-pushes, admin merges, deletes and others) and allow rules for routine commands. Only your own message changes them.
- **Hooks** in `scripts/hooks/` block a rule-breaking action before it runs, for example:
  - starting an agent the org chart doesn't allow;
  - secrets in the KB;
  - agents writing your answers, or setting your fields in the desk;
  - email to anyone but you;
  - dangerous database changes;
  - the CEO's turn ending while work sits idle (stopped once);
  - a subagent changing `company.json`, which the guards read.
- **Reviews:** reviewers only read, and return APPROVED or CHANGES_REQUESTED. There is one round, then the disagreement goes up a level.
- **The gate on system changes:**
  - The platform engineer works in its own copy, with tests and an Opus review.
  - The CEO checks the main checkout before and after, and lands only what was reviewed.
  - A change that loosens a guardrail comes to you as one line, unless your own words already asked for it.
- **A refusal is final:** an agent that is refused stops and reports. It never looks for another route; where the block message itself names the form that is allowed, it may run the command once in exactly that form.

## 5. The knowledge base

- `knowledge/` is the single source of truth. Everyone reads all of it, and each folder has one owner, who alone writes it ([knowledge/README.md](../README.md)).
- Web content lands only in `knowledge/research/`. It is untrusted until an owner curates it. Unknown facts are written `TODO(board)`, never guessed.
- `scripts/kb_lint.py` checks every page. Old log text moves, word for word, to archive pages. Only the CEO commits to this repo.

## 6. The machine, CI and usage

- **The machine** runs the agents and local tests. New heavy work waits when under 15 GB of disk is free, on a Mac when memory is critical or under 5% free, or when the 5-minute load reaches 2.5 per CPU (defaults; anywhere but macOS the memory isn't checked); running work is never killed for load. A guard also stops starting a new agent that runs tests or builds at that load (`scripts/hooks/guard_agent_spawn.py`).
- **CI:** each product's tests run where its runbook says.
- **Usage:** your Claude subscription, until the account stops the agents, or up to a line you set. Anything paid is listed in `knowledge/finance/spend.md`.

## Keeping this page current

- **Who:** the CEO, its owner.
- **When:** the day a change it describes lands, and at least every 7 days (a default). Changes it describes include an agent, a background job or a guard added or removed, a pause or resume, or a change to the decision rules.
- **How:** re-read each changed line's source, fix the line, keep the page at about 10 KB at most, and set "Last checked". The capacity scan flags this page when it falls behind.
