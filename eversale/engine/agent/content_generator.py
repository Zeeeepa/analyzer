"""
Content Generator - Domain-specific content generation for business automation
Covers: E-commerce, Real Estate, Logistics, Industrial, Marketing, Education, Government
"""

import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)

# Import hallucination guard for input validation
try:
    from .hallucination_guard import get_guard, ValidationResult
    HALLUCINATION_GUARD_AVAILABLE = True
except ImportError:
    HALLUCINATION_GUARD_AVAILABLE = False

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ProductDescription:
    title: str
    short_description: str
    long_description: str
    bullet_points: List[str]
    specifications: Dict[str, str]
    faq: List[Dict[str, str]]
    seo_keywords: List[str]

@dataclass
class MLSListing:
    headline: str
    description: str
    property_highlights: List[str]
    room_details: Dict[str, str]
    inspection_summary: str
    concerns: List[str]
    price_justification: str

@dataclass
class ShippingUpdate:
    tracking_id: str
    carrier: str
    status: str
    origin: str
    destination: str
    expected_date: str
    actual_date: str = ""
    is_delayed: bool = False
    delay_reason: str = ""
    delay_days: int = 0
    next_steps: List[str] = field(default_factory=list)

@dataclass
class MaintenanceIssue:
    equipment_id: str
    issue_type: str
    frequency: int
    first_occurrence: str
    last_occurrence: str
    root_cause: str
    recommended_action: str
    priority: str

@dataclass
class AnalyticsInsight:
    metric: str
    value: float
    change: float
    change_direction: str
    explanation: str
    recommendation: str
    experiment_idea: str

@dataclass
class QuizQuestion:
    question: str
    options: List[str]
    correct_answer: str
    explanation: str
    difficulty: str

@dataclass
class FormField:
    field_name: str
    field_type: str
    value: str
    required: bool
    validation: str = ""

# ============================================================================
# CONTENT GENERATOR CLASS
# ============================================================================

