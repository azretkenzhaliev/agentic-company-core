"""The CEO's row helper: add rows to the "## Status log" table of a directive file, after its last row. The rows come
from a file, or from standard input when that is `-`: a quoted heredoc, whose text the desk guard reads as text whatever
it says (scripts/hooks/board_desk_bash.py, status_log_run). It writes only the file it is given.

Usage: python3 scripts/status_log.py <directive file> <rows file | ->
"""

import sys


def add_rows(text, rows):
    """(the text with the rows after the last `| ` line of its "## Status log" section, that line's number + 1);
    ValueError when there is no such section or row."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip() == "## Status log"), None)
    if start is None:
        raise ValueError("no '## Status log' section")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    table = [i for i in range(start, end) if lines[i].startswith("| ")]
    if not table:
        raise ValueError("no table row under '## Status log'")
    lines[table[-1] + 1:table[-1] + 1] = rows
    return "\n".join(lines), table[-1] + 1


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    path, source = argv[1], argv[2]
    if source == "-":
        given = sys.stdin.read()
    else:
        with open(source) as f:
            given = f.read()
    rows = [row for row in given.split("\n") if row.strip()]
    with open(path) as f:
        text = f.read()
    try:
        text, after = add_rows(text, rows)
    except ValueError as error:
        print(f"{path}: {error}", file=sys.stderr)
        return 1
    with open(path, "w") as f:
        f.write(text)
    print(f"{len(rows)} row(s) after line {after}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
