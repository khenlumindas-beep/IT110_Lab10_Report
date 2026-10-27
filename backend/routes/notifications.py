"""
Notifications and Announcements Routes
Handles user notifications and system-wide announcements
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from database import get_db
from models import Notification, Announcement, User, Travel
from schemas import NotificationResponse
from security import get_current_user, get_current_admin, TokenData
from audit import log_audit
from datetime import datetime
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["notifications"])

# ==================== NOTIFICATIONS ====================

@router.get("/notifications/", response_model=List[NotificationResponse])
async def get_notifications(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False)
):
    """Get user's notifications"""
    try:
        query = db.query(Notification).filter(
            Notification.user_id == current_user.user_id
        )
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        notifications = query.order_by(
            desc(Notification.created_at)
        ).offset(skip).limit(limit).all()
        
        return notifications
    
    except Exception as e:
        logger.error(f"Error retrieving notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/notifications/unread/count")
async def get_unread_count(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get count of unread notifications"""
    try:
        unread_count = db.query(Notification).filter(
            and_(
                Notification.user_id == current_user.user_id,
                Notification.is_read == False
            )
        ).count()
        
        return {"unread_count": unread_count}
    
    except Exception as e:
        logger.error(f"Error counting unread notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_as_read(
    notification_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark notification as read"""
    try:
        notification = db.query(Notification).filter(
            and_(
                Notification.notification_id == notification_id,
                Notification.user_id == current_user.user_id
            )
        ).first()
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        notification.is_read = True
        db.commit()
        db.refresh(notification)
        
        logger.info(f"Notification marked as read: {notification_id}")
        
        return notification
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.patch("/notifications/read-all")
async def mark_all_as_read(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark all notifications as read"""
    try:
        unread = db.query(Notification).filter(
            and_(
                Notification.user_id == current_user.user_id,
                Notification.is_read == False
            )
        ).all()
        
        for notification in unread:
            notification.is_read = True
        
        db.commit()
        
        logger.info(f"All notifications marked as read for user {current_user.user_id}")
        
        return {"message": f"Marked {len(unread)} notifications as read"}
    
    except Exception as e:
        logger.error(f"Error marking all as read: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete notification"""
    try:
        notification = db.query(Notification).filter(
            and_(
                Notification.notification_id == notification_id,
                Notification.user_id == current_user.user_id
            )
        ).first()
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        db.delete(notification)
        db.commit()
        
        logger.info(f"Notification deleted: {notification_id}")
        
        return {"message": "Notification deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== ANNOUNCEMENTS ====================

@router.get("/announcements/")
async def get_announcements(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    """Get active announcements"""
    try:
        announcements = db.query(Announcement).filter(
            Announcement.is_active == True
        ).order_by(desc(Announcement.created_at)).offset(skip).limit(limit).all()
        
        return announcements
    
    except Exception as e:
        logger.error(f"Error retrieving announcements: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.post("/announcements/")
async def create_announcement(
    announcement_data: dict,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create announcement (admin only)"""
    try:
        title = announcement_data.get('title')
        content = announcement_data.get('content')
        
        if not title or not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Title and content are required"
            )
        
        announcement = Announcement(
            title=title,
            content=content,
            created_by=current_user.user_id,
            is_active=True
        )
        
        db.add(announcement)
        db.commit()
        db.refresh(announcement)
        log_audit(db, current_user.user_id, 'announcement', 'create',
                  announcement.announcement_id,
                  f"Announcement created: {title}")
        
        logger.info(f"Announcement created: {announcement.announcement_id}")
        
        # Create notifications for all users
        all_users = db.query(User).all()
        for user in all_users:
            notification = Notification(
                user_id=user.user_id,
                title=f"New Announcement: {title}",
                message=content[:200] + "..." if len(content) > 200 else content,
                type="info"
            )
            db.add(notification)
        
        db.commit()
        
        return {
            "announcement_id": announcement.announcement_id,
            "message": f"Announcement created and notified {len(all_users)} users"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating announcement: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.put("/announcements/{announcement_id}")
async def update_announcement(
    announcement_id: int,
    announcement_data: dict,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update announcement (admin only)"""
    try:
        announcement = db.query(Announcement).filter(
            Announcement.announcement_id == announcement_id
        ).first()
        
        if not announcement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Announcement not found"
            )
        
        for field, value in announcement_data.items():
            if value is not None and hasattr(announcement, field):
                setattr(announcement, field, value)
        
        db.commit()
        db.refresh(announcement)
        log_audit(db, current_user.user_id, 'announcement', 'update',
                  announcement_id, f"Announcement updated: {announcement.title}")
        
        logger.info(f"Announcement updated: {announcement_id}")
        
        return announcement
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating announcement: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.patch("/announcements/{announcement_id}/deactivate")
async def deactivate_announcement(
    announcement_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Deactivate announcement (admin only)"""
    try:
        announcement = db.query(Announcement).filter(
            Announcement.announcement_id == announcement_id
        ).first()
        
        if not announcement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Announcement not found"
            )
        
        announcement.is_active = False
        db.commit()
        db.refresh(announcement)
        log_audit(db, current_user.user_id, 'announcement', 'update',
                  announcement_id,
                  f"Announcement deactivated: {announcement.title}")
        
        logger.info(f"Announcement deactivated: {announcement_id}")
        
        return announcement
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating announcement: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== NOTIFICATION UTILITIES ====================

def create_travel_notification(
    db: Session,
    travel_id: int,
    title: str,
    message: str,
    notif_type: str = "info"
):
    """Create notification for travel-related events"""
    try:
        travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
        if not travel:
            return
        
        notification = Notification(
            user_id=travel.user_id,
            travel_id=travel_id,
            title=title,
            message=message,
            type=notif_type
        )
        
        db.add(notification)
        db.commit()
        
        logger.info(f"Travel notification created for travel {travel_id}")
    
    except Exception as e:
        logger.error(f"Error creating travel notification: {str(e)}")

def create_admin_notification(
    db: Session,
    title: str,
    message: str,
    notif_type: str = "warning"
):
    """Create notification for all admins"""
    try:
        admins = db.query(User).filter(User.role == "super_admin").all()
        
        for admin in admins:
            notification = Notification(
                user_id=admin.user_id,
                title=title,
                message=message,
                type=notif_type
            )
            db.add(notification)
        
        db.commit()
        logger.info(f"Admin notification created for {len(admins)} admins")
    
    except Exception as e:
        logger.error(f"Error creating admin notification: {str(e)}")
