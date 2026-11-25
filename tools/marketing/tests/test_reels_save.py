"""Tests for tools/marketing/reels/save.py. No network and no instaloader: a fake module stands in for 4.16, keeping its
exception classes and the calls save.py relies on (the rate controller, the csrf fetch, Post.from_shortcode, the
anonymous session and the download status check). Files are synthetic bytes: no third-party image is in git."""

import fcntl
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import zlib
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reels"))

import save  # noqa: E402
import watch  # noqa: E402
import fetch  # noqa: E402

CDN = "https://scontent-fra5-1.cdninstagram.com/v/t51/"
JPEG = b"\xff\xd8\xff\xe0" + bytes(60)
MP4 = b"\x00\x00\x00\x18ftypmp42" + bytes(60)
PNG = b"\x89PNG\r\n\x1a\n" + bytes(56)  # each only its first bytes: sips is stood in for, but in RealSipsTest
WEBP = b"RIFF\x38\x00\x00\x00WEBPVP8L" + bytes(48)
HEIC = b"\x00\x00\x00\x24ftypheic" + bytes(56)
AVIF = b"\x00\x00\x00\x20ftypavif" + bytes(56)
HEADER = ("read_date,week,platform,account,followers,median,post_code,link,views,multiple,age_days,recent_or_old,"
          "language,format,collab,collab_with")
WEEK = "2026-W05"
REASONS = {401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 429: "Too Many Requests"}


def make_library(test):
    lib = types.ModuleType("instaloader")
    lib.__version__ = "4.16"

    class InstaloaderException(Exception):
        pass

    class ConnectionException(InstaloaderException):
        pass

    class QueryReturnedNotFoundException(ConnectionException):
        pass

    class TooManyRequestsException(ConnectionException):
        pass

    class QueryReturnedBadRequestException(InstaloaderException):
        pass

    class QueryReturnedForbiddenException(InstaloaderException):
        pass

    class LoginRequiredException(InstaloaderException):
        pass

    class BadResponseException(InstaloaderException):
        pass

    class AbortDownloadException(Exception):
        pass

    for error in (InstaloaderException, ConnectionException, QueryReturnedNotFoundException, TooManyRequestsException,
                  QueryReturnedBadRequestException, QueryReturnedForbiddenException, LoginRequiredException,
                  BadResponseException, AbortDownloadException):
        setattr(lib, error.__name__, error)

    class RateController:
        def __init__(self, context):
            self._context = context

        def wait_before_query(self, query_type):
            raise AssertionError("save.py replaces this")

    class Context:
        def __init__(self, kwargs):
            self._session = types.SimpleNamespace(cookies=[types.SimpleNamespace(name="csrftoken", value="")])
            self._rate_controller = kwargs["rate_controller"](self)
            self.tokens = None

        def request(self, what):
            test.requests.append((what, len(test.sleeps)))
            if what in test.errors:
                raise test.errors[what]

        def _csrf_token(self):  # as 4.16's: the start page again, past the rate controller, when there's no csrf cookie
            if not any(cookie.name == "csrftoken" and cookie.value for cookie in self._session.cookies):
                self.request("csrf")
                self._session.cookies.append(types.SimpleNamespace(name="csrftoken", value="token"))
            return "token"

        def query(self, code):  # doc_id_graphql_query, logged out: tokens from the start page once, then the csrf token
            if self.tokens is None:
                self._rate_controller.wait_before_query("other")
                self.request("page")
                if test.page_sets_csrf:
                    self._session.cookies.append(types.SimpleNamespace(name="csrftoken", value="token"))
                self.tokens = {}
            self._csrf_token()
            self._rate_controller.wait_before_query("27128499623469141")
            self.request(code)
            return test.posts[code]

        def get_page_data(self, path):  # as 4.16's: one GET of www.instagram.com/<path>, paced as "other"
            self._rate_controller.wait_before_query("other")
            self.request(f"profile:{path}")
            return test.pages[path]

        def get_anonymous_session(self):  # a file: bytes are a 200, an int its status, ("redirect", where) a 302
            context = self

            class Session:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def get(self, url, stream, allow_redirects):
                    test.assertEqual((stream, allow_redirects), (True, False))
                    context.request(url)
                    body, status, location = test.files[url], 200, None
                    if isinstance(body, int):
                        body, status = b"", body
                    elif isinstance(body, tuple):
                        body, status, location = b"", 302, body[1]
                    return types.SimpleNamespace(url=url, status_code=status, is_redirect=location is not None,
                                                 headers={"location": location}, raw=io.BytesIO(body), close=lambda: None)

            return Session()

        def _raise_for_download_status(self, resp):  # as 4.16's
            if resp.status_code == 200:
                return
            text = f"{resp.status_code} {REASONS[resp.status_code]} when accessing {resp.url}"
            if resp.status_code == 403:
                raise QueryReturnedForbiddenException(text)
            if resp.status_code == 404:
                raise QueryReturnedNotFoundException(text)
            raise ConnectionException(text)

    class Instaloader:
        def __init__(self, **kwargs):
            test.kwargs = kwargs
            self.context = Context(kwargs)

        def close(self):
            test.closed = True

    class Post:
        @classmethod
        def from_shortcode(cls, context, code):
            return context.query(code)

    lib.RateController, lib.Instaloader, lib.Post, lib.InstaloaderContext = RateController, Instaloader, Post, Context
    return lib


def image(url=CDN + "a.jpg", caption="Hi @someone, call +49 555 123 4567", account="someaccount"):
    return types.SimpleNamespace(typename="GraphImage", owner_username=account, url=url, caption=caption,
                                 date_utc=datetime(2026, 1, 6), get_sidecar_nodes=lambda: iter(()))


def carousel(nodes, account="some.maker"):
    slides = [types.SimpleNamespace(is_video=video, display_url=display, video_url=video_url)
              for video, display, video_url in nodes]
    return types.SimpleNamespace(typename="GraphSidecar", owner_username=account, url=nodes[0][1], caption=None,
                                 date_utc=datetime(2026, 1, 5), get_sidecar_nodes=lambda: iter(slides))


def profile(*nodes, private=False):
    """What 4.16's get_page_data returns for a profile page: the user, then its first page of posts (none if private)."""
    page = [{"xig_user_by_username": {"pk": "1", "is_private": private}}]
    if not private:
        page.append({"xig_user_by_username": {"id": "x", "polaris_ordered_timeline_connection": {
            "edges": [{"node": node} for node in nodes]}}})
    return page


def node(code, media_type=None, product_type=None):  # the page's nodes may carry no type at all
    return {"code": code, **({"media_type": media_type} if media_type else {}),
            **({"product_type": product_type} if product_type else {})}


