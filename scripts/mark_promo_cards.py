"""Mark the emoji that advertise their own pack.

Most packs slip a few promo cards in among the emoji: the author's @username,
"more emoji", a link to the emoji bot, "create your name". They render as
ordinary emoji and match ordinary words, so the ranker offered "ссылки на паки"
for the line "Ссылка на оплату в закрепе" - an advertisement for someone else's
pack, inside the owner's post.

No rule separates them from a picture *of* advertising: the same tag "реклама"
sits on "миньон с мегафоном", which is exactly what an announcement post wants.
So the list below is by hand, from reading every record carrying a promo-ish tag,
and each entry names what the card actually shows.

Usage:
    python scripts/mark_promo_cards.py --dry-run
    python scripts/mark_promo_cards.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage

# Labels of cards that sell the pack rather than mean anything. Matched exactly
# against the joined label, so a future emoji labeled "надпись эмодзи дня" is
# unaffected.
PROMO_LABELS = frozenset(
    {
        "ссылки на паки",
        "ссылки автора",
        "надпись emoji bot",
        "надпись emoji1",
        "надпись emoji1 крупно",
        "надпись more emoji",
        "надпись больше эмодзи",
        "надпись больше эмодзи телеграм",
        "надпись создай имя",
        "надпись эмодзи",
    }
)

# Kept deliberately, though they carry the same tags: these depict announcing,
# which a post may legitimately want to say.
KEPT_ON_PURPOSE = ("миньон с мегафоном", "пепе с мегафоном", "надпись ad incoming", "пепе с логотипом")


def main() -> int:
    parser = argparse.ArgumentParser(description="Flag pack self-promo cards as unusable in posts.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    data = library.load_emojis()

    marked: list[str] = []
    cleared = 0
    for record in data.get("emojis", {}).values():
        label = " ".join(record.get("labels", [])).strip().lower()
        if label in PROMO_LABELS:
            if not record.get("promo"):
                marked.append(f"{label}  ({record.get('sticker_set_title', '')})")
            if not args.dry_run:
                record["promo"] = True
        elif record.get("promo"):
            # The label was rewritten and no longer describes a promo card.
            cleared += 1
            if not args.dry_run:
                record.pop("promo", None)

    print(f"помечено рекламных карточек: {len(marked)}")
    for line in sorted(marked):
        print(f"  {line}")
    if cleared:
        print(f"снята пометка: {cleared}")
    print("\nоставлены намеренно (изображают анонс, а не рекламируют пак):")
    for label in KEPT_ON_PURPOSE:
        print(f"  {label}")

    if args.dry_run:
        print("\n--dry-run: ничего не записано")
        return 0

    library._write_json(library.emojis_json, data)
    library.render_emojis_markdown()
    print("\nзаписано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
