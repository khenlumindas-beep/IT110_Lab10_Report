"""
Audit & remark services (BR-10, BR-12).

Two append-only helpers used across the app:
  - log_audit():      security + administrative activity history.
  - record_remark():  structured compliance notes + status-transition history.

Both are best-effort: a failure to write is logged but never breaks the
caller's transaction, so auditing can never take down a business action.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models import AuditLog, RemarkHistory

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    user_id: int | None,
    entity_type: str,
    action: str,
    entity_id: int | None = None,
    description: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append an audit-log row. Never raises."""
    try:
        db.add(AuditLog(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.utcnow(),
        ))
        db.commit()
    except Exception:
        logger.exception("Failed to write audit log (%s/%s)", entity_type, action)
        db.rollback()


def record_remark(
    db: Session,
    travel_id: int | None,
    admin_id: int | None,
    remark_text: str | None = None,
    document_id: int | None = None,
    remark_type: str | None = None,
    action: str | None = None,
    affected_requirement: str | None = None,
    previous_status: str | None = None,
    new_status: str | None = None,
) -> None:
    """Append a structured remark / status-transition row. Never raises."""
    try:
        db.add(RemarkHistory(
            travel_id=travel_id,
            document_id=document_id,
            admin_id=admin_id,
            remark_type=remark_type,
            action=action,
            affected_requirement=affected_requirement,
            remark_text=remark_text,
            previous_status=previous_status,
            new_status=new_status,
            created_at=datetime.utcnow(),
        ))
        db.commit()
    except Exception:
        logger.exception("Failed to write remark history (travel=%s)", travel_id)
        db.rollback()
