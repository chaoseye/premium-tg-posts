"""Give every emoji a baseline label and tags derived from its fallback symbol.

Search matches post text against labels and tags, so a freshly imported library
finds nothing at all. Inspecting thousands of images to fix that is slow and
expensive; the `alt` symbol Telegram already returns carries most of the meaning
for free. This fills the gaps from that symbol, marks what it filled, and leaves
anything a human or agent wrote alone.

Records touched here get `label_source: alt-vocabulary`, so a later visual pass
can tell baseline guesses from real inspection.

Usage:
    python scripts/tag_from_alt.py --dry-run
    python scripts/tag_from_alt.py
    python scripts/tag_from_alt.py --force      # overwrite baseline entries too
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.data.emoji_vocabulary import lookup
from premium_tg_posts.services.storage import LibraryStorage

BASELINE = "alt-vocabulary"


def main() -> int:
    parser = argparse.ArgumentParser(description="Tag emoji from their fallback symbol.")
    parser.add_argument("--dry-run", action="store_true", help="report coverage without writing")
    parser.add_argument("--force", action="store_true", help="also refresh records already tagged from the vocabulary")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    library.ensure()

    records = library.emoji_records()
    updates: dict[str, dict] = {}
    skipped_manual = 0
    unknown: Counter[str] = Counter()

    for record in records:
        emoji_id = str(record.get("custom_emoji_id") or "")
        if not emoji_id:
            continue

        already = bool(record.get("labels")) or bool(record.get("tags"))
        from_vocabulary = record.get("label_source") == BASELINE
        if already and not (args.force and from_vocabulary):
            if not from_vocabulary:
                skipped_manual += 1
            continue

        entry = lookup(record.get("alt"))
        if not entry:
            unknown[str(record.get("alt") or "?")] += 1
            continue

        label, tags = entry
        updates[emoji_id] = {"labels": [label], "tags": list(tags), "label_source": BASELINE}

    covered = len(updates)
    total = len(records)
    missing = sum(unknown.values())
    print(f"эмодзи в базе          : {total}")
    print(f"получат разметку       : {covered} ({covered * 100 // total if total else 0}%)")
    print(f"уже размечены вручную  : {skipped_manual}")
    print(f"нет в словаре          : {missing} ({len(unknown)} различных символов)")

    if unknown:
        print("\nчаще всего не хватает:")
        for alt, count in unknown.most_common(25):
            print(f"  {alt}  x{count}")

    if args.dry_run:
        print("\n--dry-run: ничего не записано")
        return 0

    if updates:
        library.bulk_upsert_emojis(updates)
        print(f"\nзаписано записей: {len(updates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
