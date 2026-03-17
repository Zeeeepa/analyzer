"""
Agent Roles - Specialized model roles for agentic tasks.

Based on Reddit research from r/LocalLLaMA:
- Specialize roles: planner vs executor vs critic
- Binary output format: tool_call JSON OR final_answer JSON
- Self-healing with error context
- Safety critic before destructive actions

Model Strategy (from BFCL v3 benchmark research):
- 0000/ui-tars-1.5-7b:latest: Primary executor for tool calling (excellent on BFCL)
- moondream:latest: Vision for UI element detection
- Kimi K2: Strategic planner for complex multi-step tasks

Reddit insight: "The graph/tools do the real work, model just chooses edges and tools"
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from loguru import logger


class AgentRole(Enum):
    """Specialized agent roles - each optimized for specific tasks."""
    PLANNER = "planner"          # High-level strategy, complex reasoning
    EXECUTOR = "executor"        # Tool calling, action execution
    CRITIC = "critic"            # Verify actions, safety checks
    HEALER = "healer"            # Fix errors, adjust arguments
    DOM_NAVIGATOR = "dom_navigator"  # Element selection from compressed DOM


@dataclass
class RoleConfig:
    """Configuration for each agent role."""
    role: AgentRole
    model: str
    temperature: float = 0.1
    max_tokens: int = 2000
    system_prompt: str = ""


# Role-specific system prompts (Reddit insight: binary outputs, no mixing)
ROLE_PROMPTS = {
    AgentRole.PLANNER: """You are a strategic task planner. Your job is to break down complex tasks into clear steps.

OUTPUT FORMAT - You must respond with ONLY valid JSON using a binary envelope:
{
  "mode": "tool_call" | "final_answer",
  "tool": "<tool_name or null>",
  "tool_args": { ... },
  "final": {
    "plan": {
      "summary": "Brief description of the approach",
      "steps": [
        {"step": 1, "action": "description", "tool": "tool_name", "expected_result": "what should happen"}
      ],
      "success_criteria": "How to know if task is complete",
      "potential_blockers": ["list of things that might go wrong"]
    }
  },
  "safety": {
    "allowed_domains": ["example.com"],
    "forbidden_actions": ["delete", "purchase"],
    "max_steps": 20,
    "destructive_actions_require_confirmation": true
  }
}

RULES:
- Output ONLY JSON, no explanations before or after
- Break complex tasks into 3-7 concrete steps
- Each step should use exactly one tool
- Consider what could go wrong at each step
- Always include safety object with constraints

FEW-SHOT EXAMPLES:

Example 1 - Login form:
Input: "Log in to example.com with email test@example.com and password mypass123"
Output:
{
  "mode": "final_answer",
  "tool": null,
  "tool_args": {},
  "final": {
    "plan": {
      "summary": "Navigate to login page and authenticate with credentials",
      "steps": [
        {"step": 1, "action": "Navigate to example.com/login", "tool": "navigate", "expected_result": "Login page loads"},
        {"step": 2, "action": "Fill email field with test@example.com", "tool": "type_text", "expected_result": "Email populated"},
        {"step": 3, "action": "Fill password field with mypass123", "tool": "type_text", "expected_result": "Password populated"},
        {"step": 4, "action": "Click login button", "tool": "click", "expected_result": "Redirect to dashboard"}
      ],
      "success_criteria": "Dashboard visible, user logged in",
      "potential_blockers": ["Invalid credentials", "CAPTCHA required", "2FA enabled"]
    }
  },
  "safety": {
    "allowed_domains": ["example.com"],
    "forbidden_actions": [],
    "max_steps": 5,
    "destructive_actions_require_confirmation": false
  }
}

Example 2 - Multi-step navigation:
Input: "Find all products under $50 in the Electronics category"
Output:
{
  "mode": "final_answer",
  "tool": null,
  "tool_args": {},
  "final": {
    "plan": {
      "summary": "Navigate to Electronics, apply price filter, extract products",
      "steps": [
        {"step": 1, "action": "Click Electronics category link", "tool": "click", "expected_result": "Category page loads"},
        {"step": 2, "action": "Select price filter max $50", "tool": "click", "expected_result": "Filter applied"},
        {"step": 3, "action": "Wait for filtered results", "tool": "wait", "expected_result": "Products updated"},
        {"step": 4, "action": "Extract product names and prices", "tool": "extract_text", "expected_result": "List of products"}
      ],
      "success_criteria": "All products under $50 extracted",
      "potential_blockers": ["No products in range", "Filter not working", "Infinite scroll"]
    }
  },
  "safety": {
    "allowed_domains": ["shop.example.com"],
    "forbidden_actions": ["purchase", "checkout"],
    "max_steps": 10,
    "destructive_actions_require_confirmation": true
  }
}

