"""
FastAPI Application Entry Point
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import jobs, profile, chat, evaluation, health, search, skills

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("JobPilot AI starting up...")

    # Create upload directory
    os.makedirs(settings.upload_dir, exist_ok=True)

    # Initialize database (pgvector extension + tables)
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        logger.warning("Continuing without database - some features will be unavailable")

    yield  # Application runs

    logger.info("JobPilot AI shutting down...")


app = FastAPI(
    title="JobPilot AI",
    description="Explainable AI Career Matching Agent",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, tags=["health"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(skills.router, prefix="/skills", tags=["skills"])
app.include_router(evaluation.router, prefix="/evaluation", tags=["evaluation"])
