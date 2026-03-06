"""
PDF/SOP Upload Parser - Extract structured workflows from PDF documents.

Converts PDF SOPs (Standard Operating Procedures) into executable workflows.
Uses PyMuPDF for PDF extraction and LLM for step extraction.

Features:
- PDF text and image extraction
- Vision-based step analysis
- Automatic action type detection
- Variable detection from action text
- JSON workflow generation
"""

import base64
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
from loguru import logger

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None
    logger.warning("PyMuPDF not available - PDF parsing disabled")

from .llm_client import LLMClient, get_llm_client
from .workflows import WorkflowStep


@dataclass
class SOPStep:
    """A single step extracted from an SOP document."""
    number: int
    action: str
    target: Optional[str] = None
    expected_result: Optional[str] = None
    screenshot: Optional[str] = None  # base64 encoded image
    notes: Optional[str] = None


@dataclass
class ParsedSOP:
    """Complete parsed SOP document."""
    title: str
    description: str
    steps: List[SOPStep] = field(default_factory=list)
    estimated_duration: int = 60  # minutes
    source_pages: int = 0
    variables: List[str] = field(default_factory=list)


@dataclass
class WorkflowVariable:
    """Variable to be filled in during workflow execution."""
    name: str
    type: str  # "text", "email", "date", "number", "url", "select"
    default_value: Optional[str] = None
    detected_from: str = ""  # which step detected this
    description: Optional[str] = None


@dataclass
class Workflow:
    """Executable workflow generated from SOP."""
    id: str
    name: str
    description: str
    variables: List[WorkflowVariable] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)
    source_recording_id: Optional[str] = None
    estimated_duration: int = 0  # seconds
    success_rate: float = 0.0
    times_executed: int = 0


class SOPParser:
    """
    Parse PDF/document SOPs into structured workflows.
    Uses local Ollama or external GPU for extraction and understanding.
    """

    # Regex patterns for variable detection
    VARIABLE_PATTERNS = {
        'email': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
        'phone': r'^[\d\-\(\)\s\+]+$',
        'date': r'^\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}$',
        'url': r'^https?:\/\/',
        'number': r'^\d+$',
    }

    # Action keywords to action type mapping
    ACTION_KEYWORDS = {
        'navigate': ['navigate', 'go to', 'open', 'visit', 'browse to', 'access'],
        'click': ['click', 'press', 'tap', 'select button', 'choose button', 'hit'],
        'fill': ['enter', 'type', 'fill', 'input', 'write', 'paste'],
        'select': ['select', 'choose', 'pick from dropdown'],
        'wait': ['wait', 'pause', 'delay', 'hold'],
        'extract': ['extract', 'copy', 'get', 'read', 'find'],
        'verify': ['verify', 'check', 'confirm', 'ensure', 'validate'],
    }

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize SOP parser.

        Args:
            llm_client: Optional LLM client. If not provided, uses default.
        """
        self.llm = llm_client or get_llm_client()

        if not PYMUPDF_AVAILABLE:
            logger.warning("PDF parsing unavailable - install PyMuPDF: pip install PyMuPDF")

    async def parse_pdf(self, pdf_path: str) -> ParsedSOP:
        """
        Parse PDF SOP document into structured format.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ParsedSOP with extracted steps

        Raises:
            ImportError: If PyMuPDF is not installed
            FileNotFoundError: If PDF file doesn't exist
        """
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF required for PDF parsing. Install: pip install PyMuPDF")

        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(f"Parsing PDF: {pdf_path}")

        # Open PDF document
        doc = fitz.open(pdf_path)
        pages_content = []

        try:
            # Extract content from each page
            for page_num, page in enumerate(doc):
                # Extract text
                text = page.get_text()

                # Render page as image for vision analysis
                # Use 2x scale for better quality
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
                img_b64 = base64.b64encode(img_bytes).decode()

                pages_content.append({
                    'page': page_num + 1,
                    'text': text,
                    'image': img_b64
                })

                logger.debug(f"Extracted page {page_num + 1}/{len(doc)}")

        finally:
            doc.close()

        logger.info(f"Extracted {len(pages_content)} pages")

        # Use LLM to extract structured steps
        extracted = await self._extract_steps(pages_content)

        # Build ParsedSOP
        sop = ParsedSOP(
            title=extracted.get('title', 'Imported SOP'),
            description=extracted.get('description', ''),
            steps=extracted.get('steps', []),
            estimated_duration=extracted.get('duration', 60),
            source_pages=len(pages_content),
            variables=extracted.get('variables', [])
        )

        logger.info(f"Parsed SOP: {sop.title} with {len(sop.steps)} steps")
        return sop

    async def _extract_steps(self, pages: List[Dict]) -> Dict[str, Any]:
        """
        Extract structured steps using LLM vision analysis.

        Args:
            pages: List of page dictionaries with text and image

        Returns:
            Dictionary with title, description, steps, duration, variables
        """
        # Combine all page texts
        full_text = '\n\n'.join([p['text'] for p in pages])

        # Truncate if too long (keep first 10000 chars)
        if len(full_text) > 10000:
            full_text = full_text[:10000] + "\n\n[... truncated ...]"

        # Build prompt for LLM
        prompt = f"""Analyze this SOP (Standard Operating Procedure) document and extract structured workflow steps.

