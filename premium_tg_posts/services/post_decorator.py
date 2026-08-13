from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from aiogram.types import MessageEntity
from aiogram.utils.text_decorations import html_decoration

from premium_tg_posts.services.emoji_search import EmojiMatch, search_emojis
from premium_tg_posts.utils.text import tg_emoji_html

# Telegram's own sendMessage ceiling; decorating must not push a post past it.
TELEGRAM_TEXT_LIMIT = 4096

MAX_EMOJI_DEFAULT = 5
# Below this a line has only a weak, mostly accidental match. Leaving the line
# bare beats decorating it with something unrelated.
MIN_LINE_SCORE = 1.0
ALTERNATIVES = 3


@dataclass(frozen=True)
class LineSuggestion:
    index: int
    text: str
    chosen: EmojiMatch | None
    alternatives: tuple[EmojiMatch, ...]


@dataclass(frozen=True)
class DecoratedPost:
    html: str
    suggestions: tuple[LineSuggestion, ...]
    used: tuple[EmojiMatch, ...]
    over_limit: bool

    @property
    def decorated_lines(self) -> int:
        return len(self.used)


def _utf16_len(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def split_lines_with_entities(
    text: str,
    entities: Sequence[MessageEntity] | None,
) -> list[tuple[str, list[MessageEntity]]]:
    """Split into lines, clipping entities to each line.

    Entity offsets are UTF-16 units, so the cursor has to advance in the same
    units. Clipping per line keeps every line independently valid HTML: a bold
    run spanning a newline becomes bold on both lines, which renders the same.
    """
    rows: list[tuple[str, list[MessageEntity]]] = []
    cursor = 0
    for line in text.split("\n"):
        length = _utf16_len(line)
        line_entities: list[MessageEntity] = []
        for entity in entities or []:
            start = max(int(entity.offset), cursor)
            end = min(int(entity.offset) + int(entity.length), cursor + length)
            if end > start:
                line_entities.append(entity.model_copy(update={"offset": start - cursor, "length": end - start}))
        rows.append((line, line_entities))
        cursor += length + 1  # the newline itself is one UTF-16 unit
    return rows


def _starts_with_pictograph(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return False
    first = stripped[0]
    return not first.isalnum() and not first.isascii()


def _has_custom_emoji(entities: Iterable[MessageEntity]) -> bool:
    return any(getattr(entity.type, "value", str(entity.type)) == "custom_emoji" for entity in entities)


def decorate_post(
    text: str,
    entities: Sequence[MessageEntity] | None,
    records: Iterable[dict[str, Any]],
    max_emoji: int = MAX_EMOJI_DEFAULT,
) -> DecoratedPost:
    rows = list(records)
    lines = split_lines_with_entities(text, entities)

    ranked: dict[int, list[EmojiMatch]] = {}
    for index, (line, line_entities) in enumerate(lines):
        if not line.strip():
            continue
        # Respect what the author already put there.
        if _starts_with_pictograph(line) or _has_custom_emoji(line_entities):
            continue
        matches = search_emojis(rows, line, limit=ALTERNATIVES + 3)
        if matches:
            ranked[index] = matches

    # Spend the emoji budget on the strongest lines, not simply the first ones.
    order = sorted(ranked, key=lambda index: (-ranked[index][0].score, index))
    chosen: dict[int, EmojiMatch] = {}
    used_ids: set[str] = set()
    for index in order:
        if len(chosen) >= max_emoji:
            break
        for match in ranked[index]:
            if match.score < MIN_LINE_SCORE:
                break
            if match.custom_emoji_id in used_ids:
                continue
            chosen[index] = match
            used_ids.add(match.custom_emoji_id)
            break

    html_lines: list[str] = []
    suggestions: list[LineSuggestion] = []
    for index, (line, line_entities) in enumerate(lines):
        line_html = html_decoration.unparse(line, line_entities)
        match = chosen.get(index)
        if match:
            item = match.record
            alt = item.get("alt") or item.get("sticker_emoji") or "🎁"
            line_html = f"{tg_emoji_html(match.custom_emoji_id, alt)} {line_html}"
        html_lines.append(line_html)
        if line.strip():
            alternatives = tuple(m for m in ranked.get(index, []) if m is not match)[:ALTERNATIVES]
            suggestions.append(LineSuggestion(index=index, text=line, chosen=match, alternatives=alternatives))

    html = "\n".join(html_lines)
    used = tuple(chosen[index] for index in sorted(chosen))
    return DecoratedPost(
        html=html,
        suggestions=tuple(suggestions),
        used=used,
        over_limit=len(html) > TELEGRAM_TEXT_LIMIT,
    )
