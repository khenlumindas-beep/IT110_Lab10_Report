"""
Phase 8 — AI Monitoring (heuristics + rules only; no LLM per project decision).

FR-AI04 compliance insight: summarize known compliance issues using actual data.
FR-AI05 priority recommendation: identify records that may require follow-up now.
FR-AI06 suggested remark: structured compliance remark derived from detected issues.

Reads the deterministic compliance engine (compliance.py) plus document,
post-travel and re-entry state, and persists results to ai_compliance_insights.
Final decisions remain with authorized personnel.
"""
import logging
from datetime import date

from sqlalchemy.orm import Session

from compliance import (
    compute_compliance, travel_limit_exceeded,
    _BLOCKING_DOC_STATUSES, _UNVERIFIED_DOC_STATUSES,
    _OPEN_POST_TRAVEL, _OPEN_REENTRY,
)
from models import (
    AIComplianceInsight, Document, PostTravelRequirement, ReentryActivity, Travel,
)

logger = logging.getLogger(__name__)


def _travel_label(db: Session, travel: Travel) -> str:
    return travel.event_title or f"Travel #{travel.travel_id}"


def _blocking_docs(db: Session, travel_id: int):
    return [d for d in db.query(Document).filter(Document.travel_id == travel_id).all()
            if d.status in _BLOCKING_DOC_STATUSES]


def _pending_docs(db: Session, travel_id: int):
    return [d for d in db.query(Document).filter(Document.travel_id == travel_id).all()
            if d.status in _UNVERIFIED_DOC_STATUSES]


def _overdue_post_travel(db: Session, travel_id: int):
    today = date.today()
    return [r for r in db.query(PostTravelRequirement)
            .filter(PostTravelRequirement.travel_id == travel_id).all()
            if r.status in _OPEN_POST_TRAVEL and r.due_date and r.due_date < today]


def _overdue_reentry(db: Session, travel_id: int):
    today = date.today()
    return [a for a in db.query(ReentryActivity)
            .filter(ReentryActivity.travel_id == travel_id).all()
            if a.status in _OPEN_REENTRY and a.target_date and a.target_date < today]


def build_remark(db: Session, travel: Travel) -> dict:
    """
    FR-AI06: derive one structured remark from the travel's actual issues.
    Returns {'remark': str|None, 'priority': 'low'|'medium'|'high', 'issues': [str]}.
    """
    comp = compute_compliance(db, travel.travel_id)
    issues = []

    blocking = _blocking_docs(db, travel.travel_id)
    pending = _pending_docs(db, travel.travel_id)
    open_post = [r for r in db.query(PostTravelRequirement)
                 .filter(PostTravelRequirement.travel_id == travel.travel_id).all()
                 if r.status in _OPEN_POST_TRAVEL]
    open_re = [a for a in db.query(ReentryActivity)
               .filter(ReentryActivity.travel_id == travel.travel_id).all()
               if a.status in _OPEN_REENTRY]
    overdue_post = _overdue_post_travel(db, travel.travel_id)
    overdue_re = _overdue_reentry(db, travel.travel_id)
    limit = travel_limit_exceeded(db, travel.user_id)

    if blocking:
        names = ', '.join(d.doc_type for d in blocking[:4])
        issues.append(f"Rejected/returned pre-travel document(s): {names}")
    if pending and not blocking:
        n = len(pending)
        issues.append(f"{n} pre-travel document(s) still awaiting verification")
    if not comp['pre_travel_ok'] and not blocking and not pending:
        issues.append("Required pre-travel documents are missing or unverified")
    if overdue_post:
        names = ', '.join(r.requirement for r in overdue_post[:3])
        issues.append(f"Post-travel requirement(s) overdue: {names}")
    elif open_post:
        n = len(open_post)
        issues.append(f"{n} post-travel requirement(s) not yet verified")
    if overdue_re:
        names = ', '.join(a.activity[:40] for a in overdue_re[:3])
        issues.append(f"Re-entry activity overdue: {names}")
    elif open_re:
        n = len(open_re)
        issues.append(f"{n} re-entry activit(ies) still open")
    if limit['exceeded']:
        issues.append(
            f"Faculty exceeded the {limit['limit']}-travel annual limit "
            f"({limit['travel_count']} travels in {limit['year']}) — BR-04")

    priority = comp['priority']
    if overdue_post or overdue_re or limit['exceeded']:
        priority = 'high'

    if not issues:
        return {'remark': None, 'priority': 'low', 'issues': []}

    label = _travel_label(db, travel)
    remark = (f"[AI suggested] {label}: {comp['status']} ({comp['score']}%) — "
              + '; '.join(issues)
              + ". Please address the flagged items and resubmit as needed.")
    return {'remark': remark, 'priority': priority, 'issues': issues}


