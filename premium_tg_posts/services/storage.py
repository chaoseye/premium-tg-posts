from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from premium_tg_posts.utils.text import (
    fenced_json,
    local_stamp,
    markdown_list,
    relative_to,
    short_id,
    slugify,
    utc_now_iso,
)


@dataclass
class StorageStats:
    emojis: int
    templates: int
    posts: int
    drafts: int


class LibraryStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.emoji_assets_dir = root / "emoji-assets"
        self.emoji_previews_dir = root / "emoji-previews"
        self.templates_dir = root / "templates"
        self.posts_dir = root / "posts"
        self.outbox_dir = root / "outbox"
        self.raw_dir = root / "raw"
        self.emoji_label_requests_dir = root / "emoji-label-requests"
        self.emojis_json = root / "emojis.json"
        self.state_json = root / "bot-state.json"
        self.premium_emojis_md = root / "premium-emojis.md"

    def ensure(self) -> None:
        for directory in (
            self.root,
            self.emoji_assets_dir,
            self.emoji_previews_dir,
            self.templates_dir,
            self.posts_dir,
            self.outbox_dir,
            self.raw_dir,
            self.emoji_label_requests_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.emojis_json.exists():
            self._write_json(self.emojis_json, {"updated_at": utc_now_iso(), "emojis": {}})
        if not self.state_json.exists():
            self._write_json(self.state_json, self._default_state())
        if not self.premium_emojis_md.exists():
            self.render_emojis_markdown()

    def stats(self) -> StorageStats:
        data = self.load_emojis()
        return StorageStats(
            emojis=len(data.get("emojis", {})),
            templates=len(list(self.templates_dir.glob("*.md"))),
            posts=len([path for path in self.posts_dir.iterdir() if path.is_dir()]) if self.posts_dir.exists() else 0,
            drafts=len(list(self.outbox_dir.glob("*.html"))),
        )

    def clear_runtime(self, preserve_owner: bool = True) -> StorageStats:
        state = self.load_state()
        owner = state.get("owner", {}) if preserve_owner else {}

        for path in (self.emojis_json, self.premium_emojis_md):
            if path.exists():
                path.unlink()

        for directory in (
            self.emoji_assets_dir,
            self.emoji_previews_dir,
            self.templates_dir,
            self.posts_dir,
            self.outbox_dir,
            self.raw_dir,
            self.emoji_label_requests_dir,
        ):
            self._clear_directory(directory)

        self._write_json(
            self.state_json,
            {
                "updated_at": utc_now_iso(),
                "owner": owner,
                "sent_drafts": {},
                "failed_drafts": {},
                "user_modes": {},
            },
        )
        self.ensure()
        return self.stats()

    def load_emojis(self) -> dict[str, Any]:
        return self._read_json(self.emojis_json, {"updated_at": utc_now_iso(), "emojis": {}})

    def load_state(self) -> dict[str, Any]:
        return self._read_json(self.state_json, self._default_state())

    def save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = utc_now_iso()
        self._write_json(self.state_json, state)

    def register_owner(
        self,
        user_id: int,
        chat_id: int,
        username: str | None = None,
        full_name: str | None = None,
        source: str = "auto",
        configured_owner_id: int | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        state = self.load_state()
        owner = state.setdefault("owner", {})
        expected_id = configured_owner_id or owner.get("user_id")

        if expected_id and int(expected_id) != int(user_id):
            return False, owner

        changed = not owner.get("user_id")
        owner.update(
            {
                "user_id": int(user_id),
                "chat_id": int(chat_id),
                "username": username,
                "full_name": full_name,
                "source": "env" if configured_owner_id else source,
                "last_seen_at": utc_now_iso(),
            }
        )
        owner.setdefault("first_seen_at", utc_now_iso())
        self.save_state(state)
        return changed, owner

    def owner_chat_id(self) -> int | None:
        owner = self.load_state().get("owner", {})
        chat_id = owner.get("chat_id")
        return int(chat_id) if chat_id else None

    def is_draft_sent(self, draft: Path) -> bool:
        state = self.load_state()
        key = self._draft_key(draft)
        return key in state.get("sent_drafts", {})

    def is_draft_failed(self, draft: Path) -> bool:
        state = self.load_state()
        key = self._draft_key(draft)
        return key in state.get("failed_drafts", {})

    def mark_draft_sent(self, draft: Path, message_id: int | None = None) -> None:
        state = self.load_state()
        sent_drafts = state.setdefault("sent_drafts", {})
        key = self._draft_key(draft)
        sent_drafts[key] = {
            "path": relative_to(draft, self.root),
            "mtime": draft.stat().st_mtime,
            "size": draft.stat().st_size,
            "message_id": message_id,
            "sent_at": utc_now_iso(),
        }
        self.save_state(state)

    def mark_draft_failed(self, draft: Path, error: str) -> None:
        state = self.load_state()
        failed_drafts = state.setdefault("failed_drafts", {})
        key = self._draft_key(draft)
        failed_drafts[key] = {
            "path": relative_to(draft, self.root),
            "mtime": draft.stat().st_mtime,
            "size": draft.stat().st_size,
            "error": error,
            "failed_at": utc_now_iso(),
        }
        self.save_state(state)

    def pending_drafts(self) -> list[Path]:
        return [
            draft
            for draft in reversed(self.list_drafts())
            if not self.is_draft_sent(draft) and not self.is_draft_failed(draft)
        ]

    def set_user_mode(self, user_id: int, mode: str, data: dict[str, Any] | None = None) -> None:
        state = self.load_state()
        user_modes = state.setdefault("user_modes", {})
        user_modes[str(user_id)] = {
            "mode": mode,
            "data": data or {},
            "created_at": utc_now_iso(),
        }
        self.save_state(state)

    def pop_user_mode(self, user_id: int) -> dict[str, Any] | None:
        state = self.load_state()
        user_modes = state.setdefault("user_modes", {})
        mode = user_modes.pop(str(user_id), None)
        self.save_state(state)
        return mode

    def peek_user_mode(self, user_id: int) -> dict[str, Any] | None:
        return self.load_state().get("user_modes", {}).get(str(user_id))

    def upsert_emoji(self, emoji_id: str, record: dict[str, Any]) -> dict[str, Any]:
        data = self.load_emojis()
        emojis = data.setdefault("emojis", {})
        existing = emojis.get(emoji_id, {})
        merged = {**existing, **{key: value for key, value in record.items() if value not in (None, "", [])}}
        merged["custom_emoji_id"] = emoji_id
        merged.setdefault("first_seen_at", utc_now_iso())
        merged["last_seen_at"] = utc_now_iso()
        merged["seen_count"] = int(existing.get("seen_count", 0)) + 1

        labels = list(dict.fromkeys([*existing.get("labels", []), *record.get("labels", [])]))
        if labels:
            merged["labels"] = labels

        tags = list(dict.fromkeys([*existing.get("tags", []), *record.get("tags", [])]))
        if tags:
            merged["tags"] = tags

        emojis[emoji_id] = merged
        data["updated_at"] = utc_now_iso()
        self._write_json(self.emojis_json, data)
        self.render_emojis_markdown()
        return merged

    def update_emoji_label(self, selector: str, label: str) -> dict[str, Any] | None:
        data = self.load_emojis()
        emoji_id = self.resolve_emoji_id(selector, data)
        if not emoji_id:
            return None
        record = data["emojis"][emoji_id]
        labels = record.setdefault("labels", [])
        if label not in labels:
            labels.insert(0, label)
        record["last_labeled_at"] = utc_now_iso()
        data["updated_at"] = utc_now_iso()
        self._write_json(self.emojis_json, data)
        self.render_emojis_markdown()
        return record

    def latest_emoji(self) -> dict[str, Any] | None:
        records = self.emoji_records(sort_by="last_seen_at", reverse=True)
        return records[0] if records else None

    def emoji_records(self, sort_by: str = "first_seen_at", reverse: bool = False) -> list[dict[str, Any]]:
        data = self.load_emojis()
        return sorted(data.get("emojis", {}).values(), key=lambda item: item.get(sort_by, ""), reverse=reverse)

    def create_emoji_label_request(self, prompt: str) -> Path:
        request_path = self._unique_file(
            self.emoji_label_requests_dir,
            f"{local_stamp()}-emoji-label-request",
            ".md",
        )
        rows = self.emoji_records(sort_by="last_seen_at", reverse=True)
        lines = [
            "# Emoji Label Request",
            "",
            f"- created_at: {utc_now_iso()}",
            f"- prompt: {prompt}",
            "",
            "## Task",
            "",
            "Inspect the downloaded emoji assets and add concise human labels to `storage/emojis.json`.",
            "After editing labels, re-render `storage/premium-emojis.md` with:",
            "",
            "```powershell",
            "python -B -c \"from pathlib import Path; from premium_tg_posts.services.storage import LibraryStorage; LibraryStorage(Path('storage')).render_emojis_markdown()\"",
            "```",
            "",
            "## Emoji Assets",
            "",
            "| Current label | Alt | Type | Short ID | Custom emoji ID | Asset | Preview | SVG | HTML tag |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in rows:
            emoji_id = item.get("custom_emoji_id", "")
            labels = ", ".join(item.get("labels", [])) or "unlabeled"
            alt = item.get("alt", "") or item.get("sticker_emoji", "") or "emoji"
            asset_type = item.get("asset_type_label", "") or item.get("asset_type", "")
            asset = item.get("asset_path", "")
            preview = item.get("preview_path", "")
            svg_preview = item.get("svg_preview_path", "")
            html_tag = f'<tg-emoji emoji-id="{emoji_id}">{alt}</tg-emoji>'
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(labels),
                        _md_cell(alt),
                        _md_cell(asset_type),
                        f"`{short_id(emoji_id)}`",
                        f"`{emoji_id}`",
                        _md_cell(asset),
                        _md_cell(preview),
                        _md_cell(svg_preview),
                        f"`{html_tag}`",
                    ]
                )
                + " |"
            )
        request_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return request_path

    def resolve_emoji_id(self, selector: str, data: dict[str, Any] | None = None) -> str | None:
        data = data or self.load_emojis()
        emojis = data.get("emojis", {})
        if selector == "last" and emojis:
            newest = max(emojis.values(), key=lambda item: item.get("last_seen_at", ""))
            return newest.get("custom_emoji_id")
        if selector in emojis:
            return selector
        matches = [emoji_id for emoji_id in emojis if emoji_id.endswith(selector)]
        if len(matches) == 1:
            return matches[0]
        return None

    def emoji_asset_path(self, emoji_id: str, suffix: str) -> Path:
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        return self.emoji_assets_dir / f"{emoji_id}{suffix}"

    def render_emojis_markdown(self) -> None:
        data = self.load_emojis()
        emojis = sorted(data.get("emojis", {}).values(), key=lambda item: item.get("first_seen_at", ""))
        lines = [
            "# Premium Emojis",
            "",
            "This file is generated by the local Telegram collector bot.",
            "Labels are optional human hints. The source of truth is the custom emoji ID plus the downloaded asset file.",
            "",
            "| Label (optional) | Alt | Type | Short ID | Custom emoji ID | HTML tag | Asset | Preview | SVG | Tags |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in emojis:
            emoji_id = item.get("custom_emoji_id", "")
            labels = ", ".join(item.get("labels", [])) or "unlabeled"
            alt = item.get("alt", "") or item.get("sticker_emoji", "") or "emoji"
            asset_type = item.get("asset_type_label", "") or item.get("asset_type", "")
            asset = item.get("asset_path", "")
            preview = item.get("preview_path", "")
            svg_preview = item.get("svg_preview_path", "")
            tags = ", ".join(item.get("tags", []))
            html_tag = f'<tg-emoji emoji-id="{emoji_id}">{alt}</tg-emoji>'
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(labels),
                        _md_cell(alt),
                        _md_cell(asset_type),
                        f"`{short_id(emoji_id)}`",
                        f"`{emoji_id}`",
                        f"`{html_tag}`",
                        _md_cell(asset),
                        _md_cell(preview),
                        _md_cell(svg_preview),
                        _md_cell(tags),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "## AI Agent Usage",
                "",
                "Use the `HTML tag` values when drafting Telegram posts. Inspect downloaded files in `storage/emoji-assets` when labels are missing or unclear.",
                "Keep normal post text in HTML format and save the final draft in `storage/outbox`.",
            ]
        )
        self.premium_emojis_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def save_template(self, title: str, text: str, entities: list[dict[str, Any]], raw_message: dict[str, Any]) -> Path:
        slug = self._unique_file(self.templates_dir, f"{local_stamp()}-{slugify(title, 'template')}", ".md")
        raw_name = slug.with_suffix(".json").name
        raw_path = self.raw_dir / raw_name
        self._write_json(raw_path, raw_message)
        body = [
            "---",
            f'title: "{title.replace(chr(34), chr(39))}"',
            f"saved_at: {utc_now_iso()}",
            f"raw_message: {relative_to(raw_path, self.root)}",
            "---",
            "",
            "# Template",
            "",
            text.strip(),
            "",
            "## Entities",
            "",
            fenced_json(json.dumps(entities, ensure_ascii=False, indent=2)),
            "",
        ]
        slug.write_text("\n".join(body), encoding="utf-8")
        return slug

    def save_post(
        self,
        title: str,
        text: str,
        entities: list[dict[str, Any]],
        raw_message: dict[str, Any],
        media_files: list[dict[str, Any]],
        post_dir: Path | None = None,
    ) -> Path:
        post_dir = post_dir or self.create_post_dir(title)
        media_lines = [
            f"{item.get('type', 'file')}: `{item.get('path', '')}`"
            + (f" ({item.get('note')})" if item.get("note") else "")
            for item in media_files
        ]
        self._write_json(post_dir / "message.json", raw_message)
        self._write_json(post_dir / "entities.json", entities)
        body = [
            f"# {title}",
            "",
            f"- saved_at: {utc_now_iso()}",
            f"- raw_message: `{relative_to(post_dir / 'message.json', self.root)}`",
            "",
            "## Text",
            "",
            text.strip() or "_No text or caption._",
            "",
            "## Media",
            "",
            markdown_list(media_lines),
            "",
            "## Entities",
            "",
            fenced_json(json.dumps(entities, ensure_ascii=False, indent=2)),
            "",
            "## Notes For AI Agents",
            "",
            "- Treat this as a reference post: keep the useful structure and tone, do not copy blindly.",
            "- If premium emoji entities are present, prefer matching saved entries from `storage/premium-emojis.md`.",
            "",
        ]
        (post_dir / "index.md").write_text("\n".join(body), encoding="utf-8")
        return post_dir

    def create_post_dir(self, title: str) -> Path:
        return self._unique_dir(self.posts_dir, f"{local_stamp()}-{slugify(title, 'post')}")

    def list_drafts(self) -> list[Path]:
        return sorted(self.outbox_dir.glob("*.html"), key=lambda path: path.stat().st_mtime, reverse=True)

    def resolve_draft(self, selector: str | None) -> Path | None:
        drafts = self.list_drafts()
        if not drafts:
            return None
        if not selector or selector == "latest":
            return drafts[0]
        for draft in drafts:
            if draft.name == selector or draft.stem == selector:
                return draft
        matches = [draft for draft in drafts if selector in draft.name]
        if len(matches) == 1:
            return matches[0]
        return None

    def _unique_file(self, directory: Path, stem: str, suffix: str) -> Path:
        candidate = directory / f"{stem}{suffix}"
        counter = 2
        while candidate.exists():
            candidate = directory / f"{stem}-{counter}{suffix}"
            counter += 1
        return candidate

    def _unique_dir(self, directory: Path, stem: str) -> Path:
        candidate = directory / stem
        counter = 2
        while candidate.exists():
            candidate = directory / f"{stem}-{counter}"
            counter += 1
        candidate.mkdir(parents=True, exist_ok=False)
        (candidate / "media").mkdir(exist_ok=True)
        return candidate

    def _clear_directory(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for child in directory.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        gitkeep = directory / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("\n", encoding="utf-8")

    def _read_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def _write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _default_state(self) -> dict[str, Any]:
        return {"updated_at": utc_now_iso(), "owner": {}, "sent_drafts": {}, "failed_drafts": {}, "user_modes": {}}

    def _draft_key(self, draft: Path) -> str:
        try:
            stat = draft.stat()
        except FileNotFoundError:
            return relative_to(draft, self.root)
        return f"{relative_to(draft, self.root)}:{stat.st_mtime_ns}:{stat.st_size}"


def _md_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")
