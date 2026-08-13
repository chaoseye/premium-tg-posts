"""Apply labels written against contact-sheet cell numbers.

Input is a JSON object keyed by the cell number printed on the sheet:

    {"320": {"l": "крик восторга", "t": ["крик", "восторг", "вау", "шок"]}}

The manifest produced by build_contact_sheets.py maps each number to a custom
emoji id, so the numbers alone are enough. Records written here are marked
`label_source: visual`, which outranks the `alt-vocabulary` baseline and tells
a later pass what has already been looked at.

Usage:
    python scripts/apply_visual_labels.py --manifest sheets/manifest.json --labels batch.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage

VISUAL = "visual"


def load_cell_map(manifest_path: Path) -> dict[str, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cells: dict[str, str] = {}
    for sheet in manifest.values():
        cells.update(sheet["cells"])
    return cells


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply visual labels by contact-sheet cell number.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--labels", required=True, help="JSON of {cell: {l: label, t: [tags]}}")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)

    cells = load_cell_map(Path(args.manifest))
    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))

    updates: dict[str, dict] = {}
    unknown: list[str] = []
    for cell, payload in labels.items():
        emoji_id = cells.get(str(cell))
        if not emoji_id:
            unknown.append(str(cell))
            continue
        label = str(payload.get("l") or "").strip()
        tags = [str(tag).strip().lower() for tag in payload.get("t") or [] if str(tag).strip()]
        if not label and not tags:
            continue
        updates[emoji_id] = {
            "labels": [label] if label else [],
            "tags": tags,
            "label_source": VISUAL,
        }

    print(f"ячеек в файле : {len(labels)}")
    print(f"будет записано: {len(updates)}")
    if unknown:
        print(f"неизвестные номера ({len(unknown)}): {', '.join(unknown[:20])}")

    if args.dry_run:
        print("--dry-run: ничего не записано")
        return 0

    if updates:
        # Replace rather than merge: a visual read supersedes the alt guess.
        data = library.load_emojis()
        emojis = data.get("emojis", {})
        for emoji_id, payload in updates.items():
            record = emojis.get(emoji_id)
            if record is None:
                continue
            record["labels"] = payload["labels"]
            record["tags"] = payload["tags"]
            record["label_source"] = VISUAL
        library._write_json(library.emojis_json, data)
        library.render_emojis_markdown()
        print(f"записано: {len(updates)}")

    total = len(library.emoji_records())
    visual = sum(1 for r in library.emoji_records() if r.get("label_source") == VISUAL)
    print(f"размечено визуально: {visual} из {total} ({visual * 100 // total if total else 0}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
