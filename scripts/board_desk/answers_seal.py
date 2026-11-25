"""The reader's seal on the Board's answers and on its own state. The Bash guard (scripts/hooks/board_desk_bash.py)
reads a command before it runs; this reads the result, whatever command or tool made it. scripts/board_desk.py, its
adapter_notion.py and scripts/capacity_scan.py use it.

- The seal: one JSON file per checkout in SEAL_DIR, outside the repo, so a write in knowledge/board/answers/ and
  workspaces/board-desk/ alone can't make it agree. Only the desk's own writers change it, each around its own write
  and from what it writes, never from what it reads: record()'s rows (written()), and FILES: save_state() of
  reader.json, reader_log()'s lines and adapter_notion.save_ids() of notion.json (writing()). It holds digests and ids,
  no word of the Board's: for each answers page (`<YYYY-Www>.md`) a digest of its text outside the rows, its
  `updated:` date aside (each write moves it); for each R-row its page, its ask id and a digest of its other cells;
  for each of FILES the digest of what the desk last wrote there. A write registers its new digest before it writes
  and drops the old one after, so a run cut short in between leaves no false alarm (settle()). And the ids the reader
  reads with (KEPT: the Board's user id and the last read's time, and notion.json's ids, no secret): with reader.json
  or notion.json not as the desk wrote it, the reader reads with these, the alarm standing (sealed()); with none kept
  yet, it stops.
- No seal yet for a checkout: the desk's first write makes it from the files as they are (the one trust on first
  use; the first read, in the main checkout). check() says nothing until then. One that can't be
  read (not JSON, or not a seal's shape) is set aside beside it and made again the same way, with an alarm that names
  it (ensure()), so it never holds a read.
- check(root): each way the files differ from the seal, as (subject, what), by R-id or file name: a row added,
  changed, moved, twice, deleted, or its R-id or ask id changed; a page made or deleted outside the reader, or its
  text outside the rows changed; one of FILES made, changed or deleted outside the desk. A row is any line whose first
  cell is an R-id (row()), so every line capacity_scan or the desk reads as one, whatever its other cells.
- The hourly check against Notion (board_desk.read_board, audit()): its time and its alarms or its failure, kept here;
  each alarm until the Board clears or seals.
- report(root): the alarm lines, `ANSWERS TAMPERED <R-id or file>: <what>`, check()'s and the last hourly check's;
  the R-ids they name, which capacity_scan.unhandled_answers() leaves out, so neither the scan, the heartbeat nor
  `board_desk.py wait` shows such a row as the Board's answer; and `ANSWERS NOT CHECKED at <time>` for an hourly check
  whose Notion read failed, or a seal that can't be read: never a pass, never an alarm.
- clear(root, edited, pair): the Board's step in Notion once it has looked at the alarms: Yes in
  Your answer on the Asks row "Answers checked" (board_desk.board_cleared(), acted on only with Notion naming the Board
  as its last editor, and only for a (Your answer, Your words) pair other than the last one acted on: the hook refuses
  those two fields by name to every caller, guard_marketing_tools.py). The alarms a read saw before that edit end
  (note_seen()); those since stand; the files as they are become the seal, and the next read checks Notion again.
- reseal(root): the Board's other route (`python3 scripts/board_desk.py seal`; the Bash guard refuses it to every
  agent, the CEO included, as any command but wait, install, uninstall and --help): every alarm ends, the files as
  they are now become the seal, and the next read checks Notion again. Both keep the highest R number (top()), and
  both set aside each R-row the alarms they end name (aside()): never an answer again, never
  checked against Notion again; the Board's words in Notion for its field, read anew (board_desk.audit()).
It is evidence of a change, not a lock, and no sandbox: the hourly check against Notion stands behind it. A value Notion
changes without an edit of its row (a select option renamed, a mentioned page's title) reads at the hourly check as a
row not as Notion holds it: an alarm, and, where the row's last editor is the Board, a new R-row with Notion's words. A
row the CEO hasn't acted on whose Notion row the Board renames a column of or moves to another database reads as a row
Notion lacks: an alarm (one in Notion's trash is not: board_desk.audit()).
"""

import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import company_config  # noqa: E402

