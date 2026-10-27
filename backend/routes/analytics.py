"""
Analytics and Compliance Analysis Routes
Handles data analytics, compliance analysis, and risk prediction
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from database import get_db
from models import Travel, User, College, Document
from security import get_current_user, get_current_admin, TokenData
from ml_engine import compliance_analyzer, risk_predictor
import logging
from typing import List, Dict
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# ==================== TRAVEL ANALYTICS ====================

@router.get("/travel/{travel_id}/compliance")
async def get_travel_compliance(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get compliance analysis for a specific travel"""
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
                detail="Not authorized"
            )
        
        # Prepare travel data for analysis
        travel_data = {
            'travel_id': travel.travel_id,
            'start_date': travel.start_date,
            'end_date': travel.end_date,
            'country': travel.country,
            'funding_type': travel.funding_type,
            'mobility_type': travel.mobility_type,
            'doc_completeness': travel.doc_completeness,
            'timeline_pct': float(travel.timeline_pct) if travel.timeline_pct else 0,
            'timeline_status': travel.timeline_status,
            'previous_travels_count': db.query(Travel).filter(
                and_(
                    Travel.user_id == travel.user_id,
                    Travel.timeline_status == 'Completed'
                )
            ).count()
        }
        
        # Get compliance analysis
        analysis = compliance_analyzer.analyze_travel_compliance(travel_data)
        
        # Get associated documents
        documents = db.query(Document).filter(Document.travel_id == travel_id).all()
        analysis['documents_count'] = len(documents)
        analysis['verified_documents'] = len([d for d in documents if d.status == 'Verified'])
        
        return analysis
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing travel compliance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/travel/{travel_id}/risk")
async def get_travel_risk_prediction(
    travel_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get risk prediction for a specific travel"""
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
                detail="Not authorized"
            )
        
        # Prepare travel data
        travel_data = {
            'travel_id': travel.travel_id,
            'start_date': travel.start_date,
            'end_date': travel.end_date,
            'country': travel.country,
            'funding_type': travel.funding_type,
            'mobility_type': travel.mobility_type,
            'doc_completeness': travel.doc_completeness,
            'previous_travels_count': db.query(Travel).filter(
                and_(
                    Travel.user_id == travel.user_id,
                    Travel.timeline_status == 'Completed'
                )
            ).count()
        }
        
        # Get risk prediction
        risk_level, risk_score = risk_predictor.predict_risk(travel_data)
        
        # Update travel record with risk data
        travel.risk_flag = risk_level
        travel.risk_score = risk_score
        db.commit()
        
        return {
            "travel_id": travel_id,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "updated_at": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error predicting risk: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== USER ANALYTICS ====================

@router.get("/user/summary")
async def get_user_analytics(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get analytics summary for current user"""
    try:
        # Get user's travels
        travels = db.query(Travel).filter(Travel.user_id == current_user.user_id).all()
        
        if not travels:
            return {
                "user_id": current_user.user_id,
                "total_travels": 0,
                "completed_travels": 0,
                "ongoing_travels": 0,
                "upcoming_travels": 0,
                "average_compliance_score": 0.0,
                "high_risk_travels": 0,
                "compliance_status": "No travels recorded"
            }
        
        # Prepare travel data
        travel_data_list = []
        for travel in travels:
            travel_data = {
                'travel_id': travel.travel_id,
                'start_date': travel.start_date,
                'end_date': travel.end_date,
                'country': travel.country,
                'funding_type': travel.funding_type,
                'mobility_type': travel.mobility_type,
                'doc_completeness': travel.doc_completeness,
                'timeline_pct': float(travel.timeline_pct) if travel.timeline_pct else 0,
                'timeline_status': travel.timeline_status,
                'previous_travels_count': len([t for t in travels if t.timeline_status == 'Completed'])
            }
            travel_data_list.append(travel_data)
        
        # Analyze compliance
        college_analysis = compliance_analyzer.analyze_college_compliance(travel_data_list)
        
        # Get status breakdown
        completed = len([t for t in travels if t.timeline_status == 'Completed'])
        ongoing = len([t for t in travels if t.timeline_status == 'Ongoing'])
        upcoming = len([t for t in travels if t.timeline_status == 'Upcoming'])
        
        return {
            "user_id": current_user.user_id,
            "total_travels": len(travels),
            "completed_travels": completed,
            "ongoing_travels": ongoing,
            "upcoming_travels": upcoming,
            "compliance_rate": college_analysis.get('compliance_rate', 0),
            "average_compliance_score": college_analysis.get('average_compliance_score', 0),
            "average_risk_score": college_analysis.get('average_risk_score', 0),
            "high_risk_travels": college_analysis.get('high_risk_count', 0),
            "medium_risk_travels": college_analysis.get('medium_risk_count', 0),
            "low_risk_travels": college_analysis.get('low_risk_count', 0),
            "analysis_timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error calculating user analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== COLLEGE ANALYTICS ====================

@router.get("/college/{college_id}/summary")
async def get_college_analytics(
    college_id: int,
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get analytics summary for a college (admin only)"""
    try:
        # Verify college exists
        college = db.query(College).filter(College.college_id == college_id).first()
        if not college:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="College not found"
            )
        
        # Get college travels
        travels = db.query(Travel).filter(Travel.college_id == college_id).all()
        
        # Prepare travel data for analysis
        travel_data_list = []
        for travel in travels:
            travel_data = {
                'travel_id': travel.travel_id,
                'start_date': travel.start_date,
                'end_date': travel.end_date,
                'country': travel.country,
                'funding_type': travel.funding_type,
                'mobility_type': travel.mobility_type,
                'doc_completeness': travel.doc_completeness,
                'timeline_pct': float(travel.timeline_pct) if travel.timeline_pct else 0,
                'timeline_status': travel.timeline_status,
                'previous_travels_count': 0
            }
            travel_data_list.append(travel_data)
        
        # Get compliance analysis
        analysis = compliance_analyzer.analyze_college_compliance(travel_data_list)
        
        # Get faculty count
        faculty_count = db.query(User).filter(User.college_id == college_id).count()
        
        # Get document statistics
        doc_stats = db.query(Document).join(Travel).filter(
            Travel.college_id == college_id
        ).all()
        
        verified_docs = len([d for d in doc_stats if d.status == 'Verified'])
        
        # Get status breakdown
        completed = len([t for t in travels if t.timeline_status == 'Completed'])
        ongoing = len([t for t in travels if t.timeline_status == 'Ongoing'])
        upcoming = len([t for t in travels if t.timeline_status == 'Upcoming'])
        
        # Get unique countries
        countries = set(t.country for t in travels if t.country)
        
        return {
            "college_id": college_id,
            "college_name": college.name,
            "total_travels": len(travels),
            "total_faculty": faculty_count,
            "completed_travels": completed,
            "ongoing_travels": ongoing,
            "upcoming_travels": upcoming,
            "countries_visited": len(countries),
            "total_documents": len(doc_stats),
            "verified_documents": verified_docs,
            "compliance_rate": analysis.get('compliance_rate', 0),
            "average_compliance_score": analysis.get('average_compliance_score', 0),
            "average_risk_score": analysis.get('average_risk_score', 0),
            "high_risk_travels": analysis.get('high_risk_count', 0),
            "medium_risk_travels": analysis.get('medium_risk_count', 0),
            "low_risk_travels": analysis.get('low_risk_count', 0),
            "analysis_timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating college analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== SYSTEM-WIDE ANALYTICS ====================

@router.get("/system/summary")
async def get_system_analytics(
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get system-wide analytics (admin only)"""
    try:
        # Get all travels
        all_travels = db.query(Travel).all()
        
        if not all_travels:
            return {
                "total_travels": 0,
                "total_colleges": 0,
                "total_faculty": 0,
                "total_documents": 0,
                "overall_compliance_rate": 0.0
            }
        
        # Prepare travel data
        travel_data_list = []
        for travel in all_travels:
            travel_data = {
                'travel_id': travel.travel_id,
                'start_date': travel.start_date,
                'end_date': travel.end_date,
                'country': travel.country,
                'funding_type': travel.funding_type,
                'mobility_type': travel.mobility_type,
                'doc_completeness': travel.doc_completeness,
                'timeline_pct': float(travel.timeline_pct) if travel.timeline_pct else 0,
                'timeline_status': travel.timeline_status
            }
            travel_data_list.append(travel_data)
        
        # Get compliance analysis
        analysis = compliance_analyzer.analyze_college_compliance(travel_data_list)
        
        # Get counts
        total_colleges = db.query(College).count()
        total_faculty = db.query(User).filter(User.role == 'faculty').count()
        total_documents = db.query(Document).count()
        
        # Get unique countries
        countries = set(t.country for t in all_travels if t.country)
        
        # Get status breakdown
        completed = len([t for t in all_travels if t.timeline_status == 'Completed'])
        ongoing = len([t for t in all_travels if t.timeline_status == 'Ongoing'])
        upcoming = len([t for t in all_travels if t.timeline_status == 'Upcoming'])
        
        return {
            "total_travels": len(all_travels),
            "completed_travels": completed,
            "ongoing_travels": ongoing,
            "upcoming_travels": upcoming,
            "total_colleges": total_colleges,
            "total_faculty": total_faculty,
            "countries_visited": len(countries),
            "total_documents": total_documents,
            "overall_compliance_rate": analysis.get('compliance_rate', 0),
            "average_compliance_score": analysis.get('average_compliance_score', 0),
            "average_risk_score": analysis.get('average_risk_score', 0),
            "high_risk_travels": analysis.get('high_risk_count', 0),
            "medium_risk_travels": analysis.get('medium_risk_count', 0),
            "low_risk_travels": analysis.get('low_risk_count', 0),
            "analysis_timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error calculating system analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

# ==================== TRENDING DATA ====================

@router.get("/trends/top-countries")
async def get_top_travel_countries(
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(10, ge=1, le=50)
):
    """Get top travel destinations"""
    try:
        travels = db.query(Travel).all()
        
        # Count by country
        country_counts = {}
        for travel in travels:
            country = travel.country or "Unknown"
            country_counts[country] = country_counts.get(country, 0) + 1
        
        # Sort and limit
        top_countries = sorted(
            country_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        return {
            "top_countries": [{"country": c, "count": count} for c, count in top_countries],
            "total_unique_countries": len(country_counts)
        }
    
    except Exception as e:
        logger.error(f"Error getting top countries: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )

@router.get("/trends/mobility-types")
async def get_mobility_type_distribution(
    current_user: TokenData = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get distribution of Type of Mobility records"""
    try:
        travels = db.query(Travel).all()
        
        # Count by mobility type
        mobility_counts = {}
        for travel in travels:
            mobility = travel.mobility_type or "Other"
            mobility_counts[mobility] = mobility_counts.get(mobility, 0) + 1
        
        return {
            "mobility_types": mobility_counts,
            "total_travels": len(travels)
        }
    
    except Exception as e:
        logger.error(f"Error getting mobility type distribution: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )
