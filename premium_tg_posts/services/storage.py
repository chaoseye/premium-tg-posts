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


DEFAULT_PROFILE_SLUG = "default"
DEFAULT_PROFILE_NAME = "Default"


class LibraryStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.profiles_dir = root / "profiles"
        self.state_json = root / "bot-state.json"

    @property
    def emoji_assets_dir(self) -> Path:
        return self.profile_root() / "emoji-assets"

    @property
    def emoji_previews_dir(self) -> Path:
        return self.profile_root() / "emoji-previews"

    @property
    def templates_dir(self) -> Path:
        return self.profile_root() / "templates"

    @property
    def posts_dir(self) -> Path:
        return self.profile_root() / "posts"

    @property
    def outbox_dir(self) -> Path:
        return self.profile_root() / "outbox"

    @property
    def raw_dir(self) -> Path:
        return self.profile_root() / "raw"

    @property
    def emoji_label_requests_dir(self) -> Path:
        return self.profile_root() / "emoji-label-requests"

    @property
    def post_generation_requests_dir(self) -> Path:
        return self.profile_root() / "post-requests"

    @property
    def emojis_json(self) -> Path:
        return self.profile_root() / "emojis.json"

    @property
    def premium_emojis_md(self) -> Path:
        return self.profile_root() / "premium-emojis.md"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_gitkeep(self.root)
        self._ensure_gitkeep(self.profiles_dir)
        if not self.state_json.exists():
            self._write_json(self.state_json, self._default_state())
        state = self.load_state()
        if self._ensure_state_profiles(state):
            self.save_state(state)
        self.ensure_profile(self.active_profile_slug(state))

    def ensure_profile(self, slug: str | None = None) -> None:
        profile_root = self.profile_root(slug)
        profile_root.mkdir(parents=True, exist_ok=True)
        self._ensure_gitkeep(profile_root)
        for directory in self._profile_directories(profile_root):
            directory.mkdir(parents=True, exist_ok=True)
            self._ensure_gitkeep(directory)
        emojis_json = profile_root / "emojis.json"
        premium_emojis_md = profile_root / "premium-emojis.md"
        if not emojis_json.exists():
            self._write_json(emojis_json, {"updated_at": utc_now_iso(), "emojis": {}})
        if not premium_emojis_md.exists():
            self.render_emojis_markdown(slug)

    def stats(self, slug: str | None = None) -> StorageStats:
        profile_root = self.profile_root(slug)
        data = self.load_emojis(slug)
        templates_dir = profile_root / "templates"
        posts_dir = profile_root / "posts"
        outbox_dir = profile_root / "outbox"
        return StorageStats(
            emojis=len(data.get("emojis", {})),
            templates=len(list(templates_dir.glob("*.md"))) if templates_dir.exists() else 0,
            posts=len([path for path in posts_dir.iterdir() if path.is_dir()]) if posts_dir.exists() else 0,
            drafts=len(list(outbox_dir.glob("*.html"))) if outbox_dir.exists() else 0,
        )

    def clear_runtime(self, preserve_owner: bool = True, all_profiles: bool = False) -> StorageStats:
        state = self.load_state()
        owner = state.get("owner", {}) if preserve_owner else {}

        if all_profiles:
            self._clear_profile_runtime(DEFAULT_PROFILE_SLUG)
            self._clear_directory(self.profiles_dir)
            next_state = self._default_state()
            next_state["owner"] = owner
        else:
            self._clear_profile_runtime(self.active_profile_slug(state))
            next_state = state
            next_state["owner"] = owner
            next_state["sent_drafts"] = {}
            next_state["failed_drafts"] = {}
            next_state["user_modes"] = {}
            self._ensure_state_profiles(next_state)

        self._write_json(self.state_json, next_state)
        self.ensure()
        return self.stats()

    def load_emojis(self, slug: str | None = None) -> dict[str, Any]:
        return self._read_json(self.profile_root(slug) / "emojis.json", {"updated_at": utc_now_iso(), "emojis": {}})

    def load_state(self) -> dict[str, Any]:
        return self._read_json(self.state_json, self._default_state())

    def save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = utc_now_iso()
        self._write_json(self.state_json, state)

    def profile_root(self, slug: str | None = None) -> Path:
        profile_slug = slug or self.active_profile_slug()
        if profile_slug == DEFAULT_PROFILE_SLUG:
            return self.root
        return self.profiles_dir / profile_slug

    def active_profile_slug(self, state: dict[str, Any] | None = None) -> str:
        state = state or self.load_state()
        return str(state.get("active_profile") or DEFAULT_PROFILE_SLUG)

    def active_profile(self) -> dict[str, Any]:
        state = self.load_state()
        if self._ensure_state_profiles(state):
            self.save_state(state)
        slug = self.active_profile_slug(state)
        return state["profiles"].get(slug, state["profiles"][DEFAULT_PROFILE_SLUG])

    def active_profile_name(self) -> str:
        return str(self.active_profile().get("name") or DEFAULT_PROFILE_NAME)

    def list_profiles(self) -> list[dict[str, Any]]:
        state = self.load_state()
        if self._ensure_state_profiles(state):
            self.save_state(state)
        active = self.active_profile_slug(state)
        rows = []
        for slug, profile in state.get("profiles", {}).items():
            stats = self.stats(slug)
            rows.append(
                {
                    **profile,
                    "slug": slug,
                    "active": slug == active,
                    "stats": stats,
                    "root": relative_to(self.profile_root(slug), self.root),
                }
            )
        return sorted(rows, key=lambda item: (not item["active"], item.get("name", "").lower(), item["slug"]))

    def create_profile(self, name: str, activate: bool = True) -> dict[str, Any]:
        display_name = " ".join(name.split()) or "New profile"
        state = self.load_state()
        self._ensure_state_profiles(state)
        profiles = state.setdefault("profiles", {})
        base_slug = slugify(display_name, "profile", max_length=40)
        slug = base_slug
        counter = 2
        while slug in profiles:
            suffix = f"-{counter}"
            slug = f"{base_slug[: 40 - len(suffix)]}{suffix}".strip("-") or f"profile-{counter}"
            counter += 1
        now = utc_now_iso()
        profiles[slug] = {
            "slug": slug,
            "name": display_name,
            "created_at": now,
            "last_used_at": now,
        }
        if activate:
            state["active_profile"] = slug
        self.save_state(state)
        self.ensure_profile(slug)
        return profiles[slug]

    def set_active_profile(self, slug: str) -> dict[str, Any] | None:
        state = self.load_state()
        self._ensure_state_profiles(state)
        profiles = state.setdefault("profiles", {})
        profile = profiles.get(slug)
        if not profile:
            return None
        state["active_profile"] = slug
        profile["last_used_at"] = utc_now_iso()
        self.save_state(state)
        self.ensure_profile(slug)
        return profile

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
        active_profile = self.active_profile()
        profile_slug = str(active_profile.get("slug") or self.active_profile_slug())
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
            f"- profile: {active_profile.get('name')} (`{profile_slug}`)",
            "",
            "## Task",
            "",
            f"Inspect the downloaded emoji assets and add concise human labels to `{self._display_path(self.emojis_json)}`.",
            f"After editing labels, re-render `{self._display_path(self.premium_emojis_md)}` with:",
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

    def create_post_generation_request(self, topic: str) -> Path:
        active_profile = self.active_profile()
        profile_slug = str(active_profile.get("slug") or self.active_profile_slug())
        request_path = self._unique_file(
            self.post_generation_requests_dir,
            f"{local_stamp()}-post-generation-request",
            ".md",
        )
        posts = sorted(
            [path for path in self.posts_dir.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        templates = sorted(self.templates_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
        lines = [
            "# Post Generation Request",
            "",
            f"- created_at: {utc_now_iso()}",
            f"- topic: {topic}",
            "",
            "## Task",
            "",
            "Generate a medium-length Telegram HTML post for the topic above.",
            f"Use premium emoji through `<tg-emoji emoji-id=\"...\">fallback</tg-emoji>` tags from `{self._display_path(self.premium_emojis_md)}`.",
            "Use saved reference posts for style, but do not copy them blindly.",
            f"Save the final HTML draft into `{self._display_path(self.outbox_dir)}`.",
            "",
            "## Context",
            "",
            f"- active profile: {active_profile.get('name')} (`{profile_slug}`)",
            f"- profile root: `{self._display_path(self.profile_root(profile_slug))}`",
            f"- emoji catalog: `{self._display_path(self.premium_emojis_md)}`",
            f"- reference posts: {len(posts)}",
            f"- style/templates: {len(templates)}",
            "",
            "## Latest Reference Posts",
            "",
            markdown_list(f"`{self._display_path(path / 'index.md')}`" for path in posts[:10]),
            "",
            "## Latest Style Templates",
            "",
            markdown_list(f"`{self._display_path(path)}`" for path in templates[:10]),
            "",
        ]
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

    def render_emojis_markdown(self, slug: str | None = None) -> None:
        profile_slug = slug or self.active_profile_slug()
        profile_root = self.profile_root(profile_slug)
        state = self.load_state()
        profile = state.get("profiles", {}).get(profile_slug, {})
        profile_name = profile.get("name") or profile_slug
        data = self.load_emojis(profile_slug)
        emojis = sorted(data.get("emojis", {}).values(), key=lambda item: item.get("first_seen_at", ""))
        lines = [
            "# Premium Emojis",
            "",
            "This file is generated by the local Telegram collector bot.",
            "Labels are optional human hints. The source of truth is the custom emoji ID plus the downloaded asset file.",
            f"Profile: {profile_name} (`{profile_slug}`)",
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
                "Use the `HTML tag` values when drafting Telegram posts. Inspect downloaded files in this profile's `emoji-assets` directory when labels are missing or unclear.",
                f"Keep normal post text in HTML format and save the final draft in `{self._display_path(profile_root / 'outbox')}`.",
            ]
        )
        (profile_root / "premium-emojis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

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
        media_text = markdown_list(media_lines) if media_lines else "_Media files are intentionally not saved._"
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
            media_text,
            "",
            "## Entities",
            "",
            fenced_json(json.dumps(entities, ensure_ascii=False, indent=2)),
            "",
            "## Notes For AI Agents",
            "",
            "- Treat this as a reference post: keep the useful structure and tone, do not copy blindly.",
            f"- If premium emoji entities are present, prefer matching saved entries from `{self._display_path(self.premium_emojis_md)}`.",
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

    def _clear_profile_runtime(self, slug: str) -> None:
        profile_root = self.profile_root(slug)
        for path in (profile_root / "emojis.json", profile_root / "premium-emojis.md"):
            if path.exists():
                path.unlink()
        for directory in self._profile_directories(profile_root):
            self._clear_directory(directory)

    def _profile_directories(self, profile_root: Path) -> tuple[Path, ...]:
        return (
            profile_root / "emoji-assets",
            profile_root / "emoji-previews",
            profile_root / "templates",
            profile_root / "posts",
            profile_root / "outbox",
            profile_root / "raw",
            profile_root / "emoji-label-requests",
            profile_root / "post-requests",
        )

    def _ensure_gitkeep(self, directory: Path) -> None:
        gitkeep = directory / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("\n", encoding="utf-8")

    def _ensure_state_profiles(self, state: dict[str, Any]) -> bool:
        changed = False
        profiles = state.setdefault("profiles", {})
        if DEFAULT_PROFILE_SLUG not in profiles:
            profiles[DEFAULT_PROFILE_SLUG] = self._profile_record(DEFAULT_PROFILE_SLUG, DEFAULT_PROFILE_NAME)
            changed = True
        active = str(state.get("active_profile") or DEFAULT_PROFILE_SLUG)
        if active not in profiles:
            active = DEFAULT_PROFILE_SLUG
            changed = True
        if state.get("active_profile") != active:
            state["active_profile"] = active
            changed = True
        for key in ("owner", "sent_drafts", "failed_drafts", "user_modes"):
            if key not in state:
                state[key] = {}
                changed = True
        return changed

    def _profile_record(self, slug: str, name: str) -> dict[str, Any]:
        now = utc_now_iso()
        return {"slug": slug, "name": name, "created_at": now, "last_used_at": now}

    def _display_path(self, path: Path) -> str:
        rel = relative_to(path, self.root)
        prefix = self.root.name or "storage"
        if rel in {"", "."}:
            return prefix
        return f"{prefix}/{rel}"

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
        return {
            "updated_at": utc_now_iso(),
            "owner": {},
            "active_profile": DEFAULT_PROFILE_SLUG,
            "profiles": {DEFAULT_PROFILE_SLUG: self._profile_record(DEFAULT_PROFILE_SLUG, DEFAULT_PROFILE_NAME)},
            "sent_drafts": {},
            "failed_drafts": {},
            "user_modes": {},
        }

    def _draft_key(self, draft: Path) -> str:
        try:
            stat = draft.stat()
        except FileNotFoundError:
            return relative_to(draft, self.root)
        return f"{relative_to(draft, self.root)}:{stat.st_mtime_ns}:{stat.st_size}"


def _md_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")
