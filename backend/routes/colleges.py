"""
College Management Routes
Handles college-related operations
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
from models import College, Department, User, Travel
from schemas import CollegeResponse, CollegeCreate, DepartmentResponse, DepartmentCreate
from security import get_current_admin, TokenData
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/colleges", tags=["colleges"])

# ==================== COLLEGES ====================

@router.get("/", response_model=List[CollegeResponse])
async def list_colleges(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """List all colleges"""
    try:
        colleges = db.query(College).offset(skip).limit(limit).all()
        return colleges
    except Exception as e:
        logger.error(f"Error listing colleges: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/{college_id}", response_model=CollegeResponse)
async def get_college(
    college_id: int,
    db: Session = Depends(get_db)
):
    """Get college details"""
    try:
        college = db.query(College).filter(College.college_id == college_id).first()
        
        if not college:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="College not found"
            )
        
        return college
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving college: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.post("/", response_model=CollegeResponse)
async def create_college(
    college_data: CollegeCreate,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create new college (admin only)"""
    try:
        # Check if code already exists
        existing = db.query(College).filter(College.code == college_data.code).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="College code already exists"
            )
        
        college = College(
            code=college_data.code,
            name=college_data.name,
            dean_name=college_data.dean_name
        )
        
        db.add(college)
        db.commit()
        db.refresh(college)
        
        logger.info(f"College created: {college.college_id}")
        
        return college
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating college: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.put("/{college_id}", response_model=CollegeResponse)
async def update_college(
    college_id: int,
    college_data: dict,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update college (admin only)"""
    try:
        college = db.query(College).filter(College.college_id == college_id).first()
        
        if not college:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="College not found"
            )
        
        for field, value in college_data.items():
            if value is not None and hasattr(college, field):
                setattr(college, field, value)
        
        db.commit()
        db.refresh(college)
        
        logger.info(f"College updated: {college_id}")
        
        return college
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating college: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== DEPARTMENTS ====================

@router.get("/{college_id}/departments", response_model=List[DepartmentResponse])
async def list_college_departments(
    college_id: int,
    db: Session = Depends(get_db)
):
    """List departments for a college"""
    try:
        departments = db.query(Department).filter(
            Department.college_id == college_id
        ).all()
        
        return departments
    except Exception as e:
        logger.error(f"Error listing departments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.post("/{college_id}/departments", response_model=DepartmentResponse)
async def create_department(
    college_id: int,
    dept_data: DepartmentCreate,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create department (admin only)"""
    try:
        # Verify college exists
        college = db.query(College).filter(College.college_id == college_id).first()
        if not college:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="College not found"
            )
        
        # Check unique constraint
        existing = db.query(Department).filter(
            and_(
                Department.college_id == college_id,
                Department.code == dept_data.code
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department code already exists in this college"
            )
        
        department = Department(
            college_id=college_id,
            code=dept_data.code,
            name=dept_data.name
        )
        
        db.add(department)
        db.commit()
        db.refresh(department)
        
        logger.info(f"Department created: {department.department_id}")
        
        return department
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating department: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== COLLEGE STATISTICS ====================

@router.get("/{college_id}/stats")
async def get_college_stats(
    college_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get statistics for a college"""
    try:
        college = db.query(College).filter(College.college_id == college_id).first()
        if not college:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="College not found"
            )
        
        # Get statistics
        total_faculty = db.query(User).filter(User.college_id == college_id).count()
        total_travels = db.query(Travel).filter(Travel.college_id == college_id).count()
        
        travels = db.query(Travel).filter(Travel.college_id == college_id).all()
        countries = len(set(t.country for t in travels if t.country))
        
        compliant = len([t for t in travels if t.doc_completeness == "Complete"])
        compliance_rate = (compliant / total_travels * 100) if total_travels > 0 else 0
        
        return {
            "college_id": college_id,
            "college_name": college.name,
            "total_faculty": total_faculty,
            "total_travels": total_travels,
            "countries_visited": countries,
            "compliance_rate": round(compliance_rate, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

from sqlalchemy import and_
