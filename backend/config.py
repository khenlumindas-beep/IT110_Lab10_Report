"""
SmartTrack Configuration Module
Handles all configuration settings for the application
"""
import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    """Application Settings"""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres@127.0.0.1:5432/smarttrack_db"
    )
    
    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Application
    APP_NAME: str = "SmartTrack"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # CORS - Allow all localhost variants, common dev ports, and LAN IP (physical devices)
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:80",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:4200",
        "http://localhost:4842",
        "http://localhost:5000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:10511",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:4200",
        "http://127.0.0.1:5000",
        "http://127.0.0.1:8000",
        # LAN IP — physical devices (phone) access the backend via PC's IP
        "http://192.168.1.80",
        "http://192.168.1.80:3000",
        "http://192.168.1.80:5000",
        "http://192.168.1.58",
        "http://192.168.1.58:3000",
        "http://192.168.1.58:5000",
    ]
    
    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 52428800  # 50MB
    
    # SMTP (Optional)
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    
    # ML Model
    MODEL_PATH: str = "./models"
    RISK_THRESHOLD: float = 0.6
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables

# Create global settings instance
settings = Settings()
