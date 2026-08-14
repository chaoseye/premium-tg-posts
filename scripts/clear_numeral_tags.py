"""Drop count words from tags where the emoji is not about that count.

A tag is meant to be a word a post would use to mean the emoji. Bare numerals
fail that test on hand gestures: "три пальца" is tagged `три`, so every post
saying "три подписки", "три раза быстрее" or "Три месяца не писал" scored an
exact hit and got a picture of a hand. Same for `первый`/`второй`/`третий`,
which in a post almost always enumerate ("Первое — ..., Второе — ...") rather
than name a place.

Numbers that are the emoji's own subject keep their words: "утка 40" stays
findable by `сорок`, "надпись 1000" by `тысяча`. There a post using the number
usually does mean that number.

Labels are left alone - they describe the picture, and "три пальца" is what the
picture shows.

Usage:
    python scripts/clear_numeral_tags.py --dry-run
    python scripts/clear_numeral_tags.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage

# Counting words that hijack ordinary sentences.
DROP = frozenset(
    {
        "один",
        "одна",
        "два",
        "две",
        "три",
        "четыре",
        "пять",
        "счёт",
        "счет",
        "первый",
        "первое",
        "первая",
        "второй",
        "второе",
        "третий",
        "третье",
    }
)

# Kept on purpose: these emoji *are* the number they name.
KEPT_ON_PURPOSE = ("десять — табличка 10", "сорок — утка 40", "тысяча — надпись 1000", "18+ — возрастная метка")


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove bare count words from emoji tags.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    data = library.load_emojis()

    touched: list[tuple[str, list[str], list[str]]] = []
    for record in data.get("emojis", {}).values():
        tags = record.get("tags") or []
        kept = [tag for tag in tags if tag.strip().lower() not in DROP]
        if len(kept) == len(tags):
            continue
        removed = [tag for tag in tags if tag.strip().lower() in DROP]
        touched.append((" ".join(record.get("labels", [])), removed, kept))
        if not args.dry_run:
            record["tags"] = kept

    print(f"записей затронуто: {len(touched)}, тегов снято: {sum(len(r) for _, r, _ in touched)}\n")
    print(f"{'подпись':30} {'снято':22} осталось")
    print("-" * 78)
    for label, removed, kept in sorted(touched):
        print(f"{label[:30]:30} {','.join(removed)[:22]:22} {','.join(kept)}")

    empty = [label for label, _, kept in touched if not kept]
    if empty:
        print(f"\nостались совсем без тегов ({len(empty)}): {', '.join(empty)}")

    print("\nсохранены намеренно (эмодзи и есть это число):")
    for line in KEPT_ON_PURPOSE:
        print(f"  {line}")

    if args.dry_run:
        print("\n--dry-run: ничего не записано")
        return 0

    library._write_json(library.emojis_json, data)
    library.render_emojis_markdown()
    print("\nзаписано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
