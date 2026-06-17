from __future__ import annotations

import json
import logging
import os
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
    svg_preview_path: Path | None = None


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
    if info.svg_preview_path:
        record["svg_preview_path"] = relative_to(info.svg_preview_path, storage_root)
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
    raster_format = _tgs_preview_format()
    svg_preview = previews_dir / f"{asset_path.stem}.svg"
    raster_preview = previews_dir / f"{asset_path.stem}.{raster_format}"
    script = Path(__file__).resolve().parents[2] / "scripts" / "render_lottie_preview.cjs"
    if script.exists():
        if _needs_refresh(asset_path, raster_preview) or _needs_refresh(asset_path, svg_preview):
            try:
                result = subprocess.run(
                    [
                        "node",
                        str(script),
                        str(asset_path),
                        str(svg_preview),
                        str(raster_preview),
                        raster_format,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                payload = json.loads(result.stdout or "{}")
                return EmojiAssetInfo(
                    asset_type="animated_tgs",
                    asset_type_label=f"animated TGS/Lottie -> SVG -> {raster_format.upper()}",
                    preview_path=raster_preview,
                    preview_type=f"{raster_format}_from_lottie_svg",
                    preview_frame=int(payload["frame"]) if "frame" in payload else None,
                    svg_preview_path=svg_preview,
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Could not convert TGS via lottie-to-svg for %s: %s", asset_path, exc)
        elif raster_preview.exists() and raster_preview.stat().st_size > 0:
            return EmojiAssetInfo(
                asset_type="animated_tgs",
                asset_type_label=f"animated TGS/Lottie -> SVG -> {raster_format.upper()}",
                preview_path=raster_preview,
                preview_type=f"{raster_format}_from_lottie_svg",
                svg_preview_path=svg_preview if svg_preview.exists() else None,
            )

    html_preview = previews_dir / f"{asset_path.stem}.html"
    try:
        from lottie.exporters import export_embedded_html
        from lottie.importers.core import import_tgs

        animation = import_tgs(str(asset_path))
        if _needs_refresh(asset_path, html_preview):
            with html_preview.open("w", encoding="utf-8") as file:
                export_embedded_html(animation, file)
            _force_lottie_svg_renderer(html_preview)
    except Exception as exc:  # noqa: BLE001
        if html_preview.exists() and html_preview.stat().st_size > 0:
            return EmojiAssetInfo(
                asset_type="animated_tgs",
                asset_type_label="animated TGS/Lottie (HTML SVG renderer)",
                preview_path=html_preview,
                preview_type="html_lottie_svg",
            )
        LOGGER.warning("Could not convert TGS preview for %s: %s", asset_path, exc)
        return EmojiAssetInfo(asset_type="animated_tgs", asset_type_label="animated TGS/Lottie")
    return EmojiAssetInfo(
        asset_type="animated_tgs",
        asset_type_label="animated TGS/Lottie (HTML SVG renderer)",
        preview_path=html_preview,
        preview_type="html_lottie_svg",
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


def _tgs_preview_format() -> str:
    value = os.getenv("EMOJI_PREVIEW_FORMAT", "png").strip().lower()
    return value if value in {"png", "webp"} else "png"


def _force_lottie_svg_renderer(html_path: Path) -> None:
    text = html_path.read_text(encoding="utf-8")
    replacements = {
        "renderer:'canvas'": "renderer:'svg'",
        'renderer:"canvas"': 'renderer:"svg"',
        "renderer: 'canvas'": "renderer: 'svg'",
        'renderer: "canvas"': 'renderer: "svg"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    html_path.write_text(text, encoding="utf-8")
