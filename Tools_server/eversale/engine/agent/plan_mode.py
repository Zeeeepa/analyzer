"""
Plan Mode System - Safe planning before execution

Based on OpenCode's session/prompt/plan.txt pattern, this module enables
read-only planning mode where the agent can:
1. Analyze requirements and ask clarifying questions
2. Think through solutions and tradeoffs
3. Construct comprehensive implementation plans
4. Observe and inspect without making changes

When plan mode is active:
- No file edits, modifications, or system changes allowed
- No write commands (sed, tee, echo >, cat <<EOF)
- Only inspection and analysis tools available
- Agent focuses on understanding and planning

Integration:
- Works with brain_enhanced_v2.py for mode tracking
- Modifies tool availability based on mode
- Tracks planning state per session
- Provides planning prompts and constraints
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


# Planning mode storage directory
PLAN_MODE_DIR = Path("memory/plan_mode")
PLAN_MODE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class PlanState:
    """
    State for a planning session.

    Tracks:
    - session_id: Unique session identifier
    - active: Whether plan mode is currently active
    - plan_content: The accumulated plan being built
    - requirements: Clarified requirements from user
    - considerations: Risks, tradeoffs, questions
    - created_at: When plan mode started
    - updated_at: Last plan update time
    """
    session_id: str
    active: bool = False
    plan_content: str = ""
    requirements: List[str] = field(default_factory=list)
    considerations: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'session_id': self.session_id,
            'active': self.active,
            'plan_content': self.plan_content,
            'requirements': self.requirements,
            'considerations': self.considerations,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PlanState':
        """Create from dictionary."""
        created_at = datetime.fromisoformat(data['created_at']) if data.get('created_at') else None
        updated_at = datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None

        return cls(
            session_id=data['session_id'],
            active=data.get('active', False),
            plan_content=data.get('plan_content', ''),
            requirements=data.get('requirements', []),
            considerations=data.get('considerations', []),
            created_at=created_at,
            updated_at=updated_at,
        )


class PlanMode:
    """
    Plan Mode Manager - Enables safe planning before execution.

    Features:
    1. Read-only planning mode activation/deactivation
    2. Tool availability modification based on mode
    3. Planning prompt injection
    4. Plan state persistence per session

    Usage:
        plan_mode = PlanMode()

        # Enter planning mode
        plan_mode.enter_plan_mode("session_123")

        # Check if in plan mode
        if plan_mode.is_plan_mode("session_123"):
            # Filter tools to read-only
            allowed_tools = plan_mode.get_allowed_tools(all_tools)

        # Exit plan mode
        plan_mode.exit_plan_mode("session_123")
    """

    # Read-only tools allowed in plan mode
    INSPECTION_TOOLS = {
        # Browser inspection (read-only)
        'playwright_navigate',
        'playwright_screenshot',
        'playwright_snapshot',
        'playwright_get_text',
        'playwright_get_markdown',
        'playwright_get_page_info',

        # File system inspection (read-only)
        'read_file',
        'list_directory',
        'glob_files',
        'grep_content',
        'search_files',

        # Data extraction (read-only)
        'playwright_llm_extract',
        'playwright_extract_list',
        'playwright_extract_structured',
        'playwright_extract_entities',

        # Analysis tools
        'analyze_page',
        'get_page_structure',
        'validate_selector',
    }

    # Commands blocked in plan mode (write operations)
    BLOCKED_COMMANDS = {
        'sed',      # Stream editor (file modification)
        'tee',      # Write to file
        'write',    # Direct write operations
        'edit',     # File editing
        'mv',       # File moving
        'cp',       # File copying
        'rm',       # File deletion
        'mkdir',    # Directory creation
        'touch',    # File creation
        'chmod',    # Permission changes
        'chown',    # Ownership changes
    }

    def __init__(self):
        """Initialize plan mode manager."""
        self._sessions: Dict[str, PlanState] = {}
        self._load_sessions()

    def enter_plan_mode(self, session_id: str) -> bool:
        """
        Activate plan mode for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if successfully entered plan mode
        """
        try:
            if session_id not in self._sessions:
                self._sessions[session_id] = PlanState(
                    session_id=session_id,
                    active=True,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
            else:
                self._sessions[session_id].active = True
                self._sessions[session_id].updated_at = datetime.now()

            self._save_session(session_id)
            logger.info(f"[PlanMode] Entered plan mode for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"[PlanMode] Failed to enter plan mode: {e}")
            return False

    def exit_plan_mode(self, session_id: str) -> bool:
        """
        Deactivate plan mode for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if successfully exited plan mode
        """
        try:
            if session_id in self._sessions:
                self._sessions[session_id].active = False
                self._sessions[session_id].updated_at = datetime.now()
                self._save_session(session_id)
                logger.info(f"[PlanMode] Exited plan mode for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"[PlanMode] Failed to exit plan mode: {e}")
            return False

    def is_plan_mode(self, session_id: str) -> bool:
        """
        Check if session is in plan mode.

        Args:
            session_id: Session identifier

        Returns:
            True if in plan mode, False otherwise
        """
        if session_id not in self._sessions:
            return False
        return self._sessions[session_id].active

    def get_plan_prompt(self) -> str:
        """
        Get the planning mode system prompt.

        Returns:
            System prompt for planning mode
        """
        return """
# PLAN MODE ACTIVE

You are in PLANNING MODE - a read-only analysis and planning phase.

## Your Role
Carefully analyze the user's request, think through the solution,
and create a comprehensive implementation plan.

## Constraints (READ-ONLY)
- NO file edits, modifications, or system changes
- NO write commands: sed, tee, echo >, cat <<EOF, mv, cp, rm
- NO creating, modifying, or deleting files
- ONLY observation, inspection, and analysis

## What You CAN Do
1. Read files and inspect directory structure
2. Navigate and screenshot web pages
3. Extract and analyze data (read-only)
4. Ask clarifying questions
5. Propose solutions and discuss tradeoffs

## Planning Process
1. **Understand Requirements**
   - What is the user trying to accomplish?
   - What are the constraints and requirements?
   - What questions need clarification?

2. **Analyze Current State**
   - Inspect relevant files and systems
   - Understand existing architecture
   - Identify dependencies and integration points

3. **Design Solution**
   - Propose approach and alternatives
   - Consider tradeoffs and risks
   - Think through edge cases

4. **Create Implementation Plan**
   - Break down into specific steps
   - Identify files to modify
   - List risks and mitigation strategies

## Plan Output Format
When ready, provide:

### Goal
[Clear summary of what we're accomplishing]

### Approach
[High-level solution strategy]

### Implementation Steps
1. [Specific step with file/action]
2. [Specific step with file/action]
...

### Files to Modify
- /path/to/file1.py - [what changes]
- /path/to/file2.ts - [what changes]

### Risks & Considerations
- [Risk 1 and mitigation]
- [Risk 2 and mitigation]

### Questions for User
- [Clarifying question 1]
- [Clarifying question 2]

Remember: This is PLANNING ONLY. Once the plan is approved,
exit plan mode to begin execution.
"""

    def get_allowed_tools(self, all_tools: List[str]) -> List[str]:
        """
        Filter tools based on plan mode.

        In plan mode, only inspection tools are allowed.

        Args:
            all_tools: List of all available tool names

        Returns:
            List of allowed tool names
        """
        # If not tracking sessions, allow all
        if not self._sessions:
            return all_tools

        # Return intersection of inspection tools and available tools
        return [tool for tool in all_tools if tool in self.INSPECTION_TOOLS]

    def is_command_allowed(self, command: str) -> bool:
        """
        Check if a shell command is allowed in plan mode.

        Args:
            command: Shell command to check

        Returns:
            True if allowed, False if blocked
        """
        # Extract the base command (first word)
        base_cmd = command.strip().split()[0] if command.strip() else ''

        # Check against blocked commands
        if base_cmd in self.BLOCKED_COMMANDS:
            return False

        # Check for redirect operators (write operations)
        if '>' in command or '>>' in command:
            return False

        # Check for heredoc (cat << EOF, echo << EOF)
        if '<<' in command:
            return False

        return True

    def update_plan_content(self, session_id: str, content: str):
        """
        Update the plan content for a session.

        Args:
            session_id: Session identifier
            content: Plan content to store
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = PlanState(
                session_id=session_id,
                created_at=datetime.now(),
            )

        self._sessions[session_id].plan_content = content
        self._sessions[session_id].updated_at = datetime.now()
        self._save_session(session_id)

    def add_requirement(self, session_id: str, requirement: str):
        """
        Add a requirement to the plan.

        Args:
            session_id: Session identifier
            requirement: Requirement text
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = PlanState(
                session_id=session_id,
                created_at=datetime.now(),
            )

        self._sessions[session_id].requirements.append(requirement)
        self._sessions[session_id].updated_at = datetime.now()
        self._save_session(session_id)

    def add_consideration(self, session_id: str, consideration: str):
        """
        Add a consideration/risk to the plan.

        Args:
            session_id: Session identifier
            consideration: Consideration text
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = PlanState(
                session_id=session_id,
                created_at=datetime.now(),
            )

        self._sessions[session_id].considerations.append(consideration)
        self._sessions[session_id].updated_at = datetime.now()
        self._save_session(session_id)

    def get_plan_state(self, session_id: str) -> Optional[PlanState]:
        """
        Get the plan state for a session.

        Args:
            session_id: Session identifier

        Returns:
            PlanState if exists, None otherwise
        """
        return self._sessions.get(session_id)

    def _save_session(self, session_id: str):
        """Save session state to disk."""
        try:
            if session_id not in self._sessions:
                return

            path = PLAN_MODE_DIR / f"{session_id}.json"
            state = self._sessions[session_id]
            path.write_text(json.dumps(state.to_dict(), indent=2))

        except Exception as e:
            logger.error(f"[PlanMode] Failed to save session {session_id}: {e}")

    def _load_sessions(self):
        """Load all session states from disk."""
        try:
            for path in PLAN_MODE_DIR.glob("*.json"):
                try:
                    data = json.loads(path.read_text())
                    state = PlanState.from_dict(data)
                    self._sessions[state.session_id] = state
                except Exception as e:
                    logger.error(f"[PlanMode] Failed to load {path}: {e}")

        except Exception as e:
            logger.error(f"[PlanMode] Failed to load sessions: {e}")


# Singleton instance
_plan_mode_instance: Optional[PlanMode] = None


def get_plan_mode() -> PlanMode:
    """
    Get the singleton PlanMode instance.

    Returns:
        PlanMode instance
    """
    global _plan_mode_instance
    if _plan_mode_instance is None:
        _plan_mode_instance = PlanMode()
    return _plan_mode_instance


def enter_plan_mode(session_id: str) -> bool:
    """
    Convenience function to enter plan mode.

    Args:
        session_id: Session identifier

    Returns:
        True if successful
    """
    return get_plan_mode().enter_plan_mode(session_id)


def exit_plan_mode(session_id: str) -> bool:
    """
    Convenience function to exit plan mode.

    Args:
        session_id: Session identifier

    Returns:
        True if successful
    """
    return get_plan_mode().exit_plan_mode(session_id)


def is_plan_mode(session_id: str) -> bool:
    """
    Convenience function to check plan mode.

    Args:
        session_id: Session identifier

    Returns:
        True if in plan mode
    """
    return get_plan_mode().is_plan_mode(session_id)


# ============================================================================
# TEST SUITE
# ============================================================================

def test_plan_mode():
    """
    Test plan mode functionality.

    Tests:
    1. Enter/exit plan mode
    2. Tool filtering
    3. Command blocking
    4. Plan state management
    """
    print("\n" + "="*70)
    print("PLAN MODE TEST SUITE")
    print("="*70 + "\n")

    # Initialize
    plan_mode = PlanMode()
    session_id = "test_session_123"

    # Test 1: Enter plan mode
    print("Test 1: Enter Plan Mode")
    print("-" * 40)
    result = plan_mode.enter_plan_mode(session_id)
    assert result is True, "Failed to enter plan mode"
    assert plan_mode.is_plan_mode(session_id), "Not in plan mode"
    print("✓ Successfully entered plan mode")
    print(f"✓ is_plan_mode returned True")

    # Test 2: Tool filtering
    print("\nTest 2: Tool Filtering")
    print("-" * 40)
    all_tools = [
        'playwright_navigate',
        'playwright_click',
        'playwright_fill',
        'playwright_screenshot',
        'read_file',
        'write_file',
        'edit_file',
        'playwright_get_markdown',
    ]

    allowed = plan_mode.get_allowed_tools(all_tools)
    print(f"All tools: {len(all_tools)}")
    print(f"Allowed in plan mode: {len(allowed)}")
    print(f"Allowed tools: {allowed}")

    assert 'playwright_navigate' in allowed, "Navigate should be allowed"
    assert 'playwright_screenshot' in allowed, "Screenshot should be allowed"
    assert 'read_file' in allowed, "Read should be allowed"
    assert 'write_file' not in allowed, "Write should be blocked"
    assert 'edit_file' not in allowed, "Edit should be blocked"
    assert 'playwright_click' not in allowed, "Click should be blocked"
    print("✓ Tool filtering works correctly")

    # Test 3: Command blocking
    print("\nTest 3: Command Blocking")
    print("-" * 40)

    safe_commands = [
        'ls -la',
        'cat file.txt',
        'grep "pattern" file.txt',
        'find . -name "*.py"',
    ]

    blocked_commands = [
        'sed -i "s/old/new/" file.txt',
        'echo "content" > file.txt',
        'cat <<EOF > file.txt',
        'mv file1.txt file2.txt',
        'rm file.txt',
        'touch newfile.txt',
    ]

    print("Safe commands:")
    for cmd in safe_commands:
        result = plan_mode.is_command_allowed(cmd)
        print(f"  {cmd}: {result}")
        assert result is True, f"Should allow: {cmd}"

    print("\nBlocked commands:")
    for cmd in blocked_commands:
        result = plan_mode.is_command_allowed(cmd)
        print(f"  {cmd}: {result}")
        assert result is False, f"Should block: {cmd}"

    print("✓ Command blocking works correctly")

    # Test 4: Plan state management
    print("\nTest 4: Plan State Management")
    print("-" * 40)

    plan_mode.add_requirement(session_id, "Must support async operations")
    plan_mode.add_requirement(session_id, "Must integrate with existing auth")
    plan_mode.add_consideration(session_id, "Risk: Breaking changes to API")
    plan_mode.update_plan_content(session_id, "Detailed plan content here...")

    state = plan_mode.get_plan_state(session_id)
    assert state is not None, "Plan state not found"
    assert len(state.requirements) == 2, "Requirements not saved"
    assert len(state.considerations) == 1, "Considerations not saved"
    assert state.plan_content == "Detailed plan content here...", "Plan content not saved"

    print(f"Requirements: {len(state.requirements)}")
    for req in state.requirements:
        print(f"  - {req}")
    print(f"Considerations: {len(state.considerations)}")
    for con in state.considerations:
        print(f"  - {con}")
    print(f"Plan content length: {len(state.plan_content)} chars")
    print("✓ Plan state management works correctly")

    # Test 5: Exit plan mode
    print("\nTest 5: Exit Plan Mode")
    print("-" * 40)
    result = plan_mode.exit_plan_mode(session_id)
    assert result is True, "Failed to exit plan mode"
    assert not plan_mode.is_plan_mode(session_id), "Still in plan mode"
    print("✓ Successfully exited plan mode")
    print(f"✓ is_plan_mode returned False")

    # Test 6: Get plan prompt
    print("\nTest 6: Get Plan Prompt")
    print("-" * 40)
    prompt = plan_mode.get_plan_prompt()
    assert "PLAN MODE ACTIVE" in prompt, "Prompt missing header"
    assert "READ-ONLY" in prompt, "Prompt missing constraints"
    assert "Implementation Steps" in prompt, "Prompt missing format"
    print(f"Plan prompt length: {len(prompt)} chars")
    print("✓ Plan prompt generated correctly")

    # Summary
    print("\n" + "="*70)
    print("ALL TESTS PASSED")
    print("="*70)
    print("\nPlan mode system is ready for integration with brain_enhanced_v2.py")
    print("\nUsage example:")
    print("  from plan_mode import enter_plan_mode, is_plan_mode, exit_plan_mode")
    print("  ")
    print("  # Enter planning phase")
    print("  enter_plan_mode('session_123')")
    print("  ")
    print("  # Check and filter tools")
    print("  if is_plan_mode('session_123'):")
    print("      allowed_tools = get_plan_mode().get_allowed_tools(all_tools)")
    print("  ")
    print("  # Exit and begin execution")
    print("  exit_plan_mode('session_123')")


if __name__ == "__main__":
    test_plan_mode()