Example 3 - Pagination:
Input: "Scrape all job listings from careers page"
Output:
{
  "mode": "final_answer",
  "tool": null,
  "tool_args": {},
  "final": {
    "plan": {
      "summary": "Extract jobs from all pages using pagination",
      "steps": [
        {"step": 1, "action": "Navigate to careers page", "tool": "navigate", "expected_result": "Listings visible"},
        {"step": 2, "action": "Extract job titles and links on current page", "tool": "extract_text", "expected_result": "Page 1 data"},
        {"step": 3, "action": "Click Next button if exists", "tool": "click", "expected_result": "Page 2 loads"},
        {"step": 4, "action": "Repeat extraction until no Next button", "tool": "extract_text", "expected_result": "All pages scraped"}
      ],
      "success_criteria": "All job listings collected from all pages",
      "potential_blockers": ["Next button selector changes", "Infinite scroll instead", "Rate limiting"]
    }
  },
  "safety": {
    "allowed_domains": ["company.com"],
    "forbidden_actions": ["submit", "apply"],
    "max_steps": 50,
    "destructive_actions_require_confirmation": false
  }
}

Example 4 - Give up:
Input: "Purchase item XYZ with credit card"
Output:
{
  "mode": "final_answer",
  "tool": null,
  "tool_args": {},
  "final": {
    "plan": {
      "summary": "Cannot proceed - destructive financial action",
      "steps": [],
      "success_criteria": "Task refused for safety",
      "potential_blockers": ["Unauthorized purchase attempt"]
    }
  },
  "safety": {
    "allowed_domains": [],
    "forbidden_actions": ["purchase", "checkout", "pay"],
    "max_steps": 0,
    "destructive_actions_require_confirmation": true
  }
}""",

    AgentRole.EXECUTOR: """You are a precise tool-calling agent. You execute one action at a time.

OUTPUT FORMAT - You must respond with ONLY ONE of these JSON formats:

Option A - Call a tool:
{"tool_call": {"name": "tool_name", "arguments": {"arg1": "value1"}}}

Option B - Report completion:
{"final_answer": {"status": "success", "result": "what was accomplished"}}

Option C - Report failure:
{"final_answer": {"status": "failed", "reason": "why it failed", "suggestion": "what to try next"}}

RULES:
- Output ONLY JSON, no prose or explanations
- Call exactly ONE tool per response
- Never mix tool_call and final_answer
- Use exact argument names from tool schema

FEW-SHOT EXAMPLES:

Example 1 - Login form execution:
Input: "Step 2 of login plan: Fill email field with test@example.com"
Output:
{"tool_call": {"name": "type_text", "arguments": {"selector": "#email", "text": "test@example.com", "clear_first": true}}}

Example 2 - Multi-step navigation:
Input: "Click Electronics category"
Output:
{"tool_call": {"name": "click", "arguments": {"selector": "a[href='/electronics']", "selector_type": "css"}}}

Example 3 - Pagination:
Input: "Extract job titles from current page"
Output:
{"tool_call": {"name": "extract_text", "arguments": {"selector": ".job-listing h2", "multiple": true}}}

Example 4 - Give up (element not found):
Input: "Click the login button"
Context: "Login button not found after 3 retries"
Output:
{"final_answer": {"status": "failed", "reason": "Login button selector not found on page after multiple attempts", "suggestion": "Verify page loaded correctly or try alternative selector like button[type='submit']"}}""",

    AgentRole.CRITIC: """You are a safety and correctness critic. Review proposed actions before execution.

OUTPUT FORMAT - Respond with ONLY valid JSON:
{
  "review": {
    "approved": true/false,
    "risk_level": "safe|caution|dangerous",
    "issues": ["list of concerns if any"],
    "suggestion": "alternative approach if not approved"
  },
  "safety": {
    "allowed_domains": ["example.com"],
    "forbidden_actions": ["delete", "purchase"],
    "max_steps": 20,
    "destructive_actions_require_confirmation": true
  }
}

