from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from premium_tg_posts.services.emoji_search import (
    EmojiIndex,
    expand_tokens,
    for_posts,
    search_emojis,
    suggest_for_topic,
    token_similarity,
    tokenize,
)
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.utils.text import emoji_fallback

GIFT = {
    "custom_emoji_id": "1000000000000000001",
    "alt": "🎁",
    "labels": ["подарок коробка"],
    "sticker_set_title": "Gifts",
    "last_seen_at": "2026-08-13T10:00:00+00:00",
}
FIRE = {
    "custom_emoji_id": "1000000000000000002",
    "alt": "🔥",
    "labels": ["огонь пламя"],
    "sticker_set_title": "Gifts",
    "last_seen_at": "2026-08-13T11:00:00+00:00",
}
ZAP = {
    "custom_emoji_id": "1000000000000000003",
    "alt": "⚡️",
    "labels": [],
    "sticker_set_title": "Topics",
    "last_seen_at": "2026-08-13T12:00:00+00:00",
}
BANG = {
    "custom_emoji_id": "1000000000000000004",
    "alt": "❗️",
    "labels": [],
    "sticker_set_title": "Topics",
    "last_seen_at": "2026-08-13T13:00:00+00:00",
}
ALL = [GIFT, FIRE, ZAP, BANG]


class TokenSimilarityTests(unittest.TestCase):
    def test_exact_beats_prefix(self) -> None:
        self.assertGreater(token_similarity("огонь", "огонь"), token_similarity("огон", "огонек"))

    def test_russian_inflection_with_mutating_stem(self) -> None:
        # Neither is a prefix of the other, but they share the stem.
        self.assertFalse("подарков".startswith("подарок"))
        self.assertGreater(token_similarity("подарков", "подарок"), 0.0)
        self.assertGreater(token_similarity("скидки", "скидка"), 0.0)

    def test_unrelated_words_sharing_a_short_head_do_not_match(self) -> None:
        self.assertEqual(token_similarity("подача", "подарок"), 0.0)

    def test_english_prefix_still_matches(self) -> None:
        self.assertGreater(token_similarity("fire", "firework"), 0.0)

    def test_short_tokens_do_not_prefix_match(self) -> None:
        self.assertEqual(token_similarity("да", "давление"), 0.0)


class SearchTests(unittest.TestCase):
    def test_finds_by_label(self) -> None:
        matches = search_emojis(ALL, "подарок")
        self.assertTrue(matches)
        self.assertEqual(matches[0].custom_emoji_id, GIFT["custom_emoji_id"])
        self.assertIn("labels", matches[0].matched_on)

    def test_finds_by_inflected_query_through_tags(self) -> None:
        tagged = {**GIFT, "tags": ["подарок", "розыгрыш"]}
        matches = search_emojis([tagged, FIRE, ZAP, BANG], "розыгрыш подарков")
        self.assertTrue(matches)
        self.assertEqual(matches[0].custom_emoji_id, GIFT["custom_emoji_id"])

    def test_an_inflected_word_does_not_reach_a_label_on_its_own(self) -> None:
        # The other half of the same contract: a label describes the picture, so
        # it is read strictly. "подарков" reaches this emoji only once someone
        # writes the tag; that is what tags are for.
        self.assertEqual(search_emojis([GIFT], "розыгрыш подарков"), [])
        self.assertTrue(search_emojis([GIFT], "подарок"))

    def test_label_outranks_pack_title(self) -> None:
        # "Gifts" is the pack title for both; only GIFT carries the label.
        matches = search_emojis(ALL, "подарок gifts")
        self.assertEqual(matches[0].custom_emoji_id, GIFT["custom_emoji_id"])
        self.assertGreater(matches[0].score, matches[1].score)

    def test_multi_word_query_ranks_broader_coverage_higher(self) -> None:
        both = search_emojis([GIFT], "подарок коробка")[0].score
        single = search_emojis([GIFT], "подарок")[0].score
        self.assertGreater(both, single)

    def test_finds_by_emoji_symbol(self) -> None:
        matches = search_emojis(ALL, "⚡️")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].custom_emoji_id, ZAP["custom_emoji_id"])
        self.assertIn("alt", matches[0].matched_on)

    def test_variation_selector_does_not_match_every_emoji(self) -> None:
        # Both ZAP and BANG contain U+FE0F; only the real pictograph may match.
        matches = search_emojis(ALL, "⚡️")
        self.assertNotIn(BANG["custom_emoji_id"], [m.custom_emoji_id for m in matches])

    def test_no_match_returns_empty(self) -> None:
        self.assertEqual(search_emojis(ALL, "квантовая механика"), [])

    def test_blank_query_returns_empty(self) -> None:
        self.assertEqual(search_emojis(ALL, "   "), [])

    def test_limit_is_respected(self) -> None:
        self.assertEqual(len(search_emojis(ALL, "gifts topics", limit=2)), 2)


