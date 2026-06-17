from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.types import Message, Sticker

from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.services.telegram_content import custom_emoji_entities
from premium_tg_posts.utils.text import relative_to

LOGGER = logging.getLogger(__name__)


async def collect_custom_emojis(bot: Bot, library: LibraryStorage, message: Message) -> list[dict[str, Any]]:
    rows = custom_emoji_entities(message)
    if not rows:
        return []

    ids = list(dict.fromkeys(row["custom_emoji_id"] for row in rows))
    stickers_by_id: dict[str, Sticker] = {}
    try:
        stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=ids)
        stickers_by_id = {str(sticker.custom_emoji_id): sticker for sticker in stickers if sticker.custom_emoji_id}
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Could not fetch custom emoji stickers: %s", exc)

    saved: list[dict[str, Any]] = []
    for row in rows:
        emoji_id = row["custom_emoji_id"]
        sticker = stickers_by_id.get(emoji_id)
        record = {
            "alt": row.get("alt") or (sticker.emoji if sticker else None),
            "sticker_emoji": sticker.emoji if sticker else None,
            "sticker_set_name": sticker.set_name if sticker else None,
            "file_id": sticker.file_id if sticker else None,
            "file_unique_id": sticker.file_unique_id if sticker else None,
            "is_animated": sticker.is_animated if sticker else None,
            "is_video": sticker.is_video if sticker else None,
        }
        if sticker:
            asset_path = await download_emoji_asset(bot, library, emoji_id, sticker)
            if asset_path:
                record["asset_path"] = relative_to(asset_path, library.root)
        saved.append(library.upsert_emoji(emoji_id, record))
    return saved


async def download_emoji_asset(bot: Bot, library: LibraryStorage, emoji_id: str, sticker: Sticker) -> Path | None:
    try:
        tg_file = await bot.get_file(sticker.file_id)
        if not tg_file.file_path:
            raise RuntimeError("Telegram did not return file_path")
        suffix = Path(tg_file.file_path).suffix
        if not suffix:
            suffix = ".webm" if sticker.is_video else ".tgs" if sticker.is_animated else ".webp"
        destination = library.emoji_asset_path(emoji_id, suffix)
        if destination.exists() and destination.stat().st_size > 0:
            return destination
        await bot.download_file(tg_file.file_path, destination=destination)
        return destination
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Could not download custom emoji %s: %s", emoji_id, exc)
        return None
