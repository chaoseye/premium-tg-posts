from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.types import Message

from premium_tg_posts.handlers.replies import answer_html
from premium_tg_posts.services.emoji_collector import collect_custom_emojis
from premium_tg_posts.services.post_collector import save_reference_post
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.services.telegram_content import has_collectable_material, is_forwarded
from premium_tg_posts.utils.text import short_id

router = Router(name="collector")


@router.message()
async def collect_message(message: Message, bot: Bot, library: LibraryStorage) -> None:
    if message.text and message.text.startswith("/"):
        return

    emoji_rows = await collect_custom_emojis(bot, library, message)

    if is_forwarded(message):
        saved_path, media_count = await save_reference_post(bot, library, message)
        await answer_html(message, f"Сохранил reference post: <code>{saved_path}</code>\nmedia files: {media_count}")
        return

    if emoji_rows:
        await answer_html(
            message,
            "\n".join(
                [
                    f"Сохранил premium emoji: {len(emoji_rows)}",
                    *[
                        f"{escape(row.get('alt', '') or row.get('sticker_emoji', '') or 'emoji')} <code>{short_id(row['custom_emoji_id'])}</code>"
                        for row in emoji_rows[:20]
                    ],
                    "",
                    "Подписать последний: <code>/label last описание</code>",
                    "Подписать конкретный: <code>/label short_id описание</code>",
                ]
            ),
        )
        return

    if has_collectable_material(message):
        await answer_html(
            message,
            "Материал получил, но сам по себе не сохраняю как шаблон. Используй <code>/template</code>, <code>/post</code> или перешли готовый пост.",
        )
