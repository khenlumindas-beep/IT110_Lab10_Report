"""
Security Module
Handles JWT authentication, password hashing, and token management
"""
from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings
import logging

logger = logging.getLogger(__name__)

# HTTP Bearer for token extraction
security = HTTPBearer()
# Lenient variant for endpoints that also accept `?token=` (file downloads):
# must NOT 401 on a missing Authorization header, so the query fallback can run.
security_optional = HTTPBearer(auto_error=False)

class TokenData:
    """Token payload data"""
    def __init__(self, user_id: int, email: str, role: str, full_name: str = ""):
        self.user_id = user_id
        self.email = email
        self.role = role
        self.full_name = full_name

class AuthenticationManager:
    """Manages authentication operations"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8")
            )
        except Exception:
            return False
    
    @staticmethod
    def create_access_token(
        data: Dict,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        
        to_encode.update({"exp": expire, "type": "access"})
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: Dict) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        
        to_encode.update({"exp": expire, "type": "refresh"})
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        
        return encoded_jwt
    
    @staticmethod
    def decode_token(token: str) -> Optional[TokenData]:
        """Decode and validate JWT token"""
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            
            user_id: int = payload.get("user_id")
            email: str = payload.get("email")
            role: str = payload.get("role")
            full_name: str = payload.get("full_name", "")
            
            if user_id is None or email is None:
                return None
            
            return TokenData(user_id=user_id, email=email, role=role, full_name=full_name)
        
        except JWTError as e:
            logger.error(f"Token decode error: {str(e)}")
            return None
    
    @staticmethod
    def get_current_user_from_token(token: str):
        """Extract and validate user from token"""
        token_data = AuthenticationManager.decode_token(token)
        
        if token_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return token_data

# Dependency to get current user
def _live_account_check(token_data: TokenData) -> TokenData:
    """Re-check the account against the DB on every request.

    UbeDelights-style behaviour: deactivating a user instantly logs them out
    (deactivated/removed accounts reject the still-valid JWT) and role
    changes take effect immediately without waiting for token expiry.
    """
    from database import SessionLocal
    from models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == token_data.user_id).first()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated or no longer exists",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_data.role = user.role
        if user.full_name:
            token_data.full_name = user.full_name
    finally:
        db.close()
    return token_data


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Dependency to extract current user from JWT token
    Usage: async def endpoint(current_user: TokenData = Depends(get_current_user)):
    """
    token = credentials.credentials
    return _live_account_check(AuthenticationManager.get_current_user_from_token(token))

async def get_current_admin(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure current user is admin
    Usage: async def endpoint(current_user: TokenData = Depends(get_current_admin)):
    """
    if current_user.role not in ["super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

async def get_current_faculty(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure current user is faculty
    """
    if current_user.role not in ["faculty", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

# Optional user (doesn't fail if not authenticated)
async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Get optional user - returns None if not authenticated"""
    if credentials is None:
        return None
    
    token = credentials.credentials
    return AuthenticationManager.get_current_user_from_token(token)


async def get_current_user_header_or_query(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    token: Optional[str] = None,
):
    """Like get_current_user, but also accepts the JWT via `token` query param.

    Needed for browser/native file downloads where custom headers cannot be set.
    """
    if credentials is not None:
        return _live_account_check(
            AuthenticationManager.get_current_user_from_token(credentials.credentials))
    if token:
        return _live_account_check(
            AuthenticationManager.get_current_user_from_token(token))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