# outside the repo: Application Support on macOS, the user's state folder elsewhere
SEAL_DIR = (Path.home() / "Library" / "Application Support" if sys.platform == "darwin" else
            Path.home() / ".local" / "state") / "agentic-company" / "board-desk-seal"
ANSWERS = Path("knowledge/board/answers")
FILES = ("workspaces/board-desk/reader.json", "workspaces/board-desk/notion.json",
         "workspaces/board-desk/reader-log.jsonl")  # the reader's state, its copy of the desk's ids, its log
STOPS = ("reader.json", "notion.json")  # they decide what counts as the Board's: changed, the reader reads with the
# ids the seal keeps of them (KEPT), and with none kept it stops
KEPT = {"workspaces/board-desk/reader.json": ("board", "since"),  # the Board's user id, the last read's time
        "workspaces/board-desk/notion.json": None}  # the desk's ids, whole: ids only, no secret, no word of the Board's
R_ID = re.compile(r"R-\d+")
CELL = re.compile(r"(?<!\\)\|")
UPDATED = re.compile(r"^updated:.*$")
AUDIT_EVERY = timedelta(hours=1)
LOCK_WAIT = 10  # seconds a check waits for a write in progress
try:
    ZONE = company_config.timezone()  # company.json's "timezone": the times the Board reads
    ZONE_NAME = str(ZONE.key).split("/")[-1].replace("_", " ")  # as they name it: UTC, New York
except (OSError, ValueError, KeyError, TypeError, AttributeError):  # the scan still checks the seal, and names the
    ZONE, ZONE_NAME = timezone.utc, "UTC"  # file; the desk's commands refuse it (adapter_notion.py)
MARK = "ANSWERS TAMPERED"


def digest(data) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8", "surrogateescape")).hexdigest()


def path_of(root) -> Path:
    return SEAL_DIR / f"{digest(str(Path(root).resolve()))[:16]}.json"


def row(line: str):
    """(R-id, ask id, digest of the rest of the line) of an answers row, or None for another line: any line whose
    first cell is an R-id, as board_desk.answer_rows() and capacity_scan's ANSWER_ROW read one."""
    parts = CELL.split(line)
    if len(parts) < 3 or not R_ID.fullmatch(parts[1].strip()):
        return None
    return parts[1].strip(), parts[2].strip(), digest(parts[0] + "|" + "|".join(parts[3:]))


def frame(text: str) -> str:
    """A page's text outside its rows, its `updated:` date aside and no blank line at its end, as a digest."""
    lines = [UPDATED.sub("updated:", line) for line in text.split("\n") if row(line) is None]
    while lines and not lines[-1].strip():
        lines.pop()
    return digest("\n".join(lines))


def pages(root) -> tuple:
    """({page name: frame}, [(R-id, page name, ask id, digest)]) of the answers pages on disk."""
    found, rows = {}, []
    for page in sorted((Path(root) / ANSWERS).glob("*-W*.md")):
        try:  # split as its readers split it: CRLF and a lone CR are line breaks (kb_sweep.read(), read_text())
            text = page.read_bytes().decode("utf-8", "surrogateescape").replace("\r\n", "\n").replace("\r", "\n")
        except OSError:
            continue
        found[page.name] = frame(text)
        rows += [(parts[0], page.name, parts[1], parts[2]) for parts in map(row, text.split("\n")) if parts]
    return found, rows


def file_digest(path: Path):
    try:
        return digest(path.read_bytes())
    except FileNotFoundError:
        return None


def kept(rel: str, data):
    """What the seal keeps of one of KEPT's files from its text (bytes or str): its ids; None for another file, or
    text that isn't a JSON object."""
    if rel not in KEPT:
        return None
    try:
        value = json.loads(data)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    return value if KEPT[rel] is None else {key: value.get(key) for key in KEPT[rel]}


def snapshot(root) -> dict:
    """A seal of the files as they are now."""
    found, rows = pages(root)
    files = {rel: [file_digest(Path(root) / rel)] for rel in FILES if (Path(root) / rel).exists()}
    ids = {rel: kept(rel, (Path(root) / rel).read_bytes()) for rel in KEPT if (Path(root) / rel).exists()}
    return {"root": str(Path(root).resolve()), "pages": found, "files": files, "pending": {"pages": {}, "rows": {}},
            "rows": {rid: [page, ask, mark] for rid, page, ask, mark in rows}, "audit": {},
            "made": datetime.now(timezone.utc).isoformat(), "ids": {rel: v for rel, v in ids.items() if v is not None}}


