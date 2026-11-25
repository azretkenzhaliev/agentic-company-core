---
title: Idea sources
owner: cmo
status: draft
updated: 2026-01-01
related: [README.md, language/red-lines.md]
---

# Idea sources

What the Board already reads, turned into one note a week: the analyst writes it, the cmo picks from it, the Board reacts (the `content-calendar` skill, "The idea note"). Empty until the Board names its sources (`docs/marketing.md`).

A source gives an idea. It never gives the founder's view, and it isn't a fact to publish: a claim in a piece still needs its own primary source.

## Telegram channels

The guard (`scripts/hooks/guard_marketing_tools.py`) lets the analyst read only the channels on this page, so a row here is how a channel joins. A private channel has no handle, so its row gives the chat id. Only the Board adds a row.

| Handle or id | Channel | Brand | Read |
|---|---|---|---|

A row looks like this (kept out of the table until it's real): the handle in backticks with its `@`, or the id in backticks; the channel's name; the brand; `week` or `latest`.

With `mcp__telegram__list_messages`, `chat_id` is the first column:
- **week:** `from_date` 7 days back, `limit` 30.
- **latest:** no `from_date`, `limit` 80: for channels that post dozens of times a day. `from_date` returns the oldest posts first, so a limit would cut off the newest.

## Newsletters

None yet. A row gives the sender's address; the analyst reads only what an order names.

## Limits

- **Private chats and groups:** never.
- **Paid channels and courses** give ideas only. The note never copies their posts or links their recordings.
- A piece doesn't repost another account's words as ours. A quoted text follows `content-qa` E.
- **Politics is in.** A claim that could read as false information, or as insult or libel, gets a one-line law note to the Board (`language/red-lines.md`).
- **Crimes and court cases naming private people** are picked like any item. The note marks the law point (insult and libel, personal data: `language/red-lines.md`) for the Board, never a block on the founder's pages. Any other brand's piece follows `content-qa` B.

## The server

Telegram is read through a local, read-only MCP server the founder runs (`docs/marketing.md`, "Telegram"). Its session file lives with the server, outside this repo, and no agent reads it. It exposes no write tool.
