"""
Document Management Routes
Handles document upload, verification, and management
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from models import Document, Travel, User, Notification
from schemas import DocumentResponse, DocumentCreate, DocumentRejectRequest
from security import get_current_user, get_current_admin, get_current_user_header_or_query, TokenData
from routes.notifications import create_travel_notification, create_admin_notification
from audit import log_audit, record_remark
from config import settings
import os
import mimetypes
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# ==================== FILE OPERATIONS ====================

def create_upload_directory():
    """Create upload directory if it doesn't exist"""
    if not os.path.exists(settings.UPLOAD_DIR):
        os.makedirs(settings.UPLOAD_DIR)

def save_uploaded_file(file: UploadFile, travel_id: int) -> tuple:
    """Save uploaded file and return (filename, filepath)"""
    create_upload_directory()
    
    # Create directory for travel
    travel_dir = os.path.join(settings.UPLOAD_DIR, str(travel_id))
    if not os.path.exists(travel_dir):
        os.makedirs(travel_dir)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_extension = os.path.splitext(file.filename)[1]
    filename = f"{timestamp}_{file.filename}"
    filepath = os.path.join(travel_dir, filename)
    
    # Save file
    with open(filepath, "wb") as buffer:
        buffer.write(file.file.read())
    
    return filename, filepath

def delete_uploaded_file(filepath: str):
    """Delete uploaded file"""
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            logger.info(f"File deleted: {filepath}")
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")

