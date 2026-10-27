"""
Document Types Routes
Admin-managed master list of required travel documents (Pre-Travel / Post-Travel)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import DocumentType
from schemas import DocumentTypeCreate, DocumentTypeUpdate, DocumentTypeResponse
from security import get_current_user, get_current_admin, TokenData
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/document-types", tags=["document-types"])

@router.get("/", response_model=list[DocumentTypeResponse])
async def list_document_types(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all document types ordered by category and sort order"""
    try:
        return db.query(DocumentType).order_by(
            DocumentType.category,
            DocumentType.sort_order,
            DocumentType.name
        ).all()
    except Exception as e:
        logger.error(f"Error listing document types: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.post("/", response_model=DocumentTypeResponse)
async def create_document_type(
    doc_type_data: DocumentTypeCreate,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a document type (admin only)"""
    try:
        existing = db.query(DocumentType).filter(
            DocumentType.name == doc_type_data.name
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document type already exists"
            )
        doc_type = DocumentType(**doc_type_data.model_dump())
        db.add(doc_type)
        db.commit()
        db.refresh(doc_type)
        logger.info(f"Document type created: {doc_type.name}")
        return doc_type
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating document type: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.put("/{doc_type_id}", response_model=DocumentTypeResponse)
async def update_document_type(
    doc_type_id: int,
    doc_type_data: DocumentTypeUpdate,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update a document type (admin only)"""
    try:
        doc_type = db.query(DocumentType).filter(
            DocumentType.doc_type_id == doc_type_id
        ).first()
        if not doc_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document type not found"
            )
        data = doc_type_data.model_dump(exclude_unset=True)
        if 'name' in data:
            duplicate = db.query(DocumentType).filter(
                DocumentType.name == data['name'],
                DocumentType.doc_type_id != doc_type_id
            ).first()
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Document type already exists"
                )
        for field, value in data.items():
            setattr(doc_type, field, value)
        db.commit()
        db.refresh(doc_type)
        logger.info(f"Document type updated: {doc_type.name}")
        return doc_type
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document type: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.delete("/{doc_type_id}")
async def delete_document_type(
    doc_type_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Delete a document type (admin only)"""
    try:
        doc_type = db.query(DocumentType).filter(
            DocumentType.doc_type_id == doc_type_id
        ).first()
        if not doc_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document type not found"
            )
        db.delete(doc_type)
        db.commit()
        logger.info(f"Document type deleted: {doc_type.name}")
        return {"message": "Document type deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document type: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )
