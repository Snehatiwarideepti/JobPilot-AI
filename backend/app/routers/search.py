"""Search history router."""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import SearchHistory

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/history")
async def get_search_history(
    user_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get search history for a user."""
    stmt = select(SearchHistory).order_by(SearchHistory.created_at.desc()).limit(limit)
    if user_id:
        try:
            uid = uuid.UUID(user_id)
            stmt = stmt.where(SearchHistory.user_id == uid)
        except ValueError:
            pass

    result = await db.execute(stmt)
    history = result.scalars().all()
    return [
        {
            "id": str(h.id),
            "query": h.query,
            "filters": h.filters,
            "result_count": h.result_count,
            "created_at": h.created_at.isoformat(),
        }
        for h in history
    ]


async def record_search(
    db: AsyncSession,
    query: str,
    user_id: Optional[str] = None,
    filters: Optional[dict] = None,
    result_count: Optional[int] = None,
    source: str = "search_page",
) -> None:
    """Helper to record a search to history."""
    try:
        uid = uuid.UUID(user_id) if user_id else None
        entry = SearchHistory(
            user_id=uid,
            query=query,
            filters=filters,
            result_count=result_count,
            source=source,
        )
        db.add(entry)
        await db.flush()
    except Exception as e:
        logger.warning("Failed to record search history: %s", e)
