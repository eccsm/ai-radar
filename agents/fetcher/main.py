#!/usr/bin/env python
"""
AI‑Radar – Fetcher Agent
========================
Responsible for pulling RSS feeds or single article URLs, storing raw content in
MinIO, and enqueueing a summarisation task via NATS JetStream.

Key changes (May 2025)
----------------------
* Updated to the current **nats‑py** API – subscriptions now pass a
  ``ConsumerConfig`` instead of individual keyword arguments such as
  ``durable_name``.
* Removed the duplicate ``fetch_article`` definition.
* Re‑used the shared ``self.s3_client`` opened in ``setup_minio`` for uploads
  (no more client‑per‑article overhead).
* Tidied imports and logging initialisation.
* Added Vault integration to fetch secrets during agent initialization
"""

from __future__ import annotations
import os
import asyncio
import logging
import sys
import tempfile
import time
import json
import uuid
import httpx

# Import SecretsManager for fetching secrets
try:
    # Try to import from parent _core first
    from _core.secrets import SecretsManager
except ImportError:
    try:
        # Fallback for local development
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from _core.secrets import SecretsManager
    except ImportError:
        # Create a simple fallback SecretsManager
        import logging
        class SecretsManager:
            def __init__(self, logger=None):
                self.logger = logger or logging.getLogger(__name__)
            
            def get_minio_config(self):
                return {
                    "endpoint": os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
                    "access_key": os.getenv("MINIO_ACCESS_KEY", "minio"),
                    "secret_key": os.getenv("MINIO_SECRET_KEY", "minio_pwd"),
                    "bucket": os.getenv("BUCKET_NAME", "ai-radar-content")
                }
            
            def get_newsapi_key(self):
                return os.getenv("NEWSAPI_KEY", "")
import hashlib
import traceback
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Dict

import aioboto3
import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser  # noqa: F401 – kept for possible future use
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, StreamConfig, StorageType, RetentionPolicy
from nats.js import errors as NatsJSErrors
from nats.js.errors import NotFoundError, APIError as JSAPIError

# ---------------------------------------------------------------------------
# Simplified base agent implementation
# ---------------------------------------------------------------------------
import nats
import asyncpg

class SimpleAgent:
    """Simplified agent base class."""
    def __init__(self, name):
        self.name = name
        self.logger = logging.getLogger(name)
        self.secrets = SecretsManager(self.logger)
        self.js = None
        self.nc = None
        self.db = None
        
    async def setup_nats(self):
        """Connect to NATS."""
        nats_url = os.getenv("NATS_URL", "nats://nats:4222")
        self.nc = await nats.connect(nats_url)
        self.js = self.nc.jetstream()
        
    async def setup_db(self):
        """Connect to database."""
        db_url = os.getenv("POSTGRES_URL", "postgresql://ai:ai_pwd@db:5432/ai_radar")
        self.db = await asyncpg.connect(db_url)
        
    async def increment_message_count(self):
        """Placeholder for metrics."""
        pass
        
    async def increment_error_count(self):
        """Placeholder for metrics."""
        pass

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------
BUCKET_NAME = os.getenv("BUCKET_NAME", "ai-radar-content")
MINIO_ENDPOINT = os.getenv("MINIO_URL", "http://minio:9000")

# Define a reasonable maximum for stream age in days to prevent overflow
# NATS int64 nanoseconds limit is ~292 years. 100 years is a safe cap.
MAX_STREAM_AGE_DAYS_CAP = 365 * 100


class FetcherConfig:
    """Configuration for the Fetcher Agent."""
    
    def __init__(self):
        """Initialize with default values from environment variables."""
        self.NATS_SUBJECT_PREFIX = os.getenv("NATS_SUBJECT_PREFIX", "ai-radar")
        self.NATS_STREAM_NAME = os.getenv("NATS_STREAM_NAME", "ai-radar")
        self.NATS_STREAM_MAX_AGE_DAYS = 7  # Default to 7 days

