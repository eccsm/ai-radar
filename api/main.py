# api/main.py - Enhanced API with CORS and Vault integration
# This should be placed in your ./api/main.py file

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import hvac
import os
import logging
from datetime import datetime, timedelta
import jwt
import asyncpg
from typing import Optional, List, Dict, Any
import asyncio
import httpx
import nats
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

class VaultClient:
    """Vault client following Single Responsibility Principle"""
    
    def __init__(self):
        self.client = None
        self.vault_addr = os.getenv('VAULT_ADDR', 'http://host.docker.internal:8200')
        self.vault_token = os.getenv('VAULT_TOKEN', 'root')
        
    async def initialize(self):
        """Initialize Vault connection with proper error handling"""
        try:
            self.client = hvac.Client(url=self.vault_addr, token=self.vault_token)
            if self.client.is_authenticated():
                logger.info(f"✅ Vault connected successfully at {self.vault_addr}")
                return True
            else:
                logger.error(f"❌ Vault authentication failed")
                return False
        except Exception as e:
            logger.error(f"❌ Vault connection failed: {e}")
            return False
    
    def get_secret(self, path: str) -> Optional[Dict[str, Any]]:
        """Get secret from Vault with error handling"""
        try:
            if not self.client:
                logger.error("Vault client not initialized")
                return None
                
            response = self.client.secrets.kv.v2.read_secret_version(path=path)
            return response['data']['data']
        except Exception as e:
            logger.error(f"Failed to get secret {path}: {e}")
            return None

class DatabaseManager:
    """Database connection manager following Dependency Inversion Principle"""
    
    def __init__(self, vault_client: VaultClient):
        self.vault_client = vault_client
        self.pool = None
        
    async def initialize(self):
        """Initialize database connection using Vault secrets"""
        try:
            # Get database secrets from Vault
            db_secrets = self.vault_client.get_secret('ai-radar/database')
            if not db_secrets:
                # Fallback to environment variables
                logger.warning("Using fallback database configuration")
                db_config = {
                    'host': os.getenv('DB_HOST', 'db'),
                    'port': int(os.getenv('DB_PORT', '5432')),
                    'user': os.getenv('DB_USER', 'ai'),
                    'password': os.getenv('DB_PASSWORD', 'ai_pwd'),
                    'database': os.getenv('DB_NAME', 'ai_radar')
                }
            else:
                db_config = {
                    'host': db_secrets['host'],
                    'port': int(db_secrets['port']),
                    'user': db_secrets['username'],
                    'password': db_secrets['password'],
                    'database': db_secrets['database']
                }
            
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                host=db_config['host'],
                port=db_config['port'],
                user=db_config['user'],
                password=db_config['password'],
                database=db_config['database'],
                min_size=2,
                max_size=10
            )
            
            logger.info("✅ Database connection pool created")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            return False
    
    async def get_connection(self):
        """Get database connection from pool"""
        if not self.pool:
            raise HTTPException(status_code=500, detail="Database not initialized")
        return self.pool.acquire()

