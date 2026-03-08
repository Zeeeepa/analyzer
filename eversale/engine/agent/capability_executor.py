"""
Capability Executor - Executes business capabilities (A-AE).

This module handles routing and execution of the 31 business capabilities
that Eversale supports across different industries.
"""
import logging
import inspect
from typing import Optional, TYPE_CHECKING
from rich.console import Console

if TYPE_CHECKING:
    from .capability_router import CapabilityRouter

logger = logging.getLogger(__name__)
console = Console()


# Capability letter -> method name mapping (A-AE)
CAP_METHODS = {
    # A-O (Original capabilities)
    'A': 'admin_triage_inbox',
    'B': 'backoffice_clean_spreadsheet',
    'C': 'custops_classify_tickets',
    'D': 'sales_research_company',
    'E': 'ecommerce_product_description',
    'F': 'realestate_summarize_report',
    'G': 'legal_extract_contract',
    'H': 'logistics_shipping_summary',
    'I': 'industrial_maintenance_analysis',
    'J': 'finance_categorize_transactions',
    'K': 'marketing_analytics_insights',
    'L': 'hr_compare_resumes',
    'M': 'education_create_quiz',
    'N': 'government_extract_form',
    'O': 'it_summarize_logs',
    # P-AE (Extended capabilities)
    'P': 'insurance_process_claim',
    'Q': 'banking_monitor_account',
    'R': 'procurement_research_vendors',
    'S': 'enterprise_admin_workflow',
    'T': 'contractor_permit_workflow',
    'U': 'recruiting_pipeline_workflow',
    'V': 'audit_compliance_workflow',
    'W': 'content_moderation_workflow',
    'X': 'inventory_reconciliation_workflow',
    'Y': 'research_automation_workflow',
    'Z': 'enterprise_monitoring_workflow',
    'AA': 'healthcare_admin_workflow',
    'AB': 'travel_management_workflow',
    'AC': 'food_service_workflow',
    'AD': 'nonprofit_fundraising_workflow',
    'AE': 'media_pr_workflow',
}


class CapabilityExecutor:
    """
    Executes business capabilities by routing prompts to specific handlers.

    Capabilities are organized A-AE covering 31 different industries from
    admin tasks to media/PR workflows.
    """

    def __init__(self, capability_router: Optional['CapabilityRouter'] = None, stats: Optional[dict] = None):
        """
        Initialize capability executor.

        Args:
            capability_router: Router for matching prompts to capabilities
            stats: Stats dictionary to track tool calls
        """
        self.capability_router = capability_router
        self.stats = stats or {}

    async def try_capability(self, prompt: str) -> Optional[str]:
        """
        Try to route to a business capability (A-AE).

        Args:
            prompt: User prompt to route

        Returns:
            Capability output if successfully routed, None otherwise
        """
        if not self.capability_router:
            return None

        match = self.capability_router.route(prompt)
        if not match or match.confidence < 0.5:
            return None

        try:
            from .capabilities import Capabilities
            caps = Capabilities()

            console.print(f"[green]Auto-routing to capability {match.capability}: {match.capability_name}[/green]")
            console.print(f"[dim]Confidence: {match.confidence:.0%} - {match.reasoning}[/dim]")

            # Get method name from mapping
            method_name = CAP_METHODS.get(match.capability)
            if not method_name:
                return None

            # Get the actual method from caps object
            method = getattr(caps, method_name, None)
            if not method:
                return None

            # Execute capability with extracted params
            params = match.extracted_params
            result = await self.execute_capability(method, params, match.capability)

            if result and result.success:
                self.stats['tool_calls'] = self.stats.get('tool_calls', 0) + 1
                return result.output

            return None

        except Exception as e:
            logger.warning(f"Capability {match.capability} failed: {e}")
            return None

    async def execute_capability(self, method, params: dict, cap_letter: str):
        """
        Execute a capability method with appropriate parameters.

        Args:
            method: Capability method to execute
            params: Extracted parameters from prompt
            cap_letter: Capability letter (A-AE)

        Returns:
            Capability result or None if execution failed
        """
        # Get method signature
        sig = inspect.signature(method)
        param_names = list(sig.parameters.keys())

        # Build args based on what the method expects
        kwargs = {}

        for name in param_names:
            if name in params and params[name] is not None:
                kwargs[name] = params[name]
            elif name == 'file_path' and params.get('file_path'):
                kwargs['file_path'] = params['file_path']
            elif name == 'company_name' and params.get('company_name'):
                kwargs['company_name'] = params['company_name']
            elif name == 'product_name' and params.get('product_name'):
                kwargs['product_name'] = params['product_name']
            elif name == 'content_path' and params.get('content_path'):
                kwargs['content_path'] = params['content_path']

        # Call method
        try:
            result = method(**kwargs) if kwargs else method()

            # Check if this is a placeholder workflow that needs ReAct
            if result and not result.success and result.error and result.error.endswith("_needs_react"):
                logger.info(f"Capability {cap_letter} needs ReAct loop - falling through")
                return None

            return result
        except TypeError as e:
            # Missing required params - let it fall through to ReAct
            logger.debug(f"Capability {cap_letter} needs more params: {e}")
            return None