ROCKET = {
    "custom_emoji_id": "3000000000000000001",
    "alt": "🚀",
    "labels": ["ракета"],
    "tags": ["запуск", "старт", "релиз"],
    "last_seen_at": "2026-08-13T10:00:00+00:00",
}
PACKAGE = {
    "custom_emoji_id": "3000000000000000002",
    "alt": "📦",
    "labels": ["коробка"],
    "tags": ["релиз", "версия"],
    "last_seen_at": "2026-08-13T11:00:00+00:00",
}
UNRELATED = {
    "custom_emoji_id": "3000000000000000003",
    "alt": "🐱",
    "labels": ["кот"],
    "tags": ["животное", "мем"],
    "last_seen_at": "2026-08-13T12:00:00+00:00",
}
TAGGED = [ROCKET, PACKAGE, UNRELATED]


class TagExpansionTests(unittest.TestCase):
    def test_expansion_collects_sibling_tags(self) -> None:
        terms = expand_tokens(TAGGED, ["запуск"])
        self.assertIn("старт", terms)
        self.assertIn("релиз", terms)
        self.assertNotIn("запуск", terms)  # the query word itself is not a new concept

    def test_reaches_emoji_with_no_shared_word(self) -> None:
        # "запуск" never appears in PACKAGE, but both share the concept "релиз".
        direct = search_emojis(TAGGED, "запуск", expand=False)
        expanded = search_emojis(TAGGED, "запуск", expand=True)

        self.assertEqual([m.custom_emoji_id for m in direct], [ROCKET["custom_emoji_id"]])
        self.assertIn(PACKAGE["custom_emoji_id"], [m.custom_emoji_id for m in expanded])

    def test_related_hits_never_outrank_direct_ones(self) -> None:
        matches = search_emojis(TAGGED, "запуск")
        self.assertEqual(matches[0].custom_emoji_id, ROCKET["custom_emoji_id"])
        self.assertGreater(matches[0].score, matches[1].score)

    def test_related_hits_are_marked(self) -> None:
        matches = search_emojis(TAGGED, "запуск")
        package = next(m for m in matches if m.custom_emoji_id == PACKAGE["custom_emoji_id"])
        self.assertIn("related", package.matched_on)

    def test_expansion_does_not_drag_in_everything(self) -> None:
        matches = search_emojis(TAGGED, "запуск")
        self.assertNotIn(UNRELATED["custom_emoji_id"], [m.custom_emoji_id for m in matches])

    def test_tag_count_does_not_inflate_a_direct_hit(self) -> None:
        # Regression: expansion used to feed a matching emoji its own sibling
        # tags back, so the most heavily tagged emoji won regardless of how well
        # it actually matched.
        precise = {
            "custom_emoji_id": "3000000000000000010",
            "alt": "🏷",
            "labels": ["скидка"],
            "tags": ["скидка"],
            "last_seen_at": "2026-08-13T10:00:00+00:00",
        }
        noisy = {
            "custom_emoji_id": "3000000000000000011",
            "alt": "🐱",
            "labels": ["кот"],
            "tags": ["скидка", *(f"тег{i}" for i in range(10))],
            "last_seen_at": "2026-08-13T11:00:00+00:00",
        }

        matches = search_emojis([precise, noisy], "скидка")

        self.assertEqual(matches[0].custom_emoji_id, precise["custom_emoji_id"])


