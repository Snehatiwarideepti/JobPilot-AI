"""
Jobvetta API provider implementation.

Official API:
  Base URL:  https://api.jobvetta.com/v1
  Auth:      Authorization: Bearer <JOBVETTA_API_KEY>
  Search:    GET /v1/jobs  ?q=...&location=...&days=...&limit=...
  Detail:    GET /v1/jobs/<job_id>
  Rate limit: ~50 requests/day (free tier, shared limit, resets 00:00 UTC)

This module handles:
  - Authentication
  - Request construction
  - Response parsing
  - Error handling (200/400/401/403/404/429/5xx/network)
  - Response normalization to ProviderJobResult
  - Retry logic with exponential backoff for retryable errors
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.providers.base import (
    JobProvider,
    ProviderJobResult,
    ProviderSearchResult,
    ProviderAuthError,
    ProviderError,
    ProviderNetworkError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderServerError,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize_workplace_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return "unspecified"
    v = value.lower().replace("-", "_").replace(" ", "_")
    if "remote" in v:
        return "remote"
    if "hybrid" in v:
        return "hybrid"
    if any(k in v for k in ["on_site", "onsite", "office", "in_person"]):
        return "on_site"
    return "unspecified"


def _normalize_employment_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return "unspecified"
    v = value.lower()
    if "intern" in v:
        return "internship"
    if "full" in v:
        return "full_time"
    if "part" in v:
        return "part_time"
    if "contract" in v or "contractor" in v:
        return "contract"
    if "freelance" in v:
        return "freelance"
    return "unspecified"


def _normalize_experience_level(value: Optional[str]) -> Optional[str]:
    if not value:
        return "unspecified"
    v = value.lower()
    if "intern" in v:
        return "internship"
    if any(k in v for k in ["entry", "junior", "fresher", "graduate", "0-1", "0-2"]):
        return "entry"
    if any(k in v for k in ["mid", "intermediate", "2-5", "3-5"]):
        return "mid"
    if any(k in v for k in ["senior", "5+", "5-10", "experienced"]):
        return "senior"
    if any(k in v for k in ["lead", "principal", "staff"]):
        return "lead"
    if any(k in v for k in ["executive", "director", "vp", "c-level", "chief"]):
        return "executive"
    return "unspecified"


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _extract_skills_from_job(raw: Dict[str, Any]) -> List[str]:
    """
    Extract skills from various possible field names in the raw API response.
    Returns a deduplicated list of skill strings.
    """
    skills_set: set[str] = set()

    # Try common field names
    for field_name in ("skills", "skills_required", "required_skills", "tech_stack", "technologies", "tags", "keywords"):
        raw_skills = raw.get(field_name)
        if isinstance(raw_skills, list):
            for s in raw_skills:
                if isinstance(s, str) and s.strip():
                    skills_set.add(s.strip())
        elif isinstance(raw_skills, str) and raw_skills.strip():
            # Comma or pipe separated
            for s in raw_skills.replace("|", ",").split(","):
                if s.strip():
                    skills_set.add(s.strip())

    return sorted(skills_set)


def _normalize_raw_job(raw: Dict[str, Any], source: str) -> ProviderJobResult:
    """
    Convert a raw Jobvetta API job object into a ProviderJobResult.
    Uses only fields actually present in the API response.
    Does not invent missing values.
    """
    # Job ID - try common field names
    job_id = (
        _safe_str(raw.get("job_id"))
        or _safe_str(raw.get("id"))
        or _safe_str(raw.get("_id"))
    )
    if not job_id:
        raise ProviderError(f"Job record missing ID field: {list(raw.keys())}")

    title = _safe_str(raw.get("title") or raw.get("job_title"))
    company = _safe_str(raw.get("company") or raw.get("company_name") or raw.get("employer"))
    location = _safe_str(raw.get("location") or raw.get("job_location"))

    # Salary - try several possible fields
    salary_min = None
    salary_max = None
    salary_currency = None
    salary_period = None

    if raw.get("salary_min") is not None:
        try:
            salary_min = int(float(raw["salary_min"]))
        except (ValueError, TypeError):
            pass
    if raw.get("salary_max") is not None:
        try:
            salary_max = int(float(raw["salary_max"]))
        except (ValueError, TypeError):
            pass
    if raw.get("salary"):
        salary_raw = raw["salary"]
        if isinstance(salary_raw, dict):
            try:
                salary_min = int(float(salary_raw.get("min", salary_min or 0))) or None
                salary_max = int(float(salary_raw.get("max", salary_max or 0))) or None
                salary_currency = _safe_str(salary_raw.get("currency"))
                salary_period = _safe_str(salary_raw.get("period") or salary_raw.get("type"))
            except (ValueError, TypeError):
                pass

    salary_currency = salary_currency or _safe_str(raw.get("salary_currency") or raw.get("currency"))
    salary_period = salary_period or _safe_str(raw.get("salary_period"))

    # URLs
    source_url = _safe_str(
        raw.get("source_url")
        or raw.get("job_url")
        or raw.get("url")
        or raw.get("link")
    )
    application_url = _safe_str(
        raw.get("application_url")
        or raw.get("apply_url")
        or raw.get("apply_link")
        or raw.get("job_url")
    ) or source_url

    # Timestamps
    posted_at = _safe_str(
        raw.get("posted_at")
        or raw.get("date_posted")
        or raw.get("published_at")
        or raw.get("created_at")
    )

    # Employment details
    workplace_type = _normalize_workplace_type(
        raw.get("workplace_type") or raw.get("work_type") or raw.get("work_model") or raw.get("remote")
    )
    employment_type = _normalize_employment_type(
        raw.get("employment_type") or raw.get("job_type") or raw.get("type")
    )
    experience_level = _normalize_experience_level(
        raw.get("experience_level") or raw.get("experience") or raw.get("seniority")
    )
    if experience_level == "unspecified":
        min_years = raw.get("min_years_experience")
        if raw.get("no_experience_required") is True or min_years == 0:
            experience_level = "entry"
        elif isinstance(min_years, (int, float)):
            if min_years >= 8:
                experience_level = "lead"
            elif min_years >= 5:
                experience_level = "senior"
            elif min_years >= 2:
                experience_level = "mid"
            elif min_years > 0:
                experience_level = "entry"

    # Content
    description = _safe_str(raw.get("description") or raw.get("job_description") or raw.get("body"))
    responsibilities = _safe_str(raw.get("responsibilities") or raw.get("duties"))
    requirements = _safe_str(
        raw.get("requirements")
        or raw.get("qualifications")
        or raw.get("minimum_qualifications")
        or raw.get("preferred_qualifications")
        or raw.get("must_have")
    )
    benefits = _safe_str(raw.get("benefits") or raw.get("perks"))

    # Skills
    skills = _extract_skills_from_job(raw)

    # Location decomposition (best-effort)
    country = _safe_str(raw.get("country"))
    city = _safe_str(raw.get("city"))

    return ProviderJobResult(
        source=source,
        source_job_id=job_id,
        raw_data=raw,
        title=title,
        company=company,
        location=location,
        country=country,
        city=city,
        workplace_type=workplace_type,
        employment_type=employment_type,
        experience_level=experience_level,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_period=salary_period,
        description=description,
        responsibilities=responsibilities,
        requirements=requirements,
        benefits=benefits,
        skills=skills,
        application_url=application_url,
        source_url=source_url,
        posted_at=posted_at,
    )


# ---------------------------------------------------------------------------
# Jobvetta Provider
# ---------------------------------------------------------------------------

class JobvettaProvider(JobProvider):
    """
    Jobvetta API provider.
    Implements the JobProvider interface against https://api.jobvetta.com/v1
    """

    SOURCE_NAME = "jobvetta"
    BASE_URL = "https://api.jobvetta.com/v1"

    def __init__(self):
        self._api_key = settings.jobvetta_api_key
        self._timeout = settings.jobvetta_timeout
        self._max_retries = settings.jobvetta_max_retries

    @property
    def name(self) -> str:
        return self.SOURCE_NAME

    def _get_client(self) -> httpx.AsyncClient:
        if not self._api_key:
            raise ProviderAuthError(
                "JOBVETTA_API_KEY is not configured. "
                "Set it in your .env file.",
                status_code=None,
            )
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Raise the appropriate ProviderError for non-2xx responses."""
        code = response.status_code
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or body.get("detail") or str(body)
        except Exception:
            message = response.text or f"HTTP {code}"

        logger.warning("Jobvetta API error: HTTP %d - %s", code, message)

        if code in (401, 403):
            raise ProviderAuthError(
                f"Jobvetta authentication failed (HTTP {code}): {message}",
                status_code=code,
            )
        if code == 404:
            raise ProviderNotFoundError(
                f"Jobvetta: resource not found (HTTP 404): {message}",
                status_code=404,
            )
        if code == 429:
            err = ProviderRateLimitError(
                "Jobvetta rate limit reached. The free tier allows ~10 requests/day (UTC). "
                "Try again after 00:00 UTC."
            )
            err.retryable = False
            raise err
        if 500 <= code < 600:
            raise ProviderServerError(
                f"Jobvetta server error (HTTP {code}): {message}",
                status_code=code,
            )
        if 400 <= code < 500:
            raise ProviderError(
                f"Jobvetta request error (HTTP {code}): {message}",
                status_code=code,
            )
        raise ProviderError(f"Unexpected Jobvetta response (HTTP {code}): {message}", status_code=code)

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with exponential backoff retry for retryable errors.
        """
        attempt = 0
        last_error: Optional[Exception] = None

        while attempt <= self._max_retries:
            try:
                async with self._get_client() as client:
                    logger.debug("Jobvetta request: %s %s params=%s (attempt %d)", method, path, params, attempt + 1)
                    response = await client.request(method, path, params=params)

                    if response.status_code == 200:
                        try:
                            return response.json()
                        except Exception as e:
                            raise ProviderError(f"Jobvetta returned malformed JSON: {e}")

                    # This raises the appropriate ProviderError
                    self._handle_error_response(response)

            except (ProviderRateLimitError, ProviderServerError, ProviderNetworkError) as e:
                last_error = e
                attempt += 1
                if attempt <= self._max_retries and e.retryable:
                    wait = 2 ** attempt  # 2, 4, 8 seconds
                    logger.warning("Retryable Jobvetta error; waiting %ds before retry %d/%d", wait, attempt, self._max_retries)
                    await asyncio.sleep(wait)
                else:
                    raise

            except httpx.TimeoutException as e:
                last_error = ProviderNetworkError(f"Jobvetta request timed out: {e}")
                attempt += 1
                if attempt <= self._max_retries:
                    wait = 2 ** attempt
                    logger.warning("Jobvetta timeout; waiting %ds before retry", wait)
                    await asyncio.sleep(wait)
                else:
                    raise ProviderNetworkError(str(e)) from e

            except httpx.ConnectError as e:
                raise ProviderNetworkError(f"Cannot connect to Jobvetta API: {e}") from e

            except (ProviderAuthError, ProviderNotFoundError, ProviderError):
                # Non-retryable
                raise

        raise last_error or ProviderError("Jobvetta request failed after all retries")

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
        Search Jobvetta for jobs.
        Returns a ProviderSearchResult with normalized job records.
        """
        params: Dict[str, Any] = {"q": query}

        if location:
            params["location"] = location
        if days is not None:
            params["days"] = days
        if limit:
            params["limit"] = min(limit, 100)

        # Jobvetta may not support all filter params; include what's available
        # We'll filter workplace/employment/experience locally after retrieval
        # if the API doesn't support them.

        logger.info("Jobvetta search: query=%r location=%r days=%s limit=%s", query, location, days, limit)

        raw = await self._request_with_retry("GET", "/jobs", params=params)

        # Parse response
        # Expected shape: {"total": int, "jobs": [...]}
        # But we handle variations.
        if not isinstance(raw, dict):
            raise ProviderError(f"Jobvetta search returned unexpected type: {type(raw)}")

        jobs_raw = raw.get("jobs") or raw.get("results") or raw.get("data") or []
        if not isinstance(jobs_raw, list):
            # Maybe the response IS the list
            if isinstance(raw, list):
                jobs_raw = raw
            else:
                logger.warning("Jobvetta search: no 'jobs' key in response. Keys: %s", list(raw.keys()))
                jobs_raw = []

        total = raw.get("total") or raw.get("count") or len(jobs_raw)

        normalized_jobs: List[ProviderJobResult] = []
        for item in jobs_raw:
            if not isinstance(item, dict):
                logger.warning("Jobvetta: skipping non-dict job item: %s", type(item))
                continue
            try:
                job = _normalize_raw_job(item, self.SOURCE_NAME)
                normalized_jobs.append(job)
            except ProviderError as e:
                logger.warning("Jobvetta: skipping malformed job: %s", e)
                continue

        logger.info("Jobvetta search: total=%s returned=%d", total, len(normalized_jobs))

        return ProviderSearchResult(
            total=int(total),
            page=page,
            limit=limit,
            jobs=normalized_jobs,
            has_more=len(normalized_jobs) == limit,
            provider=self.SOURCE_NAME,
        )

    async def get_job(self, job_id: str) -> ProviderJobResult:
        """Fetch a single job by its Jobvetta job_id."""
        logger.info("Jobvetta: fetching job_id=%s", job_id)
        raw = await self._request_with_retry("GET", f"/jobs/{job_id}")

        if isinstance(raw, dict):
            # The response might be wrapped
            job_data = raw.get("job") or raw
            if isinstance(job_data, dict) and not (job_data.get("job_id") or job_data.get("id") or job_data.get("_id")):
                job_data["job_id"] = job_id
            return _normalize_raw_job(job_data, self.SOURCE_NAME)

        raise ProviderError(f"Jobvetta: unexpected response format for job {job_id}")

    async def check_health(self) -> Dict[str, Any]:
        """
        Perform a minimal API request to verify the key and connectivity.
        Uses a low-limit search query to avoid burning quota.
        """
        try:
            result = await self.search_jobs(query="software engineer", limit=1, days=30)
            return {
                "status": "ok",
                "provider": self.SOURCE_NAME,
                "message": f"Connected. Received {result.total} total results for health-check query.",
            }
        except ProviderAuthError as e:
            return {"status": "error", "provider": self.SOURCE_NAME, "message": f"Authentication failed: {e}"}
        except ProviderRateLimitError:
            return {"status": "rate_limited", "provider": self.SOURCE_NAME, "message": "Rate limit reached."}
        except ProviderNetworkError as e:
            return {"status": "error", "provider": self.SOURCE_NAME, "message": f"Network error: {e}"}
        except Exception as e:
            return {"status": "error", "provider": self.SOURCE_NAME, "message": str(e)}
