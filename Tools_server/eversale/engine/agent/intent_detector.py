"""
Intent Detector - Smart pattern-based intent classification.

Replaces simple keyword matching with:
1. Regex pattern matching for common request types
2. Entity extraction inline
3. Confidence scoring
4. Multi-intent detection
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class IntentCategory(Enum):
    """High-level intent categories."""
    RESEARCH = "research"
    CREATE = "create"
    SEND = "send"
    UPDATE = "update"
    CHECK = "check"
    BUILD = "build"
    ANALYZE = "analyze"
    SCHEDULE = "schedule"
    DRAFT = "draft"
    FIND = "find"
    UNKNOWN = "unknown"


@dataclass
class ExtractedEntity:
    """An entity extracted from text."""
    type: str  # company, person, email, url, date, amount, industry
    value: str
    confidence: float
    start: int
    end: int


@dataclass
class DetectedIntent:
    """A detected intent with confidence and entities."""
    capability: str  # e.g., "D1", "D2", "A1"
    action: str  # e.g., "research_company", "write_cold_email"
    category: IntentCategory
    confidence: float
    entities: List[ExtractedEntity]
    raw_text: str
    requires_login: List[str]  # Service IDs needed
    parameters: Dict[str, Any]  # Extracted parameters


# Intent patterns: (pattern, capability, action, category, required_services)
INTENT_PATTERNS = [
    # ===== D - SALES/SDR =====
    # D1 - Research prospects (exclude Wikipedia, prices, candidates)
    (r"(?!.*(?:on|from|using)\s+wikipedia)(?!.*prices?\s+(?:on|at))(?!.*candidate\s+(?:on|for))research\s+(?:the\s+)?(?:company\s+)?([A-Za-z0-9\s\.\-]+?)(?:\s+for|\s+and|\s*$)",
     "D1", "research_company", IntentCategory.RESEARCH, []),
    (r"(?:look\s+up|find\s+info|get\s+info|learn\s+about)\s+(?:on\s+)?([A-Za-z0-9\s\.\-]+)",
     "D1", "research_company", IntentCategory.RESEARCH, []),
    (r"what\s+(?:do\s+you\s+know|can\s+you\s+find)\s+about\s+([A-Za-z0-9\s\.\-]+)",
     "D1", "research_company", IntentCategory.RESEARCH, []),
    (r"(?:who\s+is|find)\s+(?:the\s+)?(?:ceo|founder|cto|head\s+of)\s+(?:of\s+|at\s+)?([A-Za-z0-9\s\.\-]+)",
     "D1", "find_person", IntentCategory.FIND, ["linkedin"]),

    # D2 - Write cold emails
    (r"(?:write|draft|create|compose)\s+(?:a\s+)?(?:cold\s+)?email\s+(?:to|for)\s+(.+)",
     "D2", "write_cold_email", IntentCategory.DRAFT, []),
    (r"(?:cold\s+)?email\s+(?:to|for)\s+(.+)",
     "D2", "write_cold_email", IntentCategory.DRAFT, []),
    (r"outreach\s+(?:email|message)\s+(?:to|for)\s+(.+)",
     "D2", "write_cold_email", IntentCategory.DRAFT, []),

    # D3 - Send sequences
    (r"(?:send|start|launch)\s+(?:a\s+)?(?:email\s+)?sequence\s+(?:to|for)\s+(.+)",
     "D3", "send_sequence", IntentCategory.SEND, ["gmail", "outlook"]),
    (r"(?:set\s+up|create)\s+(?:a\s+)?follow[- ]?up\s+(?:sequence|campaign)",
     "D3", "create_sequence", IntentCategory.CREATE, ["gmail", "outlook"]),

    # D4 - Social profile research
    (r"(?:find|look\s+up|search)\s+(?:on\s+)?linkedin\s+(?:for\s+)?(.+)",
     "D4", "linkedin_search", IntentCategory.FIND, ["linkedin"]),
    (r"(?:linkedin|social)\s+(?:profile|research)\s+(?:for|of)\s+(.+)",
     "D4", "linkedin_research", IntentCategory.RESEARCH, ["linkedin"]),
    (r"(?:find|search\s+for)\s+(?:people|professionals?|executives?)\s+(?:on\s+)?linkedin\s*(.+)?",
     "D4", "linkedin_search", IntentCategory.FIND, ["linkedin"]),
    (r"(?:find|search\s+for)\s+(?:people|professionals?|executives?|ceos?)\s+(?:who|that)\s+(.+)",
     "D4", "linkedin_search", IntentCategory.FIND, ["linkedin"]),

    # D5 - Build lead lists
    (r"(?:build|create|generate|make)\s+(?:me\s+)?(?:a\s+)?(?:list\s+of\s+)?(?:\d+\s+)?(?:leads?|prospects?)\s*(?:from|of|for|on)?\s*(.*)",
     "D5", "build_lead_list", IntentCategory.BUILD, []),
    (r"(?:build|create|generate|make)\s+(?:a\s+)?lead\s+list\s*(?:from|of|for)?\s*(.*)",
     "D5", "build_lead_list", IntentCategory.BUILD, []),
    (r"(?:find|get|scrape)\s+(?:me\s+)?(?:\d+\s+)?(?:leads?|prospects?|advertisers?)\s+(?:from|in|on)\s+(.+)",
     "D5", "find_leads", IntentCategory.FIND, []),
    (r"(?:fb|facebook)\s+ads?\s+(?:library\s+)?(?:for|search|scrape)\s*(.*)",
     "D10", "fb_ads_extraction", IntentCategory.BUILD, []),
    (r"(?:scrape|extract)\s+(?:from\s+)?(?:fb|facebook)\s+ads",
     "D10", "fb_ads_extraction", IntentCategory.BUILD, []),
    (r"(?:list\s+of\s+)?(?:\d+\s+)?(?:leads?|advertisers?)\s+(?:from\s+)?(?:fb|facebook)\s+ads",
     "D10", "fb_ads_extraction", IntentCategory.BUILD, []),

    # D6 - Update CRM
    (r"(?:update|add\s+to|log\s+in)\s+(?:the\s+)?(?:crm|hubspot|salesforce|pipedrive)",
     "D6", "update_crm", IntentCategory.UPDATE, ["hubspot", "salesforce", "pipedrive"]),
    (r"(?:add|create)\s+(?:a\s+)?(?:new\s+)?(?:contact|lead|deal)\s+(?:in|to)\s+(?:the\s+)?(?:crm|hubspot)",
     "D6", "add_to_crm", IntentCategory.CREATE, ["hubspot", "salesforce", "pipedrive"]),

    # D7 - Qualify leads
    (r"(?:qualify|score|evaluate)\s+(?:this\s+)?(?:lead|prospect|contact)",
     "D7", "qualify_lead", IntentCategory.ANALYZE, []),

    # ===== A - ADMINISTRATIVE =====
    # A1 - Email inbox processing
    (r"(?:check|read|show|get|process)\s+(?:my\s+)?(?:email|inbox|gmail|mail)",
     "A1", "process_inbox", IntentCategory.CHECK, ["gmail", "outlook"]),
    (r"(?:what'?s?\s+in|any\s+new)\s+(?:my\s+)?(?:inbox|email)",
     "A1", "process_inbox", IntentCategory.CHECK, ["gmail", "outlook"]),
    (r"(?:triage|sort|organize|summarize)\s+(?:my\s+)?(?:inbox|emails?)",
     "A1", "process_inbox", IntentCategory.ANALYZE, ["gmail", "outlook"]),
    (r"(?:read|summarize)\s+(?:\d+\s+)?emails?\s+(?:and\s+)?(?:draft\s+)?(?:replies?)?",
     "A1", "process_inbox", IntentCategory.ANALYZE, ["gmail", "outlook"]),
    (r"(?:inbox|email)\s+(?:of\s+)?\d+\s+(?:emails?|messages?)",
     "A1", "process_inbox", IntentCategory.ANALYZE, ["gmail", "outlook"]),

    # A2 - Calendar scheduling
    (r"(?:schedule|book|set\s+up)\s+(?:a\s+)?(?:meeting|call|appointment)\s+(?:with\s+)?(.+)",
     "A2", "schedule_meeting", IntentCategory.SCHEDULE, ["google_calendar"]),
    (r"(?:find|check)\s+(?:available\s+)?(?:time|slots?)\s+(?:for|with)\s+(.+)",
     "A2", "find_availability", IntentCategory.CHECK, ["google_calendar"]),
    (r"(?:what'?s?\s+on|show)\s+(?:my\s+)?calendar\s*(?:today|tomorrow|this\s+week)?",
     "A2", "check_calendar", IntentCategory.CHECK, ["google_calendar"]),

    # A3 - Meeting prep
    (r"(?:prepare|prep)\s+(?:for\s+)?(?:my\s+)?(?:meeting|call)\s+(?:with\s+)?(.+)",
     "A3", "prep_meeting", IntentCategory.CREATE, []),
    (r"(?:summarize|notes?\s+from)\s+(?:the\s+)?(?:meeting|call)",
     "A3", "summarize_meeting", IntentCategory.ANALYZE, []),

    # A4 - Document creation
    (r"(?:create|write|draft|generate)\s+(?:a\s+)?(?:document|doc|report|pdf)\s*(?:for|about|on)?\s*(.*)",
     "A4", "create_document", IntentCategory.CREATE, []),

    # ===== B - BACK-OFFICE =====
    # B1 - Spreadsheet cleaning
    (r"(?:clean|normalize|fix|process)\s+(?:this\s+)?(?:spreadsheet|csv|excel|data)",
     "B1", "clean_spreadsheet", IntentCategory.ANALYZE, []),
    (r"(?:clean|dedupe|normalize)\s+(?:and\s+)?(?:verify|validate)\s+(?:this\s+)?(?:data|spreadsheet)",
     "B1", "clean_spreadsheet", IntentCategory.ANALYZE, []),
    (r"(?:structured|clean)\s+csv\s+(?:from|output)",
     "B1", "clean_spreadsheet", IntentCategory.CREATE, []),

    # ===== C - CUSTOMER SUPPORT =====
    # C1 - Ticket classification
    (r"(?:classify|categorize|triage)\s+(?:these\s+|this\s+)?(?:support\s+)?(?:tickets?|issues?|requests?)",
     "C1", "classify_tickets", IntentCategory.ANALYZE, ["zendesk", "freshdesk"]),
    (r"(?:classify|sort)\s+tickets?\s+(?:and\s+)?(?:draft|write)\s+replies?",
     "C1", "classify_tickets", IntentCategory.ANALYZE, []),
    (r"(?:support\s+)?tickets?\s+(?:classification|categorization)",
     "C1", "classify_tickets", IntentCategory.ANALYZE, []),
    (r"(?:check|read|review)\s+(?:my\s+)?(?:zendesk|freshdesk|helpdesk)\s+tickets?",
     "C1", "classify_tickets", IntentCategory.CHECK, ["zendesk", "freshdesk"]),
    (r"(?:zendesk|freshdesk|helpdesk)\s+tickets?\s+(?:and\s+)?(?:draft|write)?\s*replies?",
     "C1", "classify_tickets", IntentCategory.ANALYZE, ["zendesk", "freshdesk"]),

    # C2 - Draft customer replies
    (r"(?:draft|write|compose)\s+(?:a\s+)?(?:reply|response)\s+(?:to|for)\s+(?:this\s+)?(?:ticket|customer|email)",
     "C2", "draft_reply", IntentCategory.DRAFT, []),
    (r"(?:respond|reply)\s+to\s+(?:this\s+)?(?:ticket|customer|email)",
     "C2", "draft_reply", IntentCategory.DRAFT, []),

    # C5 - Order lookup
    (r"(?:find|look\s+up|check|get)\s+(?:order|shipment)\s+(?:#?\s*)?(\w+)",
     "C5", "lookup_order", IntentCategory.CHECK, ["shopify"]),

    # ===== G - LEGAL =====
    # G1 - Contract extraction
    (r"(?:extract|pull|get)\s+(?:key\s+)?(?:terms?|info|data)?\s*(?:from\s+)?(?:this\s+)?contract",
     "G1", "extract_contract", IntentCategory.ANALYZE, []),
    (r"(?:extract|pull|get)\s+(?:from\s+)?(?:this\s+)?contract",
     "G1", "extract_contract", IntentCategory.ANALYZE, []),
    (r"(?:extract)\s+(?:all\s+)?(?:parties|dates|amounts|obligations|terms)\s+(?:from\s+)?(?:this\s+)?contract",
     "G1", "extract_contract", IntentCategory.ANALYZE, []),
    (r"(?:analyze|review)\s+(?:this\s+)?(?:contract|agreement|legal\s+document)",
     "G1", "extract_contract", IntentCategory.ANALYZE, []),
    (r"contract\s+(?:extraction|analysis|review)",
     "G1", "extract_contract", IntentCategory.ANALYZE, []),
    (r"(?:this\s+)?(?:contract|agreement).*(?:parties|dates|payment|obligations|termination)",
     "G1", "extract_contract", IntentCategory.ANALYZE, []),
    (r"(?:extract)\s+(?:parties|amounts?|dates?)\s+(?:and\s+)?(?:amounts?|parties|dates?)?\s*(?:from\s+)?(?:this\s+)?(?:contract)?",
     "G1", "extract_contract", IntentCategory.ANALYZE, []),

    # ===== I - INDUSTRIAL =====
    # I1 - Maintenance analysis
    (r"(?:analyze|summarize|review)\s+(?:these\s+)?(?:maintenance|equipment)\s+logs?",
     "I1", "analyze_maintenance", IntentCategory.ANALYZE, []),
    (r"(?:maintenance|equipment)\s+(?:log\s+)?(?:analysis|summary|review)",
     "I1", "analyze_maintenance", IntentCategory.ANALYZE, []),
    (r"(?:identify|find)\s+(?:recurring\s+)?(?:issues?|problems?|root\s+causes?)",
     "I1", "analyze_maintenance", IntentCategory.ANALYZE, []),

    # ===== J - FINANCE =====
    # J1 - Transaction categorization
    (r"(?:categorize|classify|sort)\s+(?:these\s+)?(?:financial\s+)?transactions?",
     "J1", "categorize_transactions", IntentCategory.ANALYZE, []),
    (r"(?:transaction|expense)\s+(?:categorization|classification|analysis)",
     "J1", "categorize_transactions", IntentCategory.ANALYZE, []),
    (r"(?:flag|find)\s+(?:anomalies|unusual)\s+(?:in\s+)?transactions?",
     "J1", "categorize_transactions", IntentCategory.ANALYZE, []),
    (r"(?:monthly|financial)\s+(?:summary|report)\s+(?:from\s+)?transactions?",
     "J1", "categorize_transactions", IntentCategory.ANALYZE, []),

    # ===== K - MARKETING =====
    # K1 - Analytics insights
    (r"(?:open|go\s+to)\s+google\s+analytics",
     "K1", "analyze_marketing", IntentCategory.ANALYZE, []),
    (r"(?:analyze|read|review)\s+(?:my\s+)?(?:google\s+analytics\s+|website\s+)?(?:traffic|analytics|marketing)",
     "K1", "analyze_marketing", IntentCategory.ANALYZE, []),
    (r"(?:google\s+)?analytics\s+(?:insights?|analysis|report|metrics)",
     "K1", "analyze_marketing", IntentCategory.ANALYZE, []),
    (r"(?:produce|generate)\s+(?:marketing\s+)?insights?\s+(?:from\s+)?(?:analytics)?",
     "K1", "analyze_marketing", IntentCategory.CREATE, []),
    (r"(?:recommend|suggest)\s+(?:marketing\s+)?experiments?",
     "K1", "analyze_marketing", IntentCategory.CREATE, []),
    (r"(?:show|get)\s+(?:me\s+)?(?:website\s+)?(?:metrics|traffic|analytics)",
     "K1", "analyze_marketing", IntentCategory.ANALYZE, []),
    (r"(?:analyze|compare)\s+(?:my\s+)?(?:google\s+analytics\s+)?(?:traffic|analytics)\s+(?:vs|versus|compared\s+to)\s+(?:industry|competitors?|benchmarks?)",
     "K1", "analyze_marketing", IntentCategory.ANALYZE, []),
    (r"(?:login|log\s+in)\s+(?:to\s+)?google\s+analytics",
     "K1", "analyze_marketing", IntentCategory.ANALYZE, []),
    (r"(?:my\s+)?google\s+analytics\s+traffic\s+(?:vs|versus|compared\s+to)",
     "K1", "analyze_marketing", IntentCategory.ANALYZE, []),

    # ===== N - GOVERNMENT =====
    # N1 - Form extraction
    (r"(?:extract|pull)\s+(?:all\s+)?(?:fields?\s+)?(?:from\s+)?(?:this\s+)?(?:government\s+)?(?:form|pdf|w-?2)",
     "N1", "extract_form", IntentCategory.ANALYZE, []),
    (r"(?:government\s+)?form\s+(?:to\s+)?(?:json|structured)",
     "N1", "extract_form", IntentCategory.ANALYZE, []),
    (r"(?:w-?2|1099|i-?9)\s+(?:form\s+)?(?:extraction|processing|extract)",
     "N1", "extract_form", IntentCategory.ANALYZE, []),
    (r"(?:this\s+)?(?:w-?2|1099|i-?9)\s+form",
     "N1", "extract_form", IntentCategory.ANALYZE, []),
    (r"(?:extract|parse|read)\s+(?:this\s+)?(?:tax\s+)?form",
     "N1", "extract_form", IntentCategory.ANALYZE, []),

    # ===== E - E-COMMERCE =====
    # E1 - Product Research
    (r"(?:search|find|look\s+up|research)\s+(?:on\s+)?amazon\s+(?:for\s+)?(.+)",
     "E1", "amazon_product_research", IntentCategory.RESEARCH, []),
    (r"(?:amazon|product)\s+research\s+(?:for\s+)?(.+)",
     "E1", "amazon_product_research", IntentCategory.RESEARCH, []),
    (r"(?:find|get|list)\s+(?:products?|items?)\s+(?:on\s+)?amazon\s*(.+)?",
     "E1", "amazon_product_research", IntentCategory.FIND, []),
    (r"(?:competitor|product)\s+(?:analysis|research)\s+(?:on\s+)?amazon",
     "E1", "amazon_product_research", IntentCategory.ANALYZE, []),
    (r"(?:write|create|generate)\s+(?:a\s+)?product\s+description\s+(?:for\s+)?(.+)",
     "E1", "write_product_desc", IntentCategory.CREATE, []),
    # E-commerce research (any site)
    (r"(?:research|compare)\s+(?:book\s+)?prices?\s+(?:on|at)\s+(.+)",
     "E1", "product_research", IntentCategory.RESEARCH, []),
    (r"(?:compare|research)\s+(?:product\s+)?prices?\s+(?:across|on|at)\s+(?:websites?|stores?|sites?)",
     "E1", "product_research", IntentCategory.RESEARCH, []),
    (r"(?:e-?commerce|product|price)\s+research\s+(?:on|at|for)\s+(.+)",
     "E1", "product_research", IntentCategory.RESEARCH, []),
    (r"(?:scrape|extract)\s+(?:products?|prices?)\s+(?:from|on)\s+(.+)",
     "E1", "product_research", IntentCategory.RESEARCH, []),

    # E5 - Ad copy
    (r"(?:write|create|generate)\s+(?:an?\s+)?ad\s+(?:copy\s+)?(?:for\s+)?(.+)",
     "E5", "write_ad_copy", IntentCategory.CREATE, []),

    # E6 - Marketing emails
    (r"(?:write|create|draft)\s+(?:a\s+)?marketing\s+email\s+(?:for|about)\s+(.+)",
     "E6", "write_marketing_email", IntentCategory.CREATE, []),

    # ===== H - LOGISTICS =====
    # H1 - Shipment Tracking
    (r"(?:track|check|find)\s+(?:my\s+)?(?:shipment|package|delivery|order)\s*(?:#?\s*)?(\w+)?",
     "H1", "track_shipment", IntentCategory.CHECK, []),
    (r"(?:track|trace)\s+(?:this\s+)?(?:tracking\s+)?(?:number\s+)?(\d{10,25})",
     "H1", "track_shipment", IntentCategory.CHECK, []),
    (r"(?:fedex|ups|usps)\s+(?:tracking|shipment|package)\s*(?:#?\s*)?(\w+)?",
     "H1", "track_shipment", IntentCategory.CHECK, []),
    (r"(?:where|status)\s+(?:is\s+)?(?:my\s+)?(?:package|shipment|order)",
     "H1", "track_shipment", IntentCategory.CHECK, []),
    (r"track\s+(?:fedex|ups|usps)\s+(?:\d+)\s*(?:and)?\s*(?:(?:fedex|ups|usps)\s+(?:\d+))?",
     "H1", "track_shipment", IntentCategory.CHECK, []),
    (r"(?:is\s+)?(?:my\s+)?(?:package|shipment|order)\s+(?:delayed|late|delivered)",
     "H1", "track_shipment", IntentCategory.CHECK, []),

    # ===== M - EDUCATION =====
    # M1 - Wikipedia Research & Quiz Generation
    (r"(?:search|research|look\s+up)\s+(?:on\s+)?wikipedia\s+(?:for\s+)?(.+)",
     "M1", "wikipedia_research", IntentCategory.RESEARCH, []),
    (r"(?:research|search|look\s+up)\s+(.+?)\s+(?:on|from|using)\s+wikipedia",
     "M1", "wikipedia_research", IntentCategory.RESEARCH, []),
    (r"(?:create|generate|make)\s+(?:a\s+)?(?:quiz|test|questions?)\s+(?:about|on|for)\s+(.+?)(?:\s+from\s+|\s*$)",
     "M1", "generate_quiz", IntentCategory.CREATE, []),
    (r"(?:quiz|test)\s+me\s+(?:on|about)\s+(.+)",
     "M1", "generate_quiz", IntentCategory.CREATE, []),
    (r"(?:learn|teach\s+me|tell\s+me)\s+(?:about\s+)?(.+)\s+(?:from\s+)?wikipedia",
     "M1", "wikipedia_research", IntentCategory.RESEARCH, []),
    (r"(?:quiz|questions?)\s+(?:about|on)\s+(.+)",
     "M1", "generate_quiz", IntentCategory.CREATE, []),

    # ===== O - IT/ENGINEERING =====
    # O1 - Stack Overflow / Error Lookup
    (r"(?:search|find|look\s+up)\s+(?:on\s+)?stackoverflow\s+(?:for\s+)?(.+)",
     "O1", "stackoverflow_search", IntentCategory.RESEARCH, []),
    (r"(?:how\s+to\s+fix|solve|debug)\s+(.+error|.+exception|.+issue)",
     "O1", "stackoverflow_search", IntentCategory.RESEARCH, []),
    (r"(?:what\s+causes?|why\s+(?:is|does))\s+(.+error|.+exception)",
     "O1", "stackoverflow_search", IntentCategory.RESEARCH, []),
    (r"(?:null|nullpointer|type|syntax|runtime)\s*(?:error|exception)",
     "O1", "stackoverflow_search", IntentCategory.RESEARCH, []),
    (r"(?:search|find)\s+(?:solutions?\s+)?(?:for\s+)?(?:this\s+)?error",
     "O1", "stackoverflow_search", IntentCategory.FIND, []),

    # ===== F - REAL ESTATE =====
    # F1 - Zillow Property Search
    (r"(?:search|find|look\s+up)\s+(?:on\s+)?(?:zillow|redfin)\s+(?:for\s+)?(.+)",
     "F1", "zillow_search", IntentCategory.FIND, []),
    (r"(?:find|search\s+for)\s+(?:homes?|houses?|properties?|real\s+estate)\s+(?:in\s+)?(.+)",
     "F1", "zillow_search", IntentCategory.FIND, []),
    (r"(?:property|house|home)\s+(?:prices?|values?|listings?)\s+(?:in\s+)?(.+)",
     "F1", "zillow_search", IntentCategory.FIND, []),
    (r"(?:find|get)\s+(?:comparable|comps?)\s+(?:properties?|homes?|on\s+zillow)?\s*(?:in|for|near)\s+(.+)",
     "F1", "zillow_search", IntentCategory.FIND, []),
    (r"(?:how\s+much\s+is|what'?s?\s+the\s+value)\s+(?:of\s+)?(?:a\s+)?(?:house|home|property)\s+(?:in\s+)?(.+)",
     "F1", "zillow_search", IntentCategory.FIND, []),
    (r"comps?\s+(?:on\s+)?(?:zillow)?\s*(?:for|near|in)\s+(.+)",
     "F1", "zillow_search", IntentCategory.FIND, []),
    (r"(?:create|write|generate)\s+(?:an?\s+)?(?:mls|listing)\s+description",
     "F1", "write_mls_description", IntentCategory.CREATE, []),

    # ===== L - HR/RECRUITING =====
    # L1 - LinkedIn Profile Search & Candidate Scoring
    (r"research\s+(?:this\s+)?candidate\s+(?:on\s+)?linkedin",
     "L1", "score_candidate", IntentCategory.RESEARCH, ["linkedin"]),
    (r"(?:find|search)\s+(.+?)\s+(?:on\s+)?linkedin",
     "L1", "linkedin_search", IntentCategory.FIND, ["linkedin"]),
    (r"(?:search|find|look\s+up)\s+(?:on\s+)?linkedin\s+(?:for\s+)?(.+)",
     "L1", "linkedin_search", IntentCategory.FIND, ["linkedin"]),
    (r"(?:find|search\s+for)\s+(?:candidates?|people|professionals?)\s+(?:on\s+)?linkedin\s*(.+)?",
     "L1", "linkedin_search", IntentCategory.FIND, ["linkedin"]),
    (r"(?:research|look\s+up)\s+(?:candidate|applicant|person)\s+(.+)",
     "L1", "linkedin_search", IntentCategory.RESEARCH, ["linkedin"]),
    (r"(?:linkedin\s+)?profile\s+(?:for|of)\s+(.+)",
     "L1", "linkedin_search", IntentCategory.FIND, ["linkedin"]),
    (r"linkedin\s+(?:search|find|look\s+up)\s+(.+)",
     "L1", "linkedin_search", IntentCategory.FIND, ["linkedin"]),
    # L2 - Candidate scoring
    (r"(?:research|evaluate|review)\s+(?:this\s+)?candidate\s+(?:on\s+)?linkedin\s+(?:and\s+)?(?:score)?",
     "L1", "score_candidate", IntentCategory.ANALYZE, ["linkedin"]),
    (r"(?:score|evaluate|assess)\s+(?:this\s+)?(?:candidate|resume)\s+(?:for\s+)?(.+)\s+role",
     "L1", "score_candidate", IntentCategory.ANALYZE, ["linkedin"]),
    (r"(?:compare|evaluate)\s+(?:these\s+)?(?:resumes?|candidates?)",
     "L1", "compare_candidates", IntentCategory.ANALYZE, []),
    (r"(?:screen|review)\s+(?:this\s+)?(?:resume|cv|application)\s+(?:for\s+)?(.+)",
     "L1", "score_candidate", IntentCategory.ANALYZE, []),

    # ===== K - MARKETING =====
    # K5 - Competitor research
    (r"(?:analyze|research)\s+(?:our\s+)?competitor[s]?\s*(.+)?",
     "K5", "research_competitors", IntentCategory.RESEARCH, []),
    (r"(?:what\s+are|who\s+are)\s+(?:our\s+)?competitors?\s+(?:doing|in)\s*(.+)?",
     "K5", "research_competitors", IntentCategory.RESEARCH, []),

    # ===== B - BUSINESS OPS =====
    # B3 - Data enrichment
    (r"(?:enrich|get\s+more\s+info|find\s+details)\s+(?:on|for|about)\s+(.+)",
     "B3", "enrich_data", IntentCategory.RESEARCH, []),

    # B6 - Analyze spreadsheets
    (r"(?:analyze|summarize|review)\s+(?:this\s+)?(?:spreadsheet|csv|data|sheet)",
     "B6", "analyze_spreadsheet", IntentCategory.ANALYZE, []),

    # ===== P - PROTECTION/AUTOMATION =====
    # P1 - CAPTCHA Handling
    (r"(?:solve|handle|bypass)\s+(?:the\s+)?(?:captcha|recaptcha|hcaptcha|turnstile)",
     "P1", "solve_captcha", IntentCategory.ANALYZE, []),
    (r"captcha\s+(?:detected|appears?|showing)",
     "P1", "solve_captcha", IntentCategory.ANALYZE, []),
    (r"(?:recaptcha|hcaptcha|turnstile)\s+(?:challenge|verification)",
     "P1", "solve_captcha", IntentCategory.ANALYZE, []),

    # P2 - Cloudflare Challenge Handling
    (r"(?:bypass|handle|solve)\s+(?:the\s+)?cloudflare(?:\s+(?:challenge|block))?",
     "P2", "handle_cloudflare", IntentCategory.ANALYZE, []),
    (r"cloudflare\s+(?:is\s+)?(?:blocking|challenge|detected)",
     "P2", "handle_cloudflare", IntentCategory.ANALYZE, []),
    (r"(?:site|page)\s+(?:is\s+)?blocked\s+(?:by\s+)?cloudflare",
     "P2", "handle_cloudflare", IntentCategory.ANALYZE, []),

    # P3 - Stealth Mode
    (r"(?:use|enable|turn\s+on)\s+stealth(?:\s+mode)?",
     "P3", "enable_stealth", IntentCategory.ANALYZE, []),
    (r"(?:anti[- ]detection|anti[- ]bot)(?:\s+mode)?",
     "P3", "enable_stealth", IntentCategory.ANALYZE, []),
    (r"(?:avoid|prevent)\s+(?:bot\s+)?detection",
     "P3", "enable_stealth", IntentCategory.ANALYZE, []),
    (r"stealth\s+(?:browsing|automation)",
     "P3", "enable_stealth", IntentCategory.ANALYZE, []),
]

# Entity extraction patterns
ENTITY_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "url": r"https?://[^\s<>\"]+|www\.[^\s<>\"]+",
    "phone": r"(?:\+?1)?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    "company_domain": r"(?:at\s+)?([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|io|co|ai|app|dev|tech|net|org))",
    "linkedin_url": r"linkedin\.com/(?:company|in)/([^\s/\"]+)",
    "money": r"\$[\d,]+(?:\.\d{2})?|\d+\s*(?:dollars?|usd|k\b)",
    "date": r"(?:today|tomorrow|next\s+(?:week|month)|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2})",
    "count": r"(\d+)\s*(?:leads?|prospects?|emails?|contacts?|companies|people)",
}


class IntentDetector:
    """Detects user intent from natural language."""

    def __init__(self):
        self.patterns = INTENT_PATTERNS
        self.entity_patterns = ENTITY_PATTERNS
        self.context: Dict[str, Any] = {}

    def detect(self, text: str) -> DetectedIntent:
        """Detect the primary intent from user text."""
        text_lower = text.lower().strip()

        # Extract entities first
        entities = self._extract_entities(text)

        # Try each pattern
        best_match = None
        best_confidence = 0.0

        for pattern, capability, action, category, services in self.patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                # Calculate confidence based on match quality
                confidence = self._calculate_confidence(match, text_lower, pattern)

                if confidence > best_confidence:
                    best_confidence = confidence

                    # Extract parameters from match groups
                    params = {}
                    if match.groups():
                        params["target"] = match.group(1).strip() if match.group(1) else None

                    best_match = DetectedIntent(
                        capability=capability,
                        action=action,
                        category=category,
                        confidence=confidence,
                        entities=entities,
                        raw_text=text,
                        requires_login=services,
                        parameters=params
                    )

        # If no match, return unknown intent
        if not best_match:
            best_match = DetectedIntent(
                capability="UNKNOWN",
                action="unknown",
                category=IntentCategory.UNKNOWN,
                confidence=0.0,
                entities=entities,
                raw_text=text,
                requires_login=[],
                parameters={}
            )

        # Enhance parameters with extracted entities
        best_match = self._enhance_with_entities(best_match)

        return best_match

    def detect_all(self, text: str) -> List[DetectedIntent]:
        """Detect all possible intents (for complex requests)."""
        text_lower = text.lower().strip()
        entities = self._extract_entities(text)
        intents = []

        for pattern, capability, action, category, services in self.patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                confidence = self._calculate_confidence(match, text_lower, pattern)

                params = {}
                if match.groups():
                    params["target"] = match.group(1).strip() if match.group(1) else None

                intent = DetectedIntent(
                    capability=capability,
                    action=action,
                    category=category,
                    confidence=confidence,
                    entities=entities,
                    raw_text=text,
                    requires_login=services,
                    parameters=params
                )
                intents.append(self._enhance_with_entities(intent))

        # Sort by confidence
        intents.sort(key=lambda x: x.confidence, reverse=True)

        # Remove duplicates (same capability)
        seen = set()
        unique = []
        for intent in intents:
            if intent.capability not in seen:
                seen.add(intent.capability)
                unique.append(intent)

        return unique[:5]  # Top 5

    def _extract_entities(self, text: str) -> List[ExtractedEntity]:
        """Extract all entities from text."""
        entities = []

        for entity_type, pattern in self.entity_patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1) if match.groups() else match.group(0)
                entities.append(ExtractedEntity(
                    type=entity_type,
                    value=value.strip(),
                    confidence=0.9,
                    start=match.start(),
                    end=match.end()
                ))

        # Extract company names (heuristic: capitalized words not at start)
        company_pattern = r"(?:at\s+|for\s+|from\s+|about\s+)([A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*)"
        for match in re.finditer(company_pattern, text):
            company = match.group(1).strip()
            if len(company) > 1 and company.lower() not in ['the', 'a', 'an', 'for', 'to']:
                entities.append(ExtractedEntity(
                    type="company",
                    value=company,
                    confidence=0.7,
                    start=match.start(1),
                    end=match.end(1)
                ))

        # Extract person names (before titles like CEO, founder)
        person_pattern = r"(?:ceo|founder|cto|head)\s+(?:of\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
        for match in re.finditer(person_pattern, text, re.IGNORECASE):
            entities.append(ExtractedEntity(
                type="person",
                value=match.group(1).strip(),
                confidence=0.6,
                start=match.start(1),
                end=match.end(1)
            ))

        # Extract industries
        industries = ['saas', 'fintech', 'healthtech', 'edtech', 'ecommerce', 'e-commerce',
                     'real estate', 'marketing', 'agency', 'consulting', 'software', 'ai',
                     'crypto', 'blockchain', 'b2b', 'b2c', 'startup', 'enterprise']
        text_lower = text.lower()
        for industry in industries:
            if industry in text_lower:
                idx = text_lower.index(industry)
                entities.append(ExtractedEntity(
                    type="industry",
                    value=industry,
                    confidence=0.95,
                    start=idx,
                    end=idx + len(industry)
                ))

        return entities

    def _calculate_confidence(self, match: re.Match, text: str, pattern: str) -> float:
        """Calculate confidence score for a match."""
        confidence = 0.7  # Base confidence

        # Boost if match covers more of the text
        coverage = len(match.group(0)) / len(text)
        confidence += coverage * 0.2

        # Boost if match is at the start
        if match.start() < 5:
            confidence += 0.1

        # Cap at 1.0
        return min(1.0, confidence)

    def _extract_inline_data(self, text: str, capability: str) -> Optional[str]:
        """Extract inline data from prompts for text-heavy workflows."""
        # Workflows that accept inline text data
        inline_data_capabilities = ["B1", "C1", "G1", "I1", "J1", "N1", "A1", "O1", "M1"]

        if capability not in inline_data_capabilities:
            return None

        # Check for multi-line data (contains newlines with substantive content)
        lines = text.split('\n')
        if len(lines) > 1:
            # Find where the data starts (usually after the command)
            # Look for patterns like CSV headers, numbered items, dates, etc.
            data_start = -1
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                line_upper = line_stripped.upper()
                # Skip empty lines and command lines
                if not line_stripped:
                    continue
                # Detect data patterns
                if any([
                    ',' in line_stripped and len(line_stripped.split(',')) >= 3,  # CSV-like
                    # Contract/Agreement patterns
                    'AGREEMENT' in line_upper or 'CONTRACT' in line_upper,
                    'BETWEEN' in line_upper and ('AND' in line_upper or 'PARTY' in line_upper),
                    line_upper.startswith(('THIS ', 'WHEREAS', 'SERVICES')),
                    # Form patterns
                    re.match(r'^[a-z]\.\s', line_stripped),  # Form field (a. b. c.)
                    re.match(r'^[1-9]\d?\.\s', line_stripped),  # Numbered fields (1. 2. etc)
                    line_stripped.startswith(('FORM ', 'W-2', 'W2', '1099', 'Employee', 'Employer')),
                    # Email/Ticket patterns
                    line_stripped.startswith(('Email', 'Ticket', 'Transaction', '#')),
                    re.match(r'^(Ticket|Email|#)\s*#?\d+', line_stripped, re.IGNORECASE),
                    'From:' in line_stripped or 'Subject:' in line_stripped,
                    # Date patterns
                    re.match(r'^[\d\-/]+[\s\|,]', line_stripped),  # Starts with date
                    re.match(r'^20\d{2}-\d{2}-\d{2}', line_stripped),  # ISO date
                    # Money values
                    '$' in line_stripped and re.search(r'\$[\d,]+', line_stripped),
                    # Maintenance logs
                    'Unit:' in line_stripped or 'Issue:' in line_stripped,
                ]):
                    data_start = i
                    break

            if data_start >= 0:
                # Extract everything from data_start onwards
                data_lines = lines[data_start:]
                return '\n'.join(data_lines).strip()

            # If no pattern matched but there's multi-line content after first line, use that
            if len(lines) > 2:
                # Skip first line (command) and return rest
                rest = '\n'.join(lines[1:]).strip()
                if len(rest) > 20:  # Must have substantive content
                    return rest

        # For single-line prompts with inline error messages (O1)
        if capability == "O1":
            # Extract error message in quotes or after "error"
            error_match = re.search(r"['\"]([^'\"]+)['\"]|error[:\s]+(.+?)(?:\.|$)", text, re.IGNORECASE)
            if error_match:
                return error_match.group(1) or error_match.group(2)

        # For M1 - extract topic (clean up "quiz about" prefix if present)
        if capability == "M1":
            topic_match = re.search(r"(?:quiz|test|questions?)\s+(?:about|on|for)\s+(?:the\s+)?(.+?)(?:\s+using|\s+from|\s+include|\.|$)", text, re.IGNORECASE)
            if topic_match:
                topic = topic_match.group(1).strip()
                # Clean up common suffixes
                topic = re.sub(r'\s+using.*$', '', topic, flags=re.IGNORECASE)
                topic = re.sub(r'\s+include.*$', '', topic, flags=re.IGNORECASE)
                return topic

        return None

    def _enhance_with_entities(self, intent: DetectedIntent) -> DetectedIntent:
        """Add extracted entities to parameters."""
        for entity in intent.entities:
            if entity.type == "company" and "company" not in intent.parameters:
                intent.parameters["company"] = entity.value
            elif entity.type == "email" and "email" not in intent.parameters:
                intent.parameters["email"] = entity.value
            elif entity.type == "url" and "url" not in intent.parameters:
                intent.parameters["url"] = entity.value
            elif entity.type == "industry" and "industry" not in intent.parameters:
                intent.parameters["industry"] = entity.value
            elif entity.type == "count" and "count" not in intent.parameters:
                intent.parameters["count"] = entity.value
            elif entity.type == "person" and "person" not in intent.parameters:
                intent.parameters["person"] = entity.value

        # Extract inline data for text-heavy workflows
        inline_data = self._extract_inline_data(intent.raw_text, intent.capability)
        if inline_data:
            # Map to the correct parameter based on capability
            param_map = {
                "B1": "data",
                "C1": "tickets",
                "G1": "contract_text",
                "I1": "logs",
                "J1": "transactions",
                "N1": "form_text",
                "O1": "error",
                "M1": "topic",
            }
            param_name = param_map.get(intent.capability)
            if param_name and param_name not in intent.parameters:
                intent.parameters[param_name] = inline_data

        # Map 'target' to executor-specific parameter names
        if "target" in intent.parameters and intent.parameters["target"]:
            target = intent.parameters["target"]

            # Capability-specific parameter mapping
            param_mapping = {
                "A1": "email_provider",  # Email inbox
                "B1": "data",            # Spreadsheet cleaning
                "C1": "tickets",         # Ticket classification
                "D1": "company",         # Company research
                "D4": "name",            # LinkedIn search (SDR)
                "E1": "query",           # Amazon product research
                "F1": "location",        # Zillow/real estate
                "G1": "contract_text",   # Contract extraction
                "H1": "tracking_number", # Shipment tracking
                "I1": "logs",            # Maintenance analysis
                "J1": "transactions",    # Transaction categorization
                "K1": "platform",        # Marketing analytics
                "L1": "name",            # LinkedIn search
                "M1": "topic",           # Wikipedia/quiz
                "N1": "form_text",       # Government form extraction
                "O1": "error",           # Stack Overflow
            }

            param_name = param_mapping.get(intent.capability, "company")
            if param_name not in intent.parameters:
                intent.parameters[param_name] = target

            # Also keep company for backwards compatibility
            if "company" not in intent.parameters and len(target) > 1 and intent.capability not in ["H1", "M1", "O1"]:
                intent.parameters["company"] = target

        # Extract tracking numbers for H1
        if intent.capability == "H1":
            tracking_match = re.search(r'(\d{10,25}|1Z[A-Z0-9]{16})', intent.raw_text, re.IGNORECASE)
            if tracking_match:
                intent.parameters["tracking_number"] = tracking_match.group(1)

        return intent

    def set_context(self, key: str, value: Any):
        """Set context for follow-up detection."""
        self.context[key] = value

    def get_required_params(self, intent: DetectedIntent) -> List[str]:
        """Get list of required parameters that are missing."""
        required = {
            # A - Admin
            "A1": [],  # Email inbox - can work without params
            "A2": ["attendee"],
            # B - Back-office
            "B1": ["data"],  # Spreadsheet needs data
            # C - Customer Support
            "C1": [],  # Tickets - can prompt user
            "C2": [],  # Works on current ticket
            # D - Sales/SDR
            "D1": ["company"],
            "D2": ["company", "recipient"],
            "D5": [],  # Defaults to fb_ads
            # E - E-commerce
            "E1": ["query"],
            # F - Real Estate
            "F1": ["location"],
            # G - Legal
            "G1": ["contract_text"],
            # H - Logistics
            "H1": ["tracking_number"],
            # I - Industrial
            "I1": ["logs"],
            # J - Finance
            "J1": ["transactions"],
            # K - Marketing
            "K1": [],  # Can navigate to analytics
            # L - HR
            "L1": ["name"],
            # M - Education
            "M1": ["topic"],
            # N - Government
            "N1": ["form_text"],
            # O - IT/Engineering
            "O1": ["error"],
        }

        needed = required.get(intent.capability, [])
        missing = [p for p in needed if p not in intent.parameters or not intent.parameters[p]]

        return missing


# Convenience function
def detect_intent(text: str) -> DetectedIntent:
    """Quick intent detection."""
    detector = IntentDetector()
    return detector.detect(text)


def extract_entities(text: str) -> List[ExtractedEntity]:
    """Quick entity extraction."""
    detector = IntentDetector()
    return detector._extract_entities(text)
