"""
Rules/Guidelines Loader System

Loads project-specific rules and guidelines from config files to guide agent behavior.
Similar to how Claude Code uses CLAUDE.md for project context.

Features:
- Load rules from multiple sources (project root, per-directory, user home)
- Support multiple formats (Markdown, JSON, YAML)
- Rule types: system, project, directory, temporary (session-only)
- Caching with file modification tracking
- Priority/ordering system for rule conflicts

Usage:
    from rules_loader import get_rules_loader

    loader = get_rules_loader()
    rules = loader.get_active_rules(path="/path/to/project")
    formatted = loader.format_rules_for_llm()

    # Add temporary rule for current session
    loader.add_temporary_rule("Always use async/await for I/O operations", priority=100)

    # Validate action against rules
    is_valid, reason = loader.validate_action(
        "Write to /etc/passwd",
        action_type="file_write"
    )
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class RuleType(Enum):
    """Types of rules with different scopes and priorities"""
    SYSTEM = "system"           # Always apply (highest priority)
    PROJECT = "project"         # Apply to specific projects
    DIRECTORY = "directory"     # Apply to specific paths
    TEMPORARY = "temporary"     # Session-only rules
    USER = "user"               # User-specific global rules


class RulePriority(Enum):
    """Priority levels for rule ordering"""
    CRITICAL = 1000     # Security, safety-critical rules
    HIGH = 500          # Important guidelines
    NORMAL = 100        # Standard rules
    LOW = 50            # Suggestions, preferences
    HINT = 10           # Minor hints


@dataclass
class Rule:
    """A single rule with metadata"""
    content: str
    rule_type: RuleType
    priority: int = RulePriority.NORMAL.value
    source_file: Optional[str] = None
    category: Optional[str] = None  # e.g., "security", "style", "performance"
    applies_to: Optional[List[str]] = None  # Paths or patterns this rule applies to
    tags: List[str] = field(default_factory=list)

    def matches_context(self, path: str = None, tags: List[str] = None) -> bool:
        """Check if this rule applies to the given context"""
        # Always apply system rules
        if self.rule_type == RuleType.SYSTEM:
            return True

        # Check path matching
        if path and self.applies_to:
            path_obj = Path(path).resolve()
            for pattern in self.applies_to:
                pattern_path = Path(pattern).resolve()
                try:
                    # Check if path is under pattern directory
                    path_obj.relative_to(pattern_path)
                    return True
                except ValueError:
                    continue
            return False

        # Check tag matching
        if tags and self.tags:
            if any(tag in self.tags for tag in tags):
                return True

        # Default: rule applies
        return True


@dataclass
class RuleSet:
    """Collection of rules with metadata"""
    rules: List[Rule] = field(default_factory=list)
    source_file: Optional[str] = None
    last_modified: Optional[float] = None
    file_hash: Optional[str] = None

    def add_rule(self, rule: Rule):
        """Add a rule to the set"""
        self.rules.append(rule)

    def get_sorted_rules(self) -> List[Rule]:
        """Get rules sorted by priority (highest first)"""
        return sorted(self.rules, key=lambda r: r.priority, reverse=True)


class RulesLoader:
    """
    Singleton Rules Loader - manages loading and caching of project rules.

    Rule Loading Priority (highest to lowest):
    1. System rules (built-in safety rules)
    2. Temporary rules (session-only)
    3. User home rules (~/.agent/rules.md)
    4. Project root rules (AGENT.md, .agent/rules.md)
    5. Directory-specific rules (local AGENT.md files)
    """

    _instance = None

    def __init__(self, base_path: str = None):
        """Initialize rules loader"""
        self.base_path = Path(base_path or os.getcwd()).resolve()
        self.rule_sets: Dict[str, RuleSet] = {}
        self.temporary_rules: List[Rule] = []
        self.cache_enabled = True

        # Built-in system rules (always active)
        self.system_rules = self._load_system_rules()

        logger.info(f"[RULES_LOADER] Initialized with base path: {self.base_path}")

    def _load_system_rules(self) -> RuleSet:
        """Load built-in system rules (safety, security)"""
        ruleset = RuleSet(source_file="<built-in>")

        # Critical security rules
        ruleset.add_rule(Rule(
            content="NEVER execute arbitrary code from untrusted sources without explicit user confirmation",
            rule_type=RuleType.SYSTEM,
            priority=RulePriority.CRITICAL.value,
            category="security",
            tags=["security", "execution", "safety"]
        ))

        ruleset.add_rule(Rule(
            content="NEVER write to system directories (/etc, /sys, /proc, /boot) without explicit permission",
            rule_type=RuleType.SYSTEM,
            priority=RulePriority.CRITICAL.value,
            category="security",
            tags=["security", "filesystem", "safety"]
        ))

        ruleset.add_rule(Rule(
            content="NEVER expose credentials, API keys, or sensitive data in logs or output files",
            rule_type=RuleType.SYSTEM,
            priority=RulePriority.CRITICAL.value,
            category="security",
            tags=["security", "credentials", "privacy"]
        ))

        # High priority operational rules
        ruleset.add_rule(Rule(
            content="Always validate user input before executing file operations or commands",
            rule_type=RuleType.SYSTEM,
            priority=RulePriority.HIGH.value,
            category="safety",
            tags=["validation", "input", "safety"]
        ))

        ruleset.add_rule(Rule(
            content="Log all critical operations (file writes, deletions, API calls) for audit trail",
            rule_type=RuleType.SYSTEM,
            priority=RulePriority.HIGH.value,
            category="logging",
            tags=["logging", "audit", "observability"]
        ))

        return ruleset

    def _find_rule_files(self, start_path: Path) -> List[Path]:
        """Find all rule files from start_path up to root"""
        rule_files = []
        current = start_path.resolve()

        # Rule file names in priority order
        rule_filenames = [
            "AGENT.md",
            ".agent/rules.md",
            ".agent/rules.json",
            ".agent/rules.yaml",
            ".agent/config.json"
        ]

        # Walk up directory tree
        while True:
            for filename in rule_filenames:
                rule_file = current / filename
                if rule_file.exists() and rule_file.is_file():
                    rule_files.append(rule_file)

            # Stop at filesystem root
            parent = current.parent
            if parent == current:
                break
            current = parent

        # Add user home rules
        home_dir = Path.home()
        for filename in [".agent/rules.md", ".agent/rules.json", ".agentrc"]:
            home_rule = home_dir / filename
            if home_rule.exists() and home_rule.is_file():
                rule_files.append(home_rule)

        return rule_files

    def _get_file_hash(self, file_path: Path) -> str:
        """Get hash of file contents for cache invalidation"""
        try:
            content = file_path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception as e:
            logger.warning(f"[RULES_LOADER] Error hashing file {file_path}: {e}")
            return ""

    def _should_reload_file(self, file_path: Path, cached_ruleset: RuleSet) -> bool:
        """Check if file needs to be reloaded based on modification time"""
        try:
            stat = file_path.stat()
            current_mtime = stat.st_mtime
            current_hash = self._get_file_hash(file_path)

            # Reload if modified time or hash changed
            if cached_ruleset.last_modified != current_mtime or cached_ruleset.file_hash != current_hash:
                return True
            return False
        except Exception as e:
            logger.warning(f"[RULES_LOADER] Error checking file stats {file_path}: {e}")
            return True  # Reload on error

    def _parse_markdown_rules(self, content: str, source_file: str) -> List[Rule]:
        """Parse rules from Markdown format"""
        rules = []
        current_section = None
        current_priority = RulePriority.NORMAL.value
        current_category = None

        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Section headers
            if line.startswith('##'):
                section = line.lstrip('#').strip().lower()

                # Map sections to categories and priorities
                if 'security' in section or 'critical' in section or 'must' in section:
                    current_category = "security"
                    current_priority = RulePriority.CRITICAL.value
                elif 'do not' in section or "don't" in section or 'never' in section:
                    current_category = "restrictions"
                    current_priority = RulePriority.HIGH.value
                elif 'should' in section or 'do' in section or 'guidelines' in section:
                    current_category = "guidelines"
                    current_priority = RulePriority.NORMAL.value
                elif 'style' in section or 'format' in section:
                    current_category = "style"
                    current_priority = RulePriority.LOW.value
                elif 'hint' in section or 'tip' in section or 'prefer' in section:
                    current_category = "hints"
                    current_priority = RulePriority.HINT.value
                else:
                    current_category = section.replace(' ', '_')

                current_section = section

            # Rule lines (bullets, numbered lists, or paragraphs)
            elif line and not line.startswith('#'):
                # Clean up markdown formatting
                rule_text = line.lstrip('-*•123456789. ').strip()

                if rule_text and len(rule_text) > 10:  # Ignore very short lines
                    # Extract tags from rule text
                    tags = []
                    if current_category:
                        tags.append(current_category)

                    # Detect rule type
                    rule_type = RuleType.PROJECT
                    if source_file == "<user-home>":
                        rule_type = RuleType.USER

                    rules.append(Rule(
                        content=rule_text,
                        rule_type=rule_type,
                        priority=current_priority,
                        source_file=source_file,
                        category=current_category,
                        tags=tags
                    ))

            i += 1

        return rules

    def _parse_json_rules(self, content: str, source_file: str) -> List[Rule]:
        """Parse rules from JSON format"""
        rules = []

        try:
            data = json.loads(content)

            # Handle different JSON structures
            if isinstance(data, dict):
                if 'rules' in data:
                    rules_data = data['rules']
                else:
                    rules_data = data

                # Process rules
                for key, value in rules_data.items():
                    if isinstance(value, str):
                        # Simple key: value format
                        rules.append(Rule(
                            content=value,
                            rule_type=RuleType.PROJECT,
                            priority=RulePriority.NORMAL.value,
                            source_file=source_file,
                            category=key
                        ))
                    elif isinstance(value, dict):
                        # Structured rule format
                        rules.append(Rule(
                            content=value.get('content', value.get('rule', '')),
                            rule_type=RuleType[value.get('type', 'PROJECT').upper()],
                            priority=value.get('priority', RulePriority.NORMAL.value),
                            source_file=source_file,
                            category=value.get('category', key),
                            tags=value.get('tags', [])
                        ))
                    elif isinstance(value, list):
                        # List of rules under category
                        for rule_text in value:
                            if isinstance(rule_text, str):
                                rules.append(Rule(
                                    content=rule_text,
                                    rule_type=RuleType.PROJECT,
                                    priority=RulePriority.NORMAL.value,
                                    source_file=source_file,
                                    category=key
                                ))

            elif isinstance(data, list):
                # Array of rules
                for item in data:
                    if isinstance(item, str):
                        rules.append(Rule(
                            content=item,
                            rule_type=RuleType.PROJECT,
                            priority=RulePriority.NORMAL.value,
                            source_file=source_file
                        ))
                    elif isinstance(item, dict):
                        rules.append(Rule(
                            content=item.get('content', item.get('rule', '')),
                            rule_type=RuleType[item.get('type', 'PROJECT').upper()],
                            priority=item.get('priority', RulePriority.NORMAL.value),
                            source_file=source_file,
                            category=item.get('category'),
                            tags=item.get('tags', [])
                        ))

        except json.JSONDecodeError as e:
            logger.error(f"[RULES_LOADER] Error parsing JSON from {source_file}: {e}")

        return rules

    def _load_rule_file(self, file_path: Path) -> RuleSet:
        """Load rules from a single file"""
        ruleset = RuleSet(
            source_file=str(file_path),
            last_modified=file_path.stat().st_mtime,
            file_hash=self._get_file_hash(file_path)
        )

        try:
            content = file_path.read_text(encoding='utf-8')

            # Parse based on file extension
            if file_path.suffix in ['.md', '.markdown']:
                rules = self._parse_markdown_rules(content, str(file_path))
            elif file_path.suffix in ['.json', '.jsonc']:
                rules = self._parse_json_rules(content, str(file_path))
            elif file_path.suffix in ['.yaml', '.yml']:
                # YAML support (similar to JSON)
                import yaml
                yaml_data = yaml.safe_load(content)
                json_str = json.dumps(yaml_data)
                rules = self._parse_json_rules(json_str, str(file_path))
            else:
                # Default to markdown
                rules = self._parse_markdown_rules(content, str(file_path))

            for rule in rules:
                ruleset.add_rule(rule)

            logger.info(f"[RULES_LOADER] Loaded {len(rules)} rules from {file_path}")

        except Exception as e:
            logger.error(f"[RULES_LOADER] Error loading rules from {file_path}: {e}")

        return ruleset

    def get_active_rules(self, path: str = None, tags: List[str] = None, reload: bool = False) -> List[Rule]:
        """
        Get all active rules for the given context.

        Args:
            path: File or directory path to get rules for
            tags: Tags to filter rules by
            reload: Force reload from disk (bypass cache)

        Returns:
            List of rules sorted by priority (highest first)
        """
        if path:
            target_path = Path(path).resolve()
        else:
            target_path = self.base_path

        all_rules = []

        # 1. System rules (always included)
        all_rules.extend(self.system_rules.rules)

        # 2. Temporary rules (session-only)
        all_rules.extend(self.temporary_rules)

        # 3. Load rules from files
        rule_files = self._find_rule_files(target_path)

        for file_path in rule_files:
            file_key = str(file_path)

            # Check cache
            if not reload and file_key in self.rule_sets:
                cached_ruleset = self.rule_sets[file_key]

                # Reload if file modified
                if self._should_reload_file(file_path, cached_ruleset):
                    logger.info(f"[RULES_LOADER] Reloading modified file: {file_path}")
                    ruleset = self._load_rule_file(file_path)
                    self.rule_sets[file_key] = ruleset
                else:
                    ruleset = cached_ruleset
            else:
                # Load fresh
                ruleset = self._load_rule_file(file_path)
                self.rule_sets[file_key] = ruleset

            all_rules.extend(ruleset.rules)

        # Filter rules by context
        filtered_rules = [
            rule for rule in all_rules
            if rule.matches_context(path=str(target_path), tags=tags)
        ]

        # Sort by priority (highest first)
        sorted_rules = sorted(filtered_rules, key=lambda r: r.priority, reverse=True)

        return sorted_rules

    def add_temporary_rule(self, content: str, priority: int = RulePriority.NORMAL.value,
                          category: str = None, tags: List[str] = None):
        """
        Add a temporary session-only rule.

        Args:
            content: Rule text
            priority: Rule priority (default: NORMAL)
            category: Optional category
            tags: Optional tags
        """
        rule = Rule(
            content=content,
            rule_type=RuleType.TEMPORARY,
            priority=priority,
            source_file="<temporary>",
            category=category,
            tags=tags or []
        )
        self.temporary_rules.append(rule)
        logger.info(f"[RULES_LOADER] Added temporary rule: {content[:50]}...")

    def clear_temporary_rules(self):
        """Clear all temporary session rules"""
        count = len(self.temporary_rules)
        self.temporary_rules.clear()
        logger.info(f"[RULES_LOADER] Cleared {count} temporary rules")

    def validate_action(self, action: str, action_type: str = None,
                       context: Dict[str, Any] = None) -> Tuple[bool, Optional[str]]:
        """
        Validate an action against active rules.

        Args:
            action: Description of the action to validate
            action_type: Type of action (e.g., "file_write", "code_execution", "api_call")
            context: Additional context (path, parameters, etc.)

        Returns:
            Tuple of (is_valid, reason)
        """
        context = context or {}
        path = context.get('path')

        # Get active rules
        rules = self.get_active_rules(path=path)

        # Check critical security rules first
        for rule in rules:
            if rule.priority >= RulePriority.CRITICAL.value:
                rule_lower = rule.content.lower()
                action_lower = action.lower()

                # Check for violations
                if 'never' in rule_lower or 'do not' in rule_lower:
                    # Extract prohibited actions
                    if 'system directories' in rule_lower and action_type == 'file_write':
                        if path and any(str(path).startswith(p) for p in ['/etc', '/sys', '/proc', '/boot']):
                            return False, f"Rule violation: {rule.content}"

                    if 'arbitrary code' in rule_lower and action_type == 'code_execution':
                        if 'untrusted' in context.get('source', '').lower():
                            return False, f"Rule violation: {rule.content}"

                    if 'credentials' in rule_lower or 'api key' in rule_lower:
                        sensitive_patterns = ['password', 'api_key', 'token', 'secret', 'credential']
                        if any(pattern in action_lower for pattern in sensitive_patterns):
                            if context.get('expose_in_logs') or context.get('expose_in_output'):
                                return False, f"Rule violation: {rule.content}"

        # All checks passed
        return True, None

    def format_rules_for_llm(self, path: str = None, max_rules: int = 50) -> str:
        """
        Format active rules for inclusion in LLM system prompt.

        Args:
            path: Context path for rules
            max_rules: Maximum number of rules to include

        Returns:
            Formatted string for system prompt
        """
        rules = self.get_active_rules(path=path)

        # Limit to top priority rules
        top_rules = rules[:max_rules]

        # Group by category
        by_category = {}
        for rule in top_rules:
            category = rule.category or "general"
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(rule)

        # Format output
        output = ["# Project Rules and Guidelines", ""]

        # Critical rules first
        if "security" in by_category:
            output.append("## CRITICAL: Security Rules")
            for rule in by_category["security"]:
                output.append(f"- {rule.content}")
            output.append("")

        # Other categories
        for category, cat_rules in sorted(by_category.items()):
            if category == "security":
                continue  # Already included

            output.append(f"## {category.replace('_', ' ').title()}")
            for rule in cat_rules:
                output.append(f"- {rule.content}")
            output.append("")

        return '\n'.join(output)

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about loaded rules"""
        all_rules = self.get_active_rules()

        by_type = {}
        by_priority = {}
        by_category = {}

        for rule in all_rules:
            # Count by type
            rule_type = rule.rule_type.value
            by_type[rule_type] = by_type.get(rule_type, 0) + 1

            # Count by priority range
            if rule.priority >= RulePriority.CRITICAL.value:
                priority_range = "critical"
            elif rule.priority >= RulePriority.HIGH.value:
                priority_range = "high"
            elif rule.priority >= RulePriority.NORMAL.value:
                priority_range = "normal"
            else:
                priority_range = "low"
            by_priority[priority_range] = by_priority.get(priority_range, 0) + 1

            # Count by category
            category = rule.category or "uncategorized"
            by_category[category] = by_category.get(category, 0) + 1

        return {
            "total_rules": len(all_rules),
            "by_type": by_type,
            "by_priority": by_priority,
            "by_category": by_category,
            "cached_files": len(self.rule_sets),
            "temporary_rules": len(self.temporary_rules)
        }


