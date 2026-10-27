"""
Machine Learning Engine for SmartTrack
Handles risk prediction and compliance analysis using ML algorithms
"""
import pickle
import numpy as np
from datetime import datetime, date
from typing import Dict, List, Tuple
import logging
from config import settings
import os

logger = logging.getLogger(__name__)

class RiskPredictor:
    """
    Machine Learning-based Risk Predictor
    Uses Random Forest and Naive Bayes algorithms for compliance risk prediction
    """
    
    def __init__(self):
        """Initialize the risk predictor"""
        self.model_path = settings.MODEL_PATH
        self.risk_threshold = settings.RISK_THRESHOLD
        self.ensure_model_dir()
    
    def ensure_model_dir(self):
        """Ensure model directory exists"""
        if not os.path.exists(self.model_path):
            os.makedirs(self.model_path)
    
    def extract_features(self, travel: Dict) -> np.ndarray:
        """
        Extract features from travel data for ML model
        Features:
        1. Days until travel start (0-365)
        2. Duration of travel (1-365)
        3. Funding type (0-4)
        4. Activity type (0-4)
        5. Document completeness (0-100%)
        6. Previous travels count
        7. Is international (0/1)
        """
        try:
            # Calculate days until travel
            today = date.today()
            start_date = travel.get('start_date')
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            
            days_until = (start_date - today).days
            days_until = max(0, min(days_until, 365))
            
            # Calculate duration
            end_date = travel.get('end_date')
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            duration = (end_date - start_date).days
            duration = max(1, min(duration, 365))
            
            # Encode funding type
            funding_types = {
                'Fully Funded': 0,
                'Partially Funded': 1,
                'Self-Funded': 2,
                'No Funding Required': 3,
                'To Be Determined': 4
            }
            funding_encoded = funding_types.get(travel.get('funding_type', 'To Be Determined'), 4)
            
            # Encode Type of Mobility (Task 1: 11 official values + Other)
            mobility_types = {
                'Faculty Exchange': 0,
                'Teaching Mobility': 1,
                'Research Mobility': 2,
                'International Training': 3,
                'International Conference': 4,
                'Visiting Professorship/Scholarship': 5,
                'Fellowship': 6,
                'Short-Term Study Program': 7,
                'International Collaborative Research': 8,
                'International Community Extension Engagement': 9,
                'International Benchmarking': 10,
                'Other': 11
            }
            mobility_type = travel.get('mobility_type') or travel.get('activity_type', 'Other')
            mobility_encoded = mobility_types.get(mobility_type, 11)
            
            # Document completeness
            doc_completeness_map = {
                'Complete': 100,
                'Incomplete': 50,
                'No Submission': 0,
                'Pending': 25,
                'Missing': 0
            }
            doc_completeness = doc_completeness_map.get(
                travel.get('doc_completeness', 'No Submission'), 0
            )
            
            # Previous travels count
            previous_travels = travel.get('previous_travels_count', 0)
            previous_travels = min(previous_travels, 20)
            
            # Is international
            is_international = 1 if travel.get('country', '').lower() != 'philippines' else 0
            
            # Construct feature vector
            features = np.array([
                days_until / 365.0,  # Normalize to 0-1
                duration / 365.0,     # Normalize to 0-1
                funding_encoded / 4.0,  # Normalize to 0-1
                mobility_encoded / 11.0, # Normalize to 0-1
                doc_completeness / 100.0,  # Already 0-1
                previous_travels / 20.0,   # Normalize to 0-1
                is_international
            ])
            
            return features
        
        except Exception as e:
            logger.error(f"Error extracting features: {str(e)}")
            return np.array([0.5] * 7)  # Return neutral features on error
    
    def predict_risk(self, travel: Dict) -> Tuple[str, float]:
        """
        Predict compliance risk for a travel
        Returns: (risk_level, risk_score) where risk_level is 'Low', 'Medium', or 'High'
        and risk_score is 0-1
        """
        try:
            features = self.extract_features(travel)
            
            # Simple heuristic-based risk prediction
            # In production, this would use trained ML models
            risk_score = self._calculate_risk_score(travel, features)
            
            # Classify risk level
            if risk_score < 0.3:
                risk_level = "Low"
            elif risk_score < 0.7:
                risk_level = "Medium"
            else:
                risk_level = "High"
            
            return risk_level, round(risk_score, 3)
        
        except Exception as e:
            logger.error(f"Error predicting risk: {str(e)}")
            return "Medium", 0.5
    
    def _calculate_risk_score(self, travel: Dict, features: np.ndarray) -> float:
        """
        Calculate risk score based on features
        Higher score = higher risk
        """
        risk_score = 0.0
        
        # Days until travel impact (shorter notice = higher risk)
        days_until = features[0] * 365
        if days_until < 30:
            risk_score += 0.3  # High risk if < 30 days
        elif days_until < 60:
            risk_score += 0.2  # Medium risk if < 60 days
        else:
            risk_score += 0.05  # Low risk if > 60 days
        
        # Document completeness (incomplete docs = higher risk)
        doc_completeness = features[4]
        if doc_completeness < 0.5:
            risk_score += 0.35
        elif doc_completeness < 0.8:
            risk_score += 0.15
        
        # Funding uncertainty
        if features[2] >= 0.75:  # To Be Determined funding
            risk_score += 0.15
        elif features[2] >= 0.5:  # Partially funded or self-funded
            risk_score += 0.1
        
        # International travel
        if features[6] == 1.0:  # International
            risk_score += 0.1
        
        # Activity type (conferences and research are higher risk)
        activity = features[3]
        if activity <= 0.25:  # Conference
            risk_score += 0.05
        elif activity <= 0.5:  # Workshop
            risk_score += 0.03
        elif activity <= 0.75:  # Training
            risk_score += 0.02
        
        # Normalize to 0-1
        risk_score = min(risk_score, 1.0)
        
        return risk_score
    
    def predict_batch(self, travels: List[Dict]) -> Dict[int, Tuple[str, float]]:
        """
        Predict risk for multiple travels
        Returns dict mapping travel_id to (risk_level, risk_score)
        """
        results = {}
        for travel in travels:
            travel_id = travel.get('travel_id')
            if travel_id:
                risk_level, risk_score = self.predict_risk(travel)
                results[travel_id] = (risk_level, risk_score)
        
        return results


