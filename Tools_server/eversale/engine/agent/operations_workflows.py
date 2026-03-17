"""
Operations Workflows - Extracted from workflows_extended.py

Contains operations-focused workflow executors:
- W1_ContentModerator: Review flagged content, apply moderation policy (Workflow W)
- X1_InventoryMonitor: Monitor stock levels, generate reorder alerts (Workflow X)

Reduces workflows_extended.py by consolidating operations management capabilities.
"""

import asyncio
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger

from .executors.base import BaseExecutor, ActionResult, ActionStatus


# ============ W) CONTENT MODERATION ============

class W1_ContentModerator(BaseExecutor):
    """Review flagged content and apply moderation policy."""

    capability = "W1"
    action = "moderate_content"
    required_params = ["content"]
    optional_params = ["policy", "auto_action"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        content = params.get("content", "")
        policy = params.get("policy", "standard")
        auto_action = params.get("auto_action", False)

        if not content:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide content to moderate."
            )

        try:
            # Analyze content
            analysis = self._analyze_content(content)

            # Check against policy
            violations = self._check_policy_violations(content, analysis, policy)

            # Research context if needed
            context = {}
            if self.browser and violations:
                context = await self._research_context(content)

            # Determine moderation action
            action = self._determine_action(violations, context)

            # Generate moderation report
            report = self._create_moderation_report(content, analysis, violations, action)

            saved_path = self._save_moderation_decision(report)

            summary = self._generate_summary(analysis, violations, action)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "analysis": analysis,
                    "violations": violations,
                    "context": context,
                    "action": action,
                    "report": report,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Content moderation failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to moderate content: {e}"
            )

    def _analyze_content(self, content: str) -> Dict:
        """Analyze content for issues."""
        analysis = {
            "length": len(content),
            "word_count": len(content.split()),
            "flags": [],
            "severity": "none"
        }

        content_lower = content.lower()

        # Check for prohibited content
        prohibited_keywords = {
            "hate_speech": ["hate", "racist", "sexist"],
            "violence": ["kill", "attack", "harm"],
            "spam": ["click here", "buy now", "limited time"],
            "profanity": ["explicit terms would go here"],
            "harassment": ["threat", "stalk", "harass"]
        }

        for category, keywords in prohibited_keywords.items():
            if any(kw in content_lower for kw in keywords):
                analysis["flags"].append(category)

        # Determine severity
        if len(analysis["flags"]) >= 3:
            analysis["severity"] = "high"
        elif len(analysis["flags"]) >= 1:
            analysis["severity"] = "medium"
        else:
            analysis["severity"] = "low"

        return analysis

    def _check_policy_violations(self, content: str, analysis: Dict, policy: str) -> List[Dict]:
        """Check for policy violations."""
        violations = []

        for flag in analysis["flags"]:
            violations.append({
                "type": flag,
                "severity": analysis["severity"],
                "policy": policy,
                "description": f"Content flagged for {flag.replace('_', ' ')}"
            })

        return violations

    async def _research_context(self, content: str) -> Dict:
        """Research context for borderline cases."""
        try:
            # Search for similar cases or context
            search_terms = " ".join(content.split()[:5])
            await self.browser.navigate(f"https://www.google.com/search?q={search_terms.replace(' ', '+')}")
            await asyncio.sleep(1)

            return {
                "research_performed": True,
                "note": "Context research completed"
            }
        except:
            return {"research_performed": False}

    def _determine_action(self, violations: List[Dict], context: Dict) -> Dict:
        """Determine moderation action."""
        if not violations:
            return {
                "decision": "approve",
                "reason": "No policy violations detected",
                "requires_review": False
            }

        high_severity = any(v["severity"] == "high" for v in violations)

        if high_severity:
            return {
                "decision": "remove",
                "reason": "High severity violations detected",
                "requires_review": True
            }
        else:
            return {
                "decision": "flag_for_review",
                "reason": "Medium severity violations detected",
                "requires_review": True
            }

    def _create_moderation_report(self, content: str, analysis: Dict, violations: List, action: Dict) -> Dict:
        """Create moderation report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "content_preview": content[:200],
            "analysis": analysis,
            "violations": violations,
            "action": action,
            "moderator": "AI System"
        }

    def _save_moderation_decision(self, report: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"moderation_report_{timestamp}.json"
            return str(save_json(filename, report))
        except:
            return None

    def _generate_summary(self, analysis: Dict, violations: List, action: Dict) -> str:
        lines = [
            "## Content Moderation Report",
            f"**Severity:** {analysis['severity'].upper()}",
            f"**Decision:** {action['decision'].upper()}",
            ""
        ]

        if violations:
            lines.append("### Violations:")
            for v in violations:
                lines.append(f"- {v['type'].replace('_', ' ').title()}: {v['description']}")
            lines.append("")

        lines.append(f"**Action Required:** {action['reason']}")
        if action.get("requires_review"):
            lines.append("**Manual Review:** Required")

        return "\n".join(lines)


# ============ X) INVENTORY ============

class X1_InventoryMonitor(BaseExecutor):
    """Monitor stock levels and generate reorder alerts."""

    capability = "X1"
    action = "monitor_inventory"
    required_params = ["inventory_data"]
    optional_params = ["reorder_threshold", "warehouse"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        inventory_data = params.get("inventory_data", "")
        reorder_threshold = params.get("reorder_threshold", 10)
        warehouse = params.get("warehouse", "main")

        if not inventory_data:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide inventory data."
            )

        try:
            # Parse inventory
            items = self._parse_inventory(inventory_data)

            # Check stock levels
            stock_analysis = self._analyze_stock_levels(items, reorder_threshold)

            # Generate reorder alerts
            alerts = self._generate_reorder_alerts(stock_analysis)

            # Verify suppliers if browser available
            if self.browser and alerts:
                alerts = await self._verify_suppliers(alerts)

            # Create reorder recommendations
            recommendations = self._create_reorder_recommendations(alerts)

            saved_path = self._save_inventory_report(items, stock_analysis, alerts, recommendations)

            summary = self._generate_summary(stock_analysis, alerts)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "items": items,
                    "stock_analysis": stock_analysis,
                    "alerts": alerts,
                    "recommendations": recommendations,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Inventory monitoring failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to monitor inventory: {e}"
            )

    def _parse_inventory(self, data: str) -> List[Dict]:
        """Parse inventory data."""
        items = []

        for line in data.split('\n'):
            if not line.strip():
                continue

            item = {"raw": line}

            # Extract item name
            name_match = re.search(r'^([A-Za-z0-9\s\-]+)', line)
            if name_match:
                item["name"] = name_match.group(1).strip()

            # Extract quantity
            qty_match = re.search(r'qty[:\s]*(\d+)|quantity[:\s]*(\d+)|(\d+)\s*units?', line, re.IGNORECASE)
            if qty_match:
                item["quantity"] = int(qty_match.group(1) or qty_match.group(2) or qty_match.group(3))

            # Extract SKU
            sku_match = re.search(r'sku[:\s]*([A-Z0-9\-]+)', line, re.IGNORECASE)
            if sku_match:
                item["sku"] = sku_match.group(1)

            items.append(item)

        return items

    def _analyze_stock_levels(self, items: List[Dict], threshold: int) -> Dict:
        """Analyze stock levels."""
        analysis = {
            "total_items": len(items),
            "low_stock": 0,
            "out_of_stock": 0,
            "adequate_stock": 0,
            "items_by_status": {"low": [], "out": [], "adequate": []}
        }

        for item in items:
            qty = item.get("quantity", 0)

            if qty == 0:
                analysis["out_of_stock"] += 1
                analysis["items_by_status"]["out"].append(item)
            elif qty < threshold:
                analysis["low_stock"] += 1
                analysis["items_by_status"]["low"].append(item)
            else:
                analysis["adequate_stock"] += 1
                analysis["items_by_status"]["adequate"].append(item)

        return analysis

    def _generate_reorder_alerts(self, analysis: Dict) -> List[Dict]:
        """Generate reorder alerts."""
        alerts = []

        # Out of stock - critical
        for item in analysis["items_by_status"]["out"]:
            alerts.append({
                "item": item.get("name", "Unknown"),
                "sku": item.get("sku", "N/A"),
                "current_qty": 0,
                "severity": "critical",
                "action": "URGENT: Reorder immediately"
            })

        # Low stock - warning
        for item in analysis["items_by_status"]["low"]:
            alerts.append({
                "item": item.get("name", "Unknown"),
                "sku": item.get("sku", "N/A"),
                "current_qty": item.get("quantity", 0),
                "severity": "warning",
                "action": "Reorder soon"
            })

        return alerts

    async def _verify_suppliers(self, alerts: List[Dict]) -> List[Dict]:
        """Verify supplier availability."""
        for alert in alerts[:3]:
            item_name = alert.get("item", "")
            if item_name:
                try:
                    await self.browser.navigate(f"https://www.google.com/search?q={item_name.replace(' ', '+')}+supplier+buy")
                    await asyncio.sleep(1)

                    page_text = await self.browser.page.content()
                    alert["supplier_available"] = "buy" in page_text.lower() or "shop" in page_text.lower()
                except:
                    pass

        return alerts

    def _create_reorder_recommendations(self, alerts: List[Dict]) -> List[Dict]:
        """Create reorder recommendations."""
        recommendations = []

        for alert in alerts:
            # Suggest reorder quantity (simplified)
            current_qty = alert.get("current_qty", 0)
            suggested_qty = max(50, current_qty * 3)

            recommendations.append({
                "item": alert["item"],
                "sku": alert.get("sku"),
                "current_quantity": current_qty,
                "suggested_order": suggested_qty,
                "priority": alert["severity"]
            })

        return sorted(recommendations, key=lambda r: r["priority"] == "critical", reverse=True)

    def _save_inventory_report(self, items: List, analysis: Dict, alerts: List, recommendations: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"inventory_report_{timestamp}.json"
            return str(save_json(filename, {
                "items": items,
                "analysis": analysis,
                "alerts": alerts,
                "recommendations": recommendations
            }))
        except:
            return None

    def _generate_summary(self, analysis: Dict, alerts: List) -> str:
        lines = [
            "## Inventory Monitoring Report",
            f"**Total Items:** {analysis['total_items']}",
            f"**Out of Stock:** {analysis['out_of_stock']}",
            f"**Low Stock:** {analysis['low_stock']}",
            f"**Adequate Stock:** {analysis['adequate_stock']}",
            ""
        ]

        if alerts:
            lines.append("### Reorder Alerts:")
            for alert in alerts[:5]:
                lines.append(f"- [{alert['severity'].upper()}] {alert['item']}: {alert['action']}")
            lines.append("")

        return "\n".join(lines)
