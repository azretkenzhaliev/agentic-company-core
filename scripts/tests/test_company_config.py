"""company_config.py: defaults without the file, the file's own values over them, and a file that can't be parsed."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import company_config as config  # noqa: E402


class CompanyConfig(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, text):
        (self.root / "company.json").write_text(text, encoding="utf-8")

    def test_without_the_file_every_key_is_its_default(self):
        self.assertEqual(config.load(self.root), config.DEFAULTS)
        self.assertEqual(config.timezone(self.root), ZoneInfo("UTC"))
        self.assertIsNone(config.integration("notion", self.root))

    def test_the_file_s_own_keys_win_and_a_missing_one_keeps_its_default(self):
        self.write(json.dumps({"company_name": "Acme", "timezone": "Europe/Paris",
                               "integrations": {"notion": {"page": "x"}, "gmail": {}}}))
        self.assertEqual(config.load(self.root)["company_name"], "Acme")
        self.assertEqual(config.load(self.root)["products"], {})
        self.assertEqual(config.timezone(self.root), ZoneInfo("Europe/Paris"))
        self.assertEqual(config.integration("notion", self.root), {"page": "x"})

    def test_an_integration_with_no_settings_of_its_own_is_still_on(self):
        self.write(json.dumps({"integrations": {"gmail": {}}}))
        self.assertEqual(config.integration("gmail", self.root), {})
        self.assertIsNone(config.integration("notion", self.root))

    def test_a_file_that_can_t_be_parsed_raises(self):
        self.write("{")
        with self.assertRaises(ValueError):
            config.load(self.root)

    def test_the_repo_s_own_file_has_every_key_and_a_known_time_zone(self):
        own = json.loads((config.ROOT / "company.json").read_text(encoding="utf-8"))
        self.assertEqual(set(own), set(config.DEFAULTS))
        self.assertIsInstance(config.timezone(), ZoneInfo)


if __name__ == "__main__":
    unittest.main()