RULES:
- Output ONLY JSON
- approved=false if action could cause harm or violate policy
- Be especially careful with: deletions, posts, purchases, account changes
- Check: Is target domain expected? Is action type appropriate? Is data being leaked?
- Always include safety object with constraints

FEW-SHOT EXAMPLES:

Example 1 - Safe login action:
Input: "Review action: type_text into #email field with value test@example.com on example.com"
Output:
{
  "review": {
    "approved": true,
    "risk_level": "safe",
    "issues": [],
    "suggestion": ""
  },
  "safety": {
    "allowed_domains": ["example.com"],
    "forbidden_actions": [],
    "max_steps": 5,
    "destructive_actions_require_confirmation": false
  }
}

Example 2 - Risky purchase action:
Input: "Review action: click button #checkout-btn on shop.example.com"
Output:
{
  "review": {
    "approved": false,
    "risk_level": "dangerous",
    "issues": ["Checkout button click may complete unauthorized purchase", "No explicit user confirmation for financial action"],
    "suggestion": "Request explicit user confirmation before proceeding with checkout"
  },
  "safety": {
    "allowed_domains": ["shop.example.com"],
    "forbidden_actions": ["purchase", "checkout", "buy"],
    "max_steps": 0,
    "destructive_actions_require_confirmation": true
  }
}

Example 3 - Domain mismatch:
Input: "Review action: type_text into #password on untrusted-site.xyz"
Output:
{
  "review": {
    "approved": false,
    "risk_level": "dangerous",
    "issues": ["Domain untrusted-site.xyz not in allowed list", "Potential credential theft"],
    "suggestion": "Verify domain is legitimate before entering credentials"
  },
  "safety": {
    "allowed_domains": ["example.com"],
    "forbidden_actions": [],
    "max_steps": 0,
    "destructive_actions_require_confirmation": true
  }
}

Example 4 - Approved with caution:
Input: "Review action: click delete button on admin.example.com"
Output:
{
  "review": {
    "approved": true,
    "risk_level": "caution",
    "issues": ["Destructive action requires confirmation"],
    "suggestion": "Proceed with user confirmation"
  },
  "safety": {
    "allowed_domains": ["admin.example.com"],
    "forbidden_actions": [],
    "max_steps": 10,
    "destructive_actions_require_confirmation": true
  }
}""",

    AgentRole.HEALER: """You are an error recovery specialist. Fix failed tool calls.

Given a failed tool call and error message, output a corrected version.

OUTPUT FORMAT - Respond with ONLY valid JSON:
{
  "healed_call": {
    "name": "tool_name",
    "arguments": {"corrected_arg1": "new_value"},
    "explanation": "what was wrong and how you fixed it"
  }
}

OR if unrecoverable:
{
  "cannot_heal": {
    "reason": "why this cannot be fixed",
    "alternative": "suggested different approach"
  }
}

RULES:
- Output ONLY JSON
- Focus on fixing the specific error mentioned
- Common fixes: selector not found -> try alternative selector, timeout -> add wait

FEW-SHOT EXAMPLES:

Example 1 - Selector not found:
Input:
  Failed: {"name": "click", "arguments": {"selector": "#login-btn"}}
  Error: "Element not found: #login-btn"
  DOM snippet: "<button class='btn-primary login-button'>Login</button>"
Output:
{
  "healed_call": {
    "name": "click",
    "arguments": {"selector": ".login-button", "selector_type": "css"},
    "explanation": "Original ID selector #login-btn not found. Found button with class 'login-button' in DOM, using that instead."
  }
}

Example 2 - Timeout:
Input:
  Failed: {"name": "extract_text", "arguments": {"selector": ".product-list"}}
  Error: "Timeout waiting for element: .product-list"
Output:
{
  "healed_call": {
    "name": "wait_and_extract",
    "arguments": {"selector": ".product-list", "timeout": 10000},
    "explanation": "Element may need more time to load. Added explicit wait with 10s timeout before extraction."
  }
}

Example 3 - Wrong selector type:
Input:
  Failed: {"name": "type_text", "arguments": {"selector": "input[name='email']", "text": "test@example.com"}}
  Error: "Cannot type into non-input element"
  DOM snippet: "<input id='email-field' type='text'>"