class AuthenticationService:
    """Authentication service following Single Responsibility Principle"""
    
    def __init__(self, vault_client: VaultClient):
        self.vault_client = vault_client
        self.jwt_secret = None
        
    async def initialize(self):
        """Initialize authentication with secrets from Vault"""
        try:
            auth_secrets = self.vault_client.get_secret('ai-radar/auth')
            if auth_secrets:
                self.jwt_secret = auth_secrets.get('jwt_secret', 'default-secret')
                self.admin_username = auth_secrets.get('admin_username', 'admin')
                self.admin_password = auth_secrets.get('admin_password', 'adminpassword')
            else:
                # Fallback configuration
                self.jwt_secret = os.getenv('JWT_SECRET', 'your-secret-key')
                self.admin_username = os.getenv('ADMIN_USERNAME', 'admin')  # Use ADMIN_USERNAME env var
                self.admin_password = os.getenv('ADMIN_PASSWORD', 'admin')  # Use ADMIN_PASSWORD env var
                
            logger.info("✅ Authentication service initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Authentication initialization failed: {e}")
            return False
    
    def create_access_token(self, username: str) -> str:
        """Create JWT access token"""
        expire = datetime.utcnow() + timedelta(hours=1)
        to_encode = {"sub": username, "exp": expire}
        return jwt.encode(to_encode, self.jwt_secret, algorithm="HS256")
    
    def verify_token(self, token: str) -> Optional[str]:
        """Verify JWT token and return username"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            username: str = payload.get("sub")
            return username
        except jwt.PyJWTError:
            return None
    
    def authenticate_user(self, username: str, password: str) -> bool:
        """Authenticate user credentials"""
        return username == self.admin_username and password == self.admin_password

# Global instances
vault_client = VaultClient()
db_manager = DatabaseManager(vault_client)
auth_service = AuthenticationService(vault_client)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Starting AI Radar API")
    
    # Initialize Vault
    vault_success = await vault_client.initialize()
    if not vault_success:
        logger.warning("⚠️ Vault initialization failed, using fallback configuration")
    
    # Initialize services
    await auth_service.initialize()
    db_success = await db_manager.initialize()
    
    if db_success:
        logger.info("✅ All services initialized successfully")
    else:
        logger.error("❌ Critical services failed to initialize")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down AI Radar API")
    if db_manager.pool:
        await db_manager.pool.close()

# Create FastAPI app with lifespan
app = FastAPI(
    title="AI Radar API",
    description="AI-powered news radar system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React development server
        "http://127.0.0.1:3000",  # Alternative localhost
        "http://localhost:3001",  # Alternative React port
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Dependency for authentication
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get current authenticated user"""
    username = auth_service.verify_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username

