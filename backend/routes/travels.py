"""
Travel Records Management Routes
Handles CRUD operations for travel records
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, extract
from database import get_db
from models import Travel, User, College, Department, Document, RequirementItem
from schemas import TravelResponse, TravelCreate, TravelUpdate, TravelDetailResponse, WorkflowUpdate
from security import get_current_user, get_current_admin, TokenData
from audit import log_audit, record_remark
from constants import (
    compute_mobility_duration, FOLLOW_UP_STATUSES,
    PRE_TRAVEL_STATUSES, POST_TRAVEL_STATUSES,
    TRAVEL_WORKFLOW_TRANSITIONS, WORKFLOW_REQUIRES_PRE_TRAVEL_GATE
)
from datetime import datetime, date
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/travels", tags=["travels"])

# ==================== CREATE ====================

@router.post("/", response_model=TravelResponse)
async def create_travel(
    travel_data: TravelCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new travel record"""
    try:
        # Validate user exists
        user = db.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Validate college exists
        college = db.query(College).filter(College.college_id == travel_data.college_id).first()
        if not college:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="College not found"
            )
        
        # Create travel record (mobility duration auto-computed if not provided - Task 7)
        # user_id = record owner (faculty/admin registering the mobility).
        # Student participants have no login account - their details are stored on the row.
        travel = Travel(
            user_id=current_user.user_id,
            college_id=travel_data.college_id,
            department_id=travel_data.department_id,
            participant_type=travel_data.participant_type,
            participant_name=travel_data.participant_name,
            student_id_no=travel_data.student_id_no,
            program=travel_data.program,
            event_title=travel_data.event_title,
            mobility_type=travel_data.mobility_type,
            role_in_event=travel_data.role_in_event,
            start_date=travel_data.start_date,
            end_date=travel_data.end_date,
            location=travel_data.location,
            country=travel_data.country,
            funding_type=travel_data.funding_type,
            mobility_duration=travel_data.mobility_duration or compute_mobility_duration(
                travel_data.start_date, travel_data.end_date
            ),
            movs=travel_data.movs,
            pre_travel_status=travel_data.pre_travel_status,
            post_travel_status=travel_data.post_travel_status,
            follow_up=travel_data.follow_up,
            remarks=travel_data.remarks,
            timeline_status="Upcoming",
            workflow_status="Pending Requirements",
            doc_completeness="No Submission",
            risk_flag="Medium"
        )
        
        db.add(travel)
        db.commit()
        db.refresh(travel)
        
        logger.info(f"Travel record created: {travel.travel_id} by user {current_user.user_id}")
        
        return travel
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating travel: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating travel record"
        )

# ==================== PRE-TRAVEL REQUIREMENTS GATE ====================

def _missing_pre_travel(db: Session, travel: Travel):
    """Names of required Pre-Travel items with no usable (submitted) document.

    Same matching rules as the requirements endpoints: latest document per
    lowercased doc_type; a Rejected / Resubmission Required document does not
    satisfy the item. Used both by submit-for-approval and the Approve gate.
    """
    participant = travel.participant_type or "Faculty"
    items = (
        db.query(RequirementItem)
        .filter(
            RequirementItem.applies_to == participant,
            RequirementItem.phase == "Pre-Travel",
            RequirementItem.is_required == True,  # noqa: E712
            RequirementItem.parent_id.is_(None),
        )
        .order_by(RequirementItem.sort_order)
        .all()
    )
    docs = (
        db.query(Document)
        .filter(Document.travel_id == travel.travel_id)
        .order_by(Document.uploaded_at.desc(), Document.document_id.desc())
        .all()
    )
    latest = {}
    for d in docs:
        key = (d.doc_type or "").strip().lower()
        if key and key not in latest:
            latest[key] = d
    missing = []
    for it in items:
        doc = latest.get((it.name or "").strip().lower())
        if doc is None or (doc.status or "Submitted") in ("Rejected", "Resubmission Required"):
            missing.append(it.name)
    return missing


