from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from premium_tg_posts.handlers.replies import answer_html
from premium_tg_posts.handlers.callbacks import render_drafts, render_emojis, render_owner
from premium_tg_posts.services.drafts import DraftSendError, send_html_draft
from premium_tg_posts.services.post_collector import save_reference_post
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.services.telegram_content import (
    message_text_and_entities,
    message_title,
    raw_message,
    serializable_entities,
    split_title_and_body,
)
from premium_tg_posts.utils.text import html_code, relative_to, short_id, tg_emoji_html
from premium_tg_posts.ui.keyboards import back_menu, drafts_menu, main_menu

router = Router(name="commands")

HELP_TEXT = """<b>Сборщик материалов для Codex / Claude</b>
Автор: @fiscaldev

Рабочий порядок:
1. Отправь premium emoji пачкой.
2. Нажми <b>Добавить стиль / структуру</b> и отправь правила будущих постов.
3. Нажми <b>Добавить пример поста</b> или перешли пример.
4. Попроси Codex или Claude собрать пост.
5. Когда AI-агент сохранит HTML в <code>storage/outbox</code>, бот отправит его сам.

Подписывать emoji не обязательно: ассеты уже скачиваются, AI-агент сможет их посмотреть."""


@router.message(CommandStart())
@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu(), disable_web_page_preview=True)


@router.message(Command("stats"))
async def stats_command(message: Message, library: LibraryStorage) -> None:
    stats = library.stats()
    await message.answer(
        "\n".join(
            [
                "<b>Storage</b>",
                f"premium emojis: {stats.emojis}",
                f"templates: {stats.templates}",
                f"reference posts: {stats.posts}",
                f"outbox drafts: {stats.drafts}",
                "",
                html_code(str(library.root)),
            ]
        ),
        reply_markup=back_menu(),
        disable_web_page_preview=True,
    )


@router.message(Command("emojis"))
async def emojis_command(message: Message, library: LibraryStorage) -> None:
    data = library.load_emojis()
    rows = sorted(data.get("emojis", {}).values(), key=lambda item: item.get("last_seen_at", ""), reverse=True)
    if not rows:
        await message.answer("Пока нет сохраненных premium emoji. Пришли их пачкой обычным сообщением.", reply_markup=main_menu())
        return

    await message.answer(render_emojis(library), reply_markup=back_menu(), disable_web_page_preview=True)


@router.message(Command("label"))
async def label_command(message: Message, command: CommandObject, library: LibraryStorage) -> None:
    payload = (command.args or "").strip()
    selector, _, label = payload.partition(" ")
    selector = selector.strip()
    label = label.strip()
    if not selector or not label:
        await answer_html(
            message,
            "Формат: <code>/label short_id описание</code>\nМожно использовать <code>last</code> для последнего эмодзи.",
        )
        return

    record = library.update_emoji_label(selector, label)
    if not record:
        await answer_html(message, f"Не нашел эмодзи по селектору <code>{escape(selector)}</code>. Проверь /emojis.")
        return

    emoji_id = record.get("custom_emoji_id", "")
    alt = record.get("alt", "") or record.get("sticker_emoji", "") or "🎁"
    await message.answer(
        f"Подписал {tg_emoji_html(emoji_id, alt)} <code>{short_id(emoji_id)}</code>: {escape(label)}",
        reply_markup=main_menu(),
    )


@router.message(Command("template"))
async def template_command(message: Message, command: CommandObject, library: LibraryStorage) -> None:
    payload = (command.args or "").strip()
    reply = message.reply_to_message

    if reply:
        title = payload or message_title(reply, "template")
        text, _ = message_text_and_entities(reply)
        entities = serializable_entities(reply)
        raw = raw_message(reply)
    else:
        title, body = split_title_and_body(payload)
        if not title or not body:
            await answer_html(
                message,
                "Формат:\n<code>/template Название\nтекст шаблона</code>\n\nИли ответь /template на сообщение с шаблоном.",
            )
            return
        text = body
        entities = serializable_entities(message)
        raw = raw_message(message)

    path = library.save_template(title, text, entities, raw)
    await message.answer(f"Сохранил шаблон: <code>{relative_to(path, library.root)}</code>", reply_markup=main_menu())


@router.message(Command("post"))
async def post_command(message: Message, bot: Bot, library: LibraryStorage) -> None:
    if not message.reply_to_message:
        await answer_html(message, "Ответь командой <code>/post</code> на сообщение, которое нужно сохранить как reference post.")
        return
    saved_path, media_count = await save_reference_post(bot, library, message.reply_to_message)
    await message.answer(f"Сохранил reference post: <code>{saved_path}</code>\nmedia files: {media_count}", reply_markup=main_menu())


@router.message(Command("drafts"))
async def drafts_command(message: Message, library: LibraryStorage) -> None:
    drafts = library.list_drafts()
    if not drafts:
        await message.answer("В <code>storage/outbox</code> пока нет HTML-постов от Codex / Claude.", reply_markup=main_menu())
        return
    await message.answer(render_drafts(library), reply_markup=drafts_menu(True), disable_web_page_preview=True)


@router.message(Command("send_draft"))
async def send_draft_command(message: Message, command: CommandObject, bot: Bot, library: LibraryStorage) -> None:
    selector = (command.args or "latest").strip() or "latest"
    draft = library.resolve_draft(selector)
    if not draft:
        await answer_html(message, "Не нашел draft. Проверь <code>/drafts</code>.")
        return

    html = draft.read_text(encoding="utf-8").strip()
    if not html:
        await answer_html(message, f"Draft пустой: <code>{escape(draft.name)}</code>")
        return
    if len(html) > 4096:
        await answer_html(message, "Этот draft длиннее лимита Telegram для sendMessage (4096 символов). Разбей его на части.")
        return

    try:
        sent = await send_html_draft(bot=bot, chat_id=message.chat.id, draft=draft)
        library.mark_draft_sent(draft, sent.message_id)
    except (DraftSendError, TelegramBadRequest) as exc:
        await answer_html(
            message,
            "Telegram не принял draft.\n"
            f"Файл: <code>{escape(draft.name)}</code>\n"
            f"Ошибка: <code>{escape(str(exc))}</code>",
        )


@router.message(Command("owner"))
async def owner_command(message: Message, library: LibraryStorage) -> None:
    await message.answer(render_owner(library), reply_markup=back_menu(), disable_web_page_preview=True)
