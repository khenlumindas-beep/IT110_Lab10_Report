"""
Student Internship Abroad Program (SIAP) Routes
Admin-managed only - students do not have login accounts
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from database import get_db
from models import SiapInternship, College
from schemas import SiapCreate, SiapUpdate, SiapResponse
from security import get_current_admin
from datetime import datetime
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/siap", tags=["siap"])

@router.get("/", response_model=List[SiapResponse])
async def list_internships(
    current_user=Depends(get_current_admin),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    college_id: int = Query(None),
    status_filter: str = Query(None, alias="status")
):
    """List SIAP internships, optionally filtered by college (Task 6) or status"""
    try:
        query = db.query(SiapInternship)
        if college_id:
            query = query.filter(SiapInternship.college_id == college_id)
        if status_filter:
            query = query.filter(SiapInternship.status == status_filter)
        return query.order_by(desc(SiapInternship.created_at)).offset(skip).limit(limit).all()
    except Exception as e:
        logger.error(f"Error listing SIAP internships: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred")

@router.get("/stats/by-college")
async def internships_by_college(
    current_user=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """SIAP counts per college (separate view per college - Task 6)"""
    try:
        rows = (
            db.query(
                College.college_id,
                College.code,
                College.name,
                func.count(SiapInternship.internship_id).label("total"),
            )
            .outerjoin(SiapInternship, SiapInternship.college_id == College.college_id)
            .group_by(College.college_id, College.code, College.name)
            .order_by(College.code)
            .all()
        )
        return {
            "colleges": [
                {
                    "college_id": r.college_id,
                    "code": r.code,
                    "name": r.name,
                    "total_internships": r.total,
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error(f"Error building SIAP college stats: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred")

@router.get("/{internship_id}", response_model=SiapResponse)
async def get_internship(
    internship_id: int,
    current_user=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    internship = db.query(SiapInternship).filter(
        SiapInternship.internship_id == internship_id
    ).first()
    if not internship:
        raise HTTPException(status_code=404, detail="Internship not found")
    return internship

@router.post("/", response_model=SiapResponse)
async def create_internship(
    data: SiapCreate,
    current_user=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    college = db.query(College).filter(College.college_id == data.college_id).first()
    if not college:
        raise HTTPException(status_code=400, detail="College not found")
    internship = SiapInternship(**data.model_dump())
    db.add(internship)
    db.commit()
    db.refresh(internship)
    logger.info(f"SIAP internship created: {internship.internship_id}")
    return internship

@router.put("/{internship_id}", response_model=SiapResponse)
async def update_internship(
    internship_id: int,
    data: SiapUpdate,
    current_user=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    internship = db.query(SiapInternship).filter(
        SiapInternship.internship_id == internship_id
    ).first()
    if not internship:
        raise HTTPException(status_code=404, detail="Internship not found")
    for field, value in data.dict(exclude_unset=True).items():
        if value is not None:
            setattr(internship, field, value)
    internship.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(internship)
    return internship

@router.patch("/{internship_id}/status")
async def update_internship_status(
    internship_id: int,
    status_data: dict,
    current_user=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update status and/or milestone"""
    internship = db.query(SiapInternship).filter(
        SiapInternship.internship_id == internship_id
    ).first()
    if not internship:
        raise HTTPException(status_code=404, detail="Internship not found")
    new_status = status_data.get("status")
    milestone = status_data.get("milestone")
    if new_status:
        if new_status not in ("Not Started", "Started", "Ongoing", "Completed"):
            raise HTTPException(status_code=400, detail="Invalid status")
        internship.status = new_status
    if milestone is not None:
        internship.milestone = milestone
    internship.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(internship)
    return {"message": "Updated successfully", "internship": internship}

@router.delete("/{internship_id}")
async def delete_internship(
    internship_id: int,
    current_user=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    internship = db.query(SiapInternship).filter(
        SiapInternship.internship_id == internship_id
    ).first()
    if not internship:
        raise HTTPException(status_code=404, detail="Internship not found")
    db.delete(internship)
    db.commit()
    return {"message": "Internship deleted"}
