from __future__ import annotations

from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Message


class DraftSendError(RuntimeError):
    pass


async def send_html_draft(bot: Bot, chat_id: int, draft: Path) -> Message:
    html = draft.read_text(encoding="utf-8").strip()
    if not html:
        raise DraftSendError(f"Draft is empty: {draft.name}")
    if len(html) > 4096:
        raise DraftSendError("Draft is longer than Telegram sendMessage limit (4096 chars).")
    return await bot.send_message(
        chat_id=chat_id,
        text=html,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
