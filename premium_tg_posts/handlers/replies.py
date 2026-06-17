from __future__ import annotations

from aiogram.enums import ParseMode
from aiogram.types import Message


async def answer_html(message: Message, text: str) -> None:
    await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
