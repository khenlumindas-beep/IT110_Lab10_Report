"""
Audit-log and remark-history read endpoints (FR-A15, BR-10, BR-12).
Admin-only. Backed by the append-only audit_logs / remark_history tables
created in migration_008.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog, RemarkHistory, Travel
from security import get_current_admin, get_current_user, TokenData

router = APIRouter(prefix="/api", tags=["audit"])


def _serialize_audit(row: AuditLog) -> dict:
    return {
        "audit_id": row.audit_id,
        "user_id": row.user_id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "action": row.action,
        "description": row.description,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_remark(row: RemarkHistory) -> dict:
    return {
        "remark_id": row.remark_id,
        "travel_id": row.travel_id,
        "document_id": row.document_id,
        "admin_id": row.admin_id,
        "remark_type": row.remark_type,
        "action": row.action,
        "affected_requirement": row.affected_requirement,
        "remark_text": row.remark_text,
        "previous_status": row.previous_status,
        "new_status": row.new_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/audit-logs", response_model=List[dict])
async def list_audit_logs(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    _: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """View authorized audit logs (admin only)."""
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        q = q.filter(AuditLog.entity_id == entity_id)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action == action)
    rows = (
        q.order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_serialize_audit(r) for r in rows]


@router.get("/remarks", response_model=List[dict])
async def list_remarks(
    travel_id: Optional[int] = Query(None),
    document_id: Optional[int] = Query(None),
    admin_id: Optional[int] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    _: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """View structured compliance notes / status-transition history (admin only)."""
    q = db.query(RemarkHistory)
    if travel_id is not None:
        q = q.filter(RemarkHistory.travel_id == travel_id)
    if document_id is not None:
        q = q.filter(RemarkHistory.document_id == document_id)
    if admin_id is not None:
        q = q.filter(RemarkHistory.admin_id == admin_id)
    rows = (
        q.order_by(RemarkHistory.created_at.desc(), RemarkHistory.remark_id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_serialize_remark(r) for r in rows]


@router.get("/remarks/mine", response_model=List[dict])
async def list_my_remarks(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Faculty: structured remarks on travels the current user owns (FR-F09)."""
    owned = db.query(Travel.travel_id).filter(
        Travel.user_id == current_user.user_id).subquery()
    rows = (
        db.query(RemarkHistory)
        .filter(RemarkHistory.travel_id.in_(owned))
        .order_by(RemarkHistory.created_at.desc(), RemarkHistory.remark_id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_serialize_remark(r) for r in rows]
