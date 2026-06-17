from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Message, TelegramObject

from premium_tg_posts.config import Settings
from premium_tg_posts.services.storage import LibraryStorage


class OwnerMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        library: LibraryStorage | None = data.get("library")
        if isinstance(event, Message) and library and event.from_user and event.chat.type == ChatType.PRIVATE:
            user = event.from_user
            library.register_owner(
                user_id=user.id,
                chat_id=event.chat.id,
                username=user.username,
                full_name=user.full_name,
                configured_owner_id=self.settings.owner_user_id,
            )
        return await handler(event, data)
