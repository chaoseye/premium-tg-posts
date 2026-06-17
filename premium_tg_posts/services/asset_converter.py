from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from premium_tg_posts.utils.text import relative_to

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmojiAssetInfo:
    asset_type: str
    asset_type_label: str
    preview_path: Path | None = None
    preview_type: str | None = None
    preview_frame: int | None = None


def prepare_emoji_asset(asset_path: Path, previews_dir: Path, storage_root: Path) -> dict[str, str | int]:
    info = convert_emoji_asset(asset_path, previews_dir)
    record: dict[str, str | int] = {
        "asset_type": info.asset_type,
        "asset_type_label": info.asset_type_label,
    }
    if info.preview_path:
        record["preview_path"] = relative_to(info.preview_path, storage_root)
    if info.preview_type:
        record["preview_type"] = info.preview_type
    if info.preview_frame is not None:
        record["preview_frame"] = info.preview_frame
    return record


def convert_emoji_asset(asset_path: Path, previews_dir: Path) -> EmojiAssetInfo:
    previews_dir.mkdir(parents=True, exist_ok=True)
    suffix = asset_path.suffix.lower()
    if suffix == ".tgs":
        return _convert_tgs(asset_path, previews_dir)
    if suffix == ".webm":
        return _convert_webm(asset_path, previews_dir)
    if suffix == ".webp":
        return _convert_webp(asset_path, previews_dir)
    return EmojiAssetInfo(asset_type="unknown", asset_type_label=f"unknown {suffix or 'file'}")


def _convert_tgs(asset_path: Path, previews_dir: Path) -> EmojiAssetInfo:
    preview = previews_dir / f"{asset_path.stem}.svg"
    html_preview = previews_dir / f"{asset_path.stem}.html"
    frame = 0
    try:
        from lottie.exporters import export_embedded_html, export_svg
        from lottie.importers.core import import_tgs

        animation = import_tgs(str(asset_path))
        frame = int((float(animation.in_point) + float(animation.out_point)) / 2)
        if _needs_refresh(asset_path, preview):
            last_error: Exception | None = None
            candidate_frames = [frame, int(animation.in_point), 1, max(int(animation.out_point) - 1, 0)]
            for candidate in dict.fromkeys(candidate_frames):
                try:
                    with preview.open("w", encoding="utf-8") as file:
                        export_svg(animation, file, frame=candidate)
                    if preview.exists() and preview.stat().st_size > 0:
                        frame = candidate
                        last_error = None
                        break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            if last_error:
                if preview.exists() and preview.stat().st_size == 0:
                    preview.unlink()
                if _needs_refresh(asset_path, html_preview):
                    with html_preview.open("w", encoding="utf-8") as file:
                        export_embedded_html(animation, file)
                return EmojiAssetInfo(
                    asset_type="animated_tgs",
                    asset_type_label="animated TGS/Lottie",
                    preview_path=html_preview,
                    preview_type="html_lottie_animation",
                    preview_frame=frame,
                )
    except Exception as exc:  # noqa: BLE001
        if preview.exists() and preview.stat().st_size == 0:
            preview.unlink()
        if preview.exists() and preview.stat().st_size > 0:
            return EmojiAssetInfo(
                asset_type="animated_tgs",
                asset_type_label="animated TGS/Lottie",
                preview_path=preview,
                preview_type="svg_frame",
                preview_frame=frame,
            )
        if html_preview.exists() and html_preview.stat().st_size > 0:
            return EmojiAssetInfo(
                asset_type="animated_tgs",
                asset_type_label="animated TGS/Lottie",
                preview_path=html_preview,
                preview_type="html_lottie_animation",
                preview_frame=frame,
            )
        LOGGER.warning("Could not convert TGS preview for %s: %s", asset_path, exc)
        return EmojiAssetInfo(asset_type="animated_tgs", asset_type_label="animated TGS/Lottie")
    return EmojiAssetInfo(
        asset_type="animated_tgs",
        asset_type_label="animated TGS/Lottie",
        preview_path=preview,
        preview_type="svg_mid_frame",
        preview_frame=frame,
    )


def _convert_webm(asset_path: Path, previews_dir: Path) -> EmojiAssetInfo:
    preview = previews_dir / f"{asset_path.stem}.jpg"
    if _needs_refresh(asset_path, preview):
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(asset_path),
                    "-frames:v",
                    "1",
                    str(preview),
                ],
                check=True,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not convert WEBM preview for %s: %s", asset_path, exc)
            return EmojiAssetInfo(asset_type="video_webm", asset_type_label="video WEBM animation")
    return EmojiAssetInfo(
        asset_type="video_webm",
        asset_type_label="video WEBM animation",
        preview_path=preview,
        preview_type="jpg_first_frame",
    )


def _convert_webp(asset_path: Path, previews_dir: Path) -> EmojiAssetInfo:
    preview = previews_dir / f"{asset_path.stem}.png"
    if _needs_refresh(asset_path, preview):
        try:
            with Image.open(asset_path) as image:
                image.save(preview)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not convert WEBP preview for %s: %s", asset_path, exc)
            return EmojiAssetInfo(asset_type="static_webp", asset_type_label="static WEBP image")
    return EmojiAssetInfo(
        asset_type="static_webp",
        asset_type_label="static WEBP image",
        preview_path=preview,
        preview_type="png_static",
    )


def _needs_refresh(source: Path, target: Path) -> bool:
    return not target.exists() or target.stat().st_mtime < source.stat().st_mtime or target.stat().st_size == 0
