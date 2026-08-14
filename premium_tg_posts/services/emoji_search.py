from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Small numerals count something else in a post - "два часа", "три подписки",
# "пять человек", "Первое - ..., Второе - ...". In the library the same words
# describe what is inside a picture: "три пальца", "два миньона", "две ладони".
# An exact match between the two is almost always a false friend, and it scores
# full marks, so a post about three subscriptions was given a picture of a hand.
#
# Dropped from the library's own words as well as from queries, which is the
# point: "три пальца" stays reachable as "пальцы". Round and large numbers are
# deliberately absent - a post saying "сорок лет" or "тысяча подписчиков" does
# mean that number, and "утка 40" should answer it. Digits are kept too, so
# "2024" still finds the emoji of that year.
# The collective forms count the same way - "Двое поругались, третий подлил
# масла" was decorated from the label "двое в баре" - and so do the multiplying
# adverbs. "Пара" is deliberately absent: it names a couple as often as it counts
# ("пара приёмов" versus "влюблённая пара"), and ten emoji are tagged with it in
# the second sense.
NUMERAL_WORDS = frozenset(
    """
    один одна одно два две три четыре пять шесть семь восемь девять десять
    первый первое первая первых второй второе вторая третий третье третья
    четвёртый четвертый четвёртое четвертое пятый пятое
    двое трое четверо пятеро шестеро семеро оба обе
    вдвое втрое вчетверо
    двоих двоим двоими троих троим троими четверых четверым четверыми
    пятерых пятерым шестерых семерых обоих обоим обоими обеих обеим обеими
    одного одному одним одном одной одну двух двум двумя трёх трех трём трем тремя
    четырёх четырех четырём четырьмя пяти пятью шести шестью семи
    восьми восемью восьмью девяти девятью десяти десятью
    первого первому первым первом второго второму втором третьего третьему третьем
    """.split()
)

# One case form is missing from that list on purpose. "Семью" is the instrumental
# of "семь" and the accusative of "семья" at the same time, and two emoji are
# tagged `семья`, which a post reaches today by writing "всей семьёй". Dropping
# the word would cost that to save nothing: no label or tag contains it.

# Words that describe a pose in the library and something else entirely in a
# post. Forty-three labels read "стоит ...", and every one of them keeps its
# meaning in its tags - "стоит в форме" is [школа, форма], "стоит спокойно" is
# [жду, спокойно]. A post saying "стоит" almost always means what a thing costs,
# so "Он бесплатный и стоит на каждом компьютере" was decorated from "стоит в
# форме", and "держите его прямо сейчас" from "стоит прямо".
#
# "Сидит" and "лежит" were checked and left alone: a post saying them usually
# does mean the posture ("кот сидит на клавиатуре", "лежат на складе").
POSE_WORDS = frozenset("стоит стою прямо ровно".split())

# Function words carry no meaning but match exactly and outweigh real hits: a
# label like "звёзды в глазах" would score its "в" against the "в" in any
# sentence. Reactions that happen to be short ("ок", "да", "нет") stay in.
#
# The list was incidental and had gaps: "твой" was in it but "твоя" was not, "до"
# and "от" were but "после" was not, so a tag written as two words leaked its
# preposition into the vocabulary and "Счёт выставят после подписания" was
# decorated from "после тренировки". Every word added below was first checked
# against the library and appears in no label or tag except those leaks.
#
# "Себя", "себе" and "собой" are deliberately absent: they carry the meaning of
# the emoji that use them - "обнимает себя" answers "берегите себя" and "не
# ругать себя", "доволен собой" answers exactly that.
STOP_WORDS = NUMERAL_WORDS | POSE_WORDS | frozenset(
    """
    а бы в во вот все всё где да для до же за и из или к как ко когда ли меня мне мы на
    над не нет ни но о об от по под при про с со та так там те то тут ты у уже чем что
    чтобы эта эти это этот я он она оно они вы его её ее их наш ваш мой твой был была
    было были быть есть очень еще ещё только если тоже там сюда туда
    без почти каждый свой вам нам нас них тебя ним потом снова опять
    после перед через между около против кроме вместо среди ради возле мимо
    моя моё мои твоя твоё твои наша наше наши ваша ваше ваши сам сама само сами
    здесь сейчас теперь тогда иначе зато однако лишь разве неужели
    кто кого кому чей какая какой какое какие
    a an and as at be but by for from has have if in into is it its of on or that the
    their then there these this to too was were will with you your
    """.split()
)