def sealed(root, rel):
    """The ids the seal keeps of one of KEPT's files, when the file isn't as the desk last wrote it (changed, deleted
    or made outside it), for the reader to read with in its place; None when it is, or when none are kept."""
    try:  # a seal that can't be read: none kept (the reader's start() sets it aside first)
        seal = load(root)
    except (OSError, ValueError):
        return None
    if not valid(seal):
        return None
    accepted = seal["files"].get(str(rel))
    if accepted is not None and file_digest(Path(root) / rel) in accepted:
        return None
    return (seal.get("ids") or {}).get(str(rel))


def load(root):
    try:
        return json.loads(path_of(root).read_text())
    except (FileNotFoundError, NotADirectoryError):
        return None


def valid(seal) -> bool:
    """Whether a loaded seal has the shape its readers take, its times readable: one in another shape is set aside
    (ensure())."""
    try:
        audit, pending, cleared = (seal.get(key) or {} for key in ("audit", "pending", "cleared"))
        alarms = (audit.get("alarms") or []) + (seal.get("remade") or [])
        for moment in ([audit.get("tried"), audit.get("at"), seal.get("made"), cleared.get("at")]
                       + [alarm[2] for alarm in alarms] + list((seal.get("seen") or {}).values())):
            if moment is not None:
                datetime.fromisoformat(moment)
        rows = {**seal["rows"], **(pending.get("rows") or {})}
        return (all(isinstance(seal[key], dict) for key in ("files", "pages"))
                and all(R_ID.fullmatch(rid) and isinstance(entry, list) and len(entry) == 3
                        for rid, entry in rows.items())
                and isinstance(pending.get("pages") or {}, dict)
                and all(isinstance(marks, list) for marks in seal["files"].values())
                and all(isinstance(kept, dict) for kept in (seal.get("ids") or {}).values())
                and all(isinstance(alarm, list) and len(alarm) == 3 for alarm in alarms)
                and all(R_ID.fullmatch(rid) for rid in seal.get("aside") or [])
                and isinstance(seal.get("top") or 0, int))
    except (AttributeError, KeyError, TypeError, ValueError, IndexError):
        return False


def save(root, seal: dict) -> None:
    path = path_of(root)
    temp = path.with_name(f".{path.stem}-{os.getpid()}")
    with open(temp, "w") as file:
        file.write(json.dumps(seal, indent=0, sort_keys=True))
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp, path)


@contextlib.contextmanager
def held(root, shared: bool = False):
    """The seal's lock: each write holds it from registering to dropping the old digest; a check, shared, sees no
    write half done. A check reads anyway with no lock file (no seal yet), none it may open, or none in LOCK_WAIT: it
    never writes, so an agent's scan needs no write outside its checkout."""
    lock = path_of(root).with_suffix(".lock")
    if shared:
        try:
            handle = open(lock)
        except OSError:
            yield
            return
    else:
        SEAL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle = open(lock, "a")
    with handle:
        for _ in range(LOCK_WAIT * 10):
            try:
                fcntl.flock(handle, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.1)
        else:
            if not shared:
                raise TimeoutError("another write holds the seal")
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def ensure(root) -> tuple:
    """(the seal, '' or how it was made now from the files as they are); under held(). One that can't be read (not
    JSON, or not a seal's shape) is set aside beside it and made again as a deleted one is, with an alarm line that
    names it, so nothing holds the Board's answers."""
    path, why = path_of(root), "not a seal's shape"
    try:
        seal = load(root)
    except (OSError, ValueError) as error:
        seal, why = None, type(error).__name__
    if seal is not None and valid(seal):
        return seal, ""
    fresh = snapshot(root)
    if not (path.exists() or path.is_symlink()):
        save(root, fresh)
        return fresh, "none for this checkout yet"
    aside = path.with_name(f"{path.stem}-unreadable-{time.time_ns()}.json")
    os.replace(path, aside)
    fresh["remade"] = [["seal", f"couldn't be read ({why}): set aside as {aside.name}, made again from the files as "
                        "they are", datetime.now(timezone.utc).isoformat()]]
    save(root, fresh)
    return fresh, f"couldn't be read ({why}); set aside as {aside.name}"


