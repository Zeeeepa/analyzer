"""
LLM-Based Data Extraction - ScrapeGraphAI Style
Extract structured data from web pages using natural language prompts.

Inspired by:
- ScrapeGraphAI - Natural language extraction
- Firecrawl - Schema-based extraction
- Jina Reader - LLM-friendly output

Features:
1. Natural language extraction prompts
2. Schema-based structured extraction
3. Multi-page extraction
4. Auto-retry with alternative prompts
"""

import json
import re
from typing import Dict, List, Any, Optional, Union
from loguru import logger

# Try to import local LLM client
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Rust acceleration bridge
try:
    from .rust_bridge import (
        extract_emails as rust_extract_emails,
        extract_phones as rust_extract_phones,
        CompiledPatterns,
        fast_json_parse,
        is_rust_available
    )
    USE_RUST_CORE = is_rust_available()
except ImportError:
    USE_RUST_CORE = False

if USE_RUST_CORE:
    logger.info("LLM extractor: Rust acceleration enabled for pattern matching")
else:
    logger.info("LLM extractor: Using Python regex (slower)")

# Import hallucination guard for output validation
try:
    from .hallucination_guard import get_guard, ValidationResult
    HALLUCINATION_GUARD_AVAILABLE = True
except ImportError:
    HALLUCINATION_GUARD_AVAILABLE = False


