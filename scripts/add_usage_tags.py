"""Attach post vocabulary to the few emoji that already look the part.

Visual labeling answered "what is drawn". Matching needs the other question:
"which word would a post use to mean this". A coverage pass over ~100 words a
Telegram post leans on found sixteen with no result at all.

The first attempt handed each concept to every plausible emoji and made search
worse, not better: a word carried by a dozen emoji stops telling them apart, and
the ranking's own inverse-document-frequency weighting then discounts it. So
each rule is capped - a concept goes to the best few pictures and no further.

Usage:
    python scripts/add_usage_tags.py --dry-run
    python scripts/add_usage_tags.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage

CAP = 3

# (tags, label fragments that should carry them, fragments that disqualify)
# Only words that returned nothing at all before, aimed at the closest picture.
# The exclusions matter: "stonks" alone would hand "инвестиции" to "not stonks",
# which means the opposite.
RULES: list[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = [
    (("вышло", "выпустили"), ("big update",), ()),
    (("тариф", "прайс"), ("ценник", "табличка sale"), ()),
    (("выгода", "экономия"), ("табличка sale", "99 процентов"), ()),
    (("инвестиции", "вложения"), ("stonks",), ("not stonks",)),
    (("сегодня", "неделя", "месяц"), ("с календарём", "календарь"), ("32 июля",)),
    (("жми", "нажми"), ("красная кнопка", "кнопка start"), ()),
    (("регистрация", "участвуй", "конкурс"), ("гора подарков",), ()),
    (("поделись", "репост"), ("карта уно реверс", "фиолетовая стрелка вправо"), ()),
    (("гайд", "инструкция"), ("с указкой",), ()),
    (("совет", "подсказка"), ("лампочка идея",), ()),
    (("проект", "задача"), ("портфель",), ()),
    (("извините", "простите"), ("сложенные ладони",), ()),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Add post vocabulary to a few matching emoji.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cap", type=int, default=CAP, help="max emoji per concept")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    data = library.load_emojis()
    records = list(data.get("emojis", {}).values())

    added = 0
    for tags, patterns, forbidden in RULES:
        chosen = []
        for record in records:
            if len(chosen) >= args.cap:
                break
            label = " ".join(record.get("labels", [])).lower()
            if not label or not any(pattern in label for pattern in patterns):
                continue
            if any(bad in label for bad in forbidden):
                continue
            if all(tag in record.get("tags", []) for tag in tags):
                continue
            chosen.append(record)

        for record in chosen:
            fresh = [tag for tag in tags if tag not in record.get("tags", [])]
            if not args.dry_run:
                record["tags"] = [*record.get("tags", []), *fresh]
            added += len(fresh)

        names = ", ".join(" ".join(r.get("labels", []))[:22] for r in chosen) or "нет подходящих"
        print(f"  {', '.join(tags[:2]):24} -> {names}")

    print(f"\nдобавлено тегов: {added}")
    if args.dry_run:
        print("--dry-run: ничего не записано")
        return 0

    library._write_json(library.emojis_json, data)
    library.render_emojis_markdown()
    print("записано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
