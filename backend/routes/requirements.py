"""
Requirement Checklists Routes
Official OIGE requirement lists (Faculty Pre/Post, Student Post) with
per-travel completeness tracking and downloadable templates.

Documents are matched to requirements by exact doc_type name — items seeded
by migration_011 share names with the document_types catalog, so every upload
from either the Documents tab or the Requirements checklist counts.
"""
import csv
import io
import mimetypes
import os
from collections import Counter
from datetime import datetime
from html import escape as html_escape

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ai_engine import analyze as ai_analyze
from database import get_db
from models import Document, DocumentType, RequirementItem, Travel, User
from schemas import (
    RequirementItemResponse,
    RequirementTravelItem,
    RequirementTravelStatus,
)
from security import (
    get_current_user,
    get_current_user_header_or_query,
    TokenData,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/requirements", tags=["requirements"])

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "requirement_templates")

TEMPLATE_FILES = {
    "faculty_pre_checklist": "faculty_pre_foreign_travel_checklist.pdf",
    "faculty_post_checklist": "faculty_post_foreign_travel_checklist.pdf",
    "student_post_checklist": "student_post_foreign_travel_checklist.pdf",
    "reentry_plan": "csu_reentry_action_plan_template.pdf",
}

# Which checklist PDFs apply per participant type (for the master payload).
CHECKLIST_KEYS = {
    "Faculty": ["faculty_pre_checklist", "faculty_post_checklist"],
    "Student": ["student_post_checklist"],
}


def _match_documents(db: Session, travel_id: int) -> dict:
    """Latest uploaded document per lowercased doc_type name for a travel."""
    rows = (
        db.query(Document)
        .filter(Document.travel_id == travel_id)
        .order_by(Document.uploaded_at.desc(), Document.document_id.desc())
        .all()
    )
    latest = {}
    for d in rows:
        key = (d.doc_type or "").strip().lower()
        if key and key not in latest:
            latest[key] = d
    return latest


def _item_status(doc) -> str:
    if doc is None:
        return "Not Submitted"
    return doc.status or "Submitted"


@router.get("/", response_model=list[RequirementItemResponse])
async def list_requirement_items(
    applies_to: str = None,
    phase: str = None,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Master requirement checklist list (optionally filtered)."""
    try:
        q = db.query(RequirementItem)
        if applies_to:
            q = q.filter(RequirementItem.applies_to == applies_to)
        if phase:
            q = q.filter(RequirementItem.phase == phase)
        items = q.order_by(
            RequirementItem.applies_to,
            RequirementItem.phase,
            RequirementItem.sort_order,
        ).all()
        return items
    except Exception as e:
        logger.error(f"Error listing requirement items: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred",
        )


@router.get("/checklist-files", response_model=dict)
async def checklist_files(
    current_user: TokenData = Depends(get_current_user),
):
    """Downloadable checklist / template PDF keys available to this user."""
    return {"templates": TEMPLATE_FILES, "by_participant": CHECKLIST_KEYS}


@router.get("/templates/{template_key}")
async def download_template(
    template_key: str,
    current_user: TokenData = Depends(get_current_user_header_or_query),
):
    """Download an official checklist or the Re-Entry Action Plan template (PDF)."""
    filename = TEMPLATE_FILES.get(template_key)
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    path = os.path.join(TEMPLATE_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template file missing on server",
        )
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/travel/{travel_id}", response_model=RequirementTravelStatus)
async def travel_requirements(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Requirement checklist for one travel, with per-item document status
    and a completeness summary (owner or admin)."""
    travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
    if not travel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Travel not found",
        )
    if travel.user_id != current_user.user_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this travel's requirements",
        )

    participant = travel.participant_type or "Faculty"
    items = (
        db.query(RequirementItem)
        .filter(RequirementItem.applies_to == participant)
        .order_by(
            RequirementItem.phase,
            RequirementItem.sort_order,
        )
        .all()
    )
    docs = _match_documents(db, travel_id)

    out = []
    for it in items:
        doc = docs.get(it.name.strip().lower())
        out.append(RequirementTravelItem(
            requirement_id=it.requirement_id,
            name=it.name,
            phase=it.phase,
            parent_id=it.parent_id,
            is_required=it.is_required,
            condition_text=it.condition_text,
            display_text=it.display_text,
            has_template=it.has_template,
            template_key=it.template_key,
            sort_order=it.sort_order,
            status=_item_status(doc),
            document_id=doc.document_id if doc else None,
            file_name=doc.file_name if doc else None,
        ))

    required = [i for i in out if i.is_required and i.parent_id is None]
    required_total = len(required)
    verified = len([i for i in required if i.status == "Verified"])
    percent = round(verified * 100 / required_total, 1) if required_total else 100.0

    return RequirementTravelStatus(
        travel_id=travel_id,
        participant_type=participant,
        items=out,
        required_total=required_total,
        verified_required=verified,
        percent=percent,
        complete=(verified == required_total),
        checklist_files=CHECKLIST_KEYS.get(participant, []),
    )


