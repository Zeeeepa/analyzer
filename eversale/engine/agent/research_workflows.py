"""
Research & Analysis Workflows - Extracted from workflows_extended.py

Contains research-focused workflow executors:
- R1_VendorResearcher: Research vendors, compare suppliers (Workflow R)
- R2_RFPAnalyzer: Analyze RFP documents, extract requirements
- T1_PermitResearcher: Research permit requirements (Workflow T)
- U1_CandidateSourcer: Source candidates from GitHub/LinkedIn (Workflow U)
- Y1_ResearchAssistant: Literature review, citations (Workflow Y)
- AD1_GrantFinder: Grant searching, donor research (Workflow AD)

Reduces workflows_extended.py by ~600 lines.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger

from .executors.base import BaseExecutor, ActionResult, ActionStatus


# ============ R) PROCUREMENT RESEARCH ============

class R1_VendorResearcher(BaseExecutor):
    """Research and compare vendors for procurement."""

    capability = "R1"
    action = "research_vendors"
    required_params = ["product_category"]
    optional_params = ["vendors", "requirements"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        category = params.get("product_category", "")
        vendors = params.get("vendors", [])
        requirements = params.get("requirements", {})

        if not category and not vendors:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide product category or vendor list."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for vendor research"
            )

        try:
            # Find vendors if not provided
            if not vendors:
                vendors = await self._find_vendors(category)

            # Research each vendor
            vendor_profiles = []
            for vendor in vendors[:5]:
                profile = await self._research_vendor(vendor, category)
                if profile:
                    vendor_profiles.append(profile)

            # Score and rank vendors
            ranked = self._rank_vendors(vendor_profiles, requirements)

            # Generate comparison matrix
            comparison = self._create_comparison_matrix(ranked)

            saved_path = self._save_vendor_research(vendor_profiles, ranked, comparison)

            summary = self._generate_summary(ranked, comparison)

            return ActionResult(
                status=ActionStatus.SUCCESS if vendor_profiles else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "vendors": vendor_profiles,
                    "ranked": ranked,
                    "comparison": comparison,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Vendor research failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to research vendors: {e}"
            )

    async def _find_vendors(self, category: str) -> List[str]:
        """Find vendors for product category."""
        try:
            await self.browser.navigate(f"https://www.google.com/search?q=best+{category.replace(' ', '+')}+vendors+suppliers")
            await asyncio.sleep(2)

            vendors = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.g');

                    items.forEach(item => {
                        const title = item.querySelector('h3')?.textContent || '';
                        if (title) {
                            results.push(title);
                        }
                    });

                    return results.slice(0, 5);
                }
            """)

            return vendors
        except Exception as e:
            logger.error(f"Failed to search vendors: {e}")
            return []

    async def _research_vendor(self, vendor: str, category: str) -> Optional[Dict]:
        """Research a specific vendor."""
        try:
            await self.browser.navigate(f"https://www.google.com/search?q={vendor.replace(' ', '+')}+{category.replace(' ', '+')}")
            await asyncio.sleep(1)

            profile = {
                "name": vendor,
                "category": category,
                "website": None,
                "description": None,
                "reputation": "unknown"
            }

            # Extract basic info
            data = await self.browser.page.evaluate("""
                () => {
                    const info = {};

                    // Website
                    const link = document.querySelector('.g a[href*="http"]');
                    if (link) {
                        info.website = link.href;
                    }

                    // Description
                    const desc = document.querySelector('.g .VwiC3b');
                    if (desc) {
                        info.description = desc.textContent.trim();
                    }

                    return info;
                }
            """)

            profile.update(data)

            # Check reputation
            page_text = await self.browser.page.content()
            if "reliable" in page_text.lower() or "trusted" in page_text.lower():
                profile["reputation"] = "positive"
            elif "scam" in page_text.lower() or "complaint" in page_text.lower():
                profile["reputation"] = "negative"

            return profile
        except Exception as e:
            logger.warning(f"Failed to research vendor {vendor}: {e}")
            return None

    def _rank_vendors(self, vendors: List[Dict], requirements: Dict) -> List[Dict]:
        """Rank vendors by score."""
        scored = []

        for vendor in vendors:
            score = 0
            factors = []

            # Reputation
            if vendor.get("reputation") == "positive":
                score += 3
                factors.append("Good reputation")
            elif vendor.get("reputation") == "negative":
                score -= 2
                factors.append("Poor reputation")

            # Has website
            if vendor.get("website"):
                score += 1
                factors.append("Established online presence")

            # Has description
            if vendor.get("description"):
                score += 1

            vendor["score"] = score
            vendor["ranking_factors"] = factors
            scored.append(vendor)

        # Sort by score
        return sorted(scored, key=lambda v: v.get("score", 0), reverse=True)

    def _create_comparison_matrix(self, vendors: List[Dict]) -> Dict:
        """Create vendor comparison matrix."""
        return {
            "total_vendors": len(vendors),
            "top_recommendation": vendors[0]["name"] if vendors else None,
            "vendors_by_score": {v["name"]: v["score"] for v in vendors}
        }

    def _save_vendor_research(self, vendors: List, ranked: List, comparison: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"vendor_research_{timestamp}.json"
            return str(save_json(filename, {
                "vendors": vendors,
                "ranked": ranked,
                "comparison": comparison
            }))
        except Exception as e:
            logger.error(f"Failed to save vendor research report: {e}")
            return None

    def _generate_summary(self, ranked: List, comparison: Dict) -> str:
        lines = [
            "## Vendor Research Report",
            f"**Vendors Evaluated:** {comparison['total_vendors']}",
            ""
        ]

        if ranked:
            lines.append("### Top Vendors:")
            for i, vendor in enumerate(ranked[:3], 1):
                lines.append(f"{i}. **{vendor['name']}** (Score: {vendor['score']})")
                if vendor.get("website"):
                    lines.append(f"   - Website: {vendor['website']}")
                if vendor.get("ranking_factors"):
                    lines.append(f"   - {', '.join(vendor['ranking_factors'])}")
                lines.append("")

        if comparison.get("top_recommendation"):
            lines.append(f"**Recommended:** {comparison['top_recommendation']}")

        return "\n".join(lines)


class R2_RFPAnalyzer(BaseExecutor):
    """Analyze RFP (Request for Proposal) documents and extract requirements."""

    capability = "R2"
    action = "analyze_rfp"
    required_params = ["rfp_document"]
    optional_params = ["vendor_name", "auto_research"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        rfp_document = params.get("rfp_document", "")
        vendor_name = params.get("vendor_name", "")
        auto_research = params.get("auto_research", True)

        if not rfp_document:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide RFP document text or path."
            )

        try:
            # Extract key requirements from RFP
            requirements = self._extract_requirements(rfp_document)

            # Parse deadlines and milestones
            timeline = self._parse_timeline(rfp_document)

            # Extract budget/pricing requirements
            budget_info = self._extract_budget_info(rfp_document)

            # Identify evaluation criteria
            criteria = self._identify_criteria(rfp_document)

            # Research industry standards if browser available
            if auto_research and self.browser:
                requirements = await self._research_standards(requirements)

            # Generate compliance checklist
            checklist = self._generate_compliance_checklist(requirements, criteria)

            # Assess feasibility
            assessment = self._assess_feasibility(requirements, timeline, budget_info)

            # Generate response outline
            outline = self._generate_response_outline(requirements, criteria, timeline)

            saved_path = self._save_rfp_analysis(requirements, timeline, budget_info,
                                                 criteria, checklist, assessment, outline)

            summary = self._generate_rfp_summary(requirements, timeline, assessment)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "requirements": requirements,
                    "timeline": timeline,
                    "budget_info": budget_info,
                    "criteria": criteria,
                    "checklist": checklist,
                    "assessment": assessment,
                    "outline": outline,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"RFP analysis failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to analyze RFP: {e}"
            )

    def _extract_requirements(self, rfp: str) -> List[Dict]:
        """Extract technical and business requirements."""
        requirements = []
        sections = rfp.split('\n\n')

        for section in sections:
            if any(keyword in section.lower() for keyword in ['must', 'required', 'shall', 'requirement']):
                req = {
                    "text": section.strip(),
                    "type": "mandatory" if any(k in section.lower() for k in ['must', 'shall', 'required']) else "optional",
                    "category": self._categorize_requirement(section)
                }
                requirements.append(req)

        return requirements

    def _categorize_requirement(self, text: str) -> str:
        """Categorize requirement type."""
        text_lower = text.lower()

        if any(k in text_lower for k in ['technical', 'technology', 'software', 'system']):
            return "technical"
        elif any(k in text_lower for k in ['service', 'support', 'maintenance']):
            return "service"
        elif any(k in text_lower for k in ['price', 'cost', 'budget', 'payment']):
            return "financial"
        elif any(k in text_lower for k in ['timeline', 'schedule', 'deadline', 'delivery']):
            return "schedule"
        elif any(k in text_lower for k in ['experience', 'reference', 'qualification']):
            return "qualification"
        else:
            return "general"

    def _parse_timeline(self, rfp: str) -> Dict:
        """Parse deadlines and timeline from RFP."""
        timeline = {
            "submission_deadline": None,
            "project_start": None,
            "project_end": None,
            "milestones": []
        }

        date_pattern = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+ \d{1,2},? \d{4})'
        lines = rfp.split('\n')

        for line in lines:
            if 'deadline' in line.lower() or 'due' in line.lower():
                date_match = re.search(date_pattern, line)
                if date_match:
                    timeline["submission_deadline"] = date_match.group(1)

            if 'start' in line.lower() and 'date' in line.lower():
                date_match = re.search(date_pattern, line)
                if date_match:
                    timeline["project_start"] = date_match.group(1)

            if 'completion' in line.lower() or 'end date' in line.lower():
                date_match = re.search(date_pattern, line)
                if date_match:
                    timeline["project_end"] = date_match.group(1)

            if 'milestone' in line.lower():
                date_match = re.search(date_pattern, line)
                if date_match:
                    timeline["milestones"].append({
                        "description": line.strip(),
                        "date": date_match.group(1)
                    })

        return timeline

    def _extract_budget_info(self, rfp: str) -> Dict:
        """Extract budget and pricing requirements."""
        budget_info = {
            "budget_range": None,
            "pricing_model": None,
            "payment_terms": None
        }

        amount_pattern = r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|k|K))?'
        amounts = re.findall(amount_pattern, rfp)
        if amounts:
            budget_info["budget_range"] = amounts[0] if len(amounts) == 1 else f"{amounts[0]} - {amounts[-1]}"

        if 'fixed price' in rfp.lower():
            budget_info["pricing_model"] = "fixed_price"
        elif 'time and materials' in rfp.lower() or 't&m' in rfp.lower():
            budget_info["pricing_model"] = "time_and_materials"
        elif 'milestone' in rfp.lower():
            budget_info["pricing_model"] = "milestone_based"

        if 'net 30' in rfp.lower():
            budget_info["payment_terms"] = "Net 30"
        elif 'net 60' in rfp.lower():
            budget_info["payment_terms"] = "Net 60"

        return budget_info

    def _identify_criteria(self, rfp: str) -> List[Dict]:
        """Identify evaluation criteria."""
        criteria = []
        criteria_keywords = {
            "technical": ["technical capability", "technical approach", "solution"],
            "experience": ["experience", "past performance", "references"],
            "cost": ["price", "cost", "budget"],
            "timeline": ["schedule", "timeline", "delivery"],
            "quality": ["quality", "methodology", "process"]
        }

        for category, keywords in criteria_keywords.items():
            for keyword in keywords:
                if keyword in rfp.lower():
                    weight_match = re.search(f"{keyword}.*?(\\d+)%", rfp, re.IGNORECASE)
                    weight = int(weight_match.group(1)) if weight_match else None
                    criteria.append({
                        "category": category,
                        "description": keyword,
                        "weight": weight
                    })
                    break

        return criteria

    async def _research_standards(self, requirements: List[Dict]) -> List[Dict]:
        """Research industry standards for requirements."""
        for req in requirements:
            if req["category"] == "technical" and self.browser:
                try:
                    tech_terms = [word for word in req["text"].split()
                                 if len(word) > 5 and word[0].isupper()]
                    if tech_terms:
                        search_query = f"{tech_terms[0]} industry standard best practices"
                        await self.browser.navigate(f"https://www.google.com/search?q={search_query}")
                        await asyncio.sleep(2)
                        page_text = await self.browser.get_text("body")
                        req["industry_context"] = page_text[:200]
                except Exception as e:
                    logger.debug(f"Failed to extract industry context for requirement: {e}")
                    pass
        return requirements

    def _generate_compliance_checklist(self, requirements: List[Dict], criteria: List[Dict]) -> List[Dict]:
        """Generate compliance checklist."""
        checklist = []
        for req in requirements:
            if req["type"] == "mandatory":
                checklist.append({
                    "requirement": req["text"][:100],
                    "category": req["category"],
                    "status": "pending",
                    "notes": ""
                })
        return checklist

    def _assess_feasibility(self, requirements: List[Dict], timeline: Dict, budget_info: Dict) -> Dict:
        """Assess feasibility of the RFP."""
        mandatory_count = sum(1 for r in requirements if r["type"] == "mandatory")
        has_deadline = timeline.get("submission_deadline") is not None
        has_budget = budget_info.get("budget_range") is not None

        feasibility_score = 100
        concerns = []

        if mandatory_count > 10:
            feasibility_score -= 20
            concerns.append(f"High number of mandatory requirements ({mandatory_count})")

        if not has_deadline:
            feasibility_score -= 10
            concerns.append("No clear submission deadline")

        if not has_budget:
            feasibility_score -= 15
            concerns.append("Budget not specified")

        return {
            "score": feasibility_score,
            "rating": "high" if feasibility_score > 70 else "medium" if feasibility_score > 50 else "low",
            "concerns": concerns,
            "mandatory_requirements": mandatory_count
        }

    def _generate_response_outline(self, requirements: List[Dict], criteria: List[Dict], timeline: Dict) -> Dict:
        """Generate response outline."""
        return {
            "sections": [
                {"title": "Executive Summary", "content": "Overview of proposal"},
                {"title": "Technical Approach", "content": "Solution details"},
                {"title": "Experience & Qualifications", "content": "Past projects"},
                {"title": "Pricing", "content": "Cost breakdown"},
                {"title": "Timeline", "content": "Project schedule"},
                {"title": "Appendices", "content": "Supporting documents"}
            ],
            "estimated_pages": len(requirements) * 2 + 10
        }

    def _save_rfp_analysis(self, requirements, timeline, budget_info, criteria, checklist, assessment, outline) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"rfp_analysis_{timestamp}.json"
            return str(save_json(filename, {
                "requirements": requirements,
                "timeline": timeline,
                "budget_info": budget_info,
                "criteria": criteria,
                "checklist": checklist,
                "assessment": assessment,
                "outline": outline
            }))
        except Exception as e:
            logger.error(f"Failed to save RFP analysis: {e}")
            return None

    def _generate_rfp_summary(self, requirements: List, timeline: Dict, assessment: Dict) -> str:
        lines = [
            "## RFP Analysis Report",
            f"**Requirements Found:** {len(requirements)}",
            f"**Mandatory:** {assessment['mandatory_requirements']}",
            f"**Feasibility:** {assessment['rating'].title()} ({assessment['score']}%)",
            ""
        ]

        if timeline.get("submission_deadline"):
            lines.append(f"**Deadline:** {timeline['submission_deadline']}")

        if assessment.get("concerns"):
            lines.append("\n**Concerns:**")
            for concern in assessment["concerns"]:
                lines.append(f"- {concern}")

        return "\n".join(lines)


