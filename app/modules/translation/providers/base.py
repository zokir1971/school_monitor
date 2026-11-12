from typing import Protocol
from app.modules.translation.schemas import TranslationRequest

class TranslationProvider(Protocol):
    async def translate(self, request: TranslationRequest) -> dict[str, str]: ...
