"""
Jobvetta Enrichment Script.

Enriches the existing jobs stored in PostgreSQL via Jobvetta detail endpoint.
Requirements:
1. Enrich existing 8 jobs already stored in PostgreSQL.
2. Do not search for or ingest additional jobs.
3. Do not make unnecessary API requests.
4. Fetch each job's detail endpoint only once if needed.
5. Commit each successfully enriched job independently.
6. Do not fabricate fields.
7. Preserve existing non-empty DB values if provider returns empty/None/unspecified.
8. If HTTP 429 occurs, STOP immediately and report it. Do not retry.
9. Do not reset or delete PostgreSQL DB/volume.
10. Do not make any OpenAI API calls.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

# Add backend root to sys.path
backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

# Hard-block OpenAI API calls
os.environ["OPENAI_API_KEY"] = ""

from sqlalchemy import select, func, text
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import Job, JobEmbedding, JobSkill
from app.providers import get_provider
from app.providers.base import ProviderError, ProviderRateLimitError, ProviderJobResult
from app.services.ingestion import upsert_job, _is_empty_value

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("enrich_jobs")


def _field_changed_and_enriched(before_val: Any, after_val: Any) -> bool:
    """Check if after_val added new information compared to before_val."""
    if _is_empty_value(after_val) or after_val == "unspecified":
        return False
    if _is_empty_value(before_val) or before_val == "unspecified":
        return True
    if isinstance(before_val, list) and isinstance(after_val, list):
        return set(after_val) != set(before_val) and len(after_val) > 0
    return str(before_val).strip() != str(after_val).strip()


async def enrich_jobs():
    settings = get_settings()
    logger.info("Initializing Jobvetta provider...")
    provider = get_provider("jobvetta")

    # Step 1: Query existing jobs
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Job).order_by(Job.created_at.asc()))
        existing_jobs = result.scalars().all()

    total_existing = len(existing_jobs)
    logger.info(f"Found {total_existing} existing jobs in PostgreSQL database.")

    if total_existing == 0:
        logger.error("No existing jobs found in database to enrich!")
        return

    # Print baseline status of the jobs
    print("\n" + "=" * 80)
    print(f"BASELINE: {total_existing} JOBS IN DATABASE BEFORE ENRICHMENT")
    print("=" * 80)
    for idx, j in enumerate(existing_jobs, 1):
        desc_len = len(j.description) if j.description else 0
        skills_cnt = len(j.skills) if j.skills else 0
        print(f"[{idx}/{total_existing}] ID: {j.id} | SourceID: {j.source_job_id}")
        print(f"       Title: {j.title} | Company: {j.company}")
        print(f"       DescLen: {desc_len} | Skills: {skills_cnt} | Exp: {j.experience_level} | AppURL: {bool(j.application_url)}")

    enrichment_reports: List[Dict[str, Any]] = []
    fetched_job_ids: Set[str] = set()
    rate_limited = False

    # Step 2: Enrich each job independently
    print("\n" + "=" * 80)
    print("PERFORMING JOBVETTA DETAIL ENRICHMENT")
    print("=" * 80)

    for idx, j_orig in enumerate(existing_jobs, 1):
        job_id = j_orig.id
        source_job_id = j_orig.source_job_id
        source = j_orig.source

        report = {
            "index": idx,
            "id": str(job_id),
            "source_job_id": source_job_id,
            "title": j_orig.title,
            "company": j_orig.company,
            "status": "pending",
            "enriched_fields": [],
            "error": None,
        }

        if source != "jobvetta":
            logger.info(f"Skipping job {source_job_id}: source is {source}, not jobvetta")
            report["status"] = "skipped"
            report["error"] = f"Unsupported source: {source}"
            enrichment_reports.append(report)
            continue

        if not source_job_id:
            logger.warning(f"Job {job_id} has empty source_job_id; skipping detail fetch.")
            report["status"] = "skipped"
            report["error"] = "Empty source_job_id"
            enrichment_reports.append(report)
            continue

        if source_job_id in fetched_job_ids:
            logger.info(f"Detail for {source_job_id} already fetched; skipping duplicate request.")
            report["status"] = "skipped_duplicate"
            enrichment_reports.append(report)
            continue

        fetched_job_ids.add(source_job_id)

        # Snapshot before values
        before_state = {
            "title": j_orig.title,
            "company": j_orig.company,
            "description": j_orig.description,
            "responsibilities": j_orig.responsibilities,
            "requirements": j_orig.requirements,
            "benefits": j_orig.benefits,
            "skills": list(j_orig.skills or []),
            "experience_level": j_orig.experience_level,
            "workplace_type": j_orig.workplace_type,
            "employment_type": j_orig.employment_type,
            "salary_min": j_orig.salary_min,
            "salary_max": j_orig.salary_max,
            "salary_currency": j_orig.salary_currency,
            "salary_period": j_orig.salary_period,
            "application_url": j_orig.application_url,
            "source_url": j_orig.source_url,
            "location": j_orig.location,
            "country": j_orig.country,
            "city": j_orig.city,
        }

        logger.info(f"[{idx}/{total_existing}] Fetching Jobvetta detail for job_id={source_job_id} ({j_orig.title})...")

        detail_result: ProviderJobResult | None = None
        try:
            detail_result = await provider.get_job(source_job_id)
        except ProviderRateLimitError as e:
            logger.critical(f"HTTP 429 RATE LIMIT ENCOUNTERED: {e}. STOPPING IMMEDIATELY AS REQUIRED.")
            report["status"] = "rate_limited"
            report["error"] = str(e)
            enrichment_reports.append(report)
            rate_limited = True
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                logger.critical(f"HTTP 429 RATE LIMIT DETECTED in error: {e}. STOPPING IMMEDIATELY AS REQUIRED.")
                report["status"] = "rate_limited"
                report["error"] = str(e)
                enrichment_reports.append(report)
                rate_limited = True
                break
            logger.error(f"Failed to fetch detail for job {source_job_id}: {e}")
            report["status"] = "fetch_failed"
            report["error"] = str(e)
            enrichment_reports.append(report)
            continue

        # Commit each successfully enriched job independently
        async with AsyncSessionLocal() as session:
            try:
                updated_job, _ = await upsert_job(session, detail_result)
                await session.commit()
                # Refresh to get state from DB
                await session.refresh(updated_job)

                after_state = {
                    "title": updated_job.title,
                    "company": updated_job.company,
                    "description": updated_job.description,
                    "responsibilities": updated_job.responsibilities,
                    "requirements": updated_job.requirements,
                    "benefits": updated_job.benefits,
                    "skills": list(updated_job.skills or []),
                    "experience_level": updated_job.experience_level,
                    "workplace_type": updated_job.workplace_type,
                    "employment_type": updated_job.employment_type,
                    "salary_min": updated_job.salary_min,
                    "salary_max": updated_job.salary_max,
                    "salary_currency": updated_job.salary_currency,
                    "salary_period": updated_job.salary_period,
                    "application_url": updated_job.application_url,
                    "source_url": updated_job.source_url,
                    "location": updated_job.location,
                    "country": updated_job.country,
                    "city": updated_job.city,
                }

                # Determine enriched fields
                enriched = []
                for field_name, before_val in before_state.items():
                    after_val = after_state[field_name]
                    if _field_changed_and_enriched(before_val, after_val):
                        enriched.append(field_name)

                report["status"] = "enriched" if enriched else "unchanged"
                report["enriched_fields"] = enriched
                report["desc_length"] = len(updated_job.description) if updated_job.description else 0
                report["skills_count"] = len(updated_job.skills) if updated_job.skills else 0
                report["experience_level"] = updated_job.experience_level
                report["application_url"] = updated_job.application_url
                logger.info(f"[{idx}/{total_existing}] Job {source_job_id} successfully committed. Enriched fields: {enriched}")

            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to commit enrichment for job {source_job_id}: {e}")
                report["status"] = "commit_failed"
                report["error"] = str(e)

        enrichment_reports.append(report)

        # Brief delay to respect rate limit
        await asyncio.sleep(1.0)

    # Step 3: SQL Verification Queries
    print("\n" + "=" * 80)
    print("SQL VERIFICATION AFTER ENRICHMENT")
    print("=" * 80)

    async with AsyncSessionLocal() as session:
        # Total jobs
        res_total = await session.execute(text("SELECT COUNT(*) FROM jobs;"))
        total_jobs_sql = res_total.scalar()

        # Jobs with non-empty descriptions
        res_desc = await session.execute(text(
            "SELECT COUNT(*) FROM jobs WHERE description IS NOT NULL AND TRIM(description) != '';"
        ))
        non_empty_desc_sql = res_desc.scalar()

        # Jobs with non-empty skills
        res_skills = await session.execute(text(
            """
            SELECT COUNT(*) FROM jobs
            WHERE skills IS NOT NULL
              AND jsonb_typeof(skills) = 'array'
              AND jsonb_array_length(skills) > 0;
            """
        ))
        non_empty_skills_sql = res_skills.scalar()

        # Jobs with known experience levels
        res_exp = await session.execute(text(
            """
            SELECT COUNT(*) FROM jobs
            WHERE experience_level IS NOT NULL
              AND experience_level != 'unspecified'
              AND TRIM(experience_level) != '';
            """
        ))
        known_exp_sql = res_exp.scalar()

        # Jobs with valid application URLs
        res_url = await session.execute(text(
            """
            SELECT COUNT(*) FROM jobs
            WHERE application_url IS NOT NULL
              AND TRIM(application_url) != ''
              AND (application_url LIKE 'http://%' OR application_url LIKE 'https://%');
            """
        ))
        valid_url_sql = res_url.scalar()

        # Job embeddings count
        res_emb = await session.execute(text("SELECT COUNT(*) FROM job_embeddings;"))
        embeddings_sql = res_emb.scalar()

    print(f"Total jobs:                       {total_jobs_sql}")
    print(f"Jobs with non-empty descriptions: {non_empty_desc_sql}")
    print(f"Jobs with non-empty skills:       {non_empty_skills_sql}")
    print(f"Jobs with known experience levels:{known_exp_sql}")
    print(f"Jobs with valid application URLs: {valid_url_sql}")
    print(f"Job embeddings count:             {embeddings_sql}")

    # Step 4: Print per-job enrichment summary
    print("\n" + "=" * 80)
    print("DETAILED PER-JOB ENRICHMENT REPORT")
    print("=" * 80)
    for rep in enrichment_reports:
        print(f"Job #{rep['index']}:")
        print(f"  ID:              {rep['id']}")
        print(f"  Source Job ID:   {rep['source_job_id']}")
        print(f"  Title:           {rep['title']}")
        print(f"  Company:         {rep['company']}")
        print(f"  Status:          {rep['status']}")
        if rep['error']:
            print(f"  Error:           {rep['error']}")
        print(f"  Enriched Fields: {rep['enriched_fields']}")
        if 'desc_length' in rep:
            print(f"  Desc Length:     {rep['desc_length']}")
            print(f"  Skills Count:    {rep['skills_count']}")
            print(f"  Experience:      {rep['experience_level']}")
            print(f"  Application URL: {rep['application_url']}")
        print("-" * 60)

    if rate_limited:
        print("\n[ALERT] HTTP 429 Rate limit was encountered. Stopped immediately.")

    return {
        "total_jobs": total_jobs_sql,
        "non_empty_descriptions": non_empty_desc_sql,
        "non_empty_skills": non_empty_skills_sql,
        "known_experience_levels": known_exp_sql,
        "valid_application_urls": valid_url_sql,
        "job_embeddings_count": embeddings_sql,
        "reports": enrichment_reports,
        "rate_limited": rate_limited,
    }


if __name__ == "__main__":
    asyncio.run(enrich_jobs())
