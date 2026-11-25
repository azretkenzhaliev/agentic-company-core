"""Tests for tools/marketing/publish/strip_ai.py: the AI metadata comes off the copy, the image stays.
The files are built here, with the markers C2PA, XMP and IPTC carry."""

import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "publish"))

import strip_ai  # noqa: E402

XMP = (b'<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:Description xmlns:Iptc4xmpExt='
       b'"http://iptc.org/std/Iptc4xmpExt/2008-02-29/" Iptc4xmpExt:DigitalSourceType='
       b'"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"/></x:xmpmeta>')
C2PA = b"jumb....jumdc2pa....c2pa.actions.v2 digitalSourceType trainedAlgorithmicMedia c2pa.hash.data"


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(*extra) -> bytes:
    """A 1x1 grey PNG, with extra (type, data) chunks before its pixels."""
    return (strip_ai.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
            + b"".join(chunk(kind, data) for kind, data in extra) + chunk(b"IDAT", zlib.compress(b"\x00\x80"))
            + chunk(b"IEND", b""))


def segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def jpeg(*extra) -> bytes:
    """A JPEG's frame: SOI, JFIF, the extra (marker, payload) segments, DQT, then a scan and EOI."""
    return (b"\xff\xd8" + segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            + b"".join(segment(m, p) for m, p in extra) + segment(0xDB, b"\x00" + bytes(64))
            + segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\xff\x00\x56" + b"\xff\xd9")


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + kind + payload


def mp4(*top, udta=b"") -> bytes:
    """ftyp, moov (mvhd, a trak, udta) and mdat, with extra top-level boxes after moov."""
    moov = box(b"moov", box(b"mvhd", bytes(100)) + box(b"trak", box(b"tkhd", bytes(84))) + box(b"udta", udta))
    return box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41") + moov + b"".join(top) + box(b"mdat", b"frames" * 10)


def chunks(data: bytes) -> list:
    i, kinds = 8, []
    while i < len(data):
        length, kind = struct.unpack(">I4s", data[i:i + 8])
        kinds.append(kind)
        i += 12 + length
    return kinds


class Png(unittest.TestCase):
    def test_c2pa_xmp_and_text_go_and_the_image_stays(self):
        data = png((b"sRGB", b"\x00"), (b"caBX", C2PA), (b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + XMP),
                   (b"tEXt", b"Software\x00Gemini"), (b"zTXt", b"Raw profile type iptc\x00\x00" + zlib.compress(b"x")),
                   (b"eXIf", b"MM\x00*"), (b"tIME", bytes(7)), (b"prVt", b"unknown"))
        self.assertTrue(strip_ai.ai_marks(data))
        clean = strip_ai.strip(data, ".PNG")
        self.assertEqual(chunks(clean), [b"IHDR", b"sRGB", b"IDAT", b"IEND"])
        self.assertEqual(strip_ai.ai_marks(clean), [])
        self.assertEqual(clean, png((b"sRGB", b"\x00")))

    def test_a_clean_png_is_unchanged(self):
        self.assertEqual(strip_ai.strip(png(), ".png"), png())

    def test_whatever_follows_iend_goes(self):
        self.assertEqual(strip_ai.strip(png() + b"c2pa.trailer", ".png"), png())


class Jpeg(unittest.TestCase):
    def test_xmp_c2pa_iptc_and_comments_go_and_exif_icc_stay(self):
        exif, icc = b"Exif\x00\x00MM\x00*", b"ICC_PROFILE\x00\x01\x01profile"
        data = jpeg((0xE1, exif), (0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + XMP), (0xE2, icc),
                    (0xEB, b"JP\x00\x00" + C2PA), (0xED, b"Photoshop 3.0\x008BIM\x04\x04"), (0xFE, b"made with AI"),
                    (0xE2, b"MPF\x00\x00"), (0xEE, b"Adobe\x00d"))
        self.assertTrue(strip_ai.ai_marks(data))
        clean = strip_ai.strip(data, ".jpg")
        self.assertEqual(clean, jpeg((0xE1, exif), (0xE2, icc), (0xEE, b"Adobe\x00d")))
        self.assertEqual(strip_ai.ai_marks(clean), [])

    def test_a_clean_jpeg_is_unchanged(self):
        self.assertEqual(strip_ai.strip(jpeg(), ".jpeg"), jpeg())


class Mp4(unittest.TestCase):
    def test_uuid_and_xmp_boxes_become_free_boxes_of_the_same_size(self):
        c2pa = box(b"uuid", bytes.fromhex("d8fec3d61b0e483c92975828877ec481") + C2PA)
        xmp = box(b"uuid", bytes.fromhex("be7acfcb97a942e89c71999491e3afac") + XMP)
        data = mp4(c2pa, udta=box(b"XMP_", XMP) + xmp)
        self.assertTrue(strip_ai.ai_marks(data))
        clean = strip_ai.strip(data, ".mp4")
        self.assertEqual(len(clean), len(data))
        self.assertEqual(strip_ai.ai_marks(clean), [])
        self.assertEqual(clean.count(b"free"), 3)
        for kept in (box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41"), box(b"mvhd", bytes(100)),
                     box(b"trak", box(b"tkhd", bytes(84))), box(b"mdat", b"frames" * 10)):
            self.assertEqual(clean.find(kept), data.find(kept))

    def test_a_clean_mp4_is_unchanged(self):
        self.assertEqual(strip_ai.strip(mp4(), ".mp4"), mp4())

    def test_a_64_bit_box_size_parses(self):
        large = struct.pack(">I4sQ", 1, b"uuid", 16 + len(C2PA)) + C2PA
        clean = strip_ai.strip(mp4(large), ".mp4")
        self.assertEqual(strip_ai.ai_marks(clean), [])
        self.assertIn(struct.pack(">I4sQ", 1, b"free", 16 + len(C2PA)), clean)

    def test_xmp_inside_meta_goes_under_udta_and_at_the_top_level(self):
        hdlr = box(b"hdlr", bytes(8) + b"mdir" + bytes(13))
        iso_meta = box(b"meta", bytes(4) + hdlr + box(b"xml ", bytes(4) + XMP))  # a full box: version and flags
        quicktime_meta = box(b"meta", hdlr + box(b"uuid", bytes(16) + C2PA) + box(b"XMP_", XMP))
        keys_first = box(b"meta", box(b"keys", bytes(8)) + hdlr + box(b"XMP_", XMP))  # QuickTime: no hdlr first
        for name, data in (("ISO meta at the top level", mp4(iso_meta)),
                           ("QuickTime meta in udta", mp4(udta=quicktime_meta)),
                           ("ISO meta in udta", mp4(udta=iso_meta)),
                           ("QuickTime meta with keys first, and C2PA at the top", mp4(box(b"uuid", C2PA), keys_first))):
            with self.subTest(name):
                self.assertTrue(strip_ai.ai_marks(data))
                clean = strip_ai.strip(data, ".mp4")
                self.assertEqual(len(clean), len(data))
                self.assertEqual(strip_ai.ai_marks(clean), [])
                self.assertEqual(clean.find(hdlr), data.find(hdlr))

    def test_a_meta_that_doesnt_parse_raises(self):
        data = mp4(udta=box(b"meta", bytes(4) + b"\x00\x00\x10\x00xml " + XMP))  # the xml box runs past meta's end
        with self.assertRaises(strip_ai.Unparsed):
            strip_ai.strip(data, ".mp4")


class Unparsed(unittest.TestCase):
    def test_a_file_that_doesnt_parse_raises(self):
        """With or without a marker in it: what doesn't parse may keep metadata where nothing here looks."""
        cases = {
            "a PNG chunk cut short": (".png", strip_ai.PNG_SIGNATURE + b"\x00\x00\x10\x00IHDRc2pa.cut short"),
            "a PNG without IEND": (".png", png()[:-12]),
            "a PNG without its signature": (".png", b"no signature, no marker"),
            "a JPEG segment cut short": (".jpg", b"\xff\xd8\xff\xe1\x40\x00x:xmpmeta"),
            "a JPEG without a scan": (".jpeg", b"\xff\xd8" + segment(0xE0, b"JFIF\x00") + b"\x00"),
            "a JPEG without its signature": (".jpg", b"no signature, no marker"),
            "an MP4 box cut short": (".mp4", box(b"ftyp", b"isom") + b"\x00\x01\x00\x00uuidc2pa."),
            "an MP4 that isn't boxes": (".mp4", b"no boxes, no marker"),
        }
        for name, (suffix, data) in cases.items():
            with self.subTest(name), self.assertRaises(strip_ai.Unparsed):
                strip_ai.strip(data, suffix)

    def test_an_empty_file_raises(self):
        """Zero bytes are no file of any type, though zero MP4 boxes would parse."""
        for suffix in strip_ai.PARSED:
            with self.subTest(suffix), self.assertRaises(strip_ai.Unparsed):
                strip_ai.strip(b"", suffix)

    def test_a_suffix_without_a_parser_raises(self):
        """Even a file with no marker in it: nothing here knows where a format we don't parse keeps its metadata."""
        for suffix in (".webp", ".heic", ".gif", ".mov", ""):
            with self.subTest(suffix), self.assertRaises(strip_ai.Unparsed):
                strip_ai.strip(b"RIFF....WEBPVP8 no markers here", suffix)


if __name__ == "__main__":
    unittest.main()
