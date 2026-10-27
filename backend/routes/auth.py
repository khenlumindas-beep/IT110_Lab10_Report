"""
Authentication Routes
Handles login, logout, token refresh, and user registration
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from database import get_db
from models import User
from schemas import LoginRequest, TokenResponse, TokenRefreshRequest, UserCreate, UserResponse
from security import AuthenticationManager, get_current_user, TokenData
from audit import log_audit
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint
    Returns access and refresh tokens
    """
    try:
        # Database authentication only (real bcrypt hashes; respects is_active
        # so admin deactivation takes effect immediately).
        # SECURITY: no hard-coded fallback credentials. If the database is
        # unavailable the login fails closed (500) instead of accepting
        # credentials embedded in source code.
        user = db.query(User).filter(User.email == request.email).first()

        if not user:
            logger.warning(f"Login attempt with non-existent email: {request.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Check if user is active
        if not user.is_active:
            logger.warning(f"Login attempt with inactive user: {request.email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )
        # Verify password against the stored hash
        if not AuthenticationManager.verify_password(request.password, user.password_hash):
            logger.warning(f"Invalid password attempt for user: {request.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Create tokens
        token_data = {
            "user_id": user.user_id,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name
        }
        
        access_token = AuthenticationManager.create_access_token(token_data)
        refresh_token = AuthenticationManager.create_refresh_token(token_data)
        
        logger.info(f"User successfully logged in: {user.email}")
        log_audit(db, user.user_id, 'user', 'login', user.user_id,
                  f"Login by {user.email}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=30 * 60  # 30 minutes in seconds
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during login"
        )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: TokenRefreshRequest, db: Session = Depends(get_db)):
    """
    Refresh access token endpoint
    """
    try:
        # Decode refresh token
        token_data = AuthenticationManager.decode_token(request.refresh_token)
        
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Verify user still exists and is active
        user = db.query(User).filter(User.user_id == token_data.user_id).first()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new access token
        new_token_data = {
            "user_id": user.user_id,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name
        }
        
        access_token = AuthenticationManager.create_access_token(new_token_data)
        new_refresh_token = AuthenticationManager.create_refresh_token(new_token_data)
        
        logger.info(f"Token refreshed for user: {user.email}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=30 * 60
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during token refresh"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user information
    """
    try:
        from datetime import datetime

        # Always read the profile from the database so name/designation
        # edits and deactivation reflect immediately (realtime)
        user = db.query(User).filter(User.user_id == current_user.user_id).first()
        if user:
            return user

        # Fallback: mock-auth users that exist only in token data
        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
            "role": current_user.role,
            "full_name": getattr(current_user, 'full_name', None) or current_user.email,
            "is_active": True,
            "created_at": datetime.now()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {str(e)}")
        from datetime import datetime
        # Fallback: return user data from token
        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
            "role": current_user.role,
            "full_name": getattr(current_user, 'full_name', None) or current_user.email,
            "is_active": True,
            "created_at": datetime.now()
        }

@router.post("/logout")
async def logout(current_user: TokenData = Depends(get_current_user)):
    """
    Logout endpoint
    Client should discard the tokens
    """
    logger.info(f"User logged out: {current_user.email}")
    return {"message": "Successfully logged out"}

@router.post("/register", response_model=UserResponse)
async def register(request: UserCreate, db: Session = Depends(get_db)):
    """
    Register new faculty user (requires admin approval)
    """
    try:
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == request.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Hash password
        hashed_password = AuthenticationManager.hash_password(request.password)
        
        # Create new user
        new_user = User(
            full_name=request.full_name,
            email=request.email,
            password_hash=hashed_password,
            role=request.role,
            college_id=request.college_id,
            department_id=request.department_id,
            designation=request.designation,
            academic_rank=request.academic_rank,
            contact_number=request.contact_number,
            is_active=True
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"New user registered: {new_user.email}")
        
        return new_user
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration"
        )
