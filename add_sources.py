#!/usr/bin/env python
"""
Add RSS Sources to AI Radar Database
This script connects to the AI Radar PostgreSQL database and adds RSS feed sources.
"""
import asyncio
import asyncpg
import os
from datetime import datetime

# Define RSS feeds to add
RSS_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "VentureBeat", "url": "https://venturebeat.com/feed/"},
    {"name": "ArsTechnica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "AI News", "url": "https://artificialintelligence-news.com/feed/"}
]

async def add_sources():
    # Connect to the PostgreSQL database
    postgres_url = os.getenv("POSTGRES_URL", "postgres://ai:ai@db/ai_radar")
    print(f"Connecting to database: {postgres_url}")
    conn = await asyncpg.connect(postgres_url)
    
    try:
        # Create schema if it doesn't exist
        await conn.execute("CREATE SCHEMA IF NOT EXISTS ai_radar;")
        
        # Create sources table if it doesn't exist
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_radar.sources (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL DEFAULT 'rss',
                active BOOLEAN NOT NULL DEFAULT true,
                last_fetched_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create articles table if it doesn't exist
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_radar.articles (
                id SERIAL PRIMARY KEY,
                source_id INTEGER REFERENCES ai_radar.sources(id),
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                author TEXT,
                published_at TIMESTAMP WITH TIME ZONE NOT NULL,
                content TEXT,
                summary TEXT,
                embedding vector(1536),
                importance_score FLOAT DEFAULT 0.5,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Add sources
        for feed in RSS_FEEDS:
            try:
                await conn.execute("""
                    INSERT INTO ai_radar.sources (name, url, source_type, active)
                    VALUES ($1, $2, 'rss', true)
                    ON CONFLICT (url) DO UPDATE
                    SET name = $1, active = true, updated_at = CURRENT_TIMESTAMP;
                """, feed["name"], feed["url"])
                print(f"Added/Updated source: {feed['name']}")
            except Exception as e:
                print(f"Error adding source {feed['name']}: {e}")
        
        # Print the current sources
        sources = await conn.fetch("SELECT id, name, url FROM ai_radar.sources;")
        print("\nCurrent sources in the database:")
        for source in sources:
            print(f"ID: {source['id']}, Name: {source['name']}, URL: {source['url']}")
        
    finally:
        # Close the connection
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_sources())
