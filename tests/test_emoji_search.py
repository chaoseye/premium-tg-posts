from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from premium_tg_posts.services.emoji_search import (
    expand_tokens,
    search_emojis,
    suggest_for_topic,
    token_similarity,
)
from premium_tg_posts.services.storage import LibraryStorage

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

    def test_finds_by_inflected_query(self) -> None:
        matches = search_emojis(ALL, "розыгрыш подарков")
        self.assertTrue(matches)
        self.assertEqual(matches[0].custom_emoji_id, GIFT["custom_emoji_id"])

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