# ==================== CREATE ====================

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    travel_id: int = Query(...),
    doc_type: str = Query(...),
    doc_category: str = Query(None),
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a document"""
    try:
        # Validate travel exists and belongs to user
        travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
        if not travel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel not found"
            )
        
        # Check authorization
        if travel.user_id != current_user.user_id and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to upload documents for this travel"
            )
        
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )
        
        # Check file size
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum of {settings.MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB"
            )
        
        # Save file
        filename, filepath = save_uploaded_file(file, travel_id)
        
        # Create document record
        document = Document(
            travel_id=travel_id,
            doc_type=doc_type,
            doc_category=doc_category,
            file_name=filename,
            file_path=filepath,
            file_size=file_size,
            status="Submitted"
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        logger.info(f"Document uploaded: {document.document_id} for travel {travel_id}")
        record_remark(
            db, travel_id=travel_id, admin_id=current_user.user_id,
            document_id=document.document_id, remark_type='General',
            action='For Verification', affected_requirement=doc_type,
            remark_text='Document uploaded by faculty.', previous_status=None,
            new_status=document.status)
        log_audit(db, current_user.user_id, 'document', 'create',
                  document.document_id, f"Uploaded {doc_type}")

        # Phase 7: heuristic analysis (best-effort — never blocks the upload)
        try:
            from ai_engine import run_and_persist
            run_and_persist(db, document)
        except Exception as ai_err:
            logger.warning(f"AI analysis skipped for document {document.document_id}: {ai_err}")

        return document
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during file upload"
        )

# ==================== READ ====================

@router.get("/", response_model=List[DocumentResponse])
async def list_all_documents(
    status_filter: str = Query(None, alias="status"),
    limit: int = Query(200, le=500),
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """List all documents (admin only, optional status filter)"""
    try:
        q = db.query(Document)
        if status_filter:
            q = q.filter(Document.status == status_filter)
        docs = q.order_by(desc(Document.uploaded_at)).limit(limit).all()
        return docs
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document details"""
    try:
        document = db.query(Document).filter(Document.document_id == document_id).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Check authorization
        travel = document.travel
        if travel.user_id != current_user.user_id and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this document"
            )
        
        return document
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/{document_id}/file")
async def download_document_file(
    document_id: int,
    current_user: TokenData = Depends(get_current_user_header_or_query),
    db: Session = Depends(get_db)
):
    """Download the actual file of a document (owner or admin).

    Auth via Authorization header, or `?token=` query param for browser downloads.
    """
    try:
        document = db.query(Document).filter(Document.document_id == document_id).first()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        travel = document.travel
        if travel.user_id != current_user.user_id and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this document"
            )

        file_path = document.file_path
        if file_path and not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        if not file_path or not os.path.isfile(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on server"
            )

        media_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        return FileResponse(
            file_path,
            media_type=media_type,
            filename=document.file_name or os.path.basename(file_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading document file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/travel/{travel_id}", response_model=List[DocumentResponse])
async def get_travel_documents(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """Get documents for a travel"""
    try:
        # Verify travel exists and authorization
        travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
        if not travel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel not found"
            )
        
        if travel.user_id != current_user.user_id and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized"
            )
        
        documents = db.query(Document).filter(
            Document.travel_id == travel_id
        ).order_by(desc(Document.uploaded_at)).offset(skip).limit(limit).all()
        
        return documents
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving travel documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/user/all", response_model=List[DocumentResponse])
async def get_user_documents(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """Get all documents for current user"""
    try:
        documents = db.query(Document).join(Travel).filter(
            Travel.user_id == current_user.user_id
        ).order_by(desc(Document.uploaded_at)).offset(skip).limit(limit).all()
        
        return documents
    
    except Exception as e:
        logger.error(f"Error retrieving user documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== UPDATE ====================

@router.patch("/{document_id}/verify", response_model=DocumentResponse)
async def verify_document(
    document_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Verify document (admin only)"""
    try:
        document = db.query(Document).filter(Document.document_id == document_id).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        previous_status = document.status
        document.status = "Verified"
        document.verified_by = current_user.user_id
        document.verified_at = datetime.utcnow()
        
        db.commit()
        db.refresh(document)
        
        logger.info(f"Document verified: {document_id}")
        try:
            from compliance import persist_compliance
            persist_compliance(db, document.travel_id, actor_user_id=current_user.user_id)
        except Exception as ce:
            logger.error(f"Compliance recompute failed for travel {document.travel_id}: {ce}")
        create_travel_notification(
            db, document.travel_id,
            "Document Verified",
            f"Your document '{document.doc_type}' has been verified.",
            "success"
        )
        record_remark(
            db, travel_id=document.travel_id, admin_id=current_user.user_id,
            document_id=document.document_id, remark_type='General',
            action='Approved', affected_requirement=document.doc_type,
            remark_text='Document verified by admin.', previous_status=previous_status,
            new_status=document.status)
        log_audit(db, current_user.user_id, 'document', 'verify',
                  document.document_id, f"Verified {document.doc_type}")
        
        return document
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying document: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.patch("/{document_id}/status")
async def update_document_status(
    document_id: int,
    status_data: dict,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update document status (admin only)"""
    try:
        document = db.query(Document).filter(Document.document_id == document_id).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        new_status = status_data.get("status")
        if not new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status is required"
            )
        
        valid_statuses = [
            # legacy vocabulary (HTML frontend compatibility) + design-doc lifecycle (p19)
            "Pending", "Uploaded", "Verified", "Incomplete", "Missing",
            "Not Uploaded", "Submitted", "Under Verification", "Rejected",
            "Resubmission Required",
        ]
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status must be one of: {', '.join(valid_statuses)}"
            )
        
        previous_status = document.status
        document.status = new_status
        db.commit()
        db.refresh(document)
        
        logger.info(f"Document status updated: {document_id} -> {new_status}")
        try:
            from compliance import persist_compliance
            persist_compliance(db, document.travel_id, actor_user_id=current_user.user_id)
        except Exception as ce:
            logger.error(f"Compliance recompute failed for travel {document.travel_id}: {ce}")
        record_remark(
            db, travel_id=document.travel_id, admin_id=current_user.user_id,
            document_id=document.document_id, remark_type='General',
            action='General', affected_requirement=document.doc_type,
            remark_text=f"Status set to {new_status}.", previous_status=previous_status,
            new_status=new_status)
        log_audit(db, current_user.user_id, 'document', 'status_change',
                  document.document_id, f"{document.doc_type}: {previous_status} -> {new_status}")
        
        return {"message": "Document status updated", "document": document}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document status: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.patch("/{document_id}/reject", response_model=DocumentResponse)
async def reject_document(
    document_id: int,
    reject_data: DocumentRejectRequest,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Reject a document with a reason (admin only)"""
    try:
        document = db.query(Document).filter(Document.document_id == document_id).first()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        previous_status = document.status
        document.status = "Rejected"
        document.remarks = reject_data.remarks
        document.verified_by = current_user.user_id
        document.verified_at = datetime.utcnow()

        db.commit()
        db.refresh(document)

        logger.info(f"Document rejected: {document_id}")
        try:
            from compliance import persist_compliance
            persist_compliance(db, document.travel_id, actor_user_id=current_user.user_id)
        except Exception as ce:
            logger.error(f"Compliance recompute failed for travel {document.travel_id}: {ce}")
        create_travel_notification(
            db, document.travel_id,
            "Document Rejected",
            f"Your document '{document.doc_type}' was rejected: {reject_data.remarks}",
            "warning"
        )
        record_remark(
            db, travel_id=document.travel_id, admin_id=current_user.user_id,
            document_id=document.document_id, remark_type='Incorrect Document',
            action='For Resubmission', affected_requirement=document.doc_type,
            remark_text=reject_data.remarks, previous_status=previous_status,
            new_status=document.status)
        log_audit(db, current_user.user_id, 'document', 'reject',
                  document.document_id, f"Rejected {document.doc_type}")

        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting document: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.post("/{document_id}/resubmit", response_model=DocumentResponse)
async def resubmit_document(
    document_id: int,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resubmit a rejected document with a corrected file (document owner only)"""
    try:
        document = db.query(Document).filter(Document.document_id == document_id).first()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        travel = document.travel
        if travel.user_id != current_user.user_id and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to resubmit this document"
            )

        if document.status not in ("Rejected", "Resubmission Required", "Incomplete", "Missing"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only rejected or incomplete documents can be resubmitted"
            )

        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )

        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum of {settings.MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB"
            )

        old_path = document.file_path
        filename, filepath = save_uploaded_file(file, travel.travel_id)

        previous_status = document.status
        document.file_name = filename
        document.file_path = filepath
        document.file_size = file_size
        document.status = "Under Verification"
        document.verified_by = None
        document.verified_at = None

        db.commit()
        db.refresh(document)

        if old_path and old_path != filepath:
            delete_uploaded_file(old_path)

        logger.info(f"Document resubmitted: {document_id}")
        create_admin_notification(
            db,
            "Document Resubmitted",
            f"A corrected '{document.doc_type}' was resubmitted for verification.",
            "info"
        )
        record_remark(
            db, travel_id=document.travel_id, admin_id=current_user.user_id,
            document_id=document.document_id, remark_type='General',
            action='For Verification', affected_requirement=document.doc_type,
            remark_text='Faculty resubmitted a corrected file.', previous_status=previous_status,
            new_status=document.status)
        log_audit(db, current_user.user_id, 'document', 'resubmit',
                  document.document_id, f"Resubmitted {document.doc_type}")

        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resubmitting document: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== DELETE ====================

@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete document"""
    try:
        document = db.query(Document).filter(Document.document_id == document_id).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Check authorization
        travel = document.travel
        if travel.user_id != current_user.user_id and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this document"
            )
        
        # Delete file
        if document.file_path:
            delete_uploaded_file(document.file_path)
        
        # Delete record
        db.delete(document)
        db.commit()
        
        logger.info(f"Document deleted: {document_id}")
        
        return {"message": "Document deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== STATISTICS ====================

@router.get("/stats/summary")
async def get_document_statistics(
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get document statistics (admin only)"""
    try:
        total_documents = db.query(Document).count()
        verified = db.query(Document).filter(Document.status == "Verified").count()
        pending = db.query(Document).filter(Document.status == "Pending").count()
        missing = db.query(Document).filter(Document.status == "Missing").count()
        under_verification = db.query(Document).filter(
            Document.status.in_(["Uploaded", "Submitted", "Under Verification"])
        ).count()
        rejected = db.query(Document).filter(
            Document.status.in_(["Rejected", "Resubmission Required", "Incomplete"])
        ).count()
        
        return {
            "total_documents": total_documents,
            "verified": verified,
            "pending": pending,
            "missing": missing,
            "under_verification": under_verification,
            "rejected": rejected,
            "verification_rate": round((verified / total_documents * 100) if total_documents > 0 else 0, 2)
        }
    
    except Exception as e:
        logger.error(f"Error calculating document statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )
