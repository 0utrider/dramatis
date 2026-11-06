#!/usr/bin/env python3
"""Validate character.yaml files, stamp metadata into each .webp (.webm is listed and checked but not stamped), against the published .webp files and rebuild manifest.json.

Run from anywhere. Exits non-zero if validation fails. Embeds EXIF/XMP (repo URL, owner, license) in every published .webp (idempotent). Fills in `dimensions` for every asset
(rewrites character.yaml only when a value changed) and writes /manifest.json.
Requires Pillow and PyYAML.
"""
import json
import sys
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import webpmeta  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://0utrider.github.io/dramatis"
FOLDER_CATEGORY = {"": "character", "companions": "companion", "summons": "summon", "fx": "fx"}
TYPES = {"keyart", "portrait", "token", "bust", "fx"}
ICON_FOLDER_CATEGORY = {"abilities": "ability", "spells": "spell", "equipment": "equipment"}
SYSTEMS = {"pf2e", "sf2e", "pf1e"}
SOURCES = {"commissioned", "self", "stock"}
CHARACTER_FIELDS = ("id", "name", "campaign", "system", "gm", "owner", "race", "class", "links", "summary")


NOSTAMP_EXT = {".webm", ".gif", ".png"}  # token companions (video, GIF for Discord, static PNG): listed, not stamped
VIDEO_EXT = ".webm"  # animated token companions: validated and listed, but not stamped (no EXIF/XMP in webm)


def is_working(path: Path) -> bool:
    return any(p.startswith("_") for p in path.relative_to(ROOT).parts)


def stamp(path: Path, entry: dict) -> None:
    exif, xmp = webpmeta.build(entry)
    webpmeta.write_meta(path, exif, xmp)


def check_icons(errors: list, manifest: list) -> None:
    """Shared icon library: icons/icons.yaml lists every webp under icons/<abilities|spells|equipment>/."""
    idir, ypath = ROOT / "icons", ROOT / "icons" / "icons.yaml"
    files = sorted(f for f in idir.rglob("*.webp") if not is_working(f)) if idir.is_dir() else []
    if not ypath.is_file():
        errors += [f"{f.relative_to(ROOT)}: no icons/icons.yaml" for f in files]
        return
    data = yaml.safe_load(ypath.read_text(encoding="utf-8")) or {}
    listed, changed = set(), False
    for a in data.get("assets") or []:
        f = a.get("file", "")
        if f in listed:
            errors.append(f"icons/{f}: listed more than once")
        listed.add(f)
        path = idir / f
        if not path.is_file():
            errors.append(f"icons/{f}: listed in assets but file is missing")
            continue
        folder = Path(f).parts[0]
        want = ICON_FOLDER_CATEGORY.get(folder)
        if want is None:
            errors.append(f"icons/{f}: unknown subfolder '{folder}'")
        elif a.get("category") != want:
            errors.append(f"icons/{f}: category '{a.get('category')}' must be '{want}' for this folder")
        if a.get("type") != "icon":
            errors.append(f"icons/{f}: type must be 'icon'")
        if not a.get("subject"):
            errors.append(f"icons/{f}: missing subject")
        if a.get("source") and a["source"] not in SOURCES:
            errors.append(f"icons/{f}: source must be one of {sorted(SOURCES)}")
        with Image.open(path) as im:
            dims = f"{im.width}x{im.height}"
        if a.get("dimensions") != dims:
            a["dimensions"] = dims
            changed = True
        entry = {"collection": "icons", **a, "path": f"icons/{f}", "url": f"{BASE_URL}/icons/{f}"}
        stamp(path, {**entry, "owner": data.get("owner")})
        manifest.append(entry)
    for f in files:
        rel = f.relative_to(idir).as_posix()
        if rel not in listed:
            errors.append(f"icons/{rel}: published file has no assets entry")
    if changed:
        ypath.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")


def main() -> int:
    errors, manifest = [], []
    yamls = sorted(p for p in ROOT.glob("*/*/character.yaml") if not is_working(p))
    char_dirs = {p.parent for p in yamls}

    # every published webp must live under a character folder (or the shared icons library)
    for f in sorted([*ROOT.rglob("*.webp"), *(f for e in NOSTAMP_EXT for f in ROOT.rglob("*" + e))]):
        if is_working(f) or ROOT / "icons" in f.parents:
            continue
        if not any(d in f.parents for d in char_dirs):
            errors.append(f"{f.relative_to(ROOT)}: not inside a character folder with character.yaml")

    for ypath in yamls:
        cdir = ypath.parent
        rel_dir = cdir.relative_to(ROOT).as_posix()
        data = yaml.safe_load(ypath.read_text(encoding="utf-8")) or {}
        if data.get("id") != cdir.name:
            errors.append(f"{rel_dir}/character.yaml: id must equal folder name '{cdir.name}'")
        if data.get("system") not in SYSTEMS:
            errors.append(f"{rel_dir}/character.yaml: system must be one of {sorted(SYSTEMS)}")
        for k in ("name", "campaign", "summary"):
            if not data.get(k):
                errors.append(f"{rel_dir}/character.yaml: missing '{k}'")

        listed, changed = set(), False
        for a in data.get("assets") or []:
            f = a.get("file", "")
            if f in listed:
                errors.append(f"{rel_dir}/{f}: listed more than once")
            listed.add(f)
            path = cdir / f
            if not path.is_file():
                errors.append(f"{rel_dir}/{f}: listed in assets but file is missing")
                continue
            folder = Path(f).parts[0] if len(Path(f).parts) > 1 else ""
            want = FOLDER_CATEGORY.get(folder)
            if want is None:
                errors.append(f"{rel_dir}/{f}: unknown subfolder '{folder}'")
            elif a.get("category") != want:
                errors.append(f"{rel_dir}/{f}: category '{a.get('category')}' must be '{want}' for this folder")
            if a.get("type") not in TYPES:
                errors.append(f"{rel_dir}/{f}: type must be one of {sorted(TYPES)}")
            if not a.get("subject"):
                errors.append(f"{rel_dir}/{f}: missing subject")
            if a.get("source") and a["source"] not in SOURCES:
                errors.append(f"{rel_dir}/{f}: source must be one of {sorted(SOURCES)}")
            is_video = path.suffix == VIDEO_EXT
            nostamp = path.suffix in NOSTAMP_EXT
            if is_video:
                if not a.get("dimensions"):
                    errors.append(f"{rel_dir}/{f}: .webm needs 'dimensions' set by hand")
            else:
                with Image.open(path) as im:
                    dims = f"{im.width}x{im.height}"
                if a.get("dimensions") != dims:
                    a["dimensions"] = dims
                    changed = True
            entry = {
                **{k: data.get(k) for k in CHARACTER_FIELDS},
                **a,
                "path": f"{rel_dir}/{f}",
                "url": f"{BASE_URL}/{rel_dir}/{f}",
            }
            if not nostamp:
                stamp(path, {**entry, "license": a.get("license"), "owner": data.get("owner")})
            manifest.append(entry)

        for f in sorted([*cdir.rglob("*.webp"), *(f for e in NOSTAMP_EXT for f in cdir.rglob("*" + e))]):
            rel = f.relative_to(cdir).as_posix()
            if not is_working(f) and rel not in listed:
                errors.append(f"{rel_dir}/{rel}: published file has no assets entry")

        if changed:
            ypath.write_text(
                yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8"
            )

    check_icons(errors, manifest)

    if errors:
        print("manifest: validation failed", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"manifest: {len(manifest)} assets, {len(yamls)} characters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
