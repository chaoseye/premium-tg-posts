from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.services.asset_converter import prepare_emoji_asset
from premium_tg_posts.services.telegram_content import sticker_set_names
from premium_tg_posts.utils.text import tg_emoji_html, utf16_slice


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

    def test_owner_and_sent_draft_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()
            changed, owner = storage.register_owner(user_id=1, chat_id=10, username="owner")
            rejected, _ = storage.register_owner(user_id=2, chat_id=20, username="other")
            draft = storage.outbox_dir / "draft.html"
            draft.write_text("<b>Hello</b>", encoding="utf-8")

            self.assertTrue(changed)
            self.assertEqual(owner["chat_id"], 10)
            self.assertFalse(rejected)
            self.assertFalse(storage.is_draft_sent(draft))
            self.assertFalse(storage.is_draft_failed(draft))
            storage.mark_draft_sent(draft, message_id=123)
            self.assertTrue(storage.is_draft_sent(draft))
            storage.mark_draft_failed(draft, error="bad html")
            self.assertTrue(storage.is_draft_failed(draft))

    def test_utf16_slice_handles_non_bmp(self) -> None:
        self.assertEqual(utf16_slice("A🔥B", 1, 2), "🔥")

    def test_tg_emoji_html(self) -> None:
        self.assertEqual(
            tg_emoji_html("5368324170671202286", "🎁"),
            '<tg-emoji emoji-id="5368324170671202286">🎁</tg-emoji>',
        )

    def test_create_emoji_label_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()
            storage.upsert_emoji(
                "5368324170671202286",
                {
                    "alt": "🎁",
                    "asset_path": "emoji-assets/5368324170671202286.webp",
                },
            )

            request_path = storage.create_emoji_label_request("Name them in Russian")
            text = request_path.read_text(encoding="utf-8")

            self.assertIn("Name them in Russian", text)
            self.assertIn("5368324170671202286", text)

    def test_create_post_generation_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()
            post_dir = storage.create_post_dir("reference")
            (post_dir / "index.md").write_text("reference", encoding="utf-8")

            request_path = storage.create_post_generation_request("Пост про новый flow")
            text = request_path.read_text(encoding="utf-8")

            self.assertIn("Пост про новый flow", text)
            self.assertIn("storage/outbox", text)
            self.assertIn("posts/", text)

    def test_clear_runtime_preserves_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()
            storage.register_owner(user_id=1, chat_id=10, username="owner")
            storage.upsert_emoji("5368324170671202286", {"asset_path": "emoji-assets/5368324170671202286.webp"})
            (storage.emoji_assets_dir / "5368324170671202286.webp").write_bytes(b"asset")
            post_dir = storage.create_post_dir("post")
            (post_dir / "index.md").write_text("post", encoding="utf-8")
            (storage.post_generation_requests_dir / "request.md").write_text("topic", encoding="utf-8")
            (storage.outbox_dir / "draft.html").write_text("<b>Hello</b>", encoding="utf-8")

            stats = storage.clear_runtime()

            self.assertEqual(stats.emojis, 0)
            self.assertEqual(stats.posts, 0)
            self.assertEqual(stats.drafts, 0)
            self.assertEqual(storage.load_state()["owner"]["user_id"], 1)
            self.assertFalse(any(path.name != ".gitkeep" for path in storage.emoji_assets_dir.iterdir()))
            self.assertFalse(any(path.name != ".gitkeep" for path in storage.posts_dir.iterdir()))
            self.assertFalse(any(path.name != ".gitkeep" for path in storage.post_generation_requests_dir.iterdir()))

    def test_webp_preview_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "emoji.webp"
            from PIL import Image

            Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(source)
            record = prepare_emoji_asset(source, root / "previews", root)

            self.assertEqual(record["asset_type"], "static_webp")
            self.assertEqual(record["preview_type"], "png_static")
            self.assertTrue((root / record["preview_path"]).exists())

    def test_sticker_set_names_from_links(self) -> None:
        class FakeMessage:
            text = "one https://t.me/addemoji/MarinEmojis1_by_e4zybot\ntg://addstickers?set=Pack_2"
            caption = None
            entities = None
            caption_entities = None

        self.assertEqual(sticker_set_names(FakeMessage()), ["MarinEmojis1_by_e4zybot", "Pack_2"])


if __name__ == "__main__":
    unittest.main()
