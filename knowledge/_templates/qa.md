## <YYYY-MM-DD, the day asked, the Board's time zone>

### Q-<n> · <current, or "changed YYYY-MM-DD, see Q-<m>"> · <topic, a few words> · asked <HH:MM, or "about HH:Mx">

- **Row:** R-<n> <only for a question the Board wrote in a new row of Notion's Q&A table: its R-id, or the row's Notion id>
- **Your words:** "<the Board's words, quoted short>"
- **Answer:** <at most 5 lines; each claim read from its source in that turn>
- **Still true from Q-<m>:** <a repeat question whose earlier answer changed through later work: what still holds, first>
- **Updated:** <then the part that changed>
- **Sources:** <links: a KB path relative to this page, a PR or a web page as given>
- **Asked before:** Q-<m> <and what it said, or the Board's earlier words with their date>

<!-- One question in knowledge/company/board-desk/qa.md, under its day's "## YYYY-MM-DD" (one heading a day); the CEO
alone writes it, in the turn it answers. Ids are never reused: grep the page and its archives
(qa-archive-YYYY-MM.md) for the highest, add one. A repeat question whose answer still holds: Answer plus Asked before.
One whose answer changed: Still true from Q-<m> and Updated instead of Answer, and the old entry's status becomes
"changed YYYY-MM-DD, see Q-<n>". Leave out the lines that don't apply.
Entries are never deleted: with the desk on (docs/board-desk.md), the daily job moves a day asked over 3 days ago, word
for word, to qa-archive-YYYY-MM.md. The page is a current-state page (kb_lint: 25 KB). Past it,
`python3 scripts/kb_sweep.py --apply --owner ceo` (and the daily job) also moves the oldest questions, whatever their
age, to the end of their day there, until the page is under 22.5 KB. The read job puts each entry, from the page and its
archives, in Notion's "Q&A" database as one row, KB paths as GitHub links and Q-ids as links to their rows. An entry
with a Row line answers a row the Board added there: the read job writes its fields into that row, never a second one,
and leaves the row's title, page and any column the Board wrote in as the Board wrote them. Your words is optional
there: the Board's words are in the row, and in the answers ledger as R-ids. Add the Row line when you first write the
entry: an entry pushed before as its own row keeps that row, with its older answer. -->