def chained(outer, inner):
    try:
        try:
            raise inner
        except Exception as error:
            raise outer from error
    except Exception as error:
        return error


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "workspaces/marketing/intelligence").mkdir(parents=True)
        self.base = self.root / save.POSTS_DIR
        (self.root / "company.json").write_text('{"integrations": {"marketing": {"public_downloads": true}}}')
        self.requests, self.sleeps, self.now = [], [], 0.0
        self.posts, self.files, self.errors, self.pages = {}, {}, {}, {}
        self.page_sets_csrf, self.closed, self.kwargs = True, False, None
        self.library = make_library(self)
        for target, value in ((fetch, {"max_bytes": 1000, "max_seconds": 600, "retries": 1}), (watch, (12.345, True))):
            patcher = mock.patch.object(target, "caps" if target is fetch else "probe", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def run_save(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = save.main(list(argv), root=self.root, sleep=self.sleep, clock=lambda: self.now,
                             rand=lambda low, high: 12, library=lambda: self.library)
        return code, out.getvalue()

    def assertPaced(self):
        """Every request came after a pause of its own."""
        self.assertEqual([pauses for _, pauses in self.requests], list(range(1, len(self.requests) + 1)))
        self.assertTrue(all(10 <= pause <= 15 for pause in self.sleeps))

    def manifest(self, code):
        return json.loads((self.base / code / "MANIFEST.json").read_text(encoding="utf-8"))

    def stored(self):
        return (self.base / "stopped.txt").read_text(encoding="utf-8")


class PostTest(SaveTest):
    def test_an_image_post(self):
        self.posts["AbCdEfGhI01"] = image()
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("post", "--code", "AbCdEfGhI01")
        self.assertEqual(code, 0, out)
        folder = self.base / "AbCdEfGhI01"
        self.assertEqual((folder / "1.jpg").read_bytes(), JPEG)
        self.assertEqual((folder / "caption.txt").read_text(encoding="utf-8"), "Hi @..., call ...\n")
        self.assertEqual(self.manifest("AbCdEfGhI01"), {
            "kind": "post", "code": "AbCdEfGhI01", "account": "someaccount", "date": "2026-01-06",
            "description": "Hi @..., call ...", "slides": [{"file": "1.jpg", "type": "image"}], "cover": "1.jpg"})
        self.assertEqual(sorted(path.name for path in self.base.iterdir()), [".lock", "AbCdEfGhI01"])  # no temporary folder
        self.assertEqual([what for what, _ in self.requests], ["page", "AbCdEfGhI01", CDN + "a.jpg"])
        self.assertPaced()
        self.assertTrue(self.closed)
        self.assertEqual({key: self.kwargs[key] for key in ("sleep", "max_connection_attempts", "fatal_status_codes",
                                                            "iphone_support")},
                         {"sleep": False, "max_connection_attempts": 1, "fatal_status_codes": [401, 403, 429],
                          "iphone_support": False})
        self.assertIn("saved 1 this run.", out)

    def test_a_carousel_with_video_slides_opening_on_a_video(self):
        self.posts["AbCdEfGhI02"] = carousel([(True, CDN + "1c.jpg", CDN + "1.mp4"), (False, CDN + "2.jpg", None),
                                              (True, CDN + "3c.jpg", CDN + "3.mp4")])
        self.files.update({CDN + "1.mp4": MP4, CDN + "2.jpg": JPEG, CDN + "3.mp4": MP4, CDN + "1c.jpg": JPEG})
        code, out = self.run_save("post", "--code", "AbCdEfGhI02")
        self.assertEqual(code, 0, out)
        manifest = self.manifest("AbCdEfGhI02")
        self.assertEqual(manifest["slides"], [{"file": "1.mp4", "type": "video", "seconds": 12.35},
                                              {"file": "2.jpg", "type": "image"},
                                              {"file": "3.mp4", "type": "video", "seconds": 12.35}])
        self.assertEqual((manifest["kind"], manifest["cover"], manifest["description"]), ("carousel", "cover.jpg", ""))
        self.assertEqual(sorted(path.name for path in (self.base / "AbCdEfGhI02").iterdir()),
                         ["1.mp4", "2.jpg", "3.mp4", "MANIFEST.json", "caption.txt", "cover.jpg"])
        self.assertPaced()

    def test_a_reel_is_refused_and_recorded(self):
        self.posts["DemoCode00H"] = types.SimpleNamespace(typename="GraphVideo")
        code, out = self.run_save("post", "--code", "DemoCode00H")
        self.assertEqual(code, 0)
        self.assertIn("watch.py saves reels", (self.base / "DemoCode00H" / "failed.txt").read_text(encoding="utf-8"))
        self.assertFalse((self.base / "DemoCode00H" / "MANIFEST.json").exists())

    def test_a_file_off_instagrams_cdn_is_never_fetched_or_kept(self):
        for code, url in (("Code00001", "https://example.com/a.jpg"), ("Code00002", "http://x.cdninstagram.com/a.jpg"),
                          ("Code00003", "https://evil.com@x.cdninstagram.com/a.jpg"), ("Code00004", None)):
            self.posts[code] = image(url=url)
        self.posts["Code00005"] = image()
        self.files[CDN + "a.jpg"] = ("redirect", "https://example.com/elsewhere.jpg")  # never requested
        code, out = self.run_save("post", "--code", "Code00001", "Code00002")
        self.assertEqual(code, 0, out)
        code, out = self.run_save("post", "--code", "Code00003", "Code00004", "Code00005")
        self.assertEqual(code, 2, out)  # the third failure in a row stops the run
        fetched = [what for what, _ in self.requests if str(what).startswith("http")]
        self.assertEqual(fetched, [CDN + "a.jpg"])
        for number in range(1, 6):
            self.assertFalse((self.base / f"Code0000{number}" / "MANIFEST.json").exists())
        self.assertIn("redirected off", (self.base / "Code00005" / "failed.txt").read_text(encoding="utf-8"))

    def test_a_redirect_on_the_cdn_is_followed_by_hand_and_paced(self):
        self.posts["Code00001"] = image(url=CDN + "r.jpg")
        other = "https://scontent-ams2-1.cdninstagram.com/v/t51/a.jpg"
        self.files.update({CDN + "r.jpg": ("redirect", other), other: ("redirect", "/v/t51/b.jpg"),
                           "https://scontent-ams2-1.cdninstagram.com/v/t51/b.jpg": JPEG})
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 0, out)
        self.assertEqual([what for what, _ in self.requests],
                         ["page", "Code00001", CDN + "r.jpg", other, "https://scontent-ams2-1.cdninstagram.com/v/t51/b.jpg"])
        self.assertPaced()
        self.assertEqual((self.base / "Code00001" / "1.jpg").read_bytes(), JPEG)

    def test_more_than_three_redirects_fail_the_post(self):
        self.posts["Code00001"] = image(url=CDN + "0.jpg")
        self.files.update({CDN + f"{hop}.jpg": ("redirect", CDN + f"{hop + 1}.jpg") for hop in range(5)})
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 0, out)
        self.assertEqual([what for what, _ in self.requests][2:], [CDN + f"{hop}.jpg" for hop in range(4)])
        self.assertIn("more than 3 times", (self.base / "Code00001" / "failed.txt").read_text(encoding="utf-8"))

    def test_a_cdn_401_403_or_429_stops_the_run_and_a_404_fails_only_its_post(self):
        for status in (401, 403, 429):
            with self.subTest(status):
                (self.base / "stopped.txt").unlink(missing_ok=True)
                self.requests.clear()
                self.posts.update({"Code00001": image(), "Code00002": image()})
                self.files[CDN + "a.jpg"] = status
                code, out = self.run_save("post", "--code", "Code00001", "Code00002")
                self.assertEqual(code, 2, out)
                self.assertIn(str(status), self.stored())
                self.assertNotIn("http", self.stored())
                self.assertNotIn("Code00002", [what for what, _ in self.requests])
        (self.base / "stopped.txt").unlink()
        self.posts["Code00003"] = image(url=CDN + "gone.jpg")
        self.files[CDN + "gone.jpg"] = 404
        self.posts["Code00004"] = image()
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("post", "--code", "Code00003", "Code00004")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.base / "Code00003" / "failed.txt").read_text(encoding="utf-8"),
                         "QueryReturnedNotFoundException\n")
        self.assertTrue((self.base / "Code00004" / "MANIFEST.json").is_file())

    def test_bytes_that_arent_the_files_kind_or_are_too_big_fail(self):
        self.posts["Code00001"] = image(url=CDN + "fake.jpg")
        self.posts["Code00002"] = image(url=CDN + "big.jpg")
        self.files.update({CDN + "fake.jpg": b"<html>" + bytes(40), CDN + "big.jpg": JPEG * 20})
        code, out = self.run_save("post", "--code", "Code00001", "Code00002")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.base / "Code00001" / "failed.txt").read_text(encoding="utf-8"),
                         "1.jpg isn't an image we take: HTML, 46 bytes\n")
        self.assertIn("over the cap", (self.base / "Code00002" / "failed.txt").read_text(encoding="utf-8"))

    def test_refusals_stop_the_run_and_are_stored_without_urls(self):
        lib = self.library
        cases = {
            "401": ("Code00001", lib.AbortDownloadException(
                'Query to https://www.instagram.com/api/graphql responded with "401 Unauthorized".')),
            "feedback_required": ("Code00001", lib.AbortDownloadException(
                '400 Bad Request - "fail" status, message "feedback_required" when accessing https://www.instagram.com/x')),
            "400 feedback_required": ("Code00001", lib.QueryReturnedBadRequestException(
                '400 Bad Request - "fail" status, message "feedback_required" when accessing https://www.instagram.com/x')),
            "429": ("page", lib.ConnectionException("429 Too Many Requests when accessing https://www.instagram.com/")),
            "LoginRequiredException": ("page", lib.LoginRequiredException("Redirected to login page.")),
            "403": (CDN + "a.jpg", lib.QueryReturnedForbiddenException(f"403 Forbidden when accessing {CDN}a.jpg?sig=1")),
            "TooManyRequestsException": ("Code00001", chained(lib.ConnectionException("JSON Query to api/graphql: x"),
                                                              lib.TooManyRequestsException("Too many"))),
            "checkpoint": ("Code00001", lib.ConnectionException("JSON Query to api/graphql: checkpoint_required")),
            "wait a few minutes": ("Code00001", lib.ConnectionException('"Please wait a few minutes before you try again."')),
        }
        for signal, (where, error) in cases.items():
            with self.subTest(signal):
                (self.base / "stopped.txt").unlink(missing_ok=True)
                self.requests.clear()
                self.errors = {where: error}
                self.posts.update({"Code00001": image(), "Code00002": image()})
                self.files[CDN + "a.jpg"] = JPEG
                code, out = self.run_save("post", "--code", "Code00001", "Code00002")
                self.assertEqual(code, 2, out)
                self.assertIn(signal, self.stored())
                self.assertNotIn("http", self.stored())
                self.assertNotIn("Code00002", [what for what, _ in self.requests])
                self.assertFalse((self.base / "Code00001" / "failed.txt").exists())

    def test_other_errors_fail_the_post_by_their_class_name_and_the_run_goes_on(self):
        lib = self.library
        self.errors = {"Code00001": chained(lib.ConnectionException(f"JSON Query to api/graphql: 404 Not Found {CDN}"),
                                            lib.QueryReturnedNotFoundException("404 Not Found")),
                       "Code00002": lib.BadResponseException("Fetching Post metadata failed.")}
        self.posts["Code00003"] = image()
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("post", "--code", "Code00001", "Code00002", "Code00003")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.base / "Code00001" / "failed.txt").read_text(encoding="utf-8"), "ConnectionException\n")
        self.assertEqual((self.base / "Code00002" / "failed.txt").read_text(encoding="utf-8"), "BadResponseException\n")
        self.assertTrue((self.base / "Code00003" / "MANIFEST.json").is_file())

    def test_a_400_without_feedback_required_fails_only_its_post(self):
        self.errors = {"Code00001": self.library.QueryReturnedBadRequestException(
            '400 Bad Request - "fail" status, message "useragent mismatch" when accessing https://www.instagram.com/x')}
        self.posts["Code00002"] = image()
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("post", "--code", "Code00001", "Code00002")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.base / "Code00001" / "failed.txt").read_text(encoding="utf-8"),
                         "QueryReturnedBadRequestException\n")
        self.assertTrue((self.base / "Code00002" / "MANIFEST.json").is_file())

    def test_three_failures_in_a_row_stop_the_run(self):
        self.errors = {code: self.library.BadResponseException("no") for code in ("Code00001", "Code00002", "Code00003")}
        self.posts["Code00004"] = image()
        code, out = self.run_save("post", "--code", "Code00001", "Code00002", "Code00003", "Code00004")
        self.assertEqual(code, 2, out)
        self.assertIn("3 failures in a row", self.stored())
        self.assertNotIn("Code00004", [what for what, _ in self.requests])

    def test_a_stored_stop_fetches_nothing_until_retry_failed(self):
        self.base.mkdir()
        (self.base / "stopped.txt").write_text("stopped: Instagram refused us (429)\n", encoding="utf-8")
        self.posts["Code00001"] = image()
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 2)
        self.assertIn("Only --retry-failed", out)
        self.assertEqual(self.requests, [])
        code, out = self.run_save("post", "--code", "Code00001", "--retry-failed")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.base / "stopped.txt").exists())
        self.assertTrue((self.base / "Code00001" / "MANIFEST.json").is_file())

    def test_failed_and_saved_posts_are_skipped_and_retry_failed_clears_the_record(self):
        self.posts.update({"Code00001": image(), "Code00002": image()})
        self.files[CDN + "a.jpg"] = JPEG
        self.run_save("post", "--code", "Code00001")
        (self.base / "Code00002").mkdir()
        (self.base / "Code00002" / "failed.txt").write_text("BadResponseException\n", encoding="utf-8")
        self.requests.clear()
        code, out = self.run_save("post", "--code", "Code00001", "Code00002", "Code00001")
        self.assertEqual((code, self.requests), (0, []))
        self.assertIn("Code00001: saved already", out)
        self.assertIn("Code00002: failed before", out)
        code, out = self.run_save("post", "--code", "Code00002", "--retry-failed")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.base / "Code00002" / "failed.txt").exists())
        self.assertTrue((self.base / "Code00002" / "MANIFEST.json").is_file())

    def test_the_cap_of_requests_ends_the_run_with_nothing_half_saved(self):
        codes = [f"Code{number:05}" for number in range(1, 11)]
        for code in codes:
            self.posts[code] = image()
        self.posts["Code00011"] = carousel([(False, CDN + "1.jpg", None), (False, CDN + "2.jpg", None),
                                            (False, CDN + "3.jpg", None)])
        self.files.update({CDN + "a.jpg": JPEG, CDN + "1.jpg": JPEG, CDN + "2.jpg": JPEG, CDN + "3.jpg": JPEG})
        code, out = self.run_save("post", "--code", *codes, "Code00011")
        self.assertEqual(code, 0, out)
        self.assertIn("used up: run it again", out)
        self.assertEqual(len(self.requests), 22)  # the start page, 10 posts of 2, and the carousel's metadata: 3 files won't fit
        self.assertFalse((self.base / "Code00011").exists())
        self.assertIn("saved 10 this run.", out)

    def test_the_csrf_fetch_is_paced_too(self):
        self.page_sets_csrf = False
        self.posts["Code00001"] = image()
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 0, out)
        self.assertEqual([what for what, _ in self.requests], ["page", "csrf", "Code00001", CDN + "a.jpg"])
        self.assertPaced()


class KindTest(unittest.TestCase):
    def test_first_bytes_name_the_kind(self):
        cases = {JPEG: "JPEG", PNG: "PNG", WEBP: "WebP", HEIC: "HEIC", b"\x00\x00\x00\x18ftypmif1": "HEIC",
                 b"\x00\x00\x00\x18ftypheix": "HEIC", AVIF: "AVIF", MP4: "MP4", b"\x00\x00\x00\x18ftypisom": "MP4",
                 b"<!DOCTYPE html>": "HTML", b"\n  <html>": "HTML", b"": "empty", b"GIF89a" + bytes(10): "unknown",
                 bytes(30): "unknown", b"RIFF\x24\x00\x00\x00WAVEfmt ": "unknown", b"\x89PNG": "unknown"}
        for head, kind in cases.items():
            with self.subTest(head):
                self.assertEqual(save.kind_of(head), kind)


class ImageTest(SaveTest):
    """An image slot takes a JPEG as it is and a PNG, WebP, HEIC or AVIF made a JPEG by sips (stood in for here)."""

    def setUp(self):
        super().setUp()
        self.converted = []

        def to_jpeg(source, target, limit, what):
            self.converted.append((source.name, source.read_bytes(), target.name, limit, what))
            target.write_bytes(JPEG)

        patcher = mock.patch.object(save, "to_jpeg", side_effect=to_jpeg)
        self.to_jpeg = patcher.start()
        self.addCleanup(patcher.stop)

    def test_png_webp_heic_and_avif_are_stored_as_jpegs_and_a_jpeg_as_it_is(self):
        self.posts["AbCdEfGhI02"] = carousel([(True, CDN + "c.webp", CDN + "1.mp4"), (False, CDN + "2.png", None),
                                              (False, CDN + "3.heic", None), (False, CDN + "4.avif", None),
                                              (False, CDN + "5.jpg", None)])
        self.files.update({CDN + "c.webp": WEBP, CDN + "1.mp4": MP4, CDN + "2.png": PNG, CDN + "3.heic": HEIC,
                           CDN + "4.avif": AVIF, CDN + "5.jpg": JPEG})
        code, out = self.run_save("post", "--code", "AbCdEfGhI02")
        self.assertEqual(code, 0, out)
        self.assertEqual([call[:4] for call in self.converted],
                         [("2.png", PNG, "2.jpg", 1000), ("3.heic", HEIC, "3.jpg", 1000), ("4.avif", AVIF, "4.jpg", 1000),
                          ("cover.webp", WEBP, "cover.jpg", 1000)])
        self.assertEqual(self.converted[0][4], "2.jpg, a PNG of 64 bytes,")
        folder = self.base / "AbCdEfGhI02"
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ["1.mp4", "2.jpg", "3.jpg", "4.jpg", "5.jpg", "MANIFEST.json", "caption.txt", "cover.jpg"])
        for name in ("2.jpg", "3.jpg", "4.jpg", "5.jpg", "cover.jpg"):
            self.assertEqual((folder / name).read_bytes(), JPEG)
        manifest = self.manifest("AbCdEfGhI02")
        self.assertEqual(manifest["slides"], [{"file": "1.mp4", "type": "video", "seconds": 12.35},
                                              *({"file": f"{place}.jpg", "type": "image"} for place in range(2, 6))])
        self.assertEqual(manifest["cover"], "cover.jpg")
        self.assertEqual(sorted(path.name for path in self.base.iterdir()), [".lock", "AbCdEfGhI02"])
        self.assertPaced()

    def test_html_empty_and_unknown_bodies_fail_by_kind_and_size_and_three_stop_the_run(self):
        bodies = {"Code00001": b"\n<!DOCTYPE html><html>" + bytes(10), "Code00002": b"", "Code00003": b"GIF89a" + bytes(24)}
        for code, body in bodies.items():
            self.posts[code] = image(url=CDN + code + ".jpg")
            self.files[CDN + code + ".jpg"] = body
        self.posts["Code00004"] = image()
        code, out = self.run_save("post", "--code", *bodies, "Code00004")
        self.assertEqual(code, 2, out)
        for code, found in (("Code00001", "HTML, 32 bytes"), ("Code00002", "empty, 0 bytes"),
                            ("Code00003", "unknown, 30 bytes")):
            self.assertEqual((self.base / code / "failed.txt").read_text(encoding="utf-8"),
                             f"1.jpg isn't an image we take: {found}\n")
            self.assertFalse((self.base / code / "MANIFEST.json").exists())
        self.assertIn("3 failures in a row", self.stored())
        self.assertIn("Last reason: 1.jpg isn't an image we take: unknown, 30 bytes", self.stored())
        self.assertNotIn("Code00004", [what for what, _ in self.requests])
        self.assertEqual(self.converted, [])

    def test_a_video_slot_takes_only_an_mp4(self):
        self.posts["Code00001"] = carousel([(True, CDN + "1c.jpg", CDN + "1.mp4")])
        self.files.update({CDN + "1.mp4": HEIC, CDN + "1c.jpg": JPEG})
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.base / "Code00001" / "failed.txt").read_text(encoding="utf-8"),
                         "1.mp4 isn't an MP4: HEIC, 68 bytes\n")
        self.assertEqual(self.converted, [])

    def test_a_failed_conversion_fails_its_post_and_leaves_no_file(self):
        self.to_jpeg.side_effect = save.Failed("1.jpg, a WebP of 64 bytes, wasn't made a JPEG: sips failed")
        self.posts["Code00001"] = image(url=CDN + "a.webp")
        self.files[CDN + "a.webp"] = WEBP
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.base / "Code00001" / "failed.txt").read_text(encoding="utf-8"),
                         "1.jpg, a WebP of 64 bytes, wasn't made a JPEG: sips failed\n")
        self.assertEqual(sorted(path.name for path in (self.base / "Code00001").iterdir()), ["failed.txt"])
        self.assertEqual(sorted(path.name for path in self.base.iterdir()), [".lock", "Code00001"])


class ToJpegTest(unittest.TestCase):
    """to_jpeg with sips stood in for: what it runs, and each way it fails, never with sips's command line."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.source, self.target = Path(temp.name) / "1.webp", Path(temp.name) / "1.jpg"
        self.source.write_bytes(WEBP)
        self.calls = []

    def to_jpeg(self, writes=None, returncode=0, error=None):
        def run(argv, **kwargs):
            self.calls.append((argv, kwargs))
            if error:
                raise error
            if writes is not None:
                self.target.write_bytes(writes)
            return subprocess.CompletedProcess(argv, returncode, b"", b"")

        with mock.patch.object(save.subprocess, "run", side_effect=run):
            save.to_jpeg(self.source, self.target, 1000, "1.jpg, a WebP of 64 bytes,")

    def test_it_runs_macos_sips_with_no_input_and_a_time_limit(self):
        self.to_jpeg(writes=JPEG)
        self.assertEqual(self.calls, [(["/usr/bin/sips", "-s", "format", "jpeg", str(self.source), "--out",
                                        str(self.target)],
                                       {"stdin": subprocess.DEVNULL, "capture_output": True, "timeout": 30})])
        self.assertEqual(self.target.read_bytes(), JPEG)

    def test_each_failure_fails_the_post_without_sipss_command_line(self):
        cases = (
            ({"returncode": 1, "writes": JPEG}, "wasn't made a JPEG: sips failed"),
            ({}, "wasn't made a JPEG: sips failed"),  # nothing written
            ({"writes": PNG}, "wasn't made a JPEG: sips wrote something else"),
            ({"writes": JPEG * 20}, "made a JPEG over the cap"),
            ({"error": subprocess.TimeoutExpired(["/usr/bin/sips", str(self.source)], 30)},
             "wasn't made a JPEG: sips ran over 30 s"),
            ({"error": FileNotFoundError(2, "No such file", "/usr/bin/sips")},
             "wasn't made a JPEG: sips can't run here (FileNotFoundError)"),
        )
        for kwargs, text in cases:
            with self.subTest(text):
                self.target.unlink(missing_ok=True)
                with self.assertRaises(save.Failed) as caught:
                    self.to_jpeg(**kwargs)
                self.assertEqual(str(caught.exception), f"1.jpg, a WebP of 64 bytes, {text}"
                                 + (" of 0 MB" if "cap" in text else ""))
                self.assertIsNone(caught.exception.__context__)  # refusal() reads an error's context


def png() -> bytes:
    """A 2x2 PNG, red over blue, built here."""
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))

    rows = b"\x00" + b"\xff\x00\x00" * 2 + b"\x00" + b"\x00\x00\xff" * 2
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def webp() -> bytes:
    """A 1x1 lossless WebP, red, built bit by bit: no transform, no colour cache, five one-symbol prefix codes."""
    bits = []

    def put(value, count):
        bits.extend((value >> place) & 1 for place in range(count))

    put(0x2F, 8)
    for value, count in ((0, 14), (0, 14), (0, 1), (0, 3), (0, 1), (0, 1), (0, 1)):  # 1x1, no alpha, version 0, ...
        put(value, count)
    for symbol in (0, 255, 0, 255, 0):  # green, red, blue, alpha, distance
        for value, count in ((1, 1), (0, 1), (1, 1), (symbol, 8)):  # a simple code of one 8-bit symbol
            put(value, count)
    data = bytes(sum(bit << place for place, bit in enumerate(bits[at:at + 8])) for at in range(0, len(bits), 8))
    chunk = b"VP8L" + struct.pack("<I", len(data)) + data + b"\x00" * (len(data) % 2)
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


@unittest.skipUnless(os.path.exists(save.SIPS), "macOS's sips isn't here")
class RealSipsTest(SaveTest):
    """macOS's own sips on images built here: a PNG and a WebP, and a HEIC and an AVIF it makes from the PNG."""

    def setUp(self):
        super().setUp()
        made = self.root / "made"
        made.mkdir()
        (made / "a.png").write_bytes(png())
        for kind in ("heic", "avif"):
            subprocess.run([save.SIPS, "-s", "format", kind, str(made / "a.png"), "--out", str(made / f"a.{kind}")],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=True)
        self.images = {"PNG": png(), "WebP": webp(), "HEIC": (made / "a.heic").read_bytes(),
                       "AVIF": (made / "a.avif").read_bytes()}

    def test_its_first_bytes_name_each_kind_and_sips_makes_each_a_jpeg(self):
        for kind, data in self.images.items():
            with self.subTest(kind):
                self.assertEqual(save.kind_of(data[:64]), kind)
                source, target = self.root / f"x.{kind.lower()}", self.root / "x.jpg"
                source.write_bytes(data)
                target.unlink(missing_ok=True)
                save.to_jpeg(source, target, 10**6, "x.jpg")
                self.assertEqual(save.kind_of(target.read_bytes()[:64]), "JPEG")
        (self.root / "x.html").write_bytes(b"<html><body>not an image</body></html>")
        (self.root / "x.jpg").unlink()
        with self.assertRaises(save.Failed) as caught:
            save.to_jpeg(self.root / "x.html", self.root / "x.jpg", 10**6, "x.jpg")
        self.assertIn("sips failed", str(caught.exception))

    def test_a_carousel_of_each_kind_is_saved_as_jpegs(self):
        self.posts["AbCdEfGhI02"] = carousel([(False, CDN + f"{kind}.img", None) for kind in self.images])
        self.files.update({CDN + f"{kind}.img": data for kind, data in self.images.items()})
        with mock.patch.object(fetch, "caps", return_value={"max_bytes": 10**6, "max_seconds": 600, "retries": 1}):
            code, out = self.run_save("post", "--code", "AbCdEfGhI02")  # sips's HEIC and AVIF outgrow the 1000 bytes
        self.assertEqual(code, 0, out)
        folder = self.base / "AbCdEfGhI02"
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ["1.jpg", "2.jpg", "3.jpg", "4.jpg", "MANIFEST.json", "caption.txt"])
        for place in range(1, 5):
            self.assertEqual(save.kind_of((folder / f"{place}.jpg").read_bytes()[:64]), "JPEG")
        self.assertEqual(self.manifest("AbCdEfGhI02")["slides"],
                         [{"file": f"{place}.jpg", "type": "image"} for place in range(1, 5)])


