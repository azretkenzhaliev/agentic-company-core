"""Tests for scripts/marketing_intelligence_backup.py.

Every folder is made up in a temporary directory, which stands in for both the checkout and the backup folder: nothing here
reads the real intelligence folder, writes outside it or runs launchctl."""

import contextlib
import errno
import io
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import marketing_intelligence_backup as backup  # noqa: E402

CANARY = "C0dEcAnArY"  # a post code: the log must never name a file


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.root = self.temp / "checkout"
        self.source = self.root / backup.SOURCE
        self.to = self.temp / "synced"
        self.copy = self.to / backup.COPY
        (self.to / "media").mkdir(parents=True)
        self.write("posts.csv", "read_date,post_code\n2026-01-05,%s\n" % CANARY)
        self.write("2026-W05.md", "# week\n")
        self.write(f"reels/{CANARY}/video.mp4", "video bytes")
        self.write(f"reels/{CANARY}/breakdown.md", "format: Talking head\n")

    def write(self, relative, text, base=None):
        path = (base or self.source) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_backup(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = backup.main(["run", "--root", str(self.root), "--to", str(self.to)])
        return code, out.getvalue()

    def tree(self, base):
        return {str(path.relative_to(base)): path.read_bytes() for path in sorted(base.rglob("*")) if path.is_file()}

    def snapshot(self, base):
        return {str(path.relative_to(base)): (path.read_bytes(), os.lstat(path).st_mtime_ns)
                for path in sorted(base.rglob("*")) if path.is_file() or path.is_symlink()}


class CopyTest(Base):
    def test_first_run_copies_every_file_whole_and_logs_counts_only(self):
        code, out = self.run_backup()
        self.assertEqual(code, 0)
        self.assertEqual(self.tree(self.copy), self.tree(self.source))
        self.assertIn("4 files, 4 copied", out)
        self.assertIn("0 failed; exit 0", out)
        self.assertNotIn(CANARY, out)
        self.assertNotIn("posts.csv", out)
        self.assertEqual(len(out.splitlines()), 1)
        mtime = os.stat(self.source / "posts.csv").st_mtime_ns
        self.assertEqual(os.stat(self.copy / "posts.csv").st_mtime_ns, mtime)

    def test_second_run_writes_only_what_changed(self):
        self.run_backup()
        code, out = self.run_backup()
        self.assertEqual(code, 0)
        self.assertIn("4 files, 0 copied (0.0 MB), 4 unchanged", out)
        csv = self.source / "posts.csv"
        csv.write_text(csv.read_text() + "2026-01-06,Other\n")
        code, out = self.run_backup()
        self.assertIn("1 copied", out)
        self.assertEqual((self.copy / "posts.csv").read_text(), csv.read_text())

    def test_the_source_is_never_changed(self):
        self.run_backup()
        (self.source / "2026-W05.md").write_text("# week, edited\n")
        before = self.snapshot(self.root)
        self.run_backup()
        self.assertEqual(self.snapshot(self.root), before)

    def test_a_file_gone_from_the_folder_stays_in_the_copy(self):
        self.run_backup()
        shutil.rmtree(self.source / "reels")
        code, out = self.run_backup()
        self.assertEqual(code, 0)
        self.assertEqual((self.copy / f"reels/{CANARY}/video.mp4").read_text(), "video bytes")

    def test_a_failed_run_leaves_the_last_copy_whole(self):
        self.run_backup()
        last = self.tree(self.copy)
        self.write("posts.csv", "a new, longer posts.csv\n" * 10)
        self.write("2026-W05.md", "# week, edited\n")
        real = shutil.copy2

        def disk_full(source, target):  # half a file, then the disk is full
            if source.endswith("posts.csv"):
                Path(target).write_bytes(Path(source).read_bytes()[:20])
                raise OSError(errno.ENOSPC, "No space left on device")
            return real(source, target)

        with mock.patch.object(backup.shutil, "copy2", disk_full):
            code, out = self.run_backup()
        self.assertEqual(code, 1)
        self.assertIn("1 failed (ENOSPC 1); exit 1", out)
        self.assertEqual((self.copy / "posts.csv").read_bytes(), last["posts.csv"])
        self.assertEqual((self.copy / "2026-W05.md").read_text(), "# week, edited\n")
        self.assertEqual(set(self.tree(self.copy)), set(last), "no temporary file is left behind")
        code, out = self.run_backup()
        self.assertEqual(code, 0)
        self.assertEqual(self.tree(self.copy), self.tree(self.source))

    def test_a_stopped_run_removes_its_half_written_file_and_logs_the_stop(self):
        self.run_backup()
        last = self.tree(self.copy)
        self.write("posts.csv", "a new, longer posts.csv\n" * 10)

        def sigterm(source, target):  # launchd's SIGTERM, halfway through a file
            Path(target).write_bytes(Path(source).read_bytes()[:20])
            backup.stop(15, None)

        with mock.patch.object(backup.shutil, "copy2", sigterm):
            code, out = self.run_backup()
        self.assertEqual(code, 1)
        self.assertIn("1 failed (SIGTERM 1); exit 1", out)
        self.assertEqual(self.tree(self.copy), last, "the last copy is whole and no temporary file is left")

    def test_an_unreadable_folder_is_counted_and_the_rest_copied(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every folder")
        locked = self.source / "reels" / CANARY
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        code, out = self.run_backup()
        self.assertEqual(code, 1)
        self.assertIn("1 failed (EACCES 1); exit 1", out)
        self.assertTrue((self.copy / "posts.csv").is_file())


class OnlyThisFolderTest(Base):
    def setUp(self):
        super().setUp()
        self.outside = self.root / "workspaces/acme"
        self.write("content/customer.md", "product notes", base=self.outside)
        self.write("reviews/r1.md", "system notes", base=self.root / "workspaces/system")

    def test_only_the_intelligence_folder_is_copied(self):
        self.run_backup()
        self.assertEqual(set(self.tree(self.copy)), set(self.tree(self.source)))
        self.assertEqual(sorted(p.name for p in self.to.iterdir()), ["intelligence-backup", "media"])

    def test_links_inside_the_folder_are_never_followed(self):
        os.symlink(self.outside, self.source / "acme")
        os.symlink(self.outside / "content/customer.md", self.source / "customer.md")
        code, out = self.run_backup()
        self.assertEqual(code, 0)
        self.assertIn("2 links skipped", out)
        self.assertNotIn(b"product notes", b"".join(self.tree(self.copy).values()))
        self.assertFalse(os.path.lexists(self.copy / "acme"))
        self.assertFalse(os.path.lexists(self.copy / "customer.md"))

    def test_a_link_inside_the_copy_is_never_written_through(self):
        self.copy.mkdir()
        os.symlink(self.source, self.copy / "reels")  # planted there, pointing back at the folder
        before = self.snapshot(self.root)
        code, out = self.run_backup()
        self.assertEqual(code, 1)
        self.assertIn("1 failed (ELOOP 1); exit 1", out)
        self.assertEqual(self.snapshot(self.root), before)
        self.assertFalse((self.source / CANARY).exists())
        self.assertTrue((self.copy / "posts.csv").is_file())

    def test_the_folder_as_a_link_is_refused(self):
        shutil.rmtree(self.source)
        os.symlink(self.outside, self.source)
        code, out = self.run_backup()
        self.assertEqual(code, 2)
        self.assertIn("refused", out)
        self.assertFalse(self.copy.exists())

    def test_a_link_on_the_way_to_the_folder_is_refused(self):
        marketing = self.root / "workspaces/marketing"
        marketing.rename(self.temp / "elsewhere")
        os.symlink(self.temp / "elsewhere", marketing)
        code, out = self.run_backup()
        self.assertEqual(code, 2)
        self.assertFalse(self.copy.exists())


class RefusalTest(Base):
    def test_no_backup_folder_is_refused_and_nothing_made(self):
        shutil.rmtree(self.to)
        code, out = self.run_backup()
        self.assertEqual(code, 2)
        self.assertIn("no backup folder (ENOENT); exit 2", out)
        self.assertFalse(self.to.exists())

    def test_no_intelligence_folder_is_refused(self):
        shutil.rmtree(self.source)
        code, out = self.run_backup()
        self.assertEqual(code, 2)
        self.assertFalse(self.copy.exists())

    def test_the_backup_folder_as_a_link_is_refused_and_nothing_written(self):
        elsewhere = self.temp / "elsewhere"
        self.to.rename(elsewhere)
        os.symlink(elsewhere, self.to)
        code, out = self.run_backup()
        self.assertEqual(code, 2)
        self.assertIn("refused, the backup folder is not a folder, or is a link; exit 2", out)
        self.assertEqual([p.name for p in elsewhere.iterdir()], ["media"])
        self.assertEqual(list((elsewhere / "media").iterdir()), [])

    def test_the_copy_as_a_link_is_refused(self):
        elsewhere = self.temp / "elsewhere"
        elsewhere.mkdir()
        os.symlink(elsewhere, self.copy)
        code, out = self.run_backup()
        self.assertEqual(code, 2)
        self.assertEqual(list(elsewhere.iterdir()), [])


class FolderSettingTest(Base):
    def run_default(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = backup.main(["run", "--root", str(self.root)])
        return code, out.getvalue()

    def test_nothing_is_copied_until_the_folder_is_named(self):
        for settings in (None, "{}", '{"integrations": {"marketing": {"backup_folder": ""}}}'):
            if settings is not None:
                (self.root / "company.json").write_text(settings)
            code, out = self.run_default()
            self.assertEqual(code, 2)
            self.assertIn("company.json names no backup_folder", out)
        self.assertFalse(self.copy.exists())

    def test_the_named_folder_gets_the_copy(self):
        (self.root / "company.json").write_text('{"integrations": {"marketing": {"backup_folder": "%s"}}}' % self.to)
        self.assertEqual(self.run_default()[0], 0)
        self.assertEqual(self.tree(self.copy), self.tree(self.source))

    def test_a_broken_company_json_copies_nothing(self):
        (self.root / "company.json").write_text("{not json")
        with self.assertRaises(ValueError):
            self.run_default()
        self.assertFalse(self.copy.exists())


class InstallTest(unittest.TestCase):
    """launchctl is mocked and the plist and log go to a temporary folder: nothing is installed."""

    def setUp(self):
        temp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        self.plist = temp / "LaunchAgents" / f"{backup.LABEL}.plist"
        for name, value in (("PLIST", self.plist), ("LOG", temp / "Logs" / "intelligence-backup.log")):
            patcher = mock.patch.object(backup, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.calls = []
        self.exits = {}
        self.service = f"gui/{os.getuid()}/{backup.LABEL}"

    def launchctl(self, args, **kwargs):
        self.calls.append((args, self.plist.exists()))
        return subprocess.CompletedProcess(args, self.exits.get(args[1], 0))

    def call(self, function):
        out = io.StringIO()
        with mock.patch.object(backup.subprocess, "run", self.launchctl), contextlib.redirect_stdout(out):
            code = function()
        return code, out.getvalue()

    def test_install_writes_the_plist_then_boots_out_then_bootstraps(self):
        code, out = self.call(backup.install)
        self.assertEqual(code, 0)
        with open(self.plist, "rb") as file:
            self.assertEqual(plistlib.load(file), backup.job())
        self.assertEqual(self.calls, [(["launchctl", "bootout", self.service], True),
                                      (["launchctl", "bootstrap", f"gui/{os.getuid()}", str(self.plist)], True)])
        self.assertTrue(backup.LOG.parent.is_dir())

    def test_uninstall_boots_out_and_removes_the_plist(self):
        self.call(backup.install)
        self.calls.clear()
        code, out = self.call(backup.uninstall)
        self.assertEqual(code, 0)
        self.assertEqual(self.calls, [(["launchctl", "bootout", self.service], True)])
        self.assertFalse(self.plist.exists())
        self.assertIn("removed", out)

    def test_uninstall_of_a_job_not_loaded_removes_the_plist(self):
        self.call(backup.install)
        self.calls.clear()
        self.exits = {"bootout": 3, "print": 113}  # launchctl print's exit for a service it doesn't know
        code, out = self.call(backup.uninstall)
        self.assertEqual(code, 0)
        self.assertEqual([args[1] for args, _ in self.calls], ["bootout", "print"])
        self.assertFalse(self.plist.exists())
        self.assertIn("removed", out)

    def test_uninstall_keeps_the_plist_when_the_job_is_still_loaded(self):
        self.call(backup.install)
        self.calls.clear()
        self.exits = {"bootout": 36}
        code, out = self.call(backup.uninstall)
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [(["launchctl", "bootout", self.service], True),
                                      (["launchctl", "print", self.service], True)])
        self.assertTrue(self.plist.exists())
        self.assertNotIn("removed", out)
        self.assertIn("bootout failed (exit 36)", out)


class JobTest(unittest.TestCase):
    def test_the_job_runs_this_script_nightly_on_apples_python(self):
        job = backup.job()
        self.assertEqual(set(job), {"Label", "ProgramArguments", "StartCalendarInterval", "StandardOutPath",
                                    "StandardErrorPath"})
        self.assertEqual(job["Label"], "com.agentic-company.intelligence-backup")
        self.assertEqual(job["ProgramArguments"], ["/usr/bin/python3", str(SCRIPTS / "marketing_intelligence_backup.py"), "run"])
        self.assertEqual(job["StartCalendarInterval"], {"Hour": 3, "Minute": 0})
        self.assertEqual(job["StandardOutPath"], job["StandardErrorPath"])
        self.assertTrue(job["StandardOutPath"].endswith("Library/Logs/agentic-company/intelligence-backup.log"))

    def test_the_default_source_and_copy(self):
        self.assertEqual(backup.REPO, SCRIPTS.parent)
        self.assertEqual(str(backup.SOURCE), "workspaces/marketing/intelligence")
        self.assertEqual(backup.COPY, "intelligence-backup")


if __name__ == "__main__":
    unittest.main()