Output:
{
  "healed_call": {
    "name": "type_text",
    "arguments": {"selector": "#email-field", "text": "test@example.com", "clear_first": true},
    "explanation": "Selector was incorrect. Found input with id 'email-field' in DOM. Also added clear_first to ensure clean state."
  }
}

Example 4 - Cannot heal:
Input:
  Failed: {"name": "click", "arguments": {"selector": "#submit-payment"}}
  Error: "Element not found: #submit-payment"
  DOM snippet: "<div>Payment form not loaded yet</div>"
Output:
{
  "cannot_heal": {
    "reason": "Payment form has not loaded on the page yet. Submit button does not exist in DOM.",
    "alternative": "Navigate to payment page first, or wait for form to load before attempting to submit"
  }
}""",

    AgentRole.DOM_NAVIGATOR: """You are a DOM element selector agent. Your job is to select element IDs from a compressed DOM for specific actions.

You receive:
- goal: What the user wants to accomplish
- current_url: The page URL
- compressed_dom: Simplified DOM with stable IDs (format: [id:123] tag.class "text")

You must return an actions array with element IDs to interact with.

OUTPUT FORMAT - Respond with ONLY valid JSON:
{
  "actions": [
    {"action": "click|type|extract", "element_id": "123", "value": "optional text for type action"}
  ]
}

CRITICAL RULES:
- Use ONLY element IDs that exist in the provided DOM
- Return 1-5 actions maximum (minimal steps)
- NO explanations, NO prose, ONLY JSON
- Each action must reference a valid element_id from the DOM
- If goal impossible, return empty actions array: {"actions": []}

FEW-SHOT EXAMPLES:

Example 1 - Login form:
Input:
  Goal: "Fill login form with test@example.com and password123, then submit"
  URL: "https://example.com/login"
  DOM: "[id:42] input#email [id:43] input#password [id:44] button.submit 'Login'"
Output:
{
  "actions": [
    {"action": "type", "element_id": "42", "value": "test@example.com"},
    {"action": "type", "element_id": "43", "value": "password123"},
    {"action": "click", "element_id": "44"}
  ]
}

Example 2 - Multi-step navigation:
Input:
  Goal: "Click on Electronics category"
  URL: "https://shop.example.com"
  DOM: "[id:10] nav [id:11] a.category 'Electronics' [id:12] a.category 'Books' [id:13] a.category 'Toys'"
Output:
{
  "actions": [
    {"action": "click", "element_id": "11"}
  ]
}

Example 3 - Pagination extraction:
Input:
  Goal: "Extract all job titles and click Next"
  URL: "https://careers.example.com/jobs"
  DOM: "[id:20] h2.job-title 'Software Engineer' [id:21] h2.job-title 'Product Manager' [id:22] button.next 'Next Page'"
Output:
{
  "actions": [
    {"action": "extract", "element_id": "20"},
    {"action": "extract", "element_id": "21"},
    {"action": "click", "element_id": "22"}
  ]
}

Example 4 - Give up (impossible goal):
Input:
  Goal: "Click the checkout button"
  URL: "https://shop.example.com/products"
  DOM: "[id:50] div.products [id:51] button.add-to-cart 'Add to Cart' [id:52] a.continue 'Continue Shopping'"
