from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.router import router
import uvicorn

# Create FastAPI app
app = FastAPI(
    title="Fusefy Agent API",
    description="AI Agent for interacting with Fusefy Platform APIs",
    version="2.0.0"
)

# Configure CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, prefix="/api/v1", tags=["agent"])

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Fusefy Agent API"}

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