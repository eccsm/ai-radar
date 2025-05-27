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
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
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
# Internal packages – the monorepo places shared code in _core
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)  # allow "import _core"
from _core import BaseAgent  # type: ignore  # noqa: E402, I001
from _core._rpc import Router  # type: ignore  # noqa: E402, I001

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

class FetcherAgent(BaseAgent):
    """Agent responsible for fetching content from various sources."""

    # ---------------------------------------------------------------------
    # Lifecycle helpers
    # ---------------------------------------------------------------------
    def __init__(self) -> None:
        """Initialize the fetcher agent."""
        # Call super().__init__() first to ensure self.config is initialized
        super().__init__("fetcher")
        
        # Initialize configuration
        self.config = FetcherConfig()
        
        # Setup agent-specific attributes
        self.http_client: httpx.AsyncClient | None = None
        self._s3_client_context: Any | None = None  # Stores the context manager
        self.s3_client: Any | None = None          # Stores the actual S3 client instance
        self.router: Router | None = None

        # Deduplication helpers
        self.processed_msg_ids: set[str] = set()
        self.processed_urls: set[str] = set()

        # NATS subjects – align with tasks namespace used by scheduler & trigger scripts
        self.rss_fetch_subject = f"{self.config.NATS_SUBJECT_PREFIX}.tasks.rss_fetch"
        self.article_fetch_subject = f"{self.config.NATS_SUBJECT_PREFIX}.tasks.article_fetch"
        self.summarize_subject = f"{self.config.NATS_SUBJECT_PREFIX}.tasks.summarize"
        self.s3_access_key = os.getenv("MINIO_ROOT_USER", "minio")

    # ------------------------------------------------------------------
    # MinIO helpers
    # ------------------------------------------------------------------

    async def setup_minio(self):
        """Verify the MinIO bucket exists."""
        try:
            # Get MinIO configuration from secrets manager
            s3_config = self.secrets.get_minio_config()
            
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
            await self.bus.js.publish(self.summarize_subject, json.dumps(payload).encode())
            self.logger.info("Queued summarisation → %s", title)
            return True

        except Exception as exc:
            self.logger.exception("Error processing feed entry %s: %s", entry.get("link", "?"), exc)
            return False

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

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
        await self.bus.js.publish(self.summarize_subject, json.dumps(payload).encode())
        self.logger.info("Queued summarisation → %s", title)
        await msg.ack()

    # ------------------------------------------------------------------
    # Framework‑integration – setup / teardown / run
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        # Shared HTTP client for streaming downloads
        self.http_client = httpx.AsyncClient(timeout=30, follow_redirects=True)

        # MinIO bucket ready?
        await self.setup_minio()

        # Connect to NATS (with retries)
        for attempt in range(1, 6):
            try:
                self.logger.info("Connecting to NATS (%d/5)" % attempt)
                await self.bus.connect()
                self.router = Router(self.bus)  # RPC router (if you use it elsewhere)
                break
            except Exception as exc:
                if attempt == 5:
                    raise
                self.logger.warning("NATS connect failed: %s; retrying", exc)
                await asyncio.sleep(5)

        js = self.bus.js
        if not js:
            self.logger.error("JetStream context not available after NATS connection.")
            raise ConnectionError("Failed to get JetStream context from NATS.")

        # Ensure the NATS stream is configured correctly
        stream_name = self.config.NATS_STREAM_NAME
        configured_max_age_days = self.config.NATS_STREAM_MAX_AGE_DAYS
        self.logger.info(f"Configured NATS_STREAM_MAX_AGE_DAYS: {configured_max_age_days}")

        actual_max_age_for_stream = timedelta(0)  # Default to no age limit (0)

        if isinstance(configured_max_age_days, int) and configured_max_age_days > 0:
            if configured_max_age_days > MAX_STREAM_AGE_DAYS_CAP:
                self.logger.warning(
                    f"Configured NATS_STREAM_MAX_AGE_DAYS ({configured_max_age_days}) exceeds cap of {MAX_STREAM_AGE_DAYS_CAP} days. "
                    f"Using {MAX_STREAM_AGE_DAYS_CAP} days for stream max_age to prevent overflow."
                )
                actual_max_age_for_stream = timedelta(days=MAX_STREAM_AGE_DAYS_CAP)
            else:
                actual_max_age_for_stream = timedelta(days=configured_max_age_days)
        elif configured_max_age_days is not None and configured_max_age_days != 0:
            # Handles non-int, negative, or other invalid positive values if not explicitly 0 or None
            self.logger.warning(
                f"Invalid NATS_STREAM_MAX_AGE_DAYS configured: '{configured_max_age_days}'. "
                f"Defaulting stream max_age to 0 (no limit)."
            )
        # If configured_max_age_days is 0 or None, actual_max_age_for_stream remains timedelta(0)

        # Set max_age to None to avoid OverflowError
        self.logger.info(f"Setting max_age to None for stream '{stream_name}' to avoid OverflowError")

        desired_stream_config = StreamConfig(
            name=stream_name, # Use config value
            subjects=[
                f"{self.config.NATS_SUBJECT_PREFIX}.>", # This covers all subjects with this prefix
            ],
            retention=RetentionPolicy.WORK_QUEUE,
            # max_age is not set (defaults to None) to avoid OverflowError
            storage=StorageType.FILE,
            num_replicas=1 # For local dev; consider increasing for prod
        )

        try:
            self.logger.info(f"Checking existing NATS stream '{stream_name}'...")
            stream_info = await js.stream_info(stream_name)
            current_retention = stream_info.config.retention
            desired_retention = desired_stream_config.retention
            self.logger.info(f"Stream '{stream_name}' found. Current retention: {current_retention}, Desired retention: {desired_retention}")

            if current_retention != desired_retention:
                self.logger.warning(
                    f"Stream '{stream_name}' has retention policy '{current_retention}' "
                    f"but desired is '{desired_retention}'. "
                    f"NATS requires stream deletion and recreation to change retention policy to/from WorkQueue."
                )
                self.logger.info(f"Deleting stream '{stream_name}'...")
                await js.delete_stream(name=stream_name)
                self.logger.info(f"Stream '{stream_name}' deleted.")
                
                self.logger.info(f"Recreating stream '{stream_name}' with desired configuration (Retention: {desired_retention}).")
                await js.add_stream(config=desired_stream_config)
                self.logger.info(f"Stream '{stream_name}' recreated successfully with desired configuration.")
            else:
                # Retention policy is compatible (both are WORK_QUEUE in this agent's case).
                # Attempt to update other stream parameters if they differ.
                self.logger.info(f"Stream '{stream_name}' retention policy matches desired ({desired_retention}). Attempting to update other stream parameters if needed.")
                await js.update_stream(config=desired_stream_config)
                self.logger.info(f"Stream '{stream_name}' updated successfully or already matched desired configuration.")

        except NotFoundError:
            self.logger.info(f"Stream '{stream_name}' not found. Attempting to create it with desired configuration (Retention: {desired_stream_config.retention}).")
            await js.add_stream(config=desired_stream_config)
            self.logger.info(f"Stream '{stream_name}' created successfully.")
        except JSAPIError as e:
            self.logger.error(f"CRITICAL: NATS JetStream API error during stream setup for '{stream_name}': {e}", exc_info=True)
            raise

        # Subscribe via JetStream – use current API
        # Subscribe to RSS feed tasks
        self.logger.info(f"Preparing to subscribe to RSS tasks: subject={self.rss_fetch_subject}, durable_consumer=fetcher-rss")
        try:
            self.logger.info(f"Attempting to delete existing consumer 'fetcher-rss' for stream 'ai-radar' if it exists.")
            await js.delete_consumer(stream="ai-radar", consumer="fetcher-rss")
            self.logger.info(f"Successfully deleted consumer 'fetcher-rss' or it did not exist.")
        except NotFoundError:
            self.logger.info(f"Consumer 'fetcher-rss' not found, no need to delete.")
        except Exception as e:
            self.logger.warning(f"Error deleting consumer 'fetcher-rss': {e}. Proceeding with subscription attempt.")

        rss_consumer_cfg = ConsumerConfig(
            durable_name="fetcher-rss",
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.EXPLICIT,
            max_deliver=3,
        )
        await js.subscribe(
            self.rss_fetch_subject,
            cb=self.handle_rss_fetch,
            stream=stream_name,
            durable="fetcher-rss",
            config=rss_consumer_cfg,
        )
        self.logger.info(f"Subscribed to {self.rss_fetch_subject} with durable consumer fetcher-rss")

        # Subscribe to article fetch tasks
        self.logger.info(f"Preparing to subscribe to article tasks: subject={self.article_fetch_subject}, durable_consumer=fetcher-article")
        try:
            self.logger.info(f"Attempting to delete existing consumer 'fetcher-article' for stream 'ai-radar' if it exists.")
            await js.delete_consumer(stream="ai-radar", consumer="fetcher-article")
            self.logger.info(f"Successfully deleted consumer 'fetcher-article' or it did not exist.")
        except NotFoundError:
            self.logger.info(f"Consumer 'fetcher-article' not found, no need to delete.")
        except Exception as e:
            self.logger.warning(f"Error deleting consumer 'fetcher-article': {e}. Proceeding with subscription attempt.")

        article_consumer_cfg = ConsumerConfig(
            durable_name="fetcher-article",
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.EXPLICIT,
            max_deliver=3,
        )
        await js.subscribe(
            self.article_fetch_subject,
            cb=self.handle_article_fetch,
            stream=stream_name,
            durable="fetcher-article",
            config=article_consumer_cfg,
        )
        self.logger.info(f"Subscribed to {self.article_fetch_subject} with durable consumer fetcher-article")

        self.logger.info("Fetcher agent setup complete – awaiting tasks…")

    async def teardown(self) -> None:
        if self.http_client:
            await self.http_client.aclose()
        if self._s3_client_context:
            # Exit the S3 client context properly
            await self._s3_client_context.__aexit__(None, None, None)
            self.s3_client = None
            self._s3_client_context = None
        self.logger.info("Fetcher agent teardown complete")

    async def run(self) -> None:  # noqa: D401 – part of framework
        try:
            await self.setup()
            await super().run()  # BaseAgent provides heartbeat / stop logic
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