Output:
{
  "actions": []
}"""
}


@dataclass
class SelfHealContext:
    """Context for self-healing a failed tool call."""
    tool_name: str
    tool_arguments: Dict[str, Any]
    error_message: str
    dom_snapshot: str = ""  # Compressed DOM state
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class SafetyConfig:
    """Safety configuration for task execution."""
    allowed_domains: List[str] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)
    max_steps: int = 20
    destructive_actions_require_confirmation: bool = True


@dataclass
class SafetyReview:
    """Result of safety critic review."""
    approved: bool
    risk_level: str  # "safe", "caution", "dangerous"
    issues: List[str] = field(default_factory=list)
    suggestion: str = ""
    safety_config: Optional[SafetyConfig] = None


class AgentRoleManager:
    """
    Manages specialized agent roles for different tasks.

    Reddit insight: "Push more control flow into code, lock LLM into small decisions"
    - Planner: "What's the strategy?"
    - Executor: "Which tool to call with what args?"
    - Critic: "Is this action safe?"
    - Healer: "How do we fix this error?"
    """

    # Default model assignments per role
    DEFAULT_MODELS = {
        AgentRole.PLANNER: "0000/ui-tars-1.5-7b:latest",          # Could upgrade to Kimi for complex tasks
        AgentRole.EXECUTOR: "0000/ui-tars-1.5-7b:latest",         # Best for tool calling (BFCL benchmark)
        AgentRole.CRITIC: "0000/ui-tars-1.5-7b:latest",           # Same model, different prompt
        AgentRole.HEALER: "0000/ui-tars-1.5-7b:latest",           # Error recovery
        AgentRole.DOM_NAVIGATOR: "0000/ui-tars-1.5-7b:latest",    # Element selection from compressed DOM
    }

    # Actions that require safety review
    DESTRUCTIVE_ACTIONS = {
        "delete", "remove", "post", "submit", "send", "purchase", "buy",
        "checkout", "confirm", "authorize", "transfer", "pay", "subscribe"
    }

    # Domains that are always safe
    SAFE_DOMAINS = {
        "google.com", "duckduckgo.com", "bing.com",  # Search engines
        "github.com", "stackoverflow.com",            # Dev resources
        "wikipedia.org",                              # Reference
    }

    def __init__(self, ollama_client=None, kimi_client=None, config: Dict = None):
        """
        Initialize role manager.

        Args:
            ollama_client: Ollama client for local models
            kimi_client: Kimi K2 client for complex planning
            config: Optional config overrides
        """
        self.ollama_client = ollama_client
        self.kimi_client = kimi_client
        self.config = config or {}

        # Track consecutive failures for escalation
        self.executor_failures = 0
        self.escalation_threshold = 3

        logger.info("[ROLES] Agent role manager initialized")

    def get_model_for_role(self, role: AgentRole, complexity: str = "normal") -> str:
        """Get the appropriate model for a role, considering task complexity."""
        base_model = self.DEFAULT_MODELS.get(role, "0000/ui-tars-1.5-7b:latest")

        # Escalate planner to Kimi for complex tasks
        if role == AgentRole.PLANNER and complexity == "complex":
            if self.kimi_client and self.kimi_client.is_available():
                return "kimi-k2"

        # Escalate executor after repeated failures
        if role == AgentRole.EXECUTOR and self.executor_failures >= self.escalation_threshold:
            if self.kimi_client and self.kimi_client.is_available():
                logger.warning(f"[ROLES] Escalating executor to Kimi after {self.executor_failures} failures")
                return "kimi-k2"

        return base_model

    def get_system_prompt(self, role: AgentRole) -> str:
        """Get the system prompt for a role."""
        return ROLE_PROMPTS.get(role, "")

    def needs_safety_review(self, tool_name: str, arguments: Dict, current_url: str = "") -> bool:
        """
        Determine if an action needs safety review.

        Reddit insight: "Before any destructive action, run a check"
        """
        # Check if tool name contains destructive keywords
        tool_lower = tool_name.lower()
        for action in self.DESTRUCTIVE_ACTIONS:
            if action in tool_lower:
                return True

        # Check arguments for destructive intent
        args_str = json.dumps(arguments).lower()
        for action in self.DESTRUCTIVE_ACTIONS:
            if action in args_str:
                return True

        # Check if on unknown/risky domain
        if current_url:
            domain = self._extract_domain(current_url)
            if domain and domain not in self.SAFE_DOMAINS:
                # Unknown domain + form submission = needs review
                if "submit" in tool_lower or "click" in tool_lower:
                    if "form" in args_str or "button" in args_str:
                        return True

        return False

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def build_healer_prompt(self, context: SelfHealContext) -> str:
        """
        Build a prompt for the healer role to fix a failed tool call.

        Reddit insight: "Retry with more context - error message + DOM snippet + directive"
        """
        prompt = f"""A tool call failed. Please fix it.

FAILED TOOL CALL:
- Tool: {context.tool_name}
- Arguments: {json.dumps(context.tool_arguments, indent=2)}

ERROR MESSAGE:
{context.error_message}

"""
        if context.dom_snapshot:
            prompt += f"""CURRENT PAGE STATE (DOM snippet):
{context.dom_snapshot[:2000]}

"""

        prompt += f"""RETRY INFO:
- This is retry #{context.retry_count + 1} of {context.max_retries}

