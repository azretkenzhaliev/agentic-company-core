"""Tests for tools/marketing/publish/: post.py (the builder and the hook's check), post_hashes.py and stage_item.py.
No network: B2 is a fake. Each test builds a small repo in a temp folder: a piece page, its media,
the Board's approvals row (as the sync hook writes it) and company.json."""

import base64
import dataclasses
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

PUBLISH = Path(__file__).resolve().parents[1] / "publish"
sys.path.insert(0, str(PUBLISH))

import post  # noqa: E402
import post_hashes  # noqa: E402
import stage_item  # noqa: E402
from notion_approvals_sync import render  # noqa: E402  (post.py put scripts/ on the path)
from test_strip_ai import C2PA, XMP, mp4, png  # noqa: E402

NOW = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)
KEY = "keyid123:secret-application-key"
CAPTION = "Release 4: was ist neu?\n\n—\n\nRelease 4: what is new?\n\n#AI #Release4"
TOKEN = "3_20260203_abc_dnld"
HOST = "https://f005.backblazeb2.com"
TITLE = "Release 4: was ist neu?"
# Real PNGs: with the label off, stage_item.py refuses a file strip_ai.py can't parse.
SLIDE_ONE, SLIDE_TWO = png((b"pHYs", b"slide one")), png((b"pHYs", b"slide two"))


def page_text(account="demo", slug="thu-carousel-x", post_type="carousel", rows=None, ai="false",
              publish_at="2026-02-05T14:00+01:00", caption=CAPTION, title=None, fmt=None):
    rows = rows or [("1", "01.png"), ("2", "02.png")]
    table = "\n".join(f"| {label} | {name} | – |" for label, name in rows)
    title_line = f"- Title: {title}\n" if title else ""
    return (f"---\ntitle: \"x\"\nowner: content-producer\nstatus: draft\nupdated: 2026-02-01\nrelated: []\n"
            f"brand: founder/{account}\nweek: 2026-W06\nformat: {fmt or post_type}\nai_generated: {ai}\n---\n\n# x\n\n"
            f"## Caption\n\n```text\n{caption}\n```\n\n## Post\n\n- Type: {post_type}\n{title_line}- Publish at: {publish_at}\n\n"
            f"| # | File | SHA-256 |\n|---|---|---|\n{table}\n\n## Sources\n\nnone\n")


class FakeB2:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if url.endswith("b2_authorize_account"):
            return {"authorizationToken": "acct-token", "apiInfo": {"storageApi": {
                "apiUrl": "https://api005.backblazeb2.com", "downloadUrl": HOST,
                "allowed": {"buckets": [{"id": "bucket-id", "name": "media-bucket"}]}}}}
        if url.endswith("b2_get_upload_url"):
            return {"uploadUrl": "https://pod-000.backblaze.com/upload", "authorizationToken": "upload-token"}
        if url.endswith("b2_get_download_authorization"):
            return {"authorizationToken": TOKEN}
        return {"fileId": "f"}

    def uploads(self):
        return [(h["X-Bz-File-Name"], h["X-Bz-Content-Sha1"], body) for _, u, h, body in self.calls if u.endswith("/upload")]


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / post.CONFIG).write_text(json.dumps({"integrations": {"marketing": {
            "b2": {"bucket": "media-bucket", "download_host": HOST}, "brands": {
                "founder/demo": {"metricool_blog_id": "1000001", "timezone": "Europe/Berlin", "shorts": True},
                "founder/acme": {"metricool_blog_id": "1000002", "timezone": "Europe/Berlin"}}}}}))

    def tearDown(self):
        self.tmp.cleanup()

    def piece(self, account="demo", slug="thu-carousel-x", files=None, approval="Approved", note="", ai_label="off",
              **page):
        """Write the page and media, fill the hashes, and record the Board's decision on the page as it is."""
        files = files or {"01.png": SLIDE_ONE, "02.png": SLIDE_TWO}
        rel = f"knowledge/marketing/founder/{account}/content/2026-W06/{slug}.md"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page_text(account, slug, **page), encoding="utf-8")
        folder = self.root / "workspaces/marketing/media/founder" / account / "2026-W06" / slug
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (folder / name).write_bytes(data)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(post_hashes.main([str(path)], self.root), 0)
        self.decide(rel, approval, note, ai_label)
        return rel

    def short(self, slug="fri-short-x", **page):
        fields = {"post_type": "short", "title": TITLE, "ai": "true", "rows": [("1", "short.mp4")],
                  "files": {"short.mp4": b"video"}}
        return self.piece(slug=slug, **{**fields, **page})

    def decide(self, rel, approval="Approved", note="", ai_label="off"):
        account = rel.split("/")[3]
        row = {"item": "x", "kb_page": rel, "kb_sha256": hashlib.sha256((self.root / rel).read_bytes()).hexdigest(),
               "approval": approval, "ai_label": ai_label, "board_comment": "",
               "notion": f"https://app.notion.com/p/{account}x", "note": note}
        approvals = self.root / f"knowledge/marketing/founder/{account}/approvals/2026-W06.md"
        approvals.parent.mkdir(parents=True, exist_ok=True)
        approvals.write_text(render(f"founder/{account}", "2026-W06", [row], "2026-02-02T10:00:00Z"), encoding="utf-8")

    def stage(self, rel, now=NOW):
        fake, out, err = FakeB2(), io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = stage_item.main([str(self.root / rel)], send=fake, key=KEY, root=self.root, now=now)
        return code, out.getvalue(), err.getvalue(), fake

    def staged_args(self, rel):
        code, out, err, _ = self.stage(rel)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def check(self, args, now=NOW):
        return post.schedule_reason(args, self.root, now)

    def with_info(self, args, **changes):
        info = json.loads(args["info"])
        info.update(changes)
        return dict(args, info=json.dumps(info, ensure_ascii=False))


class Staging(Repo):
    def test_a_carousel_builds_the_exact_arguments(self):
        args = self.staged_args(self.piece())
        self.assertEqual((args["blogId"], args["date"]), ("1000001", "2026-02-05T14:00:00+01:00"))
        info = json.loads(args["info"])
        self.assertIs(info["autoPublish"], False)
        self.assertEqual(info["text"], CAPTION)
        self.assertEqual(info["providers"], [{"network": "instagram"}])
        self.assertEqual(info["publicationDate"], {"dateTime": "2026-02-05T14:00:00", "timezone": "Europe/Berlin"})
        self.assertEqual(info["instagramData"], {"type": "POST", "isAiGenerated": False})
        sha = hashlib.sha256(SLIDE_ONE).hexdigest()
        self.assertEqual(info["media"][0],
                         f"{HOST}/file/media-bucket/posts/2026-w06-demo-thu-carousel-x/{sha}-01.png?Authorization={TOKEN}")
        self.assertEqual(len(info["media"]), 2)

    def test_uploads_each_file_under_its_hash_with_the_sha1(self):
        _, _, _, fake = self.stage(self.piece())
        names = [(n, s, b) for n, s, b in fake.uploads()]
        self.assertEqual([n.rsplit("-", 1)[1] for n, _, _ in names], ["01.png", "02.png"])
        self.assertEqual(names[0][1], hashlib.sha1(SLIDE_ONE).hexdigest())
        prefix = [json.loads(b) for _, u, _, b in fake.calls if u.endswith("b2_get_download_authorization")][0]
        self.assertEqual(prefix["fileNamePrefix"], "posts/2026-w06-demo-thu-carousel-x/")
        self.assertEqual(prefix["validDurationInSeconds"], int((datetime(2026, 2, 6, 13, tzinfo=timezone.utc) - NOW).total_seconds()))

    def test_a_reel_with_a_cover_and_the_boards_ai_label(self):
        rel = self.piece(slug="sat-reel-x", post_type="reel", ai="true", rows=[("1", "reel.mp4"), ("cover", "cover.png")],
                         files={"reel.mp4": b"video", "cover.png": b"cover"}, ai_label="on")
        info = json.loads(self.staged_args(rel)["info"])
        self.assertEqual(info["instagramData"], {"type": "REEL", "isAiGenerated": True})
        self.assertIn("-cover.png?Authorization=", info["videoThumbnailUrl"])
        self.assertEqual(len(info["media"]), 1)

    def test_instagrams_ai_flag_is_the_boards_label_not_the_pages_record(self):
        for ai, label, flag in (("true", "off", False), ("false", "on", True), ("true", "on", True), ("false", "off", False)):
            with self.subTest(ai_generated=ai, ai_label=label):
                rel = self.piece(slug=f"thu-carousel-{ai}-{label}", ai=ai, ai_label=label)
                self.assertIs(json.loads(self.staged_args(rel)["info"])["instagramData"]["isAiGenerated"], flag)
                self.assertIs(post.read_piece(rel, self.root).ai_generated, ai == "true")

    def test_no_approvals_row_or_two_rows_mean_no_label(self):
        rel = self.piece(ai_label="on")
        self.assertTrue(post.read_piece(rel, self.root).ai_label)
        approvals = self.root / "knowledge/marketing/founder/demo/approvals/2026-W06.md"
        lines = approvals.read_text().split("\n")
        row = next(line for line in lines if rel in line)
        approvals.write_text("\n".join(lines).replace(row, row + "\n" + row))
        self.assertFalse(post.read_piece(rel, self.root).ai_label)
        approvals.unlink()
        self.assertFalse(post.read_piece(rel, self.root).ai_label)

    def test_another_account_stages_on_the_boards_approved_alone(self):
        rel = self.piece(account="acme", slug="fri-image-x", post_type="image", rows=[("1", "01.png")],
                         files={"01.png": png()})
        self.assertEqual(self.stage(rel)[0], 0)

    def test_no_key_or_token_in_the_log_and_no_key_anywhere(self):
        code, out, err, fake = self.stage(self.piece())
        log = (self.root / "workspaces/marketing/staged/2026-w06-demo-thu-carousel-x.json").read_text()
        secret = base64.b64encode(KEY.encode()).decode()
        for text in (out, err, log):
            self.assertNotIn("secret-application-key", text)
            self.assertNotIn(secret, text)
        self.assertNotIn(TOKEN, log)

    def test_refusals(self):
        cases = {
            "not Approved": dict(approval="Changes"),
            "has a note": dict(note="the page changed after the decision"),
            "too soon": dict(publish_at="2026-02-03T12:30+01:00"),
            "too far": dict(publish_at="2026-02-10T14:00+01:00"),
            "one-file carousel": dict(rows=[("1", "01.png")], files={"01.png": b"a"}),
            "a cover on a carousel": dict(rows=[("1", "01.png"), ("2", "02.png"), ("cover", "c.png")],
                                          files={"01.png": b"a", "02.png": b"b", "c.png": b"c"}),
            "caption too long": dict(caption="ü" * 2201),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                code, out, err, fake = self.stage(self.piece(**kwargs))
                self.assertEqual((code, out, fake.calls), (1, "", []), err)
                self.assertIn("refused", err)

    def test_an_edit_after_the_decision_or_a_changed_file_refuses(self):
        rel = self.piece()
        with (self.root / rel).open("a") as page:
            page.write("\nedited\n")
        self.assertIn("changed after the Board's decision", self.stage(rel)[2])
        rel = self.piece(slug="thu-carousel-y")
        (self.root / "workspaces/marketing/media/founder/demo/2026-W06/thu-carousel-y/02.png").write_bytes(b"swapped")
        self.assertIn("02.png changed", self.stage(rel)[2])

    def test_no_bucket_configured_is_the_boards_todo(self):
        config = self.root / post.CONFIG
        config.write_text(config.read_text().replace('"media-bucket"', "null"))
        self.assertIn("TODO(board)", self.stage(self.piece())[2])

    def test_a_key_for_another_bucket_refuses(self):
        config = self.root / post.CONFIG
        config.write_text(config.read_text().replace('"media-bucket"', '"other"'))
        code, _, err, _ = self.stage(self.piece())
        self.assertEqual(code, 1)
        self.assertIn("isn't for the bucket", err)


class AiMetadata(Repo):
    """With the Board's AI label off, Instagram gets the files without C2PA, XMP and IPTC (SA-005)."""

    def setUp(self):
        super().setUp()
        self.marked = png((b"caBX", C2PA), (b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + XMP))

    def test_label_off_uploads_the_stripped_copy_under_the_approved_hash(self):
        rel = self.piece(files={"01.png": self.marked, "02.png": png()})
        code, out, err, fake = self.stage(rel)
        self.assertEqual(code, 0, err)
        (name, sha1, body), _ = fake.uploads()
        self.assertEqual(body, png())
        self.assertEqual(sha1, hashlib.sha1(png()).hexdigest())
        self.assertIn(hashlib.sha256(self.marked).hexdigest() + "-01.png", name)
        folder = self.root / "workspaces/marketing/media/founder/demo/2026-W06/thu-carousel-x"
        self.assertEqual((folder / "01.png").read_bytes(), self.marked)
        self.assertIsNone(self.check(json.loads(out)))

    def test_label_on_uploads_the_file_as_it_is(self):
        rel = self.piece(files={"01.png": self.marked, "02.png": png()}, ai_label="on")
        code, out, err, fake = self.stage(rel)
        self.assertEqual(code, 0, err)
        self.assertEqual(fake.uploads()[0][2], self.marked)
        self.assertIs(json.loads(json.loads(out)["info"])["instagramData"]["isAiGenerated"], True)

    def test_label_off_refuses_a_file_whose_metadata_wont_come_off(self):
        kept = png((b"pHYs", b"c2pa.actions"))  # a chunk strip_ai keeps
        rel = self.piece(files={"01.png": kept, "02.png": png()})
        code, out, err, _ = self.stage(rel)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("couldn't remove the AI metadata from 01.png (c2pa.)", err)
        self.assertEqual(self.stage(self.piece(slug="thu-carousel-y", ai_label="on",
                                               files={"01.png": kept, "02.png": png()}))[0], 0)

    def test_label_off_refuses_a_file_strip_ai_cant_parse_by_name(self):
        """post.py's name check refuses .webp first; stage() refuses it too, and a .png, .jpg or .mp4 that doesn't
        parse (an empty one too), even with no marker in it, before anything is uploaded."""
        piece = post.read_piece(self.piece(), self.root)
        folder = self.root / piece.folder
        for name, data in (("01.webp", b"RIFF....WEBPVP8 no markers here"), ("01.heic", b"....ftypheic no markers"),
                           ("01.gif", b"GIF89a no markers here"), ("01.png", b"not a png, no markers"),
                           ("01.jpg", b"not a jpeg, no markers"), ("01.mp4", b"not boxes, no markers"),
                           ("02.png", b""), ("02.jpg", b""), ("02.mp4", b"")):  # empty files
            with self.subTest(name):
                (folder / name).write_bytes(data)
                webp = dataclasses.replace(piece, files=[("1", name, hashlib.sha256(data).hexdigest())])
                fake = FakeB2()
                with self.assertRaises(post.Refused) as refused:
                    stage_item.stage(webp, post.load_config(self.root), KEY, fake, self.root, NOW)
                self.assertEqual(str(refused.exception),
                                 f"strip_ai.py can't parse {name}, and the Board's AI label is off")
                self.assertEqual(fake.uploads(), [])

    def test_a_short_goes_as_it_is(self):
        """A Short's YouTube flag is still the page's ai_generated, so its file isn't touched."""
        _, _, err, fake = self.stage(self.short(files={"short.mp4": b"video with c2pa.actions"}))
        self.assertEqual(fake.uploads()[0][2], b"video with c2pa.actions", err)


class Settings(Repo):
    def test_no_settings_or_a_broken_company_json_posts_nothing(self):
        rel = self.piece()
        args = self.staged_args(rel)
        for settings, reason in (("{}", "TODO(board)"), ('{"integrations": {}}', "TODO(board)"), ("{not json", "JSON")):
            with self.subTest(settings=settings):
                (self.root / post.CONFIG).write_text(settings)
                code, out, err, fake = self.stage(rel)
                self.assertEqual((code, out, fake.calls), (1, "", []), err)
                self.assertIn(reason, err)
                self.assertIn(reason, self.check(args))
        (self.root / post.CONFIG).unlink()
        self.assertIn("TODO(board)", self.check(args))


class Hook(Repo):
    def test_the_staged_call_passes_once(self):
        args = self.staged_args(self.piece())
        self.assertIsNone(self.check(args))
        self.assertIn("already scheduled", self.check(args))
        self.assertEqual(self.stage(self.piece())[0], 1)

    def test_any_change_to_the_call_is_refused(self):
        args = self.staged_args(self.piece())
        info = json.loads(args["info"])
        other_host = [u.replace(HOST, "https://f001.backblazeb2.com") for u in info["media"]]
        cases = {
            "autoPublish true": self.with_info(args, autoPublish=True),
            "autoPublish 0": self.with_info(args, autoPublish=0),
            "autoPublish missing": dict(args, info=json.dumps({k: v for k, v in info.items() if k != "autoPublish"})),
            "caption": self.with_info(args, text=CAPTION + " extra"),
            "reordered": self.with_info(args, media=info["media"][::-1]),
            "another host": self.with_info(args, media=other_host),
            "a first comment": self.with_info(args, firstCommentText="link in bio"),
            "facebook too": self.with_info(args, providers=[{"network": "instagram"}, {"network": "facebook"}]),
            "AI flag": self.with_info(args, instagramData={"type": "POST", "isAiGenerated": True}),
            "two tokens": self.with_info(args, media=[info["media"][0], info["media"][1].replace(TOKEN, "other_dnld")]),
            "info as an object": dict(args, info=info),
            "another time": dict(args, date="2026-02-05T15:00:00+01:00"),
            "another brand": dict(args, blogId="1000002"),
            "mediaFiles": dict(args, mediaFiles=[]),
        }
        for name, call in cases.items():
            with self.subTest(name):
                self.assertIsNotNone(self.check(call))
        self.assertIsNone(self.check(args))

    def test_a_key_twice_is_refused_even_when_the_last_value_matches(self):
        args = self.staged_args(self.piece())
        for prefix in ['{"autoPublish": true, ', '{"text": "UNAPPROVED", ', '{"providers": [{"network": "facebook"}], ']:
            with self.subTest(prefix=prefix):
                self.assertIn("no key twice", self.check(dict(args, info=prefix + args["info"][1:])))
        nested = args["info"].replace('"isAiGenerated": false', '"isAiGenerated": true, "isAiGenerated": false')
        self.assertIn("no key twice", self.check(dict(args, info=nested)))

    def test_the_same_json_written_differently_is_refused(self):
        args = self.staged_args(self.piece())
        info = json.loads(args["info"])
        for variant in (json.dumps(info), json.dumps(info, ensure_ascii=False, indent=1), " " + args["info"]):
            with self.subTest(variant=variant[:30]):
                self.assertIsNotNone(self.check(dict(args, info=variant)))
        self.assertIsNone(self.check(args))

    def test_changes_after_staging_are_refused(self):
        rel = self.piece()
        args = self.staged_args(rel)
        (self.root / "workspaces/marketing/media/founder/demo/2026-W06/thu-carousel-x/01.png").write_bytes(b"x")
        self.assertIn("01.png changed", self.check(args))
        rel = self.piece(slug="thu-carousel-y")
        args = self.staged_args(rel)
        self.decide(rel, approval="Rejected")
        self.assertIn("not Approved", self.check(args))
        self.assertIn("2 hours to 6 days", self.check(args, now=datetime(2026, 2, 5, 12, tzinfo=timezone.utc)))

    def test_an_ai_label_changed_after_staging_is_refused_until_restaged(self):
        """The files went up for the old label: stage_item.py uploads them again for the new one."""
        for before, after in (("off", "on"), ("on", "off")):
            with self.subTest(before=before, after=after):
                rel = self.piece(slug=f"thu-carousel-{before}", ai_label=before)
                args = self.staged_args(rel)
                self.decide(rel, ai_label=after)
                self.assertIn("differ", self.check(args))
                self.assertIsNone(self.check(self.staged_args(rel)))


class InstagramUnchanged(Repo):
    """The calls as post.py built them for Instagram, string for string."""

    def test_a_carousel(self):
        self.assertEqual(self.staged_args(self.piece()), {
            "blogId": "1000001",
            "date": "2026-02-05T14:00:00+01:00",
            "info": r'{"autoPublish": false, "draft": false, "text": "Release 4: was ist neu?\n\n—\n\nRelease 4: what is new?\n\n#AI #Release4", "media": ["https://f005.backblazeb2.com/file/media-bucket/posts/2026-w06-demo-thu-carousel-x/3da16af80065f4357add05048dc6c0fb75f7bc4729c7a8cb4778d06e4a123f02-01.png?Authorization=THE_TOKEN", "https://f005.backblazeb2.com/file/media-bucket/posts/2026-w06-demo-thu-carousel-x/dcbc61fcff8ddfcd70d02d8230d36d8d3f21cddb526b3c01804b6eed64d1b3b7-02.png?Authorization=THE_TOKEN"], "providers": [{"network": "instagram"}], "publicationDate": {"dateTime": "2026-02-05T14:00:00", "timezone": "Europe/Berlin"}, "instagramData": {"type": "POST", "isAiGenerated": false}}'.replace("THE_TOKEN", TOKEN),
        })

    def test_a_reel_with_a_cover(self):
        rel = self.piece(slug="sat-reel-x", post_type="reel", ai="true", rows=[("1", "reel.mp4"), ("cover", "cover.png")],
                         files={"reel.mp4": b"video", "cover.png": b"cover"}, ai_label="on")
        self.assertEqual(self.staged_args(rel), {
            "blogId": "1000001",
            "date": "2026-02-05T14:00:00+01:00",
            "info": r'{"autoPublish": false, "draft": false, "text": "Release 4: was ist neu?\n\n—\n\nRelease 4: what is new?\n\n#AI #Release4", "media": ["https://f005.backblazeb2.com/file/media-bucket/posts/2026-w06-demo-sat-reel-x/0cab1c9617404faf2b24e221e189ca5945813e14d3f766345b09ca13bbe28ffc-reel.mp4?Authorization=THE_TOKEN"], "providers": [{"network": "instagram"}], "publicationDate": {"dateTime": "2026-02-05T14:00:00", "timezone": "Europe/Berlin"}, "instagramData": {"type": "REEL", "isAiGenerated": true}, "videoThumbnailUrl": "https://f005.backblazeb2.com/file/media-bucket/posts/2026-w06-demo-sat-reel-x/3fa405a8301ace34d11cf44a816080b8f0e49a48fbd048b8aef1543a8c58bdb6-cover.png?Authorization=THE_TOKEN"}'.replace("THE_TOKEN", TOKEN),
        })


class Shorts(Repo):
    def test_the_exact_call(self):
        info = json.loads(self.staged_args(self.short())["info"])
        self.assertIs(info["autoPublish"], False)
        self.assertEqual(info["text"], CAPTION)
        self.assertEqual(info["providers"], [{"network": "youtube"}])
        self.assertEqual(info["youtubeData"], {"title": TITLE, "type": "short", "privacy": "private", "madeForKids": False,
                                               "isAiGeneratedContent": True})
        self.assertEqual(len(info["media"]), 1)
        for instagram_only in ("instagramData", "videoThumbnailUrl"):
            self.assertNotIn(instagram_only, info)

    def test_the_ai_declaration_is_the_pages(self):
        info = json.loads(self.staged_args(self.short(ai="false"))["info"])
        self.assertIs(info["youtubeData"]["isAiGeneratedContent"], False)

    def test_the_staged_call_passes_once(self):
        args = self.staged_args(self.short())
        self.assertIsNone(self.check(args))
        self.assertIn("already scheduled", self.check(args))

    def test_any_change_to_the_call_is_refused(self):
        args = self.staged_args(self.short())
        info = json.loads(args["info"])
        youtube = info["youtubeData"]
        without = lambda key: dict(args, info=json.dumps({k: v for k, v in info.items() if k != key}, ensure_ascii=False))
        cases = {
            "autoPublish true": self.with_info(args, autoPublish=True),
            "autoPublish 0": self.with_info(args, autoPublish=0),
            "autoPublish missing": without("autoPublish"),
            "to Instagram": self.with_info(args, providers=[{"network": "instagram"}]),
            "to both": self.with_info(args, providers=[{"network": "youtube"}, {"network": "instagram"}]),
            "instagramData too": self.with_info(args, instagramData={"type": "REEL", "isAiGenerated": True}),
            "a thumbnail": self.with_info(args, videoThumbnailUrl=info["media"][0]),
            "no youtubeData": without("youtubeData"),
            "another title": self.with_info(args, youtubeData={**youtube, "title": "other"}),
            "not a short": self.with_info(args, youtubeData={**youtube, "type": "video"}),
            "public": self.with_info(args, youtubeData={**youtube, "privacy": "public"}),
            "unlisted": self.with_info(args, youtubeData={**youtube, "privacy": "unlisted"}),
            "made for kids": self.with_info(args, youtubeData={**youtube, "madeForKids": True}),
            "AI flag": self.with_info(args, youtubeData={**youtube, "isAiGeneratedContent": False}),
            "an extra field": self.with_info(args, youtubeData={**youtube, "playlistId": "x"}),
        }
        for name, call in cases.items():
            with self.subTest(name):
                self.assertIsNotNone(self.check(call))
        self.assertIsNone(self.check(args))

    def test_a_reel_never_goes_to_youtube(self):
        args = self.staged_args(self.piece(slug="sat-reel-x", post_type="reel", rows=[("1", "reel.mp4")],
                                           files={"reel.mp4": mp4()}))
        info = json.loads(args["info"])
        del info["instagramData"]
        info.update(providers=[{"network": "youtube"}], youtubeData={"title": TITLE, "type": "short", "privacy": "private",
                                                                     "madeForKids": False, "isAiGeneratedContent": False})
        self.assertIn("differ", self.check(dict(args, info=json.dumps(info, ensure_ascii=False))))
        self.assertIsNone(self.check(args))

    def test_a_page_that_mixes_the_two_is_refused_before_the_board_sees_it(self):
        rows = [("1", "short.mp4")]
        cases = {
            "a short with no title": (dict(post_type="short", rows=rows), "Title"),
            "a reel with a title": (dict(post_type="reel", title=TITLE, rows=rows), "Title"),
            "format short, type reel": (dict(post_type="reel", fmt="short", rows=rows), "go together"),
            "format reel, type short": (dict(post_type="short", fmt="reel", title=TITLE, rows=rows), "go together"),
            "format short, type carousel": (dict(fmt="short"), "go together"),
            "a title over the limit": (dict(post_type="short", title="ü" * 101, rows=rows), "100 characters"),
            "a title with <": (dict(post_type="short", title="a < b", rows=rows), "no < or >"),
            "a title with >": (dict(post_type="short", title="a > b", rows=rows), "no < or >"),
            "a control character": (dict(post_type="short", title="a\x07b", rows=rows), "control characters"),
            "a line separator": (dict(post_type="short", title="a b", rows=rows), "control characters"),
            "two titles": (dict(post_type="short", title=f"{TITLE}\n- Title: another", rows=rows), "at most one"),
            "a description of 5001 bytes": (dict(post_type="short", title=TITLE, rows=rows, caption="ü" * 2500 + "a"), "5000 bytes"),
            "a description with <": (dict(post_type="short", title=TITLE, rows=rows, caption="a < b"), "no < or >"),
            "a description with >": (dict(post_type="short", title=TITLE, rows=rows, caption="a > b"), "no < or >"),
            "a short on a brand without them": (dict(account="acme", post_type="short", title=TITLE, rows=rows), "has no Shorts"),
        }
        for name, (page, reason) in cases.items():
            with self.subTest(name):
                rel = f"knowledge/marketing/founder/{page.get('account', 'demo')}/content/2026-W06/fri-short-x.md"
                (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
                (self.root / rel).write_text(page_text(slug="fri-short-x", **page), encoding="utf-8")
                self.decide(rel)
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    self.assertEqual(post_hashes.main([str(self.root / rel)], self.root), 1)
                self.assertIn(reason, err.getvalue())
                code, out, err, fake = self.stage(rel)
                self.assertEqual((code, out, fake.calls), (1, "", []), err)

    def test_a_title_of_100_characters_is_taken(self):
        title = "ü" * 100
        info = json.loads(self.staged_args(self.short(title=title))["info"])
        self.assertEqual(info["youtubeData"]["title"], title)

    def test_a_description_of_5000_bytes_is_taken(self):
        caption = "ü" * 2500
        self.assertEqual(json.loads(self.staged_args(self.short(caption=caption))["info"])["text"], caption)

    def test_youtube_s_caption_rules_stay_off_instagram(self):
        self.assertEqual(json.loads(self.staged_args(self.piece(caption="a < b"))["info"])["text"], "a < b")

    def test_shape_refusals(self):
        cases = {
            "a cover": dict(rows=[("1", "short.mp4"), ("cover", "c.png")], files={"short.mp4": b"v", "c.png": b"c"}),
            "two files": dict(rows=[("1", "a.mp4"), ("2", "b.mp4")], files={"a.mp4": b"a", "b.mp4": b"b"}),
            "an image": dict(rows=[("1", "short.png")], files={"short.png": b"p"}),
        }
        for name, page in cases.items():
            with self.subTest(name):
                code, out, err, fake = self.stage(self.short(**page))
                self.assertEqual((code, out, fake.calls), (1, "", []), err)
                self.assertIn("refused", err)

    def test_it_needs_the_same_approved_row_as_a_post(self):
        for name, page, reason in (("Changes", dict(approval="Changes"), "not Approved"),
                                   ("Rejected", dict(approval="Rejected"), "not Approved"),
                                   ("a note", dict(note="the page changed"), "has a note")):
            with self.subTest(name):
                code, _, err, fake = self.stage(self.short(**page))
                self.assertEqual((code, fake.calls), (1, []), err)
                self.assertIn(reason, err)
        rel = self.short()
        (self.root / "knowledge/marketing/founder/demo/approvals/2026-W06.md").unlink()
        self.assertIn("0 approvals rows", self.stage(rel)[2])
        rel = self.short()
        with (self.root / rel).open("a") as page:
            page.write("\nedited\n")
        self.assertIn("changed after the Board's decision", self.stage(rel)[2])
        rel = self.short()
        (self.root / "workspaces/marketing/media/founder/demo/2026-W06/fri-short-x/short.mp4").write_bytes(b"swapped")
        self.assertIn("short.mp4 changed", self.stage(rel)[2])

    def test_a_decision_taken_back_after_staging_refuses(self):
        rel = self.short()
        args = self.staged_args(rel)
        self.decide(rel, approval="Rejected")
        self.assertIn("not Approved", self.check(args))


class TheHookItself(Repo):
    """guard_marketing_tools.py as Claude Code runs it, on a copy of scripts/ and publish/ inside the temp repo, with
    a stub in Metricool's place: as in a session, the stub gets a call only if the hook exits 0."""

    def setUp(self):
        super().setUp()
        repo = PUBLISH.parents[2]
        shutil.copytree(repo / "scripts/hooks", self.root / "scripts/hooks", ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("company_config.py", "kb_lint.py", "kb_secrets.py", "notion_approvals_sync.py"):
            shutil.copy(repo / "scripts" / name, self.root / "scripts" / name)
        (self.root / "tools/marketing/publish").mkdir(parents=True)
        shutil.copy(PUBLISH / "post.py", self.root / "tools/marketing/publish/post.py")
        self.metricool = []

    def call(self, args):
        event = {"session_id": "test", "cwd": str(self.root), "hook_event_name": "PreToolUse", "agent_type": "cmo",
                 "tool_name": "mcp__claude_ai_Metricool_Social_Media_Management__createScheduledPost", "tool_input": args}
        hook = subprocess.run([sys.executable, str(self.root / "scripts/hooks/guard_marketing_tools.py")],
                              input=json.dumps(event), capture_output=True, text=True, timeout=30,
                              env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)})
        self.assertIn(hook.returncode, (0, 2), hook.stderr)
        if hook.returncode == 0:
            self.metricool.append(args)
        return hook.stderr

    def test_only_the_staged_short_reaches_metricool_and_only_once(self):
        now = datetime.now(timezone.utc)
        when = (now + timedelta(days=1)).isoformat(timespec="minutes")
        code, out, err, _ = self.stage(self.short(publish_at=when), now=now)
        self.assertEqual(code, 0, err)
        args = json.loads(out)
        self.assertIn("autoPublish must be false", self.call(self.with_info(args, autoPublish=True)))
        self.assertIn("differ", self.call(self.with_info(args, providers=[{"network": "instagram"}])))
        youtube = json.loads(args["info"])["youtubeData"]
        self.assertIn("differ", self.call(self.with_info(args, youtubeData={**youtube, "privacy": "public"})))
        self.assertEqual(self.metricool, [])
        self.assertEqual(self.call(args), "")
        self.assertIn("already scheduled", self.call(args))
        self.assertEqual(self.metricool, [args])
        sent = json.loads(self.metricool[0]["info"])
        self.assertIs(sent["autoPublish"], False)
        self.assertEqual(sent["providers"], [{"network": "youtube"}])
        self.assertEqual(sent["youtubeData"]["privacy"], "private")


class Parsing(Repo):
    def test_a_hidden_caption_or_a_second_heading_is_refused(self):
        rel = self.piece()
        text = (self.root / rel).read_text()
        hidden = text.replace("## Caption\n\n", "## Caption\n\n<!--\n```text\nHIDDEN\n```\n-->\n\n")
        twice = text + "\n## Caption\n\n```text\nother\n```\n"
        for name, variant in (("hidden", hidden), ("twice", twice)):
            with self.subTest(name):
                (self.root / rel).write_text(variant)
                with self.assertRaises(post.Refused):
                    post.read_piece(rel, self.root)


class Hashes(Repo):
    def test_fills_the_column_in_order(self):
        rel = self.piece()
        text = (self.root / rel).read_text()
        self.assertIn(f"| 1 | 01.png | {hashlib.sha256(SLIDE_ONE).hexdigest()} |", text)
        self.assertIn("## Sources", text)

    def test_refuses_a_path_or_a_missing_file(self):
        for rows, files in [([("1", "../01.png"), ("2", "02.png")], {"02.png": b"b"}),
                            ([("1", "01.png"), ("2", "03.png")], {"01.png": b"a"})]:
            with self.subTest(rows=rows):
                rel = "knowledge/marketing/founder/demo/content/2026-W06/thu-carousel-z.md"
                (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
                (self.root / rel).write_text(page_text(slug="thu-carousel-z", rows=rows))
                folder = self.root / "workspaces/marketing/media/founder/demo/2026-W06/thu-carousel-z"
                folder.mkdir(parents=True, exist_ok=True)
                for name, data in files.items():
                    (folder / name).write_bytes(data)
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    self.assertEqual(post_hashes.main([str(self.root / rel)], self.root), 1)


if __name__ == "__main__":
    unittest.main()
