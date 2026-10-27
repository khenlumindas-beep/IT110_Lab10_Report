"""
Phase 7/8 — AI Document Services + AI Monitoring (heuristics + rules only; no LLM).

Phase 7: FR-AI01 classification, FR-AI02 extraction, FR-AI03 issue detection.
Phase 8: FR-AI04 compliance insight, FR-AI05 priority recommendation,
         FR-AI06 suggested remarks.
Final decisions remain with admin personnel.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ai_engine import run_and_persist
from ai_monitor import build_remark, refresh_insights, insight_dict
from database import get_db
from models import AIDocumentAnalysis, AIComplianceInsight, Document, Travel
from security import TokenData, get_current_admin, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])


def _analysis_dict(row: AIDocumentAnalysis) -> dict:
    return {
        "analysis_id": row.analysis_id,
        "document_id": row.document_id,
        "suggested_type": row.suggested_type,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "extracted_text": row.extracted_text,
        "issues": row.issues,
        "issue_flags": row.issue_flags,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _authorize_document(db: Session, document: Document, user: TokenData) -> None:
    travel = db.query(Travel).filter(Travel.travel_id == document.travel_id).first()
    if not travel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Travel not found")
    if travel.user_id != user.user_id and user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized to analyze this document")


@router.post("/document-analysis")
async def analyze_document(
    payload: dict,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run (re-run) heuristic analysis for a document. Body: {"document_id": int}."""
    document_id = payload.get("document_id")
    if not isinstance(document_id, int):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="document_id (int) is required")
    document = db.query(Document).filter(Document.document_id == document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _authorize_document(db, document, current_user)

    row = run_and_persist(db, document)
    if row is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Document analysis failed")
    logger.info(f"AI analysis {row.analysis_id} run by user {current_user.user_id}")
    return _analysis_dict(row)


@router.get("/document-analysis/{document_id}")
async def get_document_analysis(
    document_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest analysis for a document; runs one on first access if none exists."""
    document = db.query(Document).filter(Document.document_id == document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _authorize_document(db, document, current_user)

    row = (db.query(AIDocumentAnalysis)
           .filter(AIDocumentAnalysis.document_id == document_id)
           .order_by(AIDocumentAnalysis.analysis_id.desc())
           .first())
    if row is None:
        row = run_and_persist(db, document)
    if row is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Document analysis failed")
    return _analysis_dict(row)


# ==================== Phase 8: AI Monitoring ====================

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2, None: 3}


@router.get("/insights")
async def list_insights(
    limit: int = Query(100, ge=1, le=200),
    priority: str = Query(None, pattern="^(low|medium|high)$"),
    travel_id: int = Query(None),
    _: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """FR-A14/FR-AI04: compliance insights and priority recommendations (admin)."""
    q = db.query(AIComplianceInsight, Travel).outerjoin(
        Travel, AIComplianceInsight.travel_id == Travel.travel_id)
    if priority:
        q = q.filter(AIComplianceInsight.priority == priority)
    if travel_id is not None:
        q = q.filter(AIComplianceInsight.travel_id == travel_id)
    rows = q.order_by(AIComplianceInsight.insight_id.desc()).limit(limit).all()
    out = [insight_dict(r, t) for r, t in rows]
    out.sort(key=lambda d: (_PRIORITY_RANK.get(d["priority"], 3), d["created_at"] or ""),
             reverse=False)
    return out


@router.post("/insights/recompute")
async def recompute_insights(
    payload: dict = None,
    _: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Regenerate insights for one travel ({"travel_id": n}) or all active travels."""
    travel_id = (payload or {}).get("travel_id")
    if travel_id is not None and not isinstance(travel_id, int):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="travel_id must be an int")
    try:
        written = refresh_insights(db, travel_id=travel_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    logger.info(f"AI insights recomputed by admin: {written} row(s)")
    return {"written": written, "travel_id": travel_id}


@router.post("/insights/{insight_id}/accept")
async def accept_insight(
    insight_id: int,
    payload: dict = None,
    _: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """FR-AI06 flow: admin accepts/acknowledges an insight (is_accepted)."""
    row = db.query(AIComplianceInsight).filter(
        AIComplianceInsight.insight_id == insight_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Insight not found")
    accepted = bool((payload or {}).get("accepted", True))
    row.is_accepted = accepted
    db.commit()
    db.refresh(row)
    travel = db.query(Travel).filter(Travel.travel_id == row.travel_id).first()
    return insight_dict(row, travel)


@router.post("/suggest-remark")
async def suggest_remark(
    payload: dict,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    FR-AI06: structured remark suggestion for a travel (or the travel of a
    document). Body: {"travel_id": int} or {"document_id": int}.
    Advisory only — nothing is applied to the record.
    """
    travel_id = payload.get("travel_id")
    document_id = payload.get("document_id")
    if document_id is not None and travel_id is None:
        if not isinstance(document_id, int):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="document_id must be an int")
        document = db.query(Document).filter(Document.document_id == document_id).first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Document not found")
        travel_id = document.travel_id
    if not isinstance(travel_id, int):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="travel_id or document_id (int) is required")
    travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
    if not travel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Travel not found")
    if travel.user_id != current_user.user_id and current_user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized for this travel")

    result = build_remark(db, travel)
    # Persist the suggestion as an insight row (advisory, unaccepted).
    row = AIComplianceInsight(
        travel_id=travel.travel_id,
        insight_type="suggested_remark",
        summary=f"Suggested remark for {travel.event_title or travel.travel_id}",
        priority=result["priority"],
        suggested_remark=result["remark"],
        is_accepted=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(f"Suggested remark generated for travel {travel.travel_id} "
                f"by user {current_user.user_id}")
    return {
        "insight_id": row.insight_id,
        "travel_id": travel.travel_id,
        "remark": result["remark"],
        "priority": result["priority"],
        "issues": result["issues"],
        "is_accepted": False,
    }