Fix the arguments and provide a corrected tool call. Focus on the specific error.
Common fixes:
- "element not found" -> try alternative selector (id, class, text content)
- "timeout" -> the element may need time to load
- "not clickable" -> element may be covered, try scrolling first"""

        return prompt

    def build_critic_prompt(self, tool_name: str, arguments: Dict,
                           current_url: str, user_intent: str) -> str:
        """
        Build a prompt for the critic role to review an action.

        Reddit insight: "Safety critic inspects domain whitelist, action type, user intent"
        """
        domain = self._extract_domain(current_url) if current_url else "unknown"

        prompt = f"""Review this proposed action before execution:

ACTION:
- Tool: {tool_name}
- Arguments: {json.dumps(arguments, indent=2)}

CONTEXT:
- Current URL: {current_url}
- Domain: {domain}
- User's original intent: {user_intent}

REVIEW CRITERIA:
1. Does this action align with the user's stated intent?
2. Is the target domain appropriate for this action?
3. Could this action cause unintended harm (data loss, unwanted purchases, privacy leaks)?
4. Is there anything suspicious about the arguments?

Provide your safety review."""

        return prompt

    def parse_planner_response(self, response: str) -> Dict[str, Any]:
        """
        Parse planner response with binary envelope format.

        Reddit insight: "Binary envelope with mode, tool, tool_args, final, safety"

        Returns:
            Dictionary with keys: mode, tool, tool_args, final, safety
        """
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                logger.warning("[ROLES] No JSON found in planner response")
                return {}

            data = json.loads(json_match.group())

            # Parse binary envelope format
            result = {
                "mode": data.get("mode", "final_answer"),
                "tool": data.get("tool"),
                "tool_args": data.get("tool_args", {}),
                "final": data.get("final", {}),
                "safety": None
            }

            # Parse safety config if present
            if "safety" in data:
                safety_data = data["safety"]
                result["safety"] = SafetyConfig(
                    allowed_domains=safety_data.get("allowed_domains", []),
                    forbidden_actions=safety_data.get("forbidden_actions", []),
                    max_steps=safety_data.get("max_steps", 20),
                    destructive_actions_require_confirmation=safety_data.get(
                        "destructive_actions_require_confirmation", True
                    )
                )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"[ROLES] Failed to parse planner response: {e}")
            return {}

    def parse_tool_call(self, response: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Parse executor response into tool_call or final_answer.

        Reddit insight: "Binary outputs - tool_call OR final_answer, never mix"

        Returns:
            (tool_call dict, final_answer dict) - one will be None
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                logger.warning("[ROLES] No JSON found in executor response")
                return None, None

            data = json.loads(json_match.group())

            # Check for tool_call
            if "tool_call" in data:
                tool_call = data["tool_call"]
                if "name" in tool_call:
                    return tool_call, None

            # Check for final_answer
            if "final_answer" in data:
                return None, data["final_answer"]

            # Legacy format support
            if "name" in data and "arguments" in data:
                return data, None

            logger.warning(f"[ROLES] Unknown response format: {list(data.keys())}")
            return None, None

        except json.JSONDecodeError as e:
            logger.error(f"[ROLES] Failed to parse executor response: {e}")
            return None, None

    def parse_safety_review(self, response: str) -> SafetyReview:
        """Parse critic response into SafetyReview with safety config."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                review = data.get("review", data)

                # Parse safety config if present
                safety_config = None
                if "safety" in data:
                    safety_data = data["safety"]
                    safety_config = SafetyConfig(
                        allowed_domains=safety_data.get("allowed_domains", []),
                        forbidden_actions=safety_data.get("forbidden_actions", []),
                        max_steps=safety_data.get("max_steps", 20),
                        destructive_actions_require_confirmation=safety_data.get(
                            "destructive_actions_require_confirmation", True
                        )
                    )

                return SafetyReview(
                    approved=review.get("approved", True),
                    risk_level=review.get("risk_level", "safe"),
                    issues=review.get("issues", []),
                    suggestion=review.get("suggestion", ""),
                    safety_config=safety_config
                )
        except Exception as e:
            logger.error(f"[ROLES] Failed to parse safety review: {e}")

        # Default to approved if parsing fails
        return SafetyReview(approved=True, risk_level="safe")

    def parse_dom_navigator_response(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse DOM navigator response into actions list.

        Returns:
            List of action dictionaries with keys: action, element_id, value (optional)
        """
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                logger.warning("[ROLES] No JSON found in DOM navigator response")
                return []

            data = json.loads(json_match.group())
            actions = data.get("actions", [])

            if not isinstance(actions, list):
                logger.warning(f"[ROLES] DOM navigator actions not a list: {type(actions)}")
                return []

            return actions

        except json.JSONDecodeError as e:
            logger.error(f"[ROLES] Failed to parse DOM navigator response: {e}")
            return []

    def build_dom_navigator_prompt(self, goal: str, current_url: str, compressed_dom: str) -> str:
        """
        Build a prompt for the DOM navigator role.

        Reddit insight: "Give compressed DOM with stable IDs, ask for element IDs only"
        """
        prompt = f"""Select elements from the DOM to accomplish the goal.

GOAL:
{goal}

CURRENT URL:
{current_url}

COMPRESSED DOM:
{compressed_dom[:5000]}  # Limit to avoid token overflow

Return JSON with actions array using only element IDs from the DOM above."""

        return prompt

    def record_executor_result(self, success: bool):
        """Track executor success/failure for escalation decisions."""
        if success:
            self.executor_failures = 0
        else:
            self.executor_failures += 1
            if self.executor_failures >= self.escalation_threshold:
                logger.warning(
                    f"[ROLES] Executor has failed {self.executor_failures} times, "
                    "will escalate to Kimi on next call"
                )


# Tool schema format helper
def format_tool_schema(name: str, description: str, parameters: Dict) -> str:
    """
    Format a tool schema for the executor prompt.

    Reddit insight: "Provide explicit JSON schema for each tool"
    """
    schema = {
        "name": name,
        "description": description,
        "parameters": parameters
    }
    return json.dumps(schema, indent=2)


# Example tool schemas for common browser actions
BROWSER_TOOL_SCHEMAS = {
    "click": {
        "name": "click",
        "description": "Click on an element on the page",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector, XPath, or text content to find element"
                },
                "selector_type": {
                    "type": "string",
                    "enum": ["css", "xpath", "text", "role"],
                    "description": "Type of selector"
                }
            },
            "required": ["selector"]
        }
    },
    "type_text": {
        "name": "type_text",
        "description": "Type text into an input field",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Selector for input field"},
                "text": {"type": "string", "description": "Text to type"},
                "clear_first": {"type": "boolean", "description": "Clear field before typing"}
            },
            "required": ["selector", "text"]
        }
    },
    "navigate": {
        "name": "navigate",
        "description": "Navigate to a URL",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"}
            },
            "required": ["url"]
        }
    },
    "extract_text": {
        "name": "extract_text",
        "description": "Extract text content from elements",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Selector for elements"},
                "multiple": {"type": "boolean", "description": "Extract from all matching elements"}
            },
            "required": ["selector"]
        }
    }
}


def build_executor_tools_prompt(available_tools: List[str]) -> str:
    """
    Build tools section for executor prompt with JSON schemas.

    Reddit insight: "For each tool, give name, description, JSON schema with types and enums"
    """
    tools_section = "AVAILABLE TOOLS:\n\n"

    for tool_name in available_tools:
        if tool_name in BROWSER_TOOL_SCHEMAS:
            schema = BROWSER_TOOL_SCHEMAS[tool_name]
            tools_section += f"Tool: {schema['name']}\n"
            tools_section += f"Description: {schema['description']}\n"
            tools_section += f"Schema: {json.dumps(schema['parameters'], indent=2)}\n\n"

    # Add examples (Reddit insight: "2-3 positive examples of correct tool-calls")
    tools_section += """
EXAMPLES OF CORRECT TOOL CALLS:

1. Click a button:
{"tool_call": {"name": "click", "arguments": {"selector": "button.submit-btn", "selector_type": "css"}}}

2. Type in a search box:
{"tool_call": {"name": "type_text", "arguments": {"selector": "#search-input", "text": "AI news", "clear_first": true}}}

3. Report task complete:
{"final_answer": {"status": "success", "result": "Found and clicked the login button"}}

4. Report cannot proceed:
{"final_answer": {"status": "failed", "reason": "Login button not found on page", "suggestion": "Try scrolling down or check if page loaded"}}
"""

    return tools_section


# Singleton instance
_role_manager: Optional[AgentRoleManager] = None


def get_role_manager(ollama_client=None, kimi_client=None, config: Dict = None) -> AgentRoleManager:
    """Get or create the singleton role manager."""
    global _role_manager
    if _role_manager is None:
        _role_manager = AgentRoleManager(ollama_client, kimi_client, config)
    return _role_manager