@router.post("/{travel_id}/submit-for-approval", response_model=TravelResponse)
async def submit_travel_for_approval(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Owner submits a Pending Requirements travel for admin approval.

    Gate: every required Pre-Travel item must have a submitted document.
    Completeness is computed server-side (same matching as the requirements
    checklist) — the UI cannot skip it.
    """
    try:
        travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
        if not travel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel not found"
            )
        if travel.user_id != current_user.user_id and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to submit this travel"
            )

        current = travel.workflow_status or "Pending Requirements"
        if current not in ("Pending Requirements", "Draft"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Travel is already '{current}' — only 'Pending Requirements' "
                       f"or 'Draft' can be submitted for approval."
            )

        missing = _missing_pre_travel(db, travel)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Pre-Travel requirements incomplete — "
                               "upload the missing documents first.",
                    "missing": missing,
                }
            )

        travel.workflow_status = "Submitted"
        travel.pre_travel_status = "Complete Documents"
        travel.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(travel)

        logger.info(f"Travel {travel_id} submitted for approval by user {current_user.user_id}")

        record_remark(
            db, travel_id=travel_id, admin_id=current_user.user_id,
            remark_type='General', action='General',
            remark_text="Submitted for approval (pre-travel checklist complete).",
            previous_status=current, new_status="Submitted")
        log_audit(db, current_user.user_id, 'travel', 'status_change',
                  travel_id, f"{travel.event_title}: {current} -> Submitted (pre-travel gate)")

        from routes.notifications import create_admin_notification
        try:
            create_admin_notification(
                db, "Travel Awaiting Approval",
                f"'{travel.event_title}' ({travel.participant_type or 'Faculty'}) "
                f"passed the pre-travel checklist and is awaiting your review.",
                "info")
        except Exception as ne:
            logger.error(f"Admin notification failed: {ne}")

        return travel

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting travel for approval: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while submitting the travel"
        )

# ==================== READ ====================

@router.get("/{travel_id}", response_model=TravelDetailResponse)
async def get_travel(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get travel details"""
    try:
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
                detail="Not authorized to access this travel record"
            )
        
        return travel
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving travel: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/", response_model=List[TravelResponse])
async def list_travels(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: str = Query(None),
    country: str = Query(None),
    mobility_type: str = Query(None),
    participant_type: str = Query(None, description="Faculty or Student"),
    year: int = Query(None, ge=2000, le=2100),
    college_id: int = Query(None)
):
    """List travel records with optional filters"""
    try:
        query = db.query(Travel)
        
        # Filter by user if faculty, show all if admin
        if current_user.role != "super_admin":
            query = query.filter(Travel.user_id == current_user.user_id)
        elif college_id:
            query = query.filter(Travel.college_id == college_id)
        
        # Apply filters
        if status:
            query = query.filter(Travel.timeline_status == status)
        if country:
            query = query.filter(Travel.country.ilike(f"%{country}%"))
        if mobility_type:
            query = query.filter(Travel.mobility_type == mobility_type)
        if participant_type:
            if participant_type not in ("Faculty", "Student"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="participant_type must be 'Faculty' or 'Student'"
                )
            query = query.filter(Travel.participant_type == participant_type)
        if year:
            query = query.filter(
                and_(
                    func.date_part('year', Travel.start_date) == year
                )
            )
        
        travels = query.order_by(desc(Travel.created_at)).offset(skip).limit(limit).all()
        
        return travels
    
    except Exception as e:
        logger.error(f"Error listing travels: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/user/{user_id}", response_model=List[TravelResponse])
