"""Tests for tools/marketing/footage/fetch.py, with the network, the keychain and yt-dlp replaced:
folders, URLs, hosts and redirects, caps, the yt-dlp arguments and the manifest."""

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "footage"))

import fetch  # noqa: E402


class Reply(io.BytesIO):
    def __init__(self, body: bytes, status=200, headers=None):
        super().__init__(body)
        self.status, self.code, self.headers = status, status, headers or {}


class FetchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "tools/marketing").mkdir(parents=True)
        (self.root / "tools/marketing/caps.json").write_text(json.dumps(
            {"footage_max_mb": 1, "footage_max_minutes": 2, "footage_retries": 1}))
        (self.root / "company.json").write_text('{"integrations": {"marketing": {"public_downloads": true}}}')
        self.limits = fetch.caps(self.root)

    def tearDown(self):
        self.tmp.cleanup()


class Folders(FetchCase):
    def test_each_download_gets_a_new_folder_inside_sources(self):
        folder = fetch.new_folder("founder/demo", "2026-W05", "a-demo", root=self.root)
        self.assertEqual(folder, self.root / "workspaces/marketing/sources/founder/demo/2026-W05/a-demo")
        with self.assertRaises(SystemExit):
            fetch.new_folder("founder/demo", "2026-W05", "a-demo", root=self.root)  # exists
        for bad in [("../x", "2026-W05", "a"), ("founder/demo", "45", "a"), ("founder/demo", "2026-W05", "../a"),
                    ("founder/demo", "2026-W05", "A b")]:
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                fetch.new_folder(*bad, root=self.root)

    def test_a_linked_week_folder_pointing_out_is_refused(self):
        outside = self.root / "elsewhere"
        outside.mkdir()
        (self.root / "workspaces/marketing/sources/founder").mkdir(parents=True)
        (self.root / "workspaces/marketing/sources/founder/demo").symlink_to(outside)
        with self.assertRaises(SystemExit):
            fetch.new_folder("founder/demo", "2026-W05", "a", root=self.root)


class Urls(FetchCase):
    def resolving(self, *addresses):
        return mock.patch.object(fetch.socket, "getaddrinfo", return_value=[(2, 1, 6, "", (a, 0)) for a in addresses])

    def test_only_public_web_addresses(self):
        with self.resolving("142.250.74.110"):
            self.assertEqual(fetch.public_url("https://www.youtube.com/watch?v=abc"), "https://www.youtube.com/watch?v=abc")
            for bad in ["file:///etc/hosts", "ftp://x.test/a.mp4", "https://user:pw@x.test/v", "https://@x.test/v",
                        "http://localhost/v", "http://localhost./v", "http://127.0.0.1/v", "http://127.0.0.1./v",
                        "http://127.1/v", "http://2130706433/v", "http://0x7f.0.0.1/v", "http://[::1]/v",
                        "http://[::ffff:127.0.0.1]/v", "https://printer.local/v", "http://router/v", "javascript:alert(1)"]:
                with self.subTest(bad=bad), self.assertRaises(SystemExit):
                    fetch.public_url(bad)

    def test_a_name_resolving_to_a_private_address_is_refused(self):
        for address in ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "fd00::1"]:
            with self.subTest(address=address), self.resolving("142.250.74.110", address), self.assertRaises(SystemExit):
                fetch.public_url("https://news.example.com/v")

    def test_library_hosts_are_https_and_their_own(self):
        hosts = fetch.LIBRARIES["pexels"]["hosts"]
        self.assertTrue(fetch.allowed("https://videos.pexels.com/video-files/1/a.mp4", hosts))
        self.assertTrue(fetch.allowed("https://player.vimeo.com/external/1.hd.mp4", hosts))
        for bad in ["http://videos.pexels.com/a.mp4", "https://evilpexels.com/a.mp4", "https://pexels.com.evil.test/a.mp4"]:
            with self.subTest(bad=bad):
                self.assertFalse(fetch.allowed(bad, hosts))


