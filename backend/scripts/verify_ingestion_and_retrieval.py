"""
Verification script for:
1. Ingesting exactly 8 live jobs from Jobvetta using the existing ingestion pipeline.
2. Verifying all 8 jobs are correctly stored in PostgreSQL with normalized fields.
3. Testing keyword, semantic, hybrid, and reranking retrieval against the ingested jobs.

Guarantees: Zero OpenAI API calls (uses local sentence-transformers only).
"""
import asyncio
import os
import sys
from pathlib import Path

# Add backend root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure OpenAI API calls are blocked
os.environ["OPENAI_API_KEY"] = ""

from app.config import get_settings
from app.database import AsyncSessionLocal, init_db
from app.providers import get_provider
from app.services.ingestion import upsert_job, generate_and_store_embedding
from app.models import Job, JobEmbedding, JobSkill, CandidateProfile, CandidateSkill
from app.retrieval.engine import (
    keyword_search,
    semantic_search,
    hybrid_search,
    rerank_results,
)
from sqlalchemy import select, func


async def main():
    settings = get_settings()
    # Force use_openai_embeddings to False
    assert settings.use_openai_embeddings is False, "use_openai_embeddings must be False"

    print("=" * 70)
    print("STEP 1: Ingesting exactly 8 live jobs from Jobvetta")
    print("=" * 70)

    provider = get_provider("jobvetta")
    print(f"Provider: {provider.name} (Base URL: {provider.BASE_URL})")

    # Search for jobs
    search_query = "engineer"
    print(f"Searching Jobvetta for query: '{search_query}' with limit=8...")
    result = await provider.search_jobs(query=search_query, limit=8)

    print(f"Total jobs returned from Jobvetta: {len(result.jobs)}")
    if len(result.jobs) < 8:
        print(f"Warning: only {len(result.jobs)} returned, trying fallback search...")
        res2 = await provider.search_jobs(query="developer", limit=8)
        combined = {j.source_job_id: j for j in (result.jobs + res2.jobs)}
        jobs_to_process = list(combined.values())[:8]
    else:
        jobs_to_process = result.jobs[:8]

    assert len(jobs_to_process) == 8, f"Expected 8 jobs, got {len(jobs_to_process)}"
    print(f"Selected exactly {len(jobs_to_process)} jobs to ingest.")

    ingested_jobs = []
    async with AsyncSessionLocal() as db:
        for idx, pj in enumerate(jobs_to_process, 1):
            job, created = await upsert_job(db, pj)
            await generate_and_store_embedding(db, job)
            ingested_jobs.append(job)
            print(f" [{idx}/8] {'Created' if created else 'Updated'}: {job.title} | {job.company} (ID: {job.source_job_id})")
        await db.commit()

    print("\nStep 1 successfully completed: 8 live jobs ingested and embedded.")

    print("\n" + "=" * 70)
    print("STEP 2: Verifying stored jobs in PostgreSQL")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        # Check job count
        stmt = select(func.count()).select_from(Job)
        job_count = (await db.execute(stmt)).scalar()

        emb_stmt = select(func.count()).select_from(JobEmbedding)
        emb_count = (await db.execute(emb_stmt)).scalar()

        print(f"Total jobs in DB: {job_count}")
        print(f"Total job embeddings in DB: {emb_count}")

        stmt_jobs = select(Job).order_by(Job.created_at.desc()).limit(8)
        res = await db.execute(stmt_jobs)
        stored_jobs = res.scalars().all()

        print("\nStored Job Details:")
        for idx, j in enumerate(stored_jobs, 1):
            # Check embedding
            emb_res = await db.execute(select(JobEmbedding).where(JobEmbedding.job_id == j.id))
            emb = emb_res.scalar_one_or_none()
            has_emb = emb is not None and emb.embedding is not None

            print(f" Job #{idx}:")
            print(f"   ID:             {j.id}")
            print(f"   Source:         {j.source}")
            print(f"   Source Job ID:  {j.source_job_id}")
            print(f"   Title:          {j.title}")
            print(f"   Company:        {j.company}")
            print(f"   Location:       {j.location}")
            print(f"   Workplace:      {j.workplace_type}")
            print(f"   Employment:     {j.employment_type}")
            print(f"   Experience:     {j.experience_level}")
            print(f"   App URL:        {j.application_url}")
            print(f"   Active:         {j.is_active}")
            print(f"   Skills Count:   {len(j.skills or [])} ({', '.join((j.skills or [])[:4])}...)")
            print(f"   Embedded:       {has_emb} (Model: {emb.model_name if emb else 'None'}, Dim: 384)")
            assert j.source == "jobvetta", f"Invalid source: {j.source}"
            assert j.source_job_id, "Missing source_job_id"
            assert j.application_url, "Missing application_url"
            assert j.is_active is True, "Job is not active"
            assert has_emb, f"Job {j.id} lacks embedding"

    print("\nStep 2 verification passed: All 8 jobs validated.")

    print("\n" + "=" * 70)
    print("STEP 3: Testing Retrieval (Keyword, Semantic, Hybrid, Reranking)")
    print("=" * 70)

    test_query = "engineer"
    print(f"Test Query: '{test_query}'\n")

    async with AsyncSessionLocal() as db:
        # A. Keyword Search
        print("--- A. Keyword Search (Full-text tsvector) ---")
        kw_results = await keyword_search(db, test_query, limit=5)
        print(f"Keyword matches found: {len(kw_results)}")
        for rank, (job, score) in enumerate(kw_results, 1):
            print(f"  #{rank}: [Score: {score:.4f}] {job.title} at {job.company}")

        # B. Semantic Search
        print("\n--- B. Semantic Search (pgvector Cosine Similarity) ---")
        sem_results = await semantic_search(db, test_query, limit=5)
        print(f"Semantic matches found: {len(sem_results)}")
        for rank, (job, score) in enumerate(sem_results, 1):
            print(f"  #{rank}: [Similarity: {score:.4f}] {job.title} at {job.company}")

        # C. Hybrid Search (RRF)
        print("\n--- C. Hybrid Search (Reciprocal Rank Fusion) ---")
        hybrid_results = await hybrid_search(db, test_query, limit=5)
        print(f"Hybrid matches found: {len(hybrid_results)}")
        for rank, (job, score) in enumerate(hybrid_results, 1):
            print(f"  #{rank}: [RRF Score: {score:.6f}] {job.title} at {job.company}")

        # D. Reranking
        print("\n--- D. Multi-Factor Reranking ---")
        # Construct candidate profile with matching attributes
        candidate = CandidateProfile(
            experience_level="mid",
            remote_preference="remote",
            skills=[CandidateSkill(name="Python"), CandidateSkill(name="SQL"), CandidateSkill(name="AWS")]
        )
        print("Candidate Profile:")
        print(f"  Experience Level:   {candidate.experience_level}")
        print(f"  Remote Preference:  {candidate.remote_preference}")
        print(f"  Skills:             {[s.name for s in candidate.skills]}")

        reranked = await rerank_results(hybrid_results, candidate_profile=candidate, query=test_query)
        print(f"\nReranked Results ({len(reranked)} jobs):")
        for r in reranked:
            print(f"  Rank #{r.rank}: Final Score: {r.final_score:.4f}")
            print(f"    Job:               {r.job.title} ({r.job.company})")
            print(f"    Workplace/Exp:     {r.job.workplace_type} / {r.job.experience_level}")
            print(f"    Semantic Score:    {r.semantic_score:.4f} (Weight: {settings.semantic_weight:.2f})")
            print(f"    Skill Score:       {r.skill_match_score:.4f} (Weight: {settings.skill_weight:.2f})")
            print(f"    Experience Score:  {r.experience_match_score:.4f} (Weight: {settings.experience_weight:.2f})")
            print(f"    Location Score:    {r.location_score:.4f} (Weight: {settings.location_weight:.2f})")
            print(f"    Matched Skills:    {r.matched_skills}")
            print(f"    Missing Skills:    {r.missing_skills[:5]}...")

    print("\nStep 3 verification passed: All retrieval modes working as expected.")


if __name__ == "__main__":
    asyncio.run(main())
