"""
Login Manager - Handles authentication flow for all services.

Before performing tasks that require login, this module:
1. Checks if user is logged into the required service
2. Prompts user to log in if needed
3. Waits for confirmation before proceeding
4. Remembers login state in an isolated persistent browser profile (~/.eversale/browser-profile)
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from loguru import logger


class ServiceCategory(Enum):
    """Categories of services that may require login."""
    EMAIL = "email"
    CALENDAR = "calendar"
    CRM = "crm"
    PROJECT_MGMT = "project_management"
    ECOMMERCE = "ecommerce"
    SOCIAL = "social"
    DOCS = "documents"
    SPREADSHEET = "spreadsheet"
    COMMUNICATION = "communication"
    SUPPORT = "support"
    ANALYTICS = "analytics"
    FINANCE = "finance"
    HR = "hr"
    REAL_ESTATE = "real_estate"


@dataclass
class ServiceConfig:
    """Configuration for a service that may require login."""
    name: str
    category: ServiceCategory
    login_url: str
    login_check_url: str  # URL to check if logged in
    login_indicators: List[str]  # Text/elements that indicate logged in state
    logout_indicators: List[str]  # Text/elements that indicate logged out
    description: str
    required_for: List[str] = field(default_factory=list)  # Capability codes


# Master service registry
SERVICES: Dict[str, ServiceConfig] = {
    # Email Services
    "gmail": ServiceConfig(
        name="Gmail",
        category=ServiceCategory.EMAIL,
        login_url="https://mail.google.com",
        login_check_url="https://mail.google.com",
        login_indicators=["inbox", "compose", "starred"],
        logout_indicators=["sign in", "create account"],
        description="Google email for A1, C2, D2, D3, E2, etc.",
        required_for=["A1", "C2", "D2", "D3", "E2", "F2", "F7", "J7", "L3"]
    ),
    "outlook": ServiceConfig(
        name="Outlook",
        category=ServiceCategory.EMAIL,
        login_url="https://outlook.live.com",
        login_check_url="https://outlook.live.com/mail",
        login_indicators=["inbox", "new message", "focused"],
        logout_indicators=["sign in", "create"],
        description="Microsoft email",
        required_for=["A1", "C2", "D2", "D3"]
    ),

    # Calendar Services
    "google_calendar": ServiceConfig(
        name="Google Calendar",
        category=ServiceCategory.CALENDAR,
        login_url="https://calendar.google.com",
        login_check_url="https://calendar.google.com",
        login_indicators=["today", "week", "month", "create"],
        logout_indicators=["sign in"],
        description="Google Calendar for A2, F5",
        required_for=["A2", "F5", "I7"]
    ),

    # CRM Services
    "hubspot": ServiceConfig(
        name="HubSpot",
        category=ServiceCategory.CRM,
        login_url="https://app.hubspot.com",
        login_check_url="https://app.hubspot.com",
        login_indicators=["contacts", "deals", "dashboard"],
        logout_indicators=["log in", "sign up"],
        description="HubSpot CRM for B1, B2, D6, F3",
        required_for=["B1", "B2", "B4", "D6", "D7", "F3"]
    ),
    "salesforce": ServiceConfig(
        name="Salesforce",
        category=ServiceCategory.CRM,
        login_url="https://login.salesforce.com",
        login_check_url="https://login.salesforce.com",
        login_indicators=["home", "accounts", "opportunities"],
        logout_indicators=["username", "password", "log in"],
        description="Salesforce CRM",
        required_for=["B1", "B2", "D6"]
    ),
    "pipedrive": ServiceConfig(
        name="Pipedrive",
        category=ServiceCategory.CRM,
        login_url="https://app.pipedrive.com",
        login_check_url="https://app.pipedrive.com",
        login_indicators=["deals", "pipeline", "contacts"],
        logout_indicators=["log in", "sign up"],
        description="Pipedrive CRM",
        required_for=["B1", "B2", "D6"]
    ),

    # Project Management
    "trello": ServiceConfig(
        name="Trello",
        category=ServiceCategory.PROJECT_MGMT,
        login_url="https://trello.com/login",
        login_check_url="https://trello.com",
        login_indicators=["boards", "create", "workspaces"],
        logout_indicators=["log in", "sign up"],
        description="Trello for B7",
        required_for=["B7", "B8", "L8"]
    ),
    "asana": ServiceConfig(
        name="Asana",
        category=ServiceCategory.PROJECT_MGMT,
        login_url="https://app.asana.com",
        login_check_url="https://app.asana.com",
        login_indicators=["my tasks", "inbox", "projects"],
        logout_indicators=["log in", "sign up"],
        description="Asana for B7",
        required_for=["B7", "B8", "O5"]
    ),
    "notion": ServiceConfig(
        name="Notion",
        category=ServiceCategory.PROJECT_MGMT,
        login_url="https://notion.so/login",
        login_check_url="https://notion.so",
        login_indicators=["workspace", "pages", "search"],
        logout_indicators=["log in", "sign up"],
        description="Notion for docs and project management",
        required_for=["A4", "A7", "B7", "M5"]
    ),

    # E-commerce
    "shopify": ServiceConfig(
        name="Shopify Admin",
        category=ServiceCategory.ECOMMERCE,
        login_url="https://accounts.shopify.com/login",
        login_check_url="https://admin.shopify.com",
        login_indicators=["orders", "products", "customers", "analytics"],
        logout_indicators=["log in", "create account"],
        description="Shopify for C5, E1-E8",
        required_for=["C5", "E1", "E3", "E4", "E7"]
    ),
    "woocommerce": ServiceConfig(
        name="WooCommerce",
        category=ServiceCategory.ECOMMERCE,
        login_url="",  # Varies by store
        login_check_url="",
        login_indicators=["orders", "products", "woocommerce"],
        logout_indicators=["log in"],
        description="WooCommerce admin",
        required_for=["C5", "E1", "E3"]
    ),

    # Social Media
    "linkedin": ServiceConfig(
        name="LinkedIn",
        category=ServiceCategory.SOCIAL,
        login_url="https://www.linkedin.com/login",
        login_check_url="https://www.linkedin.com/feed",
        login_indicators=["feed", "my network", "messaging"],
        logout_indicators=["sign in", "join now"],
        description="LinkedIn for D1, D4, K2",
        required_for=["D1", "D4", "K2", "L1"]
    ),
    "twitter": ServiceConfig(
        name="Twitter/X",
        category=ServiceCategory.SOCIAL,
        login_url="https://twitter.com/login",
        login_check_url="https://twitter.com/home",
        login_indicators=["home", "explore", "messages"],
        logout_indicators=["log in", "sign up"],
        description="Twitter for K2",
        required_for=["K2"]
    ),
    "facebook": ServiceConfig(
        name="Facebook",
        category=ServiceCategory.SOCIAL,
        login_url="https://www.facebook.com/login",
        login_check_url="https://www.facebook.com",
        login_indicators=["home", "friends", "messenger"],
        logout_indicators=["log in", "create account"],
        description="Facebook for social and FB Ads",
        required_for=["D1", "K2"]
    ),

    # Documents
    "google_docs": ServiceConfig(
        name="Google Docs",
        category=ServiceCategory.DOCS,
        login_url="https://docs.google.com",
        login_check_url="https://docs.google.com",
        login_indicators=["recent", "owned by me", "shared"],
        logout_indicators=["sign in"],
        description="Google Docs for A4, G7",
        required_for=["A4", "G1", "G7", "L5", "M1"]
    ),

    # Spreadsheets
    "google_sheets": ServiceConfig(
        name="Google Sheets",
        category=ServiceCategory.SPREADSHEET,
        login_url="https://sheets.google.com",
        login_check_url="https://sheets.google.com",
        login_indicators=["recent", "owned by me"],
        logout_indicators=["sign in"],
        description="Google Sheets for B6, J8",
        required_for=["A5", "B6", "J8"]
    ),

    # Communication
    "slack": ServiceConfig(
        name="Slack",
        category=ServiceCategory.COMMUNICATION,
        login_url="https://slack.com/signin",
        login_check_url="",  # Varies by workspace
        login_indicators=["channels", "direct messages", "threads"],
        logout_indicators=["sign in", "create workspace"],
        description="Slack for B8, O8",
        required_for=["B8", "O8"]
    ),

    # Support
    "zendesk": ServiceConfig(
        name="Zendesk",
        category=ServiceCategory.SUPPORT,
        login_url="",  # Varies
        login_check_url="",
        login_indicators=["tickets", "views", "dashboard"],
        logout_indicators=["sign in"],
        description="Zendesk for C1-C8",
        required_for=["C1", "C2", "C3", "C8"]
    ),
    "freshdesk": ServiceConfig(
        name="Freshdesk",
        category=ServiceCategory.SUPPORT,
        login_url="",  # Varies
        login_check_url="",
        login_indicators=["tickets", "dashboard"],
        logout_indicators=["log in"],
        description="Freshdesk for support",
        required_for=["C1", "C2", "C8"]
    ),

    # Analytics
    "google_analytics": ServiceConfig(
        name="Google Analytics",
        category=ServiceCategory.ANALYTICS,
        login_url="https://analytics.google.com",
        login_check_url="https://analytics.google.com",
        login_indicators=["reports", "realtime", "audience"],
        logout_indicators=["sign in"],
        description="GA for K3, E7",
        required_for=["K3", "E7"]
    ),

    # Finance
    "quickbooks": ServiceConfig(
        name="QuickBooks",
        category=ServiceCategory.FINANCE,
        login_url="https://qbo.intuit.com",
        login_check_url="https://qbo.intuit.com",
        login_indicators=["dashboard", "transactions", "reports"],
        logout_indicators=["sign in"],
        description="QuickBooks for J1-J8",
        required_for=["J1", "J2", "J3", "J4", "J6"]
    ),
    "xero": ServiceConfig(
        name="Xero",
        category=ServiceCategory.FINANCE,
        login_url="https://login.xero.com",
        login_check_url="https://go.xero.com",
        login_indicators=["dashboard", "accounts", "reports"],
        logout_indicators=["log in"],
        description="Xero for finance",
        required_for=["J1", "J2", "J3"]
    ),

    # HR
    "bamboohr": ServiceConfig(
        name="BambooHR",
        category=ServiceCategory.HR,
        login_url="",  # Varies
        login_check_url="",
        login_indicators=["employees", "time off", "reports"],
        logout_indicators=["sign in"],
        description="BambooHR for L1-L8",
        required_for=["L1", "L2", "L8"]
    ),
    "greenhouse": ServiceConfig(
        name="Greenhouse",
        category=ServiceCategory.HR,
        login_url="https://app.greenhouse.io",
        login_check_url="https://app.greenhouse.io",
        login_indicators=["candidates", "jobs", "pipeline"],
        logout_indicators=["log in"],
        description="Greenhouse ATS",
        required_for=["L1", "L2", "L8"]
    ),

    # Real Estate
    "zillow": ServiceConfig(
        name="Zillow Premier Agent",
        category=ServiceCategory.REAL_ESTATE,
        login_url="https://www.zillow.com/agent-hub/login",
        login_check_url="https://www.zillow.com/agent-hub",
        login_indicators=["leads", "listings", "connections"],
        logout_indicators=["sign in"],
        description="Zillow for F1-F8",
        required_for=["F1", "F2", "F6"]
    ),
}


class LoginManager:
    """Manages login state and prompts for all services."""

    def __init__(self, state_file: str = "login_state.json", profile_manager=None):
        self.state_file = Path(state_file)
        self.logged_in_services: Set[str] = set()
        self.profile_manager = profile_manager
        self._load_state()

    def _load_state(self):
        """Load remembered login state."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.logged_in_services = set(data.get("logged_in", []))
            except Exception:
                self.logged_in_services = set()

    def _save_state(self):
        """Save login state."""
        self.state_file.write_text(json.dumps({
            "logged_in": list(self.logged_in_services)
        }))

    async def mark_logged_in(self, service_id: str, page=None, profile_name: str = "default"):
        """
        Mark a service as logged in.

        If profile_manager is available, also exports cookies/session data.

        Args:
            service_id: Service that was logged into
            page: Optional Playwright page object (for cookie export)
            profile_name: Profile name to save cookies to
        """
        self.logged_in_services.add(service_id)
        self._save_state()
        logger.info(f"Marked {service_id} as logged in")

        # Export session data if profile manager available
        if self.profile_manager and page:
            try:
                svc = SERVICES.get(service_id)
                if svc and svc.login_url:
                    # Extract domain from login URL
                    from urllib.parse import urlparse
                    domain = urlparse(svc.login_url).netloc

                    # Save session data
                    await self.profile_manager.on_successful_login(
                        profile_name=profile_name,
                        page=page,
                        domain=domain
                    )
            except Exception as e:
                logger.warning(f"Failed to export session data for {service_id}: {e}")

    def mark_logged_out(self, service_id: str):
        """Mark a service as logged out."""
        self.logged_in_services.discard(service_id)
        self._save_state()

    def is_logged_in(self, service_id: str) -> bool:
        """Check if we think user is logged in to a service."""
        return service_id in self.logged_in_services

    async def verify_login(
        self,
        service_id: str,
        browser,
        handle_challenges: bool = True,
        profile_name: str = "default"
    ) -> bool:
        """
        Verify login by actually checking the service. Updates state.

        Automatically attempts to restore saved session before checking.

        Args:
            service_id: Service identifier (e.g., 'gmail', 'linkedin')
            browser: Browser instance
            handle_challenges: If True, automatically handle CAPTCHA/2FA challenges
            profile_name: Profile name to restore session from

        Returns:
            True if logged in successfully, False otherwise
        """
        from .service_integrations import get_integration

        # Try to restore session first
        if self.profile_manager and browser and hasattr(browser, 'page'):
            try:
                svc = SERVICES.get(service_id)
                if svc and svc.login_url:
                    from urllib.parse import urlparse
                    domain = urlparse(svc.login_url).netloc

                    # Restore session if available
                    restored = await self.profile_manager.restore_session(
                        profile_name=profile_name,
                        page=browser.page,
                        domain=domain
                    )

                    if restored:
                        logger.info(f"Restored saved session for {service_id}")
            except Exception as e:
                logger.debug(f"Failed to restore session for {service_id}: {e}")

        integration = get_integration(service_id, browser)
        if integration:
            is_logged_in = await integration.check_login()

            # If not logged in and challenges enabled, check for auth challenges
            if not is_logged_in and handle_challenges:
                try:
                    from .captcha_solver import AuthChallengeManager
                    page = await browser.new_page()

                    # Navigate to login URL
                    svc = SERVICES.get(service_id)
                    if svc and svc.login_url:
                        await page.goto(svc.login_url)

                        # Check for challenges
                        auth_manager = AuthChallengeManager(page)
                        challenges_resolved = await auth_manager.check_and_handle_challenges()

                        if challenges_resolved:
                            # Re-check login status
                            is_logged_in = await integration.check_login()

                    await page.close()
                except Exception as e:
                    logger.error(f"Error checking auth challenges: {e}")

            if is_logged_in:
                await self.mark_logged_in(
                    service_id,
                    page=browser.page if hasattr(browser, 'page') else None,
                    profile_name=profile_name
                )
            else:
                self.mark_logged_out(service_id)
            return is_logged_in
        return False

    def get_services_for_capability(self, capability_code: str) -> List[ServiceConfig]:
        """Get services required for a specific capability."""
        return [
            svc for svc in SERVICES.values()
            if capability_code in svc.required_for
        ]

    def get_login_prompt(self, service_id: str) -> str:
        """Generate a login prompt for a service."""
        if service_id not in SERVICES:
            return f"Please log into {service_id} in the browser."

        svc = SERVICES[service_id]
        return f"""
To proceed, please log into **{svc.name}**:

1. Open a new tab in the browser
2. Go to: {svc.login_url}
3. Log in with your credentials
4. Once logged in, say "continue" or "logged in"

The browser uses an isolated profile (~/.eversale/browser-profile), so your session will be saved for future Eversale sessions without affecting your normal Chrome.
"""

    def get_required_logins(self, capability_codes: List[str]) -> List[str]:
        """Get all services that need login for given capabilities."""
        required = set()
        for code in capability_codes:
            for svc_id, svc in SERVICES.items():
                if code in svc.required_for and svc_id not in self.logged_in_services:
                    required.add(svc_id)
        return list(required)

    def format_login_checklist(self, service_ids: List[str]) -> str:
        """Format a checklist of services that need login."""
        if not service_ids:
            return "All required services are already logged in."

        lines = ["**Please log into these services before we continue:**\n"]
        for svc_id in service_ids:
            svc = SERVICES.get(svc_id)
            if svc:
                lines.append(f"- [ ] **{svc.name}** - {svc.login_url}")
            else:
                lines.append(f"- [ ] {svc_id}")

        lines.append("\n*Open each in a browser tab, log in, then say 'ready' when done.*")
        return "\n".join(lines)

    async def login_with_challenge_handling(self, service_id: str, page, timeout: int = 300) -> bool:
        """
        Perform login with automatic CAPTCHA and 2FA handling.

        Args:
            service_id: Service to login to
            page: Playwright page object
            timeout: Timeout for manual challenge resolution (seconds)

        Returns:
            True if login successful (including challenge resolution), False otherwise
        """
        from .captcha_solver import AuthChallengeManager

        svc = SERVICES.get(service_id)
        if not svc:
            logger.error(f"Unknown service: {service_id}")
            return False

        try:
            # Navigate to login URL
            logger.info(f"[LOGIN] Navigating to {svc.name} login page")
            await page.goto(svc.login_url)

            # Check for challenges before login
            auth_manager = AuthChallengeManager(page)
            await auth_manager.check_and_handle_challenges(manual_timeout=timeout)

            # Wait for user to enter credentials (if not already logged in)
            logger.info(f"[LOGIN] Please complete login for {svc.name}")
            logger.info(f"[LOGIN] Type 'continue' when done")

            # Check for challenges after login attempt
            challenges_resolved = await auth_manager.check_and_handle_challenges(manual_timeout=timeout)

            if challenges_resolved:
                # Verify login by checking for login indicators
                is_logged_in = await self._check_login_indicators(page, svc)

                if is_logged_in:
                    await self.mark_logged_in(
                        service_id,
                        page=page,
                        profile_name="default"
                    )
                    logger.success(f"[LOGIN] Successfully logged into {svc.name}")
                    return True

            logger.warning(f"[LOGIN] Failed to login to {svc.name}")
            return False

        except Exception as e:
            logger.error(f"[LOGIN] Error during login to {service_id}: {e}")
            return False

    async def _check_login_indicators(self, page, svc: ServiceConfig) -> bool:
        """Check if page contains login success indicators."""
        try:
            page_text = await page.evaluate('() => document.body.innerText.toLowerCase()')

            # Check for login indicators
            for indicator in svc.login_indicators:
                if indicator.lower() in page_text:
                    return True

            # Check for logout indicators (means not logged in)
            for indicator in svc.logout_indicators:
                if indicator.lower() in page_text:
                    return False

            # If no clear indicators, assume logged in
            return True

        except Exception as e:
            logger.error(f"[LOGIN] Error checking login indicators: {e}")
            return False


# Capability to service mapping for quick lookup
CAPABILITY_SERVICES = {
    # A - Administrative
    "A1": ["gmail", "outlook"],  # Email triage
    "A2": ["google_calendar"],   # Calendar scheduling
    "A3": ["google_docs", "notion"],  # Meeting prep
    "A4": ["google_docs"],       # Document creation
    "A5": ["google_sheets"],     # Data entry
    "A6": [],                    # Extract fields (local)
    "A7": ["google_docs", "notion"],  # SOPs
    "A8": [],                    # Reports (local)

    # B - Business Ops
    "B1": ["hubspot", "salesforce", "pipedrive"],
    "B2": ["hubspot", "salesforce", "pipedrive"],
    "B3": [],  # Data enrichment (web scraping)
    "B4": ["hubspot", "salesforce"],
    "B5": [],  # Internal reporting
    "B6": ["google_sheets"],
    "B7": ["trello", "asana", "notion"],
    "B8": ["slack"],

    # C - Customer Support
    "C1": ["zendesk", "freshdesk"],
    "C2": ["zendesk", "freshdesk", "gmail"],
    "C3": ["zendesk", "freshdesk"],
    "C4": [],  # Policy-based (local)
    "C5": ["shopify", "woocommerce"],
    "C6": [],  # FAQ (local)
    "C7": [],  # CSAT analysis (local)
    "C8": ["zendesk", "freshdesk"],

    # D - Sales/SDR
    "D1": ["linkedin", "facebook"],
    "D2": ["gmail", "outlook"],
    "D3": ["gmail", "outlook"],
    "D4": ["linkedin"],
    "D5": [],  # Web scraping
    "D6": ["hubspot", "salesforce", "pipedrive"],
    "D7": ["hubspot", "salesforce"],
    "D8": [],  # Reports

    # E - E-commerce
    "E1": ["shopify"],
    "E2": ["gmail", "shopify"],
    "E3": ["shopify"],
    "E4": ["shopify"],
    "E5": [],  # Ad copy (local)
    "E6": [],  # Marketing emails (local)
    "E7": ["shopify", "google_analytics"],
    "E8": [],  # UGC review (local)

    # F - Real Estate
    "F1": [],  # Listing description (local)
    "F2": ["gmail", "zillow"],
    "F3": ["hubspot"],
    "F4": [],  # Document summaries (local)
    "F5": ["google_calendar"],
    "F6": ["zillow"],
    "F7": ["gmail"],
    "F8": [],  # Comparison sheets (local)

    # G - Legal (admin only)
    "G1": ["google_docs"],
    "G2": [],  # Extract clauses (local)
    "G3": [],  # Organize docs (local)
    "G4": [],  # Timelines (local)
    "G5": [],  # Intake forms (local)
    "G6": ["gmail"],
    "G7": ["google_docs"],
    "G8": [],  # Evidence lists (local)

    # H - Logistics
    "H1": [],  # Shipment summaries (local)
    "H2": [],  # Delay detection (local)
    "H3": [],  # Customs docs (local)
    "H4": ["gmail"],
    "H5": [],  # Inventory reports (local)
    "H6": [],  # ETA consolidation (local)
    "H7": [],  # PO summaries (local)
    "H8": [],  # Issue flagging (local)

    # I - Industrial
    "I1": [],  # Safety docs (local)
    "I2": [],  # Compliance checklists (local)
    "I3": [],  # Audit paperwork (local)
    "I4": [],  # Maintenance logs (local)
    "I5": [],  # Inspection reports (local)
    "I6": [],  # SOP comparison (local)
    "I7": ["google_calendar"],
    "I8": [],  # Quality reports (local)

    # J - Finance
    "J1": ["quickbooks", "xero"],
    "J2": ["quickbooks", "xero"],
    "J3": ["quickbooks", "xero"],
    "J4": ["quickbooks", "xero"],
    "J5": [],  # Match receipts (local)
    "J6": ["quickbooks"],
    "J7": ["gmail"],
    "J8": ["google_sheets"],

    # K - Marketing
    "K1": [],  # Newsletters (local)
    "K2": ["linkedin", "twitter", "facebook"],
    "K3": ["google_analytics"],
    "K4": [],  # Ad copy (local)
    "K5": [],  # Competitor research (web)
    "K6": [],  # Keywords (local)
    "K7": [],  # Landing pages (local)
    "K8": [],  # Personas (local)

    # L - HR/Recruiting
    "L1": ["linkedin", "bamboohr", "greenhouse"],
    "L2": ["bamboohr", "greenhouse"],
    "L3": ["gmail"],
    "L4": [],  # Interview sheets (local)
    "L5": ["google_docs"],
    "L6": [],  # Interview summaries (local)
    "L7": [],  # Job descriptions (local)
    "L8": ["trello", "bamboohr", "greenhouse"],

    # M - Education
    "M1": ["google_docs"],
    "M2": [],  # Lesson plans (local)
    "M3": [],  # Quizzes (local)
    "M4": [],  # Flashcards (local)
    "M5": ["notion"],
    "M6": [],  # Analyze submissions (local)
    "M7": [],  # Study guides (local)
    "M8": ["gmail"],

    # N - Government Admin
    "N1": [],  # Form extraction (local)
    "N2": [],  # Case summaries (local)
    "N3": [],  # Public records (local)
    "N4": ["gmail"],
    "N5": [],  # Report generation (local)
    "N6": [],  # Meeting minutes (local)
    "N7": [],  # SOP rewriting (local)
    "N8": [],  # Intake triage (local)

    # O - IT/Engineering
    "O1": [],  # Log summarization (local)
    "O2": [],  # Bug triage (local)
    "O3": [],  # Release notes (local)
    "O4": [],  # Documentation (local)
    "O5": ["asana", "trello"],
    "O6": [],  # Code comments (local)
    "O7": [],  # Data cleanup scripts (local)
    "O8": ["slack"],
}


def get_login_requirements(capability_codes: List[str]) -> Dict[str, List[str]]:
    """Get all login requirements for a set of capabilities."""
    requirements = {}
    for code in capability_codes:
        services = CAPABILITY_SERVICES.get(code, [])
        if services:
            requirements[code] = services
    return requirements
