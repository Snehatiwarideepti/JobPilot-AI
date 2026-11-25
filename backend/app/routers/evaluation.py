"""
Evaluation router and pipeline.
Runs actual retrieval evaluation against test queries.
Never fabricates metrics.
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import EvaluationQuery, EvaluationResult
from app.schemas import EvaluationQueryCreate, EvaluationSummary
from app.evaluation.pipeline import run_evaluation_pipeline

router = APIRouter()
logger = logging.getLogger(__name__)


PREDEFINED_QUERIES = [
    {"query_text": "Python data science internship India", "category": "internship"},
    {"query_text": "Remote machine learning internship", "category": "internship"},
    {"query_text": "Entry level data analyst jobs", "category": "entry"},
    {"query_text": "Junior Python developer", "category": "entry"},
    {"query_text": "AI engineer internship", "category": "internship"},
    {"query_text": "Machine learning engineer", "category": "mid"},
    {"query_text": "Data scientist remote", "category": "mid"},
    {"query_text": "NLP engineer", "category": "mid"},
    {"query_text": "Software engineer Python", "category": "entry"},
    {"query_text": "Full stack developer React Node.js", "category": "mid"},
    {"query_text": "DevOps engineer Kubernetes", "category": "mid"},
    {"query_text": "Computer vision deep learning", "category": "mid"},
    {"query_text": "Data engineer Spark SQL", "category": "mid"},
    {"query_text": "Backend engineer Python FastAPI", "category": "mid"},
    {"query_text": "Research scientist NLP", "category": "senior"},
    {"query_text": "MLOps engineer", "category": "mid"},
    {"query_text": "Product manager AI", "category": "mid"},
    {"query_text": "Generative AI engineer LLM", "category": "mid"},
    {"query_text": "Fresher data analyst Excel SQL", "category": "entry"},
    {"query_text": "Remote Python internship", "category": "internship"},
    {"query_text": "Senior machine learning engineer AWS", "category": "senior"},
    {"query_text": "Recommendation systems engineer", "category": "mid"},
    {"query_text": "Data science intern no experience", "category": "internship"},
    {"query_text": "Python scikit-learn pandas machine learning", "category": "entry"},
    {"query_text": "Cloud engineer AWS GCP Azure", "category": "mid"},
]


@router.post("/seed")
async def seed_evaluation_queries(db: AsyncSession = Depends(get_db)):
    """Seed the predefined evaluation queries into the database."""
    created = 0
    for q in PREDEFINED_QUERIES:
        # Check if already exists
        stmt = select(EvaluationQuery).where(EvaluationQuery.query_text == q["query_text"])
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if not existing:
            db.add(EvaluationQuery(
                query_text=q["query_text"],
                category=q.get("category"),
            ))
            created += 1
    await db.commit()
    return {"message": f"Seeded {created} new evaluation queries", "total": len(PREDEFINED_QUERIES)}


@router.post("/run")
async def run_evaluation(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger the evaluation pipeline.
    Runs in the background - check /evaluation/results for results.
    """
    background_tasks.add_task(run_evaluation_pipeline)
    return {
        "message": "Evaluation pipeline started in the background.",
        "note": "Check GET /evaluation/results after a few minutes.",
    }


@router.get("/results", response_model=EvaluationSummary)
async def get_evaluation_results(db: AsyncSession = Depends(get_db)):
    """
    Get a summary of evaluation results.
    Returns actual computed metrics only - never fabricated numbers.
    """
    stmt = select(EvaluationResult)
    result = await db.execute(stmt)
    all_results = result.scalars().all()

    if not all_results:
        return EvaluationSummary(
            total_queries=0,
            methods={},
            note="Evaluation not run yet. POST to /evaluation/run to execute the evaluation pipeline.",
        )

    # Aggregate by method
    method_metrics: dict[str, dict] = {}
    for r in all_results:
        m = r.retrieval_method
        if m not in method_metrics:
            method_metrics[m] = {"hit_at_5": [], "hit_at_10": [], "mrr": []}
        if r.hit_at_5 is not None:
            method_metrics[m]["hit_at_5"].append(r.hit_at_5)
        if r.hit_at_10 is not None:
            method_metrics[m]["hit_at_10"].append(r.hit_at_10)
        if r.mrr is not None:
            method_metrics[m]["mrr"].append(r.mrr)

    summary: dict[str, dict] = {}
    for method, metrics in method_metrics.items():
        summary[method] = {
            "hit_at_5": round(sum(metrics["hit_at_5"]) / len(metrics["hit_at_5"]), 3) if metrics["hit_at_5"] else None,
            "hit_at_10": round(sum(metrics["hit_at_10"]) / len(metrics["hit_at_10"]), 3) if metrics["hit_at_10"] else None,
            "mrr": round(sum(metrics["mrr"]) / len(metrics["mrr"]), 3) if metrics["mrr"] else None,
        }

    stmt2 = select(EvaluationQuery)
    total_q = len((await db.execute(stmt2)).scalars().all())

    return EvaluationSummary(
        total_queries=total_q,
        methods=summary,
        note="All metrics computed by actually running queries against the retrieval system.",
    )
