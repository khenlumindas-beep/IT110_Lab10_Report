"""
Compliance Routes (FR-F09, FR-A05, BR-04, BR-07)
On-demand recomputation, per-travel status, institutional monitoring and
travel-limit flagging. Compliance is always calculated from actual records.
"""
from fastapi import APIRouter, Depends, HTTPException, status as http_status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional

from database import get_db
from models import ComplianceRecord, Travel, User
from schemas import ComplianceRecordResponse, TravelLimitCheck
from security import get_current_user, get_current_admin, TokenData
from audit import log_audit
from compliance import compute_compliance, persist_compliance, travel_limit_exceeded
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["compliance"])


# ==================== RECOMPUTE (admin) ====================

@router.post("/travels/{travel_id}/compliance/recompute", response_model=ComplianceRecordResponse)
async def recompute_compliance(
    travel_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Force a compliance recalculation for a travel (BR-07, admin only)."""
    if not db.query(Travel).filter(Travel.travel_id == travel_id).first():
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Travel not found")

    try:
        data = persist_compliance(db, travel_id, actor_user_id=current_user.user_id)
    except ValueError as e:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, str(e))

    return db.query(ComplianceRecord).filter(
        ComplianceRecord.travel_id == travel_id).first()


# ==================== VIEW (faculty owner or admin) ====================

@router.get("/travels/{travel_id}/compliance", response_model=ComplianceRecordResponse)
async def get_compliance(
    travel_id: int,
    recompute: bool = Query(False, description="Recompute before returning"),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """View compliance for a travel. Faculty see their own; admin sees any (BR-09)."""
    travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
    if not travel:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Travel not found")
    if current_user.role != "super_admin" and travel.user_id != current_user.user_id:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Not authorized for this travel")

    if recompute:
        try:
            persist_compliance(db, travel_id, actor_user_id=current_user.user_id)
        except ValueError as e:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, str(e))

    record = db.query(ComplianceRecord).filter(
        ComplianceRecord.travel_id == travel_id).first()

    if record is None:
        # Lazy first computation if never computed for this travel.
        try:
            persist_compliance(db, travel_id, actor_user_id=current_user.user_id)
        except ValueError as e:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, str(e))
        record = db.query(ComplianceRecord).filter(
            ComplianceRecord.travel_id == travel_id).first()

    return record


# ==================== MONITORING (admin, FR-A05) ====================

@router.get("/compliance/records", response_model=List[ComplianceRecordResponse])
async def list_compliance(
    status: Optional[str] = Query(None, description="Filter by compliance status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    user_id: Optional[int] = Query(None, description="Filter by faculty owner"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Institution-wide compliance monitoring, worst-priority first (FR-A05)."""
    q = db.query(ComplianceRecord).join(Travel, Travel.travel_id == ComplianceRecord.travel_id)

    if status:
        q = q.filter(ComplianceRecord.status == status)
    if priority:
        q = q.filter(ComplianceRecord.priority == priority)
    if user_id is not None:
        q = q.filter(Travel.user_id == user_id)

    order = {
        'high': 0, 'medium': 1, 'low': 2,
    }
    rows = q.order_by(ComplianceRecord.computed_at.desc()).limit(limit).offset(offset).all()
    rows.sort(key=lambda r: order.get(r.priority, 3))
    return rows


# ==================== TRAVEL LIMIT (BR-04) ====================

@router.get("/compliance/travel-limit/{faculty_user_id}", response_model=TravelLimitCheck)
async def check_travel_limit(
    faculty_user_id: int,
    year: Optional[int] = Query(None),
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Flag faculty exceeding the allowed foreign-travel frequency per year (BR-04)."""
    if not db.query(User).filter(User.user_id == faculty_user_id).first():
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Faculty user not found")
    return travel_limit_exceeded(db, faculty_user_id, year)


@router.get("/compliance/travel-limits", response_model=List[TravelLimitCheck])
async def list_travel_limits(
    year: Optional[int] = Query(None),
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """All faculty who exceed the travel-frequency rule this year (BR-04)."""
    faculty = db.query(User).filter(User.role == 'faculty').all()
    results = []
    for u in faculty:
        check = travel_limit_exceeded(db, u.user_id, year)
        if check['exceeded']:
            results.append(check)
    return results
