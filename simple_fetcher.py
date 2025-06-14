#!/usr/bin/env python
"""
Simple RSS Fetcher - A minimal working implementation
Fetches RSS feeds and stores articles in the database
"""
import asyncio
import asyncpg
import feedparser
import json
import logging
import os
from datetime import datetime
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple-fetcher")

# Database configuration
DB_URL = "postgresql://ai:ai_pwd@localhost:5432/ai_radar"

async def fetch_rss_feed(url, source_name):
    """Fetch and parse an RSS feed."""
    try:
        logger.info(f"Fetching RSS feed: {source_name} ({url})")
        
        # Parse the RSS feed
        feed = feedparser.parse(url)
        
        if not feed.entries:
            logger.warning(f"No entries found in feed: {source_name}")
            return []
        
        articles = []
        for entry in feed.entries[:10]:  # Limit to 10 articles per feed
            try:
                # Extract basic information
                title = getattr(entry, 'title', 'No title')
                article_url = getattr(entry, 'link', '')
                author = getattr(entry, 'author', None)
                
                # Get published date
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    published_at = datetime(*entry.updated_parsed[:6])
                else:
                    published_at = datetime.now()
                
                # Get content
                content = ""
                if hasattr(entry, 'content') and entry.content:
                    content = entry.content[0].value
                elif hasattr(entry, 'summary'):
                    content = entry.summary
                
                # Extract text from HTML
                if content:
                    soup = BeautifulSoup(content, 'html.parser')
                    content = soup.get_text(' ', strip=True)
                
                # Simple summary (first 500 chars)
                summary = content[:500] + "..." if len(content) > 500 else content
                
                articles.append({
                    'title': title,
                    'url': article_url,
                    'author': author,
                    'published_at': published_at,
                    'content': content,
                    'summary': summary,
                    'source_name': source_name
                })
                
            except Exception as e:
                logger.warning(f"Error processing entry: {e}")
                continue
                
        logger.info(f"Processed {len(articles)} articles from {source_name}")
        return articles
        
    except Exception as e:
        logger.error(f"Error fetching feed {source_name}: {e}")
        return []

async def store_articles(articles):
    """Store articles in the database."""
    if not articles:
        return
        
    try:
        # Connect to database
        conn = await asyncpg.connect(DB_URL)
        
        stored_count = 0
        for article in articles:
            try:
                # Check if article already exists
                exists = await conn.fetchval(
                    "SELECT id FROM ai_radar.articles WHERE url = $1",
                    article['url']
                )
                
                if exists:
                    logger.debug(f"Article already exists: {article['title']}")
                    continue
                
                # Get or create source
                source_id = await conn.fetchval(
                    "SELECT id FROM ai_radar.sources WHERE name = $1",
                    article['source_name']
                )
                
                if not source_id:
                    # Create source
                    source_id = await conn.fetchval(
                        """
                        INSERT INTO ai_radar.sources (name, url, source_type, active)
                        VALUES ($1, $2, 'rss', true)
                        RETURNING id
                        """,
                        article['source_name'], "unknown"
                    )
                
                # Insert article
                await conn.execute(
                    """
                    INSERT INTO ai_radar.articles 
                    (source_id, title, url, author, published_at, content, summary, importance_score)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    source_id, article['title'], article['url'], article['author'],
                    article['published_at'], article['content'], article['summary'], 0.5
                )
                
                stored_count += 1
                logger.info(f"Stored article: {article['title']}")
                
            except Exception as e:
                logger.error(f"Error storing article {article['title']}: {e}")
                continue
        
        await conn.close()
        logger.info(f"Successfully stored {stored_count} new articles")
        
    except Exception as e:
        logger.error(f"Database error: {e}")

async def fetch_all_feeds():
    """Fetch all RSS feeds and store articles."""
    
    # RSS feeds to fetch
    feeds = [
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("Wired AI", "https://www.wired.com/feed/tag/artificial-intelligence/latest/rss"),
        ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
        ("VentureBeat AI", "https://venturebeat.com/ai/feed/"),
        ("The Verge AI", "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml")
    ]
    
    logger.info(f"Starting to fetch {len(feeds)} RSS feeds...")
    
    all_articles = []
    for source_name, url in feeds:
        articles = await fetch_rss_feed(url, source_name)
        all_articles.extend(articles)
        
        # Small delay between feeds
        await asyncio.sleep(2)
    
    logger.info(f"Fetched total of {len(all_articles)} articles")
    
    # Store all articles
    await store_articles(all_articles)
    
    logger.info("RSS fetch completed!")

if __name__ == "__main__":
    asyncio.run(fetch_all_feeds())