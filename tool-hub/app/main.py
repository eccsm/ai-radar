#!/usr/bin/env python
"""
Tool Hub - Main Application Entry Point
Central API service that exposes endpoints for the AI Radar system.
"""
import os
import logging
import hashlib
import codecs
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import asyncpg
import nats
from nats.js.api import StreamConfig
import json
import httpx
from contextlib import asynccontextmanager
from datetime import datetime

# Import libraries for HTTP requests and JSON parsing

# Import MCP SDK for tool exposure
try:
    from mcp_sdk import expose_tool
except ImportError:
    # Fallback implementation if mcp_sdk is not available
    def expose_tool(app, tool_id, description=None):
        def decorator(func):
            return func
        return decorator

# Configure logging
logger = logging.getLogger("toolhub")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

async def get_db_connection_string():
    """
    Retrieves the PostgreSQL connection string.
    Prioritizes POSTGRES_URL_FILE, then POSTGRES_URL.
    Falls back to a hardcoded string for debugging if needed.
    """
    pg_url = os.getenv("POSTGRES_URL")
    pg_url_file_path = os.getenv("POSTGRES_URL_FILE")
    
    # Hardcoded fallback for debugging
    fallback_connection_string = "postgresql://ai:ai_pwd@db:5432/ai_radar"
    
    if pg_url_file_path:
        logger.info(f"Attempting to read DB connection string from file: {pg_url_file_path}")
        try:
            with open(pg_url_file_path, 'r', encoding='utf-8') as f: 
                connection_string = f.read()
                # Explicitly remove BOM if present
                if connection_string.startswith('\ufeff'):
                    logger.info("Unicode BOM (U+FEFF) detected and removed.")
                    connection_string = connection_string[1:]
                connection_string = connection_string.strip()
                
                if connection_string:
                    logger.info("Successfully read DB connection string from file.")
                    # Debug: Print the connection string bytes for debugging
                    logger.info(f"Connection string bytes: {[ord(c) for c in connection_string[:20]]}")
                    return connection_string
        except Exception as e:
            logger.error(f"Error reading DB connection string from file: {e}")
            logger.info(f"Using fallback connection string for debugging")
            return fallback_connection_string
    
    if pg_url:
        logger.info("Using POSTGRES_URL environment variable.")
        return pg_url
    
    logger.info("No PostgreSQL connection string found. Using fallback for debugging.")
    return fallback_connection_string

