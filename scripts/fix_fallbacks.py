"""Pick the fallback character shown where custom emoji do not render.

Telegram needs a plain emoji inside every <tg-emoji> tag. The bot has been using
the sticker's own `alt`, which frequently disagrees with the picture: an emoji
labeled "радость победы" carries 🏐, "с указкой" carries 👨‍⚕️. Readers whose
client hides custom emoji see that character instead - so it should describe the
image, not whatever the pack author happened to attach.

The standard-emoji vocabulary already maps symbol -> words. Running it backwards
finds, for a visual label, the plain emoji that means the same thing. Telegram
accepts any valid emoji as the tag body; verified against the live API before
this script was written.

Usage:
    python scripts/fix_fallbacks.py --dry-run
    python scripts/fix_fallbacks.py --min-score 3.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.data.emoji_vocabulary import VOCABULARY, lookup
from premium_tg_posts.services.emoji_search import EmojiIndex, search_emojis, tokenize
from premium_tg_posts.services.storage import LibraryStorage

# A confident match only. Below this the original character is left alone -
# a wrong fallback is worse than an unrelated one, because it reads as deliberate.
MIN_SCORE = 3.0
# How badly the current character has to fit before it is worth replacing.
MAX_KEEP_SCORE = 1.0

# Who is drawn does not belong in a fallback: the character stands for what is
# happening. Left in, these words dominate - "пепе улыбается" matched the frog
# and would have replaced a perfectly good 😊 with 🐸.
CHARACTER_WORDS = frozenset(
    """пепе мем кот котик кошка утка утёнок миньон смайл лягушка жаба аниме
    существо мужчина женщина девушка девочка мальчик ребёнок парень лицо персонаж
    ням чувак пёс собака хомяк медведь обезьяна свинья птица

    красный красная красное синий синяя зелёный зелёная жёлтый жёлтая чёрный чёрная
    белый белая розовый розовая серый серая фиолетовый оранжевый золотой

    знак табличка надпись иконка фото картинка кадр рисунок силуэт контур
    крупно анфас профиль сбоку сзади маленький большой""".split()
)


# Characters that embarrass a post when the custom emoji does not render. The
# pack's own alt is often one of these for reasons that have nothing to do with
# the picture: 🔫 sits on "стоит прямо", 🔞 on "пепе думает", 🍆 on "кот рыжий",
# 🍑 on "пепе фото" - which appeared three times in one real business post.
RISKY_FALLBACKS = frozenset("🍑🍆💦🖕🔞😈👅💋🩸🚬🍺🍷🔫💊🤮🤢")


def vocabulary_index() -> EmojiIndex:
    """The standard-emoji vocabulary, shaped so the search scorer can rank it."""
    rows = []
    for symbol, (label, tags) in VOCABULARY.items():
        rows.append({"custom_emoji_id": symbol, "alt": symbol, "labels": [label], "tags": list(tags)})
    return EmojiIndex(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Choose a fallback character per emoji.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE)
    parser.add_argument("--show", type=int, default=25, help="how many proposals to print")
    parser.add_argument("--max-keep-score", type=float, default=MAX_KEEP_SCORE,
                        help="how badly the current character must fit before replacing it")
    parser.add_argument("--risky-only", action="store_true",
                        help="only touch emoji whose current character would embarrass a post")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    data = library.load_emojis()
    index = vocabulary_index()

    changed = 0
    kept = 0
    samples = []
    for record in data.get("emojis", {}).values():
        label = " ".join(record.get("labels", []))
        if not label:
            continue

        current = record.get("fallback") or record.get("alt") or ""
        if args.risky_only and current not in RISKY_FALLBACKS:
            kept += 1
            continue

        # What is happening, without who is doing it.
        action = " ".join(w for w in tokenize(label) if w not in CHARACTER_WORDS)
        if not action:
            # Some labels are nothing but who and how - "пепе фото", "котик мем".
            # Stripping leaves nothing to search, and the record kept whatever
            # the pack attached. Fall back to the tags, then to the label as
            # written: any of those beats a peach on a post about an AI agency.
            action = " ".join(w for w in tokenize(" ".join(record.get("tags", []))) if w not in CHARACTER_WORDS)
        if not action:
            action = " ".join(tokenize(label))
        if not action:
            kept += 1
            continue

        current_entry = lookup(current)
        if current_entry:
            # Does the character the pack chose already describe this picture?
            fit = search_emojis(
                [{"custom_emoji_id": current, "labels": [current_entry[0]], "tags": list(current_entry[1])}],
                action, limit=1, expand=False,
            )
            if fit and fit[0].score > args.max_keep_score:
                kept += 1
                continue

        matches = search_emojis(index, action, limit=1, expand=False)
        if not matches or matches[0].score < args.min_score:
            kept += 1
            continue

        symbol = matches[0].custom_emoji_id
        if symbol == current:
            kept += 1
            continue

        if len(samples) < args.show:
            samples.append((label[:26], current, symbol, round(matches[0].score, 1)))
        if not args.dry_run:
            record["fallback"] = symbol
        changed += 1

    print(f"{'подпись':28} {'было':>6}  {'станет':>6}  счёт")
    print("-" * 56)
    for label, before, after, score in samples:
        print(f"{label:28} {before:>6}  {after:>6}  {score}")

    print(f"\nсменят fallback : {changed}")
    print(f"останутся как есть: {kept}")

    if args.dry_run:
        print("--dry-run: ничего не записано")
        return 0

    library._write_json(library.emojis_json, data)
    library.render_emojis_markdown()
    print("записано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
