"""
Provider abstraction layer.
All job providers must implement the JobProvider interface.
This makes it possible to add new providers without changing application logic.
"""
from __future__ import annotations
import abc
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProviderJobResult:
    """
    Raw job result from a provider, before normalization.
    Contains the original API response alongside extracted fields.
    """
    source: str
    source_job_id: str
    raw_data: Dict[str, Any] = field(default_factory=dict)

    # Extracted fields (may be None if provider doesn't supply them)
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    workplace_type: Optional[str] = None      # "remote" | "hybrid" | "on_site" | "unspecified"
    employment_type: Optional[str] = None     # "full_time" | "part_time" | "contract" | "internship" | "freelance"
    experience_level: Optional[str] = None   # "internship" | "entry" | "mid" | "senior" | "lead" | "executive"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    description: Optional[str] = None
    responsibilities: Optional[str] = None
    requirements: Optional[str] = None
    benefits: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    application_url: Optional[str] = None
    source_url: Optional[str] = None
    posted_at: Optional[str] = None           # ISO 8601 string; parsed downstream


@dataclass
class ProviderSearchResult:
    """Container for a search response from a provider."""
    total: int
    page: int
    limit: int
    jobs: List[ProviderJobResult] = field(default_factory=list)
    has_more: bool = False
    provider: str = ""


class ProviderError(Exception):
    """Base class for provider errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class ProviderAuthError(ProviderError):
    """Raised for 401/403 responses."""
    pass


class ProviderRateLimitError(ProviderError):
    """Raised for 429 responses."""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, status_code=429, retryable=True)


class ProviderNotFoundError(ProviderError):
    """Raised for 404 responses."""
    pass


class ProviderServerError(ProviderError):
    """Raised for 5xx responses."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message, status_code=status_code, retryable=True)


class ProviderNetworkError(ProviderError):
    """Raised for network/connection failures."""
    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class JobProvider(abc.ABC):
    """
    Abstract base class for job providers.
    Implement this interface to add a new provider.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name, e.g. 'jobvetta'."""
        ...

    @abc.abstractmethod
    async def search_jobs(
        self,
        query: str,
        location: Optional[str] = None,
        workplace_type: Optional[str] = None,
        employment_type: Optional[str] = None,
        experience_level: Optional[str] = None,
        days: Optional[int] = None,
        page: int = 1,
        limit: int = 20,
    ) -> ProviderSearchResult:
        """
        Search for jobs.
        Must return a ProviderSearchResult.
        Must raise ProviderError subclasses (never return fake data on failure).
        """
        ...

    @abc.abstractmethod
    async def get_job(self, job_id: str) -> ProviderJobResult:
        """
        Fetch details for a single job by provider-side job_id.
        Raises ProviderNotFoundError if the job no longer exists.
        """
        ...

    @abc.abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """
        Check if the provider API is accessible.
        Returns a dict with at least {"status": "ok"|"error", "message": str}.
        """
        ...
