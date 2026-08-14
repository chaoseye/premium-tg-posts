"""Replace tags that mean two different things in a post.

Some words are a fine name for a picture and a common function word at the same
time. "Пока" tags thirteen waving hands as a farewell, but a channel post writes
it as a conjunction far more often - "пока не насыплешь корм", "пока оставляю в
работе" - and both of those were decorated with a waving hand.

Replaced rather than deleted, so the concept keeps a word: the farewell is now
`прощание`. A post that literally writes "пока" no longer reaches these emoji;
that is the deliberate half of the trade, since the greeting sense stays covered
by `привет` and `приветствие`, which the same records already carry.

Usage:
    python scripts/fix_ambiguous_tags.py --dry-run
    python scripts/fix_ambiguous_tags.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage

# ambiguous tag -> unambiguous word for the same concept
REPLACEMENTS = {"пока": "прощание"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite tags that a post uses in another sense.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    data = library.load_emojis()

    touched: list[tuple[str, str, str, list[str]]] = []
    for record in data.get("emojis", {}).values():
        tags = record.get("tags") or []
        rewritten = [REPLACEMENTS.get(tag.strip().lower(), tag) for tag in tags]
        if rewritten == tags:
            continue
        deduped = list(dict.fromkeys(rewritten))
        before = next(tag for tag in tags if tag.strip().lower() in REPLACEMENTS)
        touched.append((" ".join(record.get("labels", [])), before, REPLACEMENTS[before.strip().lower()], deduped))
        if not args.dry_run:
            record["tags"] = deduped

    print(f"записей затронуто: {len(touched)}\n")
    print(f"{'подпись':32} {'было':10} {'стало':12} все теги")
    print("-" * 78)
    for label, before, after, tags in sorted(touched):
        print(f"{label[:32]:32} {before:10} {after:12} {','.join(tags)}")

    if args.dry_run:
        print("\n--dry-run: ничего не записано")
        return 0

    library._write_json(library.emojis_json, data)
    library.render_emojis_markdown()
    print("\nзаписано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
