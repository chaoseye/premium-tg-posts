from __future__ import annotations

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message


async def answer_html(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> Message:
    return await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=reply_markup)


async def edit_or_answer_html(
    source_message: Message,
    status_message: Message | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if status_message:
        try:
            await status_message.edit_text(text, disable_web_page_preview=True, reply_markup=reply_markup)
            return
        except TelegramBadRequest:
            pass
    await answer_html(source_message, text, reply_markup=reply_markup)