class FetcherAgent(SimpleAgent):
    """Agent responsible for fetching content from various sources."""

    # ---------------------------------------------------------------------
    # Lifecycle helpers
    # ---------------------------------------------------------------------
    def __init__(self) -> None:
        """Initialize the fetcher agent."""
        super().__init__("fetcher")
        
        # Initialize configuration
        self.config = FetcherConfig()
        
        # Setup agent-specific attributes
        self.http_client: httpx.AsyncClient | None = None
        self._s3_client_context: Any | None = None  # Stores the context manager
        self.s3_client: Any | None = None          # Stores the actual S3 client instance

        # Deduplication helpers
        self.processed_msg_ids: set[str] = set()
        self.processed_urls: set[str] = set()

        # NATS subjects – align with tasks namespace used by scheduler & trigger scripts
        self.rss_fetch_subject = f"{self.config.NATS_SUBJECT_PREFIX}.tasks.rss_fetch"
        self.article_fetch_subject = f"{self.config.NATS_SUBJECT_PREFIX}.tasks.article_fetch"
        self.summarize_subject = f"{self.config.NATS_SUBJECT_PREFIX}.tasks.summarize"

    # ------------------------------------------------------------------
    # MinIO helpers
    # ------------------------------------------------------------------

    async def setup_services(self):
        """Set up the various services used by this agent."""
        # Initialize secrets and fetch necessary secrets first
        await self.setup_secrets()
        
        # Now set up other services
        await self.setup_db()
        await self.setup_nats()
        await self.setup_minio()
        
    async def setup_secrets(self):
        """Initialize SecretsManager and fetch necessary secrets."""
        try:
            # Get NewsAPI key
            newsapi_key = self.secrets.get_newsapi_key()
            if newsapi_key:
                os.environ['NEWSAPI_KEY'] = newsapi_key
                self.logger.info("Successfully loaded NewsAPI key")
            else:
                self.logger.warning("Could not find NewsAPI key, some feeds may not work")
                
        except Exception as e:
            self.logger.error(f"Error setting up secrets manager: {e}")
            self.logger.info("Continuing with environment variables for secrets")

    async def setup_minio(self):
        """Verify the MinIO bucket exists."""
        try:
            # Get MinIO configuration from secrets manager
            s3_config = self.secrets.get_minio_config()
            self.logger.info(f"MinIO config from secrets: {s3_config}")
            
            # Create a session with the appropriate credentials
            session = aioboto3.Session()
            self._s3_client_context = session.client(
                's3',
                endpoint_url=s3_config["endpoint"],
                aws_access_key_id=s3_config["access_key"],
                aws_secret_access_key=s3_config["secret_key"],
            )
            
            # Enter the context manager to get the actual client
            self.s3_client = await self._s3_client_context.__aenter__()
            
            # Check if bucket exists, create if not
            bucket_name = s3_config["bucket"]
            try:
                await self.s3_client.head_bucket(Bucket=bucket_name)
                self.logger.info(f"Bucket {bucket_name} exists")
            except Exception:
                self.logger.info(f"Creating bucket {bucket_name}")
                await self.s3_client.create_bucket(Bucket=bucket_name)
                
        except Exception as e:
            self.logger.error(f"Error setting up MinIO: {e}", exc_info=True)
            await self.increment_error_count()
            raise

    # ------------------------------------------------------------------
    # RSS helpers
    # ------------------------------------------------------------------

    async def process_feed_entry(
        self,
        entry: Any,
        source_name: str,
        source_url: str,
    ) -> bool:
        """Extract metadata + body from one feed entry and schedule summarisation."""
        try:
            article_url: str | None = getattr(entry, "link", None)
            if not article_url:
                self.logger.debug("Entry has no link; skipping")
                return False

            # Basic metadata – be defensive because feeds are not consistent
            title = getattr(entry, "title", "No title")

            if getattr(entry, "published_parsed", None):
                published_at = datetime(*entry.published_parsed[:6])
            elif getattr(entry, "updated_parsed", None):
                published_at = datetime(*entry.updated_parsed[:6])
            else:
                published_at = datetime.utcnow()

            author = getattr(entry, "author", None)
            raw_content = (
                entry.content[0].value
                if getattr(entry, "content", None)
                else getattr(entry, "summary", "")
            )

            text_content = (
                BeautifulSoup(raw_content, "html.parser").get_text(" ", strip=True)
                if raw_content
                else ""
            )

            # Store raw text in S3 under a deterministic hash
            content_hash = hashlib.md5(article_url.encode()).hexdigest()
            s3_key = f"articles/{content_hash}.txt"
            
            # Get S3 configuration from secrets manager
            s3_config = self.secrets.get_minio_config()
            
            # Use the client in a proper context manager
            await self.s3_client.put_object(
                Bucket=s3_config["bucket"],
                Key=s3_key,
                Body=text_content.encode(),
            )

            # Emit job for summariser
            payload: Dict[str, Any] = {
                "title": title,
                "url": article_url,
                "published_at": published_at.isoformat(),
                "author": author,
                "content_key": s3_key,
                "source_name": source_name,
                "source_url": source_url,
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self.js.publish(self.summarize_subject, json.dumps(payload).encode())
            self.logger.info("Queued summarisation → %s", title)
            return True

        except Exception as exc:
            self.logger.exception("Error processing feed entry %s: %s", entry.get("link", "?"), exc)
            return False

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    async def handle_rss_fetch(self, msg: Any):
        """Handle RSS feed fetch requests."""
        try:
            data = json.loads(msg.data.decode())
            feed_url = data["url"]
            source_name = data.get("source_name", "Unknown")
            
            self.logger.info(f"Fetching RSS feed: {feed_url}")
            
            # Update metrics for health checks
            await self.increment_message_count()
            
            # Fetch the RSS feed
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(feed_url)
                response.raise_for_status()
                
            # Parse the feed
            feed = feedparser.parse(response.text)
            
            if feed.bozo:
                self.logger.warning(f"Feed has parsing errors: {feed_url}")
            
            # Process each entry in the feed
            processed_count = 0
            for entry in feed.entries:
                success = await self.process_feed_entry(entry, source_name, feed_url)
                if success:
                    processed_count += 1
            
            self.logger.info(f"Processed {processed_count} articles from {source_name}")
            await msg.ack()
            
        except Exception as e:
            self.logger.error(f"Error processing RSS feed: {e}", exc_info=True)
            await self.increment_error_count()
            await msg.ack()

    async def handle_article_fetch(self, msg: Any):
        try:
            data = json.loads(msg.data.decode())
            url: str = data["url"]
            title: str = data.get("title", "Untitled Article")
            source_name = data.get("source")

            if url in self.processed_urls:
                await msg.ack()
                return
            self.processed_urls.add(url)
                
            self.logger.info(f"Fetching article: {url}")
            
            # Update metrics for health checks
            await self.increment_message_count()
            
            # Fetch the article content
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                html_content = response.text
            
            # Parse the HTML content
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Extract title and content (simplified extraction)
            title = soup.title.text if soup.title else title or "Unknown Title"
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
                
            # Get text content
            text = soup.get_text(separator="\n", strip=True)
            
            # Generate a unique ID for the article
            article_id = hashlib.md5(url.encode()).hexdigest()
            
            # Get S3 configuration from secrets manager
            s3_config = self.secrets.get_minio_config()
            
            # Store the raw content in MinIO
            content_key = f"articles/{article_id}/raw.html"
            await self.s3_client.put_object(
                Bucket=s3_config["bucket"],
                Key=content_key,
                Body=html_content.encode()
            )
            
            # Create a summarization task
            await self.js.publish(
                self.summarize_subject,
                json.dumps({
                    "article_id": article_id,
                    "url": url,
                    "title": title,
                    "source": source_name or "Manual",
                    "content_key": content_key,
                    "timestamp": datetime.now().isoformat()
                }).encode()
            )
            
            await msg.ack()
            self.logger.info(f"Processed article: {title}")
            
        except Exception as e:
            self.logger.error(f"Error processing article: {e}", exc_info=True)
            # Update error metrics for health checks
            await self.increment_error_count()
            # Ack anyway to prevent redelivery loops
            await msg.ack()
        except Exception:
            self.logger.exception("Failed to download article %s", url)
            await msg.ack()
            return

        # Very naïve extraction; could be replaced with readability‑lxml etc.
        soup = BeautifulSoup(html, "html.parser")
        body_text = soup.get_text(" ", strip=True)

        content_hash = hashlib.md5(url.encode()).hexdigest()
        s3_key = f"articles/{content_hash}.txt"
        
        # Create a fresh S3 client for this operation to avoid "cannot reuse already awaited coroutine"
        session = aioboto3.Session()
        s3_client = session.client(
            service_name="s3",
            endpoint_url=self.s3_endpoint_url,
            aws_access_key_id=self.s3_access_key,
            aws_secret_access_key=self.s3_secret_key,
        )
        
        # Use the client in a proper context manager
        async with s3_client as s3:
            await s3.put_object(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                Body=body_text.encode(),
            )

        payload = {
            "title": title,
            "url": url,
            "published_at": datetime.utcnow().isoformat(),
            "content_key": s3_key,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.js.publish(self.summarize_subject, json.dumps(payload).encode())
        self.logger.info("Queued summarisation → %s", title)
        await msg.ack()

    # ------------------------------------------------------------------
    # Framework‑integration – setup / teardown / run
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        # Shared HTTP client for streaming downloads
        self.http_client = httpx.AsyncClient(timeout=30, follow_redirects=True)

        # Set up services using the existing method
        await self.setup_services()

        js = self.js
        if not js:
            self.logger.error("JetStream context not available after NATS connection.")
            raise ConnectionError("Failed to get JetStream context from NATS.")

        self.logger.info(f"Fetcher will subscribe to subjects on the existing NATS stream: {self.config.NATS_STREAM_NAME}")
        # Stream creation is assumed to be handled by another service (e.g., scheduler)

        # Subscribe to RSS feed tasks
        await js.subscribe(
            subject=self.rss_fetch_subject,
            durable="fetcher-rss",
            cb=self.handle_rss_fetch
        )
        self.logger.info(f"Subscribed to {self.rss_fetch_subject} with durable consumer fetcher-rss")

        # Subscribe to article fetch tasks
        await js.subscribe(
            subject=self.article_fetch_subject,
            durable="fetcher-article",
            cb=self.handle_article_fetch
        )
        self.logger.info(f"Subscribed to {self.article_fetch_subject} with durable consumer fetcher-article")

        self.logger.info("Fetcher agent setup complete – awaiting tasks…")

    async def teardown(self) -> None:
        if self.http_client:
            await self.http_client.aclose()
        if self._s3_client_context and self.s3_client:
            # Exit the S3 client context properly
            await self._s3_client_context.__aexit__(None, None, None)
            self.s3_client = None
            self._s3_client_context = None
        self.logger.info("Fetcher agent teardown complete")

    async def run(self) -> None:  # noqa: D401 – part of framework
        try:
            await self.setup()
            # Keep the agent running
            self.logger.info("Fetcher agent is running. Press Ctrl+C to stop.")
            while True:
                await asyncio.sleep(10)  # Keep alive
        except KeyboardInterrupt:
            self.logger.info("Shutdown signal received")
        finally:
            await self.teardown()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:  # pragma: no cover – simple wrapper
    agent = FetcherAgent()
    await agent.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
    asyncio.run(main())

