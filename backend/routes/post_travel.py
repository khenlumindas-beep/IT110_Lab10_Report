"""
Post-Travel Routes (FR-F07, FR-A06, BR-05)
Faculty submit and track post-travel deliverables; admin monitors completion.
Post-travel completion feeds the compliance engine.
"""
from fastapi import APIRouter, Depends, HTTPException, status as http_status, Query, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import PostTravelRequirement, Travel, DocumentType, User
from schemas import (
    PostTravelRequirementCreate, PostTravelRequirementUpdate,
    PostTravelRequirementResponse,
)
from security import get_current_user, get_current_admin, TokenData
from routes.documents import save_uploaded_file, delete_uploaded_file
from routes.notifications import create_travel_notification, create_admin_notification
from audit import log_audit, record_remark
from compliance import persist_compliance
from config import settings
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/travels/{travel_id}/post-travel", tags=["post-travel"])

_BLOCKING = ('Not Submitted', 'Submitted', 'Incomplete')


def _get_owned_travel(db: Session, travel_id: int, current_user: TokenData) -> Travel:
    travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
    if not travel:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Travel not found")
    if current_user.role != "super_admin" and travel.user_id != current_user.user_id:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Not authorized for this travel")
    return travel


def _notify_compliance(db: Session, travel_id: int, actor_user_id: int) -> None:
    """Recompute and persist compliance after a post-travel change (BR-07)."""
    try:
        persist_compliance(db, travel_id, actor_user_id=actor_user_id)
    except Exception as e:
        logger.error(f"Compliance recompute failed for travel {travel_id}: {e}")


# ==================== LIST (faculty owner or admin) ====================

@router.get("/", response_model=list[PostTravelRequirementResponse])
async def list_post_travel(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List post-travel requirements for a travel (owner or admin)."""
    _get_owned_travel(db, travel_id, current_user)
    return (db.query(PostTravelRequirement)
            .filter(PostTravelRequirement.travel_id == travel_id)
            .order_by(PostTravelRequirement.requirement_id)
            .all())


# ==================== CREATE ====================

@router.post("/", response_model=PostTravelRequirementResponse, status_code=http_status.HTTP_201_CREATED)
async def create_post_travel(
    travel_id: int,
    data: PostTravelRequirementCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a post-travel requirement (owner faculty or admin)."""
    _get_owned_travel(db, travel_id, current_user)

    if data.doc_type_id is not None:
        if not db.query(DocumentType).filter(DocumentType.doc_type_id == data.doc_type_id).first():
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Document type not found")

    req = PostTravelRequirement(
        travel_id=travel_id,
        requirement=data.requirement,
        doc_type_id=data.doc_type_id,
        due_date=data.due_date,
        status="Not Submitted",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    record_remark(db, travel_id=travel_id, admin_id=current_user.user_id,
                  remark_type="Post-Travel", action="General",
                  affected_requirement=data.requirement,
                  remark_text="Post-travel requirement added.")
    log_audit(db, current_user.user_id, 'travel', 'create', travel_id,
              f"Post-travel requirement added: {data.requirement}")
    _notify_compliance(db, travel_id, current_user.user_id)

    return req


# ==================== UPDATE (status / remarks) ====================

@router.patch("/{requirement_id}", response_model=PostTravelRequirementResponse)
async def update_post_travel(
    travel_id: int,
    requirement_id: int,
    data: PostTravelRequirementUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a post-travel requirement. Faculty may submit; only admin verifies or waives (BR-02)."""
    _get_owned_travel(db, travel_id, current_user)
    req = (db.query(PostTravelRequirement)
           .filter(PostTravelRequirement.requirement_id == requirement_id,
                   PostTravelRequirement.travel_id == travel_id)
           .first())
    if not req:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Post-travel requirement not found")

    is_admin = current_user.role == "super_admin"
    new_status = data.status

    # Guard: faculty cannot mark Verified/Waived - that is admin-only (BR-02, BR-09).
    if new_status in ('Verified', 'Waived') and not is_admin:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN,
                            "Only admin can verify or waive post-travel requirements")

    previous = req.status

    if data.requirement is not None:
        req.requirement = data.requirement
    if data.due_date is not None:
        req.due_date = data.due_date
    if data.remarks is not None:
        req.remarks = data.remarks
    if new_status is not None:
        req.status = new_status
        if new_status == 'Verified':
            req.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(req)

    if new_status is not None and new_status != previous:
        record_remark(db, travel_id=travel_id, document_id=None,
                      admin_id=current_user.user_id,
                      remark_type="Post-Travel",
                      action="Resubmission Required" if new_status in _BLOCKING else "General",
                      affected_requirement=req.requirement,
                      remark_text=f"Post-travel status: {previous} -> {new_status}.",
                      previous_status=previous, new_status=new_status)
        log_audit(db, current_user.user_id, 'travel', 'update', travel_id,
                  f"Post-travel '{req.requirement}': {previous} -> {new_status}")

    _notify_compliance(db, travel_id, current_user.user_id)
    return req


# ==================== UPLOAD EVIDENCE (faculty) ====================

@router.post("/{requirement_id}/evidence", response_model=PostTravelRequirementResponse)
async def upload_post_travel_evidence(
    travel_id: int,
    requirement_id: int,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Attach an evidence file to a post-travel requirement and mark it Submitted (FR-F07)."""
    _get_owned_travel(db, travel_id, current_user)
    req = (db.query(PostTravelRequirement)
           .filter(PostTravelRequirement.requirement_id == requirement_id,
                   PostTravelRequirement.travel_id == travel_id)
           .first())
    if not req:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Post-travel requirement not found")

    allowed = {'.pdf', '.jpg', '.jpeg', '.png'}
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in allowed:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Only PDF, JPG, PNG allowed (BR-11)")

    if req.evidence_path:
        delete_uploaded_file(req.evidence_path)

    filename, filepath = save_uploaded_file(file, travel_id)
    previous = req.status
    req.evidence_path = filepath
    req.status = "Submitted"

    db.commit()
    db.refresh(req)

    record_remark(db, travel_id=travel_id, admin_id=current_user.user_id,
                  remark_type="Post-Travel", action="For Verification",
                  affected_requirement=req.requirement,
                  remark_text=f"Evidence uploaded for post-travel '{req.requirement}'.",
                  previous_status=previous, new_status="Submitted")
    log_audit(db, current_user.user_id, 'travel', 'update', travel_id,
              f"Post-travel evidence uploaded: {req.requirement} ({filename})")
    create_travel_notification(db, travel_id,
                               "Post-Travel Evidence Submitted",
                               f"Your post-travel evidence '{req.requirement}' is awaiting verification.",
                               "info")
    _notify_compliance(db, travel_id, current_user.user_id)

    return req


# ==================== DELETE (admin only) ====================

@router.delete("/{requirement_id}", status_code=http_status.HTTP_200_OK)
async def delete_post_travel(
    travel_id: int,
    requirement_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete a post-travel requirement (admin only)."""
    req = (db.query(PostTravelRequirement)
           .filter(PostTravelRequirement.requirement_id == requirement_id,
                   PostTravelRequirement.travel_id == travel_id)
           .first())
    if not req:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Post-travel requirement not found")

    if req.evidence_path:
        delete_uploaded_file(req.evidence_path)

    label = req.requirement
    db.delete(req)
    db.commit()

    log_audit(db, current_user.user_id, 'travel', 'delete', travel_id,
              f"Post-travel requirement deleted: {label}")
    _notify_compliance(db, travel_id, current_user.user_id)
    return {"message": "Post-travel requirement deleted"}
