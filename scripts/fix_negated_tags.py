"""Rewrite tags whose negation the tokenizer throws away.

"Не" and "без" are stop words - they have to be, or a label would match every
sentence containing them. But a tag written as two words is tokenised like any
other text, so `не знаю` becomes `знаю` and answers a post saying "знаю, знаю"
with a shrug. Measured on the library: seventeen such tags and labels across
forty-nine emoji, every one of them matching the opposite of what it means.

Each is replaced by a single word that says the same thing without a negation,
chosen against the picture rather than from a dictionary: the shrug becomes
`недоумение`, the neutral face `равнодушие`, the thumbs-down `несогласие`.

This fixes the library's half of the problem. A post keeps losing its own
negation - "я не согласен" still tokenises to "согласен" - which is a separate
and larger job.

Usage:
    python scripts/fix_negated_tags.py --dry-run
    python scripts/fix_negated_tags.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage

# negated tag -> the word it should have been, per the picture it sits on
TAGS = {
    "без эмоций": "равнодушие",          # нейтральные лица, рядом уже стоит «нейтрально»
    "не понял": "непонимание",           # чешет голову, недоумевает
    "не знаю": "недоумение",             # разводит руками
    "не согласен": "несогласие",         # палец вниз
    "без разницы": "безразличие",        # пожимает плечами
    "нет сил": "бессилие",               # устал, выгорание
    "не надо": "нельзя",                 # жест отказа
    "не сплю": "бессонница",             # энергетик, ноутбук в постели
    "не вижу": "зажмурился",             # обезьяна закрыла глаза
    "не спал": "недосып",                # красные глаза
    "без слов": "молчание",              # лицо без эмоций
    "нет слов": "онемел",                # фигура без лица
    "не верю": "недоверие",              # мужчина x doubt
    "не пиши": "молчи",                  # надпись dont ping nerd
    "не спорь": "хватит",                # надпись dont at me
    "не нравится": "неприязнь",          # недовольная гримаса
}

# The one negation that sits in a label. A label describes the picture, so it is
# rewritten rather than swapped for a concept.
LABELS = {"без лица": "безликая фигура"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove negations the tokenizer cannot keep.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    data = library.load_emojis()

    changed_tags: list[tuple[str, str, str]] = []
    changed_labels: list[tuple[str, str]] = []
    for record in data.get("emojis", {}).values():
        label_text = " ".join(record.get("labels", []))

        tags = record.get("tags") or []
        rewritten: list[str] = []
        for tag in tags:
            replacement = TAGS.get(tag.strip().lower())
            if replacement is None:
                rewritten.append(tag)
                continue
            changed_tags.append((label_text, tag, replacement))
            rewritten.append(replacement)
        # A replacement may already be on the record; keep one copy, keep order.
        deduped = list(dict.fromkeys(rewritten))
        if deduped != tags and not args.dry_run:
            record["tags"] = deduped

        labels = record.get("labels") or []
        new_labels = [LABELS.get(label.strip().lower(), label) for label in labels]
        if new_labels != labels:
            changed_labels.append((label_text, " ".join(new_labels)))
            if not args.dry_run:
                record["labels"] = new_labels

    print(f"тегов переписано: {len(changed_tags)} на {len({c[0] for c in changed_tags})} записях\n")
    print(f"{'подпись':32} {'было':14} стало")
    print("-" * 74)
    for label, before, after in sorted(changed_tags):
        print(f"{label[:32]:32} {before:14} {after}")

    for before, after in changed_labels:
        print(f"\nподпись переписана: {before!r} -> {after!r}")

    if args.dry_run:
        print("\n--dry-run: ничего не записано")
        return 0

    library._write_json(library.emojis_json, data)
    library.render_emojis_markdown()
    print("\nзаписано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
