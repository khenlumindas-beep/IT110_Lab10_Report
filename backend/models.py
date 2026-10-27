"""
SQLAlchemy Models for SmartTrack Database
Defines all database table structures
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, 
    ForeignKey, Text, Numeric, Date, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class College(Base):
    """College Model"""
    __tablename__ = "colleges"
    __table_args__ = {'schema': 'system_core'}
    
    college_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    dean_name = Column(String(150))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    departments = relationship("Department", back_populates="college", cascade="all, delete-orphan")
    users = relationship("User", back_populates="college")
    travels = relationship("Travel", back_populates="college")

class Department(Base):
    """Department Model"""
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint('college_id', 'code', name='unique_dept_per_college'),
        {'schema': 'system_core'}
    )
    
    department_id = Column(Integer, primary_key=True, autoincrement=True)
    college_id = Column(Integer, ForeignKey('system_core.colleges.college_id'), nullable=False)
    code = Column(String(50), nullable=False)
    name = Column(String(255))
    
    # Relationships
    college = relationship("College", back_populates="departments")
    users = relationship("User", back_populates="department")
    travels = relationship("Travel", back_populates="department")

class User(Base):
    """User Model (Faculty and Super Admin)"""
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('super_admin','faculty')", name='users_role_check'),
        {'schema': 'system_core'}
    )
    
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='faculty')
    college_id = Column(Integer, ForeignKey('system_core.colleges.college_id'))
    department_id = Column(Integer, ForeignKey('system_core.departments.department_id'))
    designation = Column(String(150))
    academic_rank = Column(String(100))
    contact_number = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    college = relationship("College", back_populates="users")
    department = relationship("Department", back_populates="users")
    travels = relationship("Travel", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="verified_by_user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

class Travel(Base):
    """Travel Record Model"""
    __tablename__ = "travels"
    __table_args__ = (
        CheckConstraint(
            "mobility_type IN ('Faculty Exchange','Teaching Mobility','Research Mobility',"
            "'International Training','International Conference','Visiting Professorship/Scholarship',"
            "'Fellowship','Short-Term Study Program','International Collaborative Research',"
            "'International Community Extension Engagement','International Benchmarking','Other')",
            name='chk_mobility_type'
        ),
        CheckConstraint(
            "follow_up IS NULL OR follow_up IN ('Done','Not Yet','Ongoing')",
            name='chk_follow_up'
        ),
        CheckConstraint(
            "mobility_duration IS NULL OR mobility_duration IN "
            "('Short-Term','Medium-Term','Long-Term','One Academic Term/Semester','One Academic Year')",
            name='chk_mobility_duration'
        ),
        CheckConstraint(
            "participant_type IN ('Faculty','Student')",
            name='chk_participant_type'
        ),
        CheckConstraint(
            "funding_type IS NULL OR funding_type IN "
            "('Fully Funded','Partially Funded','Self-Funded','No Funding Required','To Be Determined')",
            name='chk_funding_type'
        ),
        CheckConstraint(
            "pre_travel_status IS NULL OR pre_travel_status IN "
            "('Not Requested','Requested','Ongoing','Complete Documents','Incomplete Documents','No Submission')",
            name='chk_pre_travel_status'
        ),
        CheckConstraint(
            "post_travel_status IS NULL OR post_travel_status IN "
            "('Not Submitted','Submitted Travel Report','Incomplete Documents','Ongoing')",
            name='chk_post_travel_status'
        ),
        CheckConstraint(
            "workflow_status IS NULL OR workflow_status IN "
            "('Pending Requirements','Draft','Submitted','Under Review','Incomplete','Approved','Ongoing','Completed','Cancelled')",
            name='chk_workflow_status'
        ),
        {'schema': 'system_core'}
    )
    
    travel_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('system_core.users.user_id'), nullable=False,
                     comment="Record owner (faculty/admin who registered the mobility)")
    college_id = Column(Integer, ForeignKey('system_core.colleges.college_id'), nullable=False)
    department_id = Column(Integer, ForeignKey('system_core.departments.department_id'))
    participant_type = Column(String(20), nullable=False, default='Faculty',
                              comment="Faculty or Student (students have no login account)")
    participant_name = Column(String(150),
                              comment="Required for Student participants; display override for faculty")
    student_id_no = Column(String(50),
                           comment="Student ID number (student participants only)")
    program = Column(String(150),
                     comment="Degree program e.g. BSTM (student participants only)")
    event_title = Column(String(500), nullable=False)
    mobility_type = Column(String(100), nullable=False)
    role_in_event = Column(String(150))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    location = Column(String(300))
    country = Column(String(100))
    funding_type = Column(String(50), default='To Be Determined')
    timeline_pct = Column(Numeric(5, 2), default=0)
    timeline_status = Column(String(20), default='Upcoming')
    workflow_status = Column(String(20), default='Pending Requirements',
                             comment="Design-doc travel workflow (Pending Requirements..Completed)")
    mobility_duration = Column(String(50))
    movs = Column(Text, comment="Means of Verification (workbook MOVs column)")
    pre_travel_status = Column(String(50),
                              comment="Workbook Pre-Travel Documents status")
    post_travel_status = Column(String(50),
                               comment="Workbook Post-Travel Documents status")
    doc_completeness = Column(String(50), default='No Submission')
    risk_flag = Column(String(20), default='Medium')
    risk_score = Column(Numeric(5, 3), default=0.5)
    follow_up = Column(String(255))
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="travels")
    college = relationship("College", back_populates="travels")
    department = relationship("Department", back_populates="travels")
    documents = relationship("Document", back_populates="travel", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="travel", cascade="all, delete-orphan")
    post_travel_requirements = relationship("PostTravelRequirement", back_populates="travel", cascade="all, delete-orphan")
    reentry_activities = relationship("ReentryActivity", back_populates="travel", cascade="all, delete-orphan")
    compliance_record = relationship("ComplianceRecord", back_populates="travel", uselist=False, cascade="all, delete-orphan")
    remark_history = relationship("RemarkHistory", back_populates="travel", cascade="all, delete-orphan")

class Document(Base):
    """Document Model"""
    __tablename__ = "documents"
    __table_args__ = {'schema': 'system_core'}
    
    document_id = Column(Integer, primary_key=True, autoincrement=True)
    travel_id = Column(Integer, ForeignKey('system_core.travels.travel_id'), nullable=False)
    doc_type = Column(String(100), nullable=False)
    doc_category = Column(String(50))  # Pre-Travel, Post-Travel
    file_name = Column(String(255))
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    status = Column(String(50), default='Pending')
    remarks = Column(Text, comment="Verification remarks / rejection reason")
    verified_by = Column(Integer, ForeignKey('system_core.users.user_id'))
    verified_at = Column(DateTime)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    travel = relationship("Travel", back_populates="documents")
    verified_by_user = relationship("User", foreign_keys=[verified_by], back_populates="documents")
    remark_history = relationship("RemarkHistory", back_populates="document")
    ai_analyses = relationship("AIDocumentAnalysis", back_populates="document", cascade="all, delete-orphan")

class Notification(Base):
    """Notification Model"""
    __tablename__ = "notifications"
    __table_args__ = {'schema': 'system_core'}
    
    notification_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('system_core.users.user_id'), nullable=False)
    travel_id = Column(Integer, ForeignKey('system_core.travels.travel_id'))
    title = Column(String(255))
    message = Column(Text)
    type = Column(String(50), default='info')
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="notifications")
    travel = relationship("Travel", back_populates="notifications")

class Announcement(Base):
    """Announcement Model"""
    __tablename__ = "announcements"
    __table_args__ = {'schema': 'system_core'}
    
    announcement_id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey('system_core.users.user_id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class SiapInternship(Base):
    """Student Internship Abroad Program (SIAP) - admin-managed, students have no login"""
    __tablename__ = "siap_internships"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Not Started','Started','Ongoing','Completed')",
            name='chk_siap_status'
        ),
        {'schema': 'system_core'}
    )
    
    internship_id = Column(Integer, primary_key=True, autoincrement=True)
    student_name = Column(String(150), nullable=False)
    student_id_no = Column(String(50))
    email = Column(String(150))
    college_id = Column(Integer, ForeignKey('system_core.colleges.college_id'), nullable=False)
    program = Column(String(150))
    major = Column(String(150))
    fhe_name = Column(String(255), comment="Foreign Host Establishment")
    fhe_address = Column(String(300))
    departure_date = Column(Date)
    arrival_ph_date = Column(Date, comment="Arrival back in the Philippines")
    flight_details = Column(Text)
    status = Column(String(30), default='Not Started')
    internship_start = Column(Date)
    internship_end = Column(Date)
    milestone = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    college = relationship("College")

class MobilityPlan(Base):
    """International Faculty Mobility Plan - faculty interest/readiness for future mobility"""
    __tablename__ = "mobility_plans"
    __table_args__ = (
        UniqueConstraint('user_id', name='unique_plan_per_faculty'),
        CheckConstraint(
            "readiness_status IN ('Interested','Preparing','Ready')",
            name='chk_readiness_status'
        ),
        {'schema': 'system_core'}
    )
    
    plan_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('system_core.users.user_id'), nullable=False)
    preferred_mobility_types = Column(Text, comment="Comma-separated Type of Mobility values of interest")
    target_country = Column(String(100))
    preferred_period = Column(String(150), comment="e.g. AY 2026-2027, 1st Semester")
    funding_needed = Column(Boolean, default=True)
    funding_type = Column(String(50))
    readiness_status = Column(String(20), default='Interested')
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User")

class DocumentType(Base):
    """Admin-managed master list of required travel documents"""
    __tablename__ = "document_types"
    __table_args__ = (
        CheckConstraint(
            "category IN ('Pre-Travel','Post-Travel')",
            name='chk_doc_type_category'
        ),
        {'schema': 'system_core'}
    )

    doc_type_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    category = Column(String(20), nullable=False, default='Pre-Travel')
    is_required = Column(Boolean, default=True)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ==================== Phase 2: Post-Travel, Re-Entry, Compliance ====================

class PostTravelRequirement(Base):
    """Per-travel post-travel deliverable checklist (BR-05)."""
    __tablename__ = "post_travel_requirements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Not Submitted','Submitted','Verified','Incomplete','Waived')",
            name='chk_post_travel_req_status'
        ),
        {'schema': 'system_core'}
    )

    requirement_id = Column(Integer, primary_key=True, autoincrement=True)
    travel_id = Column(Integer, ForeignKey('system_core.travels.travel_id', ondelete='CASCADE'), nullable=False)
    doc_type_id = Column(Integer, ForeignKey('system_core.document_types.doc_type_id'))
    requirement = Column(String(150), nullable=False)
    status = Column(String(30), nullable=False, default='Not Submitted')
    evidence_path = Column(String(500))
    due_date = Column(Date)
    completed_at = Column(DateTime)
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    travel = relationship("Travel", back_populates="post_travel_requirements")
    doc_type = relationship("DocumentType")


class ReentryActivity(Base):
    """Knowledge-sharing / re-entry activity plan and evidence (BR-06)."""
    __tablename__ = "reentry_activities"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Not Started','For Implementation','Ongoing','Completed','Not Complied')",
            name='chk_reentry_status'
        ),
        {'schema': 'system_core'}
    )

    activity_id = Column(Integer, primary_key=True, autoincrement=True)
    travel_id = Column(Integer, ForeignKey('system_core.travels.travel_id', ondelete='CASCADE'), nullable=False)
    activity = Column(String(255), nullable=False)
    description = Column(Text)
    target_date = Column(Date)
    status = Column(String(30), nullable=False, default='Not Started')
    evidence_path = Column(String(500))
    completed_at = Column(DateTime)
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    travel = relationship("Travel", back_populates="reentry_activities")


class ComplianceRecord(Base):
    """Calculated compliance state, one row per travel (BR-07)."""
    __tablename__ = "compliance_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Fully Compliant','Partially Compliant','Needs Action')",
            name='chk_compliance_status'
        ),
        CheckConstraint("priority IN ('low','medium','high')", name='chk_compliance_priority'),
        {'schema': 'system_core'}
    )

    compliance_id = Column(Integer, primary_key=True, autoincrement=True)
    travel_id = Column(Integer, ForeignKey('system_core.travels.travel_id', ondelete='CASCADE'), nullable=False, unique=True)
    status = Column(String(30), nullable=False, default='Needs Action')
    score = Column(Numeric(5, 2), default=0)
    pre_travel_ok = Column(Boolean, nullable=False, default=False)
    post_travel_ok = Column(Boolean, nullable=False, default=False)
    reentry_ok = Column(Boolean, nullable=False, default=False)
    required_docs = Column(Integer, nullable=False, default=0)
    verified_docs = Column(Integer, nullable=False, default=0)
    priority = Column(String(10), nullable=False, default='medium')
    computed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    travel = relationship("Travel", back_populates="compliance_record")


# ==================== Phase 2: Audit Structure ====================

class RemarkHistory(Base):
    """Structured compliance notes and status-transition history (BR-10, BR-12)."""
    __tablename__ = "remark_history"
    __table_args__ = (
        CheckConstraint(
            "remark_type IS NULL OR remark_type IN ("
            "'Missing Document','Incorrect Document','Expired','Illegible',"
            "'Missing Signature','Wrong Document Type','Post-Travel Pending',"
            "'Re-entry Overdue','General')",
            name='chk_remark_type'
        ),
        CheckConstraint(
            "action IS NULL OR action IN ("
            "'For Verification','For Resubmission','Follow Up','Approved',"
            "'Rejected','No Further Action','General')",
            name='chk_remark_action'
        ),
        {'schema': 'system_core'}
    )

    remark_id = Column(Integer, primary_key=True, autoincrement=True)
    travel_id = Column(Integer, ForeignKey('system_core.travels.travel_id', ondelete='CASCADE'))
    document_id = Column(Integer, ForeignKey('system_core.documents.document_id', ondelete='SET NULL'))
    admin_id = Column(Integer, ForeignKey('system_core.users.user_id'))
    remark_type = Column(String(50))
    action = Column(String(50))
    affected_requirement = Column(String(100))
    remark_text = Column(Text)
    previous_status = Column(String(30))
    new_status = Column(String(30))
    created_at = Column(DateTime, default=datetime.utcnow)

    travel = relationship("Travel", back_populates="remark_history")
    document = relationship("Document", back_populates="remark_history")
    admin = relationship("User")


class AuditLog(Base):
    """Security and administrative activity history (BR-10, FR-A15)."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('user','travel','document','compliance','reentry',"
            "'post_travel','notification','announcement','system')",
            name='chk_audit_entity'
        ),
        CheckConstraint(
            "action IN ('create','update','delete','login','logout','verify','reject',"
            "'resubmit','approve','return','status_change','deactivate',"
            "'reactivate','export','other')",
            name='chk_audit_action'
        ),
        {'schema': 'system_core'}
    )

    audit_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('system_core.users.user_id'))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer)
    action = Column(String(50), nullable=False)
    description = Column(Text)
    ip_address = Column(String(45))
    user_agent = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