class PaceTest(unittest.TestCase):
    def test_caps_on_requests_and_time(self):
        now = [0.0]
        pace = save.Pace(lambda seconds: now.__setitem__(0, now[0] + seconds), lambda: now[0], lambda low, high: high)
        for _ in range(save.MAX_FETCHES):
            pace.wait()
        self.assertFalse(pace.room(1))
        with self.assertRaises(save.Full):
            pace.wait()
        pace = save.Pace(lambda seconds: None, lambda: now[0], lambda low, high: high)
        now[0] += save.RUN_SECONDS - 14
        self.assertFalse(pace.room(1))
        with self.assertRaises(save.Full):
            pace.wait()


class OffTest(SaveTest):
    def test_nothing_is_fetched_where_public_downloads_are_off(self):
        for settings in ("{}", '{"integrations": {"marketing": {"public_downloads": false}}}',
                         '{"integrations": {"marketing": {"public_downloads": 1}}}', None):
            if settings is None:
                (self.root / "company.json").unlink()
            else:
                (self.root / "company.json").write_text(settings)
            with self.subTest(settings=settings), self.assertRaisesRegex(SystemExit, "public site is off"):
                self.run_save("post", "--code", "AbCdEfGhI01")
        self.assertEqual(self.requests, [])


class CoverTest(SaveTest):
    def reel(self, code, measured=True, cover=False, failed=False):
        folder = self.root / watch.REELS / code
        folder.mkdir(parents=True)
        if measured:
            (folder / "metrics.json").write_text("{}", encoding="utf-8")
        if cover:
            (folder / "cover.jpg").write_bytes(JPEG)
        if failed:
            (folder / "cover-failed.txt").write_text("BadResponseException\n", encoding="utf-8")
        return f"2026-01-06,{WEEK},instagram,someone,1000,100,{code},https://www.instagram.com/reel/{code}/,500,5,3,recent,,,,"

    def test_covers_for_the_weeks_measured_reels_that_have_none(self):
        rows = [self.reel("Reel00001"), self.reel("Reel00002", cover=True), self.reel("Reel00003", measured=False),
                self.reel("Reel00004", failed=True)]
        (self.root / watch.POSTS).write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
        for code in ("Reel00001", "Reel00004"):
            self.posts[code] = types.SimpleNamespace(typename="GraphVideo", url=CDN + code + ".jpg")
            self.files[CDN + code + ".jpg"] = JPEG
        code, out = self.run_save("covers", "--week", WEEK)
        self.assertEqual(code, 0, out)
        reels = self.root / watch.REELS
        self.assertEqual((reels / "Reel00001" / "cover.jpg").read_bytes(), JPEG)
        self.assertFalse((reels / "Reel00003" / "cover.jpg").exists())
        self.assertFalse((reels / "Reel00004" / "cover.jpg").exists())
        self.assertEqual([what for what, _ in self.requests], ["page", "Reel00001", CDN + "Reel00001.jpg"])
        self.assertPaced()
        code, out = self.run_save("covers", "--week", WEEK, "--retry-failed", "--count", "1")
        self.assertEqual(code, 0, out)
        self.assertTrue((reels / "Reel00004" / "cover.jpg").is_file())
        self.assertFalse((reels / "Reel00004" / "cover-failed.txt").exists())
        self.assertEqual(sorted(path.name for path in reels.iterdir() if path.name.startswith(".")), [])
        self.assertEqual(sorted(path.name for path in self.base.iterdir()), [".lock"])  # the covers' temporary folders

    def test_a_failed_cover_is_recorded_beside_the_reel(self):
        (self.root / watch.POSTS).write_text(HEADER + "\n" + self.reel("Reel00001") + "\n", encoding="utf-8")
        self.posts["Reel00001"] = types.SimpleNamespace(typename="GraphVideo", url=CDN + "c.jpg")
        self.files[CDN + "c.jpg"] = MP4
        code, out = self.run_save("covers", "--week", WEEK)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.root / watch.REELS / "Reel00001" / "cover-failed.txt").read_text(encoding="utf-8"),
                         "cover.jpg isn't an image we take: MP4, 72 bytes\n")
        self.assertFalse((self.root / watch.REELS / "Reel00001" / "cover.jpg").exists())