class StopWordTests(unittest.TestCase):
    def test_function_words_are_dropped(self) -> None:
        self.assertEqual(tokenize("звёзды в глазах"), ["звёзды", "глазах"])
        self.assertEqual(tokenize("смешно до смерти"), ["смешно", "смерти"])

    def test_a_pose_word_does_not_answer_a_price(self) -> None:
        # Regression: "Он бесплатный и стоит на каждом компьютере" was decorated
        # from the label "стоит в форме", and "держите его прямо сейчас" from
        # "стоит прямо".
        pose = {
            "custom_emoji_id": "9300000000000000001",
            "alt": "🧍",
            "labels": ["стоит в форме"],
            "tags": ["школа", "форма", "готова"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertEqual(search_emojis([pose], "Он бесплатный и стоит на каждом компьютере"), [])
        self.assertEqual(search_emojis([pose], "держите его прямо сейчас"), [])
        self.assertTrue(search_emojis([pose], "школьная форма"))

    def test_posture_that_still_means_itself_is_kept(self) -> None:
        # "Сидит" and "лежит" mean the posture in a post too, so they stay words.
        cat = {
            "custom_emoji_id": "9300000000000000002",
            "alt": "🐈",
            "labels": ["кот сидит"],
            "tags": ["кот", "жду", "мем"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertTrue(search_emojis([cat], "кот сидит на клавиатуре"))

    def test_live_broadcast_survives(self) -> None:
        # "Прямо" is a stop word but "прямой" is not - "прямой эфир" is a concept.
        live = {
            "custom_emoji_id": "9300000000000000003",
            "alt": "🔴",
            "labels": ["надпись live"],
            "tags": ["эфир", "прямой эфир", "трансляция"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertTrue(search_emojis([live], "сегодня прямой эфир"))

    def test_a_multi_word_tag_does_not_leak_its_preposition(self) -> None:
        # Regression: the tag "после тренировки" put "после" in the vocabulary,
        # and "Счёт выставят после подписания" was decorated from it.
        gym = {
            "custom_emoji_id": "9400000000000000001",
            "alt": "🏃",
            "labels": ["качок с полотенцем"],
            "tags": ["после тренировки", "устал"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertEqual(search_emojis([gym], "Счёт выставят после подписания"), [])
        self.assertTrue(search_emojis([gym], "устал после тренировки"))

    def test_possessive_forms_are_all_covered(self) -> None:
        # "твой" was a stop word but "твоя" was not, so the tag "твоя проблема"
        # answered any sentence containing it.
        self.assertEqual(tokenize("твоя проблема"), ["проблема"])
        self.assertEqual(tokenize("моя наша ваша твои мои"), [])

    def test_self_reference_still_carries_meaning(self) -> None:
        # Not every function-looking word is empty: these are what the emoji mean.
        hug = {
            "custom_emoji_id": "9400000000000000002",
            "alt": "🤗",
            "labels": ["обнимает себя"],
            "tags": ["уют", "тепло", "самоподдержка"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertTrue(search_emojis([hug], "Берегите себя"))

    def test_meaningful_short_words_survive(self) -> None:
        self.assertIn("ок", tokenize("ок"))
        self.assertIn("нло", tokenize("нло"))

    def test_preposition_in_a_label_cannot_match_a_sentence(self) -> None:
        # Regression: "звёзды в глазах" scored its "в" against any sentence
        # containing "в", outranking emoji the sentence actually names.
        starry = {
            "custom_emoji_id": "5000000000000000001",
            "alt": "🤩",
            "labels": ["звёзды в глазах"],
            "tags": ["восторг", "вау"],
            "last_seen_at": "2026-08-13T10:00:00+00:00",
        }
        question = {
            "custom_emoji_id": "5000000000000000002",
            "alt": "❓",
            "labels": ["вопрос"],
            "tags": ["вопрос", "непонятно"],
            "last_seen_at": "2026-08-13T11:00:00+00:00",
        }

        matches = search_emojis([starry, question], "Пишите вопросы в комментарии")

        self.assertTrue(matches)
        self.assertEqual(matches[0].custom_emoji_id, question["custom_emoji_id"])
        self.assertNotIn(starry["custom_emoji_id"], [m.custom_emoji_id for m in matches])


class NegationTests(unittest.TestCase):
    """A negated word must not answer as if it were affirmed."""

    DEAD = {
        "custom_emoji_id": "9000000000000000101",
        "alt": "💀",
        "labels": ["красный крестик умер"],
        "tags": ["умер", "конец", "жесть"],
        "last_seen_at": "2026-08-15T10:00:00+00:00",
    }

    def test_the_governed_word_goes_with_the_particle(self) -> None:
        self.assertEqual(tokenize("отказал клиенту и не умер"), ["отказал", "клиенту"])
        self.assertEqual(tokenize("сказал это без объяснений"), ["сказал"])
        self.assertEqual(tokenize("ни одной знакомой улицы"), ["улицы"])

    def test_function_words_do_not_shield_the_governed_word(self) -> None:
        self.assertEqual(tokenize("это было не очень хорошо"), [])

    def test_the_opposite_emoji_is_no_longer_found(self) -> None:
        # Regression: this line scored 5.0 on a picture meaning the opposite,
        # the highest of any emoji in its post.
        self.assertEqual(search_emojis([self.DEAD], "Впервые отказал клиенту и не умер"), [])
        self.assertTrue(search_emojis([self.DEAD], "проект умер тихо"))

    def test_an_affirmative_line_is_untouched(self) -> None:
        self.assertEqual(tokenize("Спасибо, что были рядом"), ["спасибо", "рядом"])

    def test_the_bare_no_is_left_alone(self) -> None:
        # A post writes "нет" as an answer as often as a negation, so it does
        # not govern the next word.
        self.assertEqual(tokenize("Сказал нет спокойно"), ["сказал", "спокойно"])


class NegatedTagTests(unittest.TestCase):
    """A tag must not lose its "не" and start meaning the opposite."""

    SHRUG = {
        "custom_emoji_id": "9100000000000000001",
        "alt": "🤷",
        "labels": ["разводит руками"],
        "tags": ["недоумение", "безразличие"],
        "last_seen_at": "2026-08-15T10:00:00+00:00",
    }

    def test_a_negated_tag_carries_nothing(self) -> None:
        # Why the tags were rewritten. Before the query side learned about
        # negation, a tag spelled "не знаю" read as "знаю" and answered "знаю,
        # знаю" with a shrug; now it reads as nothing at all. Either way it is
        # not a word for the picture, which is what a tag has to be.
        self.assertEqual(tokenize("не знаю"), [])
        self.assertEqual(tokenize("без эмоций"), [])

    def test_the_rewritten_tag_no_longer_answers_its_opposite(self) -> None:
        self.assertEqual(search_emojis([self.SHRUG], "Выкатили в пятницу, знаю, знаю"), [])

    def test_the_rewritten_tag_still_answers_its_own_meaning(self) -> None:
        self.assertTrue(search_emojis([self.SHRUG], "полное недоумение"))
        self.assertTrue(search_emojis([self.SHRUG], "безразличие ко всему"))


class NumeralTests(unittest.TestCase):
    """A number in a post counts something the picture is not about."""

    def test_small_numerals_are_dropped(self) -> None:
        # "Писал" is governed by "не" and goes with it; see NegationTests.
        self.assertEqual(tokenize("Три месяца не писал"), ["месяца"])
        self.assertEqual(tokenize("Отключить на два часа"), ["отключить", "часа"])
        self.assertEqual(tokenize("Первое — разборы проектов"), ["разборы", "проектов"])

    def test_collective_numerals_are_dropped(self) -> None:
        # Regression: "Двое поругались" was decorated from the label "двое в баре".
        self.assertEqual(tokenize("Двое поругались, третий подлил масла"), ["поругались", "подлил", "масла"])
        self.assertEqual(tokenize("Поднял обе руки"), ["поднял", "руки"])
        self.assertEqual(tokenize("Выручка выросла вдвое"), ["выручка", "выросла"])

    def test_case_forms_are_dropped_too(self) -> None:
        # Regression: "двое" was a stop word but "двоих" was not, so "Десерт
        # делят на двоих" was decorated from the label "разговор двоих".
        self.assertEqual(tokenize("Десерт делят на двоих"), ["десерт", "делят"])
        self.assertEqual(tokenize("машет обеими лапками"), ["машет", "лапками"])
        self.assertEqual(tokenize("в двух словах о первом"), ["словах"])

    def test_family_is_not_a_numeral(self) -> None:
        # "Семью" is the instrumental of "семь" and the accusative of "семья" at
        # once. Two emoji are tagged `семья`, so the word stays.
        family = {
            "custom_emoji_id": "9200000000000000001",
            "alt": "👵",
            "labels": ["пожилая женщина"],
            "tags": ["возраст", "семья"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertIn("семью", tokenize("собрались всей семью"))
        self.assertTrue(search_emojis([family], "провёл вечер с семьёй"))

    def test_a_couple_is_not_a_count(self) -> None:
        # "Пара" names a couple as often as it counts, and the library uses it
        # in that sense, so it stays a word.
        self.assertIn("пара", tokenize("влюблённая пара на скамейке"))

    def test_larger_and_written_numbers_survive(self) -> None:
        # A post saying these does mean the number, and the library has emoji of
        # exactly them.
        for word in ("сорок", "тысяча", "миллион", "2024", "10"):
            with self.subTest(word=word):
                self.assertIn(word, tokenize(f"нам {word} лет"))

    def test_a_gesture_no_longer_answers_a_counted_noun(self) -> None:
        # Regression: "три подписки" scored an exact hit on the tag "три" and
        # the post was decorated with a picture of a hand.
        hand = {
            "custom_emoji_id": "9700000000000000001",
            "alt": "✌️",
            "labels": ["три пальца"],
            "tags": ["жест"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertEqual(search_emojis([hand], "Разыгрываем три подписки"), [])

    def test_the_gesture_stays_reachable_by_what_it_shows(self) -> None:
        hand = {
            "custom_emoji_id": "9700000000000000002",
            "alt": "✌️",
            "labels": ["три пальца"],
            "tags": ["жест"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertTrue(search_emojis([hand], "пальца вверх"))
        self.assertTrue(search_emojis([hand], "жест рукой"))

    def test_loneliness_is_not_a_numeral(self) -> None:
        # "один" is dropped, but the sense the label carried lives in its tags.
        lonely = {
            "custom_emoji_id": "9700000000000000003",
            "alt": "😔",
            "labels": ["пепе грустит один"],
            "tags": ["грусть", "одиночество"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertTrue(search_emojis([lonely], "сижу в одиночестве"))


class DirectVersusRelatedTests(unittest.TestCase):
    def test_direct_hit_outranks_a_higher_scoring_related_one(self) -> None:
        # Regression: weighting alone let an emoji sharing several generic tags
        # accumulate more than one the query names outright.
        named = {
            "custom_emoji_id": "6000000000000000001",
            "alt": "😂",
            "labels": ["смех"],
            "tags": ["смех"],
            "last_seen_at": "2026-08-13T10:00:00+00:00",
        }
        seed = {
            "custom_emoji_id": "6000000000000000002",
            "alt": "🤣",
            "labels": ["хохот"],
            "tags": ["смех", "весело", "угар", "прикол", "радость"],
            "last_seen_at": "2026-08-13T11:00:00+00:00",
        }
        bystander = {
            "custom_emoji_id": "6000000000000000003",
            "alt": "🫢",
            "labels": ["рука у рта"],
            "tags": ["весело", "угар", "прикол", "радость"],
            "last_seen_at": "2026-08-13T12:00:00+00:00",
        }

        matches = search_emojis([named, seed, bystander], "смех")
        ids = [m.custom_emoji_id for m in matches]

        direct = {named["custom_emoji_id"], seed["custom_emoji_id"]}
        self.assertTrue(set(ids[:2]) <= direct, f"related hit ranked into the top: {ids}")


class FallbackCharacterTests(unittest.TestCase):
    def test_prefers_the_chosen_fallback(self) -> None:
        record = {"alt": "🚪", "fallback": "🙂", "sticker_emoji": "🚪"}
        self.assertEqual(emoji_fallback(record), "🙂")

    def test_falls_back_to_alt_then_sticker_then_default(self) -> None:
        self.assertEqual(emoji_fallback({"alt": "🔥"}), "🔥")
        self.assertEqual(emoji_fallback({"sticker_emoji": "🔥"}), "🔥")
        self.assertEqual(emoji_fallback({}), "🎁")
        self.assertEqual(emoji_fallback({}, "emoji"), "emoji")

    def test_blank_fields_do_not_win(self) -> None:
        self.assertEqual(emoji_fallback({"fallback": "", "alt": "🔥"}), "🔥")


class StemLengthTests(unittest.TestCase):
    def test_long_shared_stem_matches_despite_length_ratio(self) -> None:
        # "подписаться" and "подписка" share six letters, but only 55% of the
        # longer one - the ratio rule alone rejected this and /find returned
        # nothing for "подписаться".
        self.assertGreater(token_similarity("подписаться", "подписка"), 0.0)

    def test_short_shared_head_still_rejected(self) -> None:
        self.assertEqual(token_similarity("подача", "подарок"), 0.0)

    def test_three_letter_stem_on_short_words_is_rejected(self) -> None:
        # Regression: "месяц" passed the ratio rule against "месит" on three
        # shared letters and a post about "этот месяц" was given "месит тесто".
        self.assertEqual(token_similarity("месяц", "месит"), 0.0)

    def test_real_inflections_still_match(self) -> None:
        for query, field in (
            ("подарков", "подарок"),
            ("скидки", "скидка"),
            ("работал", "работа"),
            ("выгорел", "выгорание"),
            ("огонь", "огонек"),
        ):
            with self.subTest(query=query):
                self.assertGreater(token_similarity(query, field), 0.0)

    def test_subscribe_query_finds_the_emoji(self) -> None:
        record = {
            "custom_emoji_id": "7000000000000000001",
            "alt": "📣",
            "labels": ["призыв подписаться"],
            "tags": ["подписка", "подпишись", "канал"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }
        self.assertTrue(search_emojis([record], "подписаться"))


class PrefixLengthTests(unittest.TestCase):
    """A tag may only prefix-match a word of comparable length."""

    def test_short_tag_does_not_latch_onto_a_longer_word(self) -> None:
        # Regression: the rule checked the query's length but not the tag's, so
        # a post about "адрес" was decorated from a tag "ад", and "полная
        # занятость" from "пол".
        self.assertEqual(token_similarity("адрес", "ад"), 0.0)
        self.assertEqual(token_similarity("полная", "пол"), 0.0)
        self.assertEqual(token_similarity("потерять", "пот"), 0.0)

    def test_stray_pack_letter_matches_nothing(self) -> None:
        # Pack names leave single letters in the vocabulary ("f", "2"). Unguarded
        # they matched every word starting with them.
        self.assertEqual(token_similarity("frogemoji", "f"), 0.0)
        self.assertEqual(token_similarity("2024", "2"), 0.0)

    def test_a_derived_word_reaches_its_root(self) -> None:
        # "Кофейня" covers 57% of "кофе" - under the old bar, so a post about a
        # new coffee shop reached none of the emoji tagged `кофе`.
        self.assertGreater(token_similarity("кофейня", "кофе"), 0.0)
        self.assertGreater(token_similarity("спортсмен", "спорт"), 0.0)
        self.assertGreater(token_similarity("усталость", "устал"), 0.0)

    def test_the_lower_bar_still_refuses_what_it_was_built_for(self) -> None:
        for query, field in (("полная", "пол"), ("адрес", "ад"), ("домашний", "дом"), ("frogemoji", "f")):
            with self.subTest(query=query):
                self.assertEqual(token_similarity(query, field), 0.0)

    def test_real_extensions_still_match(self) -> None:
        for query, field in (("чаты", "чат"), ("кот", "котик"), ("мемы", "мем")):
            with self.subTest(query=query):
                self.assertGreater(token_similarity(query, field), 0.0)

    def test_guard_applies_in_both_directions(self) -> None:
        self.assertEqual(token_similarity("ад", "адрес"), token_similarity("адрес", "ад"))

    def test_one_letter_tag_cannot_pull_an_emoji_into_the_results(self) -> None:
        stray = {
            "custom_emoji_id": "9500000000000000001",
            "alt": "🙃",
            "labels": [],
            "tags": ["f"],
            "sticker_set_name": "f",
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }
        self.assertEqual(search_emojis([stray], "frogemoji"), [])


class StrictLabelTests(unittest.TestCase):
    """A label says what the picture shows, so it is read word for word."""

    MINUS = {
        "custom_emoji_id": "9600000000000000001",
        "alt": "➖",
        "labels": ["иконка минус люди"],
        "tags": ["убрать", "уход", "сокращение"],
        "last_seen_at": "2026-08-14T10:00:00+00:00",
    }

    def test_a_diverging_stem_no_longer_matches_a_label(self) -> None:
        # Regression: "минут" and "минус" share four letters of five, so a line
        # reading "обнимают через минуту" scored 6.2 on a picture meaning
        # "remove people" - the highest-scoring emoji in that whole post.
        self.assertEqual(search_emojis([self.MINUS], "обнимают тебя через минуту"), [])
        self.assertEqual(search_emojis([self.MINUS], "нужно десять минут"), [])

    def test_the_label_still_answers_its_own_word(self) -> None:
        self.assertTrue(search_emojis([self.MINUS], "поставил минус"))
        self.assertTrue(search_emojis([self.MINUS], "убрать лишних"))

    def test_labels_still_extend(self) -> None:
        # Strict is not exact-only: one word may still extend the other.
        self.assertGreater(token_similarity("чаты", "чат", strict=True), 0.0)
        self.assertEqual(token_similarity("минут", "минус", strict=True), 0.0)
        self.assertEqual(token_similarity("канале", "канате", strict=True), 0.0)

    def test_labels_accept_an_inflected_ending(self) -> None:
        # Where the words part on a vowel or a sign, they are two forms of one
        # word and the label answers: a post saying "вышел на улицу" should
        # reach the label "стоит на улице".
        for query, field in (("улицу", "улице"), ("двери", "дверь"), ("вопросы", "вопросом"), ("скидки", "скидка")):
            with self.subTest(query=query):
                self.assertGreater(token_similarity(query, field, strict=True), 0.0)

    def test_labels_refuse_a_consonant_split(self) -> None:
        for query, field in (("минут", "минус"), ("канале", "канате"), ("спорят", "спорт"), ("заказ", "закат")):
            with self.subTest(query=query):
                self.assertEqual(token_similarity(query, field, strict=True), 0.0)

    def test_the_ending_rule_only_ever_relaxes(self) -> None:
        # It is not true in general - "зелёный"/"зелёным" part on consonants and
        # are one word - so it may never decide a loose match. On a tag that pair
        # still matches; on a label it stays refused, as it was before the rule.
        self.assertGreater(token_similarity("зелёным", "зелёный"), 0.0)
        self.assertEqual(token_similarity("зелёным", "зелёный", strict=True), 0.0)

    def test_a_refused_label_does_not_return_through_expansion(self) -> None:
        # Regression: closing the label in scoring alone let the record back in
        # as a "related" hit, since the tag graph still read labels loosely.
        rope = {
            "custom_emoji_id": "9600000000000000002",
            "alt": "🐈",
            "labels": ["кот на канате"],
            "tags": ["кот", "баланс", "мем"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }

        self.assertEqual(search_emojis([rope], "что вам интереснее на канале"), [])


class FieldCorroborationTests(unittest.TestCase):
    def test_word_in_both_label_and_tags_outranks_one_field(self) -> None:
        both = {
            "custom_emoji_id": "9000000000000000001",
            "alt": "🔥",
            "labels": ["огонь"],
            "tags": ["огонь"],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }
        label_only = {
            "custom_emoji_id": "9000000000000000002",
            "alt": "🔥",
            "labels": ["огонь"],
            "tags": ["прочее"],
            "last_seen_at": "2026-08-14T11:00:00+00:00",
        }

        matches = search_emojis([label_only, both], "огонь", expand=False)

        self.assertEqual(matches[0].custom_emoji_id, both["custom_emoji_id"])
        self.assertGreater(matches[0].score, matches[1].score)

    def test_second_field_only_supplements_never_replaces(self) -> None:
        # The runner-up is a discount on top, so a strong single-field hit still
        # beats a weak pair.
        strong = {
            "custom_emoji_id": "9000000000000000003",
            "alt": "🎯",
            "labels": ["дедлайн"],
            "tags": [],
            "last_seen_at": "2026-08-14T10:00:00+00:00",
        }
        weak_pair = {
            "custom_emoji_id": "9000000000000000004",
            "alt": "📅",
            "labels": [],
            "tags": [],
            "sticker_set_title": "дедлайн",
            "sticker_set_name": "дедлайн",
            "last_seen_at": "2026-08-14T11:00:00+00:00",
        }

        matches = search_emojis([weak_pair, strong], "дедлайн", expand=False)

        self.assertEqual(matches[0].custom_emoji_id, strong["custom_emoji_id"])


class InverseDocumentFrequencyTests(unittest.TestCase):
    def test_rare_tag_outranks_a_common_one(self) -> None:
        # A tag on a quarter of the library barely narrows anything; one on a
        # single emoji nearly identifies it. Equal similarity, unequal value.
        common = [
            {
                "custom_emoji_id": f"800000000000000{index:04d}",
                "alt": "🙂",
                "labels": [],
                "tags": ["общий"],
                "last_seen_at": "2026-08-14T10:00:00+00:00",
            }
            for index in range(60)
        ]
        rare = {
            "custom_emoji_id": "8000000000000009999",
            "alt": "🎯",
            "labels": [],
            "tags": ["редкий"],
            "last_seen_at": "2026-08-14T09:00:00+00:00",
        }

        matches = search_emojis([*common, rare], "общий редкий", expand=False)

        self.assertEqual(matches[0].custom_emoji_id, rare["custom_emoji_id"])

    def test_scores_stay_positive_and_finite(self) -> None:
        matches = search_emojis(TAGGED, "запуск", expand=False)
        for match in matches:
            self.assertGreater(match.score, 0.0)
            self.assertLess(match.score, 100.0)


class CandidateFilterTests(unittest.TestCase):
    """The index narrows what gets scored; it must not narrow what matches."""

    def test_substring_match_survives_filtering(self) -> None:
        record = {
            "custom_emoji_id": "4000000000000000001",
            "alt": "🏷",
            "labels": ["ценник"],
            "tags": ["суперскидка"],
            "last_seen_at": "2026-08-13T10:00:00+00:00",
        }
        # "скидка" is inside "суперскидка" but shares no leading window with it.
        # Kept on a tag, since labels are read strictly and refuse substrings.
        self.assertTrue(search_emojis([record], "скидка"))

    def test_short_field_token_matched_by_longer_query(self) -> None:
        record = {
            "custom_emoji_id": "4000000000000000002",
            "alt": "👌",
            "labels": ["ок"],
            "last_seen_at": "2026-08-13T10:00:00+00:00",
        }
        self.assertTrue(search_emojis([record], "оке"))

    def test_symbol_query_still_reaches_untagged_emoji(self) -> None:
        record = {
            "custom_emoji_id": "4000000000000000003",
            "alt": "🔥",
            "labels": [],
            "tags": [],
            "last_seen_at": "2026-08-13T10:00:00+00:00",
        }
        self.assertTrue(search_emojis([record], "🔥"))

    def test_index_can_be_reused_across_queries(self) -> None:
        index = EmojiIndex(TAGGED)
        first = search_emojis(index, "запуск")
        second = search_emojis(index, "запуск")
        self.assertEqual(
            [(m.custom_emoji_id, m.score) for m in first],
            [(m.custom_emoji_id, m.score) for m in second],
        )


PROMO_CARD = {
    "custom_emoji_id": "9900000000000000001",
    "alt": "©️",
    "labels": ["ссылки на паки"],
    "tags": ["ссылка", "реклама", "паки"],
    "promo": True,
    "last_seen_at": "2026-08-14T23:00:00+00:00",
}
MEGAPHONE = {
    "custom_emoji_id": "9900000000000000002",
    "alt": "📢",
    "labels": ["миньон с мегафоном"],
    "tags": ["объявление", "анонс", "внимание", "реклама"],
    "last_seen_at": "2026-08-14T10:00:00+00:00",
}


class PromoCardTests(unittest.TestCase):
    """Cards advertising their own pack must never be offered for a post."""

    def test_for_posts_drops_them(self) -> None:
        self.assertEqual(for_posts([PROMO_CARD, MEGAPHONE]), [MEGAPHONE])

    def test_an_advertising_tag_alone_is_not_enough(self) -> None:
        # "реклама" also sits on a megaphone, which is what an announcement post
        # wants. Only the hand-set flag excludes.
        self.assertIn(MEGAPHONE, for_posts([MEGAPHONE]))

    def test_topic_candidates_exclude_them(self) -> None:
        matches, is_fallback = suggest_for_topic([PROMO_CARD, MEGAPHONE], "ссылка на оплату")
        self.assertNotIn(PROMO_CARD["custom_emoji_id"], [m.custom_emoji_id for m in matches])
        self.assertTrue(is_fallback or matches)

    def test_recent_fallback_excludes_them_too(self) -> None:
        # The card is the newest record, so an unfiltered fallback would lead with it.
        matches, is_fallback = suggest_for_topic([PROMO_CARD, MEGAPHONE], "квантовая механика")
        self.assertTrue(is_fallback)
        self.assertEqual([m.custom_emoji_id for m in matches], [MEGAPHONE["custom_emoji_id"]])

    def test_direct_search_still_finds_them(self) -> None:
        # /find is an explicit lookup; the owner may still want to send one.
        self.assertTrue(search_emojis([PROMO_CARD], "ссылки на паки"))


class SuggestForTopicTests(unittest.TestCase):
    def test_reports_real_matches(self) -> None:
        matches, is_fallback = suggest_for_topic(ALL, "подарок")
        self.assertFalse(is_fallback)
        self.assertEqual(matches[0].custom_emoji_id, GIFT["custom_emoji_id"])

    def test_falls_back_to_recent_and_flags_it(self) -> None:
        matches, is_fallback = suggest_for_topic(ALL, "квантовая механика")
        self.assertTrue(is_fallback)
        # Newest first, so the caller can present them as "recent", not relevant.
        self.assertEqual(matches[0].custom_emoji_id, BANG["custom_emoji_id"])
        self.assertEqual(matches[0].score, 0.0)

    def test_empty_library_yields_nothing(self) -> None:
        matches, is_fallback = suggest_for_topic([], "подарок")
        self.assertEqual(matches, [])
        self.assertTrue(is_fallback)


class PostRequestCandidateTests(unittest.TestCase):
    def _storage(self, tmp: str) -> LibraryStorage:
        storage = LibraryStorage(Path(tmp))
        storage.ensure()
        storage.upsert_emoji(GIFT["custom_emoji_id"], {"alt": "🎁", "sticker_set_title": "Gifts"})
        storage.upsert_emoji(FIRE["custom_emoji_id"], {"alt": "🔥", "sticker_set_title": "Gifts"})
        return storage

    def test_request_embeds_matching_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._storage(tmp)
            storage.update_emoji_label(GIFT["custom_emoji_id"], "подарок коробка")
            # An inflected topic reaches the emoji through tags, not the label.
            storage.upsert_emoji(GIFT["custom_emoji_id"], {"tags": ["подарок", "розыгрыш"]})

            text = storage.create_post_generation_request("розыгрыш подарков").read_text(encoding="utf-8")

            self.assertIn("## Candidate Emoji For This Topic", text)
            self.assertIn(f'<tg-emoji emoji-id="{GIFT["custom_emoji_id"]}">🎁</tg-emoji>', text)
            self.assertIn("Ranked by match against the topic", text)
            self.assertNotIn("**not** topic matches", text)

    def test_request_flags_fallback_for_unlabeled_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._storage(tmp)

            text = storage.create_post_generation_request("розыгрыш подарков").read_text(encoding="utf-8")

            self.assertIn("## Candidate Emoji For This Topic", text)
            self.assertIn("**not** topic matches", text)
            # Fallback still lists usable tags rather than leaving the agent blind.
            self.assertIn(f'<tg-emoji emoji-id="{FIRE["custom_emoji_id"]}">🔥</tg-emoji>', text)

    def test_request_handles_empty_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()

            text = storage.create_post_generation_request("любая тема").read_text(encoding="utf-8")

            self.assertIn("_No emoji saved in this profile yet._", text)

    def test_find_emojis_goes_through_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._storage(tmp)
            storage.update_emoji_label(FIRE["custom_emoji_id"], "огонь пламя")

            matches = storage.find_emojis("огонь")

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].custom_emoji_id, FIRE["custom_emoji_id"])


if __name__ == "__main__":
    unittest.main()