# ==================== Phase 2: AI Staging (Phase 7/8 targets) ====================

class AIDocumentAnalysis(Base):
    """AI document classification / extraction / issue-detection results."""
    __tablename__ = "ai_document_analysis"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','complete','failed','skipped')",
            name='chk_ai_analysis_status'
        ),
        {'schema': 'system_core'}
    )

    analysis_id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('system_core.documents.document_id', ondelete='CASCADE'), nullable=False)
    suggested_type = Column(String(100))
    confidence = Column(Numeric(5, 4))
    extracted_text = Column(Text)
    issues = Column(Text)
    issue_flags = Column(Text)
    status = Column(String(30), nullable=False, default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="ai_analyses")


class AIComplianceInsight(Base):
    """AI-generated compliance summary / priority / suggested remark."""
    __tablename__ = "ai_compliance_insights"
    __table_args__ = (
        CheckConstraint(
            "priority IS NULL OR priority IN ('low','medium','high')",
            name='chk_ai_insight_priority'
        ),
        {'schema': 'system_core'}
    )

    insight_id = Column(Integer, primary_key=True, autoincrement=True)
    travel_id = Column(Integer, ForeignKey('system_core.travels.travel_id', ondelete='CASCADE'))
    insight_type = Column(String(50))
    summary = Column(Text)
    priority = Column(String(10))
    suggested_remark = Column(Text)
    is_accepted = Column(Boolean)
    created_at = Column(DateTime, default=datetime.utcnow)

    travel = relationship("Travel")


class RequirementItem(Base):
    """Official OIGE requirement checklist item (master list per participant type + phase)."""
    __tablename__ = "requirement_items"
    __table_args__ = (
        UniqueConstraint('applies_to', 'phase', 'name', name='uq_req_item'),
        CheckConstraint(
            "applies_to IN ('Faculty', 'Student')",
            name='chk_req_applies_to'
        ),
        CheckConstraint(
            "phase IN ('Pre-Travel', 'Post-Travel')",
            name='chk_req_phase'
        ),
        {'schema': 'system_core'}
    )

    requirement_id = Column(Integer, primary_key=True, autoincrement=True)
    applies_to = Column(String(20), nullable=False)
    phase = Column(String(20), nullable=False)
    name = Column(String(150), nullable=False)
    parent_id = Column(Integer, ForeignKey('system_core.requirement_items.requirement_id'))
    is_required = Column(Boolean, nullable=False, default=True)
    condition_text = Column(String(200))
    display_text = Column(String(400))
    has_template = Column(Boolean, nullable=False, default=False)
    template_key = Column(String(50))
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