def start(root) -> str:
    """The reader's first step: '' or how it made the seal now (ensure()). A seal made before it kept ids (KEPT)
    takes them from each such file as the desk last wrote it."""
    with held(root):
        seal, made = ensure(root)
        ids = seal.setdefault("ids", {})
        found = {rel: kept(rel, (Path(root) / rel).read_bytes()) for rel in KEPT if rel not in ids
                 and file_digest(Path(root) / rel) in (seal["files"].get(rel) or [])}
        if any(value is not None for value in found.values()):
            ids.update({rel: value for rel, value in found.items() if value is not None})
            save(root, seal)
        return made


def settle(root) -> None:
    """A row write cut short (pending): its rows and new page kept where the page has them as written, else dropped."""
    with held(root):
        seal = load(root)
        if not seal or not any((seal.get("pending") or {}).values()):
            return
        found, rows = pages(root)
        on_disk = {rid: [page, ask, mark] for rid, page, ask, mark in rows}
        pending = seal["pending"]
        seal["pages"].update({page: mark for page, mark in pending.get("pages", {}).items() if found.get(page) == mark})
        seal["rows"].update({rid: want for rid, want in pending.get("rows", {}).items() if on_disk.get(rid) == want})
        seal["pending"] = {"pages": {}, "rows": {}}
        save(root, seal)


@contextlib.contextmanager
def written(root, page: str, rows: list, head: str):
    """Around record()'s write of rows [(R-id, ask id, digest)] to the answers page named page, which it makes with
    head if it isn't there."""
    with held(root):
        seal, _ = ensure(root)
        new_page = page not in seal["pages"] and not (Path(root) / ANSWERS / page).exists()
        seal["pending"] = {"pages": {page: frame(head)} if new_page else {},
                           "rows": {rid: [page, ask, mark] for rid, ask, mark in rows}}
        save(root, seal)
        yield
        seal["pages"].update(seal["pending"]["pages"])
        seal["rows"].update(seal["pending"]["rows"])
        seal["pending"] = {"pages": {}, "rows": {}}
        save(root, seal)


@contextlib.contextmanager
def writing(root, rel, data: bytes, append: bool = False):
    """Around the desk's own write of one of FILES: data is its new text (append: the text it adds). The seal takes the
    new digest only if the file is as the desk last wrote it: one changed outside stays named until the Board seals.
    The ids of one of KEPT's are kept either way: the desk writes them from the seal's own when the file was changed
    (sealed()), never from what was put there."""
    rel = str(rel)
    if rel not in FILES:
        yield
        return
    with held(root):
        seal, _ = ensure(root)
        path = Path(root) / rel
        old = path.read_bytes() if path.exists() else None
        before = None if old is None else digest(old)
        after = digest((old or b"") + data if append else data)
        accepted = seal["files"].get(rel)
        trusted = old is None if accepted is None else before in accepted
        if trusted:
            seal["files"][rel] = [mark for mark in (before, after) if mark is not None]
            save(root, seal)
        yield
        ids = kept(rel, data)
        if trusted:
            seal["files"][rel] = [after]
        if ids is not None:
            seal.setdefault("ids", {})[rel] = ids
        if trusted or ids is not None:
            save(root, seal)


def top(root) -> int:
    """The highest R number the seal knows or a page holds as pages() splits it, so a row deleted outside the reader
    never has its R-id given again, nor one hidden from the reader's own split (a lone CR) given twice."""
    seal = load(root) or {}
    ids = (list(seal.get("rows") or {}) + list((seal.get("pending") or {}).get("rows") or {})
           + [rid for rid, *_ in pages(root)[1]])
    return max([int(rid[2:]) for rid in ids] + [seal.get("top") or 0])


def spans(ids: list) -> str:
    numbers = sorted(int(rid[2:]) for rid in ids)
    return f"R-{numbers[0]}" if len(numbers) == 1 else f"R-{numbers[0]} to R-{numbers[-1]}"