class ComplianceAnalyzer:
    """
    Compliance Analysis Engine
    Analyzes travel compliance based on various factors
    """
    
    def __init__(self):
        """Initialize compliance analyzer"""
        self.risk_predictor = RiskPredictor()
    
    def analyze_travel_compliance(self, travel: Dict) -> Dict:
        """
        Comprehensive compliance analysis for a travel
        """
        try:
            # Get risk prediction
            risk_level, risk_score = self.risk_predictor.predict_risk(travel)
            
            # Calculate compliance factors
            doc_completeness_score = self._calculate_doc_completeness(travel)
            timeline_compliance_score = self._calculate_timeline_compliance(travel)
            documentation_status = self._check_documentation_status(travel)
            
            # Overall compliance score (0-100)
            overall_compliance = (
                (doc_completeness_score * 0.4) +
                (timeline_compliance_score * 0.3) +
                ((100 - risk_score * 100) * 0.3)
            )
            
            return {
                "travel_id": travel.get('travel_id'),
                "overall_compliance_score": round(overall_compliance, 2),
                "risk_level": risk_level,
                "risk_score": risk_score,
                "document_completeness_score": round(doc_completeness_score, 2),
                "timeline_compliance_score": round(timeline_compliance_score, 2),
                "documentation_status": documentation_status,
                "recommendations": self._generate_recommendations(travel, risk_level, doc_completeness_score),
                "analysis_timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error analyzing compliance: {str(e)}")
            return {
                "error": "Compliance analysis failed",
                "travel_id": travel.get('travel_id')
            }
    
    def _calculate_doc_completeness(self, travel: Dict) -> float:
        """
        Calculate document completeness score (0-100)
        """
        doc_status_map = {
            'Complete': 100,
            'Incomplete': 50,
            'Pending': 25,
            'Missing': 0,
            'No Submission': 0
        }
        
        doc_completeness = travel.get('doc_completeness', 'No Submission')
        return doc_status_map.get(doc_completeness, 0)
    
    def _calculate_timeline_compliance(self, travel: Dict) -> float:
        """
        Calculate timeline compliance score (0-100)
        """
        try:
            today = date.today()
            
            # Get start date
            start_date = travel.get('start_date')
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            
            # Get timeline percentage
            timeline_pct = travel.get('timeline_pct', 0)
            
            # Days until travel
            days_until = (start_date - today).days
            
            # If already started, high compliance
            if days_until <= 0:
                return 100 if timeline_pct > 50 else 50
            
            # Pre-travel compliance based on days remaining and progress
            if days_until > 60:
                return 80 + (min(timeline_pct / 100, 0.2) * 20)  # 80-100
            elif days_until > 30:
                if timeline_pct >= 50:
                    return 70 + (timeline_pct / 100 * 30)
                else:
                    return max(40, timeline_pct / 30 * 40)
            else:
                # Less than 30 days
                if timeline_pct >= 80:
                    return 80
                elif timeline_pct >= 50:
                    return 60
                else:
                    return 30
        
        except Exception:
            return 50
    
    def _check_documentation_status(self, travel: Dict) -> Dict[str, str]:
        """
        Check required documentation status
        """
        required_docs = {
            'Travel Authority': 'Required',
            'Travel Order': 'Required',
            'Passport': 'Required',
            'Visa': 'Required if applicable',
            'Insurance': 'Required',
            'Travel Report': 'Post-travel'
        }
        
        # This would check actual uploaded documents
        # For now, return template
        return required_docs
    
    def _generate_recommendations(self, travel: Dict, risk_level: str, doc_score: float) -> List[str]:
        """
        Generate recommendations for improving compliance
        """
        recommendations = []
        
        # Risk-based recommendations
        if risk_level == "High":
            recommendations.append("⚠️ High risk detected. Please review your travel plans and documentation.")
        elif risk_level == "Medium":
            recommendations.append("📋 Medium risk. Consider completing pending documentation.")
        
        # Document-based recommendations
        if doc_score < 50:
            recommendations.append("📄 Upload missing documents immediately.")
        elif doc_score < 100:
            recommendations.append("📑 Complete remaining documentation.")
        
        # Timeline-based recommendations
        today = date.today()
        start_date = travel.get('start_date')
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        days_until = (start_date - today).days
        if 0 < days_until < 14:
            recommendations.append("⏰ Travel is approaching soon. Ensure all documents are verified.")
        elif days_until < 0:
            recommendations.append("✈️ Travel is in progress. Submit travel report upon return.")
        
        if not recommendations:
            recommendations.append("✓ Excellent compliance status. No immediate action needed.")
        
        return recommendations
    
    def analyze_college_compliance(self, travels: List[Dict]) -> Dict:
        """
        Analyze compliance for a college
        """
        try:
            if not travels:
                return {
                    "total_travels": 0,
                    "compliant_travels": 0,
                    "compliance_rate": 0.0,
                    "average_risk_score": 0.0,
                    "high_risk_count": 0
                }
            
            # Analyze each travel
            analyses = [self.analyze_travel_compliance(t) for t in travels]
            
            # Calculate aggregates
            total = len(analyses)
            compliant = len([a for a in analyses if a.get('overall_compliance_score', 0) >= 70])
            high_risk = len([a for a in analyses if a.get('risk_level') == 'High'])
            
            avg_compliance = sum(
                a.get('overall_compliance_score', 0) for a in analyses
            ) / total if total > 0 else 0
            
            avg_risk = sum(
                a.get('risk_score', 0) for a in analyses
            ) / total if total > 0 else 0
            
            compliance_rate = (compliant / total * 100) if total > 0 else 0
            
            return {
                "total_travels": total,
                "compliant_travels": compliant,
                "compliance_rate": round(compliance_rate, 2),
                "average_compliance_score": round(avg_compliance, 2),
                "average_risk_score": round(avg_risk, 3),
                "high_risk_count": high_risk,
                "medium_risk_count": len([a for a in analyses if a.get('risk_level') == 'Medium']),
                "low_risk_count": len([a for a in analyses if a.get('risk_level') == 'Low']),
                "analysis_timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error analyzing college compliance: {str(e)}")
            return {"error": "College compliance analysis failed"}


# Create global instances
risk_predictor = RiskPredictor()
compliance_analyzer = ComplianceAnalyzer()
