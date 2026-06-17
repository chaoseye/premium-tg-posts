from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from premium_tg_posts.handlers.replies import answer_html
from premium_tg_posts.services.drafts import DraftSendError, send_html_draft
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.ui.keyboards import back_menu, clear_storage_confirm_menu, drafts_menu, emoji_label_menu, main_menu
from premium_tg_posts.utils.text import short_id, tg_emoji_html

router = Router(name="callbacks")


@router.callback_query()
async def handle_callback(callback: CallbackQuery, bot: Bot, library: LibraryStorage) -> None:
    data = callback.data or ""
    message = callback.message
    await callback.answer()

    if not isinstance(message, Message):
        return

    if data == "menu:home":
        await edit_or_answer(
            message,
            "Что делаем дальше?\n\n"
            "Если эмодзи уже импортированы, добавь стиль/структуру и пару примеров. После этого Codex или Claude сможет собрать готовый Telegram HTML-пост.",
            reply_markup=main_menu(),
        )
        return

    if data == "menu:help":
        await edit_or_answer(
            message,
            "<b>Как пользоваться</b>\n\n"
            "1. Просто отправь premium emoji пачкой. Бот сохранит ID и скачает ассеты.\n"
            "2. Нажми <b>Добавить стиль / структуру</b> и отправь правила: как писать, какие блоки, какой тон, какой CTA.\n"
            "3. Нажми <b>Добавить пример поста</b> или просто перешли пост, который нравится.\n"
            "4. Попроси Codex или Claude сделать пост. Когда AI-агент сохранит HTML в <code>storage/outbox</code>, бот отправит его тебе сам.\n\n"
            "Названия emoji необязательны: AI-агент может смотреть скачанные ассеты.",
            reply_markup=main_menu(),
        )
        return

    if data == "menu:stats":
        stats = library.stats()
        await edit_or_answer(
            message,
            "\n".join(
                [
                    "<b>Что уже сохранено</b>",
                    f"premium emoji: {stats.emojis}",
                    f"шаблоны постов: {stats.templates}",
                    f"примеры постов: {stats.posts}",
                    f"готовые HTML-посты: {stats.drafts}",
                ]
            ),
            reply_markup=back_menu(),
        )
        return

    if data == "menu:emojis":
        await edit_or_answer(message, render_emojis(library), reply_markup=back_menu())
        return

    if data == "menu:drafts":
        drafts = library.list_drafts()
        await edit_or_answer(message, render_drafts(library), reply_markup=drafts_menu(bool(drafts)))
        return

    if data == "menu:owner":
        await edit_or_answer(message, render_owner(library), reply_markup=back_menu())
        return

    if data == "storage:clear_prompt":
        if not is_owner_callback(callback, library):
            await edit_or_answer(message, "Очистка доступна только owner.", reply_markup=main_menu())
            return
        await edit_or_answer(
            message,
            "<b>Очистить хранилище?</b>\n\n"
            "Будут удалены emoji, ассеты, превью, AI-label requests, шаблоны, reference posts, raw-файлы и outbox drafts.\n"
            "Owner сохранится, чтобы бот не потерял получателя.",
            reply_markup=clear_storage_confirm_menu(),
        )
        return

    if data == "storage:clear_cancel":
        await edit_or_answer(message, "Ок, ничего не удаляю.", reply_markup=main_menu())
        return

    if data == "storage:clear_confirm":
        if not is_owner_callback(callback, library):
            await edit_or_answer(message, "Очистка доступна только owner.", reply_markup=main_menu())
            return
        stats = library.clear_runtime(preserve_owner=True)
        await edit_or_answer(
            message,
            "\n".join(
                [
                    "<b>Хранилище очищено</b>",
                    f"premium emoji: {stats.emojis}",
                    f"шаблоны постов: {stats.templates}",
                    f"примеры постов: {stats.posts}",
                    f"готовые HTML-посты: {stats.drafts}",
                ]
            ),
            reply_markup=main_menu(),
        )
        return

    if data == "mode:label_last":
        await show_emoji_label_picker(message, library, callback.from_user.id, 0)
        return

    if data.startswith("emoji_label:"):
        if data == "emoji_label:noop":
            return
        try:
            index = int(data.rsplit(":", 1)[1])
        except ValueError:
            index = 0
        await show_emoji_label_picker(message, library, callback.from_user.id, index)
        return

    if data == "mode:emoji_label_prompt":
        if not library.latest_emoji():
            await edit_or_answer(message, "Пока нечего подписывать. Сначала отправь premium emoji пачкой.", reply_markup=back_menu())
            return
        if callback.from_user:
            library.set_user_mode(callback.from_user.id, "emoji_label_prompt")
        await edit_or_answer(
            message,
            "<b>AI-подпись emoji по ассетам</b>\n\n"
            "Следующим сообщением отправь промпт для Codex / Claude: как назвать emoji, на каком языке, насколько коротко, какие теги нужны.\n\n"
            "Пример: <code>Назови все emoji коротко по-русски: 2-4 слова, по визуалу, без воды. Для одинаковых подарков различай цвет/эффект.</code>",
            reply_markup=back_menu(),
        )
        return

    if data == "mode:template":
        if callback.from_user:
            library.set_user_mode(callback.from_user.id, "template")
        await edit_or_answer(
            message,
            "<b>Следующее сообщение сохраню как стиль / структуру.</b>\n\n"
            "Сюда можно отправить любые правила для будущих постов: тон, формат, порядок блоков, CTA, что писать/не писать.\n\n"
            "Пример: «короткий премиум-стиль, 1 мощный заголовок, 2 строки пользы, CTA в конце, использовать 2-3 premium emoji».",
            reply_markup=back_menu(),
        )
        return

    if data == "mode:post":
        if callback.from_user:
            library.set_user_mode(callback.from_user.id, "post")
        await edit_or_answer(
            message,
            "<b>Следующее сообщение сохраню как пример поста.</b>\n\n"
            "Можешь переслать готовый пост или отправить свой пример. Бот сохранит текст, форматирование, premium emoji entities и медиа.",
            reply_markup=back_menu(),
        )
        return

    if data == "draft:send_latest":
        await send_latest_draft_from_button(bot, message, library)
        return


async def send_latest_draft_from_button(bot: Bot, message: Message, library: LibraryStorage) -> None:
    draft = library.resolve_draft("latest")
    if not draft:
        await answer_html(message, "Не нашел draft. Пусть Codex или Claude сохранит HTML-файл в <code>storage/outbox</code>.")
        return
    try:
        sent = await send_html_draft(bot, message.chat.id, draft)
        library.mark_draft_sent(draft, sent.message_id)
    except (DraftSendError, TelegramBadRequest) as exc:
        await answer_html(message, f"Telegram не принял draft:\n<code>{escape(str(exc))}</code>")


async def edit_or_answer(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup, disable_web_page_preview=True)


def is_owner_callback(callback: CallbackQuery, library: LibraryStorage) -> bool:
    owner = library.load_state().get("owner", {})
    owner_id = owner.get("user_id")
    return not owner_id or int(owner_id) == int(callback.from_user.id)


async def show_emoji_label_picker(message: Message, library: LibraryStorage, user_id: int, index: int) -> None:
    rows = library.emoji_records(sort_by="last_seen_at", reverse=True)
    if not rows:
        await edit_or_answer(message, "Пока нет emoji для названия. Сначала отправь premium emoji пачкой.", reply_markup=back_menu())
        return

    index %= len(rows)
    item = rows[index]
    emoji_id = item.get("custom_emoji_id", "")
    alt = item.get("alt", "") or item.get("sticker_emoji", "") or "🎁"
    labels = ", ".join(item.get("labels", [])) or "пока без названия"
    library.set_user_mode(user_id, "label_last", {"emoji_id": emoji_id, "index": index})

    await edit_or_answer(
        message,
        "Отправь короткое название вот для этого emoji:\n\n"
        f"{tg_emoji_html(emoji_id, alt)} <code>{short_id(emoji_id)}</code>\n"
        f"Сейчас: {escape(labels)}\n\n"
        "Стрелками можно выбрать другой emoji. Когда нужный выбран, просто отправь название текстом.",
        reply_markup=emoji_label_menu(index, len(rows)),
    )


def render_emojis(library: LibraryStorage) -> str:
    data = library.load_emojis()
    rows = sorted(data.get("emojis", {}).values(), key=lambda item: item.get("last_seen_at", ""), reverse=True)
    if not rows:
        return "База emoji пустая. Просто отправь premium emoji пачкой в этот чат, я сохраню ID и скачаю ассеты."

    lines = ["<b>База premium emoji</b>", "Показываю последние 15. Полный список лежит в <code>storage/premium-emojis.md</code>.", ""]
    for item in rows[:15]:
        emoji_id = item.get("custom_emoji_id", "")
        alt = item.get("alt", "") or item.get("sticker_emoji", "") or "emoji"
        labels = ", ".join(item.get("labels", [])) or "unlabeled"
        asset_type = item.get("asset_type_label", "") or item.get("asset_type", "asset")
        lines.append(f"{tg_emoji_html(emoji_id, alt)} <code>{short_id(emoji_id)}</code> - {escape(asset_type)} - {escape(labels)}")
    return "\n".join(lines)


def render_drafts(library: LibraryStorage) -> str:
    drafts = library.list_drafts()
    if not drafts:
        return "Готовых постов пока нет. Когда Codex или Claude сохранит HTML-файл в <code>storage/outbox</code>, бот отправит его owner'у сам."
    lines = ["<b>Готовые HTML-посты</b>", "Файлы из <code>storage/outbox</code>:", ""]
    for draft in drafts[:15]:
        marker = "отправлен" if library.is_draft_sent(draft) else "ошибка" if library.is_draft_failed(draft) else "новый"
        lines.append(f"- <code>{escape(draft.name)}</code> ({marker})")
    return "\n".join(lines)


def render_owner(library: LibraryStorage) -> str:
    owner = library.load_state().get("owner", {})
    if not owner.get("user_id"):
        return "Owner еще не определен. Первый пользователь, который напишет боту в личку, станет получателем готовых постов."
    username = f"@{owner['username']}" if owner.get("username") else "no username"
    return "\n".join(
        [
            "<b>Owner</b>",
            f"user_id: <code>{owner.get('user_id')}</code>",
            f"chat_id: <code>{owner.get('chat_id')}</code>",
            f"user: {escape(username)}",
            f"name: {escape(owner.get('full_name') or '')}",
        ]
    )