# ==================== AI Requirements Check (heuristics, no OCR/LLM) ====================

# File-level red flags that mean "this submission probably needs a human look".
_HARD_ISSUE_FLAGS = {
    "placeholder_file",
    "unsupported_extension",
    "executable_upload",
    "missing_extension",
    "possibly_unsigned",
    "type_mismatch",  # filename strongly suggests a DIFFERENT document
}


@router.get("/ai-check/{travel_id}")
async def ai_check_travel(
    travel_id: int,
    phase: str = "Post-Travel",
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Heuristic AI check of one travel's requirements (Pre- or Post-Travel):
    is the checklist COMPLETE, and do submitted files LOOK CORRECT?

    Signals only (file name, extension, size, declared category, phase) —
    no OCR / no LLM, per system constraint. Owner or admin.
    """
    if phase not in ("Pre-Travel", "Post-Travel"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="phase must be Pre-Travel or Post-Travel",
        )
    travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
    if not travel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Travel not found",
        )
    if travel.user_id != current_user.user_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to check this travel's requirements",
        )

    participant = travel.participant_type or "Faculty"
    items = (
        db.query(RequirementItem)
        .filter(
            RequirementItem.applies_to == participant,
            RequirementItem.phase == phase,
            RequirementItem.parent_id.is_(None),
        )
        .order_by(RequirementItem.sort_order)
        .all()
    )

    # Latest document per declared doc_type for this travel (one query).
    docs_by_type: dict = {}
    docs = (
        db.query(Document)
        .filter(Document.travel_id == travel_id)
        .order_by(Document.uploaded_at.desc(), Document.document_id.desc())
        .all()
    )
    for d in docs:
        key = (d.doc_type or "").strip().lower()
        if key and key not in docs_by_type:
            docs_by_type[key] = d

    known_types = sorted(
        {n for (n,) in db.query(DocumentType.name).all()}
        | {i.name for i in items}
    )

    out = []
    for it in items:
        doc = docs_by_type.get(it.name.strip().lower())
        label = it.display_text or it.name
        entry = {
            "requirement_id": it.requirement_id,
            "name": it.name,
            "display_text": label,
            "is_required": bool(it.is_required),
            "document_id": doc.document_id if doc else None,
            "file_name": doc.file_name if doc else None,
            "doc_status": doc.status if doc else None,
            "verdict": None,
            "reasons": [],   # hard problems (drive "needs review" / missing)
            "notes": [],     # soft observations
            "confidence": None,
        }
        if doc is None:
            entry["verdict"] = "missing" if it.is_required else "optional_missing"
            if it.is_required:
                entry["reasons"].append("Not submitted yet.")
        elif (doc.status or "") == "Verified":
            entry["verdict"] = "verified"
            entry["reasons"].append("Submitted and verified by OIGE.")
        elif (doc.status or "") in ("Rejected", "Resubmission Required"):
            entry["verdict"] = "rejected"
            entry["reasons"].append(
                doc.remarks or "Rejected by OIGE — resubmission required."
            )
        else:
            res = ai_analyze(
                doc.file_name or "",
                int(doc.file_size or 0),
                doc.doc_type or "",
                known_types,
            )
            entry["confidence"] = res.get("confidence")
            # ai_engine.analyze emits issue_flags and issues in the same order.
            flag_list = list(
                filter(None, (res.get("issue_flags") or "").split(","))
            )
            msgs = list(filter(None, (res.get("issues") or "").split(" | ")))
            pairs = list(zip(flag_list, msgs))
            entry["reasons"] = [
                m for f, m in pairs if f in _HARD_ISSUE_FLAGS
            ]
            entry["notes"] = [
                m for f, m in pairs if f not in _HARD_ISSUE_FLAGS
            ]
            if doc.doc_category and doc.doc_category != phase:
                entry["reasons"].append(
                    f'Uploaded under "{doc.doc_category}" category instead of "{phase}".'
                )
            entry["verdict"] = "needs_review" if entry["reasons"] else "ai_ok"
            if entry["verdict"] == "ai_ok":
                entry["notes"].append(
                    "File signals match this requirement (no issues found)."
                )
        out.append(entry)

    counts = Counter(e["verdict"] for e in out)
    required_total = len([e for e in out if e["is_required"]])
    passed = counts.get("verified", 0) + counts.get("ai_ok", 0)
    open_required = counts.get("missing", 0) + counts.get("rejected", 0)
    percent = (
        round(passed * 100 / required_total, 1) if required_total else 100.0
    )
    if open_required:
        verdict = "INCOMPLETE"
    elif counts.get("needs_review", 0):
        verdict = "NEEDS REVIEW"
    else:
        verdict = "COMPLETE"

    return {
        "travel_id": travel_id,
        "participant_type": participant,
        "phase": phase,
        "summary": {
            "required_total": required_total,
            "verified": counts.get("verified", 0),
            "ai_ok": counts.get("ai_ok", 0),
            "needs_review": counts.get("needs_review", 0),
            "missing": counts.get("missing", 0),
            "rejected": counts.get("rejected", 0),
            "optional_missing": counts.get("optional_missing", 0),
            "passed": passed,
            "percent": percent,
            "verdict": verdict,
        },
        "items": out,
    }


# ==================== Requirements Compliance Report (admin) ====================

def _phase_report(db: Session, applies_to: str, phase: str,
                  user_id: int | None = None) -> dict:
    """Per-travel completion of one checklist (participant type x phase).

    user_id=None → admin/system-wide; otherwise rows are scoped to that owner.
    """
    q = (
        db.query(Travel)
        .options(joinedload(Travel.user).joinedload(User.college))
        .filter(Travel.participant_type == applies_to)
    )
    if user_id is not None:
        q = q.filter(Travel.user_id == user_id)
    travels = q.order_by(Travel.start_date.desc(), Travel.travel_id.desc()).all()
    required_items = (
        db.query(RequirementItem)
        .filter(
            RequirementItem.applies_to == applies_to,
            RequirementItem.phase == phase,
            RequirementItem.is_required.is_(True),
            RequirementItem.parent_id.is_(None),
        )
        .order_by(RequirementItem.sort_order)
        .all()
    )

    # Latest document per (travel, lowercased doc_type) in one query.
    latest: dict = {}
    tids = [t.travel_id for t in travels]
    if tids:
        docs = (
            db.query(Document)
            .filter(Document.travel_id.in_(tids))
            .order_by(Document.uploaded_at.desc(), Document.document_id.desc())
            .all()
        )
        for d in docs:
            key = (d.travel_id, (d.doc_type or "").strip().lower())
            if key[1] and key not in latest:
                latest[key] = d

    rows = []
    for t in travels:
        user = t.user
        if applies_to == "Student" and t.participant_name:
            owner = t.participant_name
        else:
            owner = user.full_name if user else f"User #{t.user_id}"
        college = user.college.name if user is not None and user.college else None
        verified = 0
        missing = []
        for it in required_items:
            doc = latest.get((t.travel_id, it.name.strip().lower()))
            if doc is not None and (doc.status or "") == "Verified":
                verified += 1
            else:
                missing.append(it.display_text or it.name)
        total = len(required_items)
        pct = round(verified * 100 / total, 1) if total else 100.0
        rows.append({
            "travel_id": t.travel_id,
            "event_title": t.event_title,
            "faculty_name": owner,
            "college": college,
            "start_date": t.start_date.isoformat() if t.start_date else None,
            "workflow_status": t.workflow_status,
            "required_total": total,
            "verified_required": verified,
            "percent": pct,
            "complete": verified == total,
            "missing": missing,
        })

    complete = len([r for r in rows if r["complete"]])
    not_started = len([r for r in rows if r["verified_required"] == 0])
    avg = round(sum(r["percent"] for r in rows) / len(rows), 1) if rows else 100.0
    return {
        "applies_to": applies_to,
        "phase": phase,
        "summary": {
            "total": len(rows),
            "complete": complete,
            "incomplete": len(rows) - complete,
            "not_started": not_started,
            "in_progress": len(rows) - complete - not_started,
            "avg_percent": avg,
        },
        "rows": rows,
    }


@router.get("/report")
async def requirements_report(
    applies_to: str = "Faculty",
    phase: str = "Post-Travel",
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Requirements compliance report: per-travel completion of a checklist.

    Admin sees every travel; faculty/students see only their own rows.
    """
    if applies_to not in ("Faculty", "Student") or phase not in ("Pre-Travel", "Post-Travel"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="applies_to must be Faculty/Student; phase Pre/Post-Travel",
        )
    scope = None if current_user.role == "super_admin" else current_user.user_id
    return _phase_report(db, applies_to, phase, user_id=scope)


_REPORT_TITLES = {
    ("Faculty", "Post-Travel"): "Faculty Post-Travel Requirements Compliance Report",
    ("Faculty", "Pre-Travel"): "Faculty Pre-Travel Requirements Compliance Report",
    ("Student", "Post-Travel"): "Student Post-Travel Requirements Compliance Report",
}


@router.get("/report/export")
async def requirements_report_export(
    format: str = "csv",
    applies_to: str = "Faculty",
    phase: str = "Post-Travel",
    current_user: TokenData = Depends(get_current_user_header_or_query),
    db: Session = Depends(get_db),
):
    """Export the compliance report as CSV (Excel-ready) or a printable HTML page.

    Admin exports system-wide; faculty/students export their own travels only.
    """
    if applies_to not in ("Faculty", "Student") or phase not in ("Pre-Travel", "Post-Travel"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid applies_to or phase",
        )
    scope = None if current_user.role == "super_admin" else current_user.user_id
    report = _phase_report(db, applies_to, phase, user_id=scope)
    rows = report["rows"]
    s = report["summary"]
    title = _REPORT_TITLES.get((applies_to, phase),
                               f"{applies_to} {phase} Requirements Compliance Report")
    base_name = f"{applies_to.lower()}_{phase.lower().replace('-', '_')}_requirements_report"

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Faculty/Participant", "College", "Travel/Event", "Start Date",
            "Workflow Status", "Required", "Verified", "% Complete",
            "Status", "Missing Requirements",
        ])
        for r in rows:
            writer.writerow([
                r["faculty_name"], r["college"] or "", r["event_title"],
                r["start_date"] or "", r["workflow_status"] or "",
                r["required_total"], r["verified_required"], r["percent"],
                "Complete" if r["complete"] else "Incomplete",
                "; ".join(r["missing"]),
            ])
        # BOM so Excel opens UTF-8 names correctly.
        content = "\ufeff" + buf.getvalue()
        return Response(
            content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{base_name}.csv"'
            },
        )

    if format == "html":
        stat = lambda v, c: (  # noqa: E731
            f'<span class="box" style="border-color:{c}">'
            f'<small>{v[0]}</small><b style="color:{c}">{v[1]}</b></span>')
        body_rows = []
        for i, r in enumerate(rows, 1):
            missing = "<br>".join(html_escape(m) for m in r["missing"]) or "—"
            body_rows.append(
                f"<tr><td>{i}</td><td>{html_escape(r['faculty_name'])}</td>"
                f"<td>{html_escape(r['college'] or '—')}</td>"
                f"<td>{html_escape(r['event_title'])}</td>"
                f"<td>{r['start_date'] or '—'}</td>"
                f"<td class='num'>{r['verified_required']}/{r['required_total']}</td>"
                f"<td class='num'>{r['percent']}%</td>"
                f"<td>{'Complete' if r['complete'] else 'Incomplete'}</td>"
                f"<td class='missing'>{missing}</td></tr>"
            )
        page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html_escape(title)}</title>
