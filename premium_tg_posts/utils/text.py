from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Iterable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def local_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def slugify(value: str | None, fallback: str = "item", max_length: int = 64) -> str:
    value = value or ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", ascii_value).strip("-._").lower()
    if not slug:
        slug = fallback
    return slug[:max_length].strip("-._") or fallback


def short_id(value: str, length: int = 8) -> str:
    return value[-length:] if len(value) > length else value


def fenced_json(value: str) -> str:
    return f"```json\n{value}\n```"


def relative_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def markdown_list(items: Iterable[str]) -> str:
    rows = [f"- {item}" for item in items if item]
    return "\n".join(rows) if rows else "- none"


def html_code(value: str) -> str:
    return f"<code>{escape(value)}</code>"


def utf16_slice(text: str, offset: int, length: int) -> str:
    start = _utf16_index_to_py_index(text, offset)
    end = _utf16_index_to_py_index(text, offset + length)
    return text[start:end]


def _utf16_index_to_py_index(text: str, target_units: int) -> int:
    units = 0
    for index, char in enumerate(text):
        if units >= target_units:
            return index
        units += len(char.encode("utf-16-le")) // 2
    return len(text)
