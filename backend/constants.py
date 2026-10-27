"""
Shared domain vocabularies for SmartTrack
Aligned to the CSUCC Foreign Mobility Monitoring System workbook (Tasks sheet)
"""
from datetime import date

# Task 1: "Activity Type" -> "Type of Mobility" (11 official values + Other)
MOBILITY_TYPES = [
    "Faculty Exchange",
    "Teaching Mobility",
    "Research Mobility",
    "International Training",
    "International Conference",
    "Visiting Professorship/Scholarship",
    "Fellowship",
    "Short-Term Study Program",
    "International Collaborative Research",
    "International Community Extension Engagement",
    "International Benchmarking",
    "Other",
]

# Task 7: Mobility Duration categories
MOBILITY_DURATIONS = [
    "Short-Term",
    "Medium-Term",
    "Long-Term",
    "One Academic Term/Semester",
    "One Academic Year",
]

# Task 5: Type of Funding Support
FUNDING_TYPES = [
    "Fully Funded",
    "Partially Funded",
    "Self-Funded",
    "No Funding Required",
    "To Be Determined",
]

# Follow Up status (workbook vocabulary)
FOLLOW_UP_STATUSES = ["Done", "Not Yet", "Ongoing"]

# Timeline status
TIMELINE_STATUSES = ["Upcoming", "Ongoing", "Completed", "Cancelled"]

# Travel workflow status (design doc, p19 - 8 states, + Pending Requirements gate)
TRAVEL_WORKFLOW_STATUSES = [
    "Pending Requirements",
    "Draft",
    "Submitted",
    "Under Review",
    "Incomplete",
    "Approved",
    "Ongoing",
    "Completed",
    "Cancelled",
]

# Allowed workflow transitions (source -> targets)
TRAVEL_WORKFLOW_TRANSITIONS = {
    "Pending Requirements": ["Draft", "Submitted", "Cancelled"],
    "Draft": ["Pending Requirements", "Submitted", "Cancelled"],
    "Submitted": ["Under Review", "Cancelled"],
    "Under Review": ["Incomplete", "Approved", "Cancelled"],
    "Incomplete": ["Submitted", "Cancelled"],
    "Approved": ["Ongoing", "Cancelled"],
    "Ongoing": ["Completed", "Cancelled"],
    "Completed": [],
    "Cancelled": [],
}

# Travels only reach Approved once the pre-travel checklist passes the gate.
WORKFLOW_REQUIRES_PRE_TRAVEL_GATE = {"Approved"}

# Document lifecycle status (design doc, p19 - 6 states)
DOCUMENT_STATUSES = [
    "Not Uploaded",
    "Submitted",
    "Under Verification",
    "Verified",
    "Rejected",
    "Resubmission Required",
]

# Pre-Travel / Post-Travel document status (workbook 2026 sheet vocabulary)
PRE_TRAVEL_STATUSES = [
    "Not Requested",
    "Requested",
    "Ongoing",
    "Complete Documents",
    "Incomplete Documents",
    "No Submission",
]
POST_TRAVEL_STATUSES = [
    "Not Submitted",
    "Submitted Travel Report",
    "Incomplete Documents",
    "Ongoing",
]


def compute_mobility_duration(start: date, end: date) -> str:
    """Derive the Mobility Duration category from travel dates (Task 7)."""
    if start is None or end is None or end < start:
        return "Short-Term"
    days = (end - start).days + 1  # inclusive of both dates
    if days <= 30:
        return "Short-Term"
    if days <= 183:  # up to ~6 months
        return "Medium-Term"
    if days <= 366:  # up to ~1 academic year
        return "Long-Term"
    return "One Academic Year"
