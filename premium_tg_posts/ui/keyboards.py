from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1. Показать базу эмодзи", callback_data="menu:emojis"),
            ],
            [
                InlineKeyboardButton(text="2. Добавить стиль / структуру", callback_data="mode:template"),
            ],
            [
                InlineKeyboardButton(text="3. Добавить пример поста", callback_data="mode:post"),
            ],
            [
                InlineKeyboardButton(text="4. Готовые посты и отправка", callback_data="menu:drafts"),
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
                InlineKeyboardButton(text="Дальше: добавить стиль / структуру", callback_data="mode:template"),
            ],
            [
                InlineKeyboardButton(text="Дальше: добавить пример поста", callback_data="mode:post"),
            ],
            [
                InlineKeyboardButton(text="Показать базу эмодзи", callback_data="menu:emojis"),
            ],
            [
                InlineKeyboardButton(text="AI: назвать emoji по ассетам", callback_data="mode:emoji_label_prompt"),
            ],
            [
                InlineKeyboardButton(text="Опц.: вручную назвать emoji", callback_data="mode:label_last"),
            ],
        ]
    )


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
