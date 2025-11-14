from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.router import router
from middleware import RequestLoggingMiddleware
from config import SessionManager
import uvicorn
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Fusefy Agent API",
    description="AI Agent for interacting with Fusefy Platform APIs",
    version="2.0.0"
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Configure CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lifecycle events
@app.on_event("startup")
async def startup_event():
    logger.info("Starting Fusefy Agent API...")
    logger.info("Initializing shared HTTP session...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Fusefy Agent API...")
    await SessionManager.close_session()
    logger.info("Closed shared HTTP session")

# Include routers
app.include_router(router, prefix="/api/v1", tags=["agent"])

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check with downstream API connectivity test"""
    from tools_config import FusefyAPITools
    
    health_status = {
        "status": "healthy",
        "service": "Fusefy Agent API",
        "version": "2.0.0"
    }
    
    # Test downstream API connectivity
    try:
        docs = await FusefyAPITools.get_api_documentation()
        health_status["downstream_api"] = "connected" if "error" not in docs else "error"
    except Exception as e:
        health_status["downstream_api"] = "error"
        health_status["downstream_error"] = str(e)
    
    return health_status

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Fusefy Agent API",
        "docs": "/docs",
        "health": "/health",
        "api_prefix": "/api/v1"
    }

if __name__ == "__main__":
    # Run with uvicorn when executing directly
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Enable auto-reload during development
    )