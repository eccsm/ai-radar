#!/usr/bin/env python
"""
Summariser Agent - Main Module
Responsible for summarizing and embedding content for the AI Radar system.
"""
import os
import asyncio
import logging
import sys
import time
import json
import uuid
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
import tiktoken
import numpy as np
import aioboto3
from openai import AsyncOpenAI
from io import BytesIO
import minio

# --- DIAGNOSTIC PRINTS START ---
print("--- Summariser Diagnostic Info ---")
print(f"Current Working Directory: {os.getcwd()}")
print(f"Python Sys Path: {sys.path}")
try:
    print(f"Contents of /app: {os.listdir('/app')}")
except FileNotFoundError:
    print("Directory /app not found.")
try:
    print(f"Contents of /app/_core: {os.listdir('/app/_core')}")
except FileNotFoundError:
    print("Directory /app/_core not found.")
print("----------------------------------")
# --- DIAGNOSTIC PRINTS END ---

# Imports will rely on PYTHONPATH and the _core package structure.
from _core.health import HealthServer  # noqa: E402
from _core.secrets import SecretsManager  # noqa: E402
from agents._core._base import BaseAgent
from agents._core._rpc import Router

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
        self.secrets_manager = SecretsManager(self.logger)
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
            
            # Fetch content from S3 - use SecretsManager to get credentials
            self.logger.info(f"Fetching content from S3 with key: {content_key}")
            # Get MinIO configuration from SecretsManager
            minio_config = self.secrets_manager.get_minio_config()
            
            session = aioboto3.Session()
            s3_client = session.client(
                service_name="s3",
                endpoint_url=minio_config["endpoint"],
                aws_access_key_id=minio_config["access_key"],
                aws_secret_access_key=minio_config["secret_key"],
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
            
            # Generate summary (placeholder for invalid API key)
            try:
                summary = await self.generate_summary(content, title)
            except Exception as e:
                self.logger.warning(f"OpenAI API error, using placeholder summary: {e}")
                summary = f"Summary unavailable due to API error. Article title: {title}"
            
            # Generate embedding for combined title and summary (placeholder)
            try:
                embedding_text = f"{title}\n\n{summary}\n\n{content[:1000]}"
                embedding = await self.generate_embedding(embedding_text)
            except Exception as e:
                self.logger.warning(f"OpenAI embedding error, using placeholder: {e}")
                # Create a placeholder embedding vector (1536 dimensions for text-embedding-3-small)
                embedding = [0.0] * 1536
            
            # Convert embedding to pgvector format
            if isinstance(embedding, list):
                # Convert list to string format expected by pgvector
                embedding_str = '[' + ','.join(map(str, embedding)) + ']'
            else:
                embedding_str = str(embedding)
            
            self.logger.info(f"Inserting new article with embedding of type {type(embedding)} and length {len(embedding)}. First 5 elements: {embedding[:5]}")
            
            # Store in database with retry mechanism
            try:
                insert_query = """
                    INSERT INTO ai_radar.articles
                    (source_id, title, url, author, published_at, content, summary, embedding, importance_score)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                    """
                article_id = await self.retry_db_operation(
                    self.db.fetchval,
                    insert_query,
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
            self.logger.error(f"Error processing summarization: {e}", exc_info=True)
            # Acknowledge message to avoid redelivery
            await msg.ack()
            return
    
    async def setup(self):
        """Initialize the summariser agent, retrieving secrets and setting up clients."""
        try:
            self.logger.info("Setting up summariser agent...")
            
            # 1. Get OpenAI API key from SecretsManager (which handles Vault, env vars, etc.)
            try:
                self.logger.info(f"Retrieving OpenAI API key using Vault mount: {self.secrets_manager.vault_mount}")
                self.logger.info(f"Vault client authenticated: {self.secrets_manager.vault_client.is_authenticated() if self.secrets_manager.vault_client else False}")
                self.logger.info(f"Vault URL: {self.secrets_manager.vault_url}")
                
                # Directly try to read from Vault for debugging
                if self.secrets_manager.vault_client:
                    debug_path = "api-keys" 
                    self.logger.info(f"Attempting direct Vault read from {debug_path}")
                    try:
                        response = self.secrets_manager.vault_client.secrets.kv.v2.read_secret_version(
                            path=debug_path,
                            mount_point=self.secrets_manager.vault_mount
                        )
                        self.logger.info(f"Vault response keys: {list(response.get('data', {}).get('data', {}).keys()) if response else 'No response'}")
                    except Exception as ve:
                        self.logger.error(f"Direct Vault read failed: {ve}")
                
                # Now try the normal way
                openai_api_key = self.secrets_manager.get_openai_api_key()
                if not openai_api_key:
                    self.logger.error("OpenAI API key not found in any secret source!")
                    raise ValueError("OpenAI API key not configured")
                else:
                    self.logger.info("Successfully retrieved OpenAI API key")
            except Exception as e:
                self.logger.error(f"Failed to retrieve OpenAI API key: {e}", exc_info=True)
                raise ValueError(f"OpenAI API key retrieval failed: {e}")
            
            # Initialize OpenAI client with retrieved API key
            self.openai_client = AsyncOpenAI(api_key=openai_api_key)
            self.logger.info("OpenAI client initialized")
            
            # 2. Get MinIO config for S3 client
            minio_config = self.secrets_manager.get_minio_config()
            self.logger.info(f"Successfully retrieved MinIO configuration from secrets")
            
            # No need to initialize s3_client here as we create per-operation clients in process_summarize
            
            # 3. Get PostgreSQL connection URL
            postgres_url = self.secrets_manager.get_database_url()
            if not postgres_url:
                self.logger.error("PostgreSQL connection URL not found in any secret source!")
                raise ValueError("PostgreSQL URL not configured")
            self.logger.info(f"Database connection URL retrieved (using db: {postgres_url.split('/')[-1]})")
            
            # Configure optimal connection pool size
            min_pool_size = int(os.getenv("DB_MIN_CONNECTIONS", "1"))
            max_pool_size = int(os.getenv("DB_MAX_CONNECTIONS", "5"))
            self.logger.info(f"Using PostgreSQL connection pool with min={min_pool_size}, max={max_pool_size}")
            
            # 4. Initialize DB client with connection pool
            if not hasattr(self, 'db') or self.db is None:
                from _core._db import PostgresClient
                self.db = PostgresClient(
                    postgres_url, 
                    self.logger, 
                    min_size=min_pool_size, 
                    max_size=max_pool_size
                )
                self.logger.info("PostgreSQL client initialized with connection pool")
            
            # Connect to database
            await self.db.connect()
            self.logger.info("Successfully connected to PostgreSQL")
            
            # 5. Ensure NATS connection is established
            if not self.bus.nc:
                await self.bus.connect()
                self.logger.info("Connected to NATS")

            # Get JetStream context
            js = self.bus.js

            # Get NATS configuration
            nats_subject_prefix = os.getenv("NATS_SUBJECT_PREFIX", "ai-radar")
            stream_name = os.getenv("NATS_STREAM_NAME", "ai-radar-stream")

            # Define subject for summarization tasks
            summarize_subject = "tasks.summarize"
            
            # 6. Verify stream exists (created by fetcher agent)
            try:
                await js.stream_info(stream_name)
                self.logger.info(f"Using existing stream '{stream_name}'")
            except Exception as e:
                self.logger.warning(f"Stream info error (may be created by fetcher): {e}")
            
            # 7. Set up message handler for summarization tasks
            self.logger.info(f"Subscribing to NATS subject: {nats_subject_prefix}.{summarize_subject}")
            
            @self.router.on(summarize_subject)
            async def handle_summarize(payload, subject, reply):
                self.logger.info(f"Received message on {subject}: {json.dumps(payload)[:100]}...")
                
                # Convert payload to match what process_summarize expects
                class Message:
                    def __init__(self, data, subject):
                        self.data = data
                        self.subject = subject
                    async def ack(self):
                        pass
                
                msg = Message(json.dumps(payload).encode(), subject)
                await self.process_summarize(msg)
            
            # 8. Start the router
            await self.router.start()
            
            self.logger.info("Summariser agent setup complete")
            
        except Exception as e:
            self.logger.error(f"Error in setup: {e}", exc_info=True)
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
