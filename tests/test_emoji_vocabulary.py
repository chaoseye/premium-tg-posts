from __future__ import annotations

import ast
import unittest
from collections import Counter
from pathlib import Path

from premium_tg_posts.data import emoji_vocabulary as vocab

SOURCE = Path(vocab.__file__)


class VocabularyShapeTests(unittest.TestCase):
    def test_every_entry_has_a_label_and_tags(self) -> None:
        for symbol, (label, tags) in vocab.VOCABULARY.items():
            self.assertTrue(label.strip(), f"{symbol} has an empty label")
            self.assertTrue(tags, f"{symbol} has no tags")
            self.assertTrue(all(tag.strip() for tag in tags), f"{symbol} has a blank tag")

    def test_no_duplicate_keys_in_source(self) -> None:
        # A repeated literal key silently overwrites the earlier entry, so the
        # dict at runtime cannot reveal the loss - check the source instead.
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        literals: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict) and len(node.keys) > 50:
                literals = [key.value for key in node.keys if isinstance(key, ast.Constant)]
                break
        duplicates = [key for key, count in Counter(literals).items() if count > 1]
        self.assertEqual(duplicates, [], f"duplicate keys: {duplicates}")

    def test_tags_are_lowercase_single_words_mostly(self) -> None:
        for symbol, (_, tags) in vocab.VOCABULARY.items():
            for tag in tags:
                self.assertEqual(tag, tag.lower(), f"{symbol}: tag {tag!r} is not lowercase")


class LookupTests(unittest.TestCase):
    def test_plain_symbol(self) -> None:
        entry = vocab.lookup("🔥")
        self.assertIsNotNone(entry)
        self.assertIn("огонь", entry[1])

    def test_variation_selector_is_ignored(self) -> None:
        self.assertEqual(vocab.lookup("❤️"), vocab.lookup("❤"))
        self.assertEqual(vocab.lookup("⭐️"), vocab.lookup("⭐"))

    def test_skin_tone_is_ignored(self) -> None:
        self.assertEqual(vocab.lookup("👍🏽"), vocab.lookup("👍"))

    def test_zwj_sequence_falls_back_to_its_base(self) -> None:
        # No entry for this exact family, but the leading component resolves.
        entry = vocab.lookup("👩‍👩‍👦‍👦")
        self.assertIsNotNone(entry)

    def test_gendered_variant_resolves(self) -> None:
        self.assertIsNotNone(vocab.lookup("🤷‍♂️"))
        self.assertIsNotNone(vocab.lookup("🤷‍♀️"))

    def test_unknown_symbol_returns_none(self) -> None:
        self.assertIsNone(vocab.lookup("\U0001FAF9"))

    def test_blank_input_returns_none(self) -> None:
        self.assertIsNone(vocab.lookup(""))
        self.assertIsNone(vocab.lookup(None))


class NormalizeTests(unittest.TestCase):
    def test_strips_variation_selector(self) -> None:
        self.assertEqual(vocab.normalize("❤️"), "❤")

    def test_strips_skin_tone(self) -> None:
        self.assertEqual(vocab.normalize("👍🏿"), "👍")

    def test_keeps_plain_symbol(self) -> None:
        self.assertEqual(vocab.normalize("🔥"), "🔥")


if __name__ == "__main__":
    unittest.main()
