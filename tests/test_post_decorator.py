from __future__ import annotations

import unittest

from aiogram.types import MessageEntity

from premium_tg_posts.services.emoji_search import search_emojis
from premium_tg_posts.services.post_decorator import (
    TELEGRAM_TEXT_LIMIT,
    decorate_post,
    split_lines_with_entities,
)

ROCKET = {
    "custom_emoji_id": "2000000000000000001",
    "alt": "🚀",
    "labels": ["ракета"],
    "tags": ["запуск", "старт", "релиз"],
    "last_seen_at": "2026-08-13T10:00:00+00:00",
}
FIRE = {
    "custom_emoji_id": "2000000000000000002",
    "alt": "🔥",
    "labels": ["огонь"],
    "tags": ["скидка", "горячо", "распродажа"],
    "last_seen_at": "2026-08-13T11:00:00+00:00",
}
CLOCK = {
    "custom_emoji_id": "2000000000000000003",
    "alt": "⏰",
    "labels": ["часы"],
    "tags": ["срочно", "дедлайн", "время"],
    "last_seen_at": "2026-08-13T12:00:00+00:00",
}
LIBRARY = [ROCKET, FIRE, CLOCK]

# Scores are IDF-weighted, and IDF sits at its floor until a library has tens of
# records, so a three-emoji fixture scores a perfect tag hit at 1.5 - under the
# shipped threshold. These tests are about placement, formatting and budget, so
# they pass a threshold that lets a match through and leave calibration to
# ThresholdTests below.
MECHANICS_SCORE = 0.5


def padded_library(records: list[dict], size: int = 60) -> list[dict]:
    """The same records in a library big enough for IDF to mean something."""
    filler = [
        {
            "custom_emoji_id": f"210000000000000{index:04d}",
            "alt": "🔸",
            "labels": ["ромб"],
            "tags": ["фигура"],
            "last_seen_at": "2026-08-13T09:00:00+00:00",
        }
        for index in range(size - len(records))
    ]
    return [*records, *filler]


class SplitLinesTests(unittest.TestCase):
    def test_entity_spanning_lines_is_clipped_to_each(self) -> None:
        text = "Первая строка\nВторая строка"
        bold = MessageEntity(type="bold", offset=0, length=27)

        rows = split_lines_with_entities(text, [bold])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1][0].offset, 0)
        self.assertEqual(rows[0][1][0].length, 13)
        self.assertEqual(rows[1][1][0].offset, 0)
        self.assertEqual(rows[1][1][0].length, 13)

    def test_entity_offsets_are_utf16_aware(self) -> None:
        # The emoji occupies two UTF-16 units, so the entity on line two must
        # still line up after it.
        text = "🎁 подарок\nвторая"
        bold = MessageEntity(type="bold", offset=11, length=6)

        rows = split_lines_with_entities(text, [bold])

        self.assertEqual(rows[1][0], "вторая")
        self.assertEqual(rows[1][1][0].offset, 0)
        self.assertEqual(rows[1][1][0].length, 6)

    def test_line_without_entities_stays_empty(self) -> None:
        rows = split_lines_with_entities("одна\nдве", [])
        self.assertEqual([entities for _, entities in rows], [[], []])


