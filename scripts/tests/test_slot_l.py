"""Tests for slot-L in scripts/hooks/guard_full_suite.py: outside .landing-lock, slot-L counts for a change waiting to go
live while this machine's 5-minute load is below the limit (25 here). The hook's other tests are in
test_guard_full_suite.py, whose fixture this uses."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capacity_scan  # noqa: E402
from test_guard_full_suite import ON_BATTERY, ON_THE_CHARGER, REVIEWER, SENIOR, Guard, guard  # noqa: E402


def load(five_minutes, one=0.0, fifteen=0.0):
    return mock.patch.object(guard.os, "getloadavg", return_value=(one, five_minutes, fifteen))


class SlotL(Guard):
    def assert_waits(self, refusal, shown="is 25.00"):
        """The load's own wait: slot-L names the container, so it isn't told no slot does."""
        self.assertIn(f"{guard.LANDING_SLOT} names {SENIOR}", refusal or "")
        self.assertIn(f"below {guard.LOAD_LIMIT}", refusal)
        self.assertIn(f"it {shown}.", refusal)
        self.assertIn("a wait for the load", refusal)
        self.assertNotIn("no slot names", refusal)
        self.assertNotIn("\n", refusal)

    def test_the_limit_is_capacity_scans(self):
        spec = importlib.util.spec_from_file_location("a_fresh_guard", guard.__file__)
        fresh = importlib.util.module_from_spec(spec)  # this class's own LOAD_LIMIT is 25
        spec.loader.exec_module(fresh)
        self.assertEqual(fresh.LOAD_LIMIT, capacity_scan.LOAD_PER_CPU * (os.cpu_count() or 1))
        self.assertEqual(len(guard.SLOTS), 3)  # never over 3

    def test_a_landing_in_slot_l_runs_below_25(self):
        self.take_slot(guard.LANDING_SLOT)
        for five in (0.0, 13.0, 24.99):
            with self.subTest(load=five), load(five):
                self.assertIsNone(self.refusal(self.suite()))

    def test_at_25_or_more_it_waits(self):
        self.take_slot(guard.LANDING_SLOT)
        for five, shown in ((25.0, "is 25.00"), (25.01, "is 25.01"), (60.0, "is 60.00")):
            with self.subTest(load=five), load(five):
                self.assert_waits(self.refusal(self.suite()), shown)

    def test_only_the_5_minute_load_counts(self):
        self.take_slot(guard.LANDING_SLOT)
        with load(24.0, one=40.0, fifteen=40.0):
            self.assertIsNone(self.refusal(self.suite()))
        with load(25.0, one=1.0, fifteen=1.0):
            self.assert_waits(self.refusal(self.suite()))

    def test_the_hook_reads_the_load_not_the_owner_line(self):
        folder = self.root / guard.SLOT_FOLDER / guard.LANDING_SLOT
        folder.mkdir(parents=True)
        (folder / "owner").write_text(f"senior-engineer /2.1 {SENIOR} 10:20Z load 4.00\n")
        with load(30.0):
            self.assert_waits(self.refusal(self.suite()), "is 30.00")

    def test_a_load_it_cant_read_counts_slot_l_only_under_the_lock(self):
        self.take_slot(guard.LANDING_SLOT)
        with mock.patch.object(guard.os, "getloadavg", side_effect=OSError("no load")):
            self.assert_waits(self.refusal(self.suite()), "can't be read")
        self.assertIn("load check skipped", self.errors())

    def test_the_lock_holder_keeps_slot_l_at_any_load(self):
        self.take_slot(guard.LANDING_SLOT)
        (self.root / guard.LANDING_LOCK).mkdir()
        for five in (0.0, 25.0, 60.0):
            with self.subTest(load=five), load(five):
                self.assertIsNone(self.refusal(self.suite()))
        with mock.patch.object(guard.os, "getloadavg", side_effect=AssertionError("read under the lock")):
            self.assertIsNone(self.refusal(self.suite()))

    def test_slot_1_and_slot_2_dont_read_the_load(self):
        for slot in ("slot-1", "slot-2"):
            with self.subTest(slot=slot):
                self.take_slot(slot)
                for five in (0.0, 60.0):
                    with load(five):
                        self.assertIsNone(self.refusal(self.suite()))
                with mock.patch.object(guard.os, "getloadavg", side_effect=AssertionError("read for " + slot)):
                    self.assertIsNone(self.refusal(self.suite()))
                (self.root / guard.SLOT_FOLDER / slot / "owner").unlink()
                (self.root / guard.SLOT_FOLDER / slot).rmdir()

    def test_the_wait_shows_the_load_it_was_refused_on(self):
        """The load is read once, so a second reading just below 25 never
        shows in a refusal made on the first."""
        self.take_slot(guard.LANDING_SLOT)
        readings = [(0.0, 25.5, 0.0), (0.0, 24.9, 0.0)]
        with mock.patch.object(guard.os, "getloadavg", side_effect=readings) as read:
            self.assert_waits(self.refusal(self.suite()), "is 25.50")
        self.assertEqual(read.call_count, 1)

    def test_another_containers_slot_l_doesnt_count(self):
        self.take_slot("slot-1", REVIEWER)
        self.take_slot("slot-2", REVIEWER)
        self.take_slot(guard.LANDING_SLOT, REVIEWER)
        for five in (0.0, 25.0):
            with self.subTest(load=five), load(five):
                refusal = self.refusal(self.suite())
                self.assertIn(f"no slot names {SENIOR}", refusal or "")
                self.assertIn("a wait for a slot", refusal)
                # every lane reads this line; slot-L is a landing's
                self.assertIn("slot-L counts under .landing-lock, or for a landing while the 5-minute load", refusal)

    def test_every_other_refusal_comes_first(self):
        self.take_slot(guard.LANDING_SLOT)
        with load(0.0):
            refusal = self.refusal(self.suite("bun test"))
            self.assertIn("That's final", refusal or "")
            self.pmset = ON_BATTERY.format(3)
            self.assertIn("on battery at 3%", self.refusal(self.suite()) or "")
            self.pmset = ON_THE_CHARGER
            self.green()
            self.assertIn("already passed in full", self.refusal(self.suite()) or "")


if __name__ == "__main__":
    unittest.main()
