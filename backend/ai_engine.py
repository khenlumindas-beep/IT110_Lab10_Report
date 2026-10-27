"""
Phase 7 — AI Document Services (heuristics + rules only; no OCR/LLM per project decision).

Implements FR-AI01 (classification suggestion), FR-AI02 (metadata/field extraction
from filename + file attributes where possible), FR-AI03 (potential issue detection).
Deterministic, explainable rules; final decisions remain with admin personnel.
"""
import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Keyword lexicon: doc-type name token -> filename/declared-type signal words.
# Keys are normalized (lowercase, no spaces). Values are signals that suggest the type.
_TYPE_SIGNALS = {
    "invitation_letter": ["invitation", "invite", "letter", "invit"],
    "travel_authority": ["authority", "travel_order", "travelorder", "permit", "approval", "endorsed"],
    "passport_copy": ["passport", "pp_copy", "bio", "e passport"],
    "proof_of_funding": ["funding", "financial", "budget", "allowance", "sponsor", "grant", "costing"],
    "program_conference_information": ["program", "conference", "agenda", "itinerary", "brochure", "schedule", "abstract"],
    "certificate_of_participation": ["certificate", "cert", "participation", "attendance_cert"],
    "travel_report": ["travel_report", "travelreport", "report", "final_report", "trip_report"],
    "proof_of_attendance": ["attendance", "attend", "sign_in", "signin", "roster", "participant_list"],
    "reentry_activity_report": ["reentry", "re_entry", "re-entry", "activity_report", "dissemination"],
    "reentry_evidence": ["evidence", "mov", "photo", "photos", "proof", "minutes", "presentation"],
    "certificate_of_employment": ["employment", "coe", "appointment"],
    "endorsement": ["endorsement", "endorsed", "recommendation"],
}

_STOPWORDS = {"the", "a", "an", "of", "for", "and", "to", "in", "on", "doc", "file", "final", "copy", "new"}

_SUSPICIOUS_NAME_PATTERNS = [
    (r"(^|[^a-z0-9])(img|screenshot|screen_shot|untitled|scan|pxl|photo)([_\-]?\d{2,})?\b",
     "filename_generic", "Filename looks generic (scanner/camera default) — consider renaming descriptively."),
    (r"(final|final_?\d+)_?final", "filename_iterative", "Iterative 'final' filename suggests unclear versioning."),
    (r"(^|[^a-z0-9])copy_?\d+", "filename_duplicate_copy", "Filename indicates a duplicate copy."),
    (r"[_ ]{2,}", "filename_messy", "Filename contains repeated separators."),
]

_KNOWN_BAD_EXTENSIONS = {"exe", "bat", "cmd", "js", "html", "zip", "rar", "7z"}
_ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "doc", "docx"}

_DATE_RE = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]?([0-5]\d)\b")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_ACRO_RE = re.compile(r"\b[A-Z]{3,6}\b")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t and t not in _STOPWORDS]


def _extension(file_name: str) -> str:
    if "." not in (file_name or ""):
        return ""
    return file_name.rsplit(".", 1)[-1].lower()


def _score_type(name_norm: str, signals: List[str], hay_tokens: set, hay_raw: str) -> float:
    """Score how well the haystack (filename + declared type) supports a doc type."""
    name_tokens = [t for t in name_norm.split("_") if t and t not in _STOPWORDS]
    # Direct name-token hits in filename are strongest signals.
    hits = sum(1 for t in name_tokens if t in hay_tokens)
    score = hits / max(len(name_tokens), 1) * 0.7
    # Lexicon signal-word hits.
    sig_hits = sum(1 for s in signals if s in hay_raw or s in hay_tokens)
    score += min(sig_hits, 3) * 0.1
    # Whole declared-type string equality bonus handled by caller.
    return min(score, 0.95)


def classify(file_name: str, declared_type: str, known_types: List[str]) -> Dict:
    """FR-AI01: suggest a document type for an uploaded file."""
    name_only = _norm(file_name or "")
    name_tokens = set(_tokens(name_only))
    # Filename signals decide cross-type ranking; declared type only gets a self-bonus.
    declared_norm = _norm(declared_type)

    best_name: Optional[str] = None
    best_score = 0.0
    for type_name in known_types:
        tn = _norm(type_name)
        signals = _TYPE_SIGNALS.get(tn, [])
        score = _score_type(tn, signals, name_tokens, name_only)
        if tn == declared_norm:
            score += 0.35  # declared type self-consistency
        if score > best_score:
            best_score, best_name = score, type_name

    if best_name is None or best_score < 0.2:
        return {
            "suggested_type": declared_type,
            "confidence": 0.35,
            "flag": "low_confidence",
        }

    flag = "none"
    if _norm(best_name) != declared_norm:
        if best_score >= 0.5:
            flag = "type_mismatch"
        else:
            # Only override when clearly stronger; otherwise keep declared.
            best_name, best_score = declared_type, max(best_score, 0.4)
    if best_score < 0.5:
        flag = "low_confidence" if flag == "none" else flag
    return {"suggested_type": best_name, "confidence": round(min(best_score, 0.99), 4), "flag": flag}


