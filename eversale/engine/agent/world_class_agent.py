"""
World-Class Agent Enhancements - Beyond Claude Code / Codex

This module adds capabilities that make the agent truly world-class for forever
web automation with natural language understanding:

1. NATURAL LANGUAGE TASK INTERPRETER
   - Understands vague requests ("check my competitors", "find me leads")
   - Breaks down complex sentences into executable steps
   - Handles context and pronouns ("do it again", "try another one")

2. PROACTIVE MONITORING PATTERNS
   - Website change detection
   - Price drop alerts
   - Stock availability watchers
   - News/announcement monitors
   - Social media mention trackers

3. MULTI-AGENT ORCHESTRATION
   - Spawn specialized sub-agents
   - Parallel task execution
   - Agent communication/handoff
   - Load balancing across tasks

4. LEARNED AUTOMATION PATTERNS
   - Remember successful workflows
   - Auto-suggest based on history
   - Clone patterns across similar sites
   - Build reusable templates

5. CONVERSATION MEMORY
   - Remember user preferences
   - Track past requests
   - Learn from corrections
   - Build user profile
"""

import json
import re
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from loguru import logger
import threading


# =============================================================================
# 1. NATURAL LANGUAGE TASK INTERPRETER
# =============================================================================

class TaskIntent(Enum):
    """High-level task categories the agent can understand."""
    # Web Automation
    SCRAPE = "scrape"              # Extract data from websites
    MONITOR = "monitor"            # Watch for changes
    FILL_FORM = "fill_form"        # Fill out forms
    CLICK_FLOW = "click_flow"      # Navigate through clicks
    LOGIN = "login"                # Authenticate to a site
    DOWNLOAD = "download"          # Download files
    SCREENSHOT = "screenshot"      # Capture screenshots

    # Research
    RESEARCH = "research"          # Find information about topic
    COMPARE = "compare"            # Compare multiple things
    SUMMARIZE = "summarize"        # Summarize content
    ANALYZE = "analyze"            # Deep analysis

    # Business Operations
    FIND_LEADS = "find_leads"      # Lead generation
    SEND_EMAIL = "send_email"      # Email outreach
    CHECK_INBOX = "check_inbox"    # Monitor inbox
    SCHEDULE = "schedule"          # Schedule tasks

    # Data Management
    EXPORT = "export"              # Export data to file
    IMPORT = "import"              # Import data from file
    TRANSFORM = "transform"        # Clean/transform data
    MERGE = "merge"                # Combine datasets

    # Meta Operations
    REPEAT = "repeat"              # Do something again
    UNDO = "undo"                  # Undo last action
    EXPLAIN = "explain"            # Explain what was done
    HELP = "help"                  # Get help

    # Forever Operations
    WATCH_FOREVER = "watch_forever"  # Infinite monitoring
    PROCESS_QUEUE = "process_queue"  # Process items continuously
    ALERT_ON = "alert_on"            # Alert when condition met

    UNKNOWN = "unknown"


@dataclass
class ParsedTask:
    """A parsed task from natural language."""
    intent: TaskIntent
    target: str                    # URL, search term, file path, etc.
    parameters: Dict[str, Any]     # Extracted parameters
    conditions: List[str]          # "if X then Y" conditions
    schedule: Optional[str]        # Timing info ("every hour", "at 9am")
    output: Optional[str]          # Where to save results
    confidence: float              # How confident we are in parsing
    original_text: str             # Original user input
    context_refs: List[str]        # References to previous context ("it", "that site")


class NaturalLanguageInterpreter:
    """
    Interprets natural language into executable tasks.

    Examples it can understand:
    - "scrape the first 10 products from amazon"
    - "watch that site for price changes and alert me"
    - "find leads on facebook ads for saas companies"
    - "do it again but for the competitor site"
    - "check my email every 5 minutes and respond to urgent ones"
    - "research openai and summarize in 3 sentences"
    """

    def __init__(self, memory_dir: Path = None):
        self.memory_dir = memory_dir or Path.home() / '.eversale' / 'nlp'
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Context from previous interactions
        self.context: Dict[str, Any] = {
            'last_url': None,
            'last_target': None,
            'last_action': None,
            'last_results': None,
            'session_entities': {},  # Named entities in session
        }

        # Intent patterns (regex -> intent)
        self.intent_patterns = self._build_intent_patterns()

        # Load learned patterns
        self.learned_patterns: List[Dict] = self._load_learned_patterns()

    def _build_intent_patterns(self) -> List[Tuple[str, TaskIntent, float]]:
        """Build regex patterns for intent detection."""
        return [
            # Scraping
            (r'\b(scrape|extract|get|pull|grab|collect)\b.*\b(from|on|at)\b', TaskIntent.SCRAPE, 0.9),
            (r'\b(scrape|crawl)\b', TaskIntent.SCRAPE, 0.8),

            # Monitoring
            (r'\b(watch|monitor|track|observe)\b.*\b(forever|always|continuously)\b', TaskIntent.WATCH_FOREVER, 0.95),
            (r'\b(watch|monitor|track)\b.*\b(change|update|price|stock)\b', TaskIntent.MONITOR, 0.9),
            (r'\b(alert|notify|tell)\b.*\b(when|if)\b', TaskIntent.ALERT_ON, 0.9),

            # Research
            (r'\b(research|investigate|look up|find out|learn about)\b', TaskIntent.RESEARCH, 0.9),
            (r'\b(compare|versus|vs|difference between)\b', TaskIntent.COMPARE, 0.9),
            (r'\b(summarize|summary|tldr|brief)\b', TaskIntent.SUMMARIZE, 0.85),
            (r'\b(analyze|analysis|deep dive)\b', TaskIntent.ANALYZE, 0.85),

            # Lead Generation
            (r'\b(find|get|generate)\b.*\b(leads?|prospects?|contacts?)\b', TaskIntent.FIND_LEADS, 0.95),
            (r'\b(lead\s*(gen|generation))\b', TaskIntent.FIND_LEADS, 0.95),

            # Email
            (r'\b(send|write|compose)\b.*\b(email|mail|message)\b', TaskIntent.SEND_EMAIL, 0.9),
            (r'\b(check|read|open)\b.*\b(inbox|email|mail)\b', TaskIntent.CHECK_INBOX, 0.9),

            # Forms
            (r'\b(fill|complete|submit)\b.*\b(form|application|signup)\b', TaskIntent.FILL_FORM, 0.9),
            (r'\b(sign up|register|apply)\b', TaskIntent.FILL_FORM, 0.8),

            # Navigation
            (r'\b(click|tap|press|navigate)\b.*\b(through|on)\b', TaskIntent.CLICK_FLOW, 0.85),
            (r'\b(login|log in|sign in|authenticate)\b', TaskIntent.LOGIN, 0.9),

            # Downloads
            (r'\b(download|save|fetch)\b.*\b(file|pdf|image|document)\b', TaskIntent.DOWNLOAD, 0.9),
            (r'\b(screenshot|capture|snapshot)\b', TaskIntent.SCREENSHOT, 0.9),

            # Data
            (r'\b(export|save|write)\b.*\b(csv|json|excel|file)\b', TaskIntent.EXPORT, 0.9),
            (r'\b(import|load|read)\b.*\b(from)\b.*\b(csv|json|excel|file)\b', TaskIntent.IMPORT, 0.9),
            (r'\b(clean|transform|convert|process)\b.*\b(data)\b', TaskIntent.TRANSFORM, 0.85),

            # Meta
            (r'\b(do it again|repeat|redo|same thing)\b', TaskIntent.REPEAT, 0.95),
            (r'\b(undo|revert|go back)\b', TaskIntent.UNDO, 0.9),
            (r'\b(explain|what did you|show me what)\b', TaskIntent.EXPLAIN, 0.85),
            (r'\b(help|how do i|what can you)\b', TaskIntent.HELP, 0.9),

            # Forever ops
            (r'\b(forever|infinite|never stop|dont stop|keep going)\b', TaskIntent.WATCH_FOREVER, 0.9),
            (r'\b(process|handle)\b.*\b(queue|batch|all)\b.*\b(continuously|forever)\b', TaskIntent.PROCESS_QUEUE, 0.9),
        ]

    def parse(self, text: str) -> ParsedTask:
        """Parse natural language into a structured task."""
        text_lower = text.lower().strip()

        # Detect intent
        intent, confidence = self._detect_intent(text_lower)

        # Extract target (URL, search term, etc.)
        target = self._extract_target(text, intent)

        # Extract parameters
        parameters = self._extract_parameters(text, intent)

        # Extract conditions
        conditions = self._extract_conditions(text)

        # Extract schedule
        schedule = self._extract_schedule(text)

        # Extract output destination
        output = self._extract_output(text)

        # Handle context references
        context_refs = self._find_context_refs(text)
        target = self._resolve_context(target, context_refs)

        return ParsedTask(
            intent=intent,
            target=target,
            parameters=parameters,
            conditions=conditions,
            schedule=schedule,
            output=output,
            confidence=confidence,
            original_text=text,
            context_refs=context_refs
        )

    def _detect_intent(self, text: str) -> Tuple[TaskIntent, float]:
        """Detect the intent from text."""
        best_intent = TaskIntent.UNKNOWN
        best_confidence = 0.0

        for pattern, intent, base_confidence in self.intent_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if base_confidence > best_confidence:
                    best_intent = intent
                    best_confidence = base_confidence

        # Check learned patterns
        for learned in self.learned_patterns:
            if self._matches_learned(text, learned):
                if learned.get('confidence', 0.7) > best_confidence:
                    best_intent = TaskIntent(learned['intent'])
                    best_confidence = learned['confidence']

        return best_intent, best_confidence

    def _extract_target(self, text: str, intent: TaskIntent) -> str:
        """Extract the target from text based on intent."""
        # URL extraction
        url_match = re.search(r'https?://[^\s]+', text)
        if url_match:
            return url_match.group()

        # Domain extraction
        domain_match = re.search(r'\b([a-z0-9-]+\.(com|org|net|io|ai|co)[^\s]*)\b', text, re.I)
        if domain_match:
            return f"https://{domain_match.group(1)}"

        # For research/leads, extract the topic
        if intent in [TaskIntent.RESEARCH, TaskIntent.FIND_LEADS, TaskIntent.COMPARE]:
            # "research OpenAI" -> "OpenAI"
            # "find leads for SaaS companies" -> "SaaS companies"
            topic_patterns = [
                r'\b(?:research|investigate|about|for)\s+([^,\.]+)',
                r'\b(?:leads?|prospects?)\s+(?:for|from|on)\s+([^,\.]+)',
                r'\b(?:compare)\s+([^,\.]+)',
            ]
            for pattern in topic_patterns:
                match = re.search(pattern, text, re.I)
                if match:
                    return match.group(1).strip()

        # For file operations
        if intent in [TaskIntent.EXPORT, TaskIntent.IMPORT, TaskIntent.DOWNLOAD]:
            file_match = re.search(r'[~/\w]+\.\w{2,4}', text)
            if file_match:
                return file_match.group()

        return self.context.get('last_target', '')

    def _extract_parameters(self, text: str, intent: TaskIntent) -> Dict[str, Any]:
        """Extract parameters from text."""
        params = {}

        # Number extraction ("first 10", "top 5", "100 items")
        num_match = re.search(r'\b(first|top|last|next)?\s*(\d+)\s*(items?|products?|results?|leads?|pages?)?', text, re.I)
        if num_match:
            params['count'] = int(num_match.group(2))
            if num_match.group(1):
                params['order'] = num_match.group(1).lower()

        # Time extraction ("every 5 minutes", "hourly")
        time_match = re.search(r'every\s+(\d+)\s*(seconds?|minutes?|hours?|days?)', text, re.I)
        if time_match:
            params['interval'] = int(time_match.group(1))
            params['interval_unit'] = time_match.group(2).rstrip('s')

        # Category/filter extraction
        filter_patterns = [
            (r'\b(only|just)\s+(\w+)', 'filter'),
            (r'\b(category|type|kind)\s*[:=]?\s*(\w+)', 'category'),
            (r'\bin\s+(\w+)\s+(?:category|industry|niche)', 'industry'),
        ]
        for pattern, key in filter_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                params[key] = match.group(2) if len(match.groups()) > 1 else match.group(1)

        # Boolean flags
        if re.search(r'\b(with|include)\s+email', text, re.I):
            params['include_email'] = True
        if re.search(r'\b(with|include)\s+phone', text, re.I):
            params['include_phone'] = True
        if re.search(r'\b(unique|dedupe|no duplicates)', text, re.I):
            params['deduplicate'] = True

        return params

    def _extract_conditions(self, text: str) -> List[str]:
        """Extract if/when conditions."""
        conditions = []

        # "if X then Y" patterns
        if_patterns = [
            r'if\s+(.+?)\s+then\s+(.+?)(?:\.|$)',
            r'when\s+(.+?)\s+(?:then\s+)?(.+?)(?:\.|$)',
            r'(.+?)\s*\?\s*(.+?)(?:\.|$)',  # "price drops? alert me"
        ]

        for pattern in if_patterns:
            matches = re.findall(pattern, text, re.I)
            for condition, action in matches:
                conditions.append(f"IF {condition.strip()} THEN {action.strip()}")

        return conditions

    def _extract_schedule(self, text: str) -> Optional[str]:
        """Extract scheduling information."""
        patterns = [
            r'every\s+(\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?))',
            r'at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)',
            r'(daily|hourly|weekly|monthly)',
            r'(once|twice)\s+(?:a|per)\s+(day|hour|week|month)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group()

        return None

    def _extract_output(self, text: str) -> Optional[str]:
        """Extract output destination."""
        patterns = [
            r'save\s+(?:to|as|in)\s+([~/\w\.-]+)',
            r'export\s+(?:to|as)\s+([~/\w\.-]+)',
            r'(?:to|into)\s+([~/\w]+\.(?:csv|json|xlsx?|md|txt))',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1)

        return None

    def _find_context_refs(self, text: str) -> List[str]:
        """Find references to previous context."""
        refs = []

        ref_patterns = [
            (r'\b(it|that|this|the site|the page)\b', 'last_target'),
            (r'\b(again|same|repeat)\b', 'last_action'),
            (r'\b(them|those|the results?)\b', 'last_results'),
            (r'\b(the other|another|next)\b', 'alternatives'),
        ]

        for pattern, ref_type in ref_patterns:
            if re.search(pattern, text, re.I):
                refs.append(ref_type)

        return refs

    def _resolve_context(self, target: str, context_refs: List[str]) -> str:
        """Resolve context references to actual values."""
        if not target and 'last_target' in context_refs:
            return self.context.get('last_target', '')
        return target

    def _matches_learned(self, text: str, pattern: Dict) -> bool:
        """Check if text matches a learned pattern."""
        keywords = pattern.get('keywords', [])
        threshold = pattern.get('match_threshold', 0.6)

        text_words = set(text.lower().split())
        keyword_set = set(k.lower() for k in keywords)

        if not keyword_set:
            return False

        overlap = len(text_words & keyword_set) / len(keyword_set)
        return overlap >= threshold

    def _load_learned_patterns(self) -> List[Dict]:
        """Load learned patterns from disk."""
        path = self.memory_dir / 'learned_patterns.json'
        if path.exists():
            try:
                return json.loads(path.read_text())
            except:
                pass
        return []

    def learn_pattern(self, text: str, intent: TaskIntent, success: bool):
        """Learn from user corrections and successes."""
        keywords = [w for w in text.lower().split() if len(w) > 3]

        pattern = {
            'keywords': keywords,
            'intent': intent.value,
            'confidence': 0.8 if success else 0.5,
            'learned_at': datetime.now().isoformat(),
            'example': text
        }

        self.learned_patterns.append(pattern)

        # Persist
        path = self.memory_dir / 'learned_patterns.json'
        path.write_text(json.dumps(self.learned_patterns, indent=2))

    def update_context(self, **kwargs):
        """Update session context."""
        self.context.update(kwargs)


# =============================================================================
# 2. PROACTIVE MONITORING PATTERNS
# =============================================================================

@dataclass
class MonitorConfig:
    """Configuration for a monitoring task."""
    url: str
    check_type: str              # 'content', 'price', 'stock', 'selector', 'screenshot'
    selector: Optional[str] = None
    interval_seconds: int = 300  # 5 minutes default
    alert_on: str = "change"     # 'change', 'increase', 'decrease', 'threshold', 'contains'
    threshold: Optional[float] = None
    contains_text: Optional[str] = None
    notify_via: str = "log"      # 'log', 'email', 'webhook', 'file'
    notify_target: Optional[str] = None


@dataclass
class ChangeEvent:
    """Detected change event."""
    timestamp: str
    url: str
    change_type: str
    old_value: Any
    new_value: Any
    details: str


class ProactiveMonitor:
    """
    Proactive web monitoring - watches sites for changes.

    Use cases:
    - Price drop alerts
    - Stock availability notifications
    - Content change detection
    - Competitor monitoring
    - News/announcement tracking
    """

    def __init__(self, work_dir: Path = None):
        self.work_dir = work_dir or Path.home() / '.eversale' / 'monitors'
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self.monitors: Dict[str, MonitorConfig] = {}
        self.baselines: Dict[str, Any] = {}  # Last known values
        self.change_history: List[ChangeEvent] = []

        self._load_state()

    def add_monitor(self, name: str, config: MonitorConfig) -> str:
        """Add a new monitor."""
        monitor_id = hashlib.md5(f"{name}:{config.url}".encode()).hexdigest()[:12]
        self.monitors[monitor_id] = config
        self._save_state()
        logger.info(f"[MONITOR] Added monitor '{name}' for {config.url}")
        return monitor_id

    def check_all(self, page_fetcher: Callable[[str], str]) -> List[ChangeEvent]:
        """Check all monitors for changes."""
        events = []

        for monitor_id, config in self.monitors.items():
            try:
                event = self._check_monitor(monitor_id, config, page_fetcher)
                if event:
                    events.append(event)
                    self.change_history.append(event)
            except Exception as e:
                logger.warning(f"[MONITOR] Error checking {config.url}: {e}")

        if events:
            self._save_state()

        return events

    def _check_monitor(
        self,
        monitor_id: str,
        config: MonitorConfig,
        page_fetcher: Callable[[str], str]
    ) -> Optional[ChangeEvent]:
        """Check a single monitor for changes."""
        # Fetch current content
        content = page_fetcher(config.url)

        # Extract value based on check type
        current_value = self._extract_value(content, config)

        # Get baseline
        baseline = self.baselines.get(monitor_id)

        # First check - establish baseline
        if baseline is None:
            self.baselines[monitor_id] = current_value
            return None

        # Check for change based on alert_on type
        is_change = False
        change_type = ""

        if config.alert_on == "change":
            is_change = current_value != baseline
            change_type = "content_changed"

        elif config.alert_on == "increase":
            try:
                is_change = float(current_value) > float(baseline)
                change_type = "value_increased"
            except:
                pass

        elif config.alert_on == "decrease":
            try:
                is_change = float(current_value) < float(baseline)
                change_type = "value_decreased"
            except:
                pass

        elif config.alert_on == "threshold":
            try:
                is_change = float(current_value) <= config.threshold
                change_type = "below_threshold"
            except:
                pass

        elif config.alert_on == "contains":
            is_change = config.contains_text in str(current_value)
            change_type = "text_found"

        if is_change:
            event = ChangeEvent(
                timestamp=datetime.now().isoformat(),
                url=config.url,
                change_type=change_type,
                old_value=baseline,
                new_value=current_value,
                details=f"Monitor {monitor_id} detected {change_type}"
            )

            # Update baseline
            self.baselines[monitor_id] = current_value

            # Send notification
            self._notify(config, event)

            return event

        return None

    def _extract_value(self, content: str, config: MonitorConfig) -> Any:
        """Extract value from content based on check type."""
        if config.check_type == "content":
            return hashlib.md5(content.encode()).hexdigest()

        elif config.check_type == "price":
            # Extract price from content
            prices = re.findall(r'\$[\d,]+\.?\d*', content)
            if prices:
                return prices[0].replace('$', '').replace(',', '')

        elif config.check_type == "stock":
            # Check for stock indicators
            stock_patterns = [
                (r'in stock', True),
                (r'out of stock', False),
                (r'available', True),
                (r'sold out', False),
                (r'add to cart', True),
            ]
            content_lower = content.lower()
            for pattern, in_stock in stock_patterns:
                if re.search(pattern, content_lower):
                    return in_stock

        elif config.check_type == "selector" and config.selector:
            # Would need actual DOM parsing - simplified here
            match = re.search(f'{config.selector}[^>]*>([^<]+)', content)
            if match:
                return match.group(1).strip()

        return content[:1000]  # Fallback: first 1000 chars

    def _notify(self, config: MonitorConfig, event: ChangeEvent):
        """Send notification for change event."""
        message = f"[ALERT] {event.change_type} on {event.url}: {event.old_value} -> {event.new_value}"

        if config.notify_via == "log":
            logger.warning(message)

        elif config.notify_via == "file":
            if config.notify_target:
                with open(config.notify_target, 'a') as f:
                    f.write(json.dumps(asdict(event)) + "\n")

        elif config.notify_via == "webhook":
            # Would POST to webhook URL
            pass

    def _load_state(self):
        """Load monitor state from disk."""
        state_file = self.work_dir / 'monitor_state.json'
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                self.baselines = data.get('baselines', {})
                # Restore monitors
                for mid, mdata in data.get('monitors', {}).items():
                    self.monitors[mid] = MonitorConfig(**mdata)
            except Exception as e:
                logger.warning(f"Failed to load monitor state: {e}")

    def _save_state(self):
        """Save monitor state to disk."""
        state_file = self.work_dir / 'monitor_state.json'
        data = {
            'baselines': self.baselines,
            'monitors': {k: asdict(v) for k, v in self.monitors.items()},
            'saved_at': datetime.now().isoformat()
        }
        state_file.write_text(json.dumps(data, indent=2))


# =============================================================================
# 3. MULTI-AGENT ORCHESTRATION
# =============================================================================

class AgentRole(Enum):
    """Specialized agent roles."""
    SCRAPER = "scraper"          # Data extraction specialist
    RESEARCHER = "researcher"    # Information gathering
    WRITER = "writer"            # Content generation
    ANALYZER = "analyzer"        # Data analysis
    NAVIGATOR = "navigator"      # Form filling, login flows
    MONITOR = "monitor"          # Change detection
    COORDINATOR = "coordinator"  # Orchestrates other agents


@dataclass
class AgentTask:
    """A task for a sub-agent."""
    task_id: str
    role: AgentRole
    prompt: str
    target: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)  # Task IDs this depends on
    priority: int = 5
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3
    status: str = "pending"
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class AgentMessage:
    """Message between agents."""
    from_agent: str
    to_agent: str
    message_type: str  # 'handoff', 'data', 'request', 'response', 'alert'
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class MultiAgentOrchestrator:
    """
    Orchestrates multiple specialized agents working together.

    Example workflow:
    1. User: "Research top 5 competitors and summarize their pricing"
    2. Coordinator spawns:
       - Researcher agent to find competitors
       - Scraper agents (parallel) to get pricing from each
       - Analyzer agent to compare
       - Writer agent to create summary
    """

    def __init__(self, max_parallel: int = 5):
        self.max_parallel = max_parallel
        self.tasks: Dict[str, AgentTask] = {}
        self.messages: List[AgentMessage] = []
        self.agents_active: Dict[str, bool] = {}

        # Task execution callbacks (to be set by integrator)
        self.execute_task: Optional[Callable[[AgentTask], Any]] = None

    def plan_workflow(self, user_request: str, parsed: ParsedTask) -> List[AgentTask]:
        """
        Plan a multi-agent workflow for a complex request.
        Returns ordered list of tasks with dependencies.
        """
        tasks = []

        # Simple example: research + compare flow
        if parsed.intent == TaskIntent.COMPARE:
            # Split targets to compare
            targets = self._split_targets(parsed.target)

            # Research each target in parallel
            research_task_ids = []
            for i, target in enumerate(targets):
                task = AgentTask(
                    task_id=f"research_{i}",
                    role=AgentRole.RESEARCHER,
                    prompt=f"Research {target}: find key features, pricing, and reviews",
                    target=target,
                    priority=10
                )
                tasks.append(task)
                research_task_ids.append(task.task_id)

            # Analyze after all research complete
            analyze_task = AgentTask(
                task_id="analyze",
                role=AgentRole.ANALYZER,
                prompt=f"Compare the researched items across features, pricing, and reviews",
                dependencies=research_task_ids,
                priority=5
            )
            tasks.append(analyze_task)

            # Write summary
            write_task = AgentTask(
                task_id="summarize",
                role=AgentRole.WRITER,
                prompt="Create a comparison summary with a table",
                dependencies=["analyze"],
                priority=1
            )
            tasks.append(write_task)

        elif parsed.intent == TaskIntent.FIND_LEADS:
            # Parallel scraping
            task = AgentTask(
                task_id="scrape_leads",
                role=AgentRole.SCRAPER,
                prompt=f"Find leads matching: {parsed.target}",
                target=parsed.target,
                priority=10
            )
            tasks.append(task)

            if parsed.parameters.get('include_email'):
                enrich_task = AgentTask(
                    task_id="enrich_emails",
                    role=AgentRole.RESEARCHER,
                    prompt="Find email addresses for the leads",
                    dependencies=["scrape_leads"],
                    priority=5
                )
                tasks.append(enrich_task)

        # Store tasks
        for task in tasks:
            self.tasks[task.task_id] = task

        return tasks

    def execute_workflow(self) -> Dict[str, Any]:
        """Execute the planned workflow."""
        results = {}

        while True:
            # Find ready tasks (dependencies met)
            ready = self._get_ready_tasks()

            if not ready:
                # Check if all done
                pending = [t for t in self.tasks.values() if t.status == "pending"]
                if not pending:
                    break
                # Wait for running tasks
                time.sleep(0.5)
                continue

            # Execute ready tasks (up to max_parallel)
            for task in ready[:self.max_parallel]:
                task.status = "running"
                task.started_at = datetime.now().isoformat()

                try:
                    if self.execute_task:
                        result = self.execute_task(task)
                        task.result = result
                        task.status = "completed"
                        results[task.task_id] = result
                except Exception as e:
                    task.error = str(e)
                    task.retry_count += 1
                    if task.retry_count < task.max_retries:
                        task.status = "pending"
                    else:
                        task.status = "failed"

                task.completed_at = datetime.now().isoformat()

        return results

    def _get_ready_tasks(self) -> List[AgentTask]:
        """Get tasks that are ready to run (dependencies met)."""
        ready = []

        for task in self.tasks.values():
            if task.status != "pending":
                continue

            # Check dependencies
            deps_met = True
            for dep_id in task.dependencies:
                dep = self.tasks.get(dep_id)
                if not dep or dep.status != "completed":
                    deps_met = False
                    break

            if deps_met:
                ready.append(task)

        # Sort by priority
        ready.sort(key=lambda t: -t.priority)
        return ready

    def _split_targets(self, target: str) -> List[str]:
        """Split a compound target into individual items."""
        # "A vs B vs C" or "A, B, and C" or "A B C"
        separators = [' vs ', ' versus ', ', and ', ', ', ' and ']

        items = [target]
        for sep in separators:
            new_items = []
            for item in items:
                new_items.extend(item.split(sep))
            items = new_items

        return [i.strip() for i in items if i.strip()]

    def send_message(self, msg: AgentMessage):
        """Send message between agents."""
        self.messages.append(msg)
        logger.debug(f"[ORCHESTRATOR] {msg.from_agent} -> {msg.to_agent}: {msg.message_type}")

    def get_messages_for(self, agent_id: str) -> List[AgentMessage]:
        """Get pending messages for an agent."""
        return [m for m in self.messages if m.to_agent == agent_id]


