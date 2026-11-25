"""
Idempotent live job ingestion script.
Queries Jobvetta for configured target roles, normalizes, deduplicates,
upserts into PostgreSQL, generates/updates embeddings, and marks stale jobs inactive.

Usage:
    python scripts/refresh_live_jobs.py
    python scripts/refresh_live_jobs.py --queries "python developer,machine learning" --limit 25
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add backend root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.database import AsyncSessionLocal, init_db
from app.providers import get_provider, ProviderError, ProviderRateLimitError, ProviderAuthError
from app.services.ingestion import upsert_job, generate_and_store_embedding, mark_stale_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("refresh_live_jobs")

DEFAULT_QUERIES = [
    "python developer",
    "machine learning",
    "data science",
    "software engineer",
    "backend engineer",
]


async def refresh_jobs(
    queries: list[str],
    location: str | None = None,
    days: int = 30,
    limit: int = 20,
    mark_stale: bool = False,
) -> dict:
    """
    Execute an idempotent ingestion run against Jobvetta.
    Returns summary statistics.
    """
    settings = get_settings()
    if not settings.jobvetta_api_key or settings.jobvetta_api_key == "your_jobvetta_api_key_here":
        logger.error("JOBVETTA_API_KEY is not configured. Set a valid key in .env.")
        return {"status": "error", "reason": "missing_api_key"}

    await init_db()
    provider = get_provider("jobvetta")

    total_fetched = 0
    created_count = 0
    updated_count = 0
    embedded_count = 0
    seen_source_ids: set[str] = set()
    errors: list[str] = []

    async with AsyncSessionLocal() as db:
        for idx, query in enumerate(queries):
            logger.info("[%d/%d] Querying Jobvetta for %r (location=%r, days=%d, limit=%d)",
                        idx + 1, len(queries), query, location, days, limit)
            try:
                result = await provider.search_jobs(
                    query=query,
                    location=location,
                    days=days,
                    limit=limit,
                )
            except ProviderAuthError as e:
                logger.error("Authentication failed: %s", e)
                errors.append(str(e))
                break
            except ProviderRateLimitError as e:
                logger.warning("Rate limit reached: %s. Stopping early to preserve quota.", e)
                errors.append(str(e))
                break
            except ProviderError as e:
                logger.error("Provider error for query %r: %s", query, e)
                errors.append(f"{query}: {e}")
                continue

            total_fetched += len(result.jobs)

            for job_result in result.jobs:
                seen_source_ids.add(job_result.source_job_id)
                job, created = await upsert_job(db, job_result)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

                try:
                    await generate_and_store_embedding(db, job)
                    embedded_count += 1
                except Exception as e:
                    logger.warning("Embedding failed for job %s: %s", job.source_job_id, e)

            await db.commit()

            # Respect rate limits between queries
            if idx < len(queries) - 1:
                await asyncio.sleep(1.5)

        stale_count = 0
        if mark_stale and seen_source_ids:
            stale_count = await mark_stale_jobs(db, "jobvetta", list(seen_source_ids))
            await db.commit()

    summary = {
        "status": "ok" if not errors else "partial",
        "queries_run": len(queries),
        "total_fetched": total_fetched,
        "unique_jobs": len(seen_source_ids),
        "created": created_count,
        "updated": updated_count,
        "embedded": embedded_count,
        "marked_stale": stale_count,
        "errors": errors,
    }
    logger.info("Ingestion summary: %s", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Refresh live jobs from Jobvetta")
    parser.add_argument(
        "--queries",
        type=str,
        default=",".join(DEFAULT_QUERIES),
        help="Comma-separated search queries",
    )
    parser.add_argument("--location", type=str, default=None, help="Location filter")
    parser.add_argument("--days", type=int, default=30, help="Freshness window in days")
    parser.add_argument("--limit", type=int, default=20, help="Max jobs per query")
    parser.add_argument("--mark-stale", action="store_true", help="Mark unseen jobs inactive")
    args = parser.parse_args()

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    summary = asyncio.run(
        refresh_jobs(
            queries=queries,
            location=args.location,
            days=args.days,
            limit=args.limit,
            mark_stale=args.mark_stale,
        )
    )
    if summary.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