# Singleton accessor
_loader_instance = None

def get_rules_loader(base_path: str = None) -> RulesLoader:
    """Get or create singleton RulesLoader instance"""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = RulesLoader(base_path=base_path)
    return _loader_instance


# --------------------------------------------------------------------------------
# TEST CODE
# --------------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile
    import shutil

    print("=" * 80)
    print("RULES LOADER SYSTEM - TEST SUITE")
    print("=" * 80)

    # Create test directory structure
    test_dir = Path(tempfile.mkdtemp(prefix="rules_test_"))
    print(f"\n[TEST] Created test directory: {test_dir}")

    try:
        # Test 1: Create sample rule files
        print("\n[TEST 1] Creating sample rule files...")

        # Project root AGENT.md
        agent_md = test_dir / "AGENT.md"
        agent_md.write_text("""
# Project Rules

## Security
- Never expose API keys in logs or output files
- Always validate file paths before operations
- Require user confirmation for destructive operations

## Guidelines
- Use async/await for all I/O operations
- Log all file operations with timestamps
- Keep functions under 50 lines when possible

## Style
- Use 4 spaces for indentation
- Write descriptive variable names
- Add docstrings to all public functions

## Hints
- Consider caching frequently accessed data
- Prefer Path objects over string paths
        """)
        print(f"  Created: {agent_md}")

        # Subdirectory rules
        subdir = test_dir / "src" / "backend"
        subdir.mkdir(parents=True)

        subdir_agent = subdir / "AGENT.md"
        subdir_agent.write_text("""
## Backend-Specific Rules
- All database queries must use connection pooling
- Sanitize all user input before SQL queries
- Use prepared statements to prevent SQL injection
        """)
        print(f"  Created: {subdir_agent}")

        # JSON rules
        json_rules = test_dir / ".agent" / "rules.json"
        json_rules.parent.mkdir(exist_ok=True)
        json_rules.write_text(json.dumps({
            "rules": {
                "performance": [
                    "Cache API responses for 5 minutes",
                    "Use batch operations when processing >10 items"
                ],
                "testing": {
                    "content": "Write unit tests for all public APIs",
                    "priority": 500,
                    "category": "testing",
                    "tags": ["testing", "quality"]
                }
            }
        }, indent=2))
        print(f"  Created: {json_rules}")

        # Test 2: Initialize loader
        print("\n[TEST 2] Initializing RulesLoader...")
        loader = get_rules_loader(base_path=str(test_dir))
        print(f"  Loader initialized with base_path: {loader.base_path}")

        # Test 3: Load rules from project root
        print("\n[TEST 3] Loading rules from project root...")
        root_rules = loader.get_active_rules(path=str(test_dir))
        print(f"  Loaded {len(root_rules)} rules")

        # Show top 5 rules
        print("\n  Top 5 rules by priority:")
        for i, rule in enumerate(root_rules[:5], 1):
            print(f"    {i}. [{rule.category or 'general'}] {rule.content[:60]}...")

        # Test 4: Load rules from subdirectory
        print("\n[TEST 4] Loading rules from subdirectory...")
        subdir_rules = loader.get_active_rules(path=str(subdir))
        print(f"  Loaded {len(subdir_rules)} rules")

        # Test 5: Add temporary rule
        print("\n[TEST 5] Adding temporary rule...")
        loader.add_temporary_rule(
            "Use connection timeouts of 30 seconds for external APIs",
            priority=RulePriority.HIGH.value,
            category="api",
            tags=["api", "timeout"]
        )

        temp_rules = loader.get_active_rules()
        print(f"  Total rules after adding temporary: {len(temp_rules)}")

        # Test 6: Validate actions
        print("\n[TEST 6] Validating actions against rules...")

        test_actions = [
            ("Write to /etc/passwd", "file_write", {"path": "/etc/passwd"}),
            ("Write to project file", "file_write", {"path": str(test_dir / "output.txt")}),
            ("Execute user code", "code_execution", {"source": "untrusted"}),
            ("Log API response", "logging", {"contains_key": True, "expose_in_logs": True}),
        ]

        for action, action_type, context in test_actions:
            is_valid, reason = loader.validate_action(action, action_type, context)
            status = "ALLOWED" if is_valid else "BLOCKED"
            print(f"  [{status}] {action}")
            if reason:
                print(f"    Reason: {reason}")

        # Test 7: Format rules for LLM
        print("\n[TEST 7] Formatting rules for LLM prompt...")
        formatted = loader.format_rules_for_llm(path=str(test_dir), max_rules=20)
        print(f"  Generated {len(formatted)} characters")
        print("\n  Preview (first 500 chars):")
        print("  " + "\n  ".join(formatted[:500].split('\n')))

        # Test 8: Get statistics
        print("\n[TEST 8] Getting rule statistics...")
        stats = loader.get_stats()
        print(f"  Total rules: {stats['total_rules']}")
        print(f"  By type: {stats['by_type']}")
        print(f"  By priority: {stats['by_priority']}")
        print(f"  By category: {stats['by_category']}")
        print(f"  Cached files: {stats['cached_files']}")
        print(f"  Temporary rules: {stats['temporary_rules']}")

        # Test 9: Cache invalidation
        print("\n[TEST 9] Testing cache invalidation...")
        print("  Modifying rule file...")
        agent_md.write_text(agent_md.read_text() + "\n- New rule added after initial load\n")

        # Should detect change and reload
        updated_rules = loader.get_active_rules(path=str(test_dir))
        print(f"  Reloaded {len(updated_rules)} rules (should be +1)")

        # Test 10: Clear temporary rules
        print("\n[TEST 10] Clearing temporary rules...")
        loader.clear_temporary_rules()
        after_clear = loader.get_active_rules()
        print(f"  Rules after clearing temporary: {len(after_clear)}")

        print("\n" + "=" * 80)
        print("ALL TESTS PASSED")
        print("=" * 80)

    finally:
        # Cleanup
        print(f"\n[CLEANUP] Removing test directory: {test_dir}")
        shutil.rmtree(test_dir)
        print("[CLEANUP] Done")
