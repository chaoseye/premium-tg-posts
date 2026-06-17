from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.utils.text import utf16_slice


class StorageTests(unittest.TestCase):
    def test_upsert_label_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()

            storage.upsert_emoji(
                "5368324170671202286",
                {
                    "alt": "🔥",
                    "asset_path": "emoji-assets/5368324170671202286.webp",
                },
            )
            record = storage.update_emoji_label("last", "fire accent")

            self.assertIsNotNone(record)
            markdown = storage.premium_emojis_md.read_text(encoding="utf-8")
            self.assertIn("fire accent", markdown)
            self.assertIn('<tg-emoji emoji-id="5368324170671202286">🔥</tg-emoji>', markdown)

    def test_resolve_latest_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()
            draft = storage.outbox_dir / "draft.html"
            draft.write_text("<b>Hello</b>", encoding="utf-8")

            self.assertEqual(storage.resolve_draft("latest"), draft)
            self.assertEqual(storage.resolve_draft("draft.html"), draft)

    def test_utf16_slice_handles_non_bmp(self) -> None:
        self.assertEqual(utf16_slice("A🔥B", 1, 2), "🔥")


if __name__ == "__main__":
    unittest.main()
