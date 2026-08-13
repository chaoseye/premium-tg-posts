"""Bulk-import emoji packs into a profile.

The inline menu accepts at most five pack links per message and saves each emoji
one at a time, re-rendering the whole catalog on every record. That is fine for
a handful; importing thousands needs a different shape:

- conversions run in a worker pool instead of one at a time;
- the catalog is written once at the end, with periodic checkpoints;
- emoji already in the library are skipped without re-downloading.

Usage:
    python scripts/import_emoji_packs.py NyaEmoji DuckEmoji
    python scripts/import_emoji_packs.py --file packs.txt --workers 8
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Sticker

from premium_tg_posts.config import Settings
from premium_tg_posts.services.asset_converter import prepare_emoji_asset
from premium_tg_posts.services.emoji_collector import download_emoji_asset
from premium_tg_posts.services.storage import LibraryStorage
from premium_tg_posts.services.telegram_content import STICKER_SET_LINK_RE
from premium_tg_posts.utils.text import relative_to

LOGGER = logging.getLogger("import_emoji_packs")
CHECKPOINT_EVERY = 250
DOWNLOAD_ATTEMPTS = 3


def parse_pack_name(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    match = STICKER_SET_LINK_RE.search(value)
    if match:
        return match.group(1) or match.group(2) or ""
    return value


def read_names(args: argparse.Namespace) -> list[str]:
    raw: list[str] = list(args.packs)
    if args.file:
        raw.extend(Path(args.file).read_text(encoding="utf-8").splitlines())
    names = [parse_pack_name(item) for item in raw]
    return list(dict.fromkeys(name for name in names if name))


async def fetch_stickers(bot: Bot, names: list[str]) -> tuple[list[tuple[str, Sticker]], list[str]]:
    found: list[tuple[str, Sticker]] = []
    missing: list[str] = []
    for name in names:
        try:
            sticker_set = await bot.get_sticker_set(name=name)
        except Exception as exc:  # noqa: BLE001 - one broken link must not stop the run
            LOGGER.warning("pack %s is unavailable: %s", name, exc)
            missing.append(name)
            continue
        for sticker in sticker_set.stickers:
            if sticker.custom_emoji_id:
                found.append((sticker_set.title or name, sticker))
    return found, missing


async def process_sticker(
    bot: Bot,
    library: LibraryStorage,
    pack_title: str,
    sticker: Sticker,
    semaphore: asyncio.Semaphore,
) -> tuple[str, dict] | None:
    emoji_id = str(sticker.custom_emoji_id)
    async with semaphore:
        asset_path = None
        for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
            try:
                asset_path = await download_emoji_asset(bot, library, emoji_id, sticker)
            except TelegramRetryAfter as exc:
                await asyncio.sleep(float(exc.retry_after))
                continue
            if asset_path:
                break
            await asyncio.sleep(0.5 * attempt)
        if not asset_path:
            LOGGER.warning("could not download %s from %s", emoji_id, pack_title)
            return None

        record = {
            "alt": sticker.emoji,
            "sticker_emoji": sticker.emoji,
            "sticker_set_name": sticker.set_name,
            "sticker_set_title": pack_title,
            "file_id": sticker.file_id,
            "file_unique_id": sticker.file_unique_id,
            "is_animated": sticker.is_animated,
            "is_video": sticker.is_video,
            "source": f"sticker_set:{sticker.set_name}",
            "asset_path": relative_to(asset_path, library.root),
        }
        # Conversion shells out to node or ffmpeg, so keep it off the event loop.
        preview = await asyncio.to_thread(
            prepare_emoji_asset, asset_path, library.emoji_previews_dir, library.root
        )
        record.update(preview)
        return emoji_id, record


async def main_async(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    names = read_names(args)
    if not names:
        print("no pack names given")
        return 2

    settings = Settings.from_env()
    library = LibraryStorage(settings.storage_dir)
    library.ensure()

    bot = Bot(token=settings.telegram_bot_token)
    try:
        print(f"resolving {len(names)} packs…")
        stickers, missing = await fetch_stickers(bot, names)

        known = set(library.load_emojis().get("emojis", {}))
        pending: list[tuple[str, Sticker]] = []
        seen: set[str] = set()
        for pack_title, sticker in stickers:
            emoji_id = str(sticker.custom_emoji_id)
            if emoji_id in seen:
                continue
            seen.add(emoji_id)
            if emoji_id in known and not args.force:
                continue
            pending.append((pack_title, sticker))

        print(
            f"found {len(stickers)} emoji, {len(seen)} unique, "
            f"{len(seen) - len(pending)} already in the library, {len(pending)} to import"
        )
        if not pending:
            return 0

        semaphore = asyncio.Semaphore(args.workers)
        tasks = [
            asyncio.create_task(process_sticker(bot, library, title, sticker, semaphore))
            for title, sticker in pending
        ]

        collected: dict[str, dict] = {}
        imported = failed = 0
        started = time.monotonic()
        for index, task in enumerate(asyncio.as_completed(tasks), start=1):
            result = await task
            if result:
                collected[result[0]] = result[1]
                imported += 1
            else:
                failed += 1

            if len(collected) >= CHECKPOINT_EVERY:
                library.bulk_upsert_emojis(collected)
                collected.clear()

            if index % 50 == 0 or index == len(tasks):
                elapsed = time.monotonic() - started
                rate = index / elapsed if elapsed else 0
                remaining = (len(tasks) - index) / rate if rate else 0
                print(
                    f"  {index}/{len(tasks)}  ok={imported} fail={failed}  "
                    f"{rate:.1f}/s  осталось ~{remaining/60:.0f} мин",
                    flush=True,
                )

        library.bulk_upsert_emojis(collected)
    finally:
        await bot.session.close()

    total = len(library.load_emojis().get("emojis", {}))
    print(f"\nimported {imported}, failed {failed}, library now holds {total} emoji")
    if missing:
        print(f"unavailable packs ({len(missing)}): {', '.join(missing)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk-import Telegram emoji packs into the active profile.")
    parser.add_argument("packs", nargs="*", help="pack names or t.me/addemoji links")
    parser.add_argument("--file", help="file with one pack name or link per line")
    parser.add_argument("--workers", type=int, default=min(8, (os.cpu_count() or 4)))
    parser.add_argument("--force", action="store_true", help="re-process emoji already in the library")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
