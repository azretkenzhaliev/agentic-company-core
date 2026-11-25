"""Remove AI metadata (C2PA, XMP, IPTC) from the copy of a file that goes to Instagram.

SA-005: whether a post carries Instagram's AI label is the Board's choice for each post, set by the AI label
box in Notion. When it is off, stage_item.py uploads strip()'s copy and refuses a file in which ai_marks()
still finds something. The files in workspaces/marketing/media/ keep their metadata (gen/gemini.py writes
them as Gemini sent them), and the page's `ai_generated` stays our own record of what is AI-made. What a
platform's terms or your market's law ask about AI media is the Board's to weigh (docs/marketing.md).

- PNG: keeps the image chunks (KEEP_PNG) and drops the rest: caBX (C2PA), tEXt, zTXt and iTXt (XMP,
  IPTC), eXIf, tIME and any unknown chunk.
- JPEG: keeps APP0 (JFIF), APP1 Exif, APP2 ICC, APP14 Adobe and every non-APP segment; drops APP1 XMP,
  APP11 (C2PA), APP13 (IPTC), COM and the other APPn.
- MP4: overwrites `uuid` boxes (C2PA, XMP) at the top level and in moov, trak, udta and meta (ISO's,
  with version and flags before its hdlr, and QuickTime's, without), and `XMP_` and `xml ` boxes, with
  `free` boxes of the same size, so the chunk offsets stay valid.

A suffix with no parser here (.webp, .heic, .gif, ...), or a file whose signature or structure doesn't
parse (an empty one included), raises Unparsed, and stage_item.py refuses that file by name: nothing goes
out unchanged. A watermark in the pixels, such as SynthID, stays: nothing here removes it.
"""

import struct

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
KEEP_PNG = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT",
            b"bKGD", b"pHYs", b"cICP", b"mDCV", b"cLLI", b"acTL", b"fcTL", b"fdAT"}
KEEP_APP = {0xE0: b"JFIF", 0xE1: b"Exif\x00", 0xE2: b"ICC_PROFILE\x00", 0xEE: b"Adobe"}
PARSED = (".png", ".jpg", ".jpeg", ".mp4")
MP4_CONTAINERS = {b"moov", b"trak", b"udta", b"meta"}
MP4_DROP = {b"uuid", b"XMP_", b"xml "}
# What C2PA manifests, XMP packets and IPTC records contain; long enough not to turn up in compressed data.
MARKS = (b"c2pa.", b"x:xmpmeta", b"<?xpacket", b"http://ns.adobe.com/xap/1.0/", b"Iptc4xmp",
         b"DigitalSourceType", b"digitalsourcetype", b"AlgorithmicMedia", b"algorithmicMedia", b"Photoshop 3.0\x00")


class Unparsed(ValueError):
    """strip() has no parser for this suffix, or the file doesn't parse."""


def ai_marks(data: bytes) -> list:
    """The AI-metadata markers still in data."""
    return [mark.decode("latin-1").rstrip("\x00") for mark in MARKS if mark in data]


def _png(data: bytes) -> bytes:
    out, i = [PNG_SIGNATURE], len(PNG_SIGNATURE)
    while i + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[i:i + 8])
        end = i + 12 + length
        if end > len(data):
            break
        if kind in KEEP_PNG:
            out.append(data[i:end])
        if kind == b"IEND":
            return b"".join(out)
        i = end
    raise Unparsed("a PNG chunk runs past the end, or there is no IEND")


def _jpeg(data: bytes) -> bytes:
    out, i = [data[:2]], 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xDA:  # start of scan: the image data and what follows stay as they are
            out.append(data[i:])
            return b"".join(out)
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            out.append(data[i:i + 2])
            i += 2
            continue
        end = i + 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        if end > len(data):
            break
        payload = data[i + 4:end]
        app = 0xE0 <= marker <= 0xEF
        if marker != 0xFE and (not app or (marker in KEEP_APP and payload.startswith(KEEP_APP[marker]))):
            out.append(data[i:end])
        i = end
    raise Unparsed("a JPEG segment runs past the end, or there is no start of scan")


def _mp4(data: bytearray, start: int, stop: int) -> bool:
    """Blank the boxes in MP4_DROP between start and stop, in place; False if the boxes don't parse."""
    i = start
    while i + 8 <= stop:
        size, kind = struct.unpack(">I4s", data[i:i + 8])
        header = 8
        if size == 1:
            if i + 16 > stop:
                return False
            size, header = struct.unpack(">Q", data[i + 8:i + 16])[0], 16
        elif size == 0:
            size = stop - i
        if size < header or i + size > stop:
            return False
        if kind in MP4_DROP:
            data[i + 4:i + 8] = b"free"
            data[i + header:i + size] = bytes(size - header)
        elif kind in MP4_CONTAINERS:
            first = i + header
            if kind == b"meta" and data[first:first + 4] == bytes(4):
                first += 4  # ISO's meta is a full box (version 0, flags 0); QuickTime's starts with its first child's size
            if not _mp4(data, first, i + size):
                return False
        i += size
    return i == stop


def strip(data: bytes, suffix: str) -> bytes:
    """data without its C2PA, XMP and IPTC. Raises Unparsed for a suffix not in PARSED, or a file whose
    signature or structure doesn't parse."""
    suffix = suffix.lower()
    if suffix not in PARSED:
        raise Unparsed(f"strip_ai has no parser for {suffix or 'a name without a suffix'}")
    if suffix == ".png" and data.startswith(PNG_SIGNATURE):
        return _png(data)
    if suffix in (".jpg", ".jpeg") and data.startswith(b"\xff\xd8"):
        return _jpeg(data)
    if suffix == ".mp4" and data:  # zero boxes would parse: an empty file is no MP4
        copy = bytearray(data)
        if _mp4(copy, 0, len(copy)):
            return bytes(copy)
    raise Unparsed(f"this {suffix} file doesn't parse")
