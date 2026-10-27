"""
User Management Routes
Handles user profile, update, and admin functions
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import User
from schemas import UserResponse, UserProfileResponse, UserCreate, ChangePasswordRequest
from security import get_current_user, get_current_admin, TokenData, AuthenticationManager
from audit import log_audit
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])

# Roles allowed by the users_role_check constraint + UbeDelights-style rules
VALID_ROLES = ("super_admin", "faculty")
MAX_ACTIVE_SUPER_ADMINS = 2


def _active_super_admin_count(db: Session) -> int:
    return db.query(User).filter(
        User.role == "super_admin", User.is_active == True).count()

@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's full profile"""
    try:
        user = db.query(User).filter(User.user_id == current_user.user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return user
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.put("/profile", response_model=UserProfileResponse)
async def update_user_profile(
    user_data: dict,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile"""
    try:
        user = db.query(User).filter(User.user_id == current_user.user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update allowed fields
        allowed_fields = ['full_name', 'designation', 'academic_rank', 'contact_number']
        for field, value in user_data.items():
            if field in allowed_fields and value is not None:
                setattr(user, field, value)
        
        db.commit()
        db.refresh(user)
        
        logger.info(f"User profile updated: {user.email}")
        
        return user
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/", response_model=list[UserResponse])
async def list_users(
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all users (admin only)"""
    try:
        users = db.query(User).offset(skip).limit(limit).all()
        return users
    
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_by_id(
    user_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get user by ID (admin only)"""
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return user
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create new user (admin only)"""
    try:
        # Role whitelist (mirrors UbeDelights role validation)
        if user_data.role not in VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role"
            )
        # Max active super admins (UbeDelights max-2 rule)
        if user_data.role == "super_admin" and \
                _active_super_admin_count(db) >= MAX_ACTIVE_SUPER_ADMINS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum of 2 active super admin accounts reached. "
                       "Deactivate or demote an existing super admin first."
            )
        # Check if email exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
        
        # Hash password
        from security import AuthenticationManager
        hashed_password = AuthenticationManager.hash_password(user_data.password)
        
        # Create user
        new_user = User(
            full_name=user_data.full_name,
            email=user_data.email,
            password_hash=hashed_password,
            role=user_data.role,
            college_id=user_data.college_id,
            department_id=user_data.department_id,
            designation=user_data.designation,
            academic_rank=user_data.academic_rank,
            contact_number=user_data.contact_number
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        log_audit(db, current_user.user_id, 'user', 'create', new_user.user_id,
                  f"User created: {new_user.email} ({new_user.role})")
        
        logger.info(f"New user created: {new_user.email}")
        
        return new_user
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: dict,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update user (admin only)"""
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Whitelist: role / password / is_active must NEVER change here
        # (role changes go through POST /{user_id}/role with cap + hierarchy
        # checks; activation through POST /{user_id}/reactivate).
        allowed_fields = {
            'full_name', 'designation', 'academic_rank', 'contact_number',
            'college_id', 'department_id',
        }
        changed = []
        for field, value in user_data.items():
            if field in allowed_fields and value is not None \
                    and getattr(user, field, None) != value:
                setattr(user, field, value)
                changed.append(field)
        
        db.commit()
        db.refresh(user)
        log_audit(db, current_user.user_id, 'user', 'update', user_id,
                  f"User updated: {user.email} (fields: {', '.join(changed) or 'none'})")
        
        logger.info(f"User updated: {user.email}")
        
        return user
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.delete("/{user_id}")
async def deactivate_user(
    user_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Deactivate user (admin only)"""
    try:
        # No self-deactivation (UbeDelights self-harm guard)
        if user_id == current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account"
            )
        user = db.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user.is_active = False
        db.commit()
        log_audit(db, current_user.user_id, 'user', 'deactivate', user_id,
                  f"User deactivated: {user.email}")
        
        logger.info(f"User deactivated: {user.email}")
        
        return {"message": "User deactivated successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating user: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )


@router.post("/{user_id}/role")
async def change_user_role(
    user_id: int,
    body: dict,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Change a user's role (super admin only).

    UbeDelights SUPER_ADMIN_TRANSFER behaviour: the target account is
    blocked (deactivated) on every role change and must be reactivated by a
    super admin — this forces a fresh login so the new role/session is clean.
    """
    new_role = (body.get("role") or "").strip()
    if new_role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role"
        )

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.user_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role"
        )

    old_role = user.role
    if old_role == new_role:
        return {"message": f"User already has the role '{new_role}'"}

    if new_role == "super_admin" and \
            _active_super_admin_count(db) >= MAX_ACTIVE_SUPER_ADMINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 2 active super admin accounts reached. "
                   "Demote an existing super admin first."
        )

    user.role = new_role
    user.is_active = False  # force re-login (transfer safety)
    db.commit()
    log_audit(db, current_user.user_id, 'user', 'update', user_id,
              f"Role changed: {user.email} ({old_role} -> {new_role}); "
              f"account blocked pending reactivation")
    logger.info(f"Role changed for {user.email}: {old_role} -> {new_role}")

    return {"message": f"Role changed to {new_role}. "
                       f"The account is now blocked and must be reactivated."}


@router.post("/{user_id}/reactivate")
async def reactivate_user(
    user_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Reactivate (unblock) a deactivated user (admin only)."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.is_active:
        return {"message": "User is already active"}

    # UbeDelights unblock rule: reactivating a super admin respects the cap
    if user.role == "super_admin" and \
            _active_super_admin_count(db) >= MAX_ACTIVE_SUPER_ADMINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 2 active super admin accounts reached. "
                   "Demote an existing super admin first."
        )

    user.is_active = True
    db.commit()
    log_audit(db, current_user.user_id, 'user', 'reactivate', user_id,
              f"User reactivated: {user.email}")
    logger.info(f"User reactivated: {user.email}")

    return {"message": "User reactivated successfully"}

@router.post("/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change current user's password (verifies current password first)"""
    try:
        user = db.query(User).filter(User.user_id == current_user.user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        if not AuthenticationManager.verify_password(password_data.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        user.password_hash = AuthenticationManager.hash_password(password_data.new_password)
        db.commit()

        logger.info(f"Password changed for: {user.email}")
        return {"message": "Password changed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )
