"""
Action Executors - Do the actual work.

Each executor handles a specific capability (D1, D2, etc.)
"""

from .base import (
    BaseExecutor,
    ActionResult,
    ActionStatus,
    ValidationResult,
    CompositeExecutor,
    ParallelExecutor,
)

from .sdr import (
    D1_ResearchCompany,
    D2_WriteColdEmail,
    D4_LinkedInSearch,
    D5_BuildLeadList,
    D7_QualifyLead,
    D9_SocialSelling,
    D10_FBAdsExtraction,
    SDR_EXECUTORS,
    get_sdr_executor,
)

from .admin import (
    A1_EmailTriage,
    A2_ScheduleMeeting,
    A3_MeetingPrep,
    A4_CreateDocument,
    A5_DataEntry,
    A6_FieldExtractor,
    A7_SOPBuilder,
    A8_GenerateReport,
    ADMIN_EXECUTORS,
    get_admin_executor,
)

from .business import (
    E1_AmazonProductResearch,
    H1_ShipmentTracker,
    M1_WikipediaResearch,
    O1_StackOverflowSearch,
    F1_ZillowPropertySearch,
    L1_LinkedInProfileSearch,
    BUSINESS_EXECUTORS,
    get_business_executor,
)

from .workflows_a_to_o import (
    A1_EmailInbox,
    B1_SpreadsheetCleaner,
    C1_TicketClassifier,
    D1_CompanyResearch,
    G1_ContractExtractor,
    I1_MaintenanceAnalyzer,
    J1_TransactionCategorizer,
    K1_AnalyticsInsights,
    N1_FormExtractor,
    WORKFLOW_EXECUTORS,
    get_workflow_executor,
)

from .protection import (
    P1_CaptchaSolver,
    P2_CloudflareHandler,
    P3_StealthMode,
    PROTECTION_EXECUTORS,
    get_protection_executor,
)

# Combined registry of all executors
ALL_EXECUTORS = {**SDR_EXECUTORS, **ADMIN_EXECUTORS, **BUSINESS_EXECUTORS, **WORKFLOW_EXECUTORS, **PROTECTION_EXECUTORS}

__all__ = [
    # Base
    "BaseExecutor",
    "ActionResult",
    "ActionStatus",
    "ValidationResult",
    "CompositeExecutor",
    "ParallelExecutor",
    # SDR
    "D1_ResearchCompany",
    "D2_WriteColdEmail",
    "D4_LinkedInSearch",
    "D5_BuildLeadList",
    "D7_QualifyLead",
    "D9_SocialSelling",
    "D10_FBAdsExtraction",
    "SDR_EXECUTORS",
    "get_sdr_executor",
    # Admin
    "A1_EmailTriage",
    "A2_ScheduleMeeting",
    "A3_MeetingPrep",
    "A4_CreateDocument",
    "A5_DataEntry",
    "A6_FieldExtractor",
    "A7_SOPBuilder",
    "A8_GenerateReport",
    "ADMIN_EXECUTORS",
    "get_admin_executor",
    # Business
    "E1_AmazonProductResearch",
    "H1_ShipmentTracker",
    "M1_WikipediaResearch",
    "O1_StackOverflowSearch",
    "F1_ZillowPropertySearch",
    "L1_LinkedInProfileSearch",
    "BUSINESS_EXECUTORS",
    "get_business_executor",
    # Workflows
    "A1_EmailInbox",
    "B1_SpreadsheetCleaner",
    "C1_TicketClassifier",
    "D1_CompanyResearch",
    "G1_ContractExtractor",
    "I1_MaintenanceAnalyzer",
    "J1_TransactionCategorizer",
    "K1_AnalyticsInsights",
    "N1_FormExtractor",
    "WORKFLOW_EXECUTORS",
    "get_workflow_executor",
    # Protection
    "P1_CaptchaSolver",
    "P2_CloudflareHandler",
    "P3_StealthMode",
    "PROTECTION_EXECUTORS",
    "get_protection_executor",
    # Combined
    "ALL_EXECUTORS",
]