def check(root) -> list:
    """[(subject, what)] for each way the files differ from the seal (module docstring); [] with no seal."""
    with held(root, shared=True):
        seal = load(root)
        if not seal:
            return []
        found_pages, disk = pages(root)
        files = {rel: file_digest(Path(root) / rel) for rel in FILES}
    pending = seal.get("pending") or {}
    want_pages = {**seal["pages"], **(pending.get("pages") or {})}
    want_rows = {**seal["rows"], **(pending.get("rows") or {})}
    out, places = [], {}
    for rid, page, ask, mark in disk:
        places.setdefault(rid, []).append((page, ask, mark))
    unclaimed = {}  # the sealed rows no longer there, by ask id and digest: an R-id changed is one of them
    for was, (_, ask, mark) in reversed(list(want_rows.items())):
        if was not in places:
            unclaimed.setdefault((ask, mark), []).append(was)
    renamed, named_as = {}, {}
    for rid, held_at in places.items():
        if rid not in want_rows and len(held_at) == 1 and unclaimed.get(held_at[0][1:]):
            was = unclaimed[held_at[0][1:]].pop()
            renamed[was], named_as[rid] = rid, was
    for rid in sorted(places, key=lambda rid: int(rid[2:])):
        held_at = places[rid]
        if len(held_at) > 1:
            out.append((rid, f"there {len(held_at)} times ({', '.join(page for page, _, _ in held_at)})"))
            continue
        page, ask, mark = held_at[0]
        if rid in named_as:
            out.append((rid, f"its R-id changed: the reader wrote it as {named_as[rid]}"))
            continue
        want = want_rows.get(rid)
        if want is None:
            out.append((rid, f"added outside the reader ({page}, ask {ask or 'none'})"))
            continue
        if want[0] != page:
            out.append((rid, f"moved from {want[0]} to {page}"))
        if want[1] != ask:
            out.append((rid, f"its ask id changed from {want[1]} to {ask or 'none'}"))
        if want[2] != mark:
            out.append((rid, "its words or other cells changed"))
    gone = {}
    for rid, (page, _, _) in want_rows.items():
        if rid not in places and rid not in renamed and rid not in (pending.get("rows") or {}):
            gone.setdefault(page, []).append(rid)
    for page in sorted(set(want_pages) | set(found_pages)):
        if page not in found_pages:
            if page not in (pending.get("pages") or {}):
                rows = gone.pop(page, [])
                out.append((page, "deleted" + (f", with {len(rows)} rows ({spans(rows)})" if rows else "")))
        elif page not in want_pages:
            out.append((page, "made outside the reader"))
        elif found_pages[page] != want_pages[page]:
            out.append((page, "its text outside the rows changed"))
    for page, rows in sorted(gone.items()):
        out += [(rid, "deleted") for rid in sorted(rows, key=lambda rid: int(rid[2:]))]
    for rel in FILES:
        accepted, now = seal["files"].get(rel), files[rel]
        name = Path(rel).name
        if accepted is None and now is not None:
            out.append((name, "made outside the desk"))
        elif accepted is not None and now not in accepted:
            out.append((name, "deleted" if now is None else "changed outside the desk"))
    return out


def due(root, now: datetime) -> bool:
    """Whether the hourly check against Notion is due: no try within AUDIT_EVERY."""
    tried = ((load(root) or {}).get("audit") or {}).get("tried")
    return not tried or now - datetime.fromisoformat(tried) >= AUDIT_EVERY


def audited(root, now: datetime, alarms=(), error: str = "") -> None:
    """The hourly check's outcome: its alarms [(subject, what)], or the failure that left the answers unchecked. An
    alarm stands until the Board clears or seals (clear(), reseal()), though a later check no longer finds it: the read
    that raised it may have kept Notion's words as a new R-row, and the row it names is still no answer of the
    Board's."""
    with held(root):
        seal, _ = ensure(root)
        last = seal.get("audit") or {}
        standing = [list(alarm) for alarm in last.get("alarms") or []]
        known = {(subject, what) for subject, what, _ in standing}
        seal["audit"] = {"tried": now.isoformat(), "error": error, "at": last.get("at") if error else now.isoformat(),
                         "alarms": standing + [[subject, what, now.isoformat()] for subject, what in alarms
                                               if (subject, what) not in known]}
        save(root, seal)


def clock(moment) -> str:
    moment = datetime.fromisoformat(moment) if isinstance(moment, str) else moment
    return f"{moment.astimezone(ZONE):%Y-%m-%d %H:%M}"


def alarms(root) -> list:
    """[(subject, what)]: check()'s, then the checks against Notion's, each with the time of the read that found it,
    then a seal set aside unreadable (ensure()); each stands until the Board clears or seals."""
    found = check(root)
    seal = load(root) or {}
    audit = seal.get("audit") or {}
    return (found + [(subject, f"{what} (Notion read {clock(at)} {ZONE_NAME})")
                     for subject, what, at in audit.get("alarms") or []]
            + [(subject, f"{what} ({clock(at)} {ZONE_NAME})") for subject, what, at in seal.get("remade") or []])


def named(found) -> set:
    """The R-ids alarms [(subject, what, …)] name: an R-id subject, and each R-id its text names."""
    return {rid for subject, what, *_ in found for rid in ([subject] if R_ID.fullmatch(subject) else [])
            + R_ID.findall(what)}


def report(root, now=None) -> tuple:
    """([`ANSWERS TAMPERED <subject>: <what>` lines], {the R-ids they name, and those a clear or seal set aside}, the
    not-checked line or ''): what capacity_scan, the hour's entry and wait show. A row an alarm names, or one set
    aside when the Board ended its alarm, is never shown as the Board's answer. The
    not-checked line, for a check against Notion that failed, a seal that can't be read, or, given now, no check
    against Notion within 2 x AUDIT_EVERY (the reader stopped, or its read failed before Notion answered), is never a
    pass and never an alarm."""
    try:
        found = alarms(root)
        seal = load(root) or {}
        audit = seal.get("audit") or {}
        last = audit.get("at") or seal.get("made")
        late = bool(now and last and now - datetime.fromisoformat(last) > 2 * AUDIT_EVERY)
        flagged = {subject for subject, _ in found if R_ID.fullmatch(subject)} | set(seal.get("aside") or [])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return [], set(), (f"ANSWERS NOT CHECKED at {clock(datetime.now(timezone.utc))} {ZONE_NAME}: the seal can't "
                           f"be read ({type(error).__name__})")
    unchecked = (f"ANSWERS NOT CHECKED at {clock(audit['tried'])} {ZONE_NAME}: Notion's read failed ({audit['error']}); "
                 f"last checked {clock(audit['at']) + ' ' + ZONE_NAME if audit.get('at') else 'never'}"
                 if audit.get("error") else
                 f"ANSWERS NOT CHECKED at {clock(now)} {ZONE_NAME}: no check against Notion since {clock(last)} "
                 f"{ZONE_NAME}"
                 if late else "")
    return [f"{MARK} {subject}: {what}" for subject, what in found], flagged, unchecked


def aside(root) -> set:
    """The R-ids a clear or seal set aside: never an answer, never checked against Notion again (board_desk.audit())."""
    try:
        return set((load(root) or {}).get("aside") or [])
    except (OSError, ValueError, AttributeError):
        return set()


def note_seen(root, now: datetime, found: list) -> None:
    """The time each of check()'s alarms (found) was first seen by a read, for clear(); one no longer there dropped."""
    with held(root):
        seal = load(root)
        if not seal:
            return
        was = seal.get("seen") or {}
        seen = {f"{subject}|{what}": was.get(f"{subject}|{what}", now.isoformat()) for subject, what in found}
        if seen != was:
            seal["seen"] = seen
            save(root, seal)


def hold_back(seal: dict, old: dict, subject: str, what: str) -> None:
    """In a new seal, the old seal's entries for one alarm's subject, so the alarm stands: a file's digests and ids, a
    row's (and the R-ids its text names), or a page's frame and rows; an entry the old seal hadn't, dropped."""
    def back(key: str, name: str) -> None:
        if name in (old.get(key) or {}):
            seal.setdefault(key, {})[name] = old[key][name]
        else:
            seal.get(key, {}).pop(name, None)

    files = {Path(rel).name: rel for rel in FILES}
    if subject in files:
        back("files", files[subject])
        back("ids", files[subject])
    elif R_ID.fullmatch(subject):
        for rid in [subject] + R_ID.findall(what):
            back("rows", rid)
    else:
        back("pages", subject)
        seal["rows"].update({rid: entry for rid, entry in (old.get("rows") or {}).items() if entry[0] == subject})


def resealed(root, old: dict, top_now: int, ended=(), standing=(), audit=(), remade=(), cleared=None) -> dict:
    """A new seal from the files as they are, the old one's entries kept for each of check()'s alarms in standing,
    the hourly check's alarms in audit, the unreadable seals' in remade, and its last check's time kept; each R-id the
    ended alarms name set aside, with those set aside before; the highest R number (top_now,
    top()'s) and the last clear carried, so no R-id is given twice and no clear acted on twice."""
    seal = snapshot(root)
    for subject, what in standing:
        hold_back(seal, old, subject, what)
    last = (old.get("audit") or {}).get("at")
    seal["audit"] = {**({"at": last} if last else {}), **({"alarms": list(audit)} if audit else {})}
    seal["seen"] = {key: at for key, at in (old.get("seen") or {}).items()
                    if tuple(key.split("|", 1)) in set(standing)}
    seal["top"] = top_now
    seal["aside"] = sorted(set(old.get("aside") or []) | named(ended), key=lambda rid: int(rid[2:]))
    if remade:
        seal["remade"] = list(remade)
    if cleared or old.get("cleared"):
        seal["cleared"] = cleared or old["cleared"]
    return seal


def reseal(root) -> list:
    """The Board's `seal` in a terminal: every alarm ends, the R-rows they name set aside, and the files as they are
    now become the seal; the alarm lines it ends. The next read checks Notion again; the last check's time stays, for
    report()'s 2 x AUDIT_EVERY."""
    start(root)  # a seal that can't be read: set aside first, as the reader's read does
    before, found, top_now = report(root)[0], check(root), top(root)
    with held(root):
        old = load(root) or {}
        ended = found + [tuple(alarm) for alarm in (old.get("audit") or {}).get("alarms") or []]
        save(root, resealed(root, old, top_now, ended))
    return before


def clear(root, edited: datetime, pair=("Yes", "")):
    """The Board's clear in Notion (board_desk.board_cleared()): the
    alarms raised before edited, the Board's edit's time, end, the R-rows they name set aside (never an answer), and the
    files as they are become the seal; one raised at or after it stands, check()'s by the time a read first saw it
    (note_seen()), with the old seal's entries for its subject (hold_back()). pair is the row's (Your answer, Your
    words): a clear acts only on a pair other than the last one acted on, never on an edit before the last one acted on
    (Notion's minutes: one in the same minute acts). (alarm lines ended, alarm lines standing), or None when it doesn't
    act. The next read checks Notion again."""
    found, top_now = check(root), top(root)
    with held(root):
        old = load(root) or {}
        last = old.get("cleared") or {}
        if list(pair) == last.get("pair") or (last.get("at") and edited < datetime.fromisoformat(last["at"])):
            return None
        seen = old.get("seen") or {}
        standing = [(subject, what) for subject, what in found if not seen.get(f"{subject}|{what}")
                    or datetime.fromisoformat(seen[f"{subject}|{what}"]) >= edited]
        was = [list(alarm) for alarm in (old.get("audit") or {}).get("alarms") or []]
        audit = [alarm for alarm in was if datetime.fromisoformat(alarm[2]) >= edited]
        remade = [alarm for alarm in old.get("remade") or [] if datetime.fromisoformat(alarm[2]) >= edited]
        ended = ([alarm for alarm in found if alarm not in standing] + [alarm for alarm in was if alarm not in audit]
                 + [alarm for alarm in old.get("remade") or [] if alarm not in remade])
        save(root, resealed(root, old, top_now, ended, standing, audit, remade,
                            {"at": edited.isoformat(), "pair": list(pair)}))
    return len(ended), len(standing) + len(audit) + len(remade)
