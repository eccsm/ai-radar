#!/usr/bin/env python3
# scheduler/main.py - Service to periodically trigger source fetching

import os
import asyncio
import logging
import json
import httpx
from datetime import datetime
import nats
from nats.js import JetStreamContext
import asyncpg
from typing import List, Dict, Any, Optional
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("scheduler")

class SchedulerService:
    """Service to periodically schedule data fetching tasks"""
    
    def __init__(self):
        self.db_pool = None
        self.nats_client = None
        self.jetstream = None
        self.api_base_url = os.getenv("API_BASE_URL", "http://api:8000")
        self.api_token = None
        self.running = False
        
        # Default intervals (in seconds)
        self.fetch_interval = int(os.getenv("FETCH_INTERVAL", "1800"))  # 30 minutes
        self.stats_interval = int(os.getenv("STATS_INTERVAL", "3600"))  # 1 hour
        self.auth_interval = int(os.getenv("AUTH_INTERVAL", "3600"))   # 1 hour (token refresh)
        
    async def initialize(self):
        """Initialize connections to database and NATS"""
        try:
            # Initialize database connection
            self.db_pool = await asyncpg.create_pool(
                host=os.getenv("DB_HOST", "db"),
                port=int(os.getenv("DB_PORT", "5432")),
                user=os.getenv("DB_USER", "ai"),
                password=os.getenv("DB_PASSWORD", "ai_pwd"),
                database=os.getenv("DB_NAME", "ai_radar"),
                min_size=2,
                max_size=5,
            )
            logger.info("✅ Database connection pool created")
            
            # Initialize NATS connection
            self.nats_client = await nats.connect(os.getenv("NATS_URL", "nats://nats:4222"))
            self.jetstream = self.nats_client.jetstream()
            logger.info("✅ Connected to NATS JetStream")

            # Ensure the NATS stream for tasks exists
            stream_name = os.getenv("NATS_STREAM_NAME", "ai-radar-tasks")
            # Subjects for the stream, e.g., "ai-radar.tasks.>"
            stream_subjects = [f"{os.getenv('NATS_SUBJECT_PREFIX', 'ai-radar')}.tasks.>"]
            
            try:
                stream_info = await self.jetstream.stream_info(stream_name)
                logger.info(f"ℹ️ NATS stream '{stream_name}' already exists.")
                current_config = stream_info.config
                # Ensure all desired subjects are present
                needs_update = False
                if not all(s in current_config.subjects for s in stream_subjects):
                    needs_update = True
                    # Add new subjects without removing existing ones, unless a strict match is required
                    updated_subjects = list(set(current_config.subjects + stream_subjects))
                
                if needs_update:
                    logger.info(f"Updating subjects for stream '{stream_name}' to include: {stream_subjects}")
                    current_config.subjects = updated_subjects # Or strictly stream_subjects if preferred
                    await self.jetstream.update_stream(config=current_config)
                    logger.info(f"✅ Updated NATS stream '{stream_name}' config.")
                else:
                    logger.info(f"Stream '{stream_name}' subjects configuration is up-to-date.")

            except nats.js.errors.NotFoundError:  # Correct exception for stream not found
                logger.info(f"NATS stream '{stream_name}' not found. Creating it with subjects: {stream_subjects}")
                await self.jetstream.add_stream(name=stream_name, subjects=stream_subjects)
                logger.info(f"✅ Created NATS stream '{stream_name}'.")
            except Exception as e:
                logger.error(f"❌ Failed to ensure NATS stream '{stream_name}': {e}. This might affect publishing tasks.")
                # Depending on policy, you might want to raise e or return False here

            # Get initial auth token
            await self.refresh_auth_token()
            
            return True
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False
            
    async def refresh_auth_token(self):
        """Get authentication token from API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base_url}/api/auth/token",
                    json={
                        "username": os.getenv("ADMIN_USERNAME", "admin"),
                        "password": os.getenv("ADMIN_PASSWORD", "admin")
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.api_token = data.get("access_token")
                    logger.info("✅ Authentication token refreshed")
                    return True
                else:
                    logger.error(f"❌ Failed to get auth token: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"❌ Error refreshing auth token: {e}")
            return False
    
    async def get_all_sources(self) -> List[Dict[str, Any]]:
        """Get all sources from the database"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetch("""
                    SELECT s.*, 
                        COUNT(a.id) as article_count, 
                        MAX(a.published_at) as last_updated 
                    FROM sources s 
                    LEFT JOIN articles a ON s.id = a.source_id 
                    GROUP BY s.id 
                    ORDER BY last_updated DESC NULLS LAST
                """)
                
                sources = []
                for row in result:
                    source = dict(row)
                    # Convert datetime objects to ISO strings
                    for key, value in source.items():
                        if isinstance(value, datetime):
                            source[key] = value.isoformat()
                    sources.append(source)
                
                logger.info(f"Retrieved {len(sources)} sources from database")
                return sources
        except Exception as e:
            logger.error(f"❌ Error getting sources: {e}")
            return []
    
    async def trigger_rss_fetch(self, source: Dict[str, Any]) -> bool:
        """Trigger RSS fetch task via NATS JetStream"""
        try:
            # Convert UUID to string for JSON serialization
            source_id = str(source["id"]) if source["id"] is not None else None
            
            # Prepare the fetch request
            fetch_data = {
                "url": source["url"],
                "source_id": source_id,
                "source_name": source.get("name", ""),
                "triggered_by": "scheduler",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to the RSS fetch subject
            subject = f"{os.getenv('NATS_SUBJECT_PREFIX', 'ai-radar')}.tasks.rss_fetch"
            await self.jetstream.publish(subject, json.dumps(fetch_data).encode())
            
            logger.info(f"RSS fetch triggered for source {source['name']} (ID: {source_id})")
            return True
        except Exception as e:
            logger.error(f"❌ Error triggering RSS fetch for source {source.get('id')}: {e}")
            return False
    
    async def process_sources(self):
        """Process all sources and trigger appropriate fetch tasks"""
        sources = await self.get_all_sources()
        
        if not sources:
            logger.warning("No sources found to process")
            return
        
        for source in sources:
            source_type = source.get("type", "rss").lower()
            
            if source_type == "rss":
                await self.trigger_rss_fetch(source)
            else:
                logger.warning(f"Unsupported source type: {source_type} for source {source.get('id')}")
    
    async def auth_token_refresh_task(self):
        """Task to periodically refresh authentication token"""
        while self.running:
            await asyncio.sleep(self.auth_interval)
            await self.refresh_auth_token()
    
    async def source_processing_task(self):
        """Task to periodically process sources"""
        while self.running:
            logger.info("Starting source processing cycle")
            await self.process_sources()
            logger.info(f"Source processing complete. Sleeping for {self.fetch_interval} seconds")
            await asyncio.sleep(self.fetch_interval)
    
    async def run(self):
        """Run the scheduler service"""
        self.running = True
        
        try:
            # Start the periodic tasks as background tasks
            auth_task = asyncio.create_task(self.auth_token_refresh_task())
            source_task = asyncio.create_task(self.source_processing_task())
            
            # Keep the service running
            while self.running:
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("Service shutdown requested")
            self.running = False
            
        except Exception as e:
            logger.error(f"❌ Error in scheduler service: {e}")
            self.running = False
            
        finally:
            # Clean up
            if self.db_pool:
                await self.db_pool.close()
            if self.nats_client:
                await self.nats_client.close()
            logger.info("Service shutdown complete")

# Simple HTTP server for health checks
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/healthz':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress logging of HTTP requests to avoid cluttering logs
        pass

def start_health_server(port=8000):
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"Health check server running on port {port}")
    server.serve_forever()

async def main():
    """Main entry point for the scheduler service"""
    logger.info("🚀 Starting Scheduler Service")
    
    # Start health check server in a separate thread
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    logger.info("✅ Health check server started")
    
    scheduler = SchedulerService()
    initialized = await scheduler.initialize()
    
    if initialized:
        logger.info("✅ Scheduler service initialized successfully")
        await scheduler.run()
    else:
        logger.error("❌ Failed to initialize scheduler service")

if __name__ == "__main__":
    asyncio.run(main())
