"""
SmartTrack FastAPI Application
Main entry point for the backend API
"""
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

from config import settings
from database import init_db, close_db
from routes import auth, users, travels, colleges, documents, analytics, notifications, siap, mobility_plans, document_types, audit
from routes import post_travel, reentry, compliance
from routes import ai
from routes import requirements

# Configure logging
def setup_logging():
    """Setup application logging"""
    log_dir = "./logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # File handler
    handler = RotatingFileHandler(
        f"{log_dir}/smarttrack.log",
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="AI-Based International Travel Monitoring System for CSUCC OIGE",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# CORS Middleware - Log origins for debugging
logger.info(f"CORS Origins configured: {settings.CORS_ORIGINS}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Auto-allow ANY port on localhost / 127.0.0.1 / LAN IPs (flutter run
    # picks changing dev ports) — no more per-port CORS conflicts.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    max_age=600,  # 10 minutes preflight cache
)

# Custom exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Generic exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )

# Lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("=" * 50)
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} Starting...")
    logger.info(f"Environment: {'Development' if settings.DEBUG else 'Production'}")
    logger.info(f"Database: {settings.DATABASE_URL}")
    logger.info("=" * 50)

    if settings.SECRET_KEY == "your-secret-key-change-in-production":
        logger.warning(
            "SECRET_KEY is the insecure default! Set a strong SECRET_KEY in backend/.env "
            "before any real deployment (see backend/.env.example)."
        )
    if not settings.DEBUG:
        logger.info("Running with DEBUG=false (production mode).")

    try:
        # Initialize database
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning(f"Database initialization failed: {str(e)}")
        logger.warning("Server will continue running but database features may be unavailable")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info(f"{settings.APP_NAME} Shutting down...")
    close_db()
    logger.info("Application shutdown complete")

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(travels.router)
app.include_router(colleges.router)
app.include_router(documents.router)
app.include_router(analytics.router)
app.include_router(notifications.router)
app.include_router(siap.router)
app.include_router(mobility_plans.router)
app.include_router(document_types.router)
app.include_router(audit.router)
app.include_router(post_travel.router)
app.include_router(reentry.router)
app.include_router(compliance.router)
app.include_router(ai.router)
app.include_router(requirements.router)

# Health check endpoint
@app.get("/health")
async def health():
    """Root health check (IT 110 Activity 10 contract)."""
    return {"status": "ok"}

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION
    }

# APK download (phone install)
from fastapi.responses import FileResponse
import os as _os

@app.get("/api/download/apk")
async def download_apk():
    apk_path = _os.path.join(_os.path.dirname(__file__), "SmartTrack-v3.apk")
    if not _os.path.exists(apk_path):
        from fastapi import HTTPException
        raise HTTPException(404, "APK not found")
    return FileResponse(apk_path, media_type="application/vnd.android.package-archive",
                        filename="SmartTrack-v3.apk")

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "description": "AI-Based International Travel Monitoring System",
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "redoc": "/api/redoc"
    }

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=settings.DEBUG,
        log_level="info"
    )
