---
name: funnel-design
description: Use when the CMO drafts a brand's ladder from free value to paid, a lead magnet, a comment-keyword → DM flow or a UTM link, or checks whether a planned CTA crosses a funnel gate. Every funnel is a draft for the Board.
---

# Funnel design

How the cmo drafts a brand's funnel: the ladder from free value to paid, lead magnets, comment-keyword → DM flows and UTM links.

## Gates (read first)

**Selling isn't gated on the founder's pages.** Every funnel, lead magnet, DM flow and link is still a draft for the Board, each post is approved one by one, prices and terms are the Board's (`CLAUDE.md`, b5), and nothing leaves the company without the Board. A product brand's funnel starts only once the Board has started the brand, and a **gated** brand (marketing README, the table of brands) gets nothing until the Board lifts its gate.

- **Lead collection includes** "comment your number", "DM me for the guide", forms, waitlists and link-in-bio sign-ups (`content-qa` B). A comment-keyword → DM flow is lead collection. Each follows the consent rules in §3.
- **Not in this build:** direct-message automation tools and ads. Comment-to-DM flows are set up by the Board itself (§4).
- **No AI replies to DMs.**
- **Product brands:** no claim without a source; never invent prices, results, testimonials or features.
- **The founder's voice:** a funnel's lines on his pages are drafted in his voice from `voice.md`, marked "drafted by us", for the Board to correct (`content-qa` A).

## 1. The ladder

One table per brand. Each rung says what the person gets, the price, the CTA that moves them up, how it's measured, and its gate.

| Rung | They get | Price | CTA up | Measured by | Gate |
|---|---|---|---|---|---|
| 1. Free reach | Reels, carousels | 0 | Follow; send it to someone | Reach, shares per reach, new follows | none |
| 2. Free depth | Posts worth keeping; story series | 0 | Save; reply; comment | Saves and comments per reach | none |
| 3. Lead magnet | One free resource, by DM or link | 0 | Comment a keyword; tap a link | Keyword comments; link taps | consent (§3) |
| 4. Paid entry | The first paid step | the Board's | Buy | The product's own analytics | the Board's price and terms |
| 5. Core and continuity | The main product, renewed | the Board's | Renew; upgrade | The product's own analytics | the Board's price and terms |

- **On the founder's accounts, the funnel starts as rungs 1–2,** with a follow as the "conversion" (`instagram-formats` step 3; `reel-script` §6); rungs 3–5 are drafted when an order asks. The 8-week review measures reach, saves, shares and new followers (`ig-insights-review`).
- **The ladder's shape is practitioner method, not platform fact.** Where its detail matters, work from a verified card (`book-to-cards`).
- **Rungs 3–5 are measured off Instagram:** conversions need UTM-tagged bio and story links and the product's own analytics.

## 2. Per brand

- **A product brand,** once it starts:
  - product facts (price, what's free, how it's paid) only from `knowledge/products/<product>/README.md`; everything there marked `TODO(board)` stays out of a funnel;
  - **the funnel to measure:** Instagram → site visits → trials → paid, as aggregate counts the CTO supplies from the product's analytics. Marketing gets no database access;
  - **break-even:** the department's monthly tool budget divided by what one customer pays a month, both from the KB;
  - **the audience and consent:** who pays, who uses, and whose consent §3 asks for;
  - **lead magnets:** what the product page already gives free comes first;
  - no implied affiliation with an institution the product isn't part of (`content-qa` B).
- **A founder's page:** rungs 1–2; rungs 3–5 when an order asks.
- **A gated brand:** nothing.

## 3. Lead magnets

On the founder's pages, the law points here are `Board note:` lines in review, never a block (`content-qa` B).

- It works on its own: the person gets something useful even if they never pay. It promises only what it delivers.
- It's built from sourced material: the product pages, and content the Board has checked, exported by the CTO, never live unreviewed content.
- No "best", "№1", "only" or guaranteed results without documentary proof. A discount states its place, dates and % (`content-qa` B).
- No giveaway whose entry needs a purchase or payment (`content-qa` B).
- **Contacts only with consent** (what your market's law asks is in `language/red-lines.md`):
  - consent is given per purpose, actively, with full information, and the operator must be able to prove it; withdrawing it is as easy as giving it;
  - a parent consents for a child;
  - a consent line and a privacy notice in the page's languages, and consent logs kept;
  - sending data abroad (a platform's servers included) needs a basis, such as consent;
  - no numbers in broadcast lists without opt-in;
  - never ask for a phone number in public comments.
- TODO(board): where contacts and consent logs live, and on what lawful basis (the CRM question in `sales-playbook`). No personal data goes in the KB.

## 4. Comment-keyword → DM flows

- **The tool:** Meta Business Suite's free "Comment to message", which the Board sets up on desktop. No agent holds a DM tool (`scripts/hooks/guard_marketing_tools.py`).
- **Limits:**
  - one private reply per comment, within 7 days of it; more only after the person replies, and then within 24 hours (platform-facts, "The publishing API"; official);
  - a small number of keywords, case-sensitive and exact-match. TODO(verify): the limits against Meta's own help page before the first flow.
- **Keywords:** spend the slots on spelling variants (TEST, test, Test), and avoid letters people type differently on another keyboard.
- **A flow draft gives:**
  - the post or posts it runs on, and the keywords;
  - the exact DM text, in the brand's caption order (`second-language-copy`), checked by `language_check` unless it's off (SA-004);
  - what it delivers: a link to the free resource;
  - the consent line, if it collects anything (§3);
  - who answers replies: the Board, unless it names someone;
  - when the flow is switched off.
- **The Board approves each flow like a post,** and sets it up itself.

## 5. UTM links

- **Why:** to see Instagram traffic in the product's own analytics.
- **Our scheme** (a department rule, not a platform fact), lowercase ASCII with hyphens:
  - `utm_source=instagram`;
  - `utm_medium=bio|story|post|dm`;
  - `utm_campaign=<the campaign page's C-NNN-slug>`;
  - `utm_content=<YYYY-Www>-<piece slug>`.
- Ask the CEO whether the product's analytics record UTM parameters: it's an engineering question.
- Only our own products' links. Don't tag other people's URLs.
- Link stickers are a phone task, because the API can't publish them (platform-facts). The bio link is the Board's to set.

## 6. Where a funnel draft goes

`knowledge/marketing/<brand>/campaigns/C-NNN-<slug>.md`, `owner: cmo`, `status: draft` (the README's layout). One page per brand ladder, and one per lead magnet or DM flow, linked from the ladder page. Each holds the campaign fields from the cmo's prompt (goal and metric; audience; message and offer; channel; assets; timeline; budget, which the Board approves; success criteria; results afterwards), plus:
- **Gate:** which gate applies and what lifts it. A gated page says "structure only: not for use" at the top;
- **Ladder:** the §1 table;
- **Lead magnet, DM flow and UTM links** (§3–5), where used;
- **Consent and data** (§3);
- **Sources:** a KB path or research note for every fact.

Then give the CEO the "Approve to publish?" block from the cmo's prompt. A funnel goes live only on the Board's word.

## Rules

- Payments shown in posts: the business's own payment page or QR, never a personal card.
- Ads aren't this skill.
- Where a funnel hands a lead to sales, the CEO (as CSO) owns what happens next (`sales-playbook`). The campaign page links its pipeline page.