# =============================================================================
# 4. LEARNED AUTOMATION PATTERNS
# =============================================================================

@dataclass
class AutomationPattern:
    """A learned automation pattern that can be reused."""
    pattern_id: str
    name: str
    description: str
    site_pattern: str            # URL pattern this applies to
    steps: List[Dict[str, Any]]  # Sequence of actions
    selectors: Dict[str, str]    # Named selectors
    success_rate: float
    times_used: int
    last_used: str
    tags: List[str]
    created_at: str


class PatternLibrary:
    """
    Library of learned automation patterns.

    - Remembers successful workflows
    - Suggests patterns for similar sites
    - Allows cloning patterns across sites
    - Builds reusable templates
    """

    def __init__(self, storage_dir: Path = None):
        self.storage_dir = storage_dir or Path.home() / '.eversale' / 'patterns'
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.patterns: Dict[str, AutomationPattern] = {}
        self._load_patterns()

    def learn_from_success(
        self,
        url: str,
        steps: List[Dict],
        selectors: Dict[str, str],
        name: Optional[str] = None
    ) -> str:
        """Learn a new pattern from a successful automation."""
        pattern_id = hashlib.md5(f"{url}:{json.dumps(steps)}".encode()).hexdigest()[:12]

        # Extract site pattern from URL
        site_pattern = self._url_to_pattern(url)

        pattern = AutomationPattern(
            pattern_id=pattern_id,
            name=name or f"Pattern for {site_pattern}",
            description=f"Learned automation with {len(steps)} steps",
            site_pattern=site_pattern,
            steps=steps,
            selectors=selectors,
            success_rate=1.0,
            times_used=1,
            last_used=datetime.now().isoformat(),
            tags=self._auto_tag(steps),
            created_at=datetime.now().isoformat()
        )

        self.patterns[pattern_id] = pattern
        self._save_patterns()

        logger.info(f"[PATTERNS] Learned new pattern: {pattern.name}")
        return pattern_id

    def find_matching_patterns(self, url: str) -> List[AutomationPattern]:
        """Find patterns that might work for a URL."""
        matches = []

        for pattern in self.patterns.values():
            if self._pattern_matches_url(pattern.site_pattern, url):
                matches.append(pattern)

        # Sort by success rate and times used
        matches.sort(key=lambda p: (-p.success_rate, -p.times_used))
        return matches

    def suggest_for_task(self, task: ParsedTask) -> List[AutomationPattern]:
        """Suggest patterns based on task type."""
        suggestions = []

        for pattern in self.patterns.values():
            # Match by tags
            task_tags = self._task_to_tags(task)
            overlap = len(set(pattern.tags) & set(task_tags))
            if overlap > 0:
                suggestions.append((pattern, overlap))

        suggestions.sort(key=lambda x: -x[1])
        return [p for p, _ in suggestions[:5]]

    def record_result(self, pattern_id: str, success: bool):
        """Record the result of using a pattern."""
        if pattern_id in self.patterns:
            pattern = self.patterns[pattern_id]
            pattern.times_used += 1
            pattern.last_used = datetime.now().isoformat()

            # Update success rate (weighted average)
            old_weight = pattern.times_used - 1
            pattern.success_rate = (
                (pattern.success_rate * old_weight + (1.0 if success else 0.0)) /
                pattern.times_used
            )

            self._save_patterns()

    def clone_pattern(
        self,
        pattern_id: str,
        new_url: str,
        selector_mapping: Dict[str, str] = None
    ) -> str:
        """Clone a pattern for use on a different site."""
        if pattern_id not in self.patterns:
            raise ValueError(f"Pattern {pattern_id} not found")

        original = self.patterns[pattern_id]

        # Create new pattern
        new_id = hashlib.md5(f"clone:{pattern_id}:{new_url}".encode()).hexdigest()[:12]
        new_site_pattern = self._url_to_pattern(new_url)

        new_selectors = dict(original.selectors)
        if selector_mapping:
            for old_sel, new_sel in selector_mapping.items():
                for key, val in new_selectors.items():
                    if val == old_sel:
                        new_selectors[key] = new_sel

        cloned = AutomationPattern(
            pattern_id=new_id,
            name=f"{original.name} (cloned for {new_site_pattern})",
            description=f"Cloned from {original.pattern_id}",
            site_pattern=new_site_pattern,
            steps=original.steps.copy(),
            selectors=new_selectors,
            success_rate=0.8,  # Start with lower confidence
            times_used=0,
            last_used=datetime.now().isoformat(),
            tags=original.tags.copy(),
            created_at=datetime.now().isoformat()
        )

        self.patterns[new_id] = cloned
        self._save_patterns()

        return new_id

    def _url_to_pattern(self, url: str) -> str:
        """Convert URL to a pattern (domain-based)."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or url

    def _pattern_matches_url(self, pattern: str, url: str) -> bool:
        """Check if a pattern matches a URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return pattern in parsed.netloc or pattern in url

    def _auto_tag(self, steps: List[Dict]) -> List[str]:
        """Auto-generate tags from steps."""
        tags = set()

        for step in steps:
            action = step.get('action', '').lower()
            if 'click' in action:
                tags.add('interactive')
            if 'fill' in action or 'type' in action:
                tags.add('form')
            if 'scrape' in action or 'extract' in action:
                tags.add('scraping')
            if 'login' in action or 'auth' in action:
                tags.add('auth')
            if 'download' in action:
                tags.add('download')

        return list(tags)

    def _task_to_tags(self, task: ParsedTask) -> List[str]:
        """Convert task to tags for matching."""
        tags = []

        intent_to_tags = {
            TaskIntent.SCRAPE: ['scraping', 'data'],
            TaskIntent.FILL_FORM: ['form', 'interactive'],
            TaskIntent.LOGIN: ['auth', 'form'],
            TaskIntent.FIND_LEADS: ['scraping', 'leads', 'data'],
            TaskIntent.DOWNLOAD: ['download'],
            TaskIntent.RESEARCH: ['research', 'reading'],
        }

        tags.extend(intent_to_tags.get(task.intent, []))
        return tags

    def _load_patterns(self):
        """Load patterns from disk."""
        patterns_file = self.storage_dir / 'patterns.json'
        if patterns_file.exists():
            try:
                data = json.loads(patterns_file.read_text())
                for pid, pdata in data.items():
                    self.patterns[pid] = AutomationPattern(**pdata)
            except Exception as e:
                logger.warning(f"Failed to load patterns: {e}")

    def _save_patterns(self):
        """Save patterns to disk."""
        patterns_file = self.storage_dir / 'patterns.json'
        data = {pid: asdict(p) for pid, p in self.patterns.items()}
        patterns_file.write_text(json.dumps(data, indent=2))


