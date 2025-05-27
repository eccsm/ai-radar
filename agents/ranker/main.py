#!/usr/bin/env python
"""
Ranker Agent - Main Module
Responsible for ranking articles based on importance and relevance.
"""
import os
import logging
import asyncio
import json
import nats
from nats.js.api import StreamConfig
import asyncpg
import openai
from openai import AsyncOpenAI
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ranker-agent")

# Global connections
nc = None
js = None
db = None
openai_client = None

# Environment variables
POSTGRES_URL = os.getenv("POSTGRES_URL")
NATS_URL = os.getenv("NATS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Constants
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
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def score_article_importance(title, summary):
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

Provide ONLY a numerical score between 0.0 (low importance) and 1.0 (extremely important).
"""

        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an AI expert who evaluates the importance of AI research and news articles."},
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
                logger.warning(f"Could not parse score from '{text_score}', using default")
                score = 0.5
        
        # Ensure score is within bounds
        score = max(0.0, min(score, 1.0))
        
        logger.info(f"Generated importance score: {score:.2f}")
        return score
    
    except Exception as e:
        logger.error(f"Error scoring article: {e}")
        raise


async def process_rank(msg):
    """Process article ranking task message."""
    try:
        # Parse message data
        data = json.loads(msg.data.decode())
        article_id = data["article_id"]
        title = data["title"]
        summary = data.get("summary", "")
        
        logger.info(f"Processing ranking for article ID {article_id}: {title}")
        
        # Check if already ranked
        existing_score = await db.fetchval(
            "SELECT importance_score FROM ai_radar.articles WHERE id = $1",
            article_id
        )
        
        if existing_score is not None:
            logger.info(f"Article already has score {existing_score:.2f}, skipping")
            await msg.ack()
            return
        
        # Score article importance
        importance_score = await score_article_importance(title, summary)
        
        # Calculate similarity to trending topics
        similarity_boost = 0.0
        
        # Get article embedding
        embedding = await db.fetchval(
            "SELECT embedding FROM ai_radar.articles WHERE id = $1",
            article_id
        )
        
        if embedding:
            # Create simple embeddings for trending topics (in production, you'd use OpenAI)
            for topic in TRENDING_TOPICS:
                if topic.lower() in title.lower() or topic.lower() in summary.lower():
                    similarity_boost += 0.05  # Simple boost for matching topics
            
            # Cap the boost
            similarity_boost = min(similarity_boost, 0.2)
        
        # Calculate final score
        final_score = min(importance_score + similarity_boost, 1.0)
        
        # Update article with score
        await db.execute(
            "UPDATE ai_radar.articles SET importance_score = $1 WHERE id = $2",
            final_score, article_id
        )
        
        logger.info(f"Updated article {article_id} with score {final_score:.2f}")
        
        # If highly important, notify via Slack
        if final_score > 0.8 and SLACK_WEBHOOK_URL:
            await send_slack_notification(title, summary, final_score)
        
        # Acknowledge message
        await msg.ack()
        
    except Exception as e:
        logger.error(f"Error processing ranking: {e}")
        # For now, acknowledge to avoid redelivery
        await msg.ack()


async def send_slack_notification(title, summary, score):
    """Send a notification to Slack for important articles."""
    if not SLACK_WEBHOOK_URL:
        return
    
    try:
        import httpx
        
        message = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🔥 Important AI News Alert"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{title}*\n\n{summary}\n\n*Importance Score:* {score:.2f}"
                    }
                }
            ]
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(SLACK_WEBHOOK_URL, json=message)
            response.raise_for_status()
            logger.info(f"Sent Slack notification for important article")
            
    except Exception as e:
        logger.error(f"Error sending Slack notification: {e}")


async def weekly_trending_update():
    """Generate and send a weekly trending update to Slack."""
    while True:
        try:
            # Wait until Monday morning
            now = datetime.now()
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0 and now.hour >= 9:
                days_until_monday = 7
                
            next_run = now + timedelta(days=days_until_monday)
            next_run = next_run.replace(hour=9, minute=0, second=0, microsecond=0)
            
            seconds_to_wait = (next_run - now).total_seconds()
            logger.info(f"Scheduled next weekly update in {seconds_to_wait/3600:.1f} hours")
            
            await asyncio.sleep(seconds_to_wait)
            
            # Get top articles from the past week
            one_week_ago = datetime.now() - timedelta(days=7)
            
            top_articles = await db.fetch(
                """
                SELECT 
                    a.id, a.title, a.url, a.summary, a.importance_score, 
                    a.published_at, s.name as source
                FROM 
                    ai_radar.articles a
                JOIN 
                    ai_radar.sources s ON a.source_id = s.id
                WHERE 
                    a.published_at > $1
                ORDER BY 
                    a.importance_score DESC
                LIMIT 10
                """,
                one_week_ago
            )
            
            if not top_articles or not SLACK_WEBHOOK_URL:
                continue
                
            # Format message
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 Weekly AI Radar Trending Topics"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Here are the top AI developments from the past week:"
                    }
                }
            ]
            
            for article in top_articles:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*<{article['url']}|{article['title']}>*\n{article['summary'][:100]}...\n*Score:* {article['importance_score']:.2f} | *Source:* {article['source']}"
                    }
                })
            
            # Send to Slack
            message = {"blocks": blocks}
            
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(SLACK_WEBHOOK_URL, json=message)
                response.raise_for_status()
                logger.info(f"Sent weekly trending update to Slack")
                
        except Exception as e:
            logger.error(f"Error in weekly trending update: {e}")
            
        # Sleep for a day before checking again
        await asyncio.sleep(86400)  # 24 hours


async def main():
    """Main function to start the ranker agent."""
    global nc, js, db, openai_client
    
    try:
        # Connect to database
        logger.info(f"Connecting to PostgreSQL at {POSTGRES_URL}")
        db = await asyncpg.connect(POSTGRES_URL)
        
        # Set up OpenAI client
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        
        # Connect to NATS
        logger.info(f"Connecting to NATS at {NATS_URL}")
        nc = await nats.connect(NATS_URL)
        js = nc.jetstream()
        
        # Ensure stream exists
        try:
            await js.add_stream(
                name="ai-radar",
                subjects=["ai-radar.>"],
                storage="file",
                max_msgs=100000,
            )
        except Exception as e:
            logger.warning(f"Stream exists or error: {e}")
        
        # Subscribe to tasks
        rank_sub = await js.subscribe(
            "ai-radar.tasks.rank",
            cb=process_rank,
            durable="ranker",
            manual_ack=True,
        )
        
        logger.info("Ranker agent is running, waiting for tasks...")
        
        # Start weekly trending update task
        asyncio.create_task(weekly_trending_update())
        
        # Keep the agent running
        while True:
            await asyncio.sleep(10)
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        # Clean up
        if db:
            await db.close()
        if nc:
            await nc.close()


if __name__ == "__main__":
    asyncio.run(main())