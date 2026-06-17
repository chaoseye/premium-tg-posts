from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.types import Message

from premium_tg_posts.handlers.replies import answer_html, edit_or_answer_html
from premium_tg_posts.services.emoji_collector import collect_custom_emoji_set, collect_custom_emojis
from premium_tg_posts.services.post_collector import save_reference_post
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.services.telegram_content import (
    custom_emoji_entities,
    has_collectable_material,
    is_forwarded,
    message_text_and_entities,
    message_title,
    raw_message,
    serializable_entities,
    split_title_and_body,
    sticker_set_names,
)
from premium_tg_posts.ui.keyboards import after_collect_menu, main_menu
from premium_tg_posts.utils.text import short_id, tg_emoji_html

router = Router(name="collector")


@router.message()
async def collect_message(message: Message, bot: Bot, library: LibraryStorage) -> None:
    if message.text and message.text.startswith("/"):
        return

    if message.from_user:
        mode = library.peek_user_mode(message.from_user.id)
        if mode:
            library.pop_user_mode(message.from_user.id)
            handled = await handle_user_mode(message, bot, library, mode.get("mode", ""), mode.get("data", {}))
            if handled:
                return

    set_names = sticker_set_names(message)
    emoji_entities = custom_emoji_entities(message)
    status_message: Message | None = None
    if emoji_entities or set_names:
        unique_count = len(dict.fromkeys(row["custom_emoji_id"] for row in emoji_entities))
        intro = [f"Принял emoji pack: <code>{escape(name)}</code>" for name in set_names]
        if unique_count:
            intro.append(f"Принял premium emoji: {unique_count}")
        status_message = await answer_html(
            message,
            "\n".join(
                [
                    *intro,
                    "Скачиваю ассеты и делаю PNG/SVG-превью.",
                    "Если emoji много, это может занять немного времени.",
                ]
            ),
        )

    emoji_rows: list[dict] = []
    for set_name in set_names:
        emoji_rows.extend(await collect_custom_emoji_set(bot, library, set_name))
    emoji_rows.extend(await collect_custom_emojis(bot, library, message))
    emoji_rows = dedupe_emoji_rows(emoji_rows)

    if is_forwarded(message):
        saved_path, media_count = await save_reference_post(bot, library, message)
        await edit_or_answer_html(
            message,
            status_message,
            f"Сохранил reference post: <code>{saved_path}</code>\nmedia files: {media_count}",
            reply_markup=main_menu(),
        )
        return

    if emoji_rows:
        await edit_or_answer_html(
            message,
            status_message,
            "\n".join(
                [
                    f"Сохранил premium emoji: {len(emoji_rows)}",
                    *[
                        f"{tg_emoji_html(row['custom_emoji_id'], row.get('alt', '') or row.get('sticker_emoji', '') or '🎁')} <code>{short_id(row['custom_emoji_id'])}</code> - {escape(row.get('asset_type_label') or row.get('asset_type') or 'asset saved')}"
                        for row in emoji_rows[:20]
                    ],
                    "",
                    "Эмодзи импортированы: ID сохранены, ассеты скачаны.",
                    "Теперь добавь стиль/структуру или пример поста, чтобы Codex / Claude понял, как писать.",
                ]
            ),
            reply_markup=after_collect_menu(),
        )
        return

    if has_collectable_material(message):
        if set_names:
            await edit_or_answer_html(
                message,
                status_message,
                "Не смог скачать custom emoji из набора:\n"
                + "\n".join(f"- <code>{escape(name)}</code>" for name in set_names)
                + "\n\nПроверь, что ссылка ведет на emoji pack и набор доступен боту.",
                reply_markup=main_menu(),
            )
            return
        await edit_or_answer_html(
            message,
            status_message,
            "Я получил материал, но не понял, куда его сохранить.\n\n"
            "Нажми <b>Добавить стиль / структуру</b> или <b>Добавить пример поста</b>, а потом отправь материал еще раз.",
            reply_markup=main_menu(),
        )


async def handle_user_mode(
    message: Message,
    bot: Bot,
    library: LibraryStorage,
    mode: str,
    mode_data: dict | None = None,
) -> bool:
    if mode == "label_last":
        label, _ = message_text_and_entities(message)
        label = label.strip()
        if not label:
            await message.answer("Не вижу текста названия. Нажми кнопку еще раз и отправь короткое описание текстом.", reply_markup=main_menu())
            return True
        selector = str((mode_data or {}).get("emoji_id") or "last")
        record = library.update_emoji_label(selector, label)
        if not record:
            await message.answer("Пока нечего называть: сначала отправь premium emoji.", reply_markup=main_menu())
            return True
        emoji_id = record.get("custom_emoji_id", "")
        alt = record.get("alt", "") or record.get("sticker_emoji", "") or "🎁"
        await message.answer(
            f"Добавил название: {tg_emoji_html(emoji_id, alt)} <code>{short_id(emoji_id)}</code> - {escape(label)}",
            reply_markup=main_menu(),
        )
        return True

    if mode == "emoji_label_prompt":
        prompt, _ = message_text_and_entities(message)
        prompt = prompt.strip()
        if not prompt:
            await message.answer("Не вижу текста промпта. Нажми кнопку еще раз и отправь промпт текстом.", reply_markup=main_menu())
            return True
        path = library.create_emoji_label_request(prompt)
        await message.answer(
            "Сохранил задачу для AI-подписи emoji:\n"
            f"<code>{path.relative_to(library.root).as_posix()}</code>\n\n"
            "Теперь в Codex / Claude можно написать: «прочитай последний emoji-label-request и подпиши emoji по ассетам».",
            reply_markup=main_menu(),
        )
        return True

    if mode == "template":
        text, _ = message_text_and_entities(message)
        text = text.strip()
        if not text:
            await message.answer("Стиль/структура должны быть текстом. Нажми кнопку еще раз и отправь правила текстом.", reply_markup=main_menu())
            return True
        title, body = split_title_and_body(text)
        if not body:
            title = message_title(message, "template")
            body = text
        path = library.save_template(title, body, serializable_entities(message), raw_message(message))
        await message.answer(
            f"Сохранил стиль/структуру: <code>{path.relative_to(library.root).as_posix()}</code>\n\n"
            "Теперь можно добавить пример поста или попросить Codex / Claude собрать готовый текст.",
            reply_markup=main_menu(),
        )
        return True

    if mode == "post":
        saved_path, media_count = await save_reference_post(bot, library, message)
        await message.answer(
            f"Сохранил пример поста: <code>{saved_path}</code>\nmedia files: {media_count}\n\n"
            "Теперь Codex / Claude сможет ориентироваться на этот стиль.",
            reply_markup=main_menu(),
        )
        return True

    return False


def dedupe_emoji_rows(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        emoji_id = row.get("custom_emoji_id", "")
        if emoji_id in seen:
            continue
        seen.add(emoji_id)
        result.append(row)
    return result
