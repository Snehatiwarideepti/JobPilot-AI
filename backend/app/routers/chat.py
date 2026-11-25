"""Chat/agent router."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ChatRequest, ChatResponse
from app.agents.job_agent import JobPilotAgent

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Main chat endpoint. Routes message to the AI agent.
    Agent decides which tools to use (search, analyze, save, etc.).
    """
    session_id = request.session_id or str(uuid.uuid4())

    agent = JobPilotAgent(db=db)
    try:
        response = await agent.chat(
            message=request.message,
            session_id=session_id,
            user_id=request.user_id,
        )
        return response
    except Exception as e:
        logger.error("Chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)[:200]}")
