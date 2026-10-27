"""
Database Configuration and Connection Module
Handles PostgreSQL database connections and session management
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from config import settings
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://"),
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    echo=settings.DEBUG,
    connect_args={
        "connect_timeout": 10,
        "application_name": "smarttrack",
    }
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Create Base for models
Base = declarative_base()

# Event listener for connection pool
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set connection parameters"""
    pass

def get_db():
    """
    Dependency to get database session
    Usage: @app.get("/") def read_root(db: Session = Depends(get_db)):
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

def close_db():
    """Close database connection"""
    engine.dispose()
