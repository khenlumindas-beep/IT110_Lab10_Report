"""
International Faculty Mobility Plan Routes
Identify faculty interested in mobility + equitable distribution of opportunities
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from database import get_db
from models import MobilityPlan, User, College, Department
from schemas import (
    MobilityPlanCreate, MobilityPlanUpdate,
    MobilityPlanResponse, MobilityPlanDetailResponse
)
from security import get_current_user, get_current_admin, TokenData
from datetime import datetime
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mobility-plans", tags=["mobility-plans"])

@router.get("/", response_model=List[MobilityPlanDetailResponse])
async def list_plans(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Admin: all plans; Faculty: own plan"""
    try:
        query = db.query(MobilityPlan)
        if current_user.role != "super_admin":
            query = query.filter(MobilityPlan.user_id == current_user.user_id)
        return query.order_by(desc(MobilityPlan.updated_at)).all()
    except Exception as e:
        logger.error(f"Error listing mobility plans: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred")

@router.get("/my-plan", response_model=Optional[MobilityPlanResponse])
async def get_my_plan(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plan = db.query(MobilityPlan).filter(
        MobilityPlan.user_id == current_user.user_id
    ).first()
    if not plan:
        return None
    return plan

@router.post("/", response_model=MobilityPlanResponse)
async def create_or_update_my_plan(
    data: MobilityPlanCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update the current faculty member's plan (one per faculty)"""
    try:
        plan = db.query(MobilityPlan).filter(
            MobilityPlan.user_id == current_user.user_id
        ).first()
        if plan:
            for field, value in data.dict(exclude_unset=True).items():
                setattr(plan, field, value)
            plan.updated_at = datetime.utcnow()
        else:
            plan = MobilityPlan(user_id=current_user.user_id, **data.model_dump())
            db.add(plan)
        db.commit()
        db.refresh(plan)
        logger.info(f"Mobility plan saved for user {current_user.user_id}")
        return plan
    except Exception as e:
        logger.error(f"Error saving mobility plan: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="An error occurred")

@router.put("/{plan_id}", response_model=MobilityPlanResponse)
async def update_plan(
    plan_id: int,
    data: MobilityPlanUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plan = db.query(MobilityPlan).filter(MobilityPlan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.user_id != current_user.user_id and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    for field, value in data.dict(exclude_unset=True).items():
        if value is not None:
            setattr(plan, field, value)
    plan.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(plan)
    return plan

@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plan = db.query(MobilityPlan).filter(MobilityPlan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.user_id != current_user.user_id and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    db.delete(plan)
    db.commit()
    return {"message": "Plan deleted"}

@router.get("/distribution")
async def get_distribution(
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Equitable distribution view: plans by college, department, academic rank, readiness"""
    try:
        college_rows = (
            db.query(College.college_id, College.code, College.name,
                     func.count(MobilityPlan.plan_id))
            .select_from(MobilityPlan)
            .join(User, User.user_id == MobilityPlan.user_id)
            .join(College, College.college_id == User.college_id)
            .group_by(College.college_id, College.code, College.name)
            .order_by(College.code)
            .all()
        )
        rank_rows = (
            db.query(User.academic_rank, func.count(MobilityPlan.plan_id))
            .select_from(MobilityPlan)
            .join(User, User.user_id == MobilityPlan.user_id)
            .group_by(User.academic_rank)
            .all()
        )
        readiness_rows = (
            db.query(MobilityPlan.readiness_status, func.count(MobilityPlan.plan_id))
            .group_by(MobilityPlan.readiness_status)
            .all()
        )
        dept_rows = (
            db.query(Department.code, Department.name, func.count(MobilityPlan.plan_id))
            .select_from(MobilityPlan)
            .join(User, User.user_id == MobilityPlan.user_id)
            .outerjoin(Department, Department.department_id == User.department_id)
            .group_by(Department.code, Department.name)
            .all()
        )
        return {
            "by_college": [
                {"college_id": r[0], "code": r[1], "name": r[2], "total_plans": r[3]}
                for r in college_rows
            ],
            "by_department": [
                {"code": r[0], "name": r[1], "total_plans": r[2]}
                for r in dept_rows
            ],
            "by_academic_rank": [
                {"academic_rank": r[0] or "N/A", "total_plans": r[1]}
                for r in rank_rows
            ],
            "by_readiness": [
                {"readiness_status": r[0], "total_plans": r[1]}
                for r in readiness_rows
            ],
            "total_plans": db.query(MobilityPlan).count()
        }
    except Exception as e:
        logger.error(f"Error computing mobility plan distribution: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred")
