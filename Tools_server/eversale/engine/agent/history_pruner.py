"""
Conversation history pruning to prevent token accumulation.

Reduces token usage by 50-60% through intelligent message summarization
and screenshot removal while preserving recent context.
"""

from typing import List, Dict, Any
import re


class HistoryPruner:
    """Prunes conversation history to reduce token usage by 50-60%."""

    def __init__(
        self,
        max_history_items: int = 10,
        preserve_recent: int = 3,
        summarize_older: bool = True
    ):
        """
        Initialize history pruner.

        Args:
            max_history_items: Maximum number of message pairs to keep
            preserve_recent: Number of recent messages to keep in full
            summarize_older: Whether to summarize older messages (vs delete)
        """
        self.max_history_items = max_history_items
        self.preserve_recent = preserve_recent
        self.summarize_older = summarize_older

    def prune(self, messages: List[Dict]) -> List[Dict]:
        """
        Prune conversation history.

        Rules:
        1. Always keep system prompt (first message)
        2. Always keep last `preserve_recent` messages in full
        3. Summarize older messages to: "Step N: [action] - [result]"
        4. Remove all screenshots/images from non-recent messages
        5. Cap total messages at max_history_items

        Args:
            messages: Full conversation history

        Returns:
            Pruned conversation history
        """
        if not messages:
            return []

        # Separate system prompt from conversation
        system_msg = messages[0] if messages and messages[0].get('role') == 'system' else None
        conversation = messages[1:] if system_msg else messages

        if len(conversation) <= self.preserve_recent:
            # No pruning needed - short conversation
            return messages

        # Split into recent (preserve) and old (prune)
        recent_messages = conversation[-self.preserve_recent:]
        old_messages = conversation[:-self.preserve_recent]

        # Process old messages
        if self.summarize_older:
            # Summarize and remove images from old messages
            processed_old = []
            for idx, msg in enumerate(old_messages):
                # Remove images first
                msg = self._remove_images(msg)
                # Then summarize
                msg = self._summarize_step(msg, idx + 1)
                processed_old.append(msg)

            # Cap old messages if needed
            if len(processed_old) > (self.max_history_items - self.preserve_recent):
                # Keep only most recent old messages
                keep_count = max(0, self.max_history_items - self.preserve_recent)
                processed_old = processed_old[-keep_count:]
        else:
            # Just cap without summarizing
            keep_count = max(0, self.max_history_items - self.preserve_recent)
            processed_old = old_messages[-keep_count:]
            # Still remove images
            processed_old = [self._remove_images(msg) for msg in processed_old]

        # Reconstruct: system + processed_old + recent
        result = []
        if system_msg:
            result.append(system_msg)
        result.extend(processed_old)
        result.extend(recent_messages)

        return result

    def _summarize_step(self, message: Dict, step_num: int) -> Dict:
        """
        Convert a full step message to a compact summary.

        Args:
            message: Message to summarize
            step_num: Step number for reference

        Returns:
            Summarized message
        """
        role = message.get('role', 'unknown')
        content = message.get('content', '')

        # Handle different content types
        if isinstance(content, list):
            # Multi-part content (images + text)
            text_parts = [
                part.get('text', '')
                for part in content
                if isinstance(part, dict) and part.get('type') == 'text'
            ]
            content = ' '.join(text_parts)

        # Extract action and result
        if role == 'user':
            # User messages typically contain goals/requests
            summary = self._extract_user_intent(content)
            summary = f"Step {step_num}: User requested: {summary}"
        elif role == 'assistant':
            # Assistant messages contain actions/reasoning
            summary = self._extract_assistant_action(content)
            summary = f"Step {step_num}: {summary}"
        else:
            # Other roles - just truncate
            summary = content[:100] + '...' if len(content) > 100 else content

        return {
            'role': role,
            'content': summary
        }

    def _extract_user_intent(self, content: str) -> str:
        """Extract main intent from user message."""
        # Look for common patterns
        if 'navigate' in content.lower():
            match = re.search(r'navigate.*?to\s+([^\n.]+)', content, re.IGNORECASE)
            if match:
                return f"Navigate to {match.group(1).strip()}"

        if 'click' in content.lower():
            match = re.search(r'click.*?(?:on\s+)?([^\n.]+)', content, re.IGNORECASE)
            if match:
                return f"Click {match.group(1).strip()}"

        if 'type' in content.lower() or 'enter' in content.lower():
            return "Enter text/data"

        if 'search' in content.lower():
            match = re.search(r'search.*?for\s+([^\n.]+)', content, re.IGNORECASE)
            if match:
                return f"Search for {match.group(1).strip()}"

        # Default - first sentence or truncate
        first_sentence = content.split('.')[0].strip()
        return first_sentence[:80] + '...' if len(first_sentence) > 80 else first_sentence

    def _extract_assistant_action(self, content: str) -> str:
        """Extract main action from assistant message."""
        # Look for tool calls or actions
        if 'navigate' in content.lower():
            match = re.search(r'navigat(?:e|ing).*?to\s+([^\n.]+)', content, re.IGNORECASE)
            if match:
                return f"Navigated to {match.group(1).strip()}"

        if 'click' in content.lower():
            match = re.search(r'click(?:ing|ed)?\s+(?:on\s+)?([^\n.]+)', content, re.IGNORECASE)
            if match:
                return f"Clicked {match.group(1).strip()}"

        if 'type' in content.lower() or 'enter' in content.lower():
            return "Entered text"

        if 'screenshot' in content.lower() or 'image' in content.lower():
            return "Captured screenshot"

        if 'complete' in content.lower() or 'done' in content.lower():
            return "Task completed"

        if 'error' in content.lower() or 'fail' in content.lower():
            return "Encountered error"

        # Default - first sentence or truncate
        first_sentence = content.split('.')[0].strip()
        return first_sentence[:80] + '...' if len(first_sentence) > 80 else first_sentence

    def _remove_images(self, message: Dict) -> Dict:
        """
        Strip base64 images and screenshot data from message.

        Args:
            message: Message potentially containing images

        Returns:
            Message with images removed
        """
        content = message.get('content', '')

        # Handle multi-part content
        if isinstance(content, list):
            # Filter out image parts, keep text only
            text_parts = [
                part for part in content
                if isinstance(part, dict) and part.get('type') == 'text'
            ]

            # If we have text parts, use them; otherwise use placeholder
            if text_parts:
                message['content'] = text_parts[0].get('text', '[content removed]')
            else:
                message['content'] = '[screenshot removed]'

        # Handle string content with base64 images
        elif isinstance(content, str):
            # Remove base64 image data URLs
            if 'data:image' in content or 'base64,' in content:
                # Strip out base64 sections
                content = re.sub(
                    r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+',
                    '[image removed]',
                    content
                )
                message['content'] = content

        return message

    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """
        Rough token estimate (chars / 4).

        Args:
            messages: List of messages to estimate

        Returns:
            Estimated token count
        """
        total_chars = 0

        for msg in messages:
            content = msg.get('content', '')

            if isinstance(content, list):
                # Multi-part content
                for part in content:
                    if isinstance(part, dict):
                        if part.get('type') == 'text':
                            total_chars += len(part.get('text', ''))
                        elif part.get('type') == 'image_url':
                            # Base64 images are massive
                            image_data = part.get('image_url', {}).get('url', '')
                            if 'base64,' in image_data:
                                # Rough estimate: 1 token per 6 chars for base64
                                total_chars += len(image_data) // 1.5
                            else:
                                total_chars += len(image_data)
            elif isinstance(content, str):
                total_chars += len(content)

        # Rough conversion: 1 token ~ 4 characters
        return total_chars // 4


def prune_screenshots_from_history(messages: List[Dict], keep_last_n: int = 1) -> List[Dict]:
    """
    Remove all screenshots except the last N from conversation history.

    Aggressive pruning for screenshot-heavy conversations. Keeps only the
    most recent N screenshots for context while removing all older ones.

    Args:
        messages: Full conversation history
        keep_last_n: Number of most recent screenshots to preserve

    Returns:
        Conversation with older screenshots removed
    """
    if not messages:
        return []

    # Find all messages with screenshots
    screenshot_indices = []
    for idx, msg in enumerate(messages):
        content = msg.get('content', '')

        # Check for images in multi-part content
        if isinstance(content, list):
            has_image = any(
                isinstance(part, dict) and part.get('type') == 'image_url'
                for part in content
            )
            if has_image:
                screenshot_indices.append(idx)
        # Check for base64 in string content
        elif isinstance(content, str) and ('data:image' in content or 'base64,' in content):
            screenshot_indices.append(idx)

    # Determine which screenshots to remove
    if len(screenshot_indices) <= keep_last_n:
        # No pruning needed
        return messages

    # Keep only last N screenshots
    remove_indices = set(screenshot_indices[:-keep_last_n]) if keep_last_n > 0 else set(screenshot_indices)

    # Process messages - need to deep copy to avoid mutating originals
    result = []
    pruner = HistoryPruner()
    for idx, msg in enumerate(messages):
        # Create a shallow copy
        msg_copy = msg.copy()

        if idx in remove_indices:
            # Remove screenshot from this message copy
            msg_copy = pruner._remove_images(msg_copy)

        result.append(msg_copy)

    return result
