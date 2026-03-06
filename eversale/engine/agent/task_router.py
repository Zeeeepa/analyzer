"""
Task Router - Routes user requests to appropriate capabilities.

This module:
1. Analyzes user requests to identify required capabilities
2. Checks login requirements
3. Prompts for login if needed
4. Executes the appropriate task handlers
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import yaml
from pathlib import Path
from loguru import logger

from .login_manager import LoginManager, SERVICES, CAPABILITY_SERVICES, ServiceCategory


@dataclass
class ServiceRequirement:
    """A service requirement that can be satisfied by alternatives."""
    category: str  # e.g., "email", "crm"
    alternatives: List[str]  # e.g., ["gmail", "outlook"]
    satisfied_by: Optional[str] = None  # Which alternative is logged in


@dataclass
class TaskRequest:
    """A parsed user request."""
    raw_text: str
    detected_capabilities: List[str]
    required_services: List[str]
    service_requirements: List[ServiceRequirement]  # New: grouped by category
    category: str
    confidence: float
    parameters: Dict[str, Any]


class TaskRouter:
    """Routes requests to appropriate capabilities and handles prerequisites."""

    def __init__(self, capabilities_file: str = "config/capabilities_spec.yaml"):
        self.login_manager = LoginManager()
        self.capabilities = self._load_capabilities(capabilities_file)
        self.keyword_map = self._build_keyword_map()

    def _load_capabilities(self, file_path: str) -> Dict:
        """Load capabilities spec from YAML."""
        path = Path(file_path)
        if path.exists():
            return yaml.safe_load(path.read_text())
        return {}

    def _build_keyword_map(self) -> Dict[str, List[str]]:
        """Build keyword to capability mapping."""
        # Keywords that indicate specific capabilities
        return {
            # A - Administrative
            "email": ["A1"],
            "inbox": ["A1"],
            "triage": ["A1", "C1", "N8"],
            "calendar": ["A2", "F5", "I7"],
            "schedule": ["A2", "D3", "F5"],
            "meeting": ["A2", "A3"],
            "agenda": ["A3"],
            "notes": ["A3"],
            "document": ["A4", "G3"],
            "report": ["A4", "A8", "B5", "D8", "H5", "I8", "J3", "K3", "N5"],
            "pdf": ["A4"],
            "data entry": ["A5"],
            "spreadsheet": ["A5", "B6", "J8"],
            "extract": ["A6", "G2", "H3", "J1", "L2", "N1"],
            "sop": ["A7", "I6", "N7"],
            "checklist": ["A7", "I2"],

            # B - Business Ops
            "crm": ["B1", "B2", "D6", "F3"],
            "pipeline": ["B2", "L8"],
            "deal": ["B2"],
            "enrich": ["B3"],
            "company info": ["B3", "D1"],
            "follow-up": ["B4", "D3"],
            "reminder": ["B4"],
            "analyze": ["B6", "C7", "J6", "K3", "M6"],
            "trello": ["B7"],
            "asana": ["B7", "O5"],
            "status update": ["B8"],

            # C - Customer Support
            "ticket": ["C1", "C2", "C3", "C8", "O5"],
            "support": ["C1", "C2", "C8"],
            "customer reply": ["C2", "E2"],
            "escalate": ["C3"],
            "refund": ["C4"],
            "order": ["C5", "E3"],
            "faq": ["C6"],
            "csat": ["C7"],
            "backlog": ["C8"],

            # D - Sales/SDR
            "prospect": ["D1", "D5"],
            "research": ["D1", "D4", "K5"],
            "cold email": ["D2"],
            "outreach": ["D2", "D3"],
            "sequence": ["D3"],
            "linkedin": ["D4", "K2", "L1"],
            "lead list": ["D5"],
            "fb ads": ["D5"],
            "facebook ads": ["D5"],
            "qualify": ["D7"],
            "outbound": ["D8"],

            # E - E-commerce
            "product description": ["E1"],
            "inventory": ["E4", "H5"],
            "ad copy": ["E5", "K4"],
            "marketing email": ["E6", "K1"],
            "shopify": ["E7", "C5"],
            "review": ["E8", "G1"],

            # F - Real Estate
            "listing": ["F1", "F6"],
            "property": ["F1", "F4", "F8"],
            "showing": ["F5"],
            "mls": ["F6"],
            "buyer": ["F7"],
            "seller": ["F7"],
            "comparison": ["F8"],

            # G - Legal
            "contract": ["G1", "G2"],
            "clause": ["G2"],
            "discovery": ["G3"],
            "timeline": ["G4"],
            "intake": ["G5", "N8"],
            "template": ["G7"],
            "evidence": ["G8"],

            # H - Logistics
            "shipment": ["H1"],
            "delay": ["H2"],
            "customs": ["H3"],
            "vendor": ["H4", "J4"],
            "eta": ["H6"],
            "purchase order": ["H7"],

            # I - Industrial
            "safety": ["I1"],
            "compliance": ["I2"],
            "audit": ["I3"],
            "maintenance": ["I4"],
            "inspection": ["I5"],
            "crew": ["I7"],
            "quality": ["I8"],

            # J - Finance
            "invoice": ["J1"],
            "expense": ["J2"],
            "financial": ["J3", "J6"],
            "reconciliation": ["J4"],
            "receipt": ["J5"],
            "p&l": ["J6"],
            "payment": ["J7"],
            "budget": ["J8"],

            # K - Marketing
            "newsletter": ["K1"],
            "social": ["K2"],
            "analytics": ["K3"],
            "competitor": ["K5"],
            "keyword": ["K6"],
            "landing page": ["K7"],
            "persona": ["K8"],

            # L - HR
            "resume": ["L1"],
            "candidate": ["L1", "L2", "L3"],
            "rejection": ["L3"],
            "interview": ["L4", "L6"],
            "onboarding": ["L5"],
            "job description": ["L7"],
            "hiring": ["L8"],

            # M - Education
            "textbook": ["M1"],
            "lecture": ["M1"],
            "lesson": ["M2"],
            "quiz": ["M3"],
            "flashcard": ["M4"],
            "course": ["M5"],
            "student": ["M6", "M8"],
            "study guide": ["M7"],

            # N - Government
            "form": ["N1"],
            "case file": ["N2"],
            "public records": ["N3"],
            "correspondence": ["N4"],

            # O - IT/Engineering
            "log": ["O1", "I4"],
            "bug": ["O2"],
            "release notes": ["O3"],
            "documentation": ["O4"],
            "standup": ["O8"],
        }

    def analyze_request(self, user_text: str) -> TaskRequest:
        """Analyze a user request and identify capabilities needed."""
        text_lower = user_text.lower()

        # Find matching capabilities based on keywords
        detected = []
        for keyword, caps in self.keyword_map.items():
            if keyword in text_lower:
                detected.extend(caps)

        # Deduplicate and score
        capability_counts = {}
        for cap in detected:
            capability_counts[cap] = capability_counts.get(cap, 0) + 1

        # Sort by frequency
        sorted_caps = sorted(capability_counts.keys(),
                           key=lambda x: capability_counts[x],
                           reverse=True)

        # Group services by category (for OR logic)
        service_requirements = self._get_service_requirements(sorted_caps)

        # Flatten for backward compatibility (only include what's actually needed)
        required_services = []
        for req in service_requirements:
            # Just add the first alternative for legacy compatibility
            if req.alternatives:
                required_services.append(req.alternatives[0])

        # Determine primary category
        category = ""
        if sorted_caps:
            category = sorted_caps[0][0]  # First letter (A, B, C, etc.)

        # Calculate confidence
        confidence = min(1.0, len(sorted_caps) * 0.2) if sorted_caps else 0.0

        return TaskRequest(
            raw_text=user_text,
            detected_capabilities=sorted_caps[:5],  # Top 5
            required_services=required_services,
            service_requirements=service_requirements,
            category=category,
            confidence=confidence,
            parameters={}
        )

    def _get_service_requirements(self, capabilities: List[str]) -> List[ServiceRequirement]:
        """Group required services by category for OR logic."""
        # Collect all services needed, grouped by category
        category_services: Dict[str, set] = {}

        for cap in capabilities:
            services = CAPABILITY_SERVICES.get(cap, [])
            for svc_id in services:
                svc = SERVICES.get(svc_id)
                if svc:
                    cat_name = svc.category.value
                    if cat_name not in category_services:
                        category_services[cat_name] = set()
                    category_services[cat_name].add(svc_id)

        # Create requirements for each category
        requirements = []
        for cat_name, svc_ids in category_services.items():
            # Check if any alternative is already logged in
            satisfied_by = None
            for svc_id in svc_ids:
                if self.login_manager.is_logged_in(svc_id):
                    satisfied_by = svc_id
                    break

            requirements.append(ServiceRequirement(
                category=cat_name,
                alternatives=list(svc_ids),
                satisfied_by=satisfied_by
            ))

        return requirements

    def check_login_requirements(self, request: TaskRequest) -> Tuple[bool, List[ServiceRequirement]]:
        """Check if user is logged into required services (using OR logic for alternatives)."""
        missing_requirements = []

        for req in request.service_requirements:
            # Check if ANY alternative in this category is logged in
            any_logged_in = False
            for svc_id in req.alternatives:
                if self.login_manager.is_logged_in(svc_id):
                    any_logged_in = True
                    req.satisfied_by = svc_id
                    break

            if not any_logged_in:
                missing_requirements.append(req)

        return len(missing_requirements) == 0, missing_requirements

    def get_login_prompt(self, missing_requirements: List[ServiceRequirement]) -> str:
        """Generate a login prompt for missing services (with OR logic for alternatives)."""
        if not missing_requirements:
            return ""

        lines = [
            "**Before I can help with this task, please log into ONE of these services for each category:**\n"
        ]

        for req in missing_requirements:
            if len(req.alternatives) > 1:
                # Multiple alternatives - user can choose
                alt_names = []
                for svc_id in req.alternatives:
                    svc = SERVICES.get(svc_id)
                    if svc:
                        alt_names.append(f"{svc.name} ({svc.login_url})")
                    else:
                        alt_names.append(svc_id)
                lines.append(f"- **{req.category.title()}** (choose one):")
                for alt_name in alt_names:
                    lines.append(f"  - {alt_name}")
            else:
                # Single required service
                svc_id = req.alternatives[0]
                svc = SERVICES.get(svc_id)
                if svc:
                    lines.append(f"- **{svc.name}**: {svc.login_url}")
                else:
                    lines.append(f"- {svc_id}")

        lines.append("\n**Steps:**")
        lines.append("1. Open a new browser tab (the browser uses an isolated profile at ~/.eversale/browser-profile)")
        lines.append("2. Log into at least ONE option for each category above")
        lines.append("3. Once logged in, come back here and say 'ready' or 'continue'")
        lines.append("\n*Your login session will be saved for future use.*")

        return "\n".join(lines)

    def get_task_details_prompt(self, request: TaskRequest) -> str:
        """Generate a prompt asking for task details."""
        cap_descriptions = {
            "A1": "email triage and responses",
            "A2": "calendar scheduling",
            "B1": "CRM updates",
            "B3": "data enrichment",
            "C2": "customer reply drafts",
            "D1": "prospect research",
            "D2": "cold email writing",
            "D5": "lead list building",
            "E1": "product descriptions",
            # Add more as needed
        }

        if not request.detected_capabilities:
            return "Could you provide more details about what you'd like me to help with?"

        cap = request.detected_capabilities[0]
        desc = cap_descriptions.get(cap, "this task")

        prompts = {
            "D1": "To research prospects, please provide:\n- Company name or industry\n- What information you're looking for\n- Any specific criteria",
            "D2": "To write a cold email, please provide:\n- The recipient's name and company\n- What you're offering\n- Any specific angle or value prop",
            "D5": "To build a lead list, please provide:\n- Target industry or niche\n- Location (if relevant)\n- Any specific criteria",
            "B3": "To enrich data, please provide:\n- Company name or domain\n- What fields you need (email, phone, social, etc.)",
            "A1": "To help with email, please:\n- Share the email content or subject\n- Let me know what kind of response you need",
        }

        return prompts.get(cap, f"To help with {desc}, please provide more details about what you need.")

    def route_task(self, request: TaskRequest) -> Dict[str, Any]:
        """Route a task to the appropriate handler."""
        if not request.detected_capabilities:
            return {
                "status": "need_clarification",
                "message": "I'm not sure what you'd like me to do. Could you provide more details?",
                "suggestions": [
                    "Research a company",
                    "Write a cold email",
                    "Build a lead list",
                    "Update CRM",
                    "Draft customer response"
                ]
            }

        # Check login requirements (now uses OR logic for alternatives)
        logged_in, missing_requirements = self.check_login_requirements(request)

        if not logged_in:
            # Format missing services for display
            missing_categories = [
                f"{req.category}: {' or '.join(req.alternatives)}"
                for req in missing_requirements
            ]
            return {
                "status": "need_login",
                "message": self.get_login_prompt(missing_requirements),
                "missing_categories": missing_categories,
                "missing_requirements": missing_requirements,
                "detected_capabilities": request.detected_capabilities
            }

        # Route to appropriate handler - get which services are actually available
        primary_cap = request.detected_capabilities[0]
        category = primary_cap[0]

        # Get the actual services that are logged in
        available_services = [
            req.satisfied_by for req in request.service_requirements
            if req.satisfied_by
        ]

        return {
            "status": "ready",
            "primary_capability": primary_cap,
            "category": category,
            "available_services": available_services,
            "required_services": request.required_services,
            "confidence": request.confidence,
            "next_step": self.get_task_details_prompt(request)
        }


def create_universal_prompt() -> str:
    """Create the universal agent prompt that can handle all capabilities."""
    return """
