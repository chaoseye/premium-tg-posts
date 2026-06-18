from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.enums import MessageEntityType
from aiogram.types import Message, MessageEntity

from premium_tg_posts.utils.text import relative_to, utf16_slice

STICKER_SET_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:addemoji|addstickers)/([A-Za-z0-9_]+)|"
    r"tg://addstickers\?set=([A-Za-z0-9_]+)",
    re.IGNORECASE,
)


def message_text_and_entities(message: Message) -> tuple[str, list[MessageEntity]]:
    if message.text is not None:
        return message.text, list(message.entities or [])
    if message.caption is not None:
        return message.caption, list(message.caption_entities or [])
    return "", []


def split_title_and_body(payload: str) -> tuple[str, str]:
    title, _, body = payload.partition("\n")
    return title.strip(), body.strip()


def is_forwarded(message: Message) -> bool:
    return any(
        getattr(message, attr, None)
        for attr in ("forward_origin", "forward_date", "forward_from", "forward_sender_name", "forward_from_chat")
    )


def has_collectable_material(message: Message) -> bool:
    return any(
        getattr(message, attr, None)
        for attr in (
            "text",
            "caption",
            "photo",
            "video",
            "animation",
            "document",
            "audio",
            "voice",
            "sticker",
        )
    )


def custom_emoji_entities(message: Message) -> list[dict[str, Any]]:
    text, entities = message_text_and_entities(message)
    results: list[dict[str, Any]] = []
    for entity in entities:
        if entity_type(entity) != MessageEntityType.CUSTOM_EMOJI.value:
            continue
        emoji_id = entity.custom_emoji_id
        if not emoji_id:
            continue
        offset = int(entity.offset or 0)
        length = int(entity.length or 0)
        results.append(
            {
                "type": "custom_emoji",
                "custom_emoji_id": emoji_id,
                "offset": offset,
                "length": length,
                "alt": utf16_slice(text, offset, length),
            }
        )
    return results


def sticker_set_names(message: Message) -> list[str]:
    text, _ = message_text_and_entities(message)
    names: list[str] = []
    for match in STICKER_SET_LINK_RE.finditer(text):
        name = match.group(1) or match.group(2)
        if name:
            names.append(name)
    return list(dict.fromkeys(names))


def serializable_entities(message: Message) -> list[dict[str, Any]]:
    text, entities = message_text_and_entities(message)
    rows: list[dict[str, Any]] = []
    for entity in entities:
        offset = int(entity.offset or 0)
        length = int(entity.length or 0)
        item = entity.model_dump(mode="json", exclude_none=True)
        item["text"] = utf16_slice(text, offset, length)
        rows.append(item)
    return rows


def message_title(message: Message, fallback: str = "post") -> str:
    text, _ = message_text_and_entities(message)
    clean = " ".join(text.strip().split())
    if clean:
        return clean[:60]
    if message.from_user and message.from_user.username:
        return f"{fallback}-from-{message.from_user.username}"
    if message.chat and message.chat.title:
        return f"{fallback}-from-{message.chat.title}"
    return fallback


def raw_message(message: Message) -> dict[str, Any]:
    try:
        return message.model_dump(mode="json", exclude_none=True)
    except Exception:  # noqa: BLE001 - aiogram may keep Default sentinels in forwarded payloads.
        payload = message.model_dump(mode="python", exclude_none=True)
        return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


async def download_message_media(bot: Bot, message: Message, media_dir: Path, storage_root: Path) -> list[dict[str, Any]]:
    media_dir.mkdir(parents=True, exist_ok=True)
    media: list[dict[str, Any]] = []
    specs = _media_specs(message)
    for index, spec in enumerate(specs, start=1):
        kind = spec["type"]
        obj = spec["object"]
        file_id = getattr(obj, "file_id", None)
        if not file_id:
            continue
        try:
            tg_file = await bot.get_file(file_id)
            if not tg_file.file_path:
                raise RuntimeError("Telegram did not return file_path")
            suffix = Path(tg_file.file_path).suffix or spec.get("suffix", ".bin")
            filename = _safe_filename(getattr(obj, "file_name", None), f"{index:02d}-{kind}{suffix}")
            destination = _unique_destination(media_dir / filename)
            await bot.download_file(tg_file.file_path, destination=destination)
            media.append(
                {
                    "type": kind,
                    "file_id": file_id,
                    "path": relative_to(destination, storage_root),
                }
            )
        except Exception as exc:  # noqa: BLE001 - local collector should survive one failed attachment.
            media.append({"type": kind, "file_id": file_id, "path": "", "note": f"download failed: {exc}"})
    return media


def entity_type(entity: MessageEntity) -> str:
    value = entity.type
    return getattr(value, "value", str(value))


def _media_specs(message: Message) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if message.photo:
        specs.append({"type": "photo", "object": message.photo[-1], "suffix": ".jpg"})
    for kind, suffix in (
        ("animation", ".mp4"),
        ("audio", ".mp3"),
        ("document", ".bin"),
        ("video", ".mp4"),
        ("video_note", ".mp4"),
        ("voice", ".ogg"),
        ("sticker", ".webp"),
    ):
        obj = getattr(message, kind, None)
        if obj:
            specs.append({"type": kind, "object": obj, "suffix": suffix})
    return specs


def _safe_filename(name: str | None, fallback: str) -> str:
    if not name:
        return fallback
    forbidden = '<>:"/\\|?*'
    cleaned = "".join("-" if char in forbidden else char for char in name).strip()
    return cleaned or fallback


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