async def get_nats_url():
    """
    Retrieves the NATS connection URL.
    Prioritizes NATS_URL_FILE, then NATS_URL.
    Falls back to a hardcoded string for debugging if needed.
    """
    nats_url = os.getenv("NATS_URL")
    nats_url_file_path = os.getenv("NATS_URL_FILE")
    
    # Hardcoded fallback for debugging
    fallback_nats_url = "nats://nats:4222"
    
    if nats_url_file_path:
        logger.info(f"Attempting to read NATS URL from file: {nats_url_file_path}")
        try:
            with open(nats_url_file_path, 'r', encoding='utf-8') as f: 
                connection_url = f.read().strip()
                # Explicitly remove BOM if present
                if connection_url.startswith('\ufeff'):
                    logger.info("Unicode BOM (U+FEFF) detected and removed.")
                    connection_url = connection_url[1:]
                
                if connection_url:
                    logger.info("Successfully read NATS URL from file.")
                    return connection_url
        except Exception as e:
            logger.error(f"Error reading NATS URL file: {e}")
            logger.info(f"Using fallback NATS URL for debugging")
            return fallback_nats_url
    
    if nats_url:
        logger.info("Using NATS_URL environment variable.")
        return nats_url
    
    logger.info("No NATS URL found. Using fallback for debugging.")
    return fallback_nats_url

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the FastAPI app."""
    global db, nc, js
    db_connection = None
    try:
        # Get database connection string
        connection_string = await get_db_connection_string()
        logger.info(f"Attempting to connect to PostgreSQL with URL: {connection_string[:connection_string.find('@') if '@' in connection_string else len(connection_string)]}...") # Log URL without credentials
        db_connection = await asyncpg.connect(connection_string)
        app.state.db = db_connection
        logger.info("Successfully connected to PostgreSQL.")
        
        # NATS connection with proper URL format
        logger.info("Connecting to NATS...")
        # Use a properly formatted NATS URL
        nats_url = "nats://nats:4222"
        logger.info(f"Attempting to connect to NATS with URL: {nats_url}")
        nc = await nats.connect(nats_url)
        js = nc.jetstream()
        
        # Ensure JetStream stream exists
        try:
            await js.add_stream(
                name="ai-radar",
                subjects=["ai-radar.>"],
                storage="file",
                max_msgs=100000,
            )
        except Exception as e:
            logger.warning(f"Stream exists or error: {e}")
            
        logger.info("All connections established successfully.")
        yield
    except ValueError as ve:
        logger.critical(f"Configuration error during startup: {ve}")
        # Re-raise to ensure FastAPI knows startup failed
        raise
    except asyncpg.exceptions.ConnectionDoesNotExistError as e:
        logger.critical(f"Failed to connect to PostgreSQL: Connection does not exist. Check DB server, network, and credentials. Error: {e}")
        raise
    except asyncpg.exceptions.InvalidPasswordError as e:
        logger.critical(f"Failed to connect to PostgreSQL: Invalid password. Error: {e}")
        raise
    except ConnectionRefusedError as e:
        logger.critical(f"Failed to connect to PostgreSQL: Connection refused. Ensure DB is running and accessible. Error: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred during application startup: {e}", exc_info=True)
        # Re-raise to ensure FastAPI knows startup failed
        raise

    logger.info("Shutting down connections...")
    if hasattr(app.state, 'db') and app.state.db:
        logger.info("Closing PostgreSQL connection...")
        await app.state.db.close()
        logger.info("PostgreSQL connection closed.")
    if nc:
        await nc.close()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="AI Radar Tool Hub",
    description="Central API for the AI Radar system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Models ---

class RssFeedRequest(BaseModel):
    url: HttpUrl
    name: str


class JsonFetchRequest(BaseModel):
    url: HttpUrl
    path: str = None


class ArticleFetchRequest(BaseModel):
    url: HttpUrl


# --- Database Functions ---

async def get_db():
    """Dependency to get database connection."""
    return app.state.db


# --- API Endpoints ---

# Initialize S3 client
def init_clients_from_env():
    import aioboto3
    session = aioboto3.Session()
    db_client = app.state.db  # We already have the DB connection
    
    # Get MinIO configuration from environment variables with defaults
    s3_client = session.client(
        's3',
        endpoint_url=os.getenv('MINIO_ENDPOINT', 'http://minio:9000'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID', 'minio'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY', 'minio_pwd'),
        region_name='us-east-1',  # MinIO default
    )
    return db_client, s3_client

# Expose tool for RSS fetching
@expose_tool(app, tool_id="rss_fetch", description="Fetch RSS/Atom feed URL")
async def rss_fetch(payload: dict):
    """Fetch RSS feed content and store in MinIO."""
    url = payload["url"]
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=20)
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Upstream error")
        
        # Hash the URL to create a unique key
        key = f"raw/{hashlib.sha1(url.encode()).hexdigest()}.xml"
        
        # Get S3 client
        _, S3 = init_clients_from_env()
        
        # Store the content in MinIO
        async with S3 as s3:
            await s3.put_object(
                Bucket="ai-radar",
                Key=key,
                Body=response.text
            )
        
        return {"s3_key": key, "bytes": len(response.text)}

@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    try:
        # Verify database connection
        if app.state.db:
            version = await app.state.db.fetchval("SELECT version()")
            logger.info(f"Database connected: {version}")
        
        # Verify NATS connection
        if nc and nc.is_connected:
            logger.info("NATS connected")
            
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Unhealthy: {str(e)}")


@app.post("/sources/rss")
async def add_rss_source(
    request: RssFeedRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db)
):
    """Add a new RSS feed source and trigger initial fetch."""
    try:
        # Add source to database
        source_id = await db.fetchval(
            """
            INSERT INTO ai_radar.sources (name, url, source_type)
            VALUES ($1, $2, 'rss')
            RETURNING id
            """,
            request.name, str(request.url)
        )
        
        # Publish message to queue for fetcher
        background_tasks.add_task(
            publish_fetch_task, source_id, str(request.url)
        )
        
        return {
            "status": "success",
            "message": f"RSS source added with ID {source_id}",
            "source_id": source_id
        }
    except Exception as e:
        logger.error(f"Error adding RSS source: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rss/fetch")
async def fetch_rss(request: RssFeedRequest, background_tasks: BackgroundTasks):
    """Fetch RSS feed content."""
    try:
        # Publish message to NATS for processing
        background_tasks.add_task(
            publish_rss_fetch, str(request.url), request.name
        )
        
        return {
            "status": "success",
            "message": f"RSS fetch job queued for {request.url}"
        }
    except Exception as e:
        logger.error(f"Error fetching RSS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/json/fetch")
async def fetch_json(request: JsonFetchRequest, background_tasks: BackgroundTasks):
    """Fetch JSON from URL and optionally extract data at path."""
    try:
        # Publish message to NATS for processing
        background_tasks.add_task(
            publish_json_fetch, str(request.url), request.path
        )
        
        return {
            "status": "success",
            "message": f"JSON fetch job queued for {request.url}"
        }
    except Exception as e:
        logger.error(f"Error fetching JSON: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/article/fetch")
async def fetch_article(request: ArticleFetchRequest, background_tasks: BackgroundTasks):
    """Fetch and process an article from URL."""
    try:
        # Publish message to NATS for processing
        background_tasks.add_task(
            publish_article_fetch, str(request.url)
        )
        
        return {
            "status": "success",
            "message": f"Article fetch job queued for {request.url}"
        }
    except Exception as e:
        logger.error(f"Error fetching article: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sources")
async def list_sources(db=Depends(get_db)):
    """List all sources."""
    try:
        sources = await db.fetch(
            """
            SELECT id, name, url, source_type, active, created_at, last_fetched_at
            FROM ai_radar.sources
            ORDER BY id
            """
        )
        return [dict(source) for source in sources]
    except Exception as e:
        logger.error(f"Error listing sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/articles")
async def list_articles(
    limit: int = 20,
    offset: int = 0,
    db=Depends(get_db)
):
    """List articles with pagination."""
    try:
        articles = await db.fetch(
            """
            SELECT 
                a.id, a.title, a.url, a.author, a.published_at,
                a.fetched_at, a.summary, a.importance_score,
                s.name as source_name
            FROM 
                ai_radar.articles a
            JOIN 
                ai_radar.sources s ON a.source_id = s.id
            ORDER BY 
                a.published_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
        
        total = await db.fetchval(
            "SELECT COUNT(*) FROM ai_radar.articles"
        )
        
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "articles": [dict(article) for article in articles]
        }
    except Exception as e:
        logger.error(f"Error listing articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_metrics(db=Depends(get_db)):
    """Get system metrics."""
    try:
        stats = await db.fetchrow(
            """
            SELECT 
                (SELECT COUNT(*) FROM ai_radar.sources) as source_count,
                (SELECT COUNT(*) FROM ai_radar.articles) as article_count,
                (SELECT MIN(published_at) FROM ai_radar.articles) as oldest_article,
                (SELECT MAX(published_at) FROM ai_radar.articles) as newest_article,
                (SELECT AVG(importance_score) FROM ai_radar.articles) as avg_importance
            """
        )
        
        source_breakdown = await db.fetch(
            """
            SELECT 
                s.name, COUNT(a.id) as article_count
            FROM 
                ai_radar.sources s
            LEFT JOIN 
                ai_radar.articles a ON s.id = a.source_id
            GROUP BY 
                s.id, s.name
            ORDER BY 
                article_count DESC
            """
        )
        
        return {
            "stats": dict(stats),
            "sources": [dict(s) for s in source_breakdown]
        }
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- NATS Message Publishing Functions ---

async def publish_fetch_task(source_id, url):
    """Publish a fetch task message to NATS."""
    try:
        payload = {
            "source_id": source_id,
            "url": url,
            "timestamp": datetime.now().isoformat()
        }
        await js.publish(
            "ai-radar.tasks.fetch",
            json.dumps(payload).encode()
        )
        logger.info(f"Published fetch task for source {source_id}")
    except Exception as e:
        logger.error(f"Error publishing fetch task: {e}")


async def publish_rss_fetch(url, name):
    """Publish an RSS fetch message to NATS."""
    try:
        payload = {
            "url": url,
            "name": name,
            "timestamp": datetime.now().isoformat()
        }
        await js.publish(
            "ai-radar.tasks.rss_fetch",
            json.dumps(payload).encode()
        )
        logger.info(f"Published RSS fetch task for {url}")
    except Exception as e:
        logger.error(f"Error publishing RSS fetch task: {e}")


async def publish_json_fetch(url, path=None):
    """Publish a JSON fetch message to NATS."""
    try:
        payload = {
            "url": url,
            "path": path,
            "timestamp": datetime.now().isoformat()
        }
        await js.publish(
            "ai-radar.tasks.json_fetch",
            json.dumps(payload).encode()
        )
        logger.info(f"Published JSON fetch task for {url}")
    except Exception as e:
        logger.error(f"Error publishing JSON fetch task: {e}")


async def publish_article_fetch(url):
    """Publish an article fetch message to NATS."""
    try:
        payload = {
            "url": url,
            "timestamp": datetime.now().isoformat()
        }
        await js.publish(
            "ai-radar.tasks.article_fetch",
            json.dumps(payload).encode()
        )
        logger.info(f"Published article fetch task for {url}")
    except Exception as e:
        logger.error(f"Error publishing article fetch task: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)