class LatestTest(SaveTest):
    def test_the_latest_posts_that_arent_reels_are_saved_as_post_saves_them(self):
        self.pages["someaccount/"] = profile(node("Code00001", 1), node("Reel00001", 2, "clips"), node("Code00002", 8),
                                            node("Reel00002", product_type="clips"), node("Code00003"))
        self.posts.update({"Code00001": image(), "Code00003": image(),
                           "Code00002": carousel([(False, CDN + "1.jpg", None), (False, CDN + "2.jpg", None)])})
        self.files.update({CDN + "a.jpg": JPEG, CDN + "1.jpg": JPEG, CDN + "2.jpg": JPEG})
        code, out = self.run_save("latest", "--account", "SomeAccount", "--count", "2")
        self.assertEqual(code, 0, out)
        self.assertIn("someaccount: its page lists 5 posts; 2 left out, as reels or videos the page marked or an "
                      "earlier run found.", out)
        self.assertIn("Code00001: saved (post)", out)
        self.assertIn("Code00002: saved (carousel)", out)
        self.assertEqual(self.manifest("Code00002")["kind"], "carousel")
        self.assertFalse((self.base / "Code00003").exists())
        self.assertEqual([what for what, _ in self.requests], ["profile:someaccount/", "page", "Code00001", CDN + "a.jpg",
                                                               "Code00002", CDN + "1.jpg", CDN + "2.jpg"])
        self.assertPaced()
        self.assertTrue(self.closed)
        self.requests.clear()
        code, out = self.run_save("latest", "--account", "someaccount", "--count", "3")
        self.assertEqual(code, 0, out)
        self.assertIn("Code00001: saved already", out)
        self.assertIn("Code00003: saved (post)", out)
        self.assertEqual([what for what, _ in self.requests], ["profile:someaccount/", "page", "Code00003", CDN + "a.jpg"])

    def test_a_reel_the_page_didnt_mark_is_recorded_and_the_next_post_takes_its_place(self):
        self.pages["someaccount/"] = profile(node("Reel00001"), node("Reel00002"), node("Reel00003"), node("Code00001"),
                                            node("Code00002"))
        for code in ("Reel00001", "Reel00002", "Reel00003"):
            self.posts[code] = types.SimpleNamespace(typename="GraphVideo")
        self.posts.update({"Code00001": image(), "Code00002": image()})
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("latest", "--account", "someaccount", "--count", "4")
        self.assertEqual(code, 0, out)  # three reels in a row aren't three failures
        self.assertIn("Reel00003: skipped: a reel or a video", out)
        self.assertIn("Code00001: saved (post)", out)
        self.assertFalse((self.base / "stopped.txt").exists())
        self.assertFalse((self.base / "Code00002").exists())
        self.assertEqual((self.base / "Reel00001" / "failed.txt").read_text(encoding="utf-8"), save.REEL + "\n")
        self.requests.clear()
        code, out = self.run_save("latest", "--account", "someaccount", "--count", "2")
        self.assertEqual(code, 0, out)
        self.assertIn("its page lists 5 posts; 3 left out", out)
        self.assertEqual([what for what, _ in self.requests], ["profile:someaccount/", "page", "Code00002", CDN + "a.jpg"])

    def test_three_failures_in_a_row_still_stop_it(self):
        self.pages["someaccount/"] = profile(*(node(f"Code0000{number}") for number in range(1, 5)))
        self.errors = {f"Code0000{number}": self.library.BadResponseException("no") for number in range(1, 4)}
        code, out = self.run_save("latest", "--account", "someaccount")
        self.assertEqual(code, 2, out)
        self.assertIn("3 failures in a row", self.stored())
        self.assertNotIn("Code00004", [what for what, _ in self.requests])

    def test_a_reel_between_failures_neither_counts_nor_clears_them(self):
        self.pages["someaccount/"] = profile(node("Code00001"), node("Code00002"), node("Reel00001"), node("Code00003"),
                                            node("Code00004"))
        self.errors = {code: self.library.BadResponseException("no") for code in ("Code00001", "Code00002", "Code00003")}
        self.posts["Reel00001"] = types.SimpleNamespace(typename="GraphVideo")
        code, out = self.run_save("latest", "--account", "someaccount")
        self.assertEqual(code, 2, out)
        self.assertIn("Reel00001: skipped", out)
        self.assertIn("3 failures in a row", self.stored())
        self.assertNotIn("Code00004", [what for what, _ in self.requests])

    def test_a_run_whose_caps_are_used_up_on_the_profile_page_lists_nothing(self):
        self.errors = {"profile:someaccount/": save.Full()}
        code, out = self.run_save("latest", "--account", "someaccount")
        self.assertEqual(code, 0, out)
        self.assertIn("used up: run it again", out)
        self.assertNotIn("not listed", out)
        self.assertFalse((self.base / "stopped.txt").exists())
        self.assertTrue(self.closed)

    def test_an_account_that_cant_be_listed_saves_nothing_and_doesnt_stop_the_run(self):
        lib = self.library
        odd = "checkpoint.challenge_login"  # a name made of stop words: its address alone mustn't stop the run
        cases = (
            ("someaccount", profile(private=True), None, "a private account"),
            ("someaccount", [{"xig_user_by_username": {"pk": "1"}}], None, "its page lists no posts"),
            ("someaccount", None, lib.QueryReturnedNotFoundException(
                "404 Not Found when accessing https://www.instagram.com/someaccount/"), "no account by that name (404)"),
            (odd, None, lib.ConnectionException(
                f"Page request to https://www.instagram.com/{odd}/: HTTPSConnectionPool(host='www.instagram.com', "
                f"port=443): Max retries exceeded with url: /{odd}/"), "ConnectionException"),
            (odd, None, lib.ConnectionException(f"500 Internal Server Error when accessing https://www.instagram.com/{odd}/"),
             "ConnectionException"),
        )
        for account, page, error, why in cases:
            with self.subTest(why):
                self.requests.clear()
                self.pages = {f"{account}/": page}
                self.errors = {f"profile:{account}/": error} if error else {}
                code, out = self.run_save("latest", "--account", account)
                self.assertEqual(code, 1, out)
                self.assertIn(f"{account}: not listed: {why}", out)
                self.assertNotIn("http", out)
                self.assertFalse((self.base / "stopped.txt").exists())
                self.assertEqual([what for what, _ in self.requests], [f"profile:{account}/"])
                self.assertTrue(self.closed)

    def test_a_refusal_on_the_profile_page_stops_the_run(self):
        lib = self.library
        url = "https://www.instagram.com/someaccount/"
        cases = {
            "401": lib.ConnectionException(f"401 Unauthorized when accessing {url}"),
            "403": lib.ConnectionException(f"403 Forbidden when accessing {url}"),
            "429": lib.ConnectionException(f"429 Too Many Requests when accessing {url}"),
            "400 feedback_required": lib.ConnectionException(
                f'400 Bad Request - "fail" status, message "feedback_required" when accessing {url}'),
            "LoginRequiredException": lib.LoginRequiredException("Redirected to login page. Use --login or --load-cookies."),
            "redirected the profile page (302)": lib.ConnectionException(f"302 Found when accessing {url}"),  # 4.16's text
            "redirected the profile page (301)": lib.ConnectionException(f"301 Moved Permanently when accessing {url}"),
        }
        for signal, error in cases.items():
            with self.subTest(signal):
                (self.base / "stopped.txt").unlink(missing_ok=True)
                self.requests.clear()
                self.errors = {"profile:someaccount/": error}
                code, out = self.run_save("latest", "--account", "someaccount")
                self.assertEqual(code, 2, out)
                self.assertIn(signal, self.stored())
                self.assertNotIn("http", self.stored())
                self.assertEqual([what for what, _ in self.requests], ["profile:someaccount/"])
        code, out = self.run_save("latest", "--account", "someaccount")
        self.assertEqual(code, 2)
        self.assertIn("Only --retry-failed", out)
        self.assertEqual([what for what, _ in self.requests], ["profile:someaccount/"])  # the stored stop fetched nothing

    def test_only_a_username_and_a_count_from_1_to_12_are_taken(self):
        for account in ("https://instagram.com/x", "instagram.com/x", "@x", "a/b", "x" * 31, ".x", "x.", "a..b", "",
                        "../etc", "x?y", "x y", "x\n"):
            with self.subTest(account), self.assertRaises(SystemExit) as caught:
                self.run_save("latest", "--account", account)
            self.assertIn("--account", str(caught.exception))
        for count in ("0", "13"):
            with self.subTest(count), self.assertRaises(SystemExit) as caught:
                self.run_save("latest", "--account", "someaccount", "--count", count)
            self.assertIn("--count", str(caught.exception))
        for account in ("explore", "Reels", "p", "accounts"):  # Instagram's own pages: a login redirect, a false stop
            with self.subTest(account), self.assertRaises(SystemExit) as caught:
                self.run_save("latest", "--account", account)
            self.assertIn("Instagram's own pages", str(caught.exception))
        self.assertEqual(self.requests, [])
        self.pages["a.b_c9/"] = profile()
        code, out = self.run_save("latest", "--account", "a.b_c9", "--count", "12")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing to save.", out)
        self.assertEqual([what for what, _ in self.requests], ["profile:a.b_c9/"])