# Variation selectors and ZWJ carry no meaning on their own. Without dropping
# them, a query like "⚡️" would match every emoji containing U+FE0F.
IGNORED_SYMBOLS = frozenset({"\ufe0f", "\ufe0e", "\u200d"})

# Shortest query token allowed to match by prefix. Below this, prefixes are too
# ambiguous to be useful. The tag side is guarded by STEM_RATIO instead, since
# what matters there is not the tag's length but how much of the query it covers.
MIN_PREFIX = 3
MIN_SUBSTRING = 4

# Index granularity. Must not exceed MIN_PREFIX, or the candidate filter would
# drop rows that token_similarity would still match.
WINDOW = 3

# Share of the longer token that a common stem must cover to count as a match.
STEM_RATIO = 0.6
# ...and the stem must be at least this long. Three letters passes the ratio on
# two five-letter words, which matched "месяц" against "месит тесто" in a real
# post. Four costs 0.007 P@5 on the eval set - one position in one query - and
# removes the false pair, so it wins.
STEM_MIN = 4
# A stem this long is convincing on its own, whatever the length ratio says:
# "подписаться" and "подписка" share six letters but only 55% of the longer one.
STEM_ABSOLUTE = 5

# Rare tags say more than common ones. A tag carried by a quarter of the library
# ("пепе", "мем") barely narrows anything, while "дедлайн" on a handful of emoji
# nearly identifies them. Weight every field token by its inverse document
# frequency, normalised so a tag on PIVOT_DF records scores its plain weight.
# The range is deliberately narrow. A/B over 30 queries on a 5310-emoji library:
# plain 0.79 P@5, with a wide 0.4-1.6 band 0.82, with this one 0.83 - and a
# gentler band deviates less from the hand-set field weights, so it is the safer
# of two near-equal options.
USE_IDF = True
PIVOT_DF = 50
IDF_MIN = 0.6
IDF_MAX = 1.3

# Human labels carry the real meaning; the pack title is weak context.
FIELD_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("labels", 3.0),
    ("tags", 2.5),
    ("sticker_set_title", 1.0),
    ("sticker_set_name", 0.5),
)

# A label says what the picture shows; a tag says what a post would call it.
# Only the second is a vocabulary, so only the second is worth matching loosely.
# Reading a label approximately is where the false friends came from: "минут"
# found "минус", "канале" found "канате", "спорят" found "спорт", "следим" found
# "след" - each a genuine four-letter stem on a word describing an image. Over
# the eval set, refusing those costs nothing and hit@1 goes to 1.00; the loss is
# that an inflected word no longer reaches a label, so "подарки" finds the emoji
# through its tags rather than through the label "подарок".
STRICT_FIELDS = frozenset({"labels"})

EXACT = 1.0
PREFIX = 0.6
SUBSTRING = 0.35
SYMBOL_HIT = 4.0

# Related concepts reached through the tag graph count, but never outrank a
# direct hit on the query itself.
EXPANSION = 0.4

# A word found in both the label and the tags is better evidence than the same
# word in one of them, so the runner-up field is added at a discount instead of
# being discarded. Measured on 30 queries against the real library: 0.82 P@5
# taking only the best field, 0.83 anywhere from 0.2 to 0.5, 0.81 at 0.7. The
# plateau means the exact value hardly matters; this is its middle.
SECOND_FIELD = 0.35


@dataclass(frozen=True)
class EmojiMatch:
    record: dict[str, Any]
    score: float
    matched_on: tuple[str, ...]

    @property
    def custom_emoji_id(self) -> str:
        return str(self.record.get("custom_emoji_id", ""))


