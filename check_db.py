#!/usr/bin/env python
"""
Simple script to check if articles exist in the database.
This provides a quick way to verify if the pipeline is working.
"""
import asyncio
import asyncpg
import sys

async def check_articles():
    # Connect to PostgreSQL (using localhost since we're outside container)
    print("Connecting to PostgreSQL database...")
    try:
        conn = await asyncpg.connect("postgresql://ai:ai_pwd@localhost:5432/ai_radar")
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return
    
    try:
        # Check if ai_radar schema exists
        schemas = await conn.fetch("SELECT schema_name FROM information_schema.schemata")
        schema_names = [s['schema_name'] for s in schemas]
        if 'ai_radar' not in schema_names:
            print("Error: 'ai_radar' schema does not exist!")
            print(f"Available schemas: {schema_names}")
            return
        
        # Check if articles table exists
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'ai_radar'"
        )
        table_names = [t['table_name'] for t in tables]
        if 'articles' not in table_names:
            print("Error: 'articles' table does not exist in ai_radar schema!")
            print(f"Available tables: {table_names}")
            return
        
        # Check article count
        count = await conn.fetchval("SELECT COUNT(*) FROM ai_radar.articles")
        print(f"Total articles in database: {count}")
        
        # Show most recent articles
        if count > 0:
            print("\nMost recent articles:")
            articles = await conn.fetch("""
                SELECT id, title, url, published_at, created_at 
                FROM ai_radar.articles 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            
            for article in articles:
                print(f"ID: {article['id']}")
                print(f"Title: {article['title']}")
                print(f"URL: {article['url']}")
                print(f"Published: {article['published_at']}")
                print(f"Created: {article['created_at']}")
                print("-" * 50)
        else:
            print("No articles found in the database.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_articles())