class ContentGenerator:
    """Generate domain-specific content for business automation"""

    def __init__(self):
        """Initialize content generator with hallucination guard."""
        self._guard = get_guard() if HALLUCINATION_GUARD_AVAILABLE else None

    def _validate_input(self, data: Any, context: str = "input") -> Tuple[bool, List[str], Any]:
        """
        Validate input data for fake/placeholder patterns before generating content.

        Args:
            data: Input data to validate (dict, list, or string)
            context: Description of what this data is for (for logging)

        Returns:
            Tuple of (is_valid, issues, cleaned_data)
        """
        if not HALLUCINATION_GUARD_AVAILABLE or self._guard is None:
            return True, [], data

        result = self._guard.validate_output(data, source_tool='content_generator_input')

        if not result.is_valid:
            logger.warning(f"Content generator input validation failed for {context}: {result.issues}")

        return result.is_valid, result.issues, result.cleaned_data

    def _validate_specs_input(self, specs: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Validate product specs for fake data patterns.

        Returns cleaned specs and list of issues found.
        """
        issues = []

        if not HALLUCINATION_GUARD_AVAILABLE or self._guard is None:
            return specs, issues

        # Validate entire dict
        result = self._guard.validate_output(specs, source_tool='content_generator_input')
        if not result.is_valid:
            issues.extend(result.issues)
            logger.warning(f"Product specs contain suspicious data: {result.issues}")

        # Additional checks for specific fields
        suspicious_patterns = {
            'name': [r'^Sample Product$', r'^Test Product$', r'^Product Name$', r'^Lorem'],
            'brand': [r'^Acme', r'^Sample Brand$', r'^Test Brand$'],
            'price': [r'^\$0\.00$', r'^\$999\.99$', r'^TBD$'],
        }

        cleaned_specs = specs.copy()
        for field, patterns in suspicious_patterns.items():
            if field in specs:
                for pattern in patterns:
                    if re.search(pattern, str(specs[field]), re.IGNORECASE):
                        issues.append(f"Suspicious {field}: '{specs[field]}' matches placeholder pattern")
                        # Don't generate content with obviously fake data
                        break

        return cleaned_specs if result.cleaned_data is None else result.cleaned_data, issues

    # ========================================================================
    # E) E-COMMERCE - Product Descriptions
    # ========================================================================

    def generate_product_description(self, specs: Dict[str, Any], images_description: str = "") -> ProductDescription:
        """Generate complete product listing from specs and image descriptions"""

        # ANTI-HALLUCINATION: Validate input specs before generating content
        validated_specs, validation_issues = self._validate_specs_input(specs)
        if validation_issues:
            logger.warning(f"Input validation issues detected: {validation_issues}")
            # Continue with cleaned/original specs but log the warning

        # Extract key product info (use validated specs)
        name = validated_specs.get('name', validated_specs.get('title', 'Product'))
        brand = validated_specs.get('brand', '')
        category = validated_specs.get('category', '')
        price = validated_specs.get('price', '')
        features = validated_specs.get('features', [])
        dimensions = validated_specs.get('dimensions', {})
        materials = validated_specs.get('materials', validated_specs.get('material', ''))
        color = validated_specs.get('color', '')

        # Generate title
        title = self._generate_product_title(name, brand, category, color)

        # Generate short description (for previews)
        short_desc = self._generate_short_description(name, brand, features, images_description)

        # Generate long description
        long_desc = self._generate_long_description(name, brand, features, materials, images_description)

        # Generate bullet points
        bullets = self._generate_bullet_points(features, dimensions, materials, validated_specs)

        # Clean specifications
        clean_specs = self._format_specifications(validated_specs)

        # Generate FAQ
        faq = self._generate_product_faq(name, validated_specs, features)

        # Extract SEO keywords
        keywords = self._extract_seo_keywords(name, brand, category, features)

        return ProductDescription(
            title=title,
            short_description=short_desc,
            long_description=long_desc,
            bullet_points=bullets,
            specifications=clean_specs,
            faq=faq,
            seo_keywords=keywords
        )

    def _generate_product_title(self, name: str, brand: str, category: str, color: str) -> str:
        """Generate SEO-optimized product title"""
        parts = []
        if brand:
            parts.append(brand)
        parts.append(name)
        if color:
            parts.append(f"- {color}")
        if category:
            parts.append(f"| {category}")
        return " ".join(parts)

    def _generate_short_description(self, name: str, brand: str, features: List[str], images_desc: str) -> str:
        """Generate short product description (150-200 chars)"""
        key_features = features[:2] if features else []
        feature_text = " and ".join(key_features) if key_features else "premium quality"

        desc = f"Discover the {brand + ' ' if brand else ''}{name}. Features {feature_text}."

        if images_desc:
            # Add visual element from image
            visual = images_desc.split('.')[0][:50]
            desc += f" {visual}."

        return desc[:200]

    def _generate_long_description(self, name: str, brand: str, features: List[str],
                                   materials: str, images_desc: str) -> str:
        """Generate detailed product description"""
        paragraphs = []

        # Opening paragraph
        opening = f"Introducing the {brand + ' ' if brand else ''}{name} – designed to exceed your expectations."
        paragraphs.append(opening)

        # Features paragraph
        if features:
            features_text = f"This exceptional product features {', '.join(features[:3])}. "
            if len(features) > 3:
                features_text += f"Additionally, you'll enjoy {', '.join(features[3:6])}."
            paragraphs.append(features_text)

        # Materials/Quality paragraph
        if materials:
            materials_para = f"Crafted from {materials}, this {name} offers superior durability and quality you can trust."
            paragraphs.append(materials_para)

        # Visual description from images
        if images_desc:
            paragraphs.append(images_desc)

        # Closing
        closing = "Order now and experience the difference quality makes."
        paragraphs.append(closing)

        return "\n\n".join(paragraphs)

    def _generate_bullet_points(self, features: List[str], dimensions: Dict,
                                materials: str, specs: Dict) -> List[str]:
        """Generate product bullet points"""
        bullets = []

        # Feature bullets
        for feature in features[:5]:
            bullets.append(f"✓ {feature}")

        # Dimension bullets
        if dimensions:
            dim_str = " x ".join(f"{v}" for k, v in dimensions.items())
            bullets.append(f"✓ Dimensions: {dim_str}")

        # Material bullet
        if materials:
            bullets.append(f"✓ Made from premium {materials}")

        # Weight if available
        weight = specs.get('weight')
        if weight:
            bullets.append(f"✓ Weight: {weight}")

        # Warranty if available
        warranty = specs.get('warranty')
        if warranty:
            bullets.append(f"✓ {warranty} warranty included")

        return bullets[:8]  # Max 8 bullets

    def _format_specifications(self, specs: Dict) -> Dict[str, str]:
        """Format specifications for display"""
        clean = {}
        skip_keys = ['name', 'title', 'description', 'features', 'price', 'images']

        for key, value in specs.items():
            if key.lower() in skip_keys:
                continue
            if isinstance(value, (dict, list)):
                if isinstance(value, dict):
                    value = ", ".join(f"{k}: {v}" for k, v in value.items())
                else:
                    value = ", ".join(str(v) for v in value)

            # Format key
            clean_key = key.replace('_', ' ').title()
            clean[clean_key] = str(value)

        return clean

    def _generate_product_faq(self, name: str, specs: Dict, features: List[str]) -> List[Dict[str, str]]:
        """Generate product FAQ"""
        faq = []

        # Shipping FAQ
        faq.append({
            "question": f"How long does shipping take for the {name}?",
            "answer": "Standard shipping takes 3-5 business days. Express shipping (1-2 days) is available at checkout."
        })

        # Returns FAQ
        faq.append({
            "question": "What is your return policy?",
            "answer": "We offer a 30-day satisfaction guarantee. If you're not completely happy, return it for a full refund."
        })

        # Size/dimensions FAQ
        if specs.get('dimensions'):
            faq.append({
                "question": f"What are the exact dimensions of the {name}?",
                "answer": f"The dimensions are: {specs['dimensions']}. Please measure your space before ordering."
            })

        # Care instructions
        material = specs.get('materials', specs.get('material', ''))
        if material:
            faq.append({
                "question": f"How do I care for this {name}?",
                "answer": f"For best results with {material} products, follow the care instructions included with your purchase."
            })

        # Warranty FAQ
        warranty = specs.get('warranty')
        if warranty:
            faq.append({
                "question": "Is there a warranty?",
                "answer": f"Yes, this product comes with a {warranty} warranty against manufacturing defects."
            })

        return faq

    def _extract_seo_keywords(self, name: str, brand: str, category: str, features: List[str]) -> List[str]:
        """Extract SEO keywords"""
        keywords = []

        # Add main terms
        keywords.append(name.lower())
        if brand:
            keywords.append(brand.lower())
            keywords.append(f"{brand} {name}".lower())
        if category:
            keywords.append(category.lower())

        # Add feature-based keywords
        for feature in features[:5]:
            words = feature.lower().split()
            keywords.extend(w for w in words if len(w) > 3)

        # Add common modifiers
        modifiers = ['best', 'premium', 'quality', 'buy', 'sale']
        for mod in modifiers[:3]:
            keywords.append(f"{mod} {name}".lower())

        return list(dict.fromkeys(keywords))[:15]

    # ========================================================================
    # F) REAL ESTATE - Inspection Reports & MLS Listings
    # ========================================================================

    def process_inspection_report(self, report_content: str, property_info: Dict = None) -> MLSListing:
        """Process inspection report and create MLS listing"""

        # ANTI-HALLUCINATION: Validate property info input
        property_info = property_info or {}
        if property_info and HALLUCINATION_GUARD_AVAILABLE and self._guard:
            result = self._guard.validate_output(property_info, source_tool='content_generator_input')
            if not result.is_valid:
                logger.warning(f"Property info validation issues: {result.issues}")
            property_info = result.cleaned_data if result.cleaned_data else property_info

        # Parse inspection findings
        findings = self._parse_inspection_findings(report_content)

        # Categorize findings
        concerns, neutral, positives = self._categorize_findings(findings)

        # Generate property summary
        summary = self._generate_inspection_summary(findings, concerns, positives)

        # Extract room details
        rooms = self._extract_room_details(report_content)

        # Generate MLS description
        property_info = property_info or {}
        headline = self._generate_mls_headline(property_info, positives)
        description = self._generate_mls_description(property_info, positives, rooms)
        highlights = self._generate_property_highlights(property_info, positives)
        price_just = self._generate_price_justification(property_info, concerns, positives)

        return MLSListing(
            headline=headline,
            description=description,
            property_highlights=highlights,
            room_details=rooms,
            inspection_summary=summary,
            concerns=concerns,
            price_justification=price_just
        )

    def _parse_inspection_findings(self, content: str) -> List[Dict[str, str]]:
        """Parse inspection findings from report"""
        findings = []

        # Look for common inspection patterns
        patterns = [
            r'(?:Finding|Issue|Item|Note)[:\s]*(.+?)(?:\n|$)',
            r'(?:•|·|-|\*)\s*(.+?)(?:\n|$)',
            r'\d+\.\s*(.+?)(?:\n|$)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.M | re.I)
            for match in matches:
                if len(match) > 10:  # Minimum length
                    severity = self._assess_finding_severity(match)
                    findings.append({
                        "finding": match.strip(),
                        "severity": severity
                    })

        return findings

    def _assess_finding_severity(self, finding: str) -> str:
        """Assess severity of inspection finding"""
        finding_lower = finding.lower()

        critical_words = ['structural', 'foundation', 'safety', 'hazard', 'mold', 'asbestos',
                          'electrical hazard', 'gas leak', 'water damage', 'roof failure']
        major_words = ['repair needed', 'replace', 'damage', 'leak', 'crack', 'rot',
                       'outdated', 'not functioning', 'code violation']
        minor_words = ['minor', 'cosmetic', 'wear', 'maintenance', 'recommend', 'consider']

        if any(w in finding_lower for w in critical_words):
            return 'critical'
        elif any(w in finding_lower for w in major_words):
            return 'major'
        elif any(w in finding_lower for w in minor_words):
            return 'minor'
        else:
            return 'observation'

    def _categorize_findings(self, findings: List[Dict]) -> tuple:
        """Categorize findings into concerns, neutral, and positives"""
        concerns = []
        neutral = []
        positives = []

        for f in findings:
            finding_lower = f['finding'].lower()

            if f['severity'] in ('critical', 'major'):
                concerns.append(f['finding'])
            elif 'good condition' in finding_lower or 'no issues' in finding_lower or 'satisfactory' in finding_lower:
                positives.append(f['finding'])
            else:
                neutral.append(f['finding'])

        return concerns, neutral, positives

    def _generate_inspection_summary(self, findings: List[Dict], concerns: List[str], positives: List[str]) -> str:
        """Generate inspection summary"""
        total = len(findings)
        critical = len([f for f in findings if f['severity'] == 'critical'])
        major = len([f for f in findings if f['severity'] == 'major'])

        summary = f"Inspection Summary: {total} items reviewed.\n\n"

        if critical > 0:
            summary += f"⚠️ CRITICAL ISSUES ({critical}): Require immediate attention before closing.\n"

        if major > 0:
            summary += f"🔧 MAJOR ITEMS ({major}): Should be addressed or negotiated.\n"

        if positives:
            summary += f"\n✅ POSITIVE FINDINGS:\n"
            for p in positives[:5]:
                summary += f"  • {p}\n"

        if concerns:
            summary += f"\n❌ CONCERNS:\n"
            for c in concerns[:5]:
                summary += f"  • {c}\n"

        return summary

    def _extract_room_details(self, content: str) -> Dict[str, str]:
        """Extract room-by-room details"""
        rooms = {}

        room_patterns = [
            r'(?:Kitchen|Living Room|Bedroom|Bathroom|Basement|Attic|Garage|Dining)[:\s]*([^.]+\.)',
        ]

        common_rooms = ['Kitchen', 'Living Room', 'Master Bedroom', 'Bathroom', 'Basement', 'Garage']

        for room in common_rooms:
            pattern = rf'{room}[:\s]*([^\n]+)'
            match = re.search(pattern, content, re.I)
            if match:
                rooms[room] = match.group(1).strip()

        return rooms

    def _generate_mls_headline(self, property_info: Dict, positives: List[str]) -> str:
        """Generate MLS headline"""
        beds = property_info.get('bedrooms', '')
        baths = property_info.get('bathrooms', '')
        sqft = property_info.get('sqft', '')
        style = property_info.get('style', 'Home')
        location = property_info.get('neighborhood', property_info.get('location', ''))

        parts = []
        if beds and baths:
            parts.append(f"{beds}BR/{baths}BA")
        parts.append(style)
        if sqft:
            parts.append(f"| {sqft} SF")
        if location:
            parts.append(f"in {location}")

        headline = " ".join(parts)

        # Add a selling point
        if positives:
            selling_point = positives[0].split(',')[0][:30]
            headline += f" | {selling_point}"

        return headline

    def _generate_mls_description(self, property_info: Dict, positives: List[str], rooms: Dict) -> str:
        """Generate MLS listing description"""
        paragraphs = []

        # Opening
        style = property_info.get('style', 'home')
        location = property_info.get('neighborhood', 'this desirable location')
        opening = f"Welcome to this beautiful {style} in {location}!"
        paragraphs.append(opening)

        # Features from positives
        if positives:
            features = "This property features " + ", ".join(positives[:3]) + "."
            paragraphs.append(features)

        # Room highlights
        if rooms:
            room_desc = "Inside, you'll find "
            room_parts = [f"a {room.lower()} with {desc.lower()}" for room, desc in list(rooms.items())[:3]]
            room_desc += ", ".join(room_parts) + "."
            paragraphs.append(room_desc)

        # Closing
        closing = "Don't miss this opportunity – schedule your showing today!"
        paragraphs.append(closing)

        return "\n\n".join(paragraphs)

    def _generate_property_highlights(self, property_info: Dict, positives: List[str]) -> List[str]:
        """Generate property highlights for listing"""
        highlights = []

        # From property info
        if property_info.get('bedrooms'):
            highlights.append(f"{property_info['bedrooms']} Bedrooms")
        if property_info.get('bathrooms'):
            highlights.append(f"{property_info['bathrooms']} Bathrooms")
        if property_info.get('sqft'):
            highlights.append(f"{property_info['sqft']} Square Feet")
        if property_info.get('lot_size'):
            highlights.append(f"{property_info['lot_size']} Lot")
        if property_info.get('year_built'):
            highlights.append(f"Built in {property_info['year_built']}")
        if property_info.get('garage'):
            highlights.append(f"{property_info['garage']}-Car Garage")

        # From positives
        for positive in positives[:4]:
            if len(positive) < 50:
                highlights.append(positive)

        return highlights[:10]

    def _generate_price_justification(self, property_info: Dict, concerns: List[str], positives: List[str]) -> str:
        """Generate price justification based on inspection"""
        price = property_info.get('price', 'Asking price')

        if not concerns:
            return f"{price} is justified by the excellent condition of the property with no major issues identified."

        if len(concerns) <= 2:
            return f"{price} reflects the property's overall good condition. Minor repairs ({len(concerns)} items) may warrant negotiation of $2,000-5,000."

        if len(concerns) <= 5:
            return f"{price} may need adjustment. {len(concerns)} items requiring attention. Recommend requesting repair credits or price reduction of $5,000-15,000."

        return f"Significant issues identified ({len(concerns)} items). Strong recommendation to negotiate {price} or request substantial repair credits."

    # ========================================================================
    # H) LOGISTICS - Shipping Updates & Delays
    # ========================================================================

    def process_shipping_updates(self, content: str) -> Dict[str, Any]:
        """Process shipping updates and detect delays"""

        # ANTI-HALLUCINATION: Validate shipping content for fake tracking numbers
        if HALLUCINATION_GUARD_AVAILABLE and self._guard:
            result = self._guard.validate_output(content, source_tool='shipping_input')
            if not result.is_valid:
                logger.warning(f"Shipping content validation issues: {result.issues}")

        shipments = self._parse_shipments(content)

        # Detect delays
        delayed = []
        on_time = []

        for shipment in shipments:
            shipment = self._analyze_shipment_status(shipment)
            if shipment.is_delayed:
                delayed.append(shipment)
            else:
                on_time.append(shipment)

        # Generate summary
        summary = self._generate_shipping_summary(shipments, delayed)

        # Generate next steps
        next_steps = self._generate_shipping_next_steps(delayed)

        return {
            "total_shipments": len(shipments),
            "on_time": len(on_time),
            "delayed": len(delayed),
            "shipments": [asdict(s) for s in shipments],
            "summary": summary,
            "next_steps": next_steps
        }

    def _parse_shipments(self, content: str) -> List[ShippingUpdate]:
        """Parse shipment data from content"""
        shipments = []

        # Try JSON first
        try:
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    shipments.append(ShippingUpdate(
                        tracking_id=str(item.get('tracking_id', item.get('id', ''))),
                        carrier=item.get('carrier', ''),
                        status=item.get('status', ''),
                        origin=item.get('origin', ''),
                        destination=item.get('destination', ''),
                        expected_date=item.get('expected_date', item.get('eta', '')),
                        actual_date=item.get('actual_date', item.get('delivered_date', ''))
                    ))
                return shipments
        except json.JSONDecodeError:
            pass

        # Parse text format
        blocks = re.split(r'\n(?=Tracking|Order|Shipment)', content)
        for block in blocks:
            if not block.strip():
                continue

            tracking = re.search(r'(?:Tracking|ID)[:\s#]*(\w+)', block, re.I)
            carrier = re.search(r'(?:Carrier|Via)[:\s]*(\w+)', block, re.I)
            status = re.search(r'(?:Status)[:\s]*([^\n]+)', block, re.I)
            origin = re.search(r'(?:Origin|From)[:\s]*([^\n]+)', block, re.I)
            dest = re.search(r'(?:Destination|To)[:\s]*([^\n]+)', block, re.I)
            expected = re.search(r'(?:Expected|ETA|Due)[:\s]*([^\n]+)', block, re.I)
            actual = re.search(r'(?:Delivered|Actual)[:\s]*([^\n]+)', block, re.I)

            if tracking:
                shipments.append(ShippingUpdate(
                    tracking_id=tracking.group(1),
                    carrier=carrier.group(1) if carrier else '',
                    status=status.group(1).strip() if status else '',
                    origin=origin.group(1).strip() if origin else '',
                    destination=dest.group(1).strip() if dest else '',
                    expected_date=expected.group(1).strip() if expected else '',
                    actual_date=actual.group(1).strip() if actual else ''
                ))

        return shipments

    def _analyze_shipment_status(self, shipment: ShippingUpdate) -> ShippingUpdate:
        """Analyze shipment for delays"""
        status_lower = shipment.status.lower()

        # Check status for delay indicators
        delay_indicators = ['delayed', 'exception', 'hold', 'problem', 'issue', 'returned', 'undeliverable']
        if any(ind in status_lower for ind in delay_indicators):
            shipment.is_delayed = True
            shipment.delay_reason = shipment.status

        # Check if past expected date
        if shipment.expected_date and shipment.actual_date:
            try:
                expected = self._parse_date(shipment.expected_date)
                actual = self._parse_date(shipment.actual_date)
                if actual and expected and actual > expected:
                    shipment.is_delayed = True
                    shipment.delay_days = (actual - expected).days
                    shipment.delay_reason = f"Delivered {shipment.delay_days} days late"
            except Exception:
                pass

        # Generate next steps for delayed shipments
        if shipment.is_delayed:
            shipment.next_steps = self._get_shipment_next_steps(shipment)

        return shipment

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats"""
        formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y', '%b %d, %Y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    def _get_shipment_next_steps(self, shipment: ShippingUpdate) -> List[str]:
        """Generate next steps for delayed shipment"""
        steps = []

        if 'exception' in shipment.status.lower():
            steps.append(f"Contact {shipment.carrier or 'carrier'} with tracking #{shipment.tracking_id}")
            steps.append("Request exception details and resolution timeline")

        if 'hold' in shipment.status.lower():
            steps.append("Check for customs clearance requirements")
            steps.append("Verify shipping documentation is complete")

        if shipment.delay_days > 3:
            steps.append("Notify customer of delay and updated ETA")
            steps.append("Consider expedited reshipping if critical")

        if not steps:
            steps.append(f"Monitor tracking #{shipment.tracking_id} for updates")
            steps.append("Contact carrier if no update within 24 hours")

        return steps

    def _generate_shipping_summary(self, shipments: List[ShippingUpdate], delayed: List[ShippingUpdate]) -> str:
        """Generate shipping summary"""
        total = len(shipments)
        delayed_count = len(delayed)
        on_time_rate = ((total - delayed_count) / total * 100) if total > 0 else 0

        summary = f"""
SHIPPING STATUS SUMMARY
=======================
Total Shipments: {total}
On-Time: {total - delayed_count} ({on_time_rate:.1f}%)
Delayed: {delayed_count}
"""

        if delayed:
            summary += "\nDELAYED SHIPMENTS:\n"
            for d in delayed[:10]:
                summary += f"  • {d.tracking_id}: {d.delay_reason or 'Unknown cause'}\n"

        return summary.strip()

    def _generate_shipping_next_steps(self, delayed: List[ShippingUpdate]) -> List[str]:
        """Generate overall next steps for delayed shipments"""
        if not delayed:
            return ["No immediate action required - all shipments on track"]

        steps = []

        # Prioritize critical delays
        critical = [d for d in delayed if d.delay_days and d.delay_days > 5]
        if critical:
            steps.append(f"URGENT: {len(critical)} shipments delayed 5+ days - escalate immediately")

        # Group by carrier
        carriers = Counter(d.carrier for d in delayed if d.carrier)
        for carrier, count in carriers.most_common():
            if count > 1:
                steps.append(f"Contact {carrier} - {count} delayed shipments")

        # Customer notifications
        if len(delayed) > 0:
            steps.append(f"Send delay notifications to {len(delayed)} customers")

        return steps

    # ========================================================================
    # I) INDUSTRIAL - Maintenance Log Analysis
    # ========================================================================

    def analyze_maintenance_logs(self, content: str) -> Dict[str, Any]:
        """Analyze maintenance logs for patterns and root causes"""

        # ANTI-HALLUCINATION: Validate maintenance log content
        if HALLUCINATION_GUARD_AVAILABLE and self._guard:
            result = self._guard.validate_output(content, source_tool='maintenance_input')
            if not result.is_valid:
                logger.warning(f"Maintenance log validation issues: {result.issues}")

        # Parse log entries
        entries = self._parse_maintenance_entries(content)

        # Identify recurring issues
        issues = self._identify_recurring_issues(entries)

        # Analyze root causes
        root_causes = self._analyze_root_causes(issues)

        # Generate recommendations
        recommendations = self._generate_maintenance_recommendations(issues, root_causes)

        return {
            "total_entries": len(entries),
            "unique_issues": len(issues),
            "issues": [asdict(i) for i in issues],
            "root_causes": root_causes,
            "recommendations": recommendations,
            "summary": self._generate_maintenance_summary(entries, issues)
        }

    def _parse_maintenance_entries(self, content: str) -> List[Dict]:
        """Parse maintenance log entries"""
        entries = []

        # Try JSON
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

        # Parse text format
        patterns = [
            r'(\d{4}-\d{2}-\d{2})[:\s]+(?:Equipment|Asset)[:\s#]*(\w+)[:\s]+(.+)',
            r'Date[:\s]*(\S+)[,\s]+(?:ID|Equipment)[:\s]*(\w+)[,\s]+(?:Issue|Problem)[:\s]*(.+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.I | re.M)
            for match in matches:
                entries.append({
                    'date': match[0],
                    'equipment_id': match[1],
                    'issue': match[2].strip()
                })

        return entries

    def _identify_recurring_issues(self, entries: List[Dict]) -> List[MaintenanceIssue]:
        """Identify recurring maintenance issues"""
        # Group by equipment and issue type
        issue_groups = {}

        for entry in entries:
            eq_id = entry.get('equipment_id', 'unknown')
            issue_text = entry.get('issue', '').lower()

            # Normalize issue type
            issue_type = self._categorize_maintenance_issue(issue_text)

            key = (eq_id, issue_type)
            if key not in issue_groups:
                issue_groups[key] = {
                    'equipment_id': eq_id,
                    'issue_type': issue_type,
                    'occurrences': [],
                    'raw_issues': []
                }

            issue_groups[key]['occurrences'].append(entry.get('date', ''))
            issue_groups[key]['raw_issues'].append(entry.get('issue', ''))

        # Convert to MaintenanceIssue objects
        issues = []
        for key, group in issue_groups.items():
            if len(group['occurrences']) >= 2:  # Only recurring (2+)
                root_cause = self._guess_root_cause(group['issue_type'], group['raw_issues'])

                issues.append(MaintenanceIssue(
                    equipment_id=group['equipment_id'],
                    issue_type=group['issue_type'],
                    frequency=len(group['occurrences']),
                    first_occurrence=min(group['occurrences']) if group['occurrences'] else '',
                    last_occurrence=max(group['occurrences']) if group['occurrences'] else '',
                    root_cause=root_cause,
                    recommended_action=self._get_recommended_action(group['issue_type'], root_cause),
                    priority=self._calculate_priority(len(group['occurrences']), group['issue_type'])
                ))

        # Sort by frequency
        issues.sort(key=lambda x: x.frequency, reverse=True)
        return issues

    def _categorize_maintenance_issue(self, issue_text: str) -> str:
        """Categorize maintenance issue"""
        categories = {
            'overheating': ['overheat', 'hot', 'temperature', 'thermal'],
            'vibration': ['vibration', 'shaking', 'loose'],
            'leak': ['leak', 'drip', 'fluid', 'oil'],
            'electrical': ['electrical', 'power', 'circuit', 'fuse'],
            'mechanical_failure': ['broken', 'failed', 'malfunction', 'jammed'],
            'wear': ['wear', 'worn', 'degraded', 'friction'],
            'calibration': ['calibration', 'alignment', 'accuracy'],
            'contamination': ['contamination', 'dirty', 'debris', 'clogged'],
        }

        for category, keywords in categories.items():
            if any(k in issue_text for k in keywords):
                return category

        return 'other'

    def _guess_root_cause(self, issue_type: str, raw_issues: List[str]) -> str:
        """Guess root cause based on issue type and history"""
        causes = {
            'overheating': 'Insufficient cooling or ventilation. Check coolant levels, fan operation, and airflow blockages.',
            'vibration': 'Imbalanced components, loose mountings, or bearing wear. Inspect mounting bolts and alignment.',
            'leak': 'Seal degradation or gasket failure. Check seals, gaskets, and connection points.',
            'electrical': 'Wiring degradation, loose connections, or component aging. Inspect connections and wire insulation.',
            'mechanical_failure': 'Component fatigue or excessive stress. Review operating parameters and load conditions.',
            'wear': 'Normal wear exceeding maintenance intervals. Review and adjust preventive maintenance schedule.',
            'calibration': 'Drift from environmental factors or component aging. Implement regular calibration schedule.',
            'contamination': 'Inadequate filtration or environmental exposure. Review filtration systems and sealing.',
        }

        return causes.get(issue_type, 'Requires further investigation to determine root cause.')

    def _get_recommended_action(self, issue_type: str, root_cause: str) -> str:
        """Get recommended action for issue"""
        actions = {
            'overheating': 'Schedule cooling system inspection. Clean filters and verify fan operation.',
            'vibration': 'Perform vibration analysis. Tighten mountings and check bearing condition.',
            'leak': 'Replace seals/gaskets. Perform pressure test after repair.',
            'electrical': 'Thermographic inspection of electrical connections. Replace degraded wiring.',
            'mechanical_failure': 'Replace failed component. Investigate stress factors to prevent recurrence.',
            'wear': 'Replace worn parts. Adjust PM schedule to prevent future wear-related failures.',
            'calibration': 'Perform full calibration. Document baseline readings for future reference.',
            'contamination': 'Deep clean affected systems. Upgrade filtration if needed.',
        }

        return actions.get(issue_type, 'Schedule detailed inspection by qualified technician.')

    def _calculate_priority(self, frequency: int, issue_type: str) -> str:
        """Calculate issue priority"""
        critical_types = ['electrical', 'mechanical_failure', 'overheating']

        if issue_type in critical_types or frequency >= 5:
            return 'high'
        elif frequency >= 3:
            return 'medium'
        else:
            return 'low'

    def _analyze_root_causes(self, issues: List[MaintenanceIssue]) -> List[Dict[str, Any]]:
        """Analyze root causes across all issues"""
        root_causes = []

        # Group by root cause similarity
        cause_groups = Counter(issue.root_cause[:50] for issue in issues)

        for cause, count in cause_groups.most_common(5):
            affected_equipment = [i.equipment_id for i in issues if i.root_cause.startswith(cause[:50])]
            root_causes.append({
                'cause': cause,
                'affected_equipment': list(set(affected_equipment)),
                'occurrence_count': count
            })

        return root_causes

    def _generate_maintenance_recommendations(self, issues: List[MaintenanceIssue], root_causes: List[Dict]) -> List[str]:
        """Generate maintenance recommendations"""
        recommendations = []

        # High priority issues
        high_priority = [i for i in issues if i.priority == 'high']
        if high_priority:
            recommendations.append(f"URGENT: {len(high_priority)} high-priority issues require immediate attention")

        # Equipment with multiple issues
        equipment_counts = Counter(i.equipment_id for i in issues)
        for eq_id, count in equipment_counts.most_common(3):
            if count >= 3:
                recommendations.append(f"Equipment {eq_id} has {count} recurring issues - consider comprehensive overhaul")

        # PM schedule adjustments
        wear_issues = [i for i in issues if i.issue_type == 'wear']
        if wear_issues:
            recommendations.append(f"Adjust PM intervals - {len(wear_issues)} wear-related issues detected")

        # Training needs
        common_types = Counter(i.issue_type for i in issues).most_common(2)
        for issue_type, count in common_types:
            if count >= 3:
                recommendations.append(f"Consider operator training on {issue_type} prevention ({count} occurrences)")

        return recommendations

    def _generate_maintenance_summary(self, entries: List[Dict], issues: List[MaintenanceIssue]) -> str:
        """Generate maintenance summary"""
        return f"""
MAINTENANCE LOG ANALYSIS
========================
Total Log Entries: {len(entries)}
Recurring Issues Identified: {len(issues)}
High Priority Issues: {len([i for i in issues if i.priority == 'high'])}
Equipment Requiring Attention: {len(set(i.equipment_id for i in issues))}

Top Issue Types:
{self._format_issue_types(issues)}
"""

    def _format_issue_types(self, issues: List[MaintenanceIssue]) -> str:
        """Format issue types for summary"""
        counts = Counter(i.issue_type for i in issues)
        lines = []
        for issue_type, count in counts.most_common(5):
            lines.append(f"  • {issue_type.replace('_', ' ').title()}: {count} occurrences")
        return '\n'.join(lines)

    # ========================================================================
    # K) MARKETING - Analytics Insights
    # ========================================================================

    def analyze_marketing_data(self, content: str) -> Dict[str, Any]:
        """Analyze marketing analytics data and generate insights"""

        # ANTI-HALLUCINATION: Validate marketing data content
        if HALLUCINATION_GUARD_AVAILABLE and self._guard:
            result = self._guard.validate_output(content, source_tool='marketing_input')
            if not result.is_valid:
                logger.warning(f"Marketing data validation issues: {result.issues}")

        # Parse analytics data
        metrics = self._parse_analytics_data(content)

        # Generate insights for each metric
        insights = []
        for metric in metrics:
            insight = self._generate_metric_insight(metric)
            insights.append(insight)

        # Generate overall recommendations
        recommendations = self._generate_marketing_recommendations(insights)

        # Generate experiment ideas
        experiments = self._generate_experiment_ideas(insights)

        return {
            "insights": [asdict(i) for i in insights],
            "recommendations": recommendations,
            "experiments": experiments,
            "summary": self._generate_marketing_summary(insights)
        }

    def _parse_analytics_data(self, content: str) -> List[Dict]:
        """Parse analytics data from various formats"""
        metrics = []

        # Try JSON
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, dict):
                        metrics.append({
                            'metric': key,
                            'current': value.get('current', value.get('value', 0)),
                            'previous': value.get('previous', value.get('last_period', 0)),
                            'target': value.get('target', value.get('goal', 0))
                        })
                    elif isinstance(value, (int, float)):
                        metrics.append({'metric': key, 'current': value, 'previous': 0})
            return metrics
        except json.JSONDecodeError:
            pass

        # Parse text/CSV format
        lines = content.strip().split('\n')
        for line in lines:
            # Try common patterns
            match = re.match(r'([^:,]+)[:\s,]+(\d+\.?\d*)\s*(?:vs\.?\s*(\d+\.?\d*))?', line)
            if match:
                metrics.append({
                    'metric': match.group(1).strip(),
                    'current': float(match.group(2)),
                    'previous': float(match.group(3)) if match.group(3) else 0
                })

        return metrics

    def _generate_metric_insight(self, metric: Dict) -> AnalyticsInsight:
        """Generate insight for a single metric"""
        name = metric.get('metric', 'Unknown')
        current = metric.get('current', 0)
        previous = metric.get('previous', 0)

        # Calculate change
        if previous > 0:
            change = ((current - previous) / previous) * 100
        else:
            change = 0

        direction = 'up' if change > 0 else ('down' if change < 0 else 'flat')

        # Generate explanation
        explanation = self._explain_metric_change(name, change, direction)

        # Generate recommendation
        recommendation = self._recommend_for_metric(name, change, direction)

        # Generate experiment idea
        experiment = self._suggest_experiment(name, direction)

        return AnalyticsInsight(
            metric=name,
            value=current,
            change=abs(change),
            change_direction=direction,
            explanation=explanation,
            recommendation=recommendation,
            experiment_idea=experiment
        )

    def _explain_metric_change(self, metric: str, change: float, direction: str) -> str:
        """Explain why a metric might have changed"""
        metric_lower = metric.lower()

        if abs(change) < 5:
            return f"{metric} is relatively stable with minimal change."

        if 'traffic' in metric_lower or 'visit' in metric_lower:
            if direction == 'up':
                return "Traffic increase may be due to SEO improvements, paid campaigns, or seasonal trends."
            else:
                return "Traffic decline could indicate algorithm changes, seasonal patterns, or technical issues."

        if 'conversion' in metric_lower or 'rate' in metric_lower:
            if direction == 'up':
                return "Improved conversion may result from better UX, more relevant traffic, or pricing optimization."
            else:
                return "Conversion drop may indicate UX issues, audience mismatch, or competitive pressure."

        if 'revenue' in metric_lower or 'sales' in metric_lower:
            if direction == 'up':
                return "Revenue growth driven by increased volume, better conversion, or higher order values."
            else:
                return "Revenue decline requires analysis of traffic, conversion, and average order value."

        if 'bounce' in metric_lower:
            if direction == 'up':
                return "Higher bounce rate suggests content-audience mismatch or page experience issues."
            else:
                return "Lower bounce rate indicates improved relevance and user engagement."

        return f"{metric} has changed {abs(change):.1f}% - further analysis recommended."

    def _recommend_for_metric(self, metric: str, change: float, direction: str) -> str:
        """Generate recommendation for metric"""
        metric_lower = metric.lower()

        if 'traffic' in metric_lower and direction == 'down':
            return "Audit SEO rankings, check for technical issues, and review paid campaign performance."

        if 'conversion' in metric_lower and direction == 'down':
            return "Run user testing, check funnel drop-offs, and A/B test key conversion pages."

        if 'bounce' in metric_lower and direction == 'up':
            return "Improve page load speed, ensure content matches search intent, and test above-fold content."

        if 'email' in metric_lower and 'open' in metric_lower and direction == 'down':
            return "Test subject lines, review send times, and segment audience for better relevance."

        if direction == 'up' and change > 10:
            return f"Document what drove this improvement in {metric} and scale successful tactics."

        return "Monitor this metric and set up alerts for significant changes."

    def _suggest_experiment(self, metric: str, direction: str) -> str:
        """Suggest experiment based on metric"""
        metric_lower = metric.lower()

        experiments = {
            'traffic': "Test new content formats (video, interactive) vs traditional blog posts",
            'conversion': "A/B test checkout flow: single page vs multi-step",
            'bounce': "Test personalized landing pages based on traffic source",
            'email_open': "Test emoji vs no emoji in subject lines",
            'click': "Test button color and CTA copy variations",
            'revenue': "Test bundling vs individual product pricing",
            'engagement': "Test content length: short-form vs long-form",
        }

        for key, experiment in experiments.items():
            if key in metric_lower:
                return experiment

        return f"Design an A/B test targeting the primary driver of {metric}"

    def _generate_marketing_recommendations(self, insights: List[AnalyticsInsight]) -> List[str]:
        """Generate overall marketing recommendations"""
        recommendations = []

        # Find declining metrics
        declining = [i for i in insights if i.change_direction == 'down' and i.change > 5]
        if declining:
            top_declining = max(declining, key=lambda x: x.change)
            recommendations.append(f"PRIORITY: Address {top_declining.metric} decline ({top_declining.change:.1f}%)")

        # Find winning metrics
        improving = [i for i in insights if i.change_direction == 'up' and i.change > 10]
        if improving:
            top_improving = max(improving, key=lambda x: x.change)
            recommendations.append(f"SCALE: Double down on {top_improving.metric} success (+{top_improving.change:.1f}%)")

        # General recommendations
        if any('conversion' in i.metric.lower() for i in declining):
            recommendations.append("Run comprehensive conversion rate optimization audit")

        if any('traffic' in i.metric.lower() for i in declining):
            recommendations.append("Review and refresh content strategy and SEO approach")

        return recommendations

    def _generate_experiment_ideas(self, insights: List[AnalyticsInsight]) -> List[Dict[str, str]]:
        """Generate experiment ideas from insights"""
        experiments = []

        for insight in insights[:5]:
            if insight.experiment_idea:
                experiments.append({
                    'metric': insight.metric,
                    'hypothesis': f"By running this experiment, we can improve {insight.metric}",
                    'experiment': insight.experiment_idea,
                    'expected_impact': f"{5 + abs(insight.change) / 2:.0f}% improvement potential"
                })

        return experiments

    def _generate_marketing_summary(self, insights: List[AnalyticsInsight]) -> str:
        """Generate marketing analytics summary"""
        improving = len([i for i in insights if i.change_direction == 'up'])
        declining = len([i for i in insights if i.change_direction == 'down'])
        stable = len([i for i in insights if i.change_direction == 'flat'])

        return f"""
MARKETING ANALYTICS SUMMARY
===========================
Metrics Analyzed: {len(insights)}
Improving: {improving} | Declining: {declining} | Stable: {stable}

Key Insights:
{chr(10).join('• ' + i.explanation for i in insights[:5])}
"""

    # ========================================================================
    # M) EDUCATION - Quiz Generation
    # ========================================================================

    def generate_quiz_from_content(self, content: str, num_questions: int = 10) -> Dict[str, Any]:
        """Generate quiz, answer key, and study guide from educational content"""

        # ANTI-HALLUCINATION: Validate educational content
        if HALLUCINATION_GUARD_AVAILABLE and self._guard:
            result = self._guard.validate_output(content, source_tool='education_input')
            if not result.is_valid:
                logger.warning(f"Educational content validation issues: {result.issues}")

        # Extract key concepts
        concepts = self._extract_key_concepts(content)

        # Generate questions
        questions = self._generate_questions(content, concepts, num_questions)

        # Generate study guide
        study_guide = self._generate_study_guide(content, concepts)

        # Generate answer key
        answer_key = self._generate_answer_key(questions)

        return {
            "quiz": {
                "title": "Chapter Quiz",
                "questions": [asdict(q) for q in questions]
            },
            "answer_key": answer_key,
            "study_guide": study_guide,
            "key_concepts": concepts
        }

    def _extract_key_concepts(self, content: str) -> List[str]:
        """Extract key concepts from educational content"""
        concepts = []

        # Look for bold/emphasized text
        bold = re.findall(r'\*\*([^*]+)\*\*|\*([^*]+)\*', content)
        concepts.extend([b[0] or b[1] for b in bold])

        # Look for definitions (X is/are Y pattern)
        definitions = re.findall(r'([A-Z][a-z]+(?:\s+[a-z]+)?)\s+(?:is|are|refers to)\s+', content)
        concepts.extend(definitions)

        # Look for headers
        headers = re.findall(r'(?:^|\n)#+\s*(.+)|(?:^|\n)([A-Z][A-Z\s]+)(?:\n|:)', content)
        concepts.extend([h[0] or h[1] for h in headers if h[0] or h[1]])

        # Look for capitalized terms that appear multiple times
        cap_words = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', content)
        word_counts = Counter(cap_words)
        frequent_terms = [w for w, c in word_counts.items() if c >= 3 and len(w) > 3]
        concepts.extend(frequent_terms[:10])

        # Deduplicate and clean
        concepts = [c.strip() for c in concepts if c and len(c) > 2]
        return list(dict.fromkeys(concepts))[:20]

    def _generate_questions(self, content: str, concepts: List[str], num_questions: int) -> List[QuizQuestion]:
        """Generate quiz questions from content"""
        questions = []
        sentences = re.split(r'[.!?]+', content)

        for i, concept in enumerate(concepts[:num_questions]):
            # Find sentence containing concept
            relevant_sentences = [s for s in sentences if concept.lower() in s.lower()]

            if relevant_sentences:
                sentence = relevant_sentences[0].strip()
                question = self._create_question_from_sentence(sentence, concept)
                if question:
                    questions.append(question)

        # Fill remaining with general questions if needed
        while len(questions) < num_questions and sentences:
            sentence = sentences.pop(0).strip()
            if len(sentence) > 30:
                question = self._create_fill_blank_question(sentence)
                if question:
                    questions.append(question)

        return questions[:num_questions]

    def _create_question_from_sentence(self, sentence: str, concept: str) -> Optional[QuizQuestion]:
        """Create a question from a sentence containing a concept"""
        # Multiple choice question about the concept
        question_text = f"What is true about {concept}?"

        # Create distractors
        options = [
            sentence[:100],  # Correct
            f"{concept} is unrelated to the topic discussed.",  # Wrong
            f"{concept} was not mentioned in the material.",  # Wrong
            f"The text contradicts the importance of {concept}."  # Wrong
        ]

        return QuizQuestion(
            question=question_text,
            options=options,
            correct_answer=options[0],
            explanation=f"According to the text: {sentence[:150]}",
            difficulty="medium"
        )

    def _create_fill_blank_question(self, sentence: str) -> Optional[QuizQuestion]:
        """Create fill-in-the-blank style question"""
        words = sentence.split()
        if len(words) < 5:
            return None

        # Find a significant word to blank out
        for i, word in enumerate(words):
            if len(word) > 4 and word[0].isupper():
                blank_word = word.rstrip('.,;:')
                blanked = words[:i] + ['_____'] + words[i + 1:]
                question_text = ' '.join(blanked) + "?"

                options = [
                    blank_word,
                    "None of the above",
                    "All of the above",
                    "This was not discussed"
                ]

                return QuizQuestion(
                    question=f"Fill in the blank: {question_text}",
                    options=options,
                    correct_answer=blank_word,
                    explanation=f"The complete statement is: {sentence}",
                    difficulty="easy"
                )

        return None

    def _generate_study_guide(self, content: str, concepts: List[str]) -> str:
        """Generate study guide from content"""
        guide = "STUDY GUIDE\n===========\n\n"

        guide += "KEY CONCEPTS TO KNOW:\n"
        for i, concept in enumerate(concepts[:15], 1):
            guide += f"{i}. {concept}\n"

        guide += "\nIMPORTANT POINTS:\n"
        sentences = re.split(r'[.!?]+', content)
        important = [s.strip() for s in sentences if any(c.lower() in s.lower() for c in concepts[:5])]
        for point in important[:10]:
            if point:
                guide += f"• {point}\n"

        guide += "\nSTUDY TIPS:\n"
        guide += "• Review each key concept and be able to define it in your own words\n"
        guide += "• Create flashcards for terms you find difficult\n"
        guide += "• Try to explain the material to someone else\n"
        guide += "• Complete the practice quiz and review any questions you missed\n"

        return guide

    def _generate_answer_key(self, questions: List[QuizQuestion]) -> List[Dict[str, str]]:
        """Generate answer key for quiz"""
        answer_key = []
        for i, q in enumerate(questions, 1):
            answer_key.append({
                "question_number": i,
                "question": q.question[:50] + "...",
                "correct_answer": q.correct_answer,
                "explanation": q.explanation
            })
        return answer_key

    # ========================================================================
    # N) GOVERNMENT - Form Field Extraction
    # ========================================================================

    def extract_form_fields(self, content: str, form_type: str = "") -> Dict[str, Any]:
        """Extract fields from government form and structure as JSON"""

        # ANTI-HALLUCINATION: Validate form content for fake data
        if HALLUCINATION_GUARD_AVAILABLE and self._guard:
            result = self._guard.validate_output(content, source_tool='form_input')
            if not result.is_valid:
                logger.warning(f"Form content validation issues: {result.issues}")
                # For government forms, we may want to be stricter
                # Return early with validation errors for critical fake data
                if any('ssn' in issue.lower() or 'credit_card' in issue.lower() for issue in result.issues):
                    return {
                        "success": False,
                        "error": "Form contains suspicious placeholder data",
                        "validation_issues": result.issues
                    }

        # Parse form fields
        fields = self._parse_form_fields(content)

        # Validate required fields
        validation = self._validate_form_fields(fields, form_type)

        # Structure as JSON
        structured = self._structure_form_data(fields, form_type)

        return {
            "success": True,
            "form_type": form_type or "Unknown",
            "fields_extracted": len(fields),
            "fields": [asdict(f) for f in fields],
            "structured_data": structured,
            "validation": validation
        }

    def _parse_form_fields(self, content: str) -> List[FormField]:
        """Parse form fields from content"""
        fields = []

        # Pattern for label: value pairs
        patterns = [
            r'([A-Za-z][A-Za-z\s]+):\s*([^\n]+)',  # Label: Value
            r'([A-Za-z][A-Za-z\s]+)\s*\[([^\]]*)\]',  # Label [Value]
            r'([A-Za-z][A-Za-z\s]+)\s*=\s*([^\n]+)',  # Label = Value
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                label = match[0].strip()
                value = match[1].strip()

                if len(label) > 2 and len(label) < 50:
                    field_type = self._infer_field_type(label, value)
                    required = self._is_required_field(label)

                    fields.append(FormField(
                        field_name=self._normalize_field_name(label),
                        field_type=field_type,
                        value=value,
                        required=required
                    ))

        return fields

    def _infer_field_type(self, label: str, value: str) -> str:
        """Infer field type from label and value"""
        label_lower = label.lower()

        if 'date' in label_lower or 'dob' in label_lower:
            return 'date'
        if 'email' in label_lower:
            return 'email'
        if 'phone' in label_lower or 'tel' in label_lower:
            return 'phone'
        if 'ssn' in label_lower or 'social security' in label_lower:
            return 'ssn'
        if 'zip' in label_lower or 'postal' in label_lower:
            return 'zip'
        if 'address' in label_lower:
            return 'address'
        if 'amount' in label_lower or '$' in value:
            return 'currency'
        if re.match(r'^\d+$', value):
            return 'number'
        if value.lower() in ['yes', 'no', 'true', 'false']:
            return 'boolean'

        return 'text'

    def _is_required_field(self, label: str) -> bool:
        """Check if field is likely required"""
        required_indicators = ['*', 'required', 'must', 'mandatory']
        label_lower = label.lower()

        if any(ind in label_lower for ind in required_indicators):
            return True

        # Common required fields
        common_required = ['name', 'ssn', 'date of birth', 'address', 'signature']
        return any(req in label_lower for req in common_required)

    def _normalize_field_name(self, label: str) -> str:
        """Normalize field name for JSON"""
        # Remove special characters
        name = re.sub(r'[^\w\s]', '', label)
        # Convert to snake_case
        name = re.sub(r'\s+', '_', name.strip().lower())
        return name

    def _validate_form_fields(self, fields: List[FormField], form_type: str) -> Dict[str, Any]:
        """Validate form fields"""
        validation = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }

        for field in fields:
            # Check required fields have values
            if field.required and not field.value:
                validation["is_valid"] = False
                validation["errors"].append(f"Required field '{field.field_name}' is empty")

            # Validate specific types
            if field.field_type == 'email' and field.value:
                if not re.match(r'^[\w.-]+@[\w.-]+\.\w+$', field.value):
                    validation["warnings"].append(f"Invalid email format: {field.value}")

            if field.field_type == 'ssn' and field.value:
                if not re.match(r'^\d{3}-?\d{2}-?\d{4}$', field.value):
                    validation["warnings"].append(f"Invalid SSN format: {field.value}")

            if field.field_type == 'phone' and field.value:
                digits = re.sub(r'\D', '', field.value)
                if len(digits) not in [10, 11]:
                    validation["warnings"].append(f"Invalid phone format: {field.value}")

        return validation

    def _structure_form_data(self, fields: List[FormField], form_type: str) -> Dict[str, Any]:
        """Structure form data as JSON"""
        structured = {
            "form_type": form_type,
            "extracted_date": datetime.now().isoformat(),
            "data": {}
        }

        # Group related fields
        personal = {}
        address = {}
        financial = {}
        other = {}

        for field in fields:
            name = field.field_name
            value = field.value

            # Categorize
            if any(x in name for x in ['name', 'ssn', 'dob', 'birth', 'gender', 'email', 'phone']):
                personal[name] = value
            elif any(x in name for x in ['address', 'city', 'state', 'zip', 'street']):
                address[name] = value
            elif any(x in name for x in ['amount', 'income', 'tax', 'payment', 'deduction']):
                financial[name] = value
            else:
                other[name] = value

        if personal:
            structured["data"]["personal_information"] = personal
        if address:
            structured["data"]["address_information"] = address
        if financial:
            structured["data"]["financial_information"] = financial
        if other:
            structured["data"]["other_information"] = other

        return structured

    # ========================================================================
    # TOOL INTERFACE
    # ========================================================================

    def get_tools(self) -> Dict[str, Dict]:
        """Return tool definitions"""
        return {
            # E) E-commerce
            "generate_product_listing": {
                "description": "Generate product description, bullets, FAQ from specs and image descriptions",
                "parameters": {
                    "specs": {"type": "object", "description": "Product specifications"},
                    "images_description": {"type": "string", "description": "Description of product images"}
                }
            },
            # F) Real Estate
            "process_inspection_report": {
                "description": "Process inspection report and generate MLS listing",
                "parameters": {
                    "content": {"type": "string", "description": "Inspection report content"},
                    "property_info": {"type": "object", "description": "Property details (beds, baths, sqft, etc.)"}
                }
            },
            # H) Logistics
            "process_shipping_updates": {
                "description": "Process shipping updates, detect delays, generate summary with next steps",
                "parameters": {"content": {"type": "string", "description": "Shipping update data"}}
            },
            # I) Industrial
            "analyze_maintenance_logs": {
                "description": "Analyze maintenance logs, identify recurring issues and root causes",
                "parameters": {"content": {"type": "string", "description": "Maintenance log data"}}
            },
            # K) Marketing
            "analyze_marketing_data": {
                "description": "Analyze marketing analytics, generate insights and experiment ideas",
                "parameters": {"content": {"type": "string", "description": "Analytics data"}}
            },
            # M) Education
            "generate_quiz": {
                "description": "Generate quiz, answer key, and study guide from educational content",
                "parameters": {
                    "content": {"type": "string", "description": "Educational content"},
                    "num_questions": {"type": "integer", "description": "Number of questions"}
                }
            },
            # N) Government
            "extract_form_fields": {
                "description": "Extract fields from government form and structure as JSON",
                "parameters": {
                    "content": {"type": "string", "description": "Form content"},
                    "form_type": {"type": "string", "description": "Type of form (e.g., W-2, 1040)"}
                }
            }
        }

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a content generation tool"""

        if tool_name == "generate_product_listing":
            specs = params.get('specs', {})
            images_desc = params.get('images_description', '')
            result = self.generate_product_description(specs, images_desc)
            return {"success": True, **asdict(result)}

        elif tool_name == "process_inspection_report":
            content = params.get('content', '')
            property_info = params.get('property_info', {})
            result = self.process_inspection_report(content, property_info)
            return {"success": True, **asdict(result)}

        elif tool_name == "process_shipping_updates":
            content = params.get('content', '')
            return self.process_shipping_updates(content)

        elif tool_name == "analyze_maintenance_logs":
            content = params.get('content', '')
            return self.analyze_maintenance_logs(content)

        elif tool_name == "analyze_marketing_data":
            content = params.get('content', '')
            return self.analyze_marketing_data(content)

        elif tool_name == "generate_quiz":
            content = params.get('content', '')
            num_questions = params.get('num_questions', 10)
            return self.generate_quiz_from_content(content, num_questions)

        elif tool_name == "extract_form_fields":
            content = params.get('content', '')
            form_type = params.get('form_type', '')
            return self.extract_form_fields(content, form_type)

        else:
            return {"error": f"Unknown tool: {tool_name}"}