# ============ T) CONTRACTOR/PERMIT RESEARCH ============

class T1_PermitResearcher(BaseExecutor):
    """Research permit requirements for construction projects."""

    capability = "T1"
    action = "research_permits"
    required_params = ["project_type", "location"]
    optional_params = ["property_address", "scope"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        project_type = params.get("project_type", "")
        location = params.get("location", "")
        property_address = params.get("property_address", "")
        scope = params.get("scope", "")

        if not project_type or not location:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide project type and location."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for permit research"
            )

        try:
            # Research permit requirements
            requirements = await self._research_permit_requirements(project_type, location)

            # Find permit office
            permit_office = await self._find_permit_office(location)

            # Get application process
            process = await self._get_application_process(project_type, location)

            # Estimate timeline and costs
            estimates = self._estimate_timeline_costs(requirements, location)

            # Compile checklist
            checklist = self._create_permit_checklist(requirements, process)

            saved_path = self._save_permit_research(requirements, permit_office, process, estimates, checklist)

            summary = self._generate_summary(requirements, permit_office, estimates)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "requirements": requirements,
                    "permit_office": permit_office,
                    "process": process,
                    "estimates": estimates,
                    "checklist": checklist,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Permit research failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to research permits: {e}"
            )

    async def _research_permit_requirements(self, project_type: str, location: str) -> Dict:
        """Research permit requirements."""
        await self.browser.navigate(f"https://www.google.com/search?q={location.replace(' ', '+')}+{project_type.replace(' ', '+')}+permit+requirements")
        await asyncio.sleep(2)

        requirements = {
            "project_type": project_type,
            "location": location,
            "required_permits": [],
            "inspections": [],
            "restrictions": []
        }

        page_text = await self.browser.page.content()

        permit_types = ["building permit", "electrical permit", "plumbing permit", "mechanical permit", "zoning permit"]
        for permit in permit_types:
            if permit in page_text.lower():
                requirements["required_permits"].append(permit)

        inspection_types = ["rough inspection", "final inspection", "framing inspection", "electrical inspection"]
        for inspection in inspection_types:
            if inspection in page_text.lower():
                requirements["inspections"].append(inspection)

        return requirements

    async def _find_permit_office(self, location: str) -> Dict:
        """Find local permit office."""
        await self.browser.navigate(f"https://www.google.com/search?q={location.replace(' ', '+')}+building+permit+office+contact")
        await asyncio.sleep(1)

        office = {
            "location": location,
            "office_name": None,
            "address": None,
            "phone": None,
            "website": None
        }

        page_text = await self.browser.page.content()

        phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', page_text)
        if phone_match:
            office["phone"] = phone_match.group(0)

        url_match = re.search(r'https?://[^\s<>"]+gov[^\s<>"]*', page_text)
        if url_match:
            office["website"] = url_match.group(0)

        return office

    async def _get_application_process(self, project_type: str, location: str) -> List[Dict]:
        """Get permit application process steps."""
        await self.browser.navigate(f"https://www.google.com/search?q={location.replace(' ', '+')}+how+to+apply+for+{project_type.replace(' ', '+')}+permit")
        await asyncio.sleep(1)

        process = [
            {"step": 1, "action": "Gather project plans and documentation"},
            {"step": 2, "action": "Submit application to permit office"},
            {"step": 3, "action": "Pay permit fees"},
            {"step": 4, "action": "Schedule required inspections"},
            {"step": 5, "action": "Complete work and pass final inspection"}
        ]

        return process

    def _estimate_timeline_costs(self, requirements: Dict, location: str) -> Dict:
        """Estimate timeline and costs."""
        num_permits = len(requirements.get("required_permits", []))
        num_inspections = len(requirements.get("inspections", []))

        base_fee = 200
        per_permit_fee = 100
        per_inspection_fee = 50

        estimated_cost = base_fee + (num_permits * per_permit_fee) + (num_inspections * per_inspection_fee)
        estimated_days = 14 + (num_permits * 3) + (num_inspections * 2)

        return {
            "estimated_cost": f"${estimated_cost}",
            "estimated_timeline": f"{estimated_days} business days",
            "cost_breakdown": {
                "base_fee": f"${base_fee}",
                "permit_fees": f"${num_permits * per_permit_fee}",
                "inspection_fees": f"${num_inspections * per_inspection_fee}"
            }
        }

    def _create_permit_checklist(self, requirements: Dict, process: List[Dict]) -> List[Dict]:
        """Create permit application checklist."""
        checklist = []

        checklist.append({
            "item": "Prepare site plans and blueprints",
            "category": "documentation",
            "completed": False
        })

        for permit in requirements.get("required_permits", []):
            checklist.append({
                "item": f"Apply for {permit}",
                "category": "permits",
                "completed": False
            })

        for inspection in requirements.get("inspections", []):
            checklist.append({
                "item": f"Schedule {inspection}",
                "category": "inspections",
                "completed": False
            })

        return checklist

    def _save_permit_research(self, requirements: Dict, office: Dict, process: List, estimates: Dict, checklist: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"permit_research_{timestamp}.json"
            return str(save_json(filename, {
                "requirements": requirements,
                "permit_office": office,
                "process": process,
                "estimates": estimates,
                "checklist": checklist
            }))
        except Exception as e:
            logger.error(f"Failed to save permit research: {e}")
            return None

    def _generate_summary(self, requirements: Dict, office: Dict, estimates: Dict) -> str:
        lines = [
            "## Permit Research Report",
            f"**Project:** {requirements['project_type']}",
            f"**Location:** {requirements['location']}",
            "",
            f"**Required Permits:** {len(requirements['required_permits'])}",
        ]

        for permit in requirements["required_permits"]:
            lines.append(f"- {permit.title()}")

        lines.append("")
        lines.append(f"**Estimated Cost:** {estimates['estimated_cost']}")
        lines.append(f"**Estimated Timeline:** {estimates['estimated_timeline']}")

        if office.get("phone"):
            lines.append(f"\n**Permit Office:** {office['phone']}")

        return "\n".join(lines)


# ============ U) RECRUITING/HR RESEARCH ============

class U1_CandidateSourcer(BaseExecutor):
    """Source candidates from GitHub, LinkedIn, and other platforms."""

    capability = "U1"
    action = "source_candidates"
    required_params = ["role"]
    optional_params = ["skills", "location", "platform"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        role = params.get("role", "")
        skills = params.get("skills", [])
        location = params.get("location", "")
        platform = params.get("platform", "github")

        if not role:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide role to search for."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for candidate sourcing"
            )

        try:
            candidates = []

            if platform == "github":
                candidates = await self._source_from_github(role, skills, location)
            elif platform == "linkedin":
                candidates = await self._source_from_linkedin(role, skills, location)
            else:
                candidates.extend(await self._source_from_github(role, skills, location))

            enriched = await self._enrich_candidates(candidates[:10])
            scored = self._score_candidates(enriched, skills)
            outreach = self._generate_outreach_templates(role, scored[:5])

            saved_path = self._save_candidate_pipeline(scored, outreach)

            summary = self._generate_summary(scored, role)

            return ActionResult(
                status=ActionStatus.SUCCESS if candidates else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "candidates": scored,
                    "outreach_templates": outreach,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Candidate sourcing failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to source candidates: {e}"
            )

    async def _source_from_github(self, role: str, skills: List[str], location: str) -> List[Dict]:
        """Source candidates from GitHub."""
        candidates = []

        try:
            skill_query = "+".join(skills[:3]) if skills else role.replace(" ", "+")
            search_url = f"https://github.com/search?q={skill_query}+location:{location if location else 'world'}&type=users"

            await self.browser.navigate(search_url)
            await asyncio.sleep(2)

            users = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.user-list-item, .hx_hit-user');

                    items.forEach(item => {
                        const username = item.querySelector('.f4 a, .mr-1 a')?.textContent?.trim();
                        const name = item.querySelector('.mb-1')?.textContent?.trim();
                        const bio = item.querySelector('.text-gray')?.textContent?.trim();
                        const link = item.querySelector('a')?.href;

                        if (username) {
                            results.push({
                                username: username,
                                name: name || username,
                                bio: bio || '',
                                profile_url: link || `https://github.com/${username}`,
                                platform: 'github'
                            });
                        }
                    });

                    return results.slice(0, 10);
                }
            """)

            candidates.extend(users)

        except Exception as e:
            logger.warning(f"GitHub sourcing failed: {e}")

        return candidates

    async def _source_from_linkedin(self, role: str, skills: List[str], location: str) -> List[Dict]:
        """Source candidates from LinkedIn (requires login)."""
        candidates = []

        try:
            search_query = f"{role} {' '.join(skills[:2])}"
            if location:
                search_query += f" {location}"

            await self.browser.navigate(f"https://www.linkedin.com/search/results/people/?keywords={search_query.replace(' ', '%20')}")
            await asyncio.sleep(2)

            page_text = await self.browser.page.content()
            if "sign in" in page_text.lower() or "login" in page_text.lower():
                logger.warning("LinkedIn requires login - please login first")
                return []

            candidates.append({
                "name": "LinkedIn Profile",
                "platform": "linkedin",
                "note": "Login required to view full results"
            })

        except Exception as e:
            logger.warning(f"LinkedIn sourcing failed: {e}")

        return candidates

    async def _enrich_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Enrich candidate profiles with additional data."""
        for candidate in candidates:
            if candidate.get("profile_url"):
                try:
                    await self.browser.navigate(candidate["profile_url"])
                    await asyncio.sleep(1)

                    page_text = await self.browser.page.content()

                    repos_match = re.search(r'(\d+)\s+repositor', page_text, re.IGNORECASE)
                    if repos_match:
                        candidate["repositories"] = int(repos_match.group(1))

                    candidate["languages"] = []
                    common_langs = ["Python", "JavaScript", "Java", "TypeScript", "Go", "Rust", "C++"]
                    for lang in common_langs:
                        if lang in page_text:
                            candidate["languages"].append(lang)

                except Exception as e:
                    logger.debug(f"Failed to enrich candidate profile: {e}")
                    pass

        return candidates

    def _score_candidates(self, candidates: List[Dict], required_skills: List[str]) -> List[Dict]:
        """Score candidates based on skills and activity."""
        scored = []

        for candidate in candidates:
            score = 0
            factors = []

            candidate_langs = candidate.get("languages", [])
            matching_langs = sum(1 for lang in candidate_langs if any(skill.lower() in lang.lower() for skill in required_skills))
            score += matching_langs * 2
            if matching_langs > 0:
                factors.append(f"Matches {matching_langs} required skills")

            repos = candidate.get("repositories", 0)
            if repos > 50:
                score += 3
                factors.append("High activity (50+ repos)")
            elif repos > 20:
                score += 2
                factors.append("Active contributor")

            if candidate.get("bio"):
                score += 1

            candidate["score"] = score
            candidate["ranking_factors"] = factors
            scored.append(candidate)

        return sorted(scored, key=lambda c: c.get("score", 0), reverse=True)

    def _generate_outreach_templates(self, role: str, top_candidates: List[Dict]) -> List[Dict]:
        """Generate personalized outreach templates."""
        templates = []

        for candidate in top_candidates:
            name = candidate.get("name", "there")
            langs = ", ".join(candidate.get("languages", [])[:2]) or "your skills"

            template = {
                "candidate": name,
                "subject": f"Exciting {role} Opportunity",
                "body": f"""Hi {name},

I came across your profile and was impressed by your work in {langs}. We're looking for a talented {role} to join our team.

Would you be interested in learning more about this opportunity?

Best regards"""
            }
            templates.append(template)

        return templates

    def _save_candidate_pipeline(self, candidates: List, outreach: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"candidate_pipeline_{timestamp}.json"
            return str(save_json(filename, {
                "candidates": candidates,
                "outreach_templates": outreach
            }))
        except Exception as e:
            logger.error(f"Failed to save candidate pipeline: {e}")
            return None

    def _generate_summary(self, candidates: List, role: str) -> str:
        lines = [
            "## Candidate Sourcing Report",
            f"**Role:** {role}",
            f"**Candidates Found:** {len(candidates)}",
            ""
        ]

        if candidates:
            lines.append("### Top Candidates:")
            for i, candidate in enumerate(candidates[:5], 1):
                lines.append(f"{i}. **{candidate.get('name', 'Unknown')}** (Score: {candidate.get('score', 0)})")
                if candidate.get("languages"):
                    lines.append(f"   - Languages: {', '.join(candidate['languages'][:3])}")
                if candidate.get("profile_url"):
                    lines.append(f"   - Profile: {candidate['profile_url']}")
                lines.append("")

        return "\n".join(lines)


# ============ Y) RESEARCH AUTOMATION ============

class Y1_ResearchAssistant(BaseExecutor):
    """Review research papers, gather citations, verify sources."""

    capability = "Y1"
    action = "research_literature"
    required_params = ["topic"]
    optional_params = ["sources", "year_from"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        topic = params.get("topic", "")
        sources = params.get("sources", ["google scholar", "wikipedia"])
        year_from = params.get("year_from", 2020)

        if not topic:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide research topic."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for research"
            )

        try:
            papers = []

            for source in sources:
                results = await self._search_source(source, topic, year_from)
                papers.extend(results)

            citations = self._extract_citations(papers)
            bibliography = self._build_bibliography(citations)
            outline = self._create_review_outline(papers, topic)

            saved_path = self._save_research_report(papers, citations, bibliography, outline)

            summary = self._generate_summary(papers, citations, topic)

            return ActionResult(
                status=ActionStatus.SUCCESS if papers else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "papers": papers,
                    "citations": citations,
                    "bibliography": bibliography,
                    "outline": outline,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Research failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to conduct research: {e}"
            )

    async def _search_source(self, source: str, topic: str, year_from: int) -> List[Dict]:
        """Search a specific source for papers."""
        papers = []

        try:
            if "scholar" in source.lower():
                url = f"https://scholar.google.com/scholar?q={topic.replace(' ', '+')}&as_ylo={year_from}"
            elif "wikipedia" in source.lower():
                url = f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}"
            else:
                url = f"https://www.google.com/search?q={topic.replace(' ', '+')}+research+paper"

            await self.browser.navigate(url)
            await asyncio.sleep(2)

            if "scholar" in source.lower():
                papers = await self._extract_scholar_papers()
            elif "wikipedia" in source.lower():
                papers = await self._extract_wikipedia_references()
            else:
                papers = await self._extract_general_papers()

            for paper in papers:
                paper["source"] = source

        except Exception as e:
            logger.warning(f"Failed to search {source}: {e}")

        return papers

    async def _extract_scholar_papers(self) -> List[Dict]:
        """Extract papers from Google Scholar."""
        try:
            papers = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.gs_ri');

                    items.forEach(item => {
                        const title = item.querySelector('.gs_rt')?.textContent?.trim();
                        const authors = item.querySelector('.gs_a')?.textContent?.trim();
                        const snippet = item.querySelector('.gs_rs')?.textContent?.trim();

                        if (title) {
                            results.push({
                                title: title,
                                authors: authors || '',
                                abstract: snippet || '',
                                year: null
                            });
                        }
                    });

                    return results.slice(0, 10);
                }
            """)
            return papers
        except Exception as e:
            logger.error(f"Failed to extract Scholar papers: {e}")
            return []

    async def _extract_wikipedia_references(self) -> List[Dict]:
        """Extract references from Wikipedia."""
        try:
            refs = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const refs = document.querySelectorAll('.reference-text');

                    refs.forEach(ref => {
                        const text = ref.textContent?.trim();
                        if (text) {
                            results.push({
                                title: text.split('.')[0] || text,
                                citation: text,
                                type: 'reference'
                            });
                        }
                    });

                    return results.slice(0, 10);
                }
            """)
            return refs
        except Exception as e:
            logger.error(f"Failed to extract Wikipedia references: {e}")
            return []

    async def _extract_general_papers(self) -> List[Dict]:
        """Extract papers from general search."""
        try:
            papers = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.g');

                    items.forEach(item => {
                        const title = item.querySelector('h3')?.textContent?.trim();
                        const snippet = item.querySelector('.VwiC3b')?.textContent?.trim();

                        if (title && (title.toLowerCase().includes('paper') || title.toLowerCase().includes('research'))) {
                            results.push({
                                title: title,
                                abstract: snippet || '',
                                type: 'general'
                            });
                        }
                    });

                    return results.slice(0, 5);
                }
            """)
            return papers
        except Exception as e:
            logger.error(f"Failed to extract general papers: {e}")
            return []

    def _extract_citations(self, papers: List[Dict]) -> List[Dict]:
        """Extract citation information."""
        citations = []
        for paper in papers:
            citation = {
                "title": paper.get("title", ""),
                "authors": paper.get("authors", "Unknown"),
                "year": paper.get("year", "n.d."),
                "source": paper.get("source", "")
            }
            citations.append(citation)
        return citations

    def _build_bibliography(self, citations: List[Dict]) -> List[str]:
        """Build formatted bibliography."""
        bibliography = []
        for cit in citations:
            authors = cit.get("authors", "Unknown")
            year = cit.get("year", "n.d.")
            title = cit.get("title", "Untitled")
            bib_entry = f"{authors} ({year}). {title}."
            bibliography.append(bib_entry)
        return sorted(bibliography)

    def _create_review_outline(self, papers: List[Dict], topic: str) -> Dict:
        """Create literature review outline."""
        return {
            "title": f"Literature Review: {topic}",
            "sections": [
                {"section": "Introduction", "content": f"Overview of research on {topic}"},
                {"section": "Key Findings", "content": f"Analysis of {len(papers)} papers"},
                {"section": "Methodology", "content": "Review of research methods"},
                {"section": "Conclusions", "content": "Summary of literature"}
            ],
            "papers_reviewed": len(papers)
        }

    def _save_research_report(self, papers: List, citations: List, bibliography: List, outline: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"research_report_{timestamp}.json"
            return str(save_json(filename, {
                "papers": papers,
                "citations": citations,
                "bibliography": bibliography,
                "outline": outline
            }))
        except Exception as e:
            logger.error(f"Failed to save research literature: {e}")
            return None

    def _generate_summary(self, papers: List, citations: List, topic: str) -> str:
        lines = [
            "## Research Literature Report",
            f"**Topic:** {topic}",
            f"**Papers Found:** {len(papers)}",
            f"**Citations Extracted:** {len(citations)}",
            ""
        ]

        if papers:
            lines.append("### Key Papers:")
            for i, paper in enumerate(papers[:5], 1):
                lines.append(f"{i}. {paper.get('title', 'Untitled')}")
            lines.append("")

        return "\n".join(lines)


# ============ AD) NON-PROFIT GRANT/DONOR RESEARCH ============

class AD1_GrantFinder(BaseExecutor):
    """Search for grants and research potential donors."""

    capability = "AD1"
    action = "find_grants"
    required_params = ["mission"]
    optional_params = ["location", "amount"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        mission = params.get("mission", "")
        location = params.get("location", "")
        amount = params.get("amount", "")

        if not mission:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide organization mission."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for grant research"
            )

        try:
            grants = await self._search_grants(mission, location, amount)
            donors = await self._research_donors(mission, location)
            matched = self._match_grants(grants, mission)
            timeline = self._create_application_timeline(matched)

            saved_path = self._save_grant_report(grants, donors, matched, timeline)

            summary = self._generate_summary(grants, donors, matched)

            return ActionResult(
                status=ActionStatus.SUCCESS if grants else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "grants": grants,
                    "donors": donors,
                    "matched_grants": matched,
                    "timeline": timeline,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Grant research failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to find grants: {e}"
            )

    async def _search_grants(self, mission: str, location: str, amount: str) -> List[Dict]:
        """Search for relevant grants."""
        try:
            search_query = f"{mission} grants nonprofit"
            if location:
                search_query += f" {location}"
            if amount:
                search_query += f" up to ${amount}"

            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(2)

            grants = []

            data = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.g');

                    items.forEach(item => {
                        const title = item.querySelector('h3')?.textContent?.trim();
                        const snippet = item.querySelector('.VwiC3b')?.textContent?.trim();
                        const link = item.querySelector('a')?.href;

                        if (title && (title.toLowerCase().includes('grant') || title.toLowerCase().includes('fund'))) {
                            results.push({
                                title: title,
                                description: snippet || '',
                                url: link || ''
                            });
                        }
                    });

                    return results.slice(0, 10);
                }
            """)

            for grant in data:
                grants.append({
                    "name": grant["title"],
                    "description": grant["description"],
                    "url": grant["url"],
                    "match_score": 0
                })

            return grants

        except Exception as e:
            logger.warning(f"Grant search failed: {e}")
            return []

    async def _research_donors(self, mission: str, location: str) -> List[Dict]:
        """Research potential donors."""
        try:
            search_query = f"{mission} donors philanthropists"
            if location:
                search_query += f" {location}"

            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(2)

            donors = []

            data = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const items = document.querySelectorAll('.g');

                    items.forEach(item => {
                        const title = item.querySelector('h3')?.textContent?.trim();
                        const snippet = item.querySelector('.VwiC3b')?.textContent?.trim();

                        if (title) {
                            results.push({
                                name: title,
                                info: snippet || ''
                            });
                        }
                    });

                    return results.slice(0, 5);
                }
            """)

            for donor in data:
                donors.append({
                    "name": donor["name"],
                    "description": donor["info"],
                    "type": "individual" if "foundation" not in donor["name"].lower() else "foundation"
                })

            return donors

        except Exception as e:
            logger.warning(f"Donor research failed: {e}")
            return []

    def _match_grants(self, grants: List[Dict], mission: str) -> List[Dict]:
        """Match grants to organization mission."""
        mission_keywords = mission.lower().split()

        for grant in grants:
            score = 0
            description = (grant.get("description", "") + " " + grant.get("name", "")).lower()

            for keyword in mission_keywords:
                if len(keyword) > 3 and keyword in description:
                    score += 1

            grant["match_score"] = score

        return sorted(grants, key=lambda g: g.get("match_score", 0), reverse=True)

    def _create_application_timeline(self, grants: List[Dict]) -> List[Dict]:
        """Create grant application timeline."""
        timeline = []

        for i, grant in enumerate(grants[:5], 1):
            deadline = datetime.now() + timedelta(days=30 * i)

            timeline.append({
                "grant": grant.get("name"),
                "priority": i,
                "estimated_deadline": deadline.strftime("%Y-%m-%d"),
                "tasks": [
                    "Review grant requirements",
                    "Prepare application materials",
                    "Submit application"
                ]
            })

        return timeline

    def _save_grant_report(self, grants: List, donors: List, matched: List, timeline: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"grant_report_{timestamp}.json"
            return str(save_json(filename, {
                "grants": grants,
                "donors": donors,
                "matched_grants": matched,
                "timeline": timeline
            }))
        except Exception as e:
            logger.error(f"Failed to save grant finder report: {e}")
            return None

    def _generate_summary(self, grants: List, donors: List, matched: List) -> str:
        lines = [
            "## Grant Finder Report",
            f"**Grants Found:** {len(grants)}",
            f"**Potential Donors:** {len(donors)}",
            ""
        ]

        if matched:
            lines.append("### Top Grant Matches:")
            for i, grant in enumerate(matched[:5], 1):
                lines.append(f"{i}. {grant.get('name')} (Match Score: {grant.get('match_score')})")
            lines.append("")

        if donors:
            lines.append("### Potential Donors:")
            for donor in donors[:3]:
                lines.append(f"- {donor.get('name')} ({donor.get('type')})")

        return "\n".join(lines)


# ============ HELPER FUNCTIONS ============

def summarize_research_findings(findings: List[Dict], topic: str) -> str:
    """Summarize research findings into a coherent report."""
    summary_lines = [
        f"# Research Summary: {topic}",
        "",
        f"**Total Findings:** {len(findings)}",
        ""
    ]

    # Group by source
    by_source = {}
    for finding in findings:
        source = finding.get("source", "unknown")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(finding)

    for source, items in by_source.items():
        summary_lines.append(f"## {source.title()}")
        for item in items[:5]:
            title = item.get("title", item.get("name", "Untitled"))
            summary_lines.append(f"- {title}")
        summary_lines.append("")

    return "\n".join(summary_lines)


def create_competitive_analysis(competitors: List[Dict], focus_areas: List[str] = None) -> Dict:
    """Create a competitive analysis matrix from research data."""
    if focus_areas is None:
        focus_areas = ["pricing", "features", "market_position", "strengths", "weaknesses"]

    analysis = {
        "competitors_analyzed": len(competitors),
        "focus_areas": focus_areas,
        "matrix": []
    }

    for competitor in competitors:
        entry = {
            "name": competitor.get("name", "Unknown"),
            "scores": {}
        }
        for area in focus_areas:
            entry["scores"][area] = competitor.get(area, "N/A")
        analysis["matrix"].append(entry)

    return analysis


def extract_market_insights(research_data: List[Dict]) -> Dict:
    """Extract market insights from research data."""
    insights = {
        "trends": [],
        "opportunities": [],
        "threats": [],
        "key_players": []
    }

    # Simple keyword-based extraction
    trend_keywords = ["growing", "increasing", "trend", "rise", "surge"]
    opportunity_keywords = ["opportunity", "potential", "emerging", "untapped"]
    threat_keywords = ["risk", "threat", "challenge", "decline", "competition"]

    for item in research_data:
        text = str(item.get("description", "") + " " + item.get("abstract", "")).lower()

        for keyword in trend_keywords:
            if keyword in text:
                insights["trends"].append(item.get("title", ""))
                break

        for keyword in opportunity_keywords:
            if keyword in text:
                insights["opportunities"].append(item.get("title", ""))
                break

        for keyword in threat_keywords:
            if keyword in text:
                insights["threats"].append(item.get("title", ""))
                break

    # Deduplicate
    for key in insights:
        insights[key] = list(set(insights[key]))[:5]

    return insights
