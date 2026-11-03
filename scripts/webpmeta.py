"""Write EXIF and XMP chunks into a .webp without re-encoding the image data."""
import struct
from xml.sax.saxutils import escape

from PIL import Image

REPO_URL = "https://github.com/0utrider/dramatis"


def _chunks(data: bytes):
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a WebP file")
    pos = 12
    while pos + 8 <= len(data):
        tag, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        yield tag, data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + struct.pack("<I", len(body)) + body + (b"\0" if len(body) & 1 else b"")


def read_meta(path) -> dict:
    """Return {'EXIF': bytes|None, 'XMP ': bytes|None}."""
    out = {"EXIF": None, "XMP ": None}
    for tag, body in _chunks(open(path, "rb").read()):
        if tag in out:
            out[tag] = body
    return out


def write_meta(path, exif: bytes, xmp: bytes) -> bool:
    """Replace EXIF/XMP chunks. Returns True if the file changed."""
    data = open(path, "rb").read()
    chunks = [(t, b) for t, b in _chunks(data)]
    with Image.open(path) as im:
        w, h = im.size
    if chunks[0][0] == b"VP8X":
        flags = chunks[0][1][0]
        rest = [(t, b) for t, b in chunks[1:] if t not in (b"EXIF", b"XMP ")]
    else:  # simple lossy/lossless file: build the extended header
        flags, rest = 0, [(t, b) for t, b in chunks if t not in (b"EXIF", b"XMP ")]
    flags |= 0x08 | 0x04
    vp8x = bytes([flags, 0, 0, 0]) + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
    body = b"WEBP" + _chunk(b"VP8X", vp8x)
    body += b"".join(_chunk(t, b) for t, b in rest)
    body += _chunk(b"EXIF", exif) + _chunk(b"XMP ", xmp)
    new = b"RIFF" + struct.pack("<I", len(body)) + body
    if new == data:
        return False
    open(path, "wb").write(new)
    return True


def build(entry: dict) -> tuple:
    """Build (exif, xmp) bytes from a manifest entry. Deterministic, so re-stamping is a no-op."""
    owner = entry.get("owner") or "0utrider"
    lic = entry.get("license") or "unspecified"
    year = str(entry.get("added") or "")[:4] or "2026"
    rights = f"Copyright {year} {owner}. License: {lic}."
    path = entry["path"]
    title = f"{entry['subject']} {entry['type']}"
    if entry.get("name"):
        title += f" ({entry['name']}, {entry.get('campaign')})"
    exif = Image.Exif()
    exif[0x010E] = f"{entry['subject']} {entry['type']}. Original: {REPO_URL} ({path})"  # ImageDescription
    exif[0x013B] = owner                                                                 # Artist
    exif[0x8298] = rights                                                                # Copyright
    e = escape
    xmp = f'''<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/">
<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{e(title)}</rdf:li></rdf:Alt></dc:title>
<dc:creator><rdf:Seq><rdf:li>{e(owner)}</rdf:li></rdf:Seq></dc:creator>
<dc:rights><rdf:Alt><rdf:li xml:lang="x-default">{e(rights)}</rdf:li></rdf:Alt></dc:rights>
<dc:source>{REPO_URL}</dc:source>
<dc:identifier>{e(path)}</dc:identifier>
<xmpRights:Marked>True</xmpRights:Marked>
<xmpRights:Owner><rdf:Bag><rdf:li>{e(owner)}</rdf:li></rdf:Bag></xmpRights:Owner>
<xmpRights:UsageTerms><rdf:Alt><rdf:li xml:lang="x-default">{e(lic)}</rdf:li></rdf:Alt></xmpRights:UsageTerms>
<xmpRights:WebStatement>{REPO_URL}</xmpRights:WebStatement>
</rdf:Description></rdf:RDF></x:xmpmeta>
<?xpacket end="w"?>'''
    return exif.tobytes(), xmp.encode("utf-8")
