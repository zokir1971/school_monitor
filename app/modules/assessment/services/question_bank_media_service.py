"""Общий media/storage слой Question Bank; постоянные ключи вместо URL S3."""
from __future__ import annotations

import asyncio
import re
import warnings
from io import BytesIO
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from app.core.storage.base import BaseStorage

MEDIA_KEY_PATTERN = re.compile(r"question-bank/media/[1-9][0-9]*/[0-9a-f]{32}\.(?:png|jpg|webp)")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000


def validate_media_segment(segment: dict) -> None:
    key = segment.get("object_key")
    if not isinstance(key, str) or not MEDIA_KEY_PATTERN.fullmatch(key):
        raise ValueError("Суреттің сақтау кілті қате.")
    alt = segment.get("alt", "")
    if not isinstance(alt, str) or len(alt) > 500:
        raise ValueError("Сурет сипаттамасы 500 таңбадан аспауы керек.")


class QuestionBankMediaService:
    def __init__(self, storage: BaseStorage):
        self.storage = storage

    @staticmethod
    def _normalize_image(content: bytes) -> tuple[bytes, str, str]:
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ValueError("Сурет бос немесе көлемі 5 МБ-тан асады.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP"}:
                        raise ValueError("PNG, JPEG немесе WebP суретін таңдаңыз.")
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ValueError("Сурет өлшемі 16 мегапиксельден аспауы керек.")
                    if getattr(image, "is_animated", False):
                        raise ValueError("Қозғалмайтын суретті таңдаңыз.")
                    image.load()
                    fmt = image.format
                    output = BytesIO()
                    image.convert("RGB" if fmt == "JPEG" else "RGBA").save(output, format=fmt)
                    normalized = output.getvalue()
                    if len(normalized) > MAX_IMAGE_BYTES:
                        raise ValueError("Суреттің көлемі 5 МБ-тан асады.")
                    ext, mime = {
                        "PNG": (
                            "png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "WEBP": ("webp", "image/webp")}[fmt]
                    return normalized, ext, mime
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("Сурет файлын оқу мүмкін болмады.") from exc

    async def upload(self, *, content: bytes, user_id: int) -> dict:
        normalized, ext, mime = await asyncio.to_thread(self._normalize_image, content)
        key = f"question-bank/media/{user_id}/{uuid4().hex}.{ext}"
        await self.storage.save(content=normalized, object_key=key, content_type=mime)
        return {"type": "image", "object_key": key, "alt": ""}

    async def validate_references(self, segments: list[dict], *, user_id: int) -> None:
        for segment in segments:
            if segment.get("type") == "image":
                validate_media_segment(segment)
                key = segment["object_key"]
                if not key.startswith(f"question-bank/media/{user_id}/"):
                    raise ValueError("Өз жүктеген суретіңізді таңдаңыз.")
                if not await self.storage.exists(object_key=key):
                    raise ValueError("Сурет файлы табылмады.")

    async def validate_option_references(self, options: list[dict], *, user_id: int) -> None:
        if not isinstance(options, list) or any(not isinstance(option, dict) for option in options):
            raise ValueError("Сурет нұсқаларының пішімі қате.")
        await self.validate_references(
            [{**option, "type": "image"} for option in options], user_id=user_id,
        )