<style>
 body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 26px; color: #0f172a; }}
 h1 {{ font-size: 18px; color: #0d8353; margin: 0 0 2px; }}
 .sub {{ color: #64748b; font-size: 12px; margin-bottom: 14px; }}
 .boxes {{ margin-bottom: 14px; }}
 .box {{ display: inline-block; border: 1px solid #bbf7d0; background: #f3faf6;
         border-radius: 8px; padding: 7px 14px; margin: 0 8px 8px 0; text-align: center; }}
 .box small {{ display: block; color: #64748b; font-size: 11px; }}
 .box b {{ font-size: 18px; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
 th, td {{ border: 1px solid #d8e5dc; padding: 6px 8px; text-align: left;
           vertical-align: top; }}
 th {{ background: #f0f7f3; color: #0f5132; }}
 td.num {{ text-align: center; white-space: nowrap; }}
 td.missing {{ color: #b91c1c; font-size: 11px; }}
 .done {{ color: #059669; font-weight: 600; }}
 button {{ background: #0d8353; color: #fff; border: 0; border-radius: 8px;
           padding: 9px 16px; font-size: 13px; cursor: pointer; margin-bottom: 14px; }}
 @media print {{ button {{ display: none; }} body {{ margin: 10mm; }} }}
</style></head><body>
<button onclick="window.print()">&#128424; Print / Save as PDF</button>
<h1>{html_escape(title)}</h1>
<div class="sub">Office of Internationalization and Global Engagement (OIGE)
 &middot; SmartTrack &middot; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<div class="boxes">
 {stat(('Total Travels', s['total']), '#2563eb')}
 {stat(('Complete', s['complete']), '#059669')}
 {stat(('Incomplete', s['incomplete']), '#dc2626')}
 {stat(('Not Started', s['not_started']), '#94a3b8')}
 {stat(('Average Complete', f"{s['avg_percent']}%"), '#f59e0b')}
</div>
<table>
<thead><tr><th>#</th><th>Faculty/Participant</th><th>College</th>
<th>Travel/Event</th><th>Start Date</th><th>Verified</th><th>%</th>
<th>Status</th><th>Missing Requirements</th></tr></thead>
<tbody>{''.join(body_rows) if body_rows else '<tr><td colspan="9">No travel records.</td></tr>'}</tbody>
</table>
</body></html>"""
        return Response(page, media_type="text/html; charset=utf-8")

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="format must be csv or html",
    )
