from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    storage_dir: Path
    owner_user_id: int | None = None
    auto_push_outbox: bool = True
    outbox_poll_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and fill it.")
        storage_dir = Path(os.getenv("BOT_STORAGE_DIR", "storage")).resolve()
        owner_user_id = _optional_int(os.getenv("OWNER_USER_ID"))
        auto_push_outbox = os.getenv("AUTO_PUSH_OUTBOX", "1").strip().lower() not in {"0", "false", "no", "off"}
        outbox_poll_seconds = float(os.getenv("OUTBOX_POLL_SECONDS", "2"))
        return cls(
            telegram_bot_token=token,
            storage_dir=storage_dir,
            owner_user_id=owner_user_id,
            auto_push_outbox=auto_push_outbox,
            outbox_poll_seconds=outbox_poll_seconds,
        )


def _optional_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    return int(value)
