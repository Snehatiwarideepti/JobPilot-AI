"""
Health check router.
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.config import get_settings
from app.schemas import HealthResponse
from app.providers import get_provider

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    System health check.
    Reports actual status of each subsystem - never fakes success.
    """
    # Database
    db_status = "unavailable"
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.warning("Database health check failed: %s", e)
        db_status = f"error: {str(e)[:50]}"

    # Embedding model (checks if importable, not loaded)
    embed_status = "unknown"
    try:
        from sentence_transformers import SentenceTransformer
        embed_status = f"available (model: {settings.embedding_model})"
    except ImportError:
        if settings.use_openai_embeddings and settings.openai_api_key:
            embed_status = "openai embeddings configured"
        else:
            embed_status = "sentence-transformers not installed"

    # Provider
    provider_status = "not configured"
    if settings.jobvetta_api_key:
        provider_status = "configured (key present)"
    else:
        provider_status = "not configured (JOBVETTA_API_KEY missing)"

    # LLM
    llm_status = "not configured"
    if settings.openai_api_key:
        llm_status = f"configured (model: {settings.openai_model})"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        embeddings=embed_status,
        provider=provider_status,
        llm=llm_status,
    )