class DecoratePostTests(unittest.TestCase):
    def test_inserts_emoji_matching_each_line(self) -> None:
        result = decorate_post("Запуск нового тарифа\nСкидка 50 процентов", [], LIBRARY, min_score=MECHANICS_SCORE)

        first, second = result.html.split("\n")
        self.assertIn(f'emoji-id="{ROCKET["custom_emoji_id"]}"', first)
        self.assertIn(f'emoji-id="{FIRE["custom_emoji_id"]}"', second)
        self.assertEqual(result.decorated_lines, 2)

    def test_preserves_original_formatting(self) -> None:
        text = "Запуск нового тарифа"
        bold = MessageEntity(type="bold", offset=0, length=6)

        result = decorate_post(text, [bold], LIBRARY, min_score=MECHANICS_SCORE)

        self.assertIn("<b>Запуск</b>", result.html)
        self.assertIn("<tg-emoji", result.html)

    def test_preserves_links(self) -> None:
        text = "Запуск тарифа тут"
        link = MessageEntity(type="text_link", offset=14, length=3, url="https://example.com")

        result = decorate_post(text, [link], LIBRARY, min_score=MECHANICS_SCORE)

        self.assertIn('<a href="https://example.com">тут</a>', result.html)

    def test_skips_lines_that_already_start_with_an_emoji(self) -> None:
        result = decorate_post("🎉 Запуск нового тарифа", [], LIBRARY)

        self.assertEqual(result.decorated_lines, 0)
        self.assertNotIn("<tg-emoji", result.html)

    def test_skips_lines_that_already_carry_a_custom_emoji(self) -> None:
        text = "X Запуск нового тарифа"
        existing = MessageEntity(type="custom_emoji", offset=0, length=1, custom_emoji_id="999")

        result = decorate_post(text, [existing], LIBRARY)

        self.assertEqual(result.decorated_lines, 0)

    def test_blank_lines_are_left_alone(self) -> None:
        result = decorate_post("Запуск нового тарифа\n\nСкидка 50 процентов", [], LIBRARY)

        self.assertEqual(result.html.split("\n")[1], "")

    def test_never_repeats_the_same_emoji(self) -> None:
        result = decorate_post("Запуск тарифа\nЗапуск второго тарифа", [], LIBRARY, min_score=MECHANICS_SCORE)

        used = [match.custom_emoji_id for match in result.used]
        self.assertEqual(len(used), len(set(used)))

    def test_respects_the_emoji_budget(self) -> None:
        text = "\n".join(["Запуск тарифа", "Скидка сегодня", "Срочно дедлайн"])

        result = decorate_post(text, [], LIBRARY, max_emoji=1, min_score=MECHANICS_SCORE)

        self.assertEqual(result.decorated_lines, 1)

    def test_shipped_threshold_rejects_a_loose_label_hit(self) -> None:
        # "канале" against the label "канате" is the shape the threshold exists
        # for: a real prefix match on a visual description, meaning nothing.
        rope = padded_library([{
            "custom_emoji_id": "2000000000000000020",
            "alt": "🐈",
            "labels": ["кот на канате"],
            "tags": ["кот", "баланс", "мем"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }])

        result = decorate_post("Что вам интереснее на канале", [], rope)

        self.assertEqual(result.decorated_lines, 0)

    def test_shipped_threshold_keeps_a_tag_hit(self) -> None:
        gift = padded_library([{
            "custom_emoji_id": "2000000000000000021",
            "alt": "🎁",
            "labels": ["коробка с бантом"],
            "tags": ["подарок", "розыгрыш", "сюрприз"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }])

        result = decorate_post("Разыгрываем подарок среди подписчиков", [], gift)

        self.assertEqual(result.decorated_lines, 1)

    def test_threshold_is_calibrated_for_a_grown_library(self) -> None:
        # Documented consequence, not an accident: scores are IDF-weighted and
        # IDF sits at its floor until a library has tens of records, so the same
        # emoji and the same line decorate in a grown library and not in a tiny
        # one. A freshly started profile decorates little until it fills up.
        line = "Разыгрываем подарок среди подписчиков"
        gift = {
            "custom_emoji_id": "2000000000000000022",
            "alt": "🎁",
            "labels": ["коробка с бантом"],
            "tags": ["подарок", "розыгрыш", "сюрприз"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertEqual(decorate_post(line, [], [gift]).decorated_lines, 0)
        self.assertEqual(decorate_post(line, [], padded_library([gift])).decorated_lines, 1)

    def test_weak_matches_are_not_used(self) -> None:
        weak = [{
            "custom_emoji_id": "2000000000000000009",
            "alt": "❓",
            "labels": [],
            "tags": [],
            "sticker_set_title": "Topics",
            "last_seen_at": "2026-08-13T10:00:00+00:00",
        }]

        result = decorate_post("topicsandmore", [], weak)

        self.assertEqual(result.decorated_lines, 0)

    def test_reports_alternatives_per_line(self) -> None:
        result = decorate_post("Запуск нового тарифа", [], LIBRARY, min_score=MECHANICS_SCORE)

        chosen = [s for s in result.suggestions if s.chosen]
        self.assertTrue(chosen)
        self.assertNotIn(chosen[0].chosen.custom_emoji_id, [a.custom_emoji_id for a in chosen[0].alternatives])

    def test_flags_posts_over_the_telegram_limit(self) -> None:
        long_line = "Запуск тарифа " * 400

        result = decorate_post(long_line, [], LIBRARY, min_score=MECHANICS_SCORE)

        self.assertGreater(len(result.html), TELEGRAM_TEXT_LIMIT)
        self.assertTrue(result.over_limit)

    def test_empty_library_decorates_nothing(self) -> None:
        result = decorate_post("Запуск нового тарифа", [], [])

        self.assertEqual(result.decorated_lines, 0)
        self.assertEqual(result.html, "Запуск нового тарифа")

    def test_an_emoji_the_author_typed_is_not_a_search_term(self) -> None:
        # Regression: on a real post, the line "Напишите цифру в комментариях 👇"
        # was decorated from an emoji whose alt is 👇 - a small green frog - and
        # a symbol hit outscores any word, so it also took one of five slots.
        frog = {
            "custom_emoji_id": "2000000000000000030",
            "alt": "👇",
            "labels": ["пепе маленький зелёный"],
            "tags": ["пепе", "маленький", "мило"],
            "last_seen_at": "2026-08-15T10:00:00+00:00",
        }
        surprise = {
            "custom_emoji_id": "2000000000000000031",
            "alt": "😮",
            "labels": ["кот с большими глазами"],
            "tags": ["удивление", "кот"],
            "last_seen_at": "2026-08-15T09:00:00+00:00",
        }
        library = padded_library([frog, surprise])

        result = decorate_post(
            "Какой пункт удивил вас больше всего 👇", [], library, min_score=MECHANICS_SCORE
        )

        self.assertEqual(result.decorated_lines, 1)
        self.assertEqual(result.used[0].custom_emoji_id, surprise["custom_emoji_id"])

    def test_find_still_searches_by_symbol(self) -> None:
        # The same character remains a query when someone asks for it directly.
        frog = {
            "custom_emoji_id": "2000000000000000032",
            "alt": "👇",
            "labels": ["пепе маленький зелёный"],
            "tags": ["пепе"],
            "last_seen_at": "2026-08-15T10:00:00+00:00",
        }

        self.assertTrue(search_emojis([frog], "👇"))

    def test_pack_advertisement_is_never_placed(self) -> None:
        # Regression: the line "Ссылка на оплату в закрепе" was decorated with a
        # card advertising someone else's emoji pack, because it does name links.
        promo = {
            "custom_emoji_id": "2000000000000000010",
            "alt": "©️",
            "labels": ["ссылки на паки"],
            "tags": ["ссылка", "реклама", "паки"],
            "promo": True,
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        result = decorate_post("Ссылка на оплату в закрепе", [], [promo], min_score=MECHANICS_SCORE)

        self.assertEqual(result.decorated_lines, 0)
        self.assertNotIn(promo["custom_emoji_id"], result.html)

    def test_a_promo_card_does_not_consume_the_budget(self) -> None:
        # It must be gone before ranking, not merely skipped when chosen -
        # otherwise it still occupies a line's best slot.
        promo = {
            "custom_emoji_id": "2000000000000000011",
            "alt": "©️",
            "labels": ["запуск"],
            "tags": ["запуск", "старт", "релиз"],
            "promo": True,
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        result = decorate_post("Запуск нового тарифа", [], [promo, ROCKET], min_score=MECHANICS_SCORE)

        self.assertEqual(result.decorated_lines, 1)
        self.assertEqual(result.used[0].custom_emoji_id, ROCKET["custom_emoji_id"])


if __name__ == "__main__":
    unittest.main()
