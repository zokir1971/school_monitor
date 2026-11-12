"""Provider-independent immutable text translation contract."""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class TranslationField:
    key: str
    text: str
    allow_empty: bool = False

@dataclass(frozen=True)
class TranslationRequest:
    fields: tuple[TranslationField, ...]
    language: str
    context: Any = None
