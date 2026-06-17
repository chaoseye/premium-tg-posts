from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .config import Settings
from .handlers import callbacks_router, collector_router, commands_router
from .middlewares.owner import OwnerMiddleware
from .services.outbox_watcher import watch_outbox
from .services.storage import LibraryStorage

LOGGER = logging.getLogger(__name__)


async def main_async() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()

    library = LibraryStorage(settings.storage_dir)
    library.ensure()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher["library"] = library
    dispatcher["settings"] = settings
    dispatcher.message.outer_middleware(OwnerMiddleware(settings))
    dispatcher.include_router(commands_router)
    dispatcher.include_router(callbacks_router)
    dispatcher.include_router(collector_router)

    await bot.set_my_commands(
        [
            BotCommand(command="help", description="commands and workflow"),
            BotCommand(command="stats", description="storage counters"),
            BotCommand(command="emojis", description="recent premium emoji"),
            BotCommand(command="label", description="label an emoji"),
            BotCommand(command="template", description="save a template"),
            BotCommand(command="post", description="save replied post"),
            BotCommand(command="drafts", description="list AI drafts"),
            BotCommand(command="send_draft", description="send AI draft"),
            BotCommand(command="owner", description="detected owner"),
        ]
    )

    me = await bot.get_me()
    LOGGER.info("Bot ready: @%s (%s). Storage: %s", me.username, me.id, library.root)
    watcher = None
    if settings.auto_push_outbox:
        watcher = asyncio.create_task(watch_outbox(bot, library, settings.outbox_poll_seconds))
    try:
        await dispatcher.start_polling(bot)
    finally:
        if watcher:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)


def main() -> int:
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        return 0
    except RuntimeError as exc:
        print(exc)
        return 2
    return 0