def tokenize(value: str | None) -> list[str]:
    return [
        token
        for token in (raw.lower() for raw in TOKEN_RE.findall(value or ""))
        if token not in STOP_WORDS
    ]


def query_symbols(value: str | None) -> set[str]:
    """Pictographic characters in the query, so searching by the symbol works too."""
    return {
        char
        for char in (value or "")
        if not char.isalnum() and not char.isspace() and not char.isascii() and char not in IGNORED_SYMBOLS
    }


# Where two words part, an inflected ending begins with a vowel or a sign:
# "улицу"/"улице", "двери"/"дверь", "вопросы"/"вопросом". Words that part on a
# consonant have different stems: "минут"/"минус", "канале"/"канате",
# "спорят"/"спорт".
#
# As a general rule this is false - "зелёный"/"зелёным" and "закрыл"/"закрыт"
# part on consonants and are one word each - which is why it only ever relaxes
# strict matching, never tightens loose matching. Those pairs are refused on a
# label today and stay refused; nothing a label matches now stops matching.
INFLECTION_ENDINGS = frozenset("аеёиоуыэюяьъй")


def _endings_look_inflectional(left: str, right: str) -> bool:
    return bool(left) and bool(right) and left[0] in INFLECTION_ENDINGS and right[0] in INFLECTION_ENDINGS


