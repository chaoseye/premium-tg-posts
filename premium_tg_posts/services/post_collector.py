from __future__ import annotations

from aiogram import Bot
from aiogram.types import Message

from premium_tg_posts.services.emoji_collector import collect_custom_emojis
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.services.telegram_content import (
    message_text_and_entities,
    message_title,
    raw_message,
    serializable_entities,
)


async def save_reference_post(bot: Bot, library: LibraryStorage, message: Message) -> tuple[str, int]:
    await collect_custom_emojis(bot, library, message)

    text, _ = message_text_and_entities(message)
    title = message_title(message, "post")
    post_dir = library.create_post_dir(title)

    library.save_post(
        title=title,
        text=text,
        entities=serializable_entities(message),
        raw_message=raw_message(message),
        media_files=[],
        post_dir=post_dir,
    )
    return post_dir.relative_to(library.root).as_posix(), 0