# Health check endpoint
@app.get("/healthz")
async def health_check():
    """Health check endpoint for service monitoring"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "services": {
            "vault": "connected" if vault_client.client and vault_client.client.is_authenticated() else "disconnected",
            "database": "connected" if db_manager.pool else "disconnected",
            "authentication": "ready" if auth_service.jwt_secret else "not_ready"
        }
    }
    
    # Return 503 if critical services are down
    if health_status["services"]["database"] == "disconnected":
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status

# Authentication endpoints
@app.post("/api/auth/login")
async def login(credentials: dict):
    """User login endpoint"""
    username = credentials.get("username")
    password = credentials.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    if auth_service.authenticate_user(username, password):
        access_token = auth_service.create_access_token(username)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"username": username}
        }
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/api/auth/users/me")
async def get_current_user_info(current_user: str = Depends(get_current_user)):
    """Get current user information"""
    return {"username": current_user, "email": f"{current_user}@example.com"}

# --- Added authentication endpoint ---
from pydantic import BaseModel

# Define models
class TokenRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class ArticleFetchRequest(BaseModel):
    url: str
    source_id: Optional[int] = None

class RssFetchRequest(BaseModel):
    url: str
    source_id: Optional[int] = None
    source_name: Optional[str] = None

@app.post("/api/auth/token", response_model=TokenResponse)
async def login_for_access_token(token_req: TokenRequest):
    # Use the centralized authentication service
    if auth_service.authenticate_user(token_req.username, token_req.password):
        access_token = auth_service.create_access_token(username=token_req.username)
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

# Statistics Endpoints
@app.get("/api/stats/articles")
async def get_article_stats(current_user: str = Depends(get_current_user)):
    """Get article statistics"""
    try:
        async with await db_manager.get_connection() as conn:
            total_articles = await conn.fetchval("SELECT COUNT(*) FROM ai_radar.articles")
            new_today = await conn.fetchval(
                "SELECT COUNT(*) FROM ai_radar.articles WHERE published_at >= date_trunc('day', NOW()) AND published_at < date_trunc('day', NOW() + interval '1 day')"
            )
            articles_last_week = await conn.fetchval(
                "SELECT COUNT(*) FROM ai_radar.articles WHERE published_at >= NOW() - interval '7 days'"
            )
            articles_last_month = await conn.fetchval(
                "SELECT COUNT(*) FROM ai_radar.articles WHERE published_at >= NOW() - interval '1 month'"
            )
            avg_similarity_score_raw = await conn.fetchval(
                "SELECT AVG(similarity_score) FROM article_similarities"
            )
            avg_similarity_score = float(avg_similarity_score_raw) if avg_similarity_score_raw is not None else 0.0

            # Placeholder for unread count until logic for 'unread' articles is defined
            unread_articles = 0 

            return {
                "total_articles": total_articles or 0,
                "new_today": new_today or 0,
                "unread": unread_articles,
                "articles_last_week": articles_last_week or 0,
                "articles_last_month": articles_last_month or 0,
                "avg_similarity_score": avg_similarity_score
            }
    except Exception as e:
        logger.error(f"Error fetching article stats: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not fetch article statistics")

@app.get("/api/stats/sources")
async def get_source_stats(current_user: str = Depends(get_current_user)):
    """Get source statistics"""
    try:
        async with await db_manager.get_connection() as conn:
            # Get total sources count
            total_sources_query = "SELECT COUNT(*) FROM ai_radar.sources"
            total_sources = await conn.fetchval(total_sources_query)
            
            # Get new sources added today
            new_today_query = "SELECT COUNT(*) FROM ai_radar.sources WHERE DATE(created_at) = CURRENT_DATE"
            new_today = await conn.fetchval(new_today_query)
            
            # Calculate average articles per source
            avg_articles_query = """
                SELECT COALESCE(AVG(article_count), 0) FROM (
                    SELECT source_id, COUNT(*) as article_count 
                    FROM ai_radar.articles 
                    GROUP BY source_id
                ) AS source_articles
            """
            avg_articles_per_source = await conn.fetchval(avg_articles_query)
            
            # Get top sources by article count
            top_sources_query = """
                SELECT s.name, COUNT(a.id) as article_count 
                FROM ai_radar.sources s
                JOIN ai_radar.articles a ON s.id = a.source_id
                GROUP BY s.id, s.name
                ORDER BY article_count DESC
                LIMIT 5
            """
            top_sources_rows = await conn.fetch(top_sources_query)
            
            # Format top sources
            top_sources = []
            for row in top_sources_rows:
                top_sources.append({
                    "name": row["name"],
                    "article_count": row["article_count"]
                })
            
            return {
                "total_sources": total_sources,
                "new_today": new_today,
                "avg_articles_per_source": float(avg_articles_per_source) if avg_articles_per_source else 0.0,
                "top_sources": top_sources
            }
    except Exception as e:
        logger.error(f"Error getting source stats: {e}")
        # Fallback to placeholder data if there's an error
        return {
            "total_sources": 0,
            "new_today": 0,
            "avg_articles_per_source": 0.0,
            "top_sources": []
        }

@app.get("/api/articles/over-time")
async def get_articles_over_time(
    days: int = 30, 
    interval: str = "day",
    current_user: str = Depends(get_current_user)
):
    """Get articles published over time
    
    Args:
        days: Number of days to look back
        interval: Aggregation interval ('day', 'week', or 'month')
    """
    try:
        # Validate interval
        if interval not in ["day", "week", "month"]:
            interval = "day"
            
        async with await db_manager.get_connection() as conn:
            # Use date_trunc to aggregate by the specified interval
            query = f"""
                SELECT 
                    date_trunc($1, published_at)::date as time_period,
                    COUNT(*) as count
                FROM 
                    ai_radar.articles
                WHERE 
                    published_at >= NOW() - interval '$2 days'
                GROUP BY 
                    time_period
                ORDER BY 
                    time_period ASC
            """
            
            results = await conn.fetch(query, interval, days)
            
            # Format the results
            time_series = []
            for row in results:
                time_series.append({
                    "date": row["time_period"].isoformat(),
                    "count": row["count"]
                })
                
            # If we don't have any results, provide some empty data
            if not time_series:
                logger.warning("No article time series data found in the database")
                
            return time_series
    except Exception as e:
        logger.error(f"Error getting articles over time: {e}")
        # Return empty list to avoid frontend errors
        return []

# Agent integration endpoints
@app.post("/api/fetch/article", response_model=dict)
async def trigger_article_fetch(article_request: ArticleFetchRequest, current_user: str = Depends(get_current_user)):
    """Trigger the fetching of a specific article URL"""
    try:
        # Create a NATS connection to send the task
        nc = await nats.connect(os.getenv("NATS_URL", "nats://nats:4222"))
        js = nc.jetstream()
        
        # Prepare the fetch request
        fetch_data = {
            "url": article_request.url,
            "source_id": article_request.source_id,
            "triggered_by": "api",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to the article fetch subject
        subject = f"{os.getenv('NATS_SUBJECT_PREFIX', 'ai-radar')}.tasks.article_fetch"
        await js.publish(subject, json.dumps(fetch_data).encode())
        await nc.close()
        
        return {"status": "success", "message": f"Article fetch triggered for {article_request.url}"}
    except Exception as e:
        logger.error(f"Error triggering article fetch: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger article fetch: {str(e)}")

@app.post("/api/fetch/rss", response_model=dict)
async def trigger_rss_fetch(rss_request: RssFetchRequest, current_user: str = Depends(get_current_user)):
    """Trigger the fetching of an RSS feed"""
    try:
        # Create a NATS connection to send the task
        nc = await nats.connect(os.getenv("NATS_URL", "nats://nats:4222"))
        js = nc.jetstream()
        
        # Prepare the fetch request
        fetch_data = {
            "url": rss_request.url,
            "source_id": rss_request.source_id,
            "source_name": rss_request.source_name or "",
            "triggered_by": "api",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to the RSS fetch subject
        subject = f"{os.getenv('NATS_SUBJECT_PREFIX', 'ai-radar')}.tasks.rss_fetch"
        await js.publish(subject, json.dumps(fetch_data).encode())
        await nc.close()
        
        return {"status": "success", "message": f"RSS fetch triggered for {rss_request.url}"}
    except Exception as e:
        logger.error(f"Error triggering RSS fetch: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger RSS fetch: {str(e)}")

# Sources endpoints
@app.get("/api/sources")
async def get_sources(current_user: str = Depends(get_current_user)):
    """Get all article sources"""
    try:
        async with await db_manager.get_connection() as conn:
            result = await conn.fetch("""
                SELECT s.*, 
                    COUNT(a.id) as article_count, 
                    MAX(a.published_at) as last_updated 
                FROM ai_radar.sources s 
                LEFT JOIN ai_radar.articles a ON s.id = a.source_id 
                GROUP BY s.id 
                ORDER BY last_updated DESC NULLS LAST
            """)
            
            sources = []
            for r in result:
                source_dict = dict(r)
                # Convert datetime to ISO format string for JSON serialization
                if source_dict.get('last_updated'):
                    source_dict['last_updated'] = source_dict['last_updated'].isoformat()
                if source_dict.get('created_at'):
                    source_dict['created_at'] = source_dict['created_at'].isoformat()
                if source_dict.get('updated_at'):
                    source_dict['updated_at'] = source_dict['updated_at'].isoformat()
                # Ensure properties expected by the frontend are present even if null
                source_dict['url'] = source_dict.get('url', '')
                source_dict['name'] = source_dict.get('name', 'Unknown Source').upper()  # Frontend expects uppercase
                source_dict['type'] = source_dict.get('type', 'rss')
                sources.append(source_dict)
                
            return sources
    except Exception as e:
        logger.error(f"Error fetching sources: {e}")
        # Return empty list with minimal structure to avoid frontend errors
        return []

@app.post("/api/sources")
async def create_source(source_data: dict, current_user: str = Depends(get_current_user)):
    """Create a new source and trigger initial fetch"""
    try:
        # Validate required fields
        if not source_data.get("name"):
            raise HTTPException(status_code=400, detail="Source name is required")
        if not source_data.get("url"):
            raise HTTPException(status_code=400, detail="Source URL is required")
            
        # Ensure type is set
        source_type = source_data.get("type", "rss")
        
        async with await db_manager.get_connection() as conn:
            # Create the source
            query = """
                INSERT INTO sources 
                (name, url, type, description, created_at, updated_at) 
                VALUES ($1, $2, $3, $4, NOW(), NOW()) 
                RETURNING id, name, url, type, description, created_at, updated_at
            """
            source_record = await conn.fetchrow(
                query, 
                source_data["name"], 
                source_data["url"], 
                source_type,
                source_data.get("description", "")
            )
            
            if source_record:
                new_source = dict(source_record)
                # Convert datetime to ISO string for JSON serialization
                if new_source.get('created_at'):
                    new_source['created_at'] = new_source['created_at'].isoformat()
                if new_source.get('updated_at'):
                    new_source['updated_at'] = new_source['updated_at'].isoformat()
                    
                # If it's an RSS source, trigger an initial fetch
                if source_type.lower() == "rss":
                    try:
                        # Create a NATS connection to send the task
                        nc = await nats.connect(os.getenv("NATS_URL", "nats://nats:4222"))
                        js = nc.jetstream()
                        
                        # Prepare the fetch request
                        fetch_data = {
                            "url": new_source["url"],
                            "source_id": new_source["id"],
                            "source_name": new_source["name"],
                            "triggered_by": "api",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        
                        # Send to the RSS fetch subject
                        subject = f"{os.getenv('NATS_SUBJECT_PREFIX', 'ai-radar')}.tasks.rss_fetch"
                        await js.publish(subject, json.dumps(fetch_data).encode())
                        await nc.close()
                        
                        new_source["fetch_triggered"] = True
                    except Exception as fetch_err:
                        logger.error(f"Error triggering initial RSS fetch: {fetch_err}")
                        new_source["fetch_triggered"] = False
                        new_source["fetch_error"] = str(fetch_err)
                
                return new_source
            else:
                raise HTTPException(status_code=500, detail="Failed to create source")
    except Exception as e:
        logger.error(f"Error creating source: {e}")
        raise HTTPException(status_code=500, detail="Failed to create source")

# Trending articles endpoint
@app.get("/api/trending")
async def get_trending_articles(days: int = 7, limit: int = 10):
    """Get trending articles"""
    try:
        async with await db_manager.get_connection() as conn:
            # Example query - adjust based on your schema
            query = """
                SELECT id, title, url, source_id, published_at, summary, content, importance_score, created_at, updated_at, author
                FROM ai_radar.articles 
                WHERE created_at >= NOW() - ($2::integer * INTERVAL '1 day')
                ORDER BY importance_score DESC, created_at DESC
                LIMIT $1
            """
            # Ensure 'days' is passed as a parameter for the interval calculation
            db_articles = await conn.fetch(query, limit, days)
            
            processed_articles = []
            for article_row in db_articles:
                article_dict = dict(article_row)
                # Ensure importance_score is present and is a float, default to 0.0 if None
                article_dict['importance_score'] = float(article_dict.get('importance_score') or 0.0)
                # Add missing columns with default values for API compatibility
                article_dict['sentiment_score'] = 0.0  # Default sentiment score
                article_dict['fetched_at'] = article_dict.get('created_at')  # Use created_at as fallback
                processed_articles.append(article_dict)
            return processed_articles
    except Exception as e:
        logger.error(f"Error fetching trending articles: {e}")
        # Return mock data if database query fails, including importance_score
        return [
            {
                "id": "mock-id-1",
                "title": "Mock: AI Revolution in Tech Industry",
                "summary": "Mock: Latest developments in artificial intelligence...",
                "url": "https://example.com/mock-ai-revolution",
                "source_id": "mock-source-id",
                "published_at": datetime.utcnow().isoformat(),
                "fetched_at": datetime.utcnow().isoformat(),
                "content": "Mock content",
                "sentiment_score": 0.5,
                "importance_score": 0.85, # Added mock importance_score
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)