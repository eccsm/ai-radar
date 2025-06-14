#!/usr/bin/env python
"""
Ranker Agent - Main Module
Responsible for ranking articles based on importance and relevance using AI.
"""
import os
import asyncio
import logging
import sys
import time
import json
import uuid
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential
import numpy as np
from openai import AsyncOpenAI
import asyncpg

# --- DIAGNOSTIC PRINTS START ---
print("--- Ranker Diagnostic Info ---")
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

# Constants for AI trending topics
TRENDING_TOPICS = [
    "artificial intelligence",
    "machine learning", 
    "large language models",
    "generative AI",
    "neural networks",
    "deep learning",
    "transformer models",
    "computer vision",
    "natural language processing",
    "reinforcement learning",
    "GPT",
    "ChatGPT",
    "OpenAI",
    "anthropic",
    "claude",
    "multimodal AI",
    "robotics",
    "autonomous vehicles",
    "AI safety",
    "AI ethics"
]


class RankerAgent(BaseAgent):
    """Agent responsible for ranking articles based on importance and relevance."""
    
    def __init__(self):
        super().__init__("ranker")
        self.router = Router(self.bus)
        self.secrets_manager = SecretsManager(self.logger)
        self.openai_client = None
        self.sharing_threshold = float(os.getenv("SHARING_THRESHOLD", "0.85"))
        self.slack_notification_threshold = float(os.getenv("SLACK_NOTIFICATION_THRESHOLD", "0.75"))
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def score_article_importance(self, title, summary):
        """Score the importance of an article using OpenAI's models."""
        try:
            prompt = f"""Rate the importance and relevance of this AI technology article on a scale of 0.0 to 1.0:

Title: {title}
Summary: {summary}

Consider the following factors:
- Significance to the AI field
- Technical innovation  
- Potential real-world impact
- Recency of development
- Market impact
- Research breakthrough potential

Provide ONLY a numerical score between 0.0 (low importance) and 1.0 (extremely important).
"""

            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an AI expert who evaluates the importance of AI research and news articles. Respond with only a number between 0.0 and 1.0."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.3
            )
            
            # Extract numerical score
            text_score = response.choices[0].message.content.strip()
            
            # Handle different response formats
            try:
                # Try to parse as float first
                score = float(text_score)
            except ValueError:
                # If that fails, try to extract number from text
                import re
                match = re.search(r'(\d+\.\d+)', text_score)
                if match:
                    score = float(match.group(1))
                else:
                    # Default to middle score if parsing fails
                    self.logger.warning(f"Could not parse score from '{text_score}', using default")
                    score = 0.5
            
            # Ensure score is within bounds
            score = max(0.0, min(score, 1.0))
            
            self.logger.info(f"Generated importance score: {score:.2f}")
            return score
        
        except Exception as e:
            self.logger.error(f"Error scoring article: {e}")
            # Return default score instead of failing
            self.logger.warning("Using fallback importance score of 0.5")
            return 0.5

    async def calculate_trending_boost(self, title, summary):
        """Calculate boost score based on trending AI topics."""
        similarity_boost = 0.0
        title_lower = title.lower()
        summary_lower = summary.lower() if summary else ""
        
        # Check for trending topics in title and summary
        for topic in TRENDING_TOPICS:
            if topic.lower() in title_lower:
                similarity_boost += 0.08  # Higher boost for title matches
            elif topic.lower() in summary_lower:
                similarity_boost += 0.04  # Lower boost for summary matches
        
        # Cap the boost to prevent over-inflation
        similarity_boost = min(similarity_boost, 0.25)
        
        if similarity_boost > 0:
            self.logger.info(f"Applied trending topics boost: +{similarity_boost:.2f}")
        
        return similarity_boost

    async def send_slack_notification(self, title, summary, score, url):
        """Send a notification to Slack for important articles."""
        try:
            # Get Slack webhook URL from environment or secrets
            slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
            if not slack_webhook_url:
                try:
                    # Try SLACK_KEY which maps to "slack" in api-keys vault path
                    slack_webhook_url = self.secrets_manager.get_secret("SLACK_KEY")
                    if slack_webhook_url:
                        self.logger.info("Retrieved Slack webhook URL from Vault (key: SLACK_KEY -> api-keys/slack)")
                except Exception as e:
                    self.logger.debug(f"Could not retrieve 'SLACK_KEY' from Vault: {e}")
                    try:
                        # Fallback to SLACK_WEBHOOK_URL key name
                        slack_webhook_url = self.secrets_manager.get_secret("SLACK_WEBHOOK_URL")
                        if slack_webhook_url:
                            self.logger.info("Retrieved Slack webhook URL from Vault (key: SLACK_WEBHOOK_URL)")
                    except Exception as e2:
                        self.logger.debug(f"Could not retrieve 'SLACK_WEBHOOK_URL' key from Vault: {e2}")
            
            if not slack_webhook_url:
                self.logger.debug("No Slack webhook URL configured, skipping notification")
                return
            
            # Create Slack message payload
            message = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "🔥 High-Importance AI News Alert"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{title}*\n\n{summary[:300]}{'...' if len(summary) > 300 else ''}"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Importance Score:*\n{score:.2f}"
                            },
                            {
                                "type": "mrkdwn", 
                                "text": f"*Article URL:*\n<{url}|Read More>"
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Generated by AI Radar • Score threshold: 0.8+"
                            }
                        ]
                    }
                ]
            }
            
            # Send to Slack using httpx
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    slack_webhook_url, 
                    json=message,
                    timeout=10.0
                )
                response.raise_for_status()
                self.logger.info(f"✅ Slack notification sent for high-importance article: {title}")
                
        except Exception as e:
            self.logger.error(f"Error sending Slack notification: {e}")
            raise

    async def process_rank(self, msg):
        """Process article ranking task message."""
        try:
            # Parse message data
            data = json.loads(msg.data.decode())
            article_id = data["article_id"]
            title = data["title"]
            summary = data.get("summary", "")
            
            self.logger.info(f"Processing ranking for article ID {article_id}: {title}")
            
            # Check if already has a proper score (not the default 0.5)
            try:
                existing_score = await self.retry_db_operation(
                    self.db.fetchval,
                    "SELECT importance_score FROM ai_radar.articles WHERE id = $1",
                    article_id
                )
                
                if existing_score is not None and existing_score != 0.5:
                    self.logger.info(f"Article already has custom score {existing_score:.2f}, skipping")
                    await msg.ack()
                    return
            except Exception as db_err:
                self.logger.error(f"Database check failed: {db_err}", exc_info=True)
                await msg.ack()
                return
            
            # Score article importance using AI
            try:
                importance_score = await self.score_article_importance(title, summary)
            except Exception as e:
                self.logger.warning(f"AI scoring failed, using default: {e}")
                importance_score = 0.5
            
            # Calculate trending topics boost
            try:
                trending_boost = await self.calculate_trending_boost(title, summary)
            except Exception as e:
                self.logger.warning(f"Trending boost calculation failed: {e}")
                trending_boost = 0.0
            
            # Calculate final score
            final_score = min(importance_score + trending_boost, 1.0)
            
            # Update article with score
            try:
                await self.retry_db_operation(
                    self.db.execute,
                    "UPDATE ai_radar.articles SET importance_score = $1 WHERE id = $2",
                    final_score, article_id
                )
                self.logger.info(f"Updated article {article_id} with final score {final_score:.2f} (base: {importance_score:.2f}, boost: +{trending_boost:.2f})")
            except Exception as update_err:
                self.logger.error(f"Failed to update article score: {update_err}", exc_info=True)
                await msg.ack()
                return
            
            # Log high importance articles and send Slack notification
            if final_score >= self.slack_notification_threshold:
                self.logger.info(f"🔥 HIGH IMPORTANCE ARTICLE: {title} (score: {final_score:.2f})")
                # Send Slack notification for important articles
                try:
                    await self.send_slack_notification(title, summary, final_score, data.get("url", ""))
                except Exception as slack_err:
                    self.logger.warning(f"Failed to send Slack notification: {slack_err}")
            
            # Publish to sharing queue for very high-importance articles
            if final_score >= self.sharing_threshold:
                self.logger.info(f"Article {article_id} score {final_score:.2f} exceeds sharing threshold, queuing for LinkedIn.")
                share_payload = {
                    "article_title": title,
                    "article_url": data.get("url", "")
                }
                nats_subject_prefix = os.getenv("NATS_SUBJECT_PREFIX", "ai-radar")
                share_subject = f"{nats_subject_prefix}.tasks.share"
                await self.bus.publish(share_subject, json.dumps(share_payload).encode())
                self.logger.info(f"Published sharing task for article {article_id} to {share_subject}")
            
            await msg.ack()
            self.logger.info(f"Successfully processed and ranked article {article_id} with score {final_score:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error processing ranking: {e}", exc_info=True)
            # Acknowledge to avoid redelivery
            await msg.ack()

    async def retry_db_operation(self, operation, *args, max_retries=5, **kwargs):
        """Retry a database operation with exponential backoff."""
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                result = await operation(*args, **kwargs)
                return result
            except asyncpg.exceptions.ConnectionDoesNotExistError as e:
                retries += 1
                wait_time = 2 ** retries
                last_error = e
                self.logger.warning(f"Database connection error: {e}, retrying in {wait_time}s (attempt {retries}/{max_retries})")
                await asyncio.sleep(wait_time)
            except asyncpg.exceptions.PostgresConnectionError as e:
                retries += 1
                wait_time = 2 ** retries
                self.logger.warning(f"PostgreSQL connection error: {e}, attempting to reconnect (attempt {retries}/{max_retries})")
                
                try:
                    await self.db.connect()
                    self.logger.info("Successfully reconnected to PostgreSQL")
                    continue
                except Exception as reconnect_err:
                    self.logger.error(f"Failed to reconnect to PostgreSQL: {reconnect_err}")
                
                await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                retries += 1
                wait_time = 2 ** retries
                self.logger.error(f"Database operation failed: {e}, retrying in {wait_time}s (attempt {retries}/{max_retries})")
                await asyncio.sleep(wait_time)
                
        if last_error:
            self.logger.error(f"Failed after {max_retries} retries: {last_error}")
            raise last_error

    async def setup(self):
        """Initialize the ranker agent, retrieving secrets and setting up clients."""
        try:
            self.logger.info("Setting up ranker agent...")
            
            # 1. Get OpenAI API key from SecretsManager
            try:
                openai_api_key = self.secrets_manager.get_openai_api_key()
                if not openai_api_key:
                    self.logger.error("OpenAI API key not found in any secret source!")
                    raise ValueError("OpenAI API key not configured")
                else:
                    self.logger.info("Successfully retrieved OpenAI API key")
            except Exception as e:
                self.logger.error(f"Failed to retrieve OpenAI API key: {e}", exc_info=True)
                raise ValueError(f"OpenAI API key retrieval failed: {e}")
            
            # Initialize OpenAI client
            self.openai_client = AsyncOpenAI(api_key=openai_api_key)
            self.logger.info("OpenAI client initialized")
            
            # 2. Get PostgreSQL connection URL
            postgres_url = self.secrets_manager.get_database_url()
            if not postgres_url:
                self.logger.error("PostgreSQL connection URL not found in any secret source!")
                raise ValueError("PostgreSQL URL not configured")
            self.logger.info(f"Database connection URL retrieved")
            
            # 3. Initialize DB client with connection pool
            if not hasattr(self, 'db') or self.db is None:
                from _core._db import PostgresClient
                self.db = PostgresClient(
                    postgres_url, 
                    self.logger, 
                    min_size=1, 
                    max_size=3
                )
                self.logger.info("PostgreSQL client initialized")
            
            # Connect to database
            await self.db.connect()
            self.logger.info("Successfully connected to PostgreSQL")
            
            # 4. Ensure NATS connection is established
            if not self.bus.nc:
                await self.bus.connect()
                self.logger.info("Connected to NATS")

            # Get NATS configuration
            nats_subject_prefix = os.getenv("NATS_SUBJECT_PREFIX", "ai-radar")
            rank_subject = "tasks.rank"
            
            # 5. Set up message handler for ranking tasks
            self.logger.info(f"Subscribing to NATS subject: {nats_subject_prefix}.{rank_subject}")
            
            @self.router.on(rank_subject)
            async def handle_rank(payload, subject, reply):
                self.logger.info(f"Received ranking message on {subject}: {json.dumps(payload)[:100]}...")
                
                # Convert payload to match what process_rank expects
                class Message:
                    def __init__(self, data, subject):
                        self.data = data
                        self.subject = subject
                    async def ack(self):
                        pass
                
                msg = Message(json.dumps(payload).encode(), subject)
                await self.process_rank(msg)
            
            # 6. Start the router
            await self.router.start()
            
            self.logger.info("Ranker agent setup complete - ready to score articles!")
            
        except Exception as e:
            self.logger.error(f"Error in setup: {e}", exc_info=True)
            raise
    
    async def teardown(self):
        """Clean up resources."""
        try:
            if hasattr(self, 'db') and self.db is not None and hasattr(self.db, 'close'):
                await self.db.close()
                self.logger.info("Closed PostgreSQL connection pool")
        except Exception as e:
            self.logger.error(f"Error closing database connection: {e}", exc_info=True)
        
        self.logger.info("Ranker agent teardown complete")

    async def run(self):
        """Run the ranker agent."""
        while True:
            try:
                # Set up the agent
                await self.setup()
                self.logger.info(f"{self.name} agent running and ready to rank articles!")
                
                # Keep running until interrupted
                while True:
                    await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(f"Error in agent: {e}, restarting in 5 seconds", exc_info=True)
                await asyncio.sleep(5)


async def main():
    """Main function to start the ranker agent."""
    agent = RankerAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())