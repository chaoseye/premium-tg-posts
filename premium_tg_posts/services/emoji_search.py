from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Variation selectors and ZWJ carry no meaning on their own. Without dropping
# them, a query like "⚡️" would match every emoji containing U+FE0F.
IGNORED_SYMBOLS = frozenset({"\ufe0f", "\ufe0e", "\u200d"})

# Shortest query token allowed to match by prefix. Below this, prefixes are too
# ambiguous to be useful.
MIN_PREFIX = 3
MIN_SUBSTRING = 4

# Share of the longer token that a common stem must cover to count as a match.
STEM_RATIO = 0.6

# Human labels carry the real meaning; the pack title is weak context.
FIELD_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("labels", 3.0),
    ("tags", 2.5),
    ("sticker_set_title", 1.0),
    ("sticker_set_name", 0.5),
)

EXACT = 1.0
PREFIX = 0.6
SUBSTRING = 0.35
SYMBOL_HIT = 4.0


@dataclass(frozen=True)
class EmojiMatch:
    record: dict[str, Any]
    score: float
    matched_on: tuple[str, ...]

    @property
    def custom_emoji_id(self) -> str:
        return str(self.record.get("custom_emoji_id", ""))


def tokenize(value: str | None) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(value or "")]


def query_symbols(value: str | None) -> set[str]:
    """Pictographic characters in the query, so searching by the symbol works too."""
    return {
        char
        for char in (value or "")
        if not char.isalnum() and not char.isspace() and not char.isascii() and char not in IGNORED_SYMBOLS
    }


def _common_prefix_len(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    length = 0
    while length < limit and left[length] == right[length]:
        length += 1
    return length


def token_similarity(query_token: str, field_token: str) -> float:
    if query_token == field_token:
        return EXACT

    if len(query_token) >= MIN_PREFIX and (field_token.startswith(query_token) or query_token.startswith(field_token)):
        return PREFIX

    # Russian inflection often mutates the stem, so one token is not a prefix of
    # the other: "подарок" vs "подарков" diverge at the fleeting vowel. Comparing
    # the shared prefix against the longer token catches those while keeping
    # unrelated words apart ("подарок" vs "подача" shares only 4 of 7).
    shared = _common_prefix_len(query_token, field_token)
    if shared >= MIN_PREFIX and shared >= STEM_RATIO * max(len(query_token), len(field_token)):
        return PREFIX

    if len(query_token) >= MIN_SUBSTRING and query_token in field_token:
        return SUBSTRING
    return 0.0


def _field_tokens(record: dict[str, Any], field: str) -> list[str]:
    raw = record.get(field)
    values: Iterable[Any] = raw if isinstance(raw, list) else [raw]
    tokens: list[str] = []
    for value in values:
        tokens.extend(tokenize(str(value) if value is not None else ""))
    return tokens


def score_record(record: dict[str, Any], tokens: list[str], symbols: set[str]) -> tuple[float, set[str]]:
    """Sum the best per-token hit, so covering more query words ranks higher."""
    matched_on: set[str] = set()
    total = 0.0

    token_cache = {field: _field_tokens(record, field) for field, _ in FIELD_WEIGHTS}
    for query_token in tokens:
        best = 0.0
        best_field: str | None = None
        for field, weight in FIELD_WEIGHTS:
            for field_token in token_cache[field]:
                weighted = token_similarity(query_token, field_token) * weight
                if weighted > best:
                    best = weighted
                    best_field = field
        if best_field:
            total += best
            matched_on.add(best_field)

    if symbols:
        alt = f"{record.get('alt') or ''}{record.get('sticker_emoji') or ''}"
        if any(symbol in alt for symbol in symbols):
            total += SYMBOL_HIT
            matched_on.add("alt")

    return total, matched_on


def search_emojis(records: Iterable[dict[str, Any]], query: str, limit: int = 15) -> list[EmojiMatch]:
    tokens = tokenize(query)
    symbols = query_symbols(query)
    if not tokens and not symbols:
        return []

    matches: list[EmojiMatch] = []
    for record in records:
        score, matched_on = score_record(record, tokens, symbols)
        if score > 0:
            matches.append(EmojiMatch(record=record, score=score, matched_on=tuple(sorted(matched_on))))

    # Newest first among equal scores, so repeated searches stay stable.
    matches.sort(key=lambda match: (match.score, str(match.record.get("last_seen_at", ""))), reverse=True)
    return matches[:limit]


def suggest_for_topic(
    records: Iterable[dict[str, Any]],
    topic: str,
    limit: int = 25,
) -> tuple[list[EmojiMatch], bool]:
    """Candidates for a post topic.

    Returns (matches, is_fallback). An unlabeled library produces no textual
    match at all, so fall back to the most recent emoji and let the caller say
    so, instead of silently presenting them as topic-relevant.
    """
    rows = list(records)
    matches = search_emojis(rows, topic, limit=limit)
    if matches:
        return matches, False

    recent = sorted(rows, key=lambda item: str(item.get("last_seen_at", "")), reverse=True)[:limit]
    return [EmojiMatch(record=record, score=0.0, matched_on=()) for record in recent], True
