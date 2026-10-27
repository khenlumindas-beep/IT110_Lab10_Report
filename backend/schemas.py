"""
Pydantic Schemas for Request/Response Validation
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Literal
from datetime import date, datetime
from decimal import Decimal
from constants import (
    MOBILITY_TYPES, MOBILITY_DURATIONS, FOLLOW_UP_STATUSES,
    PRE_TRAVEL_STATUSES, POST_TRAVEL_STATUSES, FUNDING_TYPES,
    TRAVEL_WORKFLOW_STATUSES, DOCUMENT_STATUSES,
    compute_mobility_duration
)

# ==================== Authentication Schemas ====================

class LoginRequest(BaseModel):
    """Login request schema"""
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    """Token response schema"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenRefreshRequest(BaseModel):
    """Token refresh request schema"""
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    """Change password request schema"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

# ==================== User Schemas ====================

class UserBase(BaseModel):
    """Base user schema"""
    full_name: str
    email: EmailStr
    role: str = Field(default="faculty")
    designation: Optional[str] = None
    academic_rank: Optional[str] = None
    contact_number: Optional[str] = None
    college_id: Optional[int] = None
    department_id: Optional[int] = None

class UserCreate(UserBase):
    """User creation schema"""
    password: str

class UserResponse(UserBase):
    """User response schema"""
    user_id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserProfileResponse(UserResponse):
    """User profile response with full details"""
    college: Optional['CollegeResponse'] = None
    department: Optional['DepartmentResponse'] = None
    
    class Config:
        from_attributes = True

# ==================== College Schemas ====================

class CollegeBase(BaseModel):
    """Base college schema"""
    code: str
    name: str
    dean_name: Optional[str] = None

class CollegeCreate(CollegeBase):
    pass

class CollegeResponse(CollegeBase):
    """College response schema"""
    college_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# ==================== Department Schemas ====================

class DepartmentBase(BaseModel):
    """Base department schema"""
    code: str
    name: str
    college_id: int

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentResponse(DepartmentBase):
    """Department response schema"""
    department_id: int
    
    class Config:
        from_attributes = True

# ==================== Travel Schemas ====================

MobilityType = Literal[tuple(MOBILITY_TYPES)]
MobilityDuration = Literal[tuple(MOBILITY_DURATIONS)]
FundingType = Literal[tuple(FUNDING_TYPES)]
FollowUpStatus = Literal[tuple(FOLLOW_UP_STATUSES)]
PreTravelStatus = Literal[tuple(PRE_TRAVEL_STATUSES)]
PostTravelStatus = Literal[tuple(POST_TRAVEL_STATUSES)]
WorkflowStatus = Literal[tuple(TRAVEL_WORKFLOW_STATUSES)]
DocumentStatus = Literal[tuple(DOCUMENT_STATUSES)]

class TravelBase(BaseModel):
    """Base travel schema"""
    event_title: str
    mobility_type: MobilityType
    participant_type: Literal['Faculty', 'Student'] = 'Faculty'
    participant_name: Optional[str] = None
    student_id_no: Optional[str] = None
    program: Optional[str] = None
    role_in_event: Optional[str] = None
    start_date: date
    end_date: date
    location: Optional[str] = None
    country: Optional[str] = None
    funding_type: FundingType = "To Be Determined"
    mobility_duration: Optional[MobilityDuration] = None
    movs: Optional[str] = None
    pre_travel_status: Optional[PreTravelStatus] = None
    post_travel_status: Optional[PostTravelStatus] = None
    follow_up: Optional[FollowUpStatus] = None
    remarks: Optional[str] = None

    @field_validator('end_date')
    @classmethod
    def end_date_not_before_start(cls, v, info):
        data = info.data
        if 'start_date' in data and v < data['start_date']:
            raise ValueError('end_date must be on or after start_date')
        return v

    @field_validator('participant_name')
    @classmethod
    def student_requires_name(cls, v, info):
        data = info.data
        if data.get('participant_type') == 'Student' and not (v and v.strip()):
            raise ValueError('participant_name is required for Student participants')
        return v

class TravelCreate(TravelBase):
    """Travel creation schema"""
    college_id: int
    department_id: Optional[int] = None

class TravelUpdate(BaseModel):
    """Travel update schema"""
    event_title: Optional[str] = None
    mobility_type: Optional[MobilityType] = None
    participant_type: Optional[Literal['Faculty', 'Student']] = None
    participant_name: Optional[str] = None
    student_id_no: Optional[str] = None
    program: Optional[str] = None
    role_in_event: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    location: Optional[str] = None
    country: Optional[str] = None
    funding_type: Optional[FundingType] = None
    timeline_status: Optional[str] = None
    mobility_duration: Optional[MobilityDuration] = None
    movs: Optional[str] = None
    pre_travel_status: Optional[PreTravelStatus] = None
    post_travel_status: Optional[PostTravelStatus] = None
    follow_up: Optional[FollowUpStatus] = None
    remarks: Optional[str] = None

class WorkflowUpdate(BaseModel):
    """Admin travel workflow status change"""
    workflow_status: WorkflowStatus
    remarks: Optional[str] = None

class TravelResponse(TravelBase):
    """Travel response schema"""
    travel_id: int
    user_id: int
    college_id: int
    timeline_pct: Decimal
    timeline_status: str
    workflow_status: str
    doc_completeness: str
    risk_flag: str
    risk_score: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class TravelDetailResponse(TravelResponse):
    """Travel with related details"""
    user: Optional[UserResponse] = None
    college: Optional[CollegeResponse] = None
    documents: List['DocumentResponse'] = []
    
    class Config:
        from_attributes = True

# ==================== Document Schemas ====================

class DocumentBase(BaseModel):
    """Base document schema"""
    doc_type: str
    doc_category: Optional[str] = None

class DocumentCreate(DocumentBase):
    """Document creation schema"""
    travel_id: int

class DocumentResponse(DocumentBase):
    """Document response schema"""
    document_id: int
    travel_id: int
    file_name: Optional[str] = None
    file_path: str
    file_size: Optional[int] = None
    status: str
    remarks: Optional[str] = None
    uploaded_at: datetime
    
    class Config:
        from_attributes = True

class DocumentRejectRequest(BaseModel):
    """Admin document rejection with reason"""
    remarks: str = Field(..., min_length=1, max_length=1000)

# ==================== Notification Schemas ====================

class NotificationResponse(BaseModel):
    """Notification response schema"""
    notification_id: int
    user_id: int
    travel_id: Optional[int] = None
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# ==================== Analytics Schemas ====================

class TravelStatistics(BaseModel):
    """Travel statistics schema"""
    total_travels: int
    completed_travels: int
    ongoing_travels: int
    upcoming_travels: int
    compliance_rate: float
    average_duration_days: float

class CollegeMobilityStats(BaseModel):
    """College mobility statistics"""
    college_id: int
    college_name: str
    total_travels: int
    total_faculty: int
    countries_visited: int
    total_funding: Decimal
    compliance_rate: float

class RiskAnalysis(BaseModel):
    """Risk analysis schema"""
    total_travels: int
    high_risk: int
    medium_risk: int
    low_risk: int
    high_risk_percentage: float
    medium_risk_percentage: float
    low_risk_percentage: float

# ==================== Dashboard Schemas ====================

class FacultyDashboard(BaseModel):
    """Faculty dashboard schema"""
    user: UserProfileResponse
    travel_statistics: TravelStatistics
    recent_travels: List[TravelResponse] = []
    pending_documents: int
    notifications: List[NotificationResponse] = []

class AdminDashboard(BaseModel):
    """Admin dashboard schema"""
    total_travels: int
    total_users: int
    total_colleges: int
    compliance_rate: float
    college_stats: List[CollegeMobilityStats] = []
    risk_analysis: RiskAnalysis
    recent_activities: List[dict] = []

# ==================== SIAP Schemas ====================

SiapStatus = Literal['Not Started', 'Started', 'Ongoing', 'Completed']

class SiapBase(BaseModel):
    """Base SIAP internship schema"""
    student_name: str
    student_id_no: Optional[str] = None
    email: Optional[EmailStr] = None
    college_id: int
    program: Optional[str] = None
    major: Optional[str] = None
    fhe_name: Optional[str] = None
    fhe_address: Optional[str] = None
    departure_date: Optional[date] = None
    arrival_ph_date: Optional[date] = None
    flight_details: Optional[str] = None
    status: SiapStatus = 'Not Started'
    internship_start: Optional[date] = None
    internship_end: Optional[date] = None
    milestone: Optional[str] = None
    notes: Optional[str] = None

class SiapCreate(SiapBase):
    pass

class SiapUpdate(BaseModel):
    student_name: Optional[str] = None
    student_id_no: Optional[str] = None
    email: Optional[EmailStr] = None
    college_id: Optional[int] = None
    program: Optional[str] = None
    major: Optional[str] = None
    fhe_name: Optional[str] = None
    fhe_address: Optional[str] = None
    departure_date: Optional[date] = None
    arrival_ph_date: Optional[date] = None
    flight_details: Optional[str] = None
    status: Optional[SiapStatus] = None
    internship_start: Optional[date] = None
    internship_end: Optional[date] = None
    milestone: Optional[str] = None
    notes: Optional[str] = None

class SiapResponse(SiapBase):
    internship_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== Mobility Plan Schemas ====================

ReadinessStatus = Literal['Interested', 'Preparing', 'Ready']

class MobilityPlanBase(BaseModel):
    """Faculty mobility plan - interest in future international mobility"""
    preferred_mobility_types: Optional[str] = None
    target_country: Optional[str] = None
    preferred_period: Optional[str] = None
    funding_needed: bool = True
    funding_type: Optional[FundingType] = None
    readiness_status: ReadinessStatus = 'Interested'
    notes: Optional[str] = None

class MobilityPlanCreate(MobilityPlanBase):
    pass

class MobilityPlanUpdate(BaseModel):
    preferred_mobility_types: Optional[str] = None
    target_country: Optional[str] = None
    preferred_period: Optional[str] = None
    funding_needed: Optional[bool] = None
    funding_type: Optional[FundingType] = None
    readiness_status: Optional[ReadinessStatus] = None
    notes: Optional[str] = None

class MobilityPlanResponse(MobilityPlanBase):
    plan_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class MobilityPlanDetailResponse(MobilityPlanResponse):
    user: Optional[UserResponse] = None
    
    class Config:
        from_attributes = True

# ==================== Document Type Schemas ====================

class DocumentTypeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: Literal['Pre-Travel', 'Post-Travel']
    is_required: bool = True
    description: Optional[str] = None
    sort_order: int = 0

class DocumentTypeCreate(DocumentTypeBase):
    pass

class DocumentTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[Literal['Pre-Travel', 'Post-Travel']] = None
    is_required: Optional[bool] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None

class DocumentTypeResponse(DocumentTypeBase):
    doc_type_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ==================== Phase 3: Post-Travel, Re-Entry, Compliance Schemas ====================

PostTravelStatusLiteral = Literal['Not Submitted', 'Submitted', 'Verified', 'Incomplete', 'Waived']
ReentryStatusLiteral = Literal['Not Started', 'For Implementation', 'Ongoing', 'Completed', 'Not Complied']
ComplianceStatusLiteral = Literal['Fully Compliant', 'Partially Compliant', 'Needs Action']
CompliancePriorityLiteral = Literal['low', 'medium', 'high']

class PostTravelRequirementBase(BaseModel):
    requirement: str = Field(..., min_length=1, max_length=150)
    doc_type_id: Optional[int] = None
    due_date: Optional[date] = None

class PostTravelRequirementCreate(PostTravelRequirementBase):
    pass

class PostTravelRequirementUpdate(BaseModel):
    requirement: Optional[str] = Field(None, min_length=1, max_length=150)
    status: Optional[PostTravelStatusLiteral] = None
    due_date: Optional[date] = None
    remarks: Optional[str] = None

class PostTravelRequirementResponse(PostTravelRequirementBase):
    requirement_id: int
    travel_id: int
    status: PostTravelStatusLiteral
    evidence_path: Optional[str] = None
    completed_at: Optional[datetime] = None
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ReentryActivityBase(BaseModel):
    activity: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    target_date: Optional[date] = None

class ReentryActivityCreate(ReentryActivityBase):
    pass

class ReentryActivityUpdate(BaseModel):
    activity: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ReentryStatusLiteral] = None
    target_date: Optional[date] = None
    remarks: Optional[str] = None

class ReentryActivityResponse(ReentryActivityBase):
    activity_id: int
    travel_id: int
    status: ReentryStatusLiteral
    evidence_path: Optional[str] = None
    completed_at: Optional[datetime] = None
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ComplianceRecordResponse(BaseModel):
    compliance_id: int
    travel_id: int
    status: ComplianceStatusLiteral
    score: Decimal
    pre_travel_ok: bool
    post_travel_ok: bool
    reentry_ok: bool
    required_docs: int
    verified_docs: int
    priority: CompliancePriorityLiteral
    computed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class TravelLimitCheck(BaseModel):
    faculty_user_id: int
    year: int
    travel_count: int
    limit: int
    exceeded: bool

# ==================== Requirement Checklists Schemas ====================

class RequirementItemResponse(BaseModel):
    requirement_id: int
    applies_to: str
    phase: str
    name: str
    parent_id: Optional[int] = None
    is_required: bool
    condition_text: Optional[str] = None
    display_text: Optional[str] = None
    has_template: bool
    template_key: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True

class RequirementTravelItem(BaseModel):
    requirement_id: int
    name: str
    phase: str
    parent_id: Optional[int] = None
    is_required: bool
    condition_text: Optional[str] = None
    display_text: Optional[str] = None
    has_template: bool
    template_key: Optional[str] = None
    sort_order: int
    status: str
    document_id: Optional[int] = None
    file_name: Optional[str] = None

class RequirementTravelStatus(BaseModel):
    travel_id: int
    participant_type: str
    items: list[RequirementTravelItem]
    required_total: int
    verified_required: int
    percent: float
    complete: bool
    checklist_files: list[str]

# Update forward references
UserProfileResponse.model_rebuild()
TravelDetailResponse.model_rebuild()
MobilityPlanDetailResponse.model_rebuild()
