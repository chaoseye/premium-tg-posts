"""Remove tags that are not words for anything.

A tag is meant to be a word a post would use to mean the emoji. A few tags I
wrote while labeling describe the caption or the pose instead, and because they
are ordinary words they match ordinary sentences at full strength: "Смотрите,
как не надо делать рассылки" was decorated with a toilet, whose tags read
`туалет, wc, надо`.

Each removal below was checked against its own record. Words that look like
filler but carry the picture's meaning were kept: `наконец` on a sigh of relief,
`давно` on a cobwebbed face (a post saying "давно не писал" wants exactly that),
`пока` on a waving hand, `точно` on the "fax" meme, and every imperative -
`жми`, `читай`, `смотри`, `дарю` - since a post does use those words that way.

Usage:
    python scripts/clear_junk_tags.py --dry-run
    python scripts/clear_junk_tags.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage

# tag -> why it says nothing about the picture
JUNK = {
    "надо": "на «туалет wc» — обрывок подписи, к унитазу отношения не имеет",
    "внутри": "на «пепе в помещении» — наречие места, пост говорит «внутри инструкция»",
    "просто": "на «миньон на белом» — смысл уже несёт «чисто»",
    "ничего": "на «чёрный кадр» — смысл уже несут «тьма» и «пусто»",
    "вот": "на указывающих жестах — частица, смысл несёт «указание»",
    "прямо": "на «смотрит в камеру» — в постах это усилитель: «прямо сейчас»",
    "сегодня": "на «утка с календарём» — слишком частое слово для слабого ответа",
    "стоит": "на «пепе в полный рост» — в постах это «сколько стоит» и «стоит купить»",
}

KEPT_ON_PURPOSE = (
    "наконец — «выдох облегчения»",
    "давно — «паутина на лице», пост «давно не писал» хочет именно её",
    "пока — «машет рукой», это прощание",
    "точно — «надпись fax», это и есть смысл мема",
    "жми, читай, смотри, дарю, иду, несу — повелительные, пост их так и употребляет",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Drop meaningless tags.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    data = library.load_emojis()

    touched: list[tuple[str, list[str], list[str]]] = []
    for record in data.get("emojis", {}).values():
        tags = record.get("tags") or []
        kept = [tag for tag in tags if tag.strip().lower() not in JUNK]
        if len(kept) == len(tags):
            continue
        removed = [tag for tag in tags if tag.strip().lower() in JUNK]
        touched.append((" ".join(record.get("labels", [])), removed, kept))
        if not args.dry_run:
            record["tags"] = kept

    print(f"записей затронуто: {len(touched)}, тегов снято: {sum(len(r) for _, r, _ in touched)}\n")
    print(f"{'подпись':32} {'снято':12} осталось")
    print("-" * 78)
    for label, removed, kept in sorted(touched):
        print(f"{label[:32]:32} {','.join(removed)[:12]:12} {','.join(kept)}")

    empty = [label for label, _, kept in touched if not kept]
    if empty:
        print(f"\nостались без тегов ({len(empty)}): {', '.join(empty)}")

    print("\nпохожие на мусор, но оставлены:")
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