def _common_prefix_len(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    length = 0
    while length < limit and left[length] == right[length]:
        length += 1
    return length


def token_similarity(query_token: str, field_token: str, strict: bool = False) -> float:
    """How well a query word matches one word of a record.

    `strict` allows only the same word or one extending the other, refusing the
    looser stem and substring rules. See STRICT_FIELDS for why some fields ask
    for it.
    """
    if query_token == field_token:
        return EXACT

    shared = _common_prefix_len(query_token, field_token)
    shorter, longer = sorted((len(query_token), len(field_token)))

    # One token extends the other: "чаты" over "чат". Containment alone is not
    # enough - the shorter token also has to account for most of the longer one,
    # or a short tag latches onto anything that starts with it. Measured on the
    # real library, the unguarded rule matched "ад" against "адрес", "пол"
    # against "полная", and the stray pack-name letter "f" against every English
    # word in a post.
    if len(query_token) >= MIN_PREFIX and shared == shorter and shorter >= STEM_RATIO * longer:
        return PREFIX

    if strict and not _endings_look_inflectional(query_token[shared:], field_token[shared:]):
        return 0.0

    # Russian inflection often mutates the stem, so neither token contains the
    # other: "подарок" vs "подарков" diverge at the fleeting vowel. Comparing
    # the shared prefix against the longer token catches those while keeping
    # unrelated words apart ("подарок" vs "подача" shares only 4 of 7).
    if shared >= STEM_ABSOLUTE:
        return PREFIX
    if shared >= STEM_MIN and shared >= STEM_RATIO * longer:
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


class EmojiIndex:
    """Tokenised view of a library, built once and reused across queries.

    Decorating a post runs one search per line. Re-tokenising every record for
    every line dominates the cost once a library reaches thousands of emoji, so
    the tokens are computed here and the scorer just reads them.
    """

    __slots__ = ("records", "field_tokens", "alts", "windows", "short", "idf")

    def __init__(self, records: Iterable[dict[str, Any]]) -> None:
        self.records = list(records)
        self.field_tokens: list[dict[str, list[str]]] = []
        self.alts: list[str] = []
        # token window -> record positions, so a query only scores plausible rows
        self.windows: dict[str, set[int]] = {}
        # field tokens shorter than a window, kept whole
        self.short: dict[str, set[int]] = {}
        doc_freq: dict[str, int] = {}

        for position, record in enumerate(self.records):
            cache = {field: _field_tokens(record, field) for field, _ in FIELD_WEIGHTS}
            self.field_tokens.append(cache)
            self.alts.append(f"{record.get('alt') or ''}{record.get('sticker_emoji') or ''}")
            for token in {token for tokens in cache.values() for token in tokens}:
                doc_freq[token] = doc_freq.get(token, 0) + 1
            for tokens in cache.values():
                for token in tokens:
                    if len(token) < WINDOW:
                        self.short.setdefault(token, set()).add(position)
                        continue
                    for start in range(len(token) - WINDOW + 1):
                        self.windows.setdefault(token[start : start + WINDOW], set()).add(position)

        self.idf = self._build_idf(doc_freq, len(self.records))

    @staticmethod
    def _build_idf(doc_freq: dict[str, int], total: int) -> dict[str, float]:
        if not USE_IDF or total <= 0:
            return {}
        pivot = math.log(total / min(PIVOT_DF, max(total, 1))) or 1.0
        weights: dict[str, float] = {}
        for token, freq in doc_freq.items():
            raw = math.log(total / (1 + freq))
            weights[token] = min(IDF_MAX, max(IDF_MIN, raw / pivot))
        return weights

    def __len__(self) -> int:
        return len(self.records)

    def candidates(self, tokens: list[str], symbols: set[str]) -> list[int]:
        """Positions worth scoring for this query.

        Every match kind in `token_similarity` requires the query and the field
        token to share their first WINDOW characters, or the query to appear
        inside the field token - and in both cases the query's leading window is
        one of the field token's windows. Short field tokens are indexed whole
        and checked separately, so nothing is silently dropped.
        """
        if symbols:
            return list(range(len(self.records)))

        found: set[int] = set()
        for token in tokens:
            if len(token) >= WINDOW:
                found |= self.windows.get(token[:WINDOW], set())
            else:
                found |= self.short.get(token, set())
            # Field tokens below a window are absent from `windows`, so they are
            # scanned separately. The prefix rule caps how far apart in length a
            # matching pair may be, and past that bound no short token can reach
            # this query - "ок" can still be found by "оке", never by "окажется".
            if len(token) * STEM_RATIO <= WINDOW - 1:
                for short_token, positions in self.short.items():
                    if token.startswith(short_token) or short_token.startswith(token):
                        found |= positions
        return sorted(found)


def build_index(records: Iterable[dict[str, Any]] | EmojiIndex) -> EmojiIndex:
    return records if isinstance(records, EmojiIndex) else EmojiIndex(records)


def _score_tokens(
    token_cache: dict[str, list[str]],
    alt: str,
    tokens: list[str],
    symbols: set[str],
    idf: dict[str, float] | None = None,
) -> tuple[float, set[str]]:
    """Sum the best per-token hit, so covering more query words ranks higher."""
    matched_on: set[str] = set()
    total = 0.0

    for query_token in tokens:
        per_field: list[tuple[float, str]] = []
        for field, weight in FIELD_WEIGHTS:
            strict = field in STRICT_FIELDS
            best_here = 0.0
            for field_token in token_cache[field]:
                similarity = token_similarity(query_token, field_token, strict)
                if not similarity:
                    continue
                weighted = similarity * weight
                if idf:
                    weighted *= idf.get(field_token, 1.0)
                best_here = max(best_here, weighted)
            if best_here:
                per_field.append((best_here, field))

        if per_field:
            per_field.sort(reverse=True)
            total += per_field[0][0]
            matched_on.add(per_field[0][1])
            # The same word corroborated by a second field counts, at a discount.
            if len(per_field) > 1:
                total += SECOND_FIELD * per_field[1][0]
                matched_on.add(per_field[1][1])

    if symbols and any(symbol in alt for symbol in symbols):
        total += SYMBOL_HIT
        matched_on.add("alt")

    return total, matched_on


def score_record(record: dict[str, Any], tokens: list[str], symbols: set[str]) -> tuple[float, set[str]]:
    """Score a single record. Convenience wrapper; hot paths use the index."""
    token_cache = {field: _field_tokens(record, field) for field, _ in FIELD_WEIGHTS}
    alt = f"{record.get('alt') or ''}{record.get('sticker_emoji') or ''}"
    return _score_tokens(token_cache, alt, tokens, symbols)


def expand_tokens(
    records: Iterable[dict[str, Any]] | EmojiIndex,
    tokens: list[str],
    limit: int = 12,
) -> list[str]:
    """Second hop through the tag graph.

    Emoji whose own tags or labels match a query word contribute their *other*
    tags as related concepts. That lets "запуск" reach an emoji tagged
    "старт, ракета" even though the topic never says "ракета". The library's own
    annotations act as the concept graph, so no external model is involved.
    """
    if not tokens:
        return []

    index = build_index(records)
    direct = set(tokens)
    related: dict[str, int] = {}
    for position in index.candidates(tokens, set()):
        cache = index.field_tokens[position]
        tag_tokens = cache["tags"]
        if not tag_tokens and not cache["labels"]:
            continue
        # Same reading rules as scoring, or a label the scorer refuses to match
        # loosely would still pull the record in through its sibling tags.
        reached = any(
            token_similarity(token, own) > 0 for token in tokens for own in tag_tokens
        ) or any(
            token_similarity(token, own, strict=True) > 0 for token in tokens for own in cache["labels"]
        )
        if not reached:
            continue
        for tag_token in tag_tokens:
            if tag_token in direct:
                continue
            related[tag_token] = related.get(tag_token, 0) + 1

    ranked = sorted(related.items(), key=lambda item: (-item[1], item[0]))
    return [term for term, _ in ranked[:limit]]


def search_emojis(
    records: Iterable[dict[str, Any]] | EmojiIndex,
    query: str,
    limit: int = 15,
    expand: bool = True,
) -> list[EmojiMatch]:
    tokens = tokenize(query)
    symbols = query_symbols(query)
    if not tokens and not symbols:
        return []

    index = build_index(records)

    scored: dict[int, tuple[float, set[str]]] = {}
    for position in index.candidates(tokens, symbols):
        score, matched_on = _score_tokens(
            index.field_tokens[position], index.alts[position], tokens, symbols, index.idf
        )
        if score > 0:
            scored[position] = (score, matched_on)

    # Reach for related concepts only where the query itself missed. Scoring a
    # direct hit against expansion terms would feed it its own sibling tags back,
    # inflating whichever emoji happens to carry the most tags.
    if expand:
        expanded = expand_tokens(index, tokens)
        for position in index.candidates(expanded, set()) if expanded else []:
            if position in scored:
                continue
            related_score, related_fields = _score_tokens(
                index.field_tokens[position], index.alts[position], expanded, set(), index.idf
            )
            if related_score > 0:
                scored[position] = (related_score * EXPANSION, related_fields | {"related"})

    matches = [
        EmojiMatch(record=index.records[position], score=score, matched_on=tuple(sorted(matched_on)))
        for position, (score, matched_on) in scored.items()
    ]

    # Direct hits always outrank related ones, whatever the numbers say. A weight
    # alone is not enough: an emoji sharing several generic tags accumulates more
    # than one naming the query outright. Newest first among equals, so repeated
    # searches stay stable.
    matches.sort(
        key=lambda match: (
            "related" not in match.matched_on,
            match.score,
            str(match.record.get("last_seen_at", "")),
        ),
        reverse=True,
    )
    return matches[:limit]


def is_promo(record: dict[str, Any]) -> bool:
    """Does this emoji advertise the pack it came from?

    Packs ship self-promo cards among their emoji: the author's @username, a
    link to the emoji bot, "more emoji", "create your name". They are valid
    emoji and stay in the library - the owner may still want to send one - but
    they mean nothing, so nothing may offer them for a post. Marked by hand on
    the record, because no rule separates them from a picture *of* advertising:
    a megaphone tagged "реклама" is exactly what an announcement post wants.
    """
    return bool(record.get("promo"))


def for_posts(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The part of a library worth putting into someone's post."""
    return [record for record in records if not is_promo(record)]


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
    rows = for_posts(records)
    matches = search_emojis(rows, topic, limit=limit)
    if matches:
        return matches, False

    recent = sorted(rows, key=lambda item: str(item.get("last_seen_at", "")), reverse=True)[:limit]
    return [EmojiMatch(record=record, score=0.0, matched_on=()) for record in recent], True

