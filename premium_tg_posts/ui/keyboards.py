from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Профили", callback_data="profiles:menu"),
            ],
            [
                InlineKeyboardButton(text="Показать базу emoji", callback_data="menu:emojis"),
            ],
            [
                InlineKeyboardButton(text="Добавить emoji в мой пост", callback_data="mode:decorate_post"),
            ],
            [
                InlineKeyboardButton(text="Найти emoji по смыслу", callback_data="mode:emoji_find"),
            ],
            [
                InlineKeyboardButton(text="Сгенерировать пост на тему", callback_data="mode:post_topic"),
            ],
            [
                InlineKeyboardButton(text="Готовые посты и отправка", callback_data="menu:drafts"),
            ],
            [
                InlineKeyboardButton(text="Что уже сохранено?", callback_data="menu:stats"),
                InlineKeyboardButton(text="Как это работает?", callback_data="menu:help"),
            ],
            [
                InlineKeyboardButton(text="AI: назвать emoji по ассетам", callback_data="mode:emoji_label_prompt"),
            ],
            [
                InlineKeyboardButton(text="Опц.: вручную назвать emoji", callback_data="mode:label_last"),
            ],
            [
                InlineKeyboardButton(text="Доп.: добавить стиль / структуру", callback_data="mode:template"),
            ],
            [
                InlineKeyboardButton(text="Очистить хранилище", callback_data="storage:clear_prompt"),
            ],
        ]
    )


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Вернуться к шагам", callback_data="menu:home")],
        ]
    )


def drafts_menu(has_drafts: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_drafts:
        rows.append([InlineKeyboardButton(text="Отправить последний готовый пост", callback_data="draft:send_latest")])
    rows.append([InlineKeyboardButton(text="Вернуться к шагам", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_collect_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Профили", callback_data="profiles:menu"),
            ],
            [
                InlineKeyboardButton(text="Сгенерировать пост на тему", callback_data="mode:post_topic"),
            ],
            [
                InlineKeyboardButton(text="AI: назвать emoji по ассетам", callback_data="mode:emoji_label_prompt"),
            ],
            [
                InlineKeyboardButton(text="Опц.: вручную назвать emoji", callback_data="mode:label_last"),
            ],
            [
                InlineKeyboardButton(text="Показать базу emoji", callback_data="menu:emojis"),
            ],
            [
                InlineKeyboardButton(text="Добавить emoji в мой пост", callback_data="mode:decorate_post"),
            ],
            [
                InlineKeyboardButton(text="Найти emoji по смыслу", callback_data="mode:emoji_find"),
            ],
            [
                InlineKeyboardButton(text="Доп.: добавить стиль / структуру", callback_data="mode:template"),
            ],
        ]
    )


def profiles_menu(profiles: list[dict], active_slug: str) -> InlineKeyboardMarkup:
    rows = []
    for profile in profiles[:12]:
        slug = str(profile.get("slug") or "")
        name = str(profile.get("name") or slug or "profile")
        prefix = "✓ " if slug == active_slug else ""
        rows.append([InlineKeyboardButton(text=f"{prefix}{name[:40]}", callback_data=f"profile:switch:{slug}")])
    rows.append([InlineKeyboardButton(text="Создать профиль", callback_data="profile:create")])
    rows.append([InlineKeyboardButton(text="Вернуться к шагам", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def emoji_label_menu(index: int, total: int) -> InlineKeyboardMarkup:
    previous_index = (index - 1) % total if total else 0
    next_index = (index + 1) % total if total else 0
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="← Назад", callback_data=f"emoji_label:{previous_index}"),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="emoji_label:noop"),
                InlineKeyboardButton(text="Вперед →", callback_data=f"emoji_label:{next_index}"),
            ],
            [
                InlineKeyboardButton(text="К шагам", callback_data="menu:home"),
                InlineKeyboardButton(text="База emoji", callback_data="menu:emojis"),
            ],
        ]
    )


def clear_storage_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, очистить", callback_data="storage:clear_confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="storage:clear_cancel")],
        ]
    )
