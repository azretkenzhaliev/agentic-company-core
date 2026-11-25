---
name: second-language-copy
description: Use when the content-producer writes, or the content-reviewer checks, copy in a brand's second language (captions, script lines, on-image text, subtitles), including the language check of it. It doesn't apply to a brand that posts in one language.
---

# Copy in two languages

The procedure. The languages are `company.json`'s (`integrations.marketing.languages`, the first is the main one; `second_language` is the other). The detail lives in the cmo's language layer; read it, don't copy it:
- `knowledge/marketing/language/language-rules.md`: the rules and the glossary;
- `knowledge/marketing/language/captions-and-ctas.md`: caption structures, CTAs, legal footers;
- `knowledge/marketing/language/red-lines.md`.

## Which language

- **The founder's accounts:** what each brand book says.
- **Ads and paid placements, any brand:** the language or languages your market's law asks for (`red-lines.md`). Ad text follows the literary norm: slang stays in on-screen dialogue, not in an offer read-out.
- **A business's own pages:** where the law asks for a version in the official language, it carries no less information than the others.
- A filmed reel is spoken in whatever the founder speaks. Subtitles and on-image text follow the brand book's language policy; where it is silent, both, the first language first, and the question goes under "Open questions" in your report.
- Mocking how anyone speaks (an accent, a regional form, mixed speech), in any language: on the founder's pages, a one-line `Board note:` (`red-lines.md`, "Ethnicity and region"; `content-qa` B), never a block; other brands never do it.

## The default layout

The caption: **the first language's block, then a full block in the second** (`knowledge/_templates/content-piece.md`), unless the brand book says otherwise. "Full" means the same content, not a summary.

## Brand names and loan words

- How a brand name, a trademark or a loan word is written and inflected in the second language is in `language-rules.md`. Registered trademarks and logos may stay in their original language.
- A word's form comes from the glossary there. Not there: write your best form, list it in `## Language check` as "not in the glossary", and let `language_check` and the Board decide. Never invent a word.

## Plain style

In either language: cut filler and officialese, be concrete, respect the reader, give context, and mind the presentation. Spoken reels follow the spoken voice in the brand book: a plain written style can sound dry aloud. A style service that sends copy out is a new outside service: not used without the Board (SA-002).

## The quality loop

Image models garble letters, and models are uneven at small languages. So every text in the second language goes through the language check (SA-004), unless the Board turned it off, and then the Board.

1. **Write it from the founder's raw material**, or from the take drafted in his voice (`voice.md`): its meaning, nothing added. Never machine-translate blindly. If a draft starts from the first language, read it line by line against the raw material and the glossary.
2. **Keep a source line in the first language for each block in the second**, so the check can compare:
   - the caption: its other block;
   - script lines, on-image text and subtitles: pairs in `## Script`, `<CODE 2>: …` then `<CODE 1>: …`, per beat or slide. Subtitles of filmed reels go in too.
3. **Run** `python3 scripts/language_check.py <content page>`. It sends the piece's caption, script lines and on-image text to Gemini and prints its flags with the model name. It's in force once the second language and the key are set; where the Board turned it off (`language_check: false` in `company.json`) it sends nothing, and the section below says "off".
   - The script reads its key from the macOS keychain itself. Never run `security`, and never ask for, pass or print a key.
   - Only post copy goes: never customer data or product material (SA-004). Keep anything else out of those sections.
4. **Apply the fixes you agree with.** The flags are advice: check each against the glossary and the raw material. Re-render every asset whose text changed, and **run the check again if anything changed**.
5. **Record what's left** in the piece's `## Language check` section, and copy the same list into the Notion item's "Gemini flags" field:
   ```
   ## Language check

   Model: <model name as printed>, run <YYYY-MM-DD>, pass <n>.
   Remaining flags:
   1. "<text>": <the flag> → <kept because …> | <for the Board>
   ```
   With nothing left: "Remaining flags: none".
6. **On-image text only in the vetted fonts** (`content_lint` checks HTML assets). Never let an image model draw text: AI images are text-free (SA-005).
7. **The Board reads every text in the second language** in the weekly packet (SA-004). The check doesn't replace that read.

## Reviewer

- The language and layout rules above hold; an ad is in the languages the law asks for.
- `## Language check` exists, names the model (or "off"), and comes from a run after the last text change.
- Each line in the second language means what its source line says, and both say what the raw material, or the drafted take, says. A mismatch is a major. The style itself is the Board's read, not yours.
- Copy against "Plain style": minor findings.
