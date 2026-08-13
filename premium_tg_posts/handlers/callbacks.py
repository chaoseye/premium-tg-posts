from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from premium_tg_posts.handlers.replies import answer_html
from premium_tg_posts.services.drafts import DraftSendError, send_html_draft
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.ui.keyboards import (
    back_menu,
    clear_storage_confirm_menu,
    drafts_menu,
    emoji_label_menu,
    main_menu,
    profiles_menu,
)
from premium_tg_posts.utils.text import short_id, tg_emoji_html

router = Router(name="callbacks")

# Each result costs two lines plus a ready-to-paste tag; keep the message well
# under Telegram's 4096-character limit.
SEARCH_RESULT_LIMIT = 10


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
            "Если emoji уже импортированы, нафорварди примеры постов. Потом можно подписать emoji и поставить Codex / Claude задачу на пост по теме.",
            reply_markup=main_menu(),
        )
        return

    if data == "menu:help":
        await edit_or_answer(
            message,
            "<b>Как пользоваться</b>\n\n"
            "Если пост уже написан:\n"
            "1. Отправь premium emoji пачкой или до 5 ссылок на emoji-pack.\n"
            "2. Нажми <b>AI: назвать emoji по ассетам</b> — агент проставит подписи и смысловые теги.\n"
            "3. Нажми <b>Добавить emoji в мой пост</b> и пришли свой текст. Верну с emoji, форматирование сохранится.\n\n"
            "Если пост нужен с нуля:\n"
            "4. Перешли посты-референсы — сохраню текст, entities и raw JSON, без медиа.\n"
            "5. Нажми <b>Сгенерировать пост на тему</b>. Когда агент сохранит HTML в outbox, бот отправит его сам.\n\n"
            "Если нужно разделять разные тематики, открой <b>Профили</b>, создай профиль с любым названием и загружай emoji/посты уже внутрь него.\n\n"
            "Кнопка <b>Найти emoji по смыслу</b> ищет по подписям и тегам и выдает готовые "
            "<code>&lt;tg-emoji&gt;</code> теги. Подходящие emoji попадают и в задание на пост, "
            "чтобы агент не выбирал вслепую.\n\n"
            "Стиль / структуру можно добавить отдельной кнопкой ниже, если нужны особые правила.",
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
                    f"профиль: <b>{escape(library.active_profile_name())}</b>",
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

    if data == "profiles:menu":
        profiles = library.list_profiles()
        await edit_or_answer(
            message,
            render_profiles(library),
            reply_markup=profiles_menu(profiles, library.active_profile_slug()),
        )
        return

    if data == "profile:create":
        if callback.from_user:
            library.set_user_mode(callback.from_user.id, "profile_create")
        await edit_or_answer(
            message,
            "<b>Создать профиль</b>\n\n"
            "Отправь следующим сообщением название профиля. Например: <code>GiftStar</code>, <code>NFT drops</code>, <code>личный канал</code>.\n\n"
            "После создания профиль сразу станет активным: все новые emoji, форварды, темы и outbox будут сохраняться внутри него.",
            reply_markup=back_menu(),
        )
        return

    if data.startswith("profile:switch:"):
        slug = data.split(":", 2)[2]
        profile = library.set_active_profile(slug)
        if not profile:
            await edit_or_answer(message, "Не нашел такой профиль. Открой список профилей еще раз.", reply_markup=back_menu())
            return
        profiles = library.list_profiles()
        await edit_or_answer(
            message,
            f"<b>Активный профиль:</b> {escape(profile.get('name') or slug)}\n\n" + render_profiles(library),
            reply_markup=profiles_menu(profiles, library.active_profile_slug()),
        )
        return

    if data == "storage:clear_prompt":
        if not is_owner_callback(callback, library):
            await edit_or_answer(message, "Очистка доступна только owner.", reply_markup=main_menu())
            return
        await edit_or_answer(
            message,
            f"<b>Очистить активный профиль «{escape(library.active_profile_name())}»?</b>\n\n"
            "Будут удалены emoji, ассеты, превью, AI-label requests, post requests, шаблоны, reference posts, raw-файлы и outbox drafts только в активном профиле.\n"
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
                    f"профиль: <b>{escape(library.active_profile_name())}</b>",
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

    if data == "mode:decorate_post":
        if not library.latest_emoji():
            await edit_or_answer(
                message,
                "База emoji пустая, расставлять нечего. Сначала отправь premium emoji пачкой "
                "или ссылку на emoji pack.",
                reply_markup=back_menu(),
            )
            return
        if callback.from_user:
            library.set_user_mode(callback.from_user.id, "decorate_post")
        await edit_or_answer(
            message,
            "<b>Добавить emoji в готовый пост</b>\n\n"
            "Отправь следующим сообщением свой пост целиком, как есть. "
            "Я подберу emoji под смысл каждой строки, вставлю их и пришлю готовый текст.\n\n"
            "Жирный шрифт, ссылки и остальное форматирование сохранятся. "
            "Строки, где ты уже поставил emoji, не трону.",
            reply_markup=back_menu(),
        )
        return

    if data == "mode:emoji_find":
        if not library.latest_emoji():
            await edit_or_answer(
                message,
                "База emoji пустая, искать пока не в чем. Сначала отправь premium emoji пачкой.",
                reply_markup=back_menu(),
            )
            return
        if callback.from_user:
            library.set_user_mode(callback.from_user.id, "emoji_find")
        await edit_or_answer(
            message,
            "<b>Поиск emoji по смыслу</b>\n\n"
            "Отправь следующим сообщением слово или несколько слов — найду подходящие emoji "
            "и дам готовые теги для вставки в пост.\n\n"
            "Например: <code>подарок</code>, <code>огонь скидка</code>. "
            "Можно искать и самим символом: <code>🔥</code>.\n\n"
            "Поиск идет по подписям, тегам и названию пака.",
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

    if data == "mode:post_topic":
        if callback.from_user:
            library.set_user_mode(callback.from_user.id, "post_topic")
        await edit_or_answer(
            message,
            "<b>Следующее сообщение сохраню как тему для поста.</b>\n\n"
            "Напиши обычным текстом, о чем нужен пост: что сделали, для кого, какой акцент, какой CTA. "
            "Codex / Claude потом прочитает этот request вместе с emoji и референсами.",
            reply_markup=back_menu(),
        )
        return

    if data == "mode:post":
        await edit_or_answer(
            message,
            "Кнопка больше не нужна: просто перешли сюда пост-референс, и я сохраню его автоматически без медиа.",
            reply_markup=main_menu(),
        )
        return

    if data == "draft:send_latest":
        await send_latest_draft_from_button(bot, message, library)
        return


async def send_latest_draft_from_button(bot: Bot, message: Message, library: LibraryStorage) -> None:
    draft = library.resolve_draft("latest")
    if not draft:
        await answer_html(
            message,
            f"Не нашел draft. Пусть Codex или Claude сохранит HTML-файл в <code>{escape(library.outbox_dir.relative_to(library.root).as_posix())}</code>.",
        )
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
        return (
            f"База emoji в профиле <b>{escape(library.active_profile_name())}</b> пустая. "
            "Просто отправь premium emoji пачкой в этот чат, я сохраню ID и скачаю ассеты."
        )

    lines = [
        "<b>База premium emoji</b>",
        f"Профиль: <b>{escape(library.active_profile_name())}</b>",
        f"Показываю последние 15. Полный список лежит в <code>{escape(library.premium_emojis_md.relative_to(library.root).as_posix())}</code>.",
        "",
    ]
    for item in rows[:15]:
        emoji_id = item.get("custom_emoji_id", "")
        alt = item.get("alt", "") or item.get("sticker_emoji", "") or "emoji"
        labels = ", ".join(item.get("labels", [])) or "unlabeled"
        asset_type = item.get("asset_type_label", "") or item.get("asset_type", "asset")
        lines.append(f"{tg_emoji_html(emoji_id, alt)} <code>{short_id(emoji_id)}</code> - {escape(asset_type)} - {escape(labels)}")
    return "\n".join(lines)


def render_emoji_search(library: LibraryStorage, query: str) -> str:
    matches = library.find_emojis(query, limit=200)
    if not matches:
        records = library.emoji_records()
        if not records:
            return (
                f"База emoji в профиле <b>{escape(library.active_profile_name())}</b> пустая. "
                "Сначала отправь premium emoji пачкой или ссылку на emoji pack."
            )
        unlabeled = sum(1 for item in records if not item.get("labels"))
        return "\n".join(
            [
                f"По запросу «{escape(query)}» ничего не нашел.",
                "",
                f"В профиле emoji: {len(records)}, из них без подписей: {unlabeled}.",
                "Поиск идет по подписям, тегам и названию пака. "
                "Если emoji не подписаны, искать пока не по чему.",
                "",
                "Нажми <b>AI: назвать emoji по ассетам</b> — агент подпишет их по картинкам, "
                "и поиск заработает.",
            ]
        )

    shown = matches[:SEARCH_RESULT_LIMIT]
    lines = [
        f"<b>Поиск emoji: «{escape(query)}»</b>",
        f"Профиль: <b>{escape(library.active_profile_name())}</b>",
        f"Совпадений: {len(matches)}" + (f", показываю {len(shown)}" if len(matches) > len(shown) else ""),
        "",
    ]
    for match in shown:
        item = match.record
        emoji_id = str(item.get("custom_emoji_id", ""))
        alt = item.get("alt", "") or item.get("sticker_emoji", "") or "🎁"
        labels = ", ".join(item.get("labels", [])) or "без названия"
        lines.append(f"{tg_emoji_html(emoji_id, alt)} <code>{short_id(emoji_id)}</code> - {escape(labels)}")
        lines.append(f"<code>{escape(tg_emoji_html(emoji_id, alt))}</code>")
        lines.append("")
    lines.append("Скопируй готовый тег в пост или попроси агента взять эти emoji.")
    return "\n".join(lines)


def render_decoration_report(library: LibraryStorage, result, draft_path: str) -> str:
    lines = [
        f"<b>Расставил emoji: {result.decorated_lines}</b>",
        f"Профиль: <b>{escape(library.active_profile_name())}</b>",
        f"Черновик: <code>{escape(draft_path)}</code>",
        "",
    ]
    for suggestion in result.suggestions:
        if not suggestion.chosen:
            continue
        match = suggestion.chosen
        item = match.record
        alt = item.get("alt") or item.get("sticker_emoji") or "🎁"
        labels = ", ".join(item.get("labels", [])) or "без названия"
        preview = suggestion.text.strip()[:38]
        lines.append(
            f"{tg_emoji_html(match.custom_emoji_id, alt)} <code>{short_id(match.custom_emoji_id)}</code> "
            f"- {escape(labels)} ({match.score:.1f})"
        )
        lines.append(f"  <i>{escape(preview)}…</i>" if len(suggestion.text.strip()) > 38 else f"  <i>{escape(preview)}</i>")
        if suggestion.alternatives:
            swaps = " ".join(
                tg_emoji_html(
                    alternative.custom_emoji_id,
                    alternative.record.get("alt") or alternative.record.get("sticker_emoji") or "🎁",
                )
                for alternative in suggestion.alternatives
            )
            lines.append(f"  замены: {swaps}")
        lines.append("")

    lines.append("Пост выше готов к отправке. Чтобы заменить emoji, отредактируй файл черновика.")
    return "\n".join(lines)


def render_drafts(library: LibraryStorage) -> str:
    drafts = library.list_drafts()
    if not drafts:
        return (
            f"Готовых постов в профиле <b>{escape(library.active_profile_name())}</b> пока нет. "
            f"Когда Codex или Claude сохранит HTML-файл в <code>{escape(library.outbox_dir.relative_to(library.root).as_posix())}</code>, "
            "бот отправит его owner'у сам."
        )
    lines = [
        "<b>Готовые HTML-посты</b>",
        f"Профиль: <b>{escape(library.active_profile_name())}</b>",
        f"Папка: <code>{escape(library.outbox_dir.relative_to(library.root).as_posix())}</code>",
        "",
    ]
    for draft in drafts[:15]:
        marker = "отправлен" if library.is_draft_sent(draft) else "ошибка" if library.is_draft_failed(draft) else "новый"
        lines.append(f"- <code>{escape(draft.name)}</code> ({marker})")
    return "\n".join(lines)


def render_profiles(library: LibraryStorage) -> str:
    rows = library.list_profiles()
    active = library.active_profile_slug()
    lines = [
        "<b>Профили</b>",
        "Профиль разделяет emoji, reference posts, стиль, post requests и outbox для разных тематик.",
        "",
    ]
    for profile in rows:
        stats = profile["stats"]
        marker = "✓ " if profile["slug"] == active else ""
        lines.extend(
            [
                f"{marker}<b>{escape(profile.get('name') or profile['slug'])}</b> <code>{escape(profile['slug'])}</code>",
                f"root: <code>{escape(profile['root'])}</code>",
                f"emoji: {stats.emojis} · posts: {stats.posts} · templates: {stats.templates} · drafts: {stats.drafts}",
                "",
            ]
        )
    lines.append("Нажми профиль ниже, чтобы переключиться. Новые материалы будут сохраняться в активный профиль.")
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
