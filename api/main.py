"""
AI Radar API Service
Provides REST API endpoints for the React frontend
"""
import asyncio
import os
import logging
import socket
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import asyncpg
from fastapi import FastAPI, Depends, HTTPException, status, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Import authentication module
from auth import Token, User, authenticate_user, create_access_token, get_current_active_user

# Import SecretsManager
from _core.secrets import SecretsManager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory for _core module access
try:
    # First try the mounted parent path (for Docker)
    sys.path.append('/app/parent')
    from parent._core.secrets import SecretsManager
    logger.info("Successfully imported SecretsManager from parent._core")
except ImportError:
    try:
        # Fall back to regular import for local development
        sys.path.append('..')
        from _core.secrets import SecretsManager
        logger.info("Successfully imported SecretsManager from _core")
    except ImportError as e:
        logger.error(f"Failed to import SecretsManager: {e}")
        raise

# Instantiate SecretsManager
secrets_manager = SecretsManager()

# Lifespan context manager for database connection pool
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database connection pool
    db_host = secrets_manager.get_secret("DB_HOST", default="localhost")
    db_port = secrets_manager.get_secret("DB_PORT", default="5432")
    db_user = secrets_manager.get_secret("DB_USER", default="ai")
    db_password = secrets_manager.get_secret("DB_PASSWORD", default="password") # Ensure this default is safe or removed for prod
    db_name = secrets_manager.get_secret("DB_NAME", default="ai_radar")

    dsn = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    try:
        app.state.pool = await asyncpg.create_pool(dsn)
        logging.info("Successfully connected to PostgreSQL and connection pool created.")
    except Exception as e:
        logging.error(f"Failed to connect to PostgreSQL: {e}")
        app.state.pool = None # Ensure pool is None if connection fails
    
    yield
    
    # Shutdown: Close database connection pool
    if app.state.pool:
        await app.state.pool.close()
        logging.info("PostgreSQL connection pool closed.")

# Create FastAPI app
app = FastAPI(
    title="AI Radar API",
    description="API for AI Radar monitoring and analytics",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    redoc_url="/redoc",
    lifespan=lifespan # Add lifespan context manager
)

# Create API router with /api prefix
from fastapi import APIRouter
api_router = APIRouter(prefix="/api")

# Add CORS middleware to allow cross-origin requests from the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8001", "*"],  # Explicitly list React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection helper with retry and fallback logic
async def get_connection_pool():
    return app.state.pool

# Pydantic models for API responses
class ArticleStats(BaseModel):
    total_articles: int
    articles_last_day: int
    articles_last_week: int
    articles_last_month: int
    avg_similarity_score: float

class SourceStats(BaseModel):
    total_sources: int
    active_sources: int
    sources_with_articles: int
    top_sources: List[Dict[str, Any]]

class Article(BaseModel):
    id: str
    title: str
    url: str
    source_name: str
    published_at: Optional[datetime]
    fetched_at: Optional[datetime]
    summary: Optional[str]
    sentiment_score: Optional[float]
    importance_score: Optional[float]

class Source(BaseModel):
    id: str
    name: str
    url: str
    source_type: str
    active: bool
    last_fetched_at: Optional[datetime]
    article_count: int

# API endpoints
@api_router.get("/")
async def root():
    return {"message": "Welcome to AI Radar API"}

@api_router.get("/stats/articles", response_model=ArticleStats)
async def get_article_stats():
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        # Get total articles
        total = await conn.fetchval("SELECT COUNT(*) FROM articles")
        
        # Get articles in last day
        last_day = await conn.fetchval(
            "SELECT COUNT(*) FROM articles WHERE fetched_at > $1",
            datetime.now() - timedelta(days=1)
        )
        
        # Get articles in last week
        last_week = await conn.fetchval(
            "SELECT COUNT(*) FROM articles WHERE fetched_at > $1",
            datetime.now() - timedelta(weeks=1)
        )
        
        # Get articles in last month
        last_month = await conn.fetchval(
            "SELECT COUNT(*) FROM articles WHERE fetched_at > $1",
            datetime.now() - timedelta(days=30)
        )
        
        # Get average similarity score
        avg_score = await conn.fetchval(
            "SELECT AVG(similarity_score) FROM article_similarities"
        ) or 0.0
        
        return ArticleStats(
            total_articles=total,
            articles_last_day=last_day,
            articles_last_week=last_week,
            articles_last_month=last_month,
            avg_similarity_score=float(avg_score)
        )

