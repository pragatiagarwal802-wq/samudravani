"""ERA6 provider. ERA6 is not available, so this always reports NOT_AVAILABLE."""
from __future__ import annotations

from models.schemas import ProviderResult, ProviderStatus, RiskQuery
from providers.base import DataProvider


class Era6Provider(DataProvider):
    name = "era6"

    def fetch(self, query: RiskQuery) -> ProviderResult:
        return ProviderResult(
            provider=self.name,
            status=ProviderStatus.NOT_AVAILABLE,
            observations=[],
            message="ERA6 reanalysis data is not available; no values were generated.",
        )
