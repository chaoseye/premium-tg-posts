from __future__ import annotations

import unittest

from aiogram.types import MessageEntity

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
        result = decorate_post("Запуск нового тарифа\nСкидка 50 процентов", [], LIBRARY)

        first, second = result.html.split("\n")
        self.assertIn(f'emoji-id="{ROCKET["custom_emoji_id"]}"', first)
        self.assertIn(f'emoji-id="{FIRE["custom_emoji_id"]}"', second)
        self.assertEqual(result.decorated_lines, 2)

    def test_preserves_original_formatting(self) -> None:
        text = "Запуск нового тарифа"
        bold = MessageEntity(type="bold", offset=0, length=6)

        result = decorate_post(text, [bold], LIBRARY)

        self.assertIn("<b>Запуск</b>", result.html)
        self.assertIn("<tg-emoji", result.html)

    def test_preserves_links(self) -> None:
        text = "Запуск тарифа тут"
        link = MessageEntity(type="text_link", offset=14, length=3, url="https://example.com")

        result = decorate_post(text, [link], LIBRARY)

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
        result = decorate_post("Запуск тарифа\nЗапуск второго тарифа", [], LIBRARY)

        used = [match.custom_emoji_id for match in result.used]
        self.assertEqual(len(used), len(set(used)))

    def test_respects_the_emoji_budget(self) -> None:
        text = "\n".join(["Запуск тарифа", "Скидка сегодня", "Срочно дедлайн"])

        result = decorate_post(text, [], LIBRARY, max_emoji=1)

        self.assertEqual(result.decorated_lines, 1)

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
        result = decorate_post("Запуск нового тарифа", [], LIBRARY)

        chosen = [s for s in result.suggestions if s.chosen]
        self.assertTrue(chosen)
        self.assertNotIn(chosen[0].chosen.custom_emoji_id, [a.custom_emoji_id for a in chosen[0].alternatives])

    def test_flags_posts_over_the_telegram_limit(self) -> None:
        long_line = "Запуск тарифа " * 400

        result = decorate_post(long_line, [], LIBRARY)

        self.assertGreater(len(result.html), TELEGRAM_TEXT_LIMIT)
        self.assertTrue(result.over_limit)

    def test_empty_library_decorates_nothing(self) -> None:
        result = decorate_post("Запуск нового тарифа", [], [])

        self.assertEqual(result.decorated_lines, 0)
        self.assertEqual(result.html, "Запуск нового тарифа")

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

        result = decorate_post("Ссылка на оплату в закрепе", [], [promo])

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

        result = decorate_post("Запуск нового тарифа", [], [promo, ROCKET])

        self.assertEqual(result.decorated_lines, 1)
        self.assertEqual(result.used[0].custom_emoji_id, ROCKET["custom_emoji_id"])


if __name__ == "__main__":
    unittest.main()
