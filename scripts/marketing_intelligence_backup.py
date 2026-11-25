#!/usr/bin/env python3
"""Copy marketing's intelligence folder into the folder company.json names, every night
(the nightly job is launchd's: macOS only).

    python3 scripts/marketing_intelligence_backup.py            one copy (what launchd starts, at 03:00 or on waking)
    python3 scripts/marketing_intelligence_backup.py install    install and start the launchd job for this checkout
    python3 scripts/marketing_intelligence_backup.py uninstall  stop and remove it

It does nothing until the Board names the folder: "integrations"."marketing"."backup_folder", a folder on this computer
(one a cloud drive syncs, say: then what is copied leaves this computer).

- **A copy, not a move:** workspaces/marketing/intelligence stays the working folder, on this disk. reels/watch.py refuses
  a link there, and a cloud drive may keep only a placeholder of a file on this computer.
  The copy is <backup_folder>/intelligence-backup/.
- **One way, and nothing is deleted:** it only reads the folder, and writes only the copy. A file gone from the folder
  stays in the copy, so a wiped folder can't wipe the copy. Each file is written under a temporary name beside its old
  copy and renamed over it only once whole, so a failed run leaves every file of the last copy whole. A SIGTERM (launchd,
  at shutdown or logout) removes the half-written file and stops; a power cut or SIGKILL can leave it, hidden, as
  .<name>.<random>.part beside the whole old copy.
- **Only this folder:** both paths are fixed (--root and --to move both ends, for tests and dry runs). A link on the
  way to the folder is refused and a link inside it is never followed, so nothing from another workspace can come along.
- **Unchanged files** (the same size and modification second) are skipped, so a night writes only what changed.
- **Log:** one line a run, counts and exit codes only, never a file name or its text: ~/Library/Logs/agentic-company/
  intelligence-backup.log. Exit 0 when every file was copied or unchanged, 1 when some failed (counted by error code,
  SIGTERM for a stopped run), 2 when it refused to start.
"""

import argparse
import contextlib
import errno
import os
import plistlib
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from company_config import integration  # noqa: E402

SOURCE = Path("workspaces/marketing/intelligence")
COPY = "intelligence-backup"
LABEL = "com.agentic-company.intelligence-backup"
PLIST = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
LOG = Path.home() / "Library/Logs/agentic-company/intelligence-backup.log"
PYTHON = "/usr/bin/python3"  # Apple's, so a Homebrew upgrade can't break the job; keep this file Python 3.9
HOUR = 3


class Stopped(Exception):
    """Raised by SIGTERM, so the file being written is removed before the run stops."""


def stop(signum, frame) -> None:
    raise Stopped


def say(text: str) -> None:
    print(f"{datetime.now().astimezone():%Y-%m-%d %H:%M %z} intelligence copy: {text}", flush=True)


def code(error: OSError) -> str:
    return errno.errorcode.get(error.errno or 0, type(error).__name__)


def refuse(reason: str) -> int:
    say(f"refused, {reason}; exit 2")
    return 2