You are a universal business operations agent capable of handling tasks across 15 major categories:

**A - Administrative**: Email, calendar, documents, data entry, SOPs
**B - Business Ops**: CRM, pipeline, data enrichment, project boards
**C - Customer Support**: Tickets, replies, escalations, order lookup
**D - Sales/SDR**: Prospect research, cold emails, lead lists, sequences
**E - E-commerce**: Product descriptions, orders, inventory, Shopify
**F - Real Estate**: Listings, showings, MLS data, client communications
**G - Legal Admin**: Contracts, discovery, timelines, templates
**H - Logistics**: Shipments, delays, customs, vendor follow-ups
**I - Industrial**: Safety docs, compliance, maintenance, crew scheduling
**J - Finance**: Invoices, expenses, reconciliation, budgets
**K - Marketing**: Newsletters, social content, analytics, ad copy
**L - HR/Recruiting**: Resumes, candidates, interviews, onboarding
**M - Education**: Lesson plans, quizzes, course materials
**N - Government Admin**: Forms, case files, correspondence
**O - IT/Engineering**: Logs, bugs, release notes, documentation

**IMPORTANT - Login Flow:**
Before performing any task that requires access to external services (Gmail, CRM, Shopify, etc.):

1. **Check if login is needed**: If the task requires a service, ask the user if they're logged in
2. **Prompt for login**: If not logged in, provide the login URL and ask them to:
   - Open a new browser tab
   - Log into the service
   - Return and say "ready" or "continue"
3. **Remember logins**: The browser uses an isolated persistent profile (~/.eversale/browser-profile), so logins are saved

**Task Execution Flow:**
1. Understand what the user wants
2. Identify required capabilities (D1, B3, etc.)
3. Check login requirements
4. Ask for any missing details
5. Execute the task using available tools
6. Report results

**Available Tools:**
- PlaywrightClient: Browser automation (with isolated persistent browser profile)
- extract_fb_ads_batch: Facebook Ads Library scraping
- extract_reddit_posts_batch: Reddit warm prospect finding
- extract_page_data_fast: Company website data extraction
- File operations: Read, write, analyze documents
- Web search and fetch

Always be proactive about asking for login when needed, and remember that the browser maintains session cookies across uses.
"""
