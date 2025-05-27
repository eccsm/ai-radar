#!/usr/bin/env python
"""
Summariser Agent - Main Module
Responsible for summarizing and embedding content for the AI Radar system.
"""
import os
import sys
import json
import asyncio
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
import tiktoken
import numpy as np
import aioboto3
from openai import AsyncOpenAI
from io import BytesIO
import asyncpg

# Add project root to sys.path to ensure absolute imports work correctly
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Use fully qualified absolute imports to avoid any confusion
from _core.health import HealthServer  # noqa: E402
from _core.secrets import SecretsManager  # noqa: E402
from agents._core._base import BaseAgent  # noqa: E402
from agents._core._rpc import Router  # noqa: E402

# Print debug info about import paths
print(f"Python path: {sys.path}")
print(f"Project root: {project_root}")

# Environment variables
BUCKET_NAME = os.getenv("BUCKET_NAME", "ai-radar-content")
MINIO_ENDPOINT = os.getenv("MINIO_URL", "http://minio:9000")

# OpenAI model configuration
EMBEDDING_MODEL = "text-embedding-3-small"
SUMMARY_MODEL = "gpt-3.5-turbo"
MAX_TOKENS = 4096  # Adjust based on model used

# Tokenizer for counting tokens
encoding = tiktoken.get_encoding("cl100k_base")