# =============================================================================
# 5. CONVERSATION MEMORY
# =============================================================================

@dataclass
class UserPreference:
    """A learned user preference."""
    key: str
    value: Any
    confidence: float
    learned_from: str  # What interaction taught us this
    learned_at: str


@dataclass
class PastRequest:
    """A past user request."""
    request_id: str
    text: str
    parsed_intent: str
    target: str
    result: str
    success: bool
    timestamp: str
    correction: Optional[str] = None  # If user corrected the result


class ConversationMemory:
    """
    Long-term memory of user interactions.

    - Remembers preferences ("always save to CSV")
    - Tracks past requests for context
    - Learns from corrections
    - Builds user profile
    """

    def __init__(self, user_id: str = "default", storage_dir: Path = None):
        self.user_id = user_id
        self.storage_dir = storage_dir or Path.home() / '.eversale' / 'users' / user_id
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.preferences: Dict[str, UserPreference] = {}
        self.past_requests: List[PastRequest] = []
        self.corrections: List[Dict] = []

        self._load()

    def remember_request(
        self,
        text: str,
        parsed: ParsedTask,
        result: str,
        success: bool
    ) -> str:
        """Remember a request and its result."""
        request_id = hashlib.md5(f"{text}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]

        request = PastRequest(
            request_id=request_id,
            text=text,
            parsed_intent=parsed.intent.value,
            target=parsed.target,
            result=result[:500] if result else "",
            success=success,
            timestamp=datetime.now().isoformat()
        )

        self.past_requests.append(request)

        # Keep only recent history
        if len(self.past_requests) > 1000:
            self.past_requests = self.past_requests[-500:]

        self._save()
        return request_id

    def record_correction(self, request_id: str, correction: str):
        """Record when user corrects a result."""
        for req in self.past_requests:
            if req.request_id == request_id:
                req.correction = correction
                req.success = False
                break

        self.corrections.append({
            'request_id': request_id,
            'correction': correction,
            'timestamp': datetime.now().isoformat()
        })

        self._save()

    def learn_preference(self, key: str, value: Any, source: str):
        """Learn a user preference."""
        existing = self.preferences.get(key)

        if existing:
            # Increase confidence if same value
            if existing.value == value:
                existing.confidence = min(1.0, existing.confidence + 0.1)
            else:
                # Conflicting - lower confidence
                existing.confidence *= 0.5
                if existing.confidence < 0.3:
                    existing.value = value
                    existing.confidence = 0.5
        else:
            self.preferences[key] = UserPreference(
                key=key,
                value=value,
                confidence=0.6,
                learned_from=source,
                learned_at=datetime.now().isoformat()
            )

        self._save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a preference value."""
        pref = self.preferences.get(key)
        if pref and pref.confidence > 0.4:
            return pref.value
        return default

    def find_similar_requests(self, text: str, limit: int = 5) -> List[PastRequest]:
        """Find similar past requests."""
        text_words = set(text.lower().split())

        scored = []
        for req in self.past_requests:
            req_words = set(req.text.lower().split())
            overlap = len(text_words & req_words)
            if overlap > 0:
                score = overlap / max(len(text_words), len(req_words))
                scored.append((req, score))

        scored.sort(key=lambda x: -x[1])
        return [r for r, _ in scored[:limit]]

    def get_user_profile(self) -> Dict[str, Any]:
        """Get a summary of user preferences and history."""
        return {
            'user_id': self.user_id,
            'total_requests': len(self.past_requests),
            'success_rate': (
                sum(1 for r in self.past_requests if r.success) /
                len(self.past_requests) if self.past_requests else 0
            ),
            'preferences': {
                k: v.value for k, v in self.preferences.items()
                if v.confidence > 0.5
            },
            'common_intents': self._get_common_intents(),
            'corrections_count': len(self.corrections),
        }

    def _get_common_intents(self) -> Dict[str, int]:
        """Get most common intents."""
        intent_counts = {}
        for req in self.past_requests[-100:]:
            intent_counts[req.parsed_intent] = intent_counts.get(req.parsed_intent, 0) + 1
        return dict(sorted(intent_counts.items(), key=lambda x: -x[1])[:5])

    def _load(self):
        """Load memory from disk."""
        mem_file = self.storage_dir / 'memory.json'
        if mem_file.exists():
            try:
                data = json.loads(mem_file.read_text())

                for key, pdata in data.get('preferences', {}).items():
                    self.preferences[key] = UserPreference(**pdata)

                for rdata in data.get('past_requests', []):
                    self.past_requests.append(PastRequest(**rdata))

                self.corrections = data.get('corrections', [])
            except Exception as e:
                logger.warning(f"Failed to load memory: {e}")

    def _save(self):
        """Save memory to disk."""
        mem_file = self.storage_dir / 'memory.json'
        data = {
            'preferences': {k: asdict(v) for k, v in self.preferences.items()},
            'past_requests': [asdict(r) for r in self.past_requests[-500:]],
            'corrections': self.corrections[-100:],
            'saved_at': datetime.now().isoformat()
        }
        mem_file.write_text(json.dumps(data, indent=2))


# =============================================================================
# 6. WORLD-CLASS AGENT - PUTTING IT ALL TOGETHER
# =============================================================================

class WorldClassAgent:
    """
    The ultimate forever agent - combines all capabilities.

    Features:
    1. Natural language understanding
    2. Proactive monitoring
    3. Multi-agent orchestration
    4. Learned patterns
    5. Conversation memory
    6. Forever operations support
    """

    def __init__(
        self,
        user_id: str = "default",
        work_dir: Path = None
    ):
        self.user_id = user_id
        self.work_dir = work_dir or Path.home() / '.eversale' / 'agent'
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Initialize all components
        self.nlp = NaturalLanguageInterpreter(self.work_dir / 'nlp')
        self.monitor = ProactiveMonitor(self.work_dir / 'monitors')
        self.orchestrator = MultiAgentOrchestrator()
        self.patterns = PatternLibrary(self.work_dir / 'patterns')
        self.memory = ConversationMemory(user_id, self.work_dir / 'memory')

        # Task execution callback (set by Brain integration)
        self.execute_task: Optional[Callable] = None

        logger.info(f"[AGENT] WorldClassAgent initialized for user {user_id}")

    def process_request(self, text: str) -> Dict[str, Any]:
        """
        Process a natural language request.

        This is the main entry point - takes any text and figures out what to do.
        """
        # Parse the request
        parsed = self.nlp.parse(text)
        logger.info(f"[AGENT] Parsed intent: {parsed.intent.value} (confidence: {parsed.confidence:.2f})")

        # Check for similar past requests
        similar = self.memory.find_similar_requests(text)
        if similar and similar[0].success:
            logger.info(f"[AGENT] Found similar successful request from history")

        # Look for matching patterns
        if parsed.target:
            patterns = self.patterns.find_matching_patterns(parsed.target)
            if patterns:
                logger.info(f"[AGENT] Found {len(patterns)} matching patterns")

        # Apply user preferences
        output_format = self.memory.get_preference('output_format', 'csv')
        if not parsed.output:
            parsed.output = f"~/output.{output_format}"

        # Check if this is a forever operation
        is_forever = parsed.intent in [
            TaskIntent.WATCH_FOREVER,
            TaskIntent.PROCESS_QUEUE,
            TaskIntent.MONITOR,
            TaskIntent.CHECK_INBOX
        ]

        result = {
            'parsed': asdict(parsed) if hasattr(parsed, '__dict__') else str(parsed),
            'intent': parsed.intent.value,
            'target': parsed.target,
            'is_forever': is_forever,
            'similar_requests': len(similar),
            'matching_patterns': len(patterns) if 'patterns' in dir() else 0,
        }

        # For complex tasks, plan multi-agent workflow
        if parsed.intent in [TaskIntent.COMPARE, TaskIntent.RESEARCH]:
            tasks = self.orchestrator.plan_workflow(text, parsed)
            result['workflow_tasks'] = len(tasks)

        # Remember this request
        request_id = self.memory.remember_request(
            text=text,
            parsed=parsed,
            result=json.dumps(result),
            success=True  # Will be updated later
        )
        result['request_id'] = request_id

        # Update NLP context
        self.nlp.update_context(
            last_target=parsed.target,
            last_action=parsed.intent.value,
        )

        return result

    def add_watch(
        self,
        url: str,
        watch_for: str = "change",
        interval_minutes: int = 5,
        notify: str = "log"
    ) -> str:
        """Add a monitoring watch."""
        config = MonitorConfig(
            url=url,
            check_type="content" if watch_for == "change" else watch_for,
            interval_seconds=interval_minutes * 60,
            alert_on=watch_for,
            notify_via=notify
        )

        return self.monitor.add_monitor(f"watch_{url[:30]}", config)

    def learn_success(self, url: str, steps: List[Dict], selectors: Dict[str, str]):
        """Learn from a successful automation."""
        return self.patterns.learn_from_success(url, steps, selectors)

    def correct(self, request_id: str, correction: str):
        """Record a correction from the user."""
        self.memory.record_correction(request_id, correction)

        # Also update NLP
        last_text = None
        for req in self.memory.past_requests:
            if req.request_id == request_id:
                last_text = req.text
                break

        if last_text:
            # Learn the correct intent from correction
            corrected_parsed = self.nlp.parse(correction)
            self.nlp.learn_pattern(last_text, corrected_parsed.intent, False)

    def get_status(self) -> Dict[str, Any]:
        """Get agent status."""
        return {
            'user_profile': self.memory.get_user_profile(),
            'patterns_count': len(self.patterns.patterns),
            'active_monitors': len(self.monitor.monitors),
            'pending_tasks': len([t for t in self.orchestrator.tasks.values() if t.status == 'pending']),
        }


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def create_world_class_agent(user_id: str = "default") -> WorldClassAgent:
    """Factory function to create a world-class agent."""
    return WorldClassAgent(user_id=user_id)


def interpret_natural_language(text: str, agent: WorldClassAgent = None) -> Dict[str, Any]:
    """Quick helper to interpret natural language."""
    if agent is None:
        agent = WorldClassAgent()
    return agent.process_request(text)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Demo the natural language interpreter
    nlp = NaturalLanguageInterpreter()

    test_inputs = [
        "scrape the first 10 products from amazon.com",
        "watch that site for price changes and alert me",
        "find leads on facebook ads for saas companies",
        "do it again but for the competitor site",
        "check my email every 5 minutes and respond to urgent ones",
        "research openai and summarize in 3 sentences",
        "compare github copilot vs cursor vs codeium",
        "download all pdfs from that page",
        "fill out the contact form with my info",
        "monitor stocks forever and alert when they drop 5%",
    ]

    for text in test_inputs:
        parsed = nlp.parse(text)
        print(f"\n>>> {text}")
        print(f"    Intent: {parsed.intent.value} (conf: {parsed.confidence:.2f})")
        print(f"    Target: {parsed.target}")
        print(f"    Params: {parsed.parameters}")
        if parsed.conditions:
            print(f"    Conditions: {parsed.conditions}")
        if parsed.schedule:
            print(f"    Schedule: {parsed.schedule}")
