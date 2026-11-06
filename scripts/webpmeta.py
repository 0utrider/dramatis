"""Write EXIF and XMP into published files without re-encoding: .webp (EXIF+XMP chunks), .png (eXIf + iTXt XMP),
.gif (XMP application extension) and .webm (Matroska tags via ffmpeg stream copy; no EXIF/XMP in the container)."""
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
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


def write_meta(path, exif: bytes, xmp: bytes, entry: dict | None = None) -> bool:
    """Replace embedded metadata. Returns True if the file changed."""
    ext = Path(path).suffix.lower()
    if ext == ".png":
        return _write_png(path, exif, xmp)
    if ext == ".gif":
        return _write_gif(path, xmp)
    if ext == ".webm":
        return _write_webm(path, entry or {})
    return _write_webp(path, exif, xmp)


def _write_png(path, exif: bytes, xmp: bytes) -> bool:
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    if exif[:6] == b"Exif\x00\x00":
        exif = exif[6:]

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    out, pos = [data[:8]], 8
    while pos < len(data):
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + size]
        raw = data[pos:pos + 12 + size]
        pos += 12 + size
        if tag == b"eXIf" or (tag == b"iTXt" and body.startswith(b"XML:com.adobe.xmp\x00")):
            continue
        out.append(raw)
        if tag == b"IHDR":
            out.append(chunk(b"eXIf", exif))
            out.append(chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + xmp))
    new = b"".join(out)
    if new == data:
        return False
    open(path, "wb").write(new)
    return True


_GIF_XMP_TRAILER = b"\x01" + bytes(range(0xFF, 0, -1)) + b"\x00\x00"


def _write_gif(path, xmp: bytes) -> bool:
    data = open(path, "rb").read()
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError("not a GIF file")
    pos = 13
    if data[10] & 0x80:
        pos += 3 * (2 << (data[10] & 7))

    def skip_ext(p):  # p at 0x21; returns end of the extension block
        p += 2
        while data[p]:
            p += data[p] + 1
        return p + 1

    head, keep = data[:pos], []
    while data[pos] == 0x21 and data[pos + 1] != 0xF9:  # header extensions (NETSCAPE loop etc.), stop at first frame
        end = skip_ext(pos)
        if not data[pos:end].startswith(b"\x21\xff\x0bXMP DataXMP"):
            keep.append(data[pos:end])
        pos = end
    block = b"\x21\xff\x0bXMP DataXMP" + xmp + _GIF_XMP_TRAILER
    new = head + b"".join(keep) + block + data[pos:]
    if new == data:
        return False
    open(path, "wb").write(new)
    return True


def _write_webm(path, entry: dict) -> bool:
    """Matroska tags by stream copy. Idempotent: skipped when the tags already match."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not (ffmpeg and ffprobe):
        return False
    owner = entry.get("owner") or "0utrider"
    lic = entry.get("license") or "unspecified"
    year = str(entry.get("added") or "")[:4] or "2026"
    tags = {
        "title": f"{entry.get('subject')} {entry.get('type')}",
        "artist": owner,
        "copyright": f"Copyright {year} {owner}. License: {lic}.",
        "comment": f"Original: {REPO_URL} ({entry.get('path')})",
    }
    probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
                           capture_output=True, text=True).stdout
    import json
    have = {k.lower(): v for k, v in (json.loads(probe or "{}").get("format", {}).get("tags") or {}).items()}
    if all(have.get(k) == v for k, v in tags.items()):
        return False
    tmp = Path(path).with_suffix(".tmp.webm")
    cmd = [ffmpeg, "-v", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy", "-fflags", "+bitexact",
           "-map_metadata", "-1"]
    for k, v in tags.items():
        cmd += ["-metadata", f"{k}={v}"]
    subprocess.run(cmd + [str(tmp)], check=True)
    tmp.replace(path)
    return True


def _write_webp(path, exif: bytes, xmp: bytes) -> bool:
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