class PublicDownloads(FetchCase):
    def test_on_once_marketing_is_set_up(self):
        for settings in ("{}", '{"public_downloads": true}'):
            (self.root / "company.json").write_text('{"integrations": {"marketing": %s}}' % settings)
            with self.subTest(settings=settings):
                self.assertIsNone(fetch.public_ok(self.root))

    def test_a_public_url_is_refused_with_marketing_off_or_when_the_board_turned_it_off(self):
        for settings in ("{}", '{"integrations": {"marketing": {"public_downloads": false}}}',
                         '{"integrations": {"marketing": {"public_downloads": null}}}',
                         '{"integrations": {"marketing": {"public_downloads": "yes"}}}',
                         '{"integrations": {"marketing": false}}', '{"integrations": {"marketing": true}}', None):
            if settings is None:
                (self.root / "company.json").unlink()
            else:
                (self.root / "company.json").write_text(settings)
            with self.subTest(settings=settings), self.assertRaisesRegex(SystemExit, "public site is off"):
                fetch.get_url("https://www.youtube.com/watch?v=abc", ("founder/demo", "2026-W05", "a"), root=self.root)
        self.assertFalse((self.root / "workspaces").exists())

    def test_a_youtube_search_is_refused_where_it_is_off(self):
        (self.root / "company.json").write_text('{"integrations": {"marketing": {"public_downloads": false}}}')
        with mock.patch.object(fetch.subprocess, "run") as run, self.assertRaisesRegex(SystemExit, "public site is off"):
            fetch.search_youtube("a demo", 3, root=self.root)
        run.assert_not_called()


class Downloads(FetchCase):
    def test_a_redirect_off_the_library_is_refused(self):
        hop = urllib.error.HTTPError("https://videos.pexels.com/a.mp4", 302, "Found", {"Location": "https://evil.test/a.mp4"}, None)
        with mock.patch.object(fetch, "open_url", side_effect=hop), self.assertRaises(SystemExit) as caught:
            fetch.download("https://videos.pexels.com/a.mp4", self.root / "v.mp4", fetch.LIBRARIES["pexels"]["hosts"], self.limits)
        self.assertIn("evil.test", str(caught.exception))

    def test_a_redirect_within_the_library_is_followed(self):
        hop = urllib.error.HTTPError("https://videos.pexels.com/a.mp4", 302, "Found", {"Location": "https://player.vimeo.com/b.mp4"}, None)
        with mock.patch.object(fetch, "open_url", side_effect=[hop, Reply(b"video")]):
            fetch.download("https://videos.pexels.com/a.mp4", self.root / "v.mp4", fetch.LIBRARIES["pexels"]["hosts"], self.limits)
        self.assertEqual((self.root / "v.mp4").read_bytes(), b"video")

    def test_the_size_cap_stops_a_download(self):
        with mock.patch.object(fetch, "open_url", return_value=Reply(b"x" * (2 * 1024 * 1024))), self.assertRaises(SystemExit):
            fetch.download("https://cdn.pixabay.com/a.mp4", self.root / "v.mp4", ("pixabay.com",), self.limits)
        self.assertFalse((self.root / "v.mp4").exists())