class SummariserAgent(BaseAgent):
    """Agent responsible for summarizing and embedding content."""
    
    def __init__(self):
        super().__init__("summariser")
        self.router = Router(self.bus)
        self.secrets_manager = SecretsManager()
        self.s3_client = None
        self.openai_client = None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_summary(self, text, title):
        """Generate a summary of the given text using OpenAI's models."""
        try:
            # Count tokens to ensure we don't exceed limit
            tokens = len(encoding.encode(text))
            
            # Truncate if necessary
            if tokens > MAX_TOKENS:
                self.logger.warning(f"Text too long ({tokens} tokens), truncating to {MAX_TOKENS} tokens")
                encoded_text = encoding.encode(text)[:MAX_TOKENS]
                text = encoding.decode(encoded_text)
            
            response = await self.openai_client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": "You are an AI assistant that summarizes articles about AI and technology. Create a concise summary of the following article, highlighting key points and innovations."},
                    {"role": "user", "content": f"Article title: {title}\n\nArticle text: {text}\n\nProvide a summary in 3-5 sentences."}
                ],
                max_tokens=300,
                temperature=0.3
            )
            
            summary = response.choices[0].message.content.strip()
            self.logger.info(f"Generated summary ({len(summary.split())} words)")
            return summary
        
        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_embedding(self, text):
        """Generate an embedding for the given text using OpenAI's embedding model."""
        try:
            # Prepare text for embedding
            # Combine title and content for better embedding
            
            # Count tokens to ensure we don't exceed limit
            tokens = len(encoding.encode(text))
            
            # Truncate if necessary
            if tokens > 8191:  # OpenAI's text-embedding-3-small limit
                self.logger.warning(f"Text too long for embedding ({tokens} tokens), truncating")
                encoded_text = encoding.encode(text)[:8191]
                text = encoding.decode(encoded_text)
            
            response = await self.openai_client.embeddings.create(
                input=text,
                model=EMBEDDING_MODEL
            )
            
            embedding = response.data[0].embedding
            self.logger.info(f"Generated embedding (vector dimension: {len(embedding)})")
            return embedding
        
        except Exception as e:
            self.logger.error(f"Error generating embedding: {e}")
            raise

    async def process_summarize(self, msg):
        """Process summarization task message."""
        try:
            # Parse message data
            data = json.loads(msg.data.decode())
            title = data["title"]
            url = data["url"]
            published_at = data.get("published_at", datetime.now().isoformat())
            content_key = data["content_key"]
            author = data.get("author")
            source_name = data.get("source_name")
            
            self.logger.info(f"Processing summarization for: {title}")
            
            # Use our retry_db_operation for database queries to handle connection issues
            try:
                # Check if article already exists
                existing = await self.retry_db_operation(
                    self.db.fetchval,
                    """
                    SELECT id FROM ai_radar.articles 
                    WHERE url = $1
                    """,
                    url
                )
            except Exception as db_err:
                self.logger.error(f"Database operation failed even after retries: {db_err}", exc_info=True)
                # Acknowledge message to avoid endless redelivery, but log the error
                await msg.ack()
                return
            
            if existing:
                self.logger.info(f"Article already exists with ID {existing}, skipping")
                await msg.ack()
                return
            
            # Get source ID or create if not exists
            source_id = None
            if source_name:
                try:
                    source_id = await self.retry_db_operation(
                        self.db.fetchval,
                        "SELECT id FROM ai_radar.sources WHERE name = $1", 
                        source_name
                    )
                    
                    if not source_id and data.get("source_url"):
                        source_id = await self.retry_db_operation(
                            self.db.fetchval,
                            """
                            INSERT INTO ai_radar.sources (name, url, source_type)
                            VALUES ($1, $2, 'rss')
                            RETURNING id
                            """,
                            source_name, data.get("source_url")
                        )
                except Exception as source_err:
                    self.logger.error(f"Error handling source data: {source_err}", exc_info=True)
                    # Continue without source ID rather than failing the whole process
            
            # Fetch content from S3 - create a fresh client for this operation
            self.logger.info(f"Fetching content from S3 with key: {content_key}")
            session = aioboto3.Session()
            s3_client = session.client(
                service_name="s3",
                endpoint_url=MINIO_ENDPOINT,
                aws_access_key_id=os.getenv("MINIO_ROOT_USER", "minio"),
                aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", "minio_pwd"),
            )
            
            try:
                async with s3_client as s3:
                    response = await s3.get_object(Bucket=BUCKET_NAME, Key=content_key)
                    content = await response['Body'].read()
                    content = content.decode('utf-8')
                self.logger.info(f"Successfully fetched content from S3, length: {len(content)} chars")
            except Exception as s3_error:
                self.logger.error(f"Failed to fetch content from S3: {s3_error}", exc_info=True)
                raise
            
            # Generate summary
            summary = await self.generate_summary(content, title)
            
            # Generate embedding for combined title and summary
            embedding_text = f"{title}\n\n{summary}\n\n{content[:1000]}"
            embedding = await self.generate_embedding(embedding_text)
            
            # Convert embedding to a format compatible with pgvector
            # For pgvector, we need to convert the Python list to a string representation
            # that PostgreSQL can parse as a vector
            embedding_str = f"[{','.join(map(str, embedding))}]"
            
            # Store in database with retry mechanism
            try:
                article_id = await self.retry_db_operation(
                    self.db.fetchval,
                    """
                    INSERT INTO ai_radar.articles
                    (source_id, title, url, author, published_at, content, summary, embedding, importance_score)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, $9)
                    RETURNING id
                    """,
                    source_id, title, url, author, 
                    datetime.fromisoformat(published_at), 
                    content, summary, embedding_str, 0.5  # Default importance score
                )
                
                self.logger.info(f"Stored article with ID {article_id}")
            except Exception as insert_err:
                self.logger.error(f"Failed to insert article in database: {insert_err}", exc_info=True)
                # Acknowledge message but log the error
                await msg.ack()
                return
            
            self.logger.info(f"Stored article with ID {article_id}")
            
            # Publish for ranking
            payload = {
                "article_id": article_id,
                "title": title,
                "url": url,
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }
            
            await self.bus.js.publish(
                "ai-radar.tasks.rank",
                json.dumps(payload).encode()
            )
            
            self.logger.info(f"Published for ranking: {title}")
            
            # Acknowledge message
            await msg.ack()
            
        except Exception as e:
            self.logger.error(f"Error processing summarization: {e}")
            # For serious errors, we might want to retry
            # For now, acknowledge to avoid redelivery
            await msg.ack()
    
    async def retry_db_operation(self, operation, *args, max_retries=5, **kwargs):
        """Retry a database operation with exponential backoff.
        
        Args:
            operation: Async function to retry (e.g., self.db.fetch)
            *args: Arguments to pass to the operation
            max_retries: Maximum number of retry attempts
            **kwargs: Keyword arguments to pass to the operation
            
        Returns:
            The result of the operation if successful
            
        Raises:
            Exception: If all retries fail
        """
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                return await operation(*args, **kwargs)
            except RuntimeError as e:
                if "Not connected to PostgreSQL" in str(e):
                    retries += 1
                    wait_time = 2 ** retries  # Exponential backoff
                    self.logger.warning(f"Database not connected, attempting to reconnect (attempt {retries}/{max_retries})")
                    
                    try:
                        await self.db.connect()
                        self.logger.info("Successfully reconnected to PostgreSQL")
                        # Try the operation again immediately after reconnecting
                        continue
                    except Exception as reconnect_err:
                        self.logger.error(f"Failed to reconnect to PostgreSQL: {reconnect_err}")
                        # Continue with the backoff and retry
                        
                    self.logger.info(f"Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    # If it's a different RuntimeError, re-raise it
                    raise
            except asyncpg.exceptions.TooManyConnectionsError as e:
                # Special handling for connection pool exhaustion
                retries += 1
                # Use shorter wait times for connection issues, as we just need to let connections free up
                wait_time = min(1 * retries, 5)  # Linear backoff with 5s max
                self.logger.warning(f"Too many database connections, waiting before retry (attempt {retries}/{max_retries})")
                await asyncio.sleep(wait_time)
            except asyncpg.exceptions.PostgresConnectionError as e:
                # For connection errors, try to reconnect
                retries += 1
                wait_time = 2 ** retries  # Exponential backoff
                self.logger.warning(f"PostgreSQL connection error: {e}, attempting to reconnect (attempt {retries}/{max_retries})")
                
                try:
                    await self.db.connect()
                    self.logger.info("Successfully reconnected to PostgreSQL")
                    # Try the operation again immediately after reconnecting
                    continue
                except Exception as reconnect_err:
                    self.logger.error(f"Failed to reconnect to PostgreSQL: {reconnect_err}")
                
                self.logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
            except Exception as e:
                # For other exceptions, retry with backoff
                last_error = e
                retries += 1
                wait_time = 2 ** retries
                self.logger.error(f"Database operation failed: {e}, retrying in {wait_time}s (attempt {retries}/{max_retries})")
                await asyncio.sleep(wait_time)
        
        # If we've exhausted all retries, raise the last error
        raise last_error if last_error else RuntimeError(f"Failed after {max_retries} attempts")
    
    async def setup(self):
        """Set up the summariser agent."""
        try:
            # Set up S3 client
            session = aioboto3.Session()
            self.s3_client = session.client(
                service_name="s3",
                endpoint_url=MINIO_ENDPOINT,
                aws_access_key_id=os.getenv("MINIO_ROOT_USER", "minio"),
                aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", "minio_pwd"),
            )
            
            # Set up OpenAI client
            openai_api_key_value = self.secrets_manager.get_secret("openai_key")
            if not openai_api_key_value:
                self.logger.error("OPENAI_API_KEY not found. Please ensure 'openai_key' is set in Vault or Docker secrets.")
                raise ValueError("OPENAI_API_KEY not configured")
            self.openai_client = AsyncOpenAI(api_key=openai_api_key_value)
            
            # Explicitly connect to PostgreSQL with better error handling and connection pooling
            postgres_url = self.secrets_manager.get_secret("postgres_url")
            if not postgres_url:
                self.logger.error("POSTGRES_URL not found. Please ensure 'postgres_url' is set in Vault or Docker secrets.")
                raise ValueError("POSTGRES_URL not configured")
            self.logger.info(f"Connecting to PostgreSQL with URL: {postgres_url}")
            
            # Configure optimal pool size for summarizer agent to avoid too many connections
            # Lower values than default to avoid overwhelming the database
            min_pool_size = int(os.getenv("POSTGRES_MIN_CONNECTIONS", "1"))
            max_pool_size = int(os.getenv("POSTGRES_MAX_CONNECTIONS", "5"))
            self.logger.info(f"Using PostgreSQL connection pool with min={min_pool_size}, max={max_pool_size}")
            
            # Print all environment variables for debugging
            self.logger.info("Environment variables:")
            for key, value in os.environ.items():
                if 'PASSWORD' not in key and 'SECRET' not in key and 'KEY' not in key:
                    self.logger.info(f"  {key}={value}")
                else:
                    self.logger.info(f"  {key}=*****")
                    
            # Initialize DB with custom pool size
            if not hasattr(self, 'db') or self.db is None:
                from _core._db import PostgresClient
                self.db = PostgresClient(
                    postgres_url, 
                    self.logger, 
                    min_size=min_pool_size, 
                    max_size=max_pool_size
                )
                
            # Ensure NATS connection is established before interacting with JetStream
            if not self.bus.nc:
                await self.bus.connect()

            # JetStream context from the connected bus
            js = self.bus.js

            # We'll use the stream created by the fetcher agent rather than creating our own
            nats_subject_prefix = os.getenv("NATS_SUBJECT_PREFIX", "ai-radar")
            stream_name = os.getenv("NATS_STREAM_NAME", "ai-radar-stream")

            # Router expects bare subject (it will prepend the prefix automatically)
            summarize_subject = "tasks.summarize"
            
            # Check if the stream exists but don't try to modify it
            try:
                await js.stream_info(stream_name)
                self.logger.info(f"Using existing stream '{stream_name}'")
            except Exception as e:
                # Log warning but continue - the fetcher agent should create the stream
                self.logger.warning(f"Stream exists or error: {e}")
            
            # Register message handlers using the full subject name (with prefix)
            self.logger.info(f"Subscribing to NATS subject: {nats_subject_prefix}.{summarize_subject}")
            
            @self.router.on(summarize_subject)
            async def handle_summarize(payload, subject, reply):
                # Log the received message for debugging
                self.logger.info(f"Received message on {subject}: {json.dumps(payload)[:100]}...")
                
                # Convert payload to a message object that matches what process_summarize expects
                class Message:
                    def __init__(self, data, subject):
                        self.data = data
                        self.subject = subject
                    async def ack(self):
                        pass
                
                msg = Message(json.dumps(payload).encode(), subject)
                await self.process_summarize(msg)
            
            # Start the router
            await self.router.start()
            
            self.logger.info("Summariser agent setup complete")
            
        except Exception as e:
            self.logger.error(f"Error in setup: {e}")
            raise
    
    async def teardown(self):
        """Clean up resources."""
        try:
            # Close the database pool to release connections
            if hasattr(self, 'db') and self.db is not None and hasattr(self.db, 'close'):
                await self.db.close()
                self.logger.info("Closed PostgreSQL connection pool")
        except Exception as e:
            self.logger.error(f"Error closing database connection: {e}", exc_info=True)
        
        self.logger.info("Summariser agent teardown complete")

    async def run(self):
        """Run the summariser agent."""
        while True:
            try:
                # Set up the agent
                await self.setup()
                self.logger.info(f"{self.name} agent running")
                
                # Keep running until interrupted
                while True:
                    await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(f"Error in agent: {e}, restarting in 5 seconds", exc_info=True)
                await asyncio.sleep(5)


async def main():
    """Main function to start the summariser agent."""
    agent = SummariserAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
