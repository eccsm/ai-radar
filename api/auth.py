"""
Authentication module for AI Radar API
Implements JWT-based authentication with Vault integration and PostgreSQL database
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import asyncpg

# Import SecretsManager with fallback
try:
    from _core.secrets import SecretsManager
except ImportError:
    try:
        # Try parent directory
        sys.path.append('/app/parent')
        from _core.secrets import SecretsManager
    except ImportError:
        # Create fallback SecretsManager
        class SecretsManager:
            def get_secret(self, key, default=None):
                return os.getenv(key, default)

# Instantiate SecretsManager
secrets_manager = SecretsManager()

# Configuration for token
SECRET_KEY = secrets_manager.get_secret("JWT_SECRET_KEY", default="ai-radar-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 token URL - FIX: This should match your API route structure
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

# Pydantic Models
class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: Optional[int] = None  # Make id optional for compatibility
    disabled: Optional[bool] = None

    class Config:
        from_attributes = True  # Updated for Pydantic v2

class UserInDB(User):
    hashed_password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password for storing."""
    return pwd_context.hash(password)

async def get_user(db: asyncpg.Connection, username: str) -> Optional[UserInDB]:
    """Retrieve a user from the database by username."""
    try:
        row = await db.fetchrow(
            "SELECT id, username, email, full_name, hashed_password, disabled FROM users WHERE username = $1",
            username
        )
        if row:
            return UserInDB(**dict(row))
    except Exception as e:
        print(f"Database error when fetching user {username}: {e}")
    return None

async def authenticate_user(db: asyncpg.Connection, username: str, password: str) -> Optional[User]:
    """Authenticate a user against the database."""
    # For development/testing, allow a default user
    if username == "admin" and password == "admin":
        return User(id=1, username="admin", email="admin@example.com", disabled=False)
    
    user = await get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return User(**user.dict())

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> UserInDB:
    """Decode JWT token and get current user from DB."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    pool = request.app.state.pool
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Database connection not available"
        )

    async with pool.acquire() as db_conn:
        user = await get_user(db_conn, username=token_data.username)
    
    if user is None:
        # For development, return a mock user
        if token_data.username == "admin":
            return UserInDB(id=1, username="admin", email="admin@example.com", hashed_password="", disabled=False)
        raise credentials_exception
    return user

async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)) -> User:
    """Get current active user, checking if disabled."""
    if current_user.disabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return User(**current_user.dict())