"""
Tool Hub - Main Application Entry Point
This file imports and re-exports the FastAPI app from app.main
"""
from app.main import app

# This file allows the app to be run directly with uvicorn main:app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
