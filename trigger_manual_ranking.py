#!/usr/bin/env python
"""
Manually trigger a ranking task for testing Slack notifications
"""
import asyncio
import json
import nats
from nats.js import JetStreamContext

async def trigger_ranking():
    """Send a manual ranking task"""
    
    # Article data for testing
    article_data = {
        "article_id": 70,
        "title": "Mistral releases a pair of AI reasoning models",
        "summary": "Mistral released Magistral, its first family of reasoning models. Like other reasoning models — e.g. OpenAI's o3 and Google's Gemini 2.5 Pro — Magistral works through problems step-by-step for improved consistency and reliability across topics such as math and physics.",
        "url": "https://techcrunch.com/2025/06/10/mistral-releases-a-pair-of-ai-reasoning-models/"
    }
    
    print(f"🎯 Triggering manual ranking for article: {article_data['title']}")
    
    try:
        # Connect to NATS
        nc = await nats.connect("nats://localhost:4222")
        js = nc.jetstream()
        
        # Send ranking task
        subject = "ai-radar.tasks.rank"
        message = json.dumps(article_data).encode()
        
        await js.publish(subject, message)
        print(f"✅ Successfully sent ranking task to {subject}")
        
        # Close connection
        await nc.close()
        print(f"📤 Ranking task sent - check ranker logs for Slack notification!")
        
    except Exception as e:
        print(f"❌ Error sending ranking task: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_ranking())