class LLMExtractor:
    """
    Extract structured data from web pages using LLM.

    Usage:
        extractor = LLMExtractor()
        data = await extractor.extract(page_content, "Extract all product names and prices")

    Or with schema:
        schema = {"products": [{"name": "string", "price": "number"}]}
        data = await extractor.extract_with_schema(page_content, schema)
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.llm_url = config.get('llm_url', 'http://localhost:11434/api/generate') if config else 'http://localhost:11434/api/generate'
        # Use 0000/ui-tars-1.5-7b:latest as default - best for tool calling and extraction
        self.model = config.get('model', '0000/ui-tars-1.5-7b:latest') if config else '0000/ui-tars-1.5-7b:latest'
        # Fast model for simple extractions - same model for consistency
        self.fast_model = config.get('fast_model', '0000/ui-tars-1.5-7b:latest') if config else '0000/ui-tars-1.5-7b:latest'
        self.timeout = config.get('timeout', 60) if config else 60

        # Initialize Rust-accelerated pattern matching if available
        if USE_RUST_CORE:
            try:
                self._compiled_patterns = CompiledPatterns()
                logger.debug("LLM extractor: Using Rust-compiled regex patterns")
            except Exception as e:
                logger.warning(f"Failed to initialize Rust patterns: {e}")
                self._compiled_patterns = None
        else:
            self._compiled_patterns = None

    async def extract(
        self,
        content: str,
        prompt: str,
        output_format: str = 'json'
    ) -> Dict[str, Any]:
        """
        Extract data using natural language prompt.

        Args:
            content: Page content (markdown or text)
            prompt: Natural language extraction prompt
            output_format: 'json', 'text', or 'list'

        Returns:
            Extracted data or error

        Example:
            await extractor.extract(
                markdown_content,
                "Extract all company names and their descriptions"
            )
        """
        # Build extraction prompt
        system_prompt = self._build_extraction_prompt(prompt, output_format)

        # Truncate content if too long
        max_content = 8000
        if len(content) > max_content:
            content = content[:max_content] + "\n... [truncated]"

        full_prompt = f"{system_prompt}\n\n---\nCONTENT TO EXTRACT FROM:\n---\n{content}\n---\n\nExtracted data:"

        try:
            # Pass content length for smart model selection
            result = await self._call_llm(full_prompt, content_length=len(content))

            if result.get('error'):
                return result

            # Parse response
            response_text = result.get('response', '')
            parsed = self._parse_response(response_text, output_format)

            output = {
                'success': True,
                'data': parsed,
                'raw_response': response_text,
                'prompt_used': prompt,
                'model_used': result.get('model_used', 'unknown')
            }

            # ANTI-HALLUCINATION: Validate LLM response for hallucination phrases
            if HALLUCINATION_GUARD_AVAILABLE:
                guard = get_guard()
                llm_check = guard.validate_llm_response(response_text, expected_source='llm')
                if not llm_check.is_valid:
                    logger.warning(f"LLM response may contain hallucination: {llm_check.issues}")
                    output['hallucination_warning'] = llm_check.issues

            return output

        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            return {'error': str(e)}

    async def extract_with_schema(
        self,
        content: str,
        schema: Dict[str, Any],
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract data matching a specific JSON schema.

        Args:
            content: Page content
            schema: JSON schema describing expected output
            description: Optional description of what to extract

        Returns:
            Extracted data matching schema

        Example:
            schema = {
                "products": [{
                    "name": "string",
                    "price": "number",
                    "description": "string"
                }]
            }
            await extractor.extract_with_schema(content, schema)
        """
        schema_str = json.dumps(schema, indent=2)

        prompt = f"""Extract data from the content below and return it as JSON matching this exact schema:

{schema_str}

{f"Additional context: {description}" if description else ""}

Rules:
- Return ONLY valid JSON matching the schema
- Use null for missing values
- For arrays, include all matching items found
- Numbers should be actual numbers, not strings
- Dates should be ISO format strings
"""

        result = await self.extract(content, prompt, output_format='json')

        # Validate against schema (basic)
        if result.get('success') and result.get('data'):
            validated = self._validate_schema(result['data'], schema)
            result['schema_valid'] = validated

            # ANTI-HALLUCINATION: Validate extracted data for fake patterns
            if HALLUCINATION_GUARD_AVAILABLE:
                guard = get_guard()
                hallucination_check = guard.validate_output(
                    result['data'],
                    source_tool='llm_extractor',
                    data_type=None  # Check all types
                )
                result['hallucination_check'] = {
                    'passed': hallucination_check.is_valid,
                    'issues': hallucination_check.issues
                }

                # If fake data detected, clean or warn
                if not hallucination_check.is_valid:
                    logger.warning(f"LLM extraction contains potential fake data: {hallucination_check.issues}")
                    # Use cleaned data if available
                    if hallucination_check.cleaned_data:
                        result['data'] = hallucination_check.cleaned_data
                        result['data_was_cleaned'] = True

        return result

    async def extract_entities(
        self,
        content: str,
        entity_types: List[str]
    ) -> Dict[str, Any]:
        """
        Extract specific entity types from content.

        Args:
            content: Page content
            entity_types: List of entity types to extract
                         e.g., ['person', 'company', 'email', 'phone', 'location', 'date', 'money']

        Returns:
            Dict with entity type -> list of found entities
        """
        entities_str = ', '.join(entity_types)

        prompt = f"""Extract all instances of these entity types from the content:
{entities_str}

Return as JSON with entity type as key and array of found values.

Example format:
{{
    "person": ["John Smith", "Jane Doe"],
    "company": ["Acme Corp"],
    "email": ["contact@example.com"],
    "money": ["$1,500", "$99/month"]
}}

Only include entity types that have matches. Be thorough - find ALL instances."""

        result = await self.extract(content, prompt, output_format='json')
        return result

    async def answer_question(
        self,
        content: str,
        question: str
    ) -> Dict[str, Any]:
        """
        Answer a question based on page content.

        Args:
            content: Page content
            question: Question to answer

        Returns:
            Answer with supporting evidence
        """
        prompt = f"""Based ONLY on the content provided, answer this question:

{question}

Rules:
- Only use information from the provided content
- If the answer isn't in the content, say "Not found in content"
- Include relevant quotes as evidence
- Be concise but complete

Return as JSON:
{{
    "answer": "your answer here",
    "confidence": "high/medium/low",
    "evidence": ["relevant quote 1", "relevant quote 2"],
    "found_in_content": true/false
}}"""

        result = await self.extract(content, prompt, output_format='json')
        return result

    async def summarize(
        self,
        content: str,
        style: str = 'concise',
        max_length: int = 500
    ) -> Dict[str, Any]:
        """
        Summarize page content.

        Args:
            content: Page content
            style: 'concise', 'detailed', 'bullets', or 'key_points'
            max_length: Maximum summary length in characters

        Returns:
            Summary of content
        """
        style_instructions = {
            'concise': 'Write a brief 2-3 sentence summary.',
            'detailed': f'Write a comprehensive summary in {max_length} characters or less.',
            'bullets': 'Summarize as 5-7 bullet points.',
            'key_points': 'List the 3-5 most important points.'
        }

        instruction = style_instructions.get(style, style_instructions['concise'])

        prompt = f"""{instruction}

Focus on:
- Main topic/purpose
- Key facts and figures
- Important conclusions

Return as JSON:
{{
    "summary": "your summary here",
    "main_topic": "what this page is about",
    "key_facts": ["fact 1", "fact 2"]
}}"""

        result = await self.extract(content, prompt, output_format='json')
        return result

    async def compare_pages(
        self,
        content1: str,
        content2: str,
        comparison_prompt: str
    ) -> Dict[str, Any]:
        """
        Compare content from two pages.

        Args:
            content1: First page content
            content2: Second page content
            comparison_prompt: What to compare (e.g., "Compare pricing")

        Returns:
            Comparison results
        """
        combined_content = f"""PAGE 1:
{content1[:4000]}

---

PAGE 2:
{content2[:4000]}"""

        prompt = f"""{comparison_prompt}

Compare the two pages above and return:
{{
    "similarities": ["similarity 1", "similarity 2"],
    "differences": ["difference 1", "difference 2"],
    "page1_unique": ["unique to page 1"],
    "page2_unique": ["unique to page 2"],
    "recommendation": "which is better for X and why"
}}"""

        result = await self.extract(combined_content, prompt, output_format='json')
        return result

    def _build_extraction_prompt(self, user_prompt: str, output_format: str) -> str:
        """Build the system prompt for extraction."""
        format_instructions = {
            'json': 'Return ONLY valid JSON. No markdown, no explanations, no code blocks.',
            'text': 'Return the result as plain text.',
            'list': 'Return the result as a JSON array of items.'
        }

        return f"""You are a precise data extraction assistant. Extract information from web page content.

TASK: {user_prompt}

OUTPUT FORMAT: {format_instructions.get(output_format, format_instructions['json'])}

CRITICAL RULES:
1. Extract ALL matching items found in the content
2. Look for data in headings, lists, tables, links, and paragraphs
3. Common patterns to recognize:
   - Titles: h1, h2, h3 tags, bold text, link text
   - Prices: $XX.XX, £XX.XX, numbers followed by currency words
   - Names: Capitalized words, text in quotes
4. If extracting products/books/items, PAIR the title with its price
5. Return structured data - each item as an object with all its properties
6. Be thorough - scan the ENTIRE content
7. Never make up data - only extract what's actually present

Example for "extract books with prices":
[
  {{"title": "Book Name", "price": "£51.77"}},
  {{"title": "Another Book", "price": "£22.65"}}
]
"""

    def _select_model(self, prompt: str, content_length: int) -> str:
        """
        Smart model routing: Choose fast or main model based on task complexity.
        Fast model for: short content, simple extractions, entity extraction
        Main model for: complex reasoning, long content, multi-step tasks
        """
        prompt_lower = prompt.lower()

        # Use fast model for simple tasks
        simple_indicators = [
            'extract all', 'list all', 'find all',  # Simple extraction
            'email', 'phone', 'price', 'name',  # Entity extraction
            'summarize', 'summary',  # Summarization
            'json', 'return as json',  # Structured output
        ]

        # Use main model for complex tasks
        complex_indicators = [
            'compare', 'analyze', 'explain why',  # Analysis
            'multiple steps', 'first', 'then',  # Multi-step
            'relationship', 'correlation',  # Complex reasoning
        ]

        # Check for complexity indicators
        is_complex = any(ind in prompt_lower for ind in complex_indicators)
        is_simple = any(ind in prompt_lower for ind in simple_indicators)

        # Short content + simple task = fast model
        if content_length < 3000 and is_simple and not is_complex:
            return self.fast_model

        # Very short content = fast model
        if content_length < 1500:
            return self.fast_model

        # Default to main model for complex/long tasks
        return self.model

    async def _call_llm(self, prompt: str, content_length: int = 0) -> Dict[str, Any]:
        """Call local LLM via Ollama API with smart model selection."""
        if not HTTPX_AVAILABLE:
            return {'error': 'httpx not installed. Run: pip install httpx'}

        # Smart model selection
        selected_model = self._select_model(prompt, content_length)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.llm_url,
                    json={
                        'model': selected_model,
                        'prompt': prompt,
                        'stream': False,
                        'options': {
                            'temperature': 0.1,  # Low temp for extraction
                            'num_predict': 2000 if selected_model == self.model else 1000
                        }
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    return {'response': data.get('response', ''), 'model_used': selected_model}
                else:
                    return {'error': f'LLM API error: {response.status_code}'}

        except Exception as e:
            return {'error': f'LLM call failed: {e}'}

    def _parse_response(self, response: str, output_format: str) -> Any:
        """Parse LLM response into expected format."""
        response = response.strip()

        if output_format == 'text':
            return response

        # Try to extract JSON
        try:
            # Find JSON in response
            json_match = re.search(r'(\{.*\}|\[.*\])', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                # Use Rust-accelerated JSON parsing if available
                if USE_RUST_CORE:
                    try:
                        return fast_json_parse(json_str)
                    except Exception as e:
                        logger.debug(f"Rust JSON parse failed, using Python: {e}")
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Try parsing entire response as JSON
        try:
            if USE_RUST_CORE:
                try:
                    return fast_json_parse(response)
                except Exception:
                    pass
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Return as-is if JSON parsing fails
        return response

    def _validate_schema(self, data: Any, schema: Dict) -> bool:
        """Basic schema validation."""
        try:
            if isinstance(schema, dict):
                if not isinstance(data, dict):
                    return False
                for key in schema:
                    if key not in data:
                        return False
            return True
        except Exception:
            return False


class BatchExtractor:
    """
    Extract data from multiple pages efficiently.

    Usage:
        batch = BatchExtractor()
        results = await batch.extract_from_urls(browser, urls, "Extract product info")
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.llm_extractor = LLMExtractor(config)

    async def extract_from_urls(
        self,
        playwright_client,
        urls: List[str],
        prompt: str,
        converter=None  # WebToMarkdown instance
    ) -> Dict[str, Any]:
        """
        Extract data from multiple URLs using the same prompt.

        Args:
            playwright_client: Browser client
            urls: List of URLs to extract from
            prompt: Extraction prompt
            converter: WebToMarkdown converter (optional)

        Returns:
            Results for each URL
        """
        results = []

        # Import converter if not provided
        if converter is None:
            try:
                from .web_to_markdown import WebToMarkdown
                converter = WebToMarkdown()
            except ImportError:
                converter = None

        for url in urls:
            try:
                # Navigate
                await playwright_client.navigate(url)

                # Get content
                if converter:
                    content_result = await converter.convert(playwright_client.page)
                    content = content_result.get('markdown', '')
                else:
                    text_result = await playwright_client.get_text()
                    content = text_result.get('text', '')

                # Extract
                extract_result = await self.llm_extractor.extract(content, prompt)

                results.append({
                    'url': url,
                    'success': extract_result.get('success', False),
                    'data': extract_result.get('data'),
                    'error': extract_result.get('error')
                })

            except Exception as e:
                results.append({
                    'url': url,
                    'success': False,
                    'error': str(e)
                })

        return {
            'results': results,
            'total': len(urls),
            'successful': len([r for r in results if r.get('success')])
        }


# Convenience functions
async def extract(content: str, prompt: str) -> Dict[str, Any]:
    """Quick extraction with natural language prompt."""
    extractor = LLMExtractor()
    return await extractor.extract(content, prompt)


async def extract_entities(content: str, entity_types: List[str]) -> Dict[str, Any]:
    """Quick entity extraction."""
    extractor = LLMExtractor()
    return await extractor.extract_entities(content, entity_types)


async def answer(content: str, question: str) -> Dict[str, Any]:
    """Quick Q&A based on content."""
    extractor = LLMExtractor()
    return await extractor.answer_question(content, question)