async def get_user_travels(
    user_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Get travels for specific user (own records, or any user for admins)"""
    try:
        if user_id != current_user.user_id and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this user's travel records"
            )
        travels = db.query(Travel).filter(
            Travel.user_id == user_id
        ).order_by(desc(Travel.created_at)).offset(skip).limit(limit).all()
        
        return travels
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing user travels: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/college/{college_id}", response_model=List[TravelResponse])
async def get_college_travels(
    college_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """Get all travels for a college (admin only)"""
    try:
        travels = db.query(Travel).filter(
            Travel.college_id == college_id
        ).order_by(desc(Travel.created_at)).offset(skip).limit(limit).all()
        
        return travels
    
    except Exception as e:
        logger.error(f"Error listing college travels: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== UPDATE ====================

@router.put("/{travel_id}", response_model=TravelResponse)
async def update_travel(
    travel_id: int,
    travel_data: TravelUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update travel record"""
    try:
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
                detail="Not authorized to update this travel record"
            )
        
        # Update fields
        explicit_duration = travel_data.mobility_duration
        for field, value in travel_data.dict(exclude_unset=True).items():
            if value is not None:
                setattr(travel, field, value)
        
        # Recompute mobility duration if dates changed and duration not explicitly set
        if explicit_duration is None and (
            'start_date' in travel_data.dict(exclude_unset=True) or
            'end_date' in travel_data.dict(exclude_unset=True)
        ):
            travel.mobility_duration = compute_mobility_duration(travel.start_date, travel.end_date)
        
        travel.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(travel)
        
        logger.info(f"Travel record updated: {travel_id}")
        
        return travel
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating travel: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating travel record"
        )

@router.patch("/{travel_id}/status")
async def update_travel_status(
    travel_id: int,
    status_data: dict,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update travel status (admin only)"""
    try:
        travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
        
        if not travel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel not found"
            )
        
        new_status = status_data.get("timeline_status")
        if not new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status is required"
            )
        
        valid_statuses = ["Upcoming", "Ongoing", "Completed", "Cancelled"]
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status must be one of: {', '.join(valid_statuses)}"
            )
        
        travel.timeline_status = new_status
        travel.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(travel)
        
        logger.info(f"Travel status updated: {travel_id} -> {new_status}")
        
        return {"message": "Status updated successfully", "travel": travel}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating travel status: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.patch("/{travel_id}/workflow")
async def update_travel_workflow(
    travel_id: int,
    workflow_data: WorkflowUpdate,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Advance travel workflow status (admin only, design-doc 8-state lifecycle)"""
    try:
        travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()

        if not travel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel not found"
            )

        current = travel.workflow_status or "Submitted"
        target = workflow_data.workflow_status

        allowed = TRAVEL_WORKFLOW_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot change workflow from '{current}' to '{target}'. "
                       f"Allowed: {', '.join(allowed) if allowed else 'none (terminal state)'}"
            )

        # Pre-travel requirements gate: Approve only when the checklist is complete.
        if target in WORKFLOW_REQUIRES_PRE_TRAVEL_GATE:
            missing = _missing_pre_travel(db, travel)
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": "Cannot approve — Pre-Travel requirements incomplete. "
                                   "Ask the faculty to upload the missing documents.",
                        "missing": missing,
                    }
                )

        travel.workflow_status = target
        if workflow_data.remarks:
            travel.remarks = workflow_data.remarks
        travel.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(travel)

        logger.info(f"Travel workflow updated: {travel_id} {current} -> {target}")

        record_remark(
            db, travel_id=travel_id, admin_id=current_user.user_id,
            remark_type='General', action='General',
            remark_text=workflow_data.remarks or f"Workflow moved to {target}.",
            previous_status=current, new_status=target)
        log_audit(db, current_user.user_id, 'travel', 'status_change',
                  travel_id, f"{travel.event_title}: {current} -> {target}")

        # Recompute compliance whenever workflow advances (BR-07).
        try:
            from compliance import persist_compliance
            persist_compliance(db, travel_id, actor_user_id=current_user.user_id)
        except Exception as ce:
            logger.error(f"Compliance recompute failed for travel {travel_id}: {ce}")

        from routes.notifications import create_travel_notification
        create_travel_notification(
            db, travel_id,
            "Travel Status Update",
            f"Your travel '{travel.event_title}' status is now '{target}'."
            + (f" Remarks: {workflow_data.remarks}" if workflow_data.remarks else ""),
            "info"
        )

        return {"message": "Workflow updated successfully", "travel": travel}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating travel workflow: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.patch("/{travel_id}/compliance")
