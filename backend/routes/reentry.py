"""
Re-Entry Routes (FR-F08, FR-A07, BR-06)
Faculty submit and update re-entry activities with evidence; admin monitors.
Re-entry completion feeds the compliance engine.
"""
from fastapi import APIRouter, Depends, HTTPException, status as http_status, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import ReentryActivity, Travel
from schemas import ReentryActivityCreate, ReentryActivityUpdate, ReentryActivityResponse
from security import get_current_user, get_current_admin, TokenData
from routes.documents import save_uploaded_file, delete_uploaded_file
from routes.notifications import create_travel_notification
from audit import log_audit, record_remark
from compliance import persist_compliance
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/travels/{travel_id}/re-entry", tags=["re-entry"])

_BLOCKING = ('Not Started', 'For Implementation', 'Ongoing', 'Not Complied')


def _get_owned_travel(db: Session, travel_id: int, current_user: TokenData) -> Travel:
    travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
    if not travel:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Travel not found")
    if current_user.role != "super_admin" and travel.user_id != current_user.user_id:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Not authorized for this travel")
    return travel


def _notify_compliance(db: Session, travel_id: int, actor_user_id: int) -> None:
    try:
        persist_compliance(db, travel_id, actor_user_id=actor_user_id)
    except Exception as e:
        logger.error(f"Compliance recompute failed for travel {travel_id}: {e}")


# ==================== LIST ====================

@router.get("/", response_model=list[ReentryActivityResponse])
async def list_reentry(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List re-entry activities for a travel (owner or admin)."""
    _get_owned_travel(db, travel_id, current_user)
    return (db.query(ReentryActivity)
            .filter(ReentryActivity.travel_id == travel_id)
            .order_by(ReentryActivity.activity_id)
            .all())


# ==================== CREATE ====================

@router.post("/", response_model=ReentryActivityResponse, status_code=http_status.HTTP_201_CREATED)
async def create_reentry(
    travel_id: int,
    data: ReentryActivityCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a re-entry activity (knowledge-sharing plan) for a travel (FR-F08)."""
    _get_owned_travel(db, travel_id, current_user)

    activity = ReentryActivity(
        travel_id=travel_id,
        activity=data.activity,
        description=data.description,
        target_date=data.target_date,
        status="Not Started",
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    record_remark(db, travel_id=travel_id, admin_id=current_user.user_id,
                  remark_type="Re-Entry", action="General",
                  affected_requirement=data.activity,
                  remark_text="Re-entry activity added.")
    log_audit(db, current_user.user_id, 'travel', 'create', travel_id,
              f"Re-entry activity added: {data.activity}")
    _notify_compliance(db, travel_id, current_user.user_id)

    return activity


# ==================== UPDATE ====================

@router.patch("/{activity_id}", response_model=ReentryActivityResponse)
async def update_reentry(
    travel_id: int,
    activity_id: int,
    data: ReentryActivityUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a re-entry activity. Faculty manage their own; admin may set any status (BR-09)."""
    _get_owned_travel(db, travel_id, current_user)
    activity = (db.query(ReentryActivity)
                .filter(ReentryActivity.activity_id == activity_id,
                        ReentryActivity.travel_id == travel_id)
                .first())
    if not activity:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Re-entry activity not found")

    is_admin = current_user.role == "super_admin"
    previous = activity.status
    new_status = data.status

    if data.activity is not None:
        activity.activity = data.activity
    if data.description is not None:
        activity.description = data.description
    if data.target_date is not None:
        activity.target_date = data.target_date
    if data.remarks is not None:
        activity.remarks = data.remarks
    if new_status is not None:
        activity.status = new_status
        if new_status == 'Completed':
            activity.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(activity)

    if new_status is not None and new_status != previous:
        action = "Resubmission Required" if new_status == 'Not Complied' else "General"
        record_remark(db, travel_id=travel_id, admin_id=current_user.user_id,
                      remark_type="Re-Entry", action=action,
                      affected_requirement=activity.activity,
                      remark_text=f"Re-entry status: {previous} -> {new_status}.",
                      previous_status=previous, new_status=new_status)
        log_audit(db, current_user.user_id, 'travel', 'update', travel_id,
                  f"Re-entry '{activity.activity}': {previous} -> {new_status}")

    _notify_compliance(db, travel_id, current_user.user_id)
    return activity


# ==================== UPLOAD EVIDENCE (BR-06) ====================

@router.post("/{activity_id}/evidence", response_model=ReentryActivityResponse)
async def upload_reentry_evidence(
    travel_id: int,
    activity_id: int,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Attach evidence for a re-entry activity and move it to Ongoing (FR-F08)."""
    _get_owned_travel(db, travel_id, current_user)
    activity = (db.query(ReentryActivity)
                .filter(ReentryActivity.activity_id == activity_id,
                        ReentryActivity.travel_id == travel_id)
                .first())
    if not activity:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Re-entry activity not found")

    allowed = {'.pdf', '.jpg', '.jpeg', '.png'}
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in allowed:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Only PDF, JPG, PNG allowed (BR-11)")

    if activity.evidence_path:
        delete_uploaded_file(activity.evidence_path)

    filename, filepath = save_uploaded_file(file, travel_id)
    previous = activity.status
    activity.evidence_path = filepath
    if activity.status in ('Not Started', 'For Implementation'):
        activity.status = "Ongoing"

    db.commit()
    db.refresh(activity)

    record_remark(db, travel_id=travel_id, admin_id=current_user.user_id,
                  remark_type="Re-Entry", action="For Verification",
                  affected_requirement=activity.activity,
                  remark_text=f"Re-entry evidence uploaded for '{activity.activity}'.",
                  previous_status=previous, new_status=activity.status)
    log_audit(db, current_user.user_id, 'travel', 'update', travel_id,
              f"Re-entry evidence uploaded: {activity.activity} ({filename})")
    create_travel_notification(db, travel_id,
                               "Re-Entry Evidence Submitted",
                               f"Your re-entry evidence '{activity.activity}' has been recorded.",
                               "info")
    _notify_compliance(db, travel_id, current_user.user_id)

    return activity


# ==================== DELETE (admin only) ====================

@router.delete("/{activity_id}", status_code=http_status.HTTP_200_OK)
async def delete_reentry(
    travel_id: int,
    activity_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete a re-entry activity (admin only)."""
    activity = (db.query(ReentryActivity)
                .filter(ReentryActivity.activity_id == activity_id,
                        ReentryActivity.travel_id == travel_id)
                .first())
    if not activity:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Re-entry activity not found")

    if activity.evidence_path:
        delete_uploaded_file(activity.evidence_path)

    label = activity.activity
    db.delete(activity)
    db.commit()

    log_audit(db, current_user.user_id, 'travel', 'delete', travel_id,
              f"Re-entry activity deleted: {label}")
    _notify_compliance(db, travel_id, current_user.user_id)
    return {"message": "Re-entry activity deleted"}
