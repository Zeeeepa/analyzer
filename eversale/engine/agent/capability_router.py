"""
Capability Router - Auto-detect when to use business capabilities.

Maps natural language prompts to the appropriate capability (A-O).
"""

import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class CapabilityMatch:
    """Result of capability matching."""
    capability: str  # Letter A-O or None
    capability_name: str
    confidence: float
    extracted_params: Dict
    reasoning: str


# ============ Parameter Extractors (defined first) ============

def _extract_file_path(prompt: str) -> Dict:
    """Extract file path from prompt."""
    patterns = [
        r'[\'"]([^"\']+\.[a-z]{2,4})[\'"]',  # Quoted paths
        r'(\S+\.(?:csv|xlsx?|pdf|txt|log|json))',  # File extensions
        r'(?:file|path):\s*(\S+)',  # Explicit file: prefix
    ]

    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return {'file_path': match.group(1)}

    return {'file_path': None}  # Will prompt user


def _extract_company_name(prompt: str) -> Dict:
    """Extract company name from prompt."""
    patterns = [
        r'research\s+(?:the\s+)?company\s+["\']?(\w+)',
        r'(?:about|on)\s+["\']?(\w+)["\']?\s*(?:company)?',
        r'company\s+["\']?(\w+)',
        r'(?:research|look up)\s+["\']?(\w+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            name = match.group(1)
            # Filter out common words
            if name.lower() not in ['the', 'a', 'this', 'that', 'for', 'about']:
                return {'company_name': name}

    return {'company_name': None}


def _extract_product_info(prompt: str) -> Dict:
    """Extract product info from prompt."""
    params = {}

    # Product name
    name_match = re.search(r'(?:product|for)\s+["\']?([^"\']+)["\']?', prompt, re.IGNORECASE)
    if name_match:
        params['product_name'] = name_match.group(1).strip()

    # Image path
    image_match = re.search(r'image:\s*(\S+)|(\S+\.(?:png|jpg|jpeg|webp))', prompt, re.IGNORECASE)
    if image_match:
        params['image_path'] = image_match.group(1) or image_match.group(2)

    return params if params else {'product_name': None}


def _extract_resume_info(prompt: str) -> Dict:
    """Extract resume file paths and job requirements."""
    params = {'resume_paths': []}

    # Find all file paths
    file_pattern = r'(\S+\.(?:pdf|docx?|txt))'
    files = re.findall(file_pattern, prompt, re.IGNORECASE)
    if files:
        params['resume_paths'] = files

    # Job requirements
    req_match = re.search(r'(?:for|requirements?:)\s*["\']?([^"\']+)["\']?', prompt, re.IGNORECASE)
    if req_match:
        params['job_requirements'] = req_match.group(1).strip()

    return params


def _extract_quiz_info(prompt: str) -> Dict:
    """Extract quiz parameters."""
    params = {}

    # Number of questions
    num_match = re.search(r'(\d+)\s*questions?', prompt, re.IGNORECASE)
    if num_match:
        params['num_questions'] = int(num_match.group(1))

    # Content file
    file_match = re.search(r'from\s+["\']?(\S+)["\']?', prompt, re.IGNORECASE)
    if file_match:
        params['content_path'] = file_match.group(1)

    return params if params else {'content_path': None}


# ============ Capability Patterns ============

CAPABILITY_PATTERNS = {
    'A': {
        'name': 'Admin Inbox Triage',
        'triggers': [
            r'triage\s+(?:my\s+)?(?:inbox|emails?)',
            r'sort\s+(?:my\s+)?(?:inbox|emails?)',
            r'prioritize\s+(?:my\s+)?(?:inbox|emails?)',
            r'organize\s+(?:my\s+)?emails?',
            r'inbox\s+(?:triage|management)',
            r'email\s+triage',
        ],
        'keywords': ['inbox', 'email', 'triage', 'prioritize', 'urgent', 'sort'],
        'param_extractor': lambda p: {'emails': 'from_prompt'},
    },
    'B': {
        'name': 'Back-office Spreadsheet Clean',
        'triggers': [
            r'clean\s+(?:up\s+)?(?:this\s+)?spreadsheet',
            r'clean\s+(?:this\s+)?(?:csv|excel|xlsx)',
            r'fix\s+(?:the\s+)?data\s+(?:in|from)',
            r'normalize\s+(?:the\s+)?(?:spreadsheet|data)',
            r'dedupe\s+(?:this\s+|the\s+)?(?:spreadsheet|data|file)',
            r'standardize\s+(?:the\s+)?(?:spreadsheet|data)',
        ],
        'keywords': ['spreadsheet', 'csv', 'excel', 'clean', 'normalize', 'dedupe', 'fix data'],
        'param_extractor': _extract_file_path,
    },
    'C': {
        'name': 'CustOps Ticket Classification',
        'triggers': [
            r'classify\s+(?:these\s+)?(?:support\s+|customer\s+)?tickets?',
            r'categorize\s+(?:these\s+)?(?:support\s+)?(?:tickets?|requests?)',
            r'sort\s+(?:these\s+)?tickets?\s+by',
            r'ticket\s+classification',
            r'support\s+(?:ticket\s+)?(?:triage|sorting|requests?)',
        ],
        'keywords': ['ticket', 'support', 'classify', 'categorize', 'customer', 'requests'],
        'param_extractor': lambda p: {'tickets': 'from_prompt'},
    },
    'D': {
        'name': 'Sales Company Research',
        'triggers': [
            r'research\s+(?:the\s+)?company\s+(\w+)',
            r'research\s+(\w+)',  # Simple "research X"
            r'look\s+up\s+(?:the\s+)?(?:company\s+)?(\w+)',
            r'find\s+(?:info|information)\s+(?:about|on)\s+(\w+)',
            r'company\s+research\s+(?:for|on)\s+(\w+)',
            r'tell\s+me\s+about\s+(\w+)\s+(?:company|business)',
            r'what\s+(?:do\s+)?(?:you\s+)?know\s+about\s+(\w+)',
            r'(\w+)\s+company',  # "Salesforce company"
        ],
        'keywords': ['research', 'company', 'business', 'look up', 'find info'],
        'param_extractor': _extract_company_name,
    },
    'E': {
        'name': 'E-commerce Product Description',
        'triggers': [
            r'(?:write|create|generate)\s+(?:a\s+)?product\s+description',
            r'describe\s+(?:this\s+)?product',
            r'product\s+(?:listing|description)\s+(?:for|about)',
            r'e-?commerce\s+(?:listing|description)',
            r'(?:write|create)\s+listing\s+for',
            r'product\s+description\s+for\s+\w+',
        ],
        'keywords': ['product', 'description', 'listing', 'e-commerce', 'ecommerce'],
        'param_extractor': _extract_product_info,
    },
    'F': {
        'name': 'Real Estate Report Summary',
        'triggers': [
            r'summarize\s+(?:this\s+)?(?:property|real\s*estate|inspection)\s+report',
            r'(?:property|real\s*estate|inspection)\s+report\s+(?:summary|analysis)',
            r'analyze\s+(?:this\s+)?(?:property|inspection)\s+(?:report)?',
            r'what\s+does\s+(?:this\s+)?(?:property|inspection)\s+report\s+say',
        ],
        'keywords': ['property', 'real estate', 'inspection', 'report', 'summary', 'appraisal'],
        'param_extractor': _extract_file_path,
    },
    'G': {
        'name': 'Legal Contract Extraction',
        'triggers': [
            r'extract\s+(?:from\s+)?(?:this\s+)?contract',
            r'extract\s+(?:clauses|terms)\s+from\s+contract',
            r'analyze\s+(?:this\s+)?(?:contract|legal\s+document)',
            r'(?:pull|get)\s+(?:key\s+)?(?:terms|clauses|dates)\s+from\s+contract',
            r'contract\s+(?:analysis|extraction|review)',
            r'legal\s+document\s+(?:analysis|extraction)',
        ],
        'keywords': ['contract', 'legal', 'extract', 'terms', 'clauses', 'agreement', 'document'],
        'param_extractor': _extract_file_path,
    },
    'H': {
        'name': 'Logistics Shipping Summary',
        'triggers': [
            r'summarize\s+(?:these\s+)?shipping\s+(?:updates|status)',
            r'shipping\s+(?:summary|overview)',
            r'logistics\s+(?:summary|report)',
            r'track(?:ing)?\s+summary',
            r'delivery\s+status\s+(?:summary|report)',
        ],
        'keywords': ['shipping', 'logistics', 'tracking', 'delivery', 'updates'],
        'param_extractor': lambda p: {'updates': 'from_prompt'},
    },
    'I': {
        'name': 'Industrial Maintenance Analysis',
        'triggers': [
            r'analyze\s+(?:this\s+)?(?:maintenance|equipment)\s+log',
            r'maintenance\s+(?:log\s+)?(?:analysis|report|review)',
            r'equipment\s+(?:log|maintenance)\s+(?:analysis|review)',
            r'predictive\s+maintenance',
            r'(?:find|identify)\s+maintenance\s+(?:issues|patterns)',
        ],
        'keywords': ['maintenance', 'equipment', 'log', 'industrial', 'predictive'],
        'param_extractor': _extract_file_path,
    },
    'J': {
        'name': 'Finance Transaction Categorization',
        'triggers': [
            r'categorize\s+(?:these\s+)?(?:transactions?|expenses?)',
            r'classify\s+(?:these\s+)?(?:bank\s+)?transactions?',
            r'transaction\s+(?:categorization|classification|sorting)',
            r'sort\s+(?:my\s+)?(?:bank\s+)?transactions?',
            r'expense\s+(?:categorization|classification)',
        ],
        'keywords': ['transaction', 'categorize', 'bank', 'expense', 'finance', 'sorting'],
        'param_extractor': _extract_file_path,
    },
    'K': {
        'name': 'Marketing Analytics Insights',
        'triggers': [
            r'analyze\s+(?:this\s+)?marketing\s+(?:data|analytics)',
            r'marketing\s+(?:insights|analysis)',
            r'campaign\s+(?:analysis|performance)',
            r'(?:what\s+)?(?:are\s+)?(?:the\s+)?marketing\s+(?:trends|insights)',
        ],
        'keywords': ['marketing', 'analytics', 'campaign', 'insights', 'performance'],
        'param_extractor': lambda p: {'data': 'from_prompt'},
    },
    'L': {
        'name': 'HR Resume Comparison',
        'triggers': [
            r'compare\s+(?:these\s+)?resumes?',
            r'resume\s+comparison',
            r'(?:rank|evaluate)\s+(?:these\s+)?(?:candidates?|resumes?)',
            r'(?:which|who)\s+(?:candidate|resume)\s+is\s+(?:better|best)',
            r'candidate\s+(?:comparison|evaluation)',
        ],
        'keywords': ['resume', 'candidate', 'compare', 'HR', 'hiring', 'evaluate'],
        'param_extractor': _extract_resume_info,
    },
    'M': {
        'name': 'Education Quiz Creation',
        'triggers': [
            r'create\s+(?:a\s+)?quiz\s+(?:from|about|on)',
            r'generate\s+(?:a\s+)?quiz',
            r'make\s+(?:a\s+)?(?:quiz|test)\s+(?:from|about)',
            r'quiz\s+(?:me|creation|generator)',
            r'(?:study|test)\s+questions?\s+(?:from|about)',
        ],
        'keywords': ['quiz', 'test', 'questions', 'education', 'study', 'create'],
        'param_extractor': _extract_quiz_info,
    },
    'N': {
        'name': 'Government Form Extraction',
        'triggers': [
            r'extract\s+(?:from\s+)?(?:this\s+)?(?:government\s+)?form',
            r'(?:fill|parse|read)\s+(?:this\s+)?(?:government\s+)?form',
            r'form\s+(?:extraction|data|parsing)',
            r'(?:government|official)\s+form\s+(?:analysis|extraction)',
        ],
        'keywords': ['form', 'government', 'extract', 'official', 'document', 'parse'],
        'param_extractor': _extract_file_path,
    },
    'O': {
        'name': 'IT Log Summary',
        'triggers': [
            r'summarize\s+(?:these?\s+)?(?:it\s+)?logs?',
            r'(?:it|server|error)\s+log\s+(?:summary|analysis)',
            r'analyze\s+(?:these?\s+)?(?:error\s+)?logs?',
            r'(?:what|find)\s+(?:errors?|issues?)\s+in\s+(?:the\s+)?logs?',
            r'log\s+(?:analysis|summary|review)',
        ],
        'keywords': ['log', 'IT', 'server', 'error', 'analyze', 'summary'],
        'param_extractor': _extract_file_path,
    },
    'P': {
        'name': 'Insurance Claims & Policies',
        'triggers': [
            r'process\s+(?:insurance\s+)?claim',
            r'analyze\s+(?:insurance\s+)?claim',
            r'compare\s+(?:insurance\s+)?polic(?:y|ies)',
            r'check\s+(?:for\s+)?(?:insurance\s+)?fraud',
            r'get\s+insurance\s+quote',
        ],
        'keywords': ['insurance', 'claim', 'policy', 'fraud', 'quote', 'coverage'],
        'param_extractor': lambda p: {'claim_data': 'from_prompt'},
    },
    'Q': {
        'name': 'Banking & Fraud Detection',
        'triggers': [
            r'monitor\s+(?:my\s+)?(?:bank\s+)?account',
            r'check\s+(?:for\s+)?fraud',
            r'analyze\s+(?:my\s+)?(?:bank\s+)?transactions?',
            r'flag\s+suspicious\s+transactions?',
            r'detect\s+(?:unusual|anomalous)\s+activity',
            r'(?:bank|banking)\s+(?:fraud|account|monitor)',
        ],
        'keywords': ['bank', 'account', 'fraud', 'suspicious', 'transaction', 'monitor', 'unusual'],
        'param_extractor': lambda p: {'transactions': 'from_prompt'},
    },
    'R': {
        'name': 'Procurement & Vendor Research',
        'triggers': [
            r'research\s+vendors?\s+for',
            r'find\s+suppliers?\s+for',
            r'compare\s+(?:vendors?|suppliers?)',
            r'evaluate\s+(?:vendors?|suppliers?)',
            r'(?:vendor|supplier)\s+research',
        ],
        'keywords': ['vendor', 'supplier', 'procurement', 'rfp', 'compare', 'research'],
        'param_extractor': lambda p: {'product_category': 'from_prompt'},
    },
    'S': {
        'name': 'Enterprise Admin & SaaS Management',
        'triggers': [
            r'audit\s+user\s+access',
            r'provision\s+users?',
            r'manage\s+saas',
            r'check\s+(?:user\s+)?permissions?',
            r'enterprise\s+admin',
        ],
        'keywords': ['enterprise', 'admin', 'saas', 'provision', 'audit', 'access'],
        'param_extractor': lambda p: {},
    },
    'T': {
        'name': 'Contractor Permit & Licensing',
        'triggers': [
            r'find\s+permit\s+requirements?',
            r'verify\s+licen[cs]e',
            r'contractor\s+(?:permit|licen[cs]e)',
            r'track\s+bids?',
            r'construction\s+permit',
        ],
        'keywords': ['permit', 'license', 'contractor', 'construction', 'bid'],
        'param_extractor': lambda p: {},
    },
    'U': {
        'name': 'Recruiting Pipeline Automation',
        'triggers': [
            r'source\s+candidates?',
            r'find\s+(?:developers?|engineers?)',
            r'recruit(?:ing)?\s+pipeline',
            r'schedule\s+interviews?',
            r'candidate\s+sourcing',
        ],
        'keywords': ['recruit', 'candidate', 'source', 'interview', 'pipeline'],
        'param_extractor': lambda p: {},
    },
    'V': {
        'name': 'Audit & Compliance',
        'triggers': [
            r'(?:check|verify)\s+compliance',
            r'audit\s+trail',
            r'compliance\s+check',
            r'gather\s+evidence',
            r'(?:gdpr|hipaa|sox)\s+compliance',
        ],
        'keywords': ['audit', 'compliance', 'evidence', 'gdpr', 'hipaa', 'sox'],
        'param_extractor': lambda p: {},
    },
    'W': {
        'name': 'Content Moderation',
        'triggers': [
            r'moderate\s+content',
            r'review\s+flagged\s+content',
            r'process\s+moderation\s+queue',
            r'enforce\s+(?:content\s+)?policy',
            r'content\s+moderation',
        ],
        'keywords': ['moderate', 'content', 'flagged', 'policy', 'review', 'queue'],
        'param_extractor': lambda p: {},
    },
    'X': {
        'name': 'Inventory Reconciliation',
        'triggers': [
            r'monitor\s+(?:stock|inventory)',
            r'reconcile\s+inventory',
            r'reorder\s+alerts?',
            r'stock\s+levels?',
            r'warehouse\s+sync',
        ],
        'keywords': ['inventory', 'stock', 'reorder', 'warehouse', 'reconcile'],
        'param_extractor': lambda p: {},
    },
    'Y': {
        'name': 'Research Automation',
        'triggers': [
            r'literature\s+review',
            r'gather\s+citations?',
            r'review\s+(?:papers?|research)',
            r'research\s+automation',
            r'verify\s+sources?',
        ],
        'keywords': ['research', 'literature', 'citation', 'paper', 'review', 'source'],
        'param_extractor': lambda p: {},
    },
    'Z': {
        'name': 'Enterprise Monitoring',
        'triggers': [
            r'aggregate\s+logs?',
            r'correlate\s+alerts?',
            r'incident\s+response',
            r'monitor\s+(?:services?|systems?)',
            r'enterprise\s+monitoring',
        ],
        'keywords': ['monitor', 'log', 'alert', 'incident', 'aggregate', 'correlate'],
        'param_extractor': lambda p: {},
    },
    'AA': {
        'name': 'Healthcare Administration',
        'triggers': [
            r'verify\s+(?:patient\s+)?insurance',
            r'patient\s+lookup',
            r'schedule\s+appointments?',
            r'healthcare\s+admin',
            r'(?:verify|check)\s+coverage',
        ],
        'keywords': ['healthcare', 'patient', 'insurance', 'appointment', 'medical'],
        'param_extractor': lambda p: {},
    },
    'AB': {
        'name': 'Travel Management',
        'triggers': [
            r'monitor\s+flight\s+prices?',
            r'track\s+flights?',
            r'build\s+itinerary',
            r'find\s+(?:cheap|best)\s+flights?',
            r'travel\s+(?:alert|monitoring)',
        ],
        'keywords': ['travel', 'flight', 'itinerary', 'price', 'monitor', 'alert'],
        'param_extractor': lambda p: {},
    },
    'AC': {
        'name': 'Food Service Management',
        'triggers': [
            r'aggregate\s+menu',
            r'(?:supplier|vendor)\s+pricing',
            r'food\s+service',
            r'restaurant\s+inventory',
            r'menu\s+aggregation',
        ],
        'keywords': ['food', 'menu', 'restaurant', 'supplier', 'pricing', 'inventory'],
        'param_extractor': lambda p: {},
    },
    'AD': {
        'name': 'Non-Profit Fundraising',
        'triggers': [
            r'search\s+(?:for\s+)?grants?',
            r'find\s+donors?',
            r'donor\s+research',
            r'grant\s+(?:search|research)',
            r'campaign\s+tracking',
        ],
        'keywords': ['grant', 'donor', 'non-profit', 'fundraising', 'campaign'],
        'param_extractor': lambda p: {},
    },
    'AE': {
        'name': 'Media & PR Monitoring',
        'triggers': [
            r'monitor\s+(?:press|media)',
            r'find\s+journalists?',
            r'track\s+coverage',
            r'press\s+(?:mention|monitoring)',
            r'journalist\s+outreach',
        ],
        'keywords': ['media', 'press', 'journalist', 'coverage', 'monitor', 'pr'],
        'param_extractor': lambda p: {},
    },
}


class CapabilityRouter:
    """
    Routes natural language prompts to appropriate business capabilities.
    """

    def __init__(self):
        self.patterns = CAPABILITY_PATTERNS

    def route(self, prompt: str) -> Optional[CapabilityMatch]:
        """
        Analyze prompt and return matching capability if found.

        Returns None if no capability matches with high confidence.
        """
        prompt_lower = prompt.lower()

        # Skip capability routing if user explicitly wants web browsing
        # These should go to direct patterns or ReAct loop with Playwright instead
        web_browsing_patterns = [
            r'go to\s+\S+\.(?:com|org|net|io)',  # "go to amazon.com"
            r'browse\s+(?:to\s+)?\S+\.(?:com|org|net)',  # "browse to site.com"
            r'visit\s+\S+\.(?:com|org|net)',  # "visit amazon.com"
            r'open\s+\S+\.(?:com|org|net)',  # "open google.com"
            r'(?:go to|open|visit)\s+(?:gmail|zoho|google maps|facebook ads|linkedin)',  # Single-site without .com
            r'(?:search|look)\s+(?:on|in)\s+(?:amazon|google|linkedin|facebook|zillow|fedex|ups|wikipedia|stackoverflow)',  # "search on amazon"
            r'facebook\.com/ads',  # FB Ads Library
            r'(?:amazon|google|linkedin|zillow|fedex|ups|wikipedia|stackoverflow)\.com',  # Direct site mentions
            r'search\s+(?:facebook|fb)\s+ads',  # FB Ads search
        ]

        for pattern in web_browsing_patterns:
            if re.search(pattern, prompt_lower):
                logger.debug(f"Skipping capability routing - explicit web browsing detected: {pattern}")
                return None

        best_match = None
        best_score = 0.0

        for cap_letter, cap_info in self.patterns.items():
            score, reasoning = self._score_match(prompt_lower, cap_info)

            if score > best_score:
                best_score = score
                best_match = (cap_letter, cap_info, reasoning)

        # Threshold for routing
        if best_score >= 0.5 and best_match:
            cap_letter, cap_info, reasoning = best_match

            # Extract parameters
            extractor = cap_info.get('param_extractor', lambda p: {})
            params = extractor(prompt)

            return CapabilityMatch(
                capability=cap_letter,
                capability_name=cap_info['name'],
                confidence=best_score,
                extracted_params=params,
                reasoning=reasoning
            )

        return None

    def _score_match(self, prompt: str, cap_info: Dict) -> Tuple[float, str]:
        """Score how well a prompt matches a capability."""
        score = 0.0
        reasons = []

        # Check trigger patterns (high weight)
        for pattern in cap_info.get('triggers', []):
            if re.search(pattern, prompt):
                score += 0.6
                reasons.append(f"Matched trigger: {pattern[:30]}")
                break

        # Check keywords (lower weight)
        keywords = cap_info.get('keywords', [])
        matched_keywords = [k for k in keywords if k in prompt]
        if matched_keywords:
            keyword_score = min(0.4, len(matched_keywords) * 0.1)
            score += keyword_score
            reasons.append(f"Keywords: {', '.join(matched_keywords[:3])}")

        reasoning = "; ".join(reasons) if reasons else "No match"
        return min(score, 1.0), reasoning

    def get_capability_help(self) -> str:
        """Return help text for all capabilities."""
        lines = ["Business Capabilities (auto-detected from prompts):"]

        for letter, info in sorted(self.patterns.items()):
            keywords = ", ".join(info['keywords'][:4])
            lines.append(f"  {letter}. {info['name']}")
            lines.append(f"     Keywords: {keywords}")

        return "\n".join(lines)


# Singleton instance
router = CapabilityRouter()


def route_to_capability(prompt: str) -> Optional[CapabilityMatch]:
    """Quick function to route a prompt to a capability."""
    return router.route(prompt)