def build_insights(db: Session, travel: Travel) -> list:
    """
    FR-AI04 + FR-AI05: produce insight rows (dicts) for one travel.
    Types: 'compliance_summary' (always), 'priority' (when not low),
    'document_issue' (when blocking/pending docs exist).
    """
    comp = compute_compliance(db, travel.travel_id)
    label = _travel_label(db, travel)
    remark = build_remark(db, travel)
    out = []

    summary = (
        f"{label}: {comp['status']} — {comp['verified_docs']}/{comp['required_docs']} "
        f"required documents verified ({comp['score']}%); "
        f"pre-travel {'ok' if comp['pre_travel_ok'] else 'not ok'}, "
        f"post-travel {'ok' if comp['post_travel_ok'] else 'not ok'}, "
        f"re-entry {'ok' if comp['reentry_ok'] else 'not ok'}.")
    out.append({
        'insight_type': 'compliance_summary',
        'summary': summary,
        'priority': comp['priority'],
        'suggested_remark': remark['remark'],
    })

    if comp['priority'] != 'low':
        top = remark['issues'][0] if remark['issues'] else 'compliance gaps remain'
        out.append({
            'insight_type': 'priority',
            'summary': (f"Follow-up recommended ({comp['priority']}): {label} — {top}"
                        + (f" (+{len(remark['issues']) - 1} more issue(s))"
                           if len(remark['issues']) > 1 else '')),
            'priority': comp['priority'],
            'suggested_remark': remark['remark'],
        })

    blocking = _blocking_docs(db, travel.travel_id)
    if blocking:
        names = ', '.join(d.doc_type for d in blocking[:5])
        out.append({
            'insight_type': 'document_issue',
            'summary': f"{label}: document issue — {names} rejected/returned; resubmission required.",
            'priority': 'high',
            'suggested_remark': remark['remark'],
        })
    return out


def refresh_insights(db: Session, travel_id: int = None) -> int:
    """
    Regenerate insight rows. Un-accepted auto insights for the travel are
    replaced (accepted ones are kept as history). Returns rows written.
    """
    q = db.query(Travel)
    if travel_id is not None:
        q = q.filter(Travel.travel_id == travel_id)
        travels = q.all()
        if not travels:
            raise ValueError(f"Travel {travel_id} not found")
    else:
        travels = q.filter(Travel.workflow_status != 'Cancelled').all()

    written = 0
    for travel in travels:
        # Drop stale un-accepted insights for this travel.
        db.query(AIComplianceInsight).filter(
            AIComplianceInsight.travel_id == travel.travel_id,
            AIComplianceInsight.is_accepted.isnot(True),
        ).delete(synchronize_session=False)
        for ins in build_insights(db, travel):
            db.add(AIComplianceInsight(
                travel_id=travel.travel_id,
                insight_type=ins['insight_type'],
                summary=ins['summary'],
                priority=ins['priority'],
                suggested_remark=ins['suggested_remark'],
            ))
            written += 1
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info(f"AI insights refreshed for {len(travels)} travel(s): {written} row(s)")
    return written


def insight_dict(row: AIComplianceInsight, travel: Travel = None) -> dict:
    return {
        'insight_id': row.insight_id,
        'travel_id': row.travel_id,
        'event_title': (travel.event_title if travel else None),
        'insight_type': row.insight_type,
        'summary': row.summary,
        'priority': row.priority,
        'suggested_remark': row.suggested_remark,
        'is_accepted': row.is_accepted,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }
