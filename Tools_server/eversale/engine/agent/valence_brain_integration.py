"""
Valence System - Brain Integration Example

This shows how the brain (brain_enhanced_v2.py) can use the valence system
to adjust its decision-making based on emotional state.

Integration points:
1. Include emotional context in LLM prompts
2. Adjust speed/verification based on motivation
3. Check if should pause before risky actions
4. Use valence to guide strategy selection
"""

from typing import Dict, Any, Optional
from loguru import logger

from agent.organism_core import get_organism
from agent.valence_system import ValenceSystem


class ValenceAwareBrain:
    """
    Example brain wrapper that adjusts behavior based on valence.

    This demonstrates how to integrate the valence system into
    decision-making without modifying the existing brain code.
    """

    def __init__(self, brain, valence_system: ValenceSystem):
        """
        Initialize valence-aware brain wrapper.

        Args:
            brain: The existing brain instance (brain_enhanced_v2.py)
            valence_system: The valence system instance
        """
        self.brain = brain
        self.valence = valence_system

    def augment_prompt(self, base_prompt: str) -> str:
        """
        Add emotional context to LLM prompts.

        This gives the LLM awareness of the agent's emotional state
        so it can adjust its reasoning accordingly.
        """
        # Check if should pause
        should_pause, reason = self.valence.should_pause()
        if should_pause:
            logger.warning(f"Agent in emotional distress: {reason}")
            # Could add pause notice to prompt
            pause_context = f"\n\n⚠️ EMOTIONAL DISTRESS: {reason}\n"
        else:
            pause_context = ""

        # Get emotional context
        emotional_context = self.valence.get_emotional_context()

        # Augment prompt
        augmented = f"""{base_prompt}

{pause_context}
{emotional_context}

IMPORTANT: Adjust your approach based on the emotional state:
- If stressed/struggling → be more careful, slower, verify more
- If content/thriving → be efficient, confident, take on challenges
- If neutral → operate normally
"""
        return augmented

    def should_verify_action(self, action: str, tool: str) -> bool:
        """
        Decide if an action should be verified before execution.

        Uses motivation system to determine verification level.
        """
        motivation = self.valence.get_motivation()
        verification_level = motivation["verification_level"]

        # High-risk actions always verify
        high_risk_tools = [
            "playwright_fill",  # Entering data
            "playwright_click", # Clicking buttons
        ]

        if tool in high_risk_tools:
            return True

        # Otherwise, use motivation level
        return verification_level >= 1

    def get_speed_multiplier(self) -> float:
        """
        Get speed multiplier based on emotional state.

        Returns:
            float: Speed multiplier (0.5 = slow, 1.0 = normal, 1.5 = fast)
        """
        motivation = self.valence.get_motivation()
        return motivation["speed_multiplier"]

    def get_retry_strategy(self) -> Dict[str, Any]:
        """
        Get retry strategy based on emotional state.

        Returns:
            dict with retry parameters
        """
        motivation = self.valence.get_motivation()
        risk_tolerance = motivation["risk_tolerance"]

        # Low risk tolerance → more retries, longer delays
        if risk_tolerance < 0.3:
            return {
                "max_retries": 5,
                "delay_seconds": 3.0,
                "exponential_backoff": True,
                "verify_before_retry": True,
            }
        elif risk_tolerance < 0.6:
            return {
                "max_retries": 3,
                "delay_seconds": 1.0,
                "exponential_backoff": False,
                "verify_before_retry": False,
            }
        else:
            return {
                "max_retries": 2,
                "delay_seconds": 0.5,
                "exponential_backoff": False,
                "verify_before_retry": False,
            }

    def should_take_action(self, action: str, tool: str, risk_level: str) -> tuple[bool, Optional[str]]:
        """
        Decide if an action should be taken given current emotional state.

        Args:
            action: Description of the action
            tool: Tool to be used
            risk_level: "low", "medium", "high"

        Returns:
            (should_proceed: bool, reason: str or None)
        """
        # Check for pause state
        should_pause, pause_reason = self.valence.should_pause()
        if should_pause:
            return False, f"Paused due to emotional distress: {pause_reason}"

        # Get risk tolerance
        motivation = self.valence.get_motivation()
        risk_tolerance = motivation["risk_tolerance"]

        # Map risk level to required tolerance
        risk_requirements = {
            "low": 0.0,     # Always ok
            "medium": 0.4,  # Need some confidence
            "high": 0.7,    # Need high confidence
        }

        required_tolerance = risk_requirements.get(risk_level, 0.5)

        if risk_tolerance < required_tolerance:
            return False, (
                f"Current emotional state ({motivation['strategy']}) "
                f"is too cautious for {risk_level}-risk action. "
                f"Risk tolerance: {risk_tolerance:.2f}, required: {required_tolerance:.2f}"
            )

        return True, None

    async def execute_with_valence_awareness(
        self,
        action: str,
        tool: str,
        arguments: Dict,
        risk_level: str = "medium"
    ) -> Dict[str, Any]:
        """
        Execute an action with full valence awareness.

        This wraps the brain's execution with valence checks and adjustments.

        Args:
            action: Action description
            tool: Tool name
            arguments: Tool arguments
            risk_level: "low", "medium", "high"

        Returns:
            dict with execution result
        """
        # 1. Check if should proceed
        should_proceed, reason = self.should_take_action(action, tool, risk_level)
        if not should_proceed:
            logger.warning(f"Action blocked by valence system: {reason}")
            return {
                "success": False,
                "error": reason,
                "blocked_by_valence": True,
            }

        # 2. Adjust speed
        speed_multiplier = self.get_speed_multiplier()
        if speed_multiplier < 1.0:
            logger.info(f"Slowing down action by {speed_multiplier:.1f}x due to emotional state")
            # Could add delays here
        elif speed_multiplier > 1.0:
            logger.info(f"Speeding up action by {speed_multiplier:.1f}x (feeling confident)")

        # 3. Verify if needed
        should_verify = self.should_verify_action(action, tool)
        if should_verify:
            logger.info("Extra verification required due to emotional state")
            # Could add verification step here

        # 4. Get retry strategy
        retry_strategy = self.get_retry_strategy()

        # 5. Augment prompt if calling LLM
        # (This would be done in the actual brain execution)

        # 6. Execute action (delegating to actual brain)
        logger.info(
            f"Executing {tool} with valence awareness: "
            f"mood={self.valence.get_mood()}, "
            f"strategy={self.valence.get_motivation()['strategy']}"
        )

        # Placeholder - actual brain would execute here
        result = {
            "success": True,
            "tool": tool,
            "valence_adjusted": True,
            "speed_multiplier": speed_multiplier,
            "verification_level": self.valence.get_motivation()["verification_level"],
        }

        return result


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

def example_brain_integration():
    """Show how to integrate valence into the brain."""

    # Get organism (assumes it's been initialized)
    organism = get_organism()
    if not organism:
        logger.error("Organism not initialized")
        return

    # Get or create valence system
    # (In practice, this would be created when organism is initialized)
    from agent.valence_system import create_valence_system
    valence = create_valence_system(organism.event_bus)

    # Wrap brain with valence awareness
    # brain = BrainEnhancedV2(...)  # Your actual brain
    # valence_brain = ValenceAwareBrain(brain, valence)

    # Example 1: Augment prompt with emotional context
    base_prompt = "Navigate to example.com and extract the title"

    # This adds emotional context to the prompt
    # augmented_prompt = valence_brain.augment_prompt(base_prompt)
    # logger.info(f"Augmented prompt:\n{augmented_prompt}")

    # Example 2: Check if should take risky action
    # should_proceed, reason = valence_brain.should_take_action(
    #     action="Submit payment form",
    #     tool="playwright_click",
    #     risk_level="high"
    # )
    #
    # if should_proceed:
    #     logger.info("Proceeding with high-risk action")
    #     # Execute
    # else:
    #     logger.warning(f"Blocking high-risk action: {reason}")

    # Example 3: Execute with full valence awareness
    # result = await valence_brain.execute_with_valence_awareness(
    #     action="Click submit button",
    #     tool="playwright_click",
    #     arguments={"selector": "button[type=submit]"},
    #     risk_level="medium"
    # )

    logger.info("Valence integration example complete")


# =============================================================================
# INTEGRATION INTO EXISTING BRAIN
# =============================================================================

def integrate_into_brain_v2():
    """
    How to integrate valence into brain_enhanced_v2.py without major refactoring.

    Add these methods to BrainEnhancedV2 class:
    """

    integration_code = '''
class BrainEnhancedV2:
    """Enhanced brain with valence awareness."""

    def __init__(self, ...):
        # Existing initialization
        ...

        # Add valence system
        self.organism = get_organism()
        if self.organism:
            from agent.valence_system import create_valence_system
            self.valence = create_valence_system(self.organism.event_bus)
        else:
            self.valence = None

    async def think(self, user_input: str) -> str:
        """Main thinking loop - augmented with valence."""

        # Check emotional state
        if self.valence:
            should_pause, reason = self.valence.should_pause()
            if should_pause:
                return f"I need to pause and assess. {reason}"

        # Build prompt with emotional context
        base_prompt = self._build_base_prompt(user_input)

        if self.valence:
            # Add emotional context
            emotional_context = self.valence.get_emotional_context()
            augmented_prompt = f"{base_prompt}\\n\\n{emotional_context}"
        else:
            augmented_prompt = base_prompt

        # Continue with existing logic
        response = await self.llm.chat(augmented_prompt)
        ...

    async def execute_tool(self, tool: str, arguments: dict) -> dict:
        """Execute tool with valence-based adjustments."""

        # Get motivation
        if self.valence:
            motivation = self.valence.get_motivation()

            # Adjust based on strategy
            if motivation["strategy"] == "defensive":
                logger.warning("Defensive mode - adding extra verification")
                # Add verification step

            elif motivation["strategy"] == "cautious":
                logger.info("Cautious mode - slowing down")
                await asyncio.sleep(1.0)  # Add delay

        # Execute tool (existing logic)
        result = await self._execute_tool_internal(tool, arguments)

        return result
'''

    logger.info("Integration code example generated")
    return integration_code


if __name__ == "__main__":
    logger.info("Valence brain integration example")
    logger.info("=" * 70)

    # Show integration code
    code = integrate_into_brain_v2()
    print("\nINTEGRATION CODE:\n")
    print(code)
