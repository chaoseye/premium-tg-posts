"""Lay emoji previews out as numbered contact sheets for visual labeling.

An agent cannot open five thousand images one by one, but it can read a grid of
a hundred at a glance. Each cell carries an index, and a manifest maps every
index back to its custom emoji id, so labels written against the grid can be
applied without ambiguity.

Sheets are grouped by pack: a pack is visually coherent, and knowing "this is a
Pepe pack" makes the individual cells far easier to read.

Usage:
    python scripts/build_contact_sheets.py --out sheets
    python scripts/build_contact_sheets.py --out sheets --only-untagged --cols 10 --rows 10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage

CELL = 96
PAD = 22          # strip under each cell for its index
BACKGROUND = (250, 250, 250)
GRID = (205, 205, 205)
TEXT = (20, 20, 20)
VISUAL = "visual"


def load_preview(path: Path, size: int) -> Image.Image | None:
    try:
        image = Image.open(path).convert("RGBA")
    except Exception:  # noqa: BLE001 - a broken preview must not stop the sheet
        return None
    image.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2), image)
    return canvas


def build_sheet(entries: list[dict], cols: int, rows: int) -> Image.Image:
    width = cols * CELL
    height = rows * (CELL + PAD)
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet)

    for position, entry in enumerate(entries):
        col, row = position % cols, position // cols
        x, y = col * CELL, row * (CELL + PAD)
        draw.rectangle([x, y, x + CELL - 1, y + CELL + PAD - 1], outline=GRID)

        preview = entry.get("_image")
        if preview is not None:
            sheet.paste(preview, (x, y), preview)

        draw.text((x + 4, y + CELL + 5), f"{entry['n']:>3} {entry['alt']}", fill=TEXT)
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser(description="Build numbered contact sheets of emoji previews.")
    parser.add_argument("--out", required=True, help="directory for sheets and the manifest")
    parser.add_argument("--cols", type=int, default=10)
    parser.add_argument("--rows", type=int, default=10)
    parser.add_argument("--only-untagged", action="store_true",
                        help="skip emoji already labeled by a visual pass")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    per_sheet = args.cols * args.rows
    by_pack: dict[str, list[dict]] = defaultdict(list)
    for record in library.emoji_records(sort_by="last_seen_at", reverse=True):
        if args.only_untagged and record.get("label_source") == VISUAL:
            continue
        preview = record.get("preview_path")
        if not preview:
            continue
        by_pack[str(record.get("sticker_set_name") or "unknown")].append(record)

    manifest: dict[str, dict] = {}
    sheet_index = 0
    counter = 0
    skipped = 0

    for pack in sorted(by_pack):
        records = by_pack[pack]
        for start in range(0, len(records), per_sheet):
            chunk = records[start : start + per_sheet]
            entries = []
            for record in chunk:
                image = load_preview(library.root / record["preview_path"], CELL - 8)
                if image is None:
                    skipped += 1
                    continue
                counter += 1
                entries.append(
                    {
                        "n": counter,
                        "alt": record.get("alt") or "",
                        "id": record["custom_emoji_id"],
                        "_image": image,
                    }
                )
            if not entries:
                continue

            sheet_index += 1
            name = f"sheet-{sheet_index:03d}-{pack[:28]}.png"
            build_sheet(entries, args.cols, args.rows).save(out_dir / name)
            manifest[name] = {
                "pack": pack,
                "pack_title": chunk[0].get("sticker_set_title") or pack,
                "cells": {str(entry["n"]): entry["id"] for entry in entries},
            }
            print(f"{name}  {len(entries)} шт.")

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nлистов: {sheet_index}, эмодзи: {counter}, пропущено превью: {skipped}")
    print(f"манифест: {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