class RefusedTest(SaveTest):
    def test_a_linked_posts_folder_is_refused(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        os.symlink(elsewhere, self.base)
        with self.assertRaises(SystemExit) as caught:
            self.run_save("post", "--code", "Code00001")
        self.assertIn("is a link", str(caught.exception))
        self.assertEqual(self.requests, [])

    def test_a_linked_folder_above_posts_or_reels_is_refused(self):
        marketing = self.root / "workspaces/marketing"
        elsewhere = self.root / "elsewhere"
        os.rename(marketing, elsewhere)
        os.symlink(elsewhere, marketing)
        self.posts["Code00001"] = image()
        for argv in (["post", "--code", "Code00001"], ["covers", "--week", WEEK]):
            with self.subTest(argv), self.assertRaises(SystemExit) as caught:
                self.run_save(*argv)
            self.assertIn("workspaces/marketing is a link", str(caught.exception))
        os.unlink(marketing)
        os.rename(elsewhere, marketing)
        cloud = self.root / "cloud"
        cloud.mkdir()
        (marketing / "intelligence/reels").symlink_to(cloud, target_is_directory=True)
        with self.assertRaises(SystemExit) as caught:
            self.run_save("covers", "--week", WEEK)
        self.assertIn("reels is a link", str(caught.exception))
        self.assertEqual(self.requests, [])
        self.assertEqual(list(cloud.iterdir()), [])

    def test_a_second_run_is_refused_while_one_holds_the_lock(self):
        self.base.mkdir()
        held = os.open(self.base / ".lock", os.O_WRONLY | os.O_CREAT)
        self.addCleanup(os.close, held)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.posts["Code00001"] = image()
        with self.assertRaises(SystemExit) as caught:
            self.run_save("post", "--code", "Code00001")
        self.assertIn("another save.py run", str(caught.exception))
        self.assertEqual(self.requests, [])
        fcntl.flock(held, fcntl.LOCK_UN)
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 0, out)

    def test_a_killed_runs_temporary_folders_are_removed(self):
        stale = self.base / ".tmp-Code00001-abc"
        stale.mkdir(parents=True)
        (stale / "1.jpg").write_bytes(JPEG)
        (self.base / "Code00001").mkdir()
        (self.base / "Code00001" / "MANIFEST.json").write_text("{}\n", encoding="utf-8")
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 0, out)
        self.assertIn("saved already", out)
        self.assertFalse(stale.exists())

    def test_a_failure_record_that_cant_be_written_stops_the_run(self):
        self.base.mkdir()
        (self.base / "Code00001").write_text("a file, not a folder\n", encoding="utf-8")
        self.errors = {"Code00001": self.library.BadResponseException("no")}
        self.posts["Code00002"] = image()
        code, out = self.run_save("post", "--code", "Code00001", "Code00002")
        self.assertEqual(code, 2, out)
        self.assertIn("couldn't be written (FileExistsError)", self.stored())
        self.assertNotIn("Code00002", [what for what, _ in self.requests])

    def test_a_stop_that_cant_be_stored_is_still_printed(self):
        self.base.mkdir()
        (self.base / "stopped.txt.tmp").mkdir()  # where watch.py writes it first
        self.errors = {"page": self.library.ConnectionException("429 Too Many Requests when accessing x")}
        self.posts["Code00001"] = image()
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 2)
        self.assertIn("stopped: Instagram refused us (429", out)
        self.assertIn("couldn't be stored in stopped.txt", out)
        self.assertFalse((self.base / "stopped.txt").exists())

    def test_a_linked_or_odd_stop_file_is_never_followed_and_holds_the_run(self):
        self.base.mkdir()
        target = self.root / "elsewhere.txt"
        target.write_text("words of another file\n", encoding="utf-8")
        os.symlink(target, self.base / "stopped.txt")
        self.posts["Code00001"] = image()
        self.files[CDN + "a.jpg"] = JPEG
        code, out = self.run_save("post", "--code", "Code00001")
        self.assertEqual(code, 2)
        self.assertIn("can't be read", out)
        self.assertNotIn("another file", out)
        self.assertEqual(self.requests, [])
        code, out = self.run_save("post", "--code", "Code00001", "--retry-failed")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.lexists(self.base / "stopped.txt"))
        self.assertEqual(target.read_text(encoding="utf-8"), "words of another file\n")
        os.mkfifo(self.base / "stopped.txt")  # opened without blocking, and not read
        self.requests.clear()
        code, out = self.run_save("post", "--code", "Code00002")
        self.assertEqual(code, 2)
        self.assertIn("isn't a plain file", out)
        self.assertEqual(self.requests, [])

    def test_the_csrf_wrapper_refuses_an_instaloader_it_wasnt_checked_against(self):
        self.posts["Code00001"] = image()
        self.library.__version__ = "4.17"
        with self.assertRaises(SystemExit) as caught:
            self.run_save("post", "--code", "Code00001")
        self.assertIn("csrf", str(caught.exception))
        self.assertTrue(self.closed)
        self.library.__version__, self.closed = "4.16", False
        with mock.patch.object(self.library.InstaloaderContext, "_csrf_token", None):
            with self.assertRaises(SystemExit) as caught:
                self.run_save("post", "--code", "Code00001")
        self.assertIn("csrf", str(caught.exception))
        self.assertTrue(self.closed)
        self.assertEqual(self.requests, [])

    def test_bad_arguments_are_refused(self):
        for argv, text in ((["post", "--code", "../etc"], "--code"), (["covers", "--week", "2026-05"], "--week"),
                           (["covers", "--week", WEEK, "--count", "0"], "--count")):
            with self.subTest(argv), self.assertRaises(SystemExit) as caught:
                self.run_save(*argv)
            self.assertIn(text, str(caught.exception))
        self.assertEqual(self.requests, [])

    def test_only_the_pinned_version_runs(self):
        with mock.patch.dict(sys.modules, {"instaloader": types.SimpleNamespace(__version__="4.15")}):
            with self.assertRaises(SystemExit) as caught:
                save.load_instaloader()
        self.assertIn("4.15", str(caught.exception))
        with mock.patch.dict(sys.modules, {"instaloader": self.library}):
            self.assertIs(save.load_instaloader(), self.library)


class PinnedTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.venv = Path(temp.name) / "venv"
        (self.venv / "bin").mkdir(parents=True)
        self.python = self.venv / "bin/python"
        self.python.write_text("", encoding="utf-8")
        for name, value in (("VENV", self.venv), ("PINNED", self.python)):
            patcher = mock.patch.object(save, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.calls = []

    def pinned(self, isolated, prefix, executable="/usr/bin/python3"):
        save.pinned(["covers", "--week", WEEK], isolated, str(prefix), executable,
                    execv=lambda path, args: self.calls.append((path, args)))

    def test_it_goes_on_only_isolated_in_the_pinned_environment(self):
        self.pinned(True, self.venv)
        self.assertEqual(self.calls, [])

    def test_from_anywhere_else_it_reruns_with_the_pinned_interpreter_isolated(self):
        for isolated, prefix in ((False, self.venv), (False, "/usr"), (True, "/usr")):
            with self.subTest((isolated, prefix)):
                self.calls.clear()
                self.pinned(isolated, prefix)
                self.assertEqual(self.calls, [(self.python, [str(self.python), "-I", str(Path(save.__file__).resolve()),
                                                             "covers", "--week", WEEK])])

    def test_a_rerun_that_still_isnt_the_environment_is_refused_not_looped(self):
        with self.assertRaises(SystemExit) as caught:
            self.pinned(True, "/usr", executable=str(self.python))
        self.assertIn("doesn't run in", str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_no_pinned_environment_is_refused(self):
        self.python.unlink()
        with self.assertRaises(SystemExit) as caught:
            self.pinned(False, "/usr")
        self.assertIn("no pinned environment", str(caught.exception))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