Document text:
{full_text}

Extract the following information:
1. Title of the procedure (clear, concise name)
2. Brief description (1-2 sentences)
3. Estimated duration in minutes
4. Numbered steps with:
   - Action: What to do (e.g., "Click the Submit button")
   - Target: Where to do it (URL, button name, field name, element identifier)
   - Expected result: What should happen after this step
   - Notes: Any additional information or warnings

5. Variables: Any inputs that need to be provided (names, emails, dates, etc.)

Output ONLY valid JSON in this exact format:
{{
    "title": "Procedure Name",
    "description": "Brief description of the procedure",
    "duration": 30,
    "variables": ["customer_name", "customer_email", "product_id"],
    "steps": [
        {{
            "number": 1,
            "action": "Navigate to the customer portal",
            "target": "https://portal.example.com",
            "expected_result": "Login page appears",
            "notes": "Ensure VPN is connected"
        }},
        {{
            "number": 2,
            "action": "Enter username and password",
            "target": "Login form",
            "expected_result": "Dashboard loads successfully",
            "notes": null
        }}
    ]
}}

IMPORTANT:
- Output ONLY the JSON, no other text
- Use null for optional fields that are missing
- Be specific about targets (exact button names, URLs, field labels)
- Break down complex actions into multiple steps
- Detect variables like {{customer_name}}, {{email}}, etc. in the text
"""

        # Call LLM
        response = await self.llm.generate(
            prompt=prompt,
            temperature=0.1,  # Low temperature for consistency
            max_tokens=4096
        )

        if response.error:
            logger.error(f"LLM error during SOP extraction: {response.error}")
            return {'title': 'Imported SOP', 'steps': []}

        # Parse JSON from response
        try:
            # Extract JSON from response (handle cases where LLM adds explanation)
            json_start = response.content.find('{')
            json_end = response.content.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response.content[json_start:json_end]
                data = json.loads(json_str)

                # Convert steps dict to SOPStep objects
                steps = []
                for step_data in data.get('steps', []):
                    steps.append(SOPStep(
                        number=step_data.get('number', len(steps) + 1),
                        action=step_data.get('action', ''),
                        target=step_data.get('target'),
                        expected_result=step_data.get('expected_result'),
                        notes=step_data.get('notes')
                    ))

                data['steps'] = steps
                return data
            else:
                logger.warning("No JSON found in LLM response")
                return {'title': 'Imported SOP', 'steps': []}

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response content: {response.content[:500]}")
            return {'title': 'Imported SOP', 'steps': []}

    async def sop_to_workflow(self, sop: ParsedSOP) -> Workflow:
        """
        Convert parsed SOP to executable workflow.

        Args:
            sop: ParsedSOP from parse_pdf()

        Returns:
            Workflow ready for execution
        """
        logger.info(f"Converting SOP to workflow: {sop.title}")

        steps = []
        variables = []
        detected_vars = set()

        for sop_step in sop.steps:
            # Determine action type from action text
            action_type = self._detect_action_type(sop_step.action)

            # Extract target selector/value
            target = sop_step.target or ''
            value_template = None

            # Detect variables in action text
            step_vars = self._detect_variables_in_text(sop_step.action)
            for var_name, var_type in step_vars:
                if var_name not in detected_vars:
                    detected_vars.add(var_name)
                    variables.append(WorkflowVariable(
                        name=var_name,
                        type=var_type,
                        default_value=None,
                        detected_from=f"step_{sop_step.number}",
                        description=f"From: {sop_step.action}"
                    ))

            # If action type is fill, check if we need a value template
            if action_type == 'fill':
                # Look for variable references in action
                var_match = re.search(r'\{\{(\w+)\}\}', sop_step.action)
                if var_match:
                    value_template = f"{{{{{var_match.group(1)}}}}}"

            # Build success indicators
            success_indicators = []
            if sop_step.expected_result:
                success_indicators.append(sop_step.expected_result)

            # Create workflow step
            workflow_step = WorkflowStep(
                name=f"step_{sop_step.number}",
                capability="playwright",  # Default to playwright capability
                action=action_type,
                params={
                    'target': target,
                    'value': value_template,
                    'expected_result': sop_step.expected_result,
                    'notes': sop_step.notes
                }
            )

            steps.append(workflow_step)

        # Create workflow ID from title
        workflow_id = f"sop_{hash(sop.title) & 0xFFFFFFFF:08x}"

        workflow = Workflow(
            id=workflow_id,
            name=sop.title,
            description=sop.description,
            variables=variables,
            steps=steps,
            source_recording_id=None,
            estimated_duration=sop.estimated_duration * 60  # Convert minutes to seconds
        )

        logger.info(f"Created workflow: {workflow.id} with {len(steps)} steps and {len(variables)} variables")
        return workflow

    def _detect_action_type(self, action_text: str) -> str:
        """
        Detect action type from action text using keyword matching.

        Args:
            action_text: Action description text

        Returns:
            Action type string (navigate, click, fill, wait, extract, verify)
        """
        action_lower = action_text.lower()

        # Check each action type's keywords
        for action_type, keywords in self.ACTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in action_lower:
                    return action_type

        # Default to click if no match
        return 'click'

    def _detect_variables_in_text(self, text: str) -> List[tuple[str, str]]:
        """
        Detect variable references in text.

        Looks for patterns like {{variable_name}} and common variable types
        like email, name, date references.

        Args:
            text: Text to analyze

        Returns:
            List of (variable_name, variable_type) tuples
        """
        variables = []

        # Find {{variable}} patterns
        var_pattern = r'\{\{(\w+)\}\}'
        matches = re.finditer(var_pattern, text)

        for match in matches:
            var_name = match.group(1)
            # Infer type from name
            var_type = self._infer_variable_type(var_name)
            variables.append((var_name, var_type))

        # Also look for common variable references without {{ }}
        text_lower = text.lower()

        if 'email' in text_lower and 'enter' in text_lower:
            variables.append(('user_email', 'email'))

        if 'name' in text_lower and ('enter' in text_lower or 'type' in text_lower):
            if 'first' in text_lower:
                variables.append(('first_name', 'text'))
            elif 'last' in text_lower:
                variables.append(('last_name', 'text'))
            else:
                variables.append(('full_name', 'text'))

        if 'phone' in text_lower and 'enter' in text_lower:
            variables.append(('phone_number', 'phone'))

        if 'date' in text_lower and 'select' in text_lower:
            variables.append(('date', 'date'))

        return variables

    def _infer_variable_type(self, var_name: str) -> str:
        """
        Infer variable type from variable name.

        Args:
            var_name: Variable name

        Returns:
            Variable type (text, email, phone, date, url, number)
        """
        name_lower = var_name.lower()

        if 'email' in name_lower:
            return 'email'
        elif 'phone' in name_lower or 'tel' in name_lower:
            return 'phone'
        elif 'date' in name_lower or 'time' in name_lower:
            return 'date'
        elif 'url' in name_lower or 'link' in name_lower or 'website' in name_lower:
            return 'url'
        elif 'count' in name_lower or 'number' in name_lower or 'amount' in name_lower or 'quantity' in name_lower:
            return 'number'
        else:
            return 'text'

    async def export_workflow_json(self, workflow: Workflow, output_path: str) -> None:
        """
        Export workflow to JSON file.

        Args:
            workflow: Workflow to export
            output_path: Path to output JSON file
        """
        from dataclasses import asdict

        # Convert to dict
        workflow_dict = {
            'id': workflow.id,
            'name': workflow.name,
            'description': workflow.description,
            'estimated_duration': workflow.estimated_duration,
            'variables': [
                {
                    'name': v.name,
                    'type': v.type,
                    'default_value': v.default_value,
                    'detected_from': v.detected_from,
                    'description': v.description
                }
                for v in workflow.variables
            ],
            'steps': [
                {
                    'name': s.name,
                    'capability': s.capability,
                    'action': s.action,
                    'params': s.params
                }
                for s in workflow.steps
            ]
        }

        # Write to file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(workflow_dict, f, indent=2)

        logger.info(f"Exported workflow to {output_path}")


# Convenience function for quick parsing
async def parse_sop_pdf(pdf_path: str) -> tuple[ParsedSOP, Workflow]:
    """
    Parse PDF SOP and convert to workflow in one step.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Tuple of (ParsedSOP, Workflow)
    """
    parser = SOPParser()
    sop = await parser.parse_pdf(pdf_path)
    workflow = await parser.sop_to_workflow(sop)
    return sop, workflow
