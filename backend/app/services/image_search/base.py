"""Abstract base for image search providers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ImageResult:
    source: str
    source_url: str
    thumbnail_url: str = ""
    width: int = 0
    height: int = 0
    title: str = ""
    has_transparency: bool = False


class ImageSearchProvider(ABC):
    name: str = ""

    @property
    @abstractmethod
    def enabled(self) -> bool: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10, country: str | None = None) -> list[ImageResult]: ...

    async def safe_search(
        self, query: str, limit: int = 10, country: str | None = None
    ) -> list[ImageResult]:
        if not self.enabled:
            return []
        try:
            results = await self.search(query, limit, country)
            logger.info(f"[{self.name}] {len(results)} results for {query!r} (country={country})")
            return results
        except Exception as e:
            logger.warning(f"[{self.name}] failed for {query!r}: {e}")
            return []