@api_router.get("/stats/sources", response_model=SourceStats)
async def get_source_stats():
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        # Get total sources
        total = await conn.fetchval("SELECT COUNT(*) FROM sources")
        
        # Get active sources
        active = await conn.fetchval("SELECT COUNT(*) FROM sources WHERE active = true")
        
        # Get sources with at least one article
        with_articles = await conn.fetchval("""
            SELECT COUNT(DISTINCT s.id) 
            FROM sources s
            JOIN articles a ON s.id = a.source_id
        """)
        
        # Get top sources by article count
        top_sources = await conn.fetch("""
            SELECT s.name, COUNT(a.id) as article_count
            FROM sources s
            JOIN articles a ON s.id = a.source_id
            GROUP BY s.name
            ORDER BY article_count DESC
            LIMIT 5
        """)
        
        return SourceStats(
            total_sources=total,
            active_sources=active,
            sources_with_articles=with_articles,
            top_sources=[dict(s) for s in top_sources]
        )

@api_router.get("/trending", response_model=List[Article])
async def get_trending_articles(days: int = 7, limit: int = 10):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        articles = await conn.fetch("""
            SELECT 
                a.id, 
                a.title, 
                a.url, 
                s.name as source_name,
                a.published_at,
                a.fetched_at,
                a.summary,
                a.sentiment_score,
                a.importance_score
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            WHERE a.fetched_at > $1
            ORDER BY a.importance_score DESC NULLS LAST
            LIMIT $2
        """, datetime.now() - timedelta(days=days), limit)
        
        return [dict(a) for a in articles]

@api_router.get("/articles/over-time")
async def get_articles_over_time():
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        # Get article counts grouped by day for the last 30 days
        results = await conn.fetch("""
            SELECT 
                date_trunc('day', fetched_at) as day,
                COUNT(*) as count
            FROM articles
            WHERE fetched_at > $1
            GROUP BY day
            ORDER BY day
        """, datetime.now() - timedelta(days=30))
        
        return [{"date": row["day"].isoformat(), "count": row["count"]} for row in results]

@api_router.get("/articles/similar/{article_id}", response_model=List[Article])
async def get_similar_articles(article_id: str, limit: int = 5):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        # Check if article exists
        article_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM articles WHERE id = $1)",
            article_id
        )
        
        if not article_exists:
            raise HTTPException(status_code=404, detail=f"Article with ID {article_id} not found")
        
        # Get similar articles
        similar_articles = await conn.fetch("""
            SELECT 
                a.id, 
                a.title, 
                a.url, 
                s.name as source_name,
                a.published_at,
                a.fetched_at,
                a.summary,
                a.sentiment_score,
                a.importance_score,
                sim.similarity_score
            FROM article_similarities sim
            JOIN articles a ON sim.article_id_2 = a.id
            JOIN sources s ON a.source_id = s.id
            WHERE sim.article_id_1 = $1
            ORDER BY sim.similarity_score DESC
            LIMIT $2
        """, article_id, limit)
        
        return [dict(a) for a in similar_articles]

