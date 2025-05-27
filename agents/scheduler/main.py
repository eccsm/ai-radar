#!/usr/bin/env python
"""
Scheduler Agent - Main Module
Responsible for scheduling recurring tasks in the AI Radar system.
"""
import os
import logging
import asyncio
import json
import nats
from nats.js.api import StreamConfig
import asyncpg
from datetime import datetime, timedelta
from dateutil.rrule import rrulestr
import croniter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("scheduler-agent")

# Global connections
nc = None
js = None
db = None

# Environment variables
POSTGRES_URL = os.getenv("POSTGRES_URL")
NATS_URL = os.getenv("NATS_URL")

# Set default schedule to run every 30 minutes
# This can be overridden with the CRON_RRULE environment variable
CRON_RRULE = os.getenv("CRON_RRULE", "RRULE:FREQ=MINUTELY;INTERVAL=30")


async def schedule_rss_updates():
    """Schedule updates for all active RSS feeds."""
    try:
        # Get all active RSS sources
        sources = await db.fetch(
            """
            SELECT id, name, url 
            FROM ai_radar.sources 
            WHERE active = true AND source_type = 'rss'
            ORDER BY last_fetched_at ASC NULLS FIRST
            """
        )
        
        if not sources:
            logger.warning("No active RSS sources found")
            return
        
        logger.info(f"Scheduling updates for {len(sources)} RSS sources")
        
        # Publish tasks for each source
        success_count = 0
        for source in sources:
            try:
                payload = {
                    "source_id": source["id"],
                    "url": source["url"],
                    "name": source["name"],
                    "timestamp": datetime.now().isoformat()
                }
                
                await js.publish(
                    "ai-radar.tasks.rss_fetch",
                    json.dumps(payload).encode()
                )
                
                logger.info(f"Scheduled update for source: {source['name']}")
                
                # Update last_fetched_at timestamp
                await db.execute(
                    "UPDATE ai_radar.sources SET last_fetched_at = $1 WHERE id = $2",
                    datetime.now(), source["id"]
                )
                
                success_count += 1
                
                # Small delay between tasks to avoid overwhelming the system
                await asyncio.sleep(1)
            except Exception as source_error:
                logger.error(f"Error scheduling update for source {source['name']}: {source_error}")
                # Continue with other sources even if one fails
                continue
        
        logger.info(f"Successfully scheduled updates for {success_count}/{len(sources)} sources")
            
    except Exception as e:
        logger.error(f"Error scheduling RSS updates: {e}")


async def run_scheduled_tasks():
    """Run scheduled tasks based on CRON_RRULE."""
    # Run immediately on startup to fetch articles right away
    logger.info("Running initial scheduled tasks on startup")
    try:
        await schedule_rss_updates()
    except Exception as e:
        logger.error(f"Error in initial schedule run: {e}")
    
    # Then continue with regular schedule
    while True:
        try:
            now = datetime.now()
            
            # Check if rule is RRULE or cron format
            if CRON_RRULE.startswith("RRULE:"):
                # RRule format
                rule = rrulestr(CRON_RRULE)
                next_run = rule.after(now)
            else:
                # Cron format
                cron = croniter.croniter(CRON_RRULE, now)
                next_run = datetime.fromtimestamp(cron.get_next())
            
            # Calculate seconds until next run
            seconds_to_wait = (next_run - now).total_seconds()
            
            logger.info(f"Next scheduled run at {next_run.isoformat()} ({seconds_to_wait:.1f} seconds from now)")
            
            await asyncio.sleep(seconds_to_wait)
            
            # Run scheduled tasks
            logger.info("Running scheduled tasks")
            await schedule_rss_updates()
            
            # Small delay to avoid running twice
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error in run_scheduled_tasks: {e}")
            # Sleep for a minute before retrying
            await asyncio.sleep(60)


async def check_source_health():
    """Check health of sources and mark inactive if needed."""
    while True:
        try:
            # Wait for 24 hours between checks
            await asyncio.sleep(86400)
            
            logger.info("Checking source health")
            
            # Find sources that haven't been updated in 7 days
            one_week_ago = datetime.now() - timedelta(days=7)
            
            inactive_sources = await db.fetch(
                """
                SELECT id, name 
                FROM ai_radar.sources 
                WHERE active = true 
                AND (last_fetched_at IS NULL OR last_fetched_at < $1)
                """,
                one_week_ago
            )
            
            if not inactive_sources:
                logger.info("All sources are healthy")
                continue
                
            logger.warning(f"Found {len(inactive_sources)} inactive sources")
            
            # Mark sources as inactive
            for source in inactive_sources:
                await db.execute(
                    "UPDATE ai_radar.sources SET active = false WHERE id = $1",
                    source["id"]
                )
                logger.info(f"Marked source '{source['name']}' as inactive")
                
        except Exception as e:
            logger.error(f"Error checking source health: {e}")


async def cleanup_old_data():
    """Clean up old data to maintain database performance."""
    while True:
        try:
            # Wait for 7 days between cleanups
            await asyncio.sleep(7 * 86400)
            
            logger.info("Running data cleanup")
            
            # Remove articles older than 90 days with low importance
            ninety_days_ago = datetime.now() - timedelta(days=90)
            
            result = await db.execute(
                """
                DELETE FROM ai_radar.articles
                WHERE published_at < $1
                AND importance_score < 0.3
                """,
                ninety_days_ago
            )
            
            logger.info(f"Cleaned up old low-importance articles")
                
        except Exception as e:
            logger.error(f"Error in data cleanup: {e}")


async def main():
    """Main function to start the scheduler agent."""
    global nc, js, db
    
    try:
        # Connect to database
        logger.info(f"Connecting to PostgreSQL at {POSTGRES_URL}")
        db = await asyncpg.connect(POSTGRES_URL)
        
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
        
        logger.info(f"Scheduler agent is running with rule: {CRON_RRULE}")
        
        # Start background tasks
        task1 = asyncio.create_task(run_scheduled_tasks())
        task2 = asyncio.create_task(check_source_health())
        task3 = asyncio.create_task(cleanup_old_data())
        
        # Keep the agent running
        await asyncio.gather(task1, task2, task3)
            
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