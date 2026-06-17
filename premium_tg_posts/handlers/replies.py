from __future__ import annotations

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, Message


async def answer_html(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=reply_markup)