class Stock(FetchCase):
    PEXELS = {"url": "https://www.pexels.com/video/1/", "duration": 12, "user": {"name": "Ann", "url": "https://www.pexels.com/@ann"},
              "video_files": [{"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "https://videos.pexels.com/4k.mp4"},
                              {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://videos.pexels.com/hd.mp4"},
                              {"file_type": "video/mp4", "width": 540, "height": 960, "link": "https://videos.pexels.com/sd.mp4"}]}

    def test_no_key_skips_with_a_message(self):
        with mock.patch.object(fetch, "read_key", return_value=None), mock.patch("builtins.print") as said:
            self.assertIsNone(fetch.get_stock("pexels", "1", ("founder/demo", "2026-W05", "a"), root=self.root))
        self.assertIn("skipped", said.call_args[0][0])
        self.assertFalse((self.root / "workspaces").exists())

    def test_a_stock_clip_lands_with_its_manifest(self):
        with mock.patch.object(fetch, "read_key", return_value="k"), \
                mock.patch.object(fetch, "get_json", return_value=self.PEXELS), \
                mock.patch.object(fetch, "open_url", return_value=Reply(b"clip")) as opened:
            manifest = fetch.get_stock("pexels", "1", ("founder/demo", "2026-W05", "city-night"), root=self.root)
        self.assertEqual(opened.call_args[0][0], "https://videos.pexels.com/hd.mp4")  # the largest within 1920 px
        entry = json.loads(manifest.read_text())["files"][0]
        self.assertEqual(entry["sha256"], fetch.sha256(manifest.parent / "video.mp4"))
        self.assertEqual((entry["owner"], entry["licence"], entry["source_url"], entry["music_ok"]),
                         ("Ann", "Pexels License", "https://www.pexels.com/video/1/", False))

    def test_ids_are_numbers_and_long_clips_are_refused(self):
        with self.assertRaises(SystemExit):
            fetch.stock_clip("pexels", "1/../2", "k", self.limits)
        with mock.patch.object(fetch, "get_json", return_value={**self.PEXELS, "duration": 999}), self.assertRaises(SystemExit):
            fetch.stock_clip("pexels", "1", "k", self.limits)


class YtDlp(FetchCase):
    def test_the_arguments_keep_it_public_capped_and_single(self):
        made = {}

        def fake_run(args, cwd, **kwargs):
            made["args"], made["cwd"] = args, cwd
            (Path(cwd) / "video.mp4").write_bytes(b"clip")
            (Path(cwd) / "video.info.json").write_text(json.dumps({
                "webpage_url": "https://www.youtube.com/watch?v=abc", "id": "abc", "channel": "Some Channel", "title": "A talk",
                "upload_date": "20260130", "duration": 61, "extractor_key": "Youtube", "license": None}))
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(fetch, "YT_PYTHON", Path(sys.executable)), mock.patch.object(fetch.subprocess, "run", fake_run), \
                mock.patch.object(fetch, "public_url", side_effect=lambda u: u):
            manifest = fetch.get_url("https://www.youtube.com/watch?v=abc", ("founder/demo", "2026-W05", "a-talk"), root=self.root)
        args = made["args"]
        for flag in ["-I", "--ignore-config", "--no-plugin-dirs", "--no-cookies", "--no-cookies-from-browser", "--no-exec", "--no-playlist"]:
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--max-filesize") + 1], "1M")
        self.assertIn("duration <=? 120", args[args.index("--match-filters") + 1])
        self.assertEqual(args[args.index("--retries") + 1], "1")
        self.assertEqual(args[-2:], ["--", "https://www.youtube.com/watch?v=abc"])  # the URL can't be read as an option
        self.assertNotIn("--cookies", args)
        self.assertNotIn("--write-pages", args)  # only Freesound's own page is kept, and only to read its licence
        entry = json.loads(manifest.read_text())["files"][0]
        self.assertEqual((entry["owner"], entry["date"], entry["seconds"], entry["library"]), ("Some Channel", "2026-01-30", 61, "Youtube"))

    def freesound(self, page, slug="a-click", extractor="Freesound"):
        """A Freesound download, as yt-dlp leaves it: the sound, its info (no licence) and the saved page."""
        made = {}

        def fake_run(args, cwd, **kwargs):
            made["args"] = args
            (Path(cwd) / "video.mp3").write_bytes(b"sound")
            (Path(cwd) / "video.info.json").write_text(json.dumps({
                "webpage_url": "https://freesound.org/people/a/sounds/1/", "id": "1", "uploader": "a",
                "title": "click", "extractor_key": extractor, "duration": 1.5}))
            (Path(cwd) / "1_https_-_freesound.org_people_a_sounds_1.dump").write_text(page, encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(fetch, "YT_PYTHON", Path(sys.executable)), mock.patch.object(fetch.subprocess, "run", fake_run), \
                mock.patch.object(fetch, "public_url", side_effect=lambda u: u):
            manifest = fetch.get_url("https://freesound.org/people/a/sounds/1/", ("founder/demo", "2026-W05", slug), root=self.root)
        return made["args"], manifest

    def test_a_freesound_sound_records_the_licence_on_its_page(self):
        page = '<a href="https://creativecommons.org/publicdomain/zero/1.0/" title="the licence">Creative Commons 0</a>'
        args, manifest = self.freesound(page)
        self.assertLess(args.index("--write-pages"), args.index("--"))
        entry = json.loads(manifest.read_text())["files"][0]
        self.assertEqual((entry["licence"], entry["licence_url"], entry["music_ok"]),
                         ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/", False))
        self.assertEqual(list(manifest.parent.glob("*.dump")), [])  # the page isn't kept

    def test_a_freesound_page_without_one_clear_licence_records_none_and_says_so(self):
        two = '<a href="https://creativecommons.org/publicdomain/zero/1.0/">a</a> <a href="https://creativecommons.org/licenses/by-nc/4.0/">b</a>'
        for slug, page in (("no-link", "<p>a click</p>"), ("two-links", two)):
            with self.subTest(slug=slug), mock.patch("builtins.print") as said:
                _, manifest = self.freesound(page, slug)
                entry = json.loads(manifest.read_text())["files"][0]
                self.assertEqual((entry["licence"], entry["licence_url"]), (None, None))
                self.assertIn("no single licence", said.call_args[0][0])
                self.assertEqual(list(manifest.parent.glob("*.dump")), [])

    def test_a_page_on_freesound_that_isnt_a_sound_records_no_licence(self):
        page = '<a href="https://creativecommons.org/publicdomain/zero/1.0/">x</a>'
        _, manifest = self.freesound(page, extractor="Generic")  # a pack or forum page, which yt-dlp's generic extractor took
        entry = json.loads(manifest.read_text())["files"][0]
        self.assertEqual((entry["licence"], entry["licence_url"]), (None, None))
        self.assertEqual(list(manifest.parent.glob("*.dump")), [])

    def test_licence_links_read_as_their_short_name(self):
        for href, name, deed in (
                ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
                ("https://www.creativecommons.org/licenses/by/4.0/", "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
                ("https://creativecommons.org/licenses/by-nc/3.0/deed.en", "CC BY-NC 3.0", "https://creativecommons.org/licenses/by-nc/3.0/"),
                ("https://creativecommons.org/licenses/sampling+/1.0/", "CC SAMPLING+ 1.0", "https://creativecommons.org/licenses/sampling+/1.0/")):
            with self.subTest(href=href):
                self.assertEqual(fetch.freesound_licence([f'<a href="{href}">x</a>'] * 2), (name, deed))  # a repeat is one link

    def test_a_failed_or_too_long_download_leaves_no_folder(self):
        def too_long(args, cwd, **kwargs):
            (Path(cwd) / "video.mp4").write_bytes(b"clip")
            (Path(cwd) / "video.info.json").write_text(json.dumps({"duration": 999}))
            return subprocess.CompletedProcess(args, 0, "", "")
        with mock.patch.object(fetch, "YT_PYTHON", Path(sys.executable)), mock.patch.object(fetch.subprocess, "run", too_long), \
                mock.patch.object(fetch, "public_url", side_effect=lambda u: u), self.assertRaises(SystemExit):
            fetch.get_url("https://www.youtube.com/watch?v=x", ("founder/demo", "2026-W05", "long"), root=self.root)
        self.assertFalse((self.root / "workspaces/marketing/sources/founder/demo/2026-W05/long").exists())

    @unittest.skipUnless(fetch.YT_PYTHON.exists(), "yt-dlp's venv isn't installed (footage/requirements.txt)")
    def test_yt_dlps_own_filter_passes_only_a_missing_duration(self):
        made = {}

        def capture(args, cwd, **kwargs):
            made["args"] = args
            return subprocess.CompletedProcess(args, 1, "", "")
        with mock.patch.object(fetch.subprocess, "run", capture), mock.patch.object(fetch, "public_url", side_effect=lambda u: u), \
                self.assertRaises(SystemExit):
            fetch.get_url("https://www.instagram.com/p/x/", ("founder/demo", "2026-W05", "f"), root=self.root)
        rule = made["args"][made["args"].index("--match-filters") + 1]
        check = "import json, sys; from yt_dlp.utils import match_str; print(json.dumps([match_str(sys.argv[1], d) for d in json.loads(sys.argv[2])]))"
        cases = [{"id": "x"}, {"duration": 61}, {"duration": 200}, {"duration": 61, "is_live": True}]  # the cap here is 120 s
        run = subprocess.run([str(fetch.YT_PYTHON), "-I", "-c", check, rule, json.dumps(cases)], capture_output=True, text=True, timeout=60)
        self.assertEqual(json.loads(run.stdout or "null"), [True, True, False, False], run.stderr)

    def test_a_video_with_no_reported_duration_downloads(self):
        # The manifest's null length; yt-dlp's own filter is checked in the test above.
        def no_duration(args, cwd, **kwargs):  # Instagram reports none
            (Path(cwd) / "video.mp4").write_bytes(b"clip")
            (Path(cwd) / "video.info.json").write_text(json.dumps({"webpage_url": "https://www.instagram.com/p/x/", "id": "x"}))
            return subprocess.CompletedProcess(args, 0, "", "")
        with mock.patch.object(fetch, "YT_PYTHON", Path(sys.executable)), mock.patch.object(fetch.subprocess, "run", no_duration), \
                mock.patch.object(fetch, "public_url", side_effect=lambda u: u):
            manifest = fetch.get_url("https://www.instagram.com/p/x/", ("founder/demo", "2026-W05", "ig"), root=self.root)
        entry = json.loads(manifest.read_text())["files"][0]
        self.assertEqual((entry["file"], entry["seconds"], entry["source_url"]), ("video.mp4", None, "https://www.instagram.com/p/x/"))

    def test_a_filtered_video_says_why_and_leaves_no_folder(self):
        said = "[instagram] x: Downloading JSON metadata\n[download] A reel does not pass filter (!is_live & duration <=? 120), skipping ..\n"
        filtered = lambda args, cwd, **kw: subprocess.CompletedProcess(args, 0, said, "")  # noqa: E731
        with mock.patch.object(fetch, "YT_PYTHON", Path(sys.executable)), mock.patch.object(fetch.subprocess, "run", filtered), \
                mock.patch.object(fetch, "public_url", side_effect=lambda u: u), self.assertRaises(SystemExit) as caught:
            fetch.get_url("https://www.instagram.com/p/x/", ("founder/demo", "2026-W05", "ig"), root=self.root)
        self.assertIn("does not pass filter", str(caught.exception))
        self.assertNotIn("JSON metadata", str(caught.exception))
        self.assertFalse((self.root / "workspaces/marketing/sources/founder/demo/2026-W05/ig").exists())

    def test_abbreviated_flags_are_refused(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            fetch.main(["get", "--u", "https://x.test/v", "--brand", "founder/demo", "--week", "2026-W05", "--slug", "a"])

    def test_a_failed_download_says_so(self):
        failed = lambda args, cwd, **kw: subprocess.CompletedProcess(args, 1, "", "ERROR: Private video")  # noqa: E731
        with mock.patch.object(fetch, "YT_PYTHON", Path(sys.executable)), mock.patch.object(fetch.subprocess, "run", failed), \
                mock.patch.object(fetch, "public_url", side_effect=lambda u: u), self.assertRaises(SystemExit) as caught:
            fetch.get_url("https://www.youtube.com/watch?v=x", ("founder/demo", "2026-W05", "x"), root=self.root)
        self.assertIn("Private video", str(caught.exception))


@unittest.skipUnless(shutil.which("security"), "macOS only")
class Keychain(unittest.TestCase):
    def test_a_missing_item_reads_as_no_key(self):
        with mock.patch.dict(fetch.LIBRARIES, {"pexels": {**fetch.LIBRARIES["pexels"], "keychain": "agentic-company-test-no-such-item"}}):
            self.assertIsNone(fetch.read_key("pexels"))


if __name__ == "__main__":
    unittest.main()
