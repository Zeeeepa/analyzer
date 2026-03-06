"""
Text Processing - Classification, Extraction, Summarization.

Core NLP capabilities powered by local LLM.
"""

import re
import json
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from loguru import logger
import ollama


@dataclass
class ProcessingResult:
    """Result from text processing."""
    success: bool
    data: Any = None
    raw_response: str = ""
    error: str = ""


class TextProcessor:
    """
    Text processing using local LLM.

    Capabilities:
    - Classification (categorize text)
    - Extraction (pull out entities, fields)
    - Summarization (condense text)
    - Comparison (analyze differences)
    - Generation (create content from specs)
    """

    def __init__(self, model: str = "llama3.1:8b-instruct-q8_0"):
        self.model = model

    def _call_llm(self, prompt: str, json_mode: bool = False) -> str:
        """Call LLM with prompt."""
        try:
            messages = [{'role': 'user', 'content': prompt}]

            if json_mode:
                # Add JSON instruction
                messages[0]['content'] += "\n\nRespond with valid JSON only, no other text."

            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={'temperature': 0.3}
            )

            return response['message']['content']

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _parse_json(self, text: str) -> Any:
        """Extract JSON from LLM response."""
        def clean_json_string(s: str) -> str:
            """Clean control characters from JSON string."""
            # Replace literal newlines in string values with escaped versions
            # First, normalize line endings
            s = s.replace('\r\n', '\n').replace('\r', '\n')
            # Replace control chars except newlines that are part of JSON structure
            import re as regex
            # This cleans control chars that might be inside string values
            result = []
            in_string = False
            escape_next = False
            for char in s:
                if escape_next:
                    result.append(char)
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    result.append(char)
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    result.append(char)
                    continue
                if in_string and char == '\n':
                    result.append('\\n')
                    continue
                if in_string and char == '\t':
                    result.append('\\t')
                    continue
                result.append(char)
            return ''.join(result)

        # Try direct parse first
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to find JSON in response
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*\}',
            r'\[[\s\S]*\]',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                content = match.group(1) if '```' in pattern else match.group(0)
                # Try parsing as-is
                try:
                    return json.loads(content)
                except (json.JSONDecodeError, ValueError):
                    pass
                # Try with cleaned content
                try:
                    cleaned = clean_json_string(content)
                    return json.loads(cleaned)
                except (json.JSONDecodeError, ValueError):
                    continue

        return None

    # =========== CLASSIFICATION ===========

    def classify(self, text: str, categories: List[str], multi_label: bool = False) -> ProcessingResult:
        """
        Classify text into categories.

        Args:
            text: Text to classify
            categories: List of possible categories
            multi_label: Allow multiple categories

        Returns:
            ProcessingResult with category/categories
        """
        if multi_label:
            prompt = f"""Classify this text into one or more of these categories: {', '.join(categories)}

Text:
{text[:3000]}

Return JSON: {{"categories": ["cat1", "cat2"], "confidence": {{"cat1": 0.9, "cat2": 0.7}}, "reasoning": "brief explanation"}}"""
        else:
            prompt = f"""Classify this text into exactly ONE of these categories: {', '.join(categories)}

Text:
{text[:3000]}

Return JSON: {{"category": "chosen_category", "confidence": 0.95, "reasoning": "brief explanation"}}"""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)
            else:
                # Fallback: find category mention in response
                for cat in categories:
                    if cat.lower() in response.lower():
                        return ProcessingResult(
                            success=True,
                            data={"category": cat, "confidence": 0.7},
                            raw_response=response
                        )

                return ProcessingResult(success=False, error="Could not parse classification", raw_response=response)

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    def classify_priority(self, text: str) -> ProcessingResult:
        """Classify by priority (high/medium/low)."""
        return self.classify(text, ["high", "medium", "low"])

    def classify_sentiment(self, text: str) -> ProcessingResult:
        """Classify sentiment (positive/negative/neutral)."""
        return self.classify(text, ["positive", "negative", "neutral"])

    # =========== EXTRACTION ===========

    def extract_entities(self, text: str, entity_types: List[str] = None) -> ProcessingResult:
        """
        Extract named entities from text.

        Args:
            text: Text to process
            entity_types: Types to extract (default: person, org, date, money, location)

        Returns:
            ProcessingResult with extracted entities
        """
        if not entity_types:
            entity_types = ["person", "organization", "date", "money", "location", "email", "phone"]

        prompt = f"""Extract all entities from this text.

Entity types to find: {', '.join(entity_types)}

Text:
{text[:4000]}

Return JSON: {{"entities": {{"person": ["name1", "name2"], "organization": ["org1"], "date": ["2024-01-15"], "money": ["$1,000"], "location": ["New York"]}}}}

Only include entity types that are actually found."""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)

            return ProcessingResult(success=False, error="Could not parse entities", raw_response=response)

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    def extract_fields(self, text: str, fields: List[str]) -> ProcessingResult:
        """
        Extract specific fields from text.

        Args:
            text: Text to process
            fields: List of field names to extract

        Returns:
            ProcessingResult with field values
        """
        prompt = f"""Extract these specific fields from the text:
{', '.join(fields)}

Text:
{text[:4000]}

Return JSON with field names as keys and extracted values. Use null for fields not found.
Example: {{"field1": "value1", "field2": "value2", "field3": null}}"""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)

            return ProcessingResult(success=False, error="Could not parse fields", raw_response=response)

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    def extract_table(self, text: str, columns: List[str] = None) -> ProcessingResult:
        """
        Extract tabular data from text.

        Args:
            text: Text containing tabular info
            columns: Expected column names (optional)

        Returns:
            ProcessingResult with list of row dicts
        """
        col_hint = f"Expected columns: {', '.join(columns)}" if columns else "Detect columns automatically"

        prompt = f"""Extract tabular data from this text.
{col_hint}

Text:
{text[:4000]}

Return JSON: {{"columns": ["col1", "col2"], "rows": [{{"col1": "val1", "col2": "val2"}}]}}"""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)

            return ProcessingResult(success=False, error="Could not parse table", raw_response=response)

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    # =========== SUMMARIZATION ===========

    def summarize(self, text: str, max_length: int = 200, style: str = "bullet") -> ProcessingResult:
        """
        Summarize text.

        Args:
            text: Text to summarize
            max_length: Approximate max length
            style: "bullet", "paragraph", or "executive"

        Returns:
            ProcessingResult with summary
        """
        style_instructions = {
            "bullet": "Use bullet points. Be concise.",
            "paragraph": "Write a clear paragraph summary.",
            "executive": "Write an executive summary with key takeaways and action items.",
        }

        prompt = f"""Summarize this text in approximately {max_length} words.
{style_instructions.get(style, style_instructions['bullet'])}

Text:
{text[:6000]}

Return JSON: {{"summary": "your summary here", "key_points": ["point1", "point2", "point3"]}}"""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)

            # Fallback: use raw response as summary
            return ProcessingResult(
                success=True,
                data={"summary": response.strip(), "key_points": []},
                raw_response=response
            )

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    def summarize_for_domain(self, text: str, domain: str) -> ProcessingResult:
        """
        Summarize with domain-specific focus.

        Args:
            text: Text to summarize
            domain: Domain context (legal, medical, technical, financial, etc.)
        """
        domain_focus = {
            "legal": "Focus on parties, obligations, dates, terms, and risks.",
            "financial": "Focus on amounts, transactions, dates, and anomalies.",
            "technical": "Focus on errors, causes, solutions, and metrics.",
            "medical": "Focus on conditions, treatments, outcomes, and recommendations.",
            "hr": "Focus on qualifications, experience, skills, and fit assessment.",
            "real_estate": "Focus on property details, condition, value factors, and recommendations.",
        }

        focus = domain_focus.get(domain, f"Focus on key {domain}-related information.")

        prompt = f"""Summarize this {domain} document.
{focus}

Text:
{text[:6000]}

Return JSON: {{
    "summary": "overall summary",
    "key_findings": ["finding1", "finding2"],
    "action_items": ["action1", "action2"],
    "concerns": ["concern1"] or []
}}"""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)

            return ProcessingResult(success=False, error="Could not parse summary", raw_response=response)

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    # =========== COMPARISON ===========

    def compare(self, items: List[Dict], criteria: List[str] = None) -> ProcessingResult:
        """
        Compare multiple items.

        Args:
            items: List of items to compare (dicts with data)
            criteria: Comparison criteria

        Returns:
            ProcessingResult with comparison table and analysis
        """
        if not criteria:
            criteria = ["strengths", "weaknesses", "overall_score"]

        prompt = f"""Compare these {len(items)} items on these criteria: {', '.join(criteria)}

Items:
{json.dumps(items, indent=2)[:4000]}

Return JSON: {{
    "comparison_table": [
        {{"item": "item1", "criteria1": "value", "criteria2": "value"}},
        {{"item": "item2", "criteria1": "value", "criteria2": "value"}}
    ],
    "ranking": ["best_item", "second", "third"],
    "recommendation": "which item is best and why",
    "analysis": "detailed comparison notes"
}}"""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)

            return ProcessingResult(success=False, error="Could not parse comparison", raw_response=response)

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    # =========== GENERATION ===========

    def generate_from_template(self, template: str, data: Dict) -> ProcessingResult:
        """
        Generate text from template and data.

        Args:
            template: Template type or description
            data: Data to use in generation
        """
        prompt = f"""Generate a {template} using this data:

{json.dumps(data, indent=2)[:3000]}

Write professional, clear content. Return the generated text."""

        try:
            response = self._call_llm(prompt)
            return ProcessingResult(
                success=True,
                data={"generated_text": response.strip()},
                raw_response=response
            )

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    def generate_questions(self, text: str, count: int = 5, question_type: str = "mixed") -> ProcessingResult:
        """
        Generate questions from text (for quizzes, study guides).

        Args:
            text: Source text
            count: Number of questions
            question_type: "multiple_choice", "short_answer", "true_false", or "mixed"
        """
        prompt = f"""Generate {count} {question_type} questions based on this text:

{text[:4000]}

Return JSON: {{
    "questions": [
        {{
            "question": "Question text?",
            "type": "multiple_choice",
            "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
            "correct_answer": "A",
            "explanation": "Why this is correct"
        }}
    ]
}}

For short_answer, omit options. For true_false, use options ["True", "False"]."""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)

            return ProcessingResult(success=False, error="Could not parse questions", raw_response=response)

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    def draft_reply(self, original_text: str, context: str = "", tone: str = "professional") -> ProcessingResult:
        """
        Draft a reply to a message/email.

        Args:
            original_text: The message to reply to
            context: Additional context
            tone: "professional", "friendly", "formal", "brief"
        """
        prompt = f"""Draft a {tone} reply to this message:

Original:
{original_text[:2000]}

{f'Context: {context}' if context else ''}

Write a helpful, appropriate reply. Return JSON: {{"reply": "your reply text", "suggested_subject": "Re: ..."}}"""

        try:
            response = self._call_llm(prompt)
            data = self._parse_json(response)

            if data:
                return ProcessingResult(success=True, data=data, raw_response=response)

            # Fallback
            return ProcessingResult(
                success=True,
                data={"reply": response.strip()},
                raw_response=response
            )

        except Exception as e:
            return ProcessingResult(success=False, error=str(e))


# Convenience instance
processor = TextProcessor()


# Convenience functions
def classify(text: str, categories: List[str]) -> Dict:
    """Classify text into categories."""
    result = processor.classify(text, categories)
    return result.data if result.success else {"error": result.error}


def extract_entities(text: str) -> Dict:
    """Extract entities from text."""
    result = processor.extract_entities(text)
    return result.data if result.success else {"error": result.error}


def extract_fields(text: str, fields: List[str]) -> Dict:
    """Extract specific fields from text."""
    result = processor.extract_fields(text, fields)
    return result.data if result.success else {"error": result.error}


def summarize(text: str, style: str = "bullet") -> str:
    """Summarize text."""
    result = processor.summarize(text, style=style)
    if result.success:
        return result.data.get("summary", "")
    return f"Error: {result.error}"


def compare_items(items: List[Dict], criteria: List[str] = None) -> Dict:
    """Compare multiple items."""
    result = processor.compare(items, criteria)
    return result.data if result.success else {"error": result.error}


def draft_reply(text: str, tone: str = "professional") -> str:
    """Draft a reply."""
    result = processor.draft_reply(text, tone=tone)
    if result.success:
        return result.data.get("reply", "")
    return f"Error: {result.error}"
