"""
Business Automation Tools - Unified registry for all business automation capabilities
Supports use cases A-O across all industries
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Import processors
from agent.document_processor import DocumentProcessor
from agent.content_generator import ContentGenerator
from agent.workspace_paths import get_workspace_root_path

# ============================================================================
# UNIFIED TOOL REGISTRY
# ============================================================================

class BusinessTools:
    """
    Unified interface for all business automation tools.

    Supported Use Cases:
    A) Admin - Email inbox processing, summarization, reply drafting
    B) Back-office - Spreadsheet cleaning and CSV normalization
    C) Customer Operations - Support ticket classification and replies
    D) Sales/SDR - Prospecting (handled by playwright tools)
    E) E-commerce - Product descriptions from specs/images
    F) Real Estate - Inspection reports and MLS listings
    G) Legal/Admin - Contract entity extraction
    H) Logistics - Shipping updates and delay detection
    I) Industrial - Maintenance log analysis
    J) Finance/Accounting - Transaction categorization
    K) Marketing - Analytics insights and experiments
    L) HR/Recruiting - Resume parsing and scoring
    M) Education - Quiz generation from content
    N) Government - Form field extraction to JSON
    O) IT/Engineering - Log file analysis and Jira tickets
    """

    def __init__(self):
        self.document_processor = DocumentProcessor()
        self.content_generator = ContentGenerator()
        workspace_root = get_workspace_root_path()
        self._output_dir = workspace_root / "output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def get_all_tools(self) -> Dict[str, Dict]:
        """Get all available business automation tools"""
        tools = {}

        # Document processor tools (A, B, C, G, J, L, O)
        tools.update(self.document_processor.get_tools())

        # Content generator tools (E, F, H, I, K, M, N)
        tools.update(self.content_generator.get_tools())

        # Add meta tools
        tools.update({
            "list_capabilities": {
                "description": "List all available business automation capabilities",
                "parameters": {}
            },
            "save_output": {
                "description": "Save processed output to file (CSV, JSON, or text)",
                "parameters": {
                    "filename": {"type": "string", "description": "Output filename"},
                    "content": {"type": "string", "description": "Content to save"},
                    "format": {"type": "string", "description": "Format: csv, json, txt, md"}
                }
            }
        })

        return tools

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Route tool call to appropriate processor"""

        # Document processor tools
        doc_tools = ['process_emails', 'clean_spreadsheet', 'classify_tickets',
                     'extract_contract', 'process_transactions', 'analyze_resumes', 'analyze_logs']

        # Content generator tools
        content_tools = ['generate_product_listing', 'process_inspection_report',
                         'process_shipping_updates', 'analyze_maintenance_logs',
                         'analyze_marketing_data', 'generate_quiz', 'extract_form_fields']

        try:
            if tool_name in doc_tools:
                return await self.document_processor.call_tool(tool_name, params)

            elif tool_name in content_tools:
                return await self.content_generator.call_tool(tool_name, params)

            elif tool_name == "list_capabilities":
                return self._list_capabilities()

            elif tool_name == "save_output":
                return self._save_output(params)

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"Tool error ({tool_name}): {e}")
            return {"error": str(e)}

    def _list_capabilities(self) -> Dict[str, Any]:
        """List all business automation capabilities"""
        return {
            "success": True,
            "capabilities": {
                "A_admin": {
                    "name": "Admin - Email Processing",
                    "tool": "process_emails",
                    "description": "Read inbox, summarize emails, draft replies for action items"
                },
                "B_backoffice": {
                    "name": "Back-office - Spreadsheet Cleaning",
                    "tool": "clean_spreadsheet",
                    "description": "Clean and normalize messy spreadsheet data to structured CSV"
                },
                "C_customer_ops": {
                    "name": "Customer Operations - Ticket Classification",
                    "tool": "classify_tickets",
                    "description": "Classify support tickets and draft appropriate replies"
                },
                "D_sales_sdr": {
                    "name": "Sales/SDR - Prospecting",
                    "tool": "playwright_* tools",
                    "description": "Research companies, find contacts, generate outbound emails"
                },
                "E_ecommerce": {
                    "name": "E-commerce - Product Descriptions",
                    "tool": "generate_product_listing",
                    "description": "Create product descriptions, bullets, and FAQ from specs"
                },
                "F_real_estate": {
                    "name": "Real Estate - Inspection Reports",
                    "tool": "process_inspection_report",
                    "description": "Summarize inspection reports and create MLS listings"
                },
                "G_legal": {
                    "name": "Legal/Admin - Contract Extraction",
                    "tool": "extract_contract",
                    "description": "Extract parties, dates, amounts, obligations from contracts"
                },
                "H_logistics": {
                    "name": "Logistics - Shipping Updates",
                    "tool": "process_shipping_updates",
                    "description": "Track shipments, detect delays, generate action summaries"
                },
                "I_industrial": {
                    "name": "Industrial - Maintenance Analysis",
                    "tool": "analyze_maintenance_logs",
                    "description": "Analyze maintenance logs, identify patterns and root causes"
                },
                "J_finance": {
                    "name": "Finance/Accounting - Transaction Processing",
                    "tool": "process_transactions",
                    "description": "Categorize transactions, detect anomalies, monthly summary"
                },
                "K_marketing": {
                    "name": "Marketing - Analytics Insights",
                    "tool": "analyze_marketing_data",
                    "description": "Analyze metrics, generate insights and experiment ideas"
                },
                "L_hr": {
                    "name": "HR/Recruiting - Resume Analysis",
                    "tool": "analyze_resumes",
                    "description": "Parse resumes, score against requirements, comparison table"
                },
                "M_education": {
                    "name": "Education - Quiz Generation",
                    "tool": "generate_quiz",
                    "description": "Create quiz, answer key, and study guide from content"
                },
                "N_government": {
                    "name": "Government Admin - Form Extraction",
                    "tool": "extract_form_fields",
                    "description": "Extract form fields and structure as JSON"
                },
                "O_it_engineering": {
                    "name": "IT/Engineering - Log Analysis",
                    "tool": "analyze_logs",
                    "description": "Analyze logs, summarize errors, suggest Jira tickets"
                }
            }
        }

    def _save_output(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Save output to file"""
        filename = params.get('filename', 'output')
        content = params.get('content', '')
        fmt = params.get('format', 'txt')

        # Sanitize filename
        filename = "".join(c for c in filename if c.isalnum() or c in '._-')
        if not filename.endswith(f'.{fmt}'):
            filename = f"{filename}.{fmt}"

        filepath = self._output_dir / filename

        try:
            if fmt == 'json':
                # Try to parse and pretty-print JSON
                try:
                    data = json.loads(content) if isinstance(content, str) else content
                    content = json.dumps(data, indent=2)
                except (json.JSONDecodeError, TypeError):
                    pass

            with open(filepath, 'w') as f:
                f.write(content)

            return {
                "success": True,
                "filepath": str(filepath),
                "size": len(content)
            }

        except Exception as e:
            return {"error": f"Failed to save: {e}"}


# ============================================================================
# QUICK ACCESS FUNCTIONS
# ============================================================================

async def process_inbox(email_content: str) -> Dict[str, Any]:
    """A) Process email inbox - summarize and draft replies"""
    tools = BusinessTools()
    return await tools.call_tool('process_emails', {'content': email_content})


async def clean_csv(spreadsheet_content: str) -> Dict[str, Any]:
    """B) Clean and normalize spreadsheet data"""
    tools = BusinessTools()
    return await tools.call_tool('clean_spreadsheet', {'content': spreadsheet_content})


async def classify_support_tickets(tickets_content: str) -> Dict[str, Any]:
    """C) Classify support tickets and draft replies"""
    tools = BusinessTools()
    return await tools.call_tool('classify_tickets', {'content': tickets_content})


async def generate_product_content(specs: Dict, images_desc: str = "") -> Dict[str, Any]:
    """E) Generate product description from specs"""
    tools = BusinessTools()
    return await tools.call_tool('generate_product_listing', {
        'specs': specs,
        'images_description': images_desc
    })


async def process_inspection(report_content: str, property_info: Dict = None) -> Dict[str, Any]:
    """F) Process inspection report and create MLS listing"""
    tools = BusinessTools()
    return await tools.call_tool('process_inspection_report', {
        'content': report_content,
        'property_info': property_info or {}
    })


async def extract_contract_data(contract_text: str) -> Dict[str, Any]:
    """G) Extract entities from contract"""
    tools = BusinessTools()
    return await tools.call_tool('extract_contract', {'content': contract_text})


async def track_shipments(shipping_data: str) -> Dict[str, Any]:
    """H) Process shipping updates and detect delays"""
    tools = BusinessTools()
    return await tools.call_tool('process_shipping_updates', {'content': shipping_data})


async def analyze_maintenance(log_content: str) -> Dict[str, Any]:
    """I) Analyze maintenance logs"""
    tools = BusinessTools()
    return await tools.call_tool('analyze_maintenance_logs', {'content': log_content})


async def categorize_transactions(transaction_data: str) -> Dict[str, Any]:
    """J) Categorize financial transactions"""
    tools = BusinessTools()
    return await tools.call_tool('process_transactions', {'content': transaction_data})


async def analyze_marketing_metrics(analytics_data: str) -> Dict[str, Any]:
    """K) Analyze marketing data and generate insights"""
    tools = BusinessTools()
    return await tools.call_tool('analyze_marketing_data', {'content': analytics_data})


async def score_resumes(resume_content: str, requirements: Dict = None) -> Dict[str, Any]:
    """L) Parse and score resumes"""
    tools = BusinessTools()
    return await tools.call_tool('analyze_resumes', {
        'content': resume_content,
        'requirements': requirements or {}
    })


async def create_quiz(educational_content: str, num_questions: int = 10) -> Dict[str, Any]:
    """M) Generate quiz from educational content"""
    tools = BusinessTools()
    return await tools.call_tool('generate_quiz', {
        'content': educational_content,
        'num_questions': num_questions
    })


async def extract_form_data(form_content: str, form_type: str = "") -> Dict[str, Any]:
    """N) Extract form fields to JSON"""
    tools = BusinessTools()
    return await tools.call_tool('extract_form_fields', {
        'content': form_content,
        'form_type': form_type
    })


async def analyze_system_logs(log_content: str) -> Dict[str, Any]:
    """O) Analyze system logs and suggest Jira tickets"""
    tools = BusinessTools()
    return await tools.call_tool('analyze_logs', {'content': log_content})


# ============================================================================
# TOOL REGISTRATION FOR AGENT
# ============================================================================

def register_business_tools() -> Dict[str, Dict]:
    """Register all business tools for the agent"""
    tools = BusinessTools()
    return tools.get_all_tools()


def get_business_tool_descriptions() -> str:
    """Get formatted descriptions of all business tools"""
    capabilities = BusinessTools()._list_capabilities()['capabilities']

    desc = "BUSINESS AUTOMATION TOOLS:\n\n"
    for key, cap in capabilities.items():
        desc += f"{key.upper()}) {cap['name']}\n"
        desc += f"   Tool: {cap['tool']}\n"
        desc += f"   {cap['description']}\n\n"

    return desc
