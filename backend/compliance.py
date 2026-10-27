"""
Compliance Engine (BR-07)

Calculates compliance status from actual record, document, post-travel and
re-entry states rather than a manual checkbox. Pure computation plus a single
persist helper, so the same logic backs the on-demand recompute endpoint, the
monitoring list and the post-travel/re-entry write paths.

Statuses: 'Fully Compliant' | 'Partially Compliant' | 'Needs Action'
Priority: 'low' | 'medium' | 'high'
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy.orm import Session

from models import (
    Travel, Document, PostTravelRequirement, ReentryActivity, ComplianceRecord,
)
from audit import log_audit

# Documents still in any of these states are NOT compliant (BR-02, BR-03).
_UNVERIFIED_DOC_STATUSES = ('Submitted', 'Under Verification', 'Rejected', 'Resubmission Required')
_BLOCKING_DOC_STATUSES = ('Rejected', 'Resubmission Required')

# Post-travel requirement states that still block completion (BR-05).
_OPEN_POST_TRAVEL = ('Not Submitted', 'Submitted', 'Incomplete')
# Re-entry activity states that still block full compliance (BR-06).
_OPEN_REENTRY = ('Not Started', 'For Implementation', 'Ongoing', 'Not Complied')

# Institutional rule (BR-04): max foreign travels per faculty per calendar year.
TRAVEL_LIMIT_PER_YEAR = 3


def _travel_year(travel: Travel):
    if travel.start_date:
        return travel.start_date.year if hasattr(travel.start_date, 'year') else travel.start_date
    return None


def compute_compliance(db: Session, travel_id: int) -> dict:
    """
    Compute the compliance snapshot for a single travel without persisting.
    Returns a dict shaped like the ComplianceRecord columns.
    """
    travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
    if not travel:
        raise ValueError(f"Travel {travel_id} not found")

    # --- Pre-travel: verified documents (BR-01, BR-02) ---
    docs = db.query(Document).filter(Document.travel_id == travel_id).all()
    required_docs = len(docs)
    verified_docs = len([d for d in docs if d.status == 'Verified'])
    has_blocking = any(d.status in _BLOCKING_DOC_STATUSES for d in docs)
    has_pending = any(d.status in _UNVERIFIED_DOC_STATUSES for d in docs)
    pre_travel_ok = required_docs > 0 and verified_docs == required_docs and not has_blocking

    # --- Post-travel (BR-05): every requirement must be Verified or Waived ---
    post_reqs = db.query(PostTravelRequirement).filter(
        PostTravelRequirement.travel_id == travel_id).all()
    if post_reqs:
        open_post = [r for r in post_reqs if r.status in _OPEN_POST_TRAVEL]
        post_travel_ok = len(open_post) == 0
    else:
        # Nothing configured yet: not a blocker, but not an explicit pass either.
        post_travel_ok = travel.post_travel_status in ('Complete Documents',)

    # --- Re-entry (BR-06): every activity must be Completed ---
    activities = db.query(ReentryActivity).filter(
        ReentryActivity.travel_id == travel_id).all()
    if activities:
        open_re = [a for a in activities if a.status in _OPEN_REENTRY]
        reentry_ok = len(open_re) == 0
    else:
        reentry_ok = True

    # --- Score and status (BR-07) ---
    if required_docs == 0:
        score = Decimal('0.00')
    else:
        score = (Decimal(verified_docs) / Decimal(required_docs) * 100).quantize(Decimal('0.01'))

    if pre_travel_ok and post_travel_ok and reentry_ok:
        compliance_status = 'Fully Compliant'
    elif has_blocking or not pre_travel_ok:
        # Rejected documents or unmet required documents demand action now.
        compliance_status = 'Needs Action'
    else:
        compliance_status = 'Partially Compliant'

    # --- Priority: raise urgency for overdue or repeated problems (FR-A05, 11.2) ---
    today = date.today()
    overdue = False
    for r in post_reqs:
        if r.status in _OPEN_POST_TRAVEL and r.due_date and r.due_date < today:
            overdue = True
    for a in activities:
        if a.status in _OPEN_REENTRY and a.target_date and a.target_date < today:
            overdue = True

    if has_blocking or overdue:
        priority = 'high'
    elif compliance_status == 'Fully Compliant':
        priority = 'low'
    else:
        priority = 'medium'

    return {
        'travel_id': travel_id,
        'status': compliance_status,
        'score': score,
        'pre_travel_ok': pre_travel_ok,
        'post_travel_ok': post_travel_ok,
        'reentry_ok': reentry_ok,
        'required_docs': required_docs,
        'verified_docs': verified_docs,
        'priority': priority,
        'computed_at': datetime.utcnow(),
    }


def persist_compliance(db: Session, travel_id: int, actor_user_id: int = None) -> dict:
    """
    Recompute and upsert the compliance row for a travel, returning the result.
    Creates the row on first call, updates it thereafter. Commits on success.
    """
    data = compute_compliance(db, travel_id)
    row = db.query(ComplianceRecord).filter(
        ComplianceRecord.travel_id == travel_id).first()

    if row is None:
        row = ComplianceRecord(**data)
        db.add(row)
    else:
        for key, value in data.items():
            if key != 'travel_id':
                setattr(row, key, value)

    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise

    if actor_user_id is not None:
        log_audit(db, actor_user_id, 'travel', 'status_change', travel_id,
                  f"Compliance recomputed: {data['status']} ({data['score']}%)")

    return data


def travel_limit_exceeded(db: Session, faculty_user_id: int, year: int = None) -> dict:
    """
    BR-04: flag faculty who exceed the allowed foreign-travel frequency per year.
    Counts non-cancelled travels for the faculty user in the given calendar year.
    """
    year = year or date.today().year
    travels = db.query(Travel).filter(
        Travel.user_id == faculty_user_id,
        Travel.workflow_status != 'Cancelled',
    ).all()

    in_year = [t for t in travels if _travel_year(t) == year]
    count = len(in_year)

    return {
        'faculty_user_id': faculty_user_id,
        'year': year,
        'travel_count': count,
        'limit': TRAVEL_LIMIT_PER_YEAR,
        'exceeded': count > TRAVEL_LIMIT_PER_YEAR,
    }
