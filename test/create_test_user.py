#!/usr/bin/env python3
"""
Script to create test users in the database
Run this to create a test user for authentication
"""
import asyncio
import asyncpg
import sys
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_test_user():
    # Database connection parameters
    db_host = "localhost"  # or "db" if running inside Docker
    db_port = "5432"
    db_user = "ai"
    db_password = "ai_pwd"
    db_name = "ai_radar"
    
    dsn = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    try:
        # Connect to database
        conn = await asyncpg.connect(dsn)
        
        # Create users table if it doesn't exist
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100),
                full_name VARCHAR(100),
                hashed_password VARCHAR(255) NOT NULL,
                disabled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Hash password
        hashed_password = pwd_context.hash("admin")
        
        # Insert test user
        await conn.execute("""
            INSERT INTO users (username, email, full_name, hashed_password, disabled)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (username) DO UPDATE SET
                hashed_password = EXCLUDED.hashed_password,
                email = EXCLUDED.email,
                full_name = EXCLUDED.full_name
        """, "admin", "admin@example.com", "Administrator", hashed_password, False)
        
        print("✅ Test user 'admin' created successfully!")
        print("   Username: admin")
        print("   Password: admin")
        print("   Email: admin@example.com")
        
        # Close connection
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error creating test user: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(create_test_user())