def extract_fields(file_name: str, file_size: int) -> Dict:
    """FR-AI02 (heuristic): extract useful fields from file attributes/filename."""
    base = file_name or ""
    stem = base.rsplit(".", 1)[0] if "." in base else base
    fields: Dict[str, object] = {}
    m = _DATE_RE.search(stem)
    if m:
        fields["date"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    elif _YEAR_RE.search(stem):
        fields["year"] = _YEAR_RE.search(stem).group(0)
    t = _TIME_RE.search(stem)
    if t:
        fields["time"] = f"{t.group(1).zfill(2)}:{t.group(2)}"
    acros = _ACRO_RE.findall(stem)
    if acros:
        fields["acronyms"] = ",".join(sorted(set(acros))[:5])
    fields["extension"] = _extension(file_name)
    fields["size_kb"] = round(file_size / 1024, 1)
    fields["size_class"] = (
        "very_small" if file_size < 1024 else
        "small" if file_size < 50 * 1024 else
        "medium" if file_size < 5 * 1024 * 1024 else "large"
    )
    fields["word_count_est"] = max(len(_tokens(stem)), 1)
    return fields


def detect_issues(file_name: str, file_size: int, declared_type: str,
                  suggested_type: str, confidence: float, field_flag: str) -> List[Dict]:
    """FR-AI03: flag possible missing info, unreadable-scan indicators, inconsistencies."""
    issues: List[Dict] = []
    ext = _extension(file_name)

    if ext and ext not in _ALLOWED_EXTENSIONS:
        issues.append({"flag": "unsupported_extension",
                       "message": f"File extension '.{ext}' is outside the supported set (PDF/JPG/PNG)."})
    if ext in _KNOWN_BAD_EXTENSIONS:
        issues.append({"flag": "executable_upload",
                       "message": "Executable/script uploads are not permitted."})
    if not ext:
        issues.append({"flag": "missing_extension", "message": "File has no extension — readability uncertain."})
    if file_size < 1024:
        issues.append({"flag": "placeholder_file",
                       "message": "File is under 1KB — likely a placeholder or empty scan."})
    if file_size > 5 * 1024 * 1024:
        issues.append({"flag": "oversized",
                       "message": "File exceeds 5MB — consider compressing for archival quality."})
    for pattern, flag, msg in _SUSPICIOUS_NAME_PATTERNS:
        if re.search(pattern, (file_name or "").lower()):
            issues.append({"flag": flag, "message": msg})
    if field_flag == "type_mismatch":
        issues.append({"flag": "type_mismatch",
                       "message": f"Declared type '{declared_type}' differs from suggested '{suggested_type}' "
                                  f"based on filename signals."})
    if field_flag == "low_confidence" or confidence < 0.5:
        issues.append({"flag": "low_confidence",
                       "message": "Classification confidence is low — verify the document type manually."})
    # Keywords implying an unsigned/incomplete document.
    low_name = (file_name or "").lower()
    if re.search(r"(^|[^a-z0-9])(draft|unsigned|un_signed|pending_sign|no_sign)",
                 low_name):
        issues.append({"flag": "possibly_unsigned",
                       "message": "Filename suggests a draft/unsigned document."})
    return issues


def analyze(file_name: str, file_size: int, declared_type: str,
            known_types: List[str]) -> Dict:
    """Run full Phase 7 pipeline; returns a dict ready for ai_document_analysis."""
    cls = classify(file_name, declared_type, known_types)
    fields = extract_fields(file_name, file_size)
    issues = detect_issues(file_name, file_size, declared_type,
                           cls["suggested_type"], cls["confidence"], cls["flag"])
    extracted = "; ".join(f"{k}={v}" for k, v in fields.items())
    issue_flags = ",".join(i["flag"] for i in issues) if issues else ""
    issue_text = " | ".join(i["message"] for i in issues) if issues else ""
    return {
        "suggested_type": cls["suggested_type"],
        "confidence": cls["confidence"],
        "extracted_text": extracted,
        "issues": issue_text or None,
        "issue_flags": issue_flags or None,
        "status": "complete",
    }


def run_and_persist(db, document) -> Optional[object]:
    """Best-effort: analyze a Document and persist to ai_document_analysis.

    Never raises — analysis failures must not break uploads (PHASE7 best-effort).
    """
    try:
        from models import AIDocumentAnalysis, DocumentType
        known = [r.name for r in db.query(DocumentType.name).all()]
        if document.doc_type and document.doc_type not in known:
            known.append(document.doc_type)
        result = analyze(document.file_name, document.file_size or 0,
                         document.doc_type or "", known)
        row = AIDocumentAnalysis(
            document_id=document.document_id,
            suggested_type=result["suggested_type"],
            confidence=result["confidence"],
            extracted_text=result["extracted_text"],
            issues=result["issues"],
            issue_flags=result["issue_flags"],
            status=result["status"],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(f"AI analysis {row.analysis_id} for document {document.document_id}: "
                    f"{row.suggested_type} ({row.confidence})")
        return row
    except Exception as e:
        logger.error(f"AI analysis failed for document {getattr(document, 'document_id', '?')}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None