@api_router.get("/search", response_model=List[Article])
async def search_articles(query: str, limit: int = 20):
    if not query or len(query.strip()) < 3:
        raise HTTPException(status_code=400, detail="Search query must be at least 3 characters")
    
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        # Search for articles matching the query
        search_results = await conn.fetch("""
            SELECT 
                a.id, 
                a.title, 
                a.url, 
                s.name as source_name,
                a.published_at,
                a.fetched_at,
                a.summary,
                a.sentiment_score,
                a.importance_score
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            WHERE 
                a.title ILIKE $1 OR
                a.summary ILIKE $1
            ORDER BY a.importance_score DESC NULLS LAST
            LIMIT $2
        """, f"%{query}%", limit)
        
        return [dict(a) for a in search_results]

@api_router.get("/sources", response_model=List[Source])
async def get_all_sources():
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        sources = await conn.fetch("""
            SELECT 
                s.id, 
                s.name, 
                s.url, 
                s.source_type, 
                s.active, 
                s.last_fetched_at,
                COUNT(a.id) as article_count
            FROM sources s
            LEFT JOIN articles a ON s.id = a.source_id
            GROUP BY s.id
            ORDER BY s.name
        """)
        
        return [dict(s) for s in sources]

@app.post("/sources")
async def add_source(name: str, url: str, source_type: str = "rss", active: bool = True, current_user: User = Depends(get_current_active_user)):
    pool = await get_connection_pool()
    try:
        async with pool.acquire() as conn:
            # Check if source with this URL already exists
            exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM sources WHERE url = $1)", url)
            if exists:
                raise HTTPException(status_code=400, detail=f"Source with URL {url} already exists")
            
            # Add new source
            source_id = await conn.fetchval("""
                INSERT INTO sources (name, url, source_type, active)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, name, url, source_type, active)
            
            return {"id": source_id, "name": name, "message": "Source added successfully"}
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(status_code=400, detail=f"Source with name {name} already exists")
    except Exception as e:
        logger.error(f"Error adding source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/sources/{source_id}")
async def update_source(source_id: str, name: str, url: str, source_type: str, active: bool, current_user: User = Depends(get_current_active_user)):
    pool = await get_connection_pool()
    try:
        async with pool.acquire() as conn:
            # Check if source exists
            exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM sources WHERE id = $1)", source_id)
            if not exists:
                raise HTTPException(status_code=404, detail=f"Source with ID {source_id} not found")
            
            # Update source
            await conn.execute("""
                UPDATE sources
                SET name = $1, url = $2, source_type = $3, active = $4
                WHERE id = $5
            """, name, url, source_type, active, source_id)
            
            return {"id": source_id, "name": name, "message": "Source updated successfully"}
    except Exception as e:
        logger.error(f"Error updating source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/sources/{source_id}")
async def delete_source(source_id: str, current_user: User = Depends(get_current_active_user)):
    pool = await get_connection_pool()
    try:
        async with pool.acquire() as conn:
            # Check if source exists
            exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM sources WHERE id = $1)", source_id)
            if not exists:
                raise HTTPException(status_code=404, detail=f"Source with ID {source_id} not found")
            
            # Delete source (cascade will handle related articles)
            await conn.execute("DELETE FROM sources WHERE id = $1", source_id)
            
            return {"id": source_id, "message": "Source deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Authentication endpoints

ACCESS_TOKEN_EXPIRE_MINUTES = 30

@api_router.post("/auth/token", response_model=Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint to get JWT token."""
    pool = request.app.state.pool
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection pool not available."
        )

    async with pool.acquire() as db_conn:
        user = await authenticate_user(db_conn, form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@api_router.get("/auth/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """Fetch the current logged-in user."""
    return current_user

# Health check endpoints

@api_router.get("/healthz", status_code=status.HTTP_200_OK)
async def health_check():
    """Simple health check endpoint for Docker health checks"""
    return {"status": "ok"}

@api_router.get("/health", status_code=status.HTTP_200_OK)
async def detailed_health_check():
    """Detailed health check that tests database connectivity"""
    try:
        pool = await get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute('SELECT 1')
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "healthy", "database": "connected"}
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "disconnected", "error": str(e)}
        )

# Include the API router in the main app
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
