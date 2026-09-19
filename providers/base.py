"""Abstract data-provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from models.schemas import ProviderResult, RiskQuery


class DataProvider(ABC):
    """A source of ocean/atmosphere observations.

    Implementations must never fabricate data: if the source cannot serve the
    query they return a ProviderResult with status NOT_AVAILABLE or ERROR.
    """

    name: str

    def health(self) -> dict:
        """Local configuration check only (no network call): {'configured': bool, 'detail': str}."""
        return {"configured": True, "detail": ""}

    @abstractmethod
    def fetch(self, query: RiskQuery) -> ProviderResult:
        """Return observations for the query, or a non-OK status."""