async def update_compliance_status(
    travel_id: int,
    compliance_data: dict,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update compliance status (admin only)"""
    try:
        travel = db.query(Travel).filter(Travel.travel_id == travel_id).first()
        
        if not travel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel not found"
            )
        
        doc_completeness = compliance_data.get("doc_completeness")
        risk_flag = compliance_data.get("risk_flag")
        follow_up = compliance_data.get("follow_up")
        pre_travel_status = compliance_data.get("pre_travel_status")
        post_travel_status = compliance_data.get("post_travel_status")
        movs = compliance_data.get("movs")
        
        if doc_completeness:
            travel.doc_completeness = doc_completeness
        if risk_flag:
            travel.risk_flag = risk_flag
        if follow_up is not None:
            if follow_up not in FOLLOW_UP_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Follow Up must be one of: {', '.join(FOLLOW_UP_STATUSES)}"
                )
            travel.follow_up = follow_up
        if pre_travel_status is not None:
            if pre_travel_status not in PRE_TRAVEL_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"pre_travel_status must be one of: {', '.join(PRE_TRAVEL_STATUSES)}"
                )
            travel.pre_travel_status = pre_travel_status
        if post_travel_status is not None:
            if post_travel_status not in POST_TRAVEL_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"post_travel_status must be one of: {', '.join(POST_TRAVEL_STATUSES)}"
                )
            travel.post_travel_status = post_travel_status
        if movs is not None:
            travel.movs = movs
        
        travel.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(travel)
        
        logger.info(f"Travel compliance updated: {travel_id}")
        
        return {"message": "Compliance updated successfully", "travel": travel}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating compliance: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== DELETE ====================

@router.delete("/{travel_id}")
async def delete_travel(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete travel record"""
    try:
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
                detail="Not authorized to delete this travel record"
            )
        
        db.delete(travel)
        db.commit()
        
        logger.info(f"Travel record deleted: {travel_id}")
        
        return {"message": "Travel record deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting travel: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting travel record"
        )

# ==================== STATISTICS ====================

@router.get("/statistics/", response_model=dict)
async def get_travel_statistics(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get travel statistics"""
    try:
        query = db.query(Travel)
        
        # Filter by user if faculty
        if current_user.role != "super_admin":
            query = query.filter(Travel.user_id == current_user.user_id)
        
        travels = query.all()
        
        if not travels:
            return {
                "total_travels": 0,
                "completed_travels": 0,
                "ongoing_travels": 0,
                "upcoming_travels": 0,
                "compliance_rate": 0.0,
                "average_duration_days": 0
            }
        
        total = len(travels)
        completed = len([t for t in travels if t.timeline_status == "Completed"])
        ongoing = len([t for t in travels if t.timeline_status == "Ongoing"])
        upcoming = len([t for t in travels if t.timeline_status == "Upcoming"])
        
        # Calculate compliance rate
        compliant = len([t for t in travels if t.doc_completeness == "Complete"])
        compliance_rate = (compliant / total * 100) if total > 0 else 0
        
        # Calculate average duration
        total_days = 0
        for travel in travels:
            delta = travel.end_date - travel.start_date
            total_days += delta.days
        average_duration = total_days / total if total > 0 else 0
        
        return {
            "total_travels": total,
            "completed_travels": completed,
            "ongoing_travels": ongoing,
            "upcoming_travels": upcoming,
            "compliance_rate": round(compliance_rate, 2),
            "average_duration_days": round(average_duration, 1)
        }
    
    except Exception as e:
        logger.error(f"Error calculating statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/college/{college_id}/statistics", response_model=dict)
async def get_college_statistics(
    college_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get statistics for a college (admin only)"""
    try:
        travels = db.query(Travel).filter(Travel.college_id == college_id).all()
        users = db.query(User).filter(User.college_id == college_id).count()
        
        if not travels:
            return {
                "college_id": college_id,
                "total_travels": 0,
                "total_faculty": users,
                "countries_visited": 0,
                "total_funding": 0,
                "compliance_rate": 0.0
            }
        
        # Unique countries
        countries = set(t.country for t in travels if t.country)
        
        total = len(travels)
        compliant = len([t for t in travels if t.doc_completeness == "Complete"])
        compliance_rate = (compliant / total * 100) if total > 0 else 0
        
        return {
            "college_id": college_id,
            "total_travels": total,
            "total_faculty": users,
            "countries_visited": len(countries),
            "total_funding": total,
            "compliance_rate": round(compliance_rate, 2)
        }
    
    except Exception as e:
        logger.error(f"Error calculating college statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )
