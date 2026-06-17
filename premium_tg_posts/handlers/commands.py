from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from premium_tg_posts.handlers.replies import answer_html
from premium_tg_posts.services.post_collector import save_reference_post
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.services.telegram_content import (
    message_text_and_entities,
    message_title,
    raw_message,
    serializable_entities,
    split_title_and_body,
)
from premium_tg_posts.utils.text import html_code, relative_to, short_id

router = Router(name="commands")

HELP_TEXT = """Я локальный Telegram-интерфейс для Codex.

Что можно делать:
/stats - показать сколько материалов сохранено
/template Название
текст шаблона - сохранить текстовый шаблон
/label short_id описание - подписать эмодзи
/emojis - показать последние эмодзи
/drafts - показать готовые посты из storage/outbox
/send_draft latest - отправить готовый HTML-пост

Просто отправь пачку premium/custom emoji - я сохраню их ID, скачаю файлы и обновлю storage/premium-emojis.md.
Перешли любой пост - я сохраню его текст, entities, raw JSON и медиа в storage/posts.
"""


@router.message(CommandStart())
@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await answer_html(message, HELP_TEXT)


@router.message(Command("stats"))
async def stats_command(message: Message, library: LibraryStorage) -> None:
    stats = library.stats()
    await answer_html(
        message,
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
    )


@router.message(Command("emojis"))
async def emojis_command(message: Message, library: LibraryStorage) -> None:
    data = library.load_emojis()
    rows = sorted(data.get("emojis", {}).values(), key=lambda item: item.get("last_seen_at", ""), reverse=True)
    if not rows:
        await answer_html(message, "Пока нет сохраненных premium emoji. Пришли их пачкой обычным сообщением.")
        return

    lines = ["<b>Последние premium emoji</b>"]
    for item in rows[:20]:
        emoji_id = item.get("custom_emoji_id", "")
        alt = item.get("alt", "") or item.get("sticker_emoji", "") or "emoji"
        labels = ", ".join(item.get("labels", [])) or "unlabeled"
        lines.append(f"{escape(alt)} <code>{short_id(emoji_id)}</code> - {escape(labels)}")
    lines.append("")
    lines.append("Подписать: <code>/label short_id описание</code>")
    await answer_html(message, "\n".join(lines))


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
    await answer_html(message, f"Подписал <code>{short_id(emoji_id)}</code>: {escape(label)}")


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
    await answer_html(message, f"Сохранил шаблон: <code>{relative_to(path, library.root)}</code>")


@router.message(Command("post"))
async def post_command(message: Message, bot: Bot, library: LibraryStorage) -> None:
    if not message.reply_to_message:
        await answer_html(message, "Ответь командой <code>/post</code> на сообщение, которое нужно сохранить как reference post.")
        return
    saved_path, media_count = await save_reference_post(bot, library, message.reply_to_message)
    await answer_html(message, f"Сохранил reference post: <code>{saved_path}</code>\nmedia files: {media_count}")


@router.message(Command("drafts"))
async def drafts_command(message: Message, library: LibraryStorage) -> None:
    drafts = library.list_drafts()
    if not drafts:
        await answer_html(message, "В <code>storage/outbox</code> пока нет HTML-постов от Codex.")
        return
    lines = ["<b>Outbox drafts</b>"]
    for draft in drafts[:20]:
        lines.append(f"- <code>{escape(draft.name)}</code>")
    lines.append("")
    lines.append("Отправить: <code>/send_draft latest</code> или <code>/send_draft file.html</code>")
    await answer_html(message, "\n".join(lines))


@router.message(Command("send_draft"))
async def send_draft_command(message: Message, command: CommandObject, library: LibraryStorage) -> None:
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
        await message.answer(html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        await answer_html(
            message,
            "Telegram не принял draft.\n"
            f"Файл: <code>{escape(draft.name)}</code>\n"
            f"Ошибка: <code>{escape(str(exc))}</code>",
        )