def copy_file(source: str, target: Path) -> None:
    """Writes the file beside target under a temporary name, then renames it over target, so target is never half written."""
    handle, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".part")
    try:
        os.close(handle)
        shutil.copy2(source, temp)
        os.replace(temp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise


def copy_tree(source: Path, target: Path, counts: Counter, errors: Counter) -> None:
    def failed(error: OSError) -> None:
        counts["failed"] += 1
        errors[code(error)] += 1

    for folder, folders, files in os.walk(source, onerror=failed):  # never follows a link
        into = target / os.path.relpath(folder, source)
        try:
            into.mkdir(exist_ok=True)
            if not stat.S_ISDIR(os.lstat(into).st_mode):  # a link in the copy: mkdir follows it, writes must not
                raise OSError(errno.ELOOP, "a link in the copy")
        except OSError as error:
            failed(error)
            folders[:] = []
            continue
        for name in [name for name in folders if os.path.islink(os.path.join(folder, name))]:
            folders.remove(name)
            counts["skipped"] += 1
        for name in files:
            path = os.path.join(folder, name)
            try:
                status = os.lstat(path)
                if not stat.S_ISREG(status.st_mode):  # a link or anything else that isn't a plain file
                    counts["skipped"] += 1
                    continue
                counts["files"] += 1
                with contextlib.suppress(FileNotFoundError):
                    old = os.lstat(into / name)
                    if old.st_size == status.st_size and int(old.st_mtime) == int(status.st_mtime):
                        counts["unchanged"] += 1
                        continue
                copy_file(path, into / name)
                counts["copied"] += 1
                counts["bytes"] += status.st_size
            except OSError as error:
                failed(error)


def run(root: Path, to: "Path | None") -> int:
    if to is None:
        return refuse("company.json names no backup_folder")
    source = root / SOURCE
    if not source.is_dir() or source.resolve() != root.resolve() / SOURCE:
        return refuse(f"{SOURCE} is missing or reached through a link")
    try:
        if not stat.S_ISDIR(os.lstat(to).st_mode):  # a link there would carry the copy elsewhere
            return refuse("the backup folder is not a folder, or is a link")
    except OSError as error:
        return refuse(f"no backup folder ({code(error)})")
    target = to / COPY
    if target.is_symlink():
        return refuse(f"{COPY} is a link")
    try:
        target.mkdir(exist_ok=True)
    except OSError as error:
        return refuse(f"can't make {COPY} ({code(error)})")
    counts, errors = Counter(), Counter()
    try:
        copy_tree(source, target, counts, errors)
    except Stopped:
        counts["failed"] += 1
        errors["SIGTERM"] += 1
    exit_code = 1 if counts["failed"] else 0
    by_code = f" ({', '.join(f'{name} {n}' for name, n in sorted(errors.items()))})" if errors else ""
    say(f"{counts['files']} files, {counts['copied']} copied ({counts['bytes'] / 1e6:.1f} MB), {counts['unchanged']} "
        f"unchanged, {counts['skipped']} links skipped, {counts['failed']} failed{by_code}; exit {exit_code}")
    return exit_code


def job() -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [PYTHON, str(Path(__file__).resolve()), "run"],
        "StartCalendarInterval": {"Hour": HOUR, "Minute": 0},
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }


def install() -> int:
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST, "wb") as file:
        plistlib.dump(job(), file)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], check=True)
    print(f"installed {LABEL}: every night at {HOUR:02d}:00, from {REPO}; log {LOG}")
    return 0


def uninstall() -> int:
    service = f"gui/{os.getuid()}/{LABEL}"
    stopped = subprocess.run(["launchctl", "bootout", service], stderr=subprocess.DEVNULL)
    if stopped.returncode and subprocess.run(["launchctl", "print", service], stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL).returncode == 0:  # still loaded
        print(f"bootout failed (exit {stopped.returncode}), {LABEL} is still loaded; the plist stays, run uninstall again")
        return 1
    with contextlib.suppress(FileNotFoundError):
        PLIST.unlink()
    print(f"removed {LABEL}; the copy stays")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", default="run", choices=["run", "install", "uninstall"])
    parser.add_argument("--root", type=Path, default=REPO, help="run only: the checkout whose folder is copied")
    parser.add_argument("--to", type=Path, help="run only: the folder that gets the copy, instead of company.json's")
    args = parser.parse_args(argv)
    if args.command != "run" and sys.platform != "darwin":
        print("the nightly job runs only on macOS (launchd)")
        return 0
    if args.command == "install":
        return install()
    if args.command == "uninstall":
        return uninstall()
    named = (integration("marketing", args.root) or {}).get("backup_folder")
    return run(args.root, args.to or (Path(named).expanduser() if named else None))


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    sys.exit(main())
