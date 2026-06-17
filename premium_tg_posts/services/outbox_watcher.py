from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from premium_tg_posts.services.drafts import DraftSendError, send_html_draft
from premium_tg_posts.services.storage import LibraryStorage

LOGGER = logging.getLogger(__name__)


async def watch_outbox(bot: Bot, library: LibraryStorage, interval_seconds: float) -> None:
    while True:
        await push_pending_drafts(bot, library)
        await asyncio.sleep(interval_seconds)


async def push_pending_drafts(bot: Bot, library: LibraryStorage) -> None:
    owner_chat_id = library.owner_chat_id()
    if not owner_chat_id:
        return

    for draft in library.pending_drafts():
        try:
            sent = await send_html_draft(bot, owner_chat_id, draft)
            library.mark_draft_sent(draft, sent.message_id)
            LOGGER.info("Auto-pushed draft to owner: %s", draft.name)
        except (DraftSendError, TelegramBadRequest) as exc:
            library.mark_draft_failed(draft, str(exc))
            LOGGER.warning("Could not auto-push draft %s: %s", draft.name, exc)
