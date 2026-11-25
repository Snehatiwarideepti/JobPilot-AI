"""Provider package - exports the registry."""
from app.providers.base import (
    JobProvider,
    ProviderJobResult,
    ProviderSearchResult,
    ProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderNotFoundError,
    ProviderServerError,
    ProviderNetworkError,
)
from app.providers.jobvetta import JobvettaProvider

# Provider registry - add new providers here
PROVIDER_REGISTRY: dict[str, type[JobProvider]] = {
    "jobvetta": JobvettaProvider,
}


def get_provider(name: str = "jobvetta") -> JobProvider:
    """Factory function to get a configured provider instance."""
    provider_class = PROVIDER_REGISTRY.get(name)
    if not provider_class:
        raise ValueError(f"Unknown provider: '{name}'. Available: {list(PROVIDER_REGISTRY.keys())}")
    return provider_class()


__all__ = [
    "JobProvider", "ProviderJobResult", "ProviderSearchResult",
    "ProviderError", "ProviderAuthError", "ProviderRateLimitError",
    "ProviderNotFoundError", "ProviderServerError", "ProviderNetworkError",
    "JobvettaProvider", "PROVIDER_REGISTRY", "get_provider",
]
