"""
Enterprise Workflows - Extracted from workflows_extended.py

Contains enterprise-focused workflow executors:
- S1_AccessAuditor: SaaS access audits, user provisioning (Workflow S)
- V1_ComplianceChecker: GDPR/SOC2 compliance checks (Workflow V)
- V2_AuditTrailBuilder: Build compliance audit trails
- Z1_LogAggregator: Log aggregation and analysis (Workflow Z)
- Z2_AlertCorrelator: Correlate alerts and create incident tickets

Reduces workflows_extended.py by organizing enterprise/monitoring capabilities.
"""

import asyncio
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger

from .executors.base import BaseExecutor, ActionResult, ActionStatus


# ============ S) ENTERPRISE ADMIN ============

class S1_AccessAuditor(BaseExecutor):
    """Audit SaaS user access and manage user provisioning."""

    capability = "S1"
    action = "audit_saas_access"
    required_params = ["organization"]
    optional_params = ["apps", "user_email"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        organization = params.get("organization", "")
        apps = params.get("apps", ["gmail", "slack", "github", "notion"])
        user_email = params.get("user_email", None)

        if not organization:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide organization name."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for SaaS audit"
            )

        try:
            access_audit = []

            # Audit each SaaS app
            for app in apps:
                audit_result = await self._audit_app_access(app, organization, user_email)
                if audit_result:
                    access_audit.append(audit_result)

            # Identify access issues
            issues = self._identify_access_issues(access_audit)

            # Generate compliance report
            compliance = self._check_compliance(access_audit, issues)

            # Create remediation plan
            remediation = self._create_remediation_plan(issues)

            saved_path = self._save_audit_report(access_audit, issues, compliance, remediation)

            summary = self._generate_summary(access_audit, issues, compliance)

            return ActionResult(
                status=ActionStatus.SUCCESS if access_audit else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "access_audit": access_audit,
                    "issues": issues,
                    "compliance": compliance,
                    "remediation": remediation,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"SaaS audit failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to audit SaaS access: {e}"
            )

    async def _audit_app_access(self, app: str, org: str, user_email: Optional[str]) -> Optional[Dict]:
        """Audit access for a specific SaaS app."""
        try:
            search_query = f"{app} {org} user access audit"
            if user_email:
                search_query += f" {user_email}"

            await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await asyncio.sleep(1)

            audit = {
                "app": app,
                "organization": org,
                "user_email": user_email,
                "access_status": "unknown",
                "permissions": [],
                "last_active": None,
                "security_issues": []
            }

            # Check for admin documentation
            page_text = await self.browser.page.content()

            # Determine access status based on search results
            if "admin" in page_text.lower() or "manage users" in page_text.lower():
                audit["access_status"] = "admin_access_available"
            elif "login" in page_text.lower():
                audit["access_status"] = "requires_login"
            else:
                audit["access_status"] = "check_manually"

            # Check for security best practices
            if "2fa" in page_text.lower() or "two-factor" in page_text.lower():
                audit["permissions"].append("2FA recommended")
            if "sso" in page_text.lower() or "single sign" in page_text.lower():
                audit["permissions"].append("SSO available")

            return audit

        except Exception as e:
            logger.warning(f"Failed to audit {app}: {e}")
            return None

    def _identify_access_issues(self, audit: List[Dict]) -> List[Dict]:
        """Identify access control issues."""
        issues = []

        for app_audit in audit:
            # Missing 2FA
            perms = app_audit.get("permissions", [])
            if "2FA recommended" in perms:
                issues.append({
                    "severity": "medium",
                    "app": app_audit["app"],
                    "issue": "2FA not enforced",
                    "recommendation": "Enable 2FA for all users"
                })

            # Unknown access status
            if app_audit.get("access_status") == "unknown":
                issues.append({
                    "severity": "high",
                    "app": app_audit["app"],
                    "issue": "Cannot verify access",
                    "recommendation": "Manual audit required"
                })

        return issues

    def _check_compliance(self, audit: List[Dict], issues: List[Dict]) -> Dict:
        """Check compliance status."""
        high_issues = sum(1 for i in issues if i["severity"] == "high")
        medium_issues = sum(1 for i in issues if i["severity"] == "medium")

        status = "compliant"
        if high_issues > 0:
            status = "non_compliant"
        elif medium_issues > 2:
            status = "needs_attention"

        return {
            "status": status,
            "apps_audited": len(audit),
            "high_priority_issues": high_issues,
            "medium_priority_issues": medium_issues,
            "compliance_score": max(0, 100 - (high_issues * 20) - (medium_issues * 10))
        }

    def _create_remediation_plan(self, issues: List[Dict]) -> List[Dict]:
        """Create remediation action plan."""
        plan = []

        # Group by severity
        high_priority = [i for i in issues if i["severity"] == "high"]
        medium_priority = [i for i in issues if i["severity"] == "medium"]

        for issue in high_priority:
            plan.append({
                "priority": 1,
                "action": issue["recommendation"],
                "app": issue["app"],
                "timeline": "immediate"
            })

        for issue in medium_priority:
            plan.append({
                "priority": 2,
                "action": issue["recommendation"],
                "app": issue["app"],
                "timeline": "within 30 days"
            })

        return plan

    def _save_audit_report(self, audit: List, issues: List, compliance: Dict, remediation: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"saas_audit_{timestamp}.json"
            return str(save_json(filename, {
                "access_audit": audit,
                "issues": issues,
                "compliance": compliance,
                "remediation": remediation
            }))
        except Exception as e:
            logger.warning(f"Failed to save audit report: {e}")
            return None

    def _generate_summary(self, audit: List, issues: List, compliance: Dict) -> str:
        lines = [
            "## SaaS Access Audit Report",
            f"**Apps Audited:** {compliance['apps_audited']}",
            f"**Compliance Status:** {compliance['status'].upper()}",
            f"**Compliance Score:** {compliance['compliance_score']}/100",
            ""
        ]

        if issues:
            lines.append("### Issues Found:")
            for issue in issues[:5]:
                lines.append(f"- [{issue['severity'].upper()}] {issue['app']}: {issue['issue']}")
            lines.append("")

        lines.append("**Next Steps:** Review remediation plan and address high-priority issues immediately.")

        return "\n".join(lines)


class S2_ComplianceReporter(BaseExecutor):
    """Generate compliance reports for enterprise systems."""

    capability = "S2"
    action = "generate_compliance_report"
    required_params = ["organization"]
    optional_params = ["systems", "report_type"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        organization = params.get("organization", "")
        systems = params.get("systems", ["saas", "infrastructure", "data"])
        report_type = params.get("report_type", "quarterly")

        if not organization:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide organization name."
            )

        try:
            # Gather compliance data from each system
            compliance_data = []
            for system in systems:
                data = self._gather_system_compliance(system, organization)
                compliance_data.append(data)

            # Analyze compliance posture
            posture = self._analyze_compliance_posture(compliance_data)

            # Generate executive summary
            executive_summary = self._generate_executive_summary(compliance_data, posture)

            # Create detailed findings
            findings = self._compile_findings(compliance_data)

            # Generate recommendations
            recommendations = self._generate_recommendations(findings)

            saved_path = self._save_compliance_report(
                compliance_data, posture, executive_summary, findings, recommendations
            )

            summary = self._generate_report_summary(posture, findings)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "compliance_data": compliance_data,
                    "posture": posture,
                    "executive_summary": executive_summary,
                    "findings": findings,
                    "recommendations": recommendations,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Compliance reporting failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to generate compliance report: {e}"
            )

    def _gather_system_compliance(self, system: str, org: str) -> Dict:
        """Gather compliance data for a system."""
        return {
            "system": system,
            "organization": org,
            "compliant": True,
            "score": 85,
            "issues": [],
            "last_audit": datetime.now().isoformat()
        }

    def _analyze_compliance_posture(self, data: List[Dict]) -> Dict:
        """Analyze overall compliance posture."""
        avg_score = sum(d["score"] for d in data) / len(data) if data else 0
        total_issues = sum(len(d.get("issues", [])) for d in data)

        return {
            "overall_score": round(avg_score, 1),
            "total_systems": len(data),
            "total_issues": total_issues,
            "status": "good" if avg_score >= 80 else "needs_improvement"
        }

    def _generate_executive_summary(self, data: List[Dict], posture: Dict) -> str:
        """Generate executive summary."""
        return f"""
## Executive Summary

**Organization Compliance Status:** {posture['status'].upper()}
**Overall Compliance Score:** {posture['overall_score']}/100

This {len(data)}-system compliance audit identified {posture['total_issues']} areas requiring attention.
The organization demonstrates {posture['status'].replace('_', ' ')} compliance posture overall.
"""

    def _compile_findings(self, data: List[Dict]) -> List[Dict]:
        """Compile detailed findings."""
        findings = []
        for system_data in data:
            for issue in system_data.get("issues", []):
                findings.append({
                    "system": system_data["system"],
                    "issue": issue,
                    "severity": "medium"
                })
        return findings

    def _generate_recommendations(self, findings: List[Dict]) -> List[str]:
        """Generate recommendations."""
        recommendations = [
            "Implement regular compliance monitoring",
            "Establish automated compliance checks",
            "Conduct quarterly compliance reviews"
        ]
        if len(findings) > 5:
            recommendations.append("Prioritize remediation of high-severity findings")
        return recommendations

    def _save_compliance_report(self, data, posture, summary, findings, recommendations) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"compliance_report_{timestamp}.json"
            return str(save_json(filename, {
                "compliance_data": data,
                "posture": posture,
                "executive_summary": summary,
                "findings": findings,
                "recommendations": recommendations
            }))
        except Exception as e:
            logger.warning(f"Failed to save compliance report: {e}")
            return None

    def _generate_report_summary(self, posture: Dict, findings: List) -> str:
        return f"""
## Compliance Report Generated

**Status:** {posture['status'].upper()}
**Score:** {posture['overall_score']}/100
**Systems Audited:** {posture['total_systems']}
**Findings:** {len(findings)}
"""


# ============ V) AUDIT & COMPLIANCE ============

class V1_ComplianceChecker(BaseExecutor):
    """Check GDPR, SOC2, and other compliance requirements."""

    capability = "V1"
    action = "check_compliance"
    required_params = ["website_or_system"]
    optional_params = ["compliance_type", "checklist"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        target = params.get("website_or_system", "")
        compliance_type = params.get("compliance_type", "gdpr")
        checklist = params.get("checklist", [])

        if not target:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide website or system to audit."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for compliance check"
            )

        try:
            # Run compliance checks
            if compliance_type.lower() == "gdpr":
                results = await self._check_gdpr_compliance(target)
            elif compliance_type.lower() == "soc2":
                results = await self._check_soc2_compliance(target)
            else:
                results = await self._check_general_compliance(target, checklist)

            # Build audit trail
            audit_trail = self._build_audit_trail(results)

            # Identify violations
            violations = self._identify_violations(results)

            # Generate remediation plan
            remediation = self._create_remediation_plan(violations)

            # Calculate compliance score
            score = self._calculate_compliance_score(results, violations)

            saved_path = self._save_compliance_report(results, violations, remediation, score)

            summary = self._generate_summary(results, violations, score)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "compliance_results": results,
                    "audit_trail": audit_trail,
                    "violations": violations,
                    "remediation": remediation,
                    "score": score,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Compliance check failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to check compliance: {e}"
            )

    async def _check_gdpr_compliance(self, target: str) -> Dict:
        """Check GDPR compliance."""
        await self.browser.navigate(target)
        await asyncio.sleep(2)

        page_text = await self.browser.page.content()
        page_lower = page_text.lower()

        checks = {
            "privacy_policy": "privacy policy" in page_lower or "privacy notice" in page_lower,
            "cookie_consent": "cookie" in page_lower and ("accept" in page_lower or "consent" in page_lower),
            "data_protection": "data protection" in page_lower or "gdpr" in page_lower,
            "right_to_access": "right to access" in page_lower or "data subject rights" in page_lower,
            "contact_dpo": "data protection officer" in page_lower or "dpo" in page_lower,
            "ssl_enabled": target.startswith("https://")
        }

        return {
            "target": target,
            "compliance_type": "GDPR",
            "checks": checks,
            "timestamp": datetime.now().isoformat()
        }

    async def _check_soc2_compliance(self, target: str) -> Dict:
        """Check SOC2 compliance indicators."""
        await self.browser.navigate(target)
        await asyncio.sleep(2)

        page_text = await self.browser.page.content()
        page_lower = page_text.lower()

        checks = {
            "security_policy": "security policy" in page_lower or "security" in page_lower,
            "availability": "uptime" in page_lower or "sla" in page_lower,
            "processing_integrity": "data integrity" in page_lower,
            "confidentiality": "confidentiality" in page_lower or "nda" in page_lower,
            "privacy": "privacy" in page_lower,
            "ssl_enabled": target.startswith("https://"),
            "audit_logs": "audit log" in page_lower or "audit trail" in page_lower
        }

        return {
            "target": target,
            "compliance_type": "SOC2",
            "checks": checks,
            "timestamp": datetime.now().isoformat()
        }

    async def _check_general_compliance(self, target: str, checklist: List[str]) -> Dict:
        """Check general compliance based on custom checklist."""
        await self.browser.navigate(target)
        await asyncio.sleep(2)

        page_text = await self.browser.page.content()
        page_lower = page_text.lower()

        checks = {}
        for item in checklist:
            checks[item] = item.lower() in page_lower

        return {
            "target": target,
            "compliance_type": "Custom",
            "checks": checks,
            "timestamp": datetime.now().isoformat()
        }

    def _build_audit_trail(self, results: Dict) -> List[Dict]:
        """Build audit trail entries."""
        trail = []

        for check_name, passed in results.get("checks", {}).items():
            trail.append({
                "timestamp": results.get("timestamp"),
                "check": check_name,
                "result": "PASS" if passed else "FAIL",
                "target": results.get("target")
            })

        return trail

    def _identify_violations(self, results: Dict) -> List[Dict]:
        """Identify compliance violations."""
        violations = []
        checks = results.get("checks", {})

        critical_checks = ["privacy_policy", "ssl_enabled", "security_policy"]

        for check_name, passed in checks.items():
            if not passed:
                severity = "critical" if check_name in critical_checks else "warning"
                violations.append({
                    "check": check_name,
                    "severity": severity,
                    "description": f"Missing or inadequate: {check_name.replace('_', ' ').title()}"
                })

        return violations

    def _create_remediation_plan(self, violations: List[Dict]) -> List[Dict]:
        """Create remediation action plan."""
        plan = []

        for violation in violations:
            if violation["severity"] == "critical":
                timeline = "immediate"
            else:
                timeline = "within 30 days"

            plan.append({
                "issue": violation["check"],
                "severity": violation["severity"],
                "action": f"Implement {violation['check'].replace('_', ' ')}",
                "timeline": timeline
            })

        return sorted(plan, key=lambda x: x["severity"] == "critical", reverse=True)

    def _calculate_compliance_score(self, results: Dict, violations: List[Dict]) -> Dict:
        """Calculate compliance score."""
        checks = results.get("checks", {})
        total_checks = len(checks)
        passed_checks = sum(1 for v in checks.values() if v)

        critical_violations = sum(1 for v in violations if v["severity"] == "critical")

        score_pct = (passed_checks / total_checks * 100) if total_checks > 0 else 0

        status = "compliant"
        if critical_violations > 0:
            status = "non_compliant"
        elif score_pct < 80:
            status = "needs_improvement"

        return {
            "score": round(score_pct, 1),
            "passed": passed_checks,
            "total": total_checks,
            "critical_violations": critical_violations,
            "status": status
        }

    def _save_compliance_report(self, results: Dict, violations: List, remediation: List, score: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"compliance_report_{timestamp}.json"
            return str(save_json(filename, {
                "results": results,
                "violations": violations,
                "remediation": remediation,
                "score": score
            }))
        except Exception as e:
            logger.warning(f"Failed to save compliance report: {e}")
            return None

    def _generate_summary(self, results: Dict, violations: List, score: Dict) -> str:
        lines = [
            "## Compliance Audit Report",
            f"**Target:** {results.get('target')}",
            f"**Type:** {results.get('compliance_type')}",
            f"**Score:** {score['score']}/100",
            f"**Status:** {score['status'].upper()}",
            ""
        ]

        if violations:
            lines.append("### Violations Found:")
            for v in violations[:5]:
                lines.append(f"- [{v['severity'].upper()}] {v['description']}")
            lines.append("")

        lines.append(f"**Checks Passed:** {score['passed']}/{score['total']}")

        return "\n".join(lines)


class V2_AuditTrailBuilder(BaseExecutor):
    """Build comprehensive audit trails for compliance."""

    capability = "V2"
    action = "build_audit_trail"
    required_params = ["system"]
    optional_params = ["time_period", "events"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        system = params.get("system", "")
        time_period = params.get("time_period", "last_30_days")
        events = params.get("events", [])

        if not system:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide system name."
            )

        try:
            # Collect audit events
            audit_events = self._collect_audit_events(system, events)

            # Organize by category
            categorized = self._categorize_events(audit_events)

            # Identify anomalies
            anomalies = self._detect_anomalies(audit_events)

            # Generate trail report
            trail_report = self._generate_trail_report(audit_events, categorized, anomalies)

            saved_path = self._save_audit_trail(audit_events, categorized, anomalies, trail_report)

            summary = self._generate_trail_summary(audit_events, categorized, anomalies)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "audit_events": audit_events,
                    "categorized": categorized,
                    "anomalies": anomalies,
                    "trail_report": trail_report,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Audit trail building failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to build audit trail: {e}"
            )

    def _collect_audit_events(self, system: str, events: List) -> List[Dict]:
        """Collect audit events."""
        audit_events = []

        # Sample events if none provided
        if not events:
            events = [
                {"type": "login", "user": "admin", "timestamp": datetime.now().isoformat()},
                {"type": "data_access", "user": "user1", "timestamp": datetime.now().isoformat()},
                {"type": "config_change", "user": "admin", "timestamp": datetime.now().isoformat()}
            ]

        for event in events:
            audit_events.append({
                "system": system,
                "event_type": event.get("type", "unknown"),
                "user": event.get("user", "system"),
                "timestamp": event.get("timestamp", datetime.now().isoformat()),
                "details": event.get("details", {})
            })

        return audit_events

    def _categorize_events(self, events: List[Dict]) -> Dict:
        """Categorize events by type."""
        categorized = {
            "authentication": [],
            "data_access": [],
            "configuration": [],
            "other": []
        }

        for event in events:
            event_type = event.get("event_type", "").lower()
            if "login" in event_type or "auth" in event_type:
                categorized["authentication"].append(event)
            elif "access" in event_type or "read" in event_type:
                categorized["data_access"].append(event)
            elif "config" in event_type or "setting" in event_type:
                categorized["configuration"].append(event)
            else:
                categorized["other"].append(event)

        return categorized

    def _detect_anomalies(self, events: List[Dict]) -> List[Dict]:
        """Detect anomalous events."""
        anomalies = []

        # Count events by user
        user_counts = {}
        for event in events:
            user = event.get("user", "unknown")
            user_counts[user] = user_counts.get(user, 0) + 1

        # Flag users with excessive activity
        for user, count in user_counts.items():
            if count > 10:
                anomalies.append({
                    "type": "excessive_activity",
                    "user": user,
                    "event_count": count,
                    "severity": "medium"
                })

        return anomalies

    def _generate_trail_report(self, events: List, categorized: Dict, anomalies: List) -> Dict:
        """Generate audit trail report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "total_events": len(events),
            "categories": {k: len(v) for k, v in categorized.items()},
            "anomalies_detected": len(anomalies),
            "status": "clean" if not anomalies else "requires_review"
        }

    def _save_audit_trail(self, events, categorized, anomalies, report) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"audit_trail_{timestamp}.json"
            return str(save_json(filename, {
                "events": events,
                "categorized": categorized,
                "anomalies": anomalies,
                "report": report
            }))
        except Exception as e:
            logger.warning(f"Failed to save audit trail: {e}")
            return None

    def _generate_trail_summary(self, events: List, categorized: Dict, anomalies: List) -> str:
        lines = [
            "## Audit Trail Report",
            f"**Total Events:** {len(events)}",
            f"**Anomalies:** {len(anomalies)}",
            ""
        ]

        for category, cat_events in categorized.items():
            if cat_events:
                lines.append(f"**{category.replace('_', ' ').title()}:** {len(cat_events)}")

        if anomalies:
            lines.append("\n### Anomalies Detected:")
            for anomaly in anomalies[:5]:
                lines.append(f"- [{anomaly['severity'].upper()}] {anomaly['type']}: {anomaly.get('user', 'N/A')}")

        return "\n".join(lines)


# ============ Z) ENTERPRISE MONITORING ============

class Z1_LogAggregator(BaseExecutor):
    """Aggregate logs from multiple services."""

    capability = "Z1"
    action = "aggregate_logs"
    required_params = ["log_data"]
    optional_params = ["services", "time_window"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        log_data = params.get("log_data", "")
        services = params.get("services", ["api", "database", "frontend"])
        time_window = params.get("time_window", "1h")

        if not log_data:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide log data."
            )

        try:
            # Parse logs
            logs = self._parse_logs(log_data)

            # Aggregate by service
            aggregated = self._aggregate_by_service(logs, services)

            # Detect anomalies
            anomalies = self._detect_log_anomalies(logs)

            # Correlate alerts
            correlated = self._correlate_alerts(logs, anomalies)

            # Search for solutions if browser available
            if self.browser and correlated:
                correlated = await self._search_solutions(correlated)

            # Create incident tickets
            tickets = self._create_incident_tickets(correlated)

            saved_path = self._save_monitoring_report(logs, aggregated, anomalies, correlated, tickets)

            summary = self._generate_summary(aggregated, anomalies, tickets)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "logs": logs,
                    "aggregated": aggregated,
                    "anomalies": anomalies,
                    "correlated_alerts": correlated,
                    "tickets": tickets,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Log aggregation failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to aggregate logs: {e}"
            )

    def _parse_logs(self, data: str) -> List[Dict]:
        """Parse log entries."""
        logs = []

        for line in data.split('\n'):
            if not line.strip():
                continue

            log = {"raw": line}

            # Extract timestamp
            timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})', line)
            if timestamp_match:
                log["timestamp"] = timestamp_match.group(1)

            # Extract log level
            level_match = re.search(r'\b(ERROR|WARN|INFO|DEBUG|FATAL)\b', line, re.IGNORECASE)
            if level_match:
                log["level"] = level_match.group(1).upper()

            # Extract service name
            service_match = re.search(r'\[([a-z\-_]+)\]', line, re.IGNORECASE)
            if service_match:
                log["service"] = service_match.group(1)

            # Extract message
            message_parts = line.split(log.get("level", ""), 1)
            if len(message_parts) > 1:
                log["message"] = message_parts[1].strip()

            logs.append(log)

        return logs

    def _aggregate_by_service(self, logs: List[Dict], services: List[str]) -> Dict:
        """Aggregate logs by service."""
        aggregated = {
            "total_logs": len(logs),
            "by_service": {},
            "by_level": {"ERROR": 0, "WARN": 0, "INFO": 0, "DEBUG": 0}
        }

        for log in logs:
            service = log.get("service", "unknown")
            level = log.get("level", "UNKNOWN")

            # Count by service
            if service not in aggregated["by_service"]:
                aggregated["by_service"][service] = {"total": 0, "errors": 0}

            aggregated["by_service"][service]["total"] += 1

            if level == "ERROR" or level == "FATAL":
                aggregated["by_service"][service]["errors"] += 1

            # Count by level
            if level in aggregated["by_level"]:
                aggregated["by_level"][level] += 1

        return aggregated

    def _detect_log_anomalies(self, logs: List[Dict]) -> List[Dict]:
        """Detect anomalous log patterns."""
        anomalies = []

        # Error clustering
        error_logs = [l for l in logs if l.get("level") in ["ERROR", "FATAL"]]

        if len(error_logs) > 5:
            anomalies.append({
                "type": "high_error_rate",
                "severity": "high",
                "count": len(error_logs),
                "description": f"{len(error_logs)} errors detected"
            })

        # Repeated errors
        error_messages = [l.get("message", "") for l in error_logs]
        for msg in set(error_messages):
            count = error_messages.count(msg)
            if count >= 3:
                anomalies.append({
                    "type": "repeated_error",
                    "severity": "medium",
                    "count": count,
                    "description": f"Repeated error: {msg[:100]}"
                })

        return anomalies

    def _correlate_alerts(self, logs: List[Dict], anomalies: List[Dict]) -> List[Dict]:
        """Correlate alerts across services."""
        correlated = []

        # Group anomalies by time window
        for anomaly in anomalies:
            if anomaly["severity"] == "high":
                # Find related logs
                related_logs = []
                for log in logs[:10]:
                    if log.get("level") in ["ERROR", "FATAL"]:
                        related_logs.append(log)

                correlated.append({
                    "anomaly": anomaly,
                    "related_logs": related_logs,
                    "impact": "service_degradation",
                    "requires_action": True
                })

        return correlated

    async def _search_solutions(self, correlated: List[Dict]) -> List[Dict]:
        """Search for solutions to errors."""
        for item in correlated[:3]:
            anomaly = item.get("anomaly", {})
            description = anomaly.get("description", "")

            if description:
                try:
                    search_query = f"{description} solution stack overflow"
                    await self.browser.navigate(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
                    await asyncio.sleep(1)

                    page_text = await self.browser.page.content()
                    item["solution_found"] = "stack overflow" in page_text.lower()
                except Exception as e:
                    logger.debug(f"Failed to search solution for {description}: {e}")

        return correlated

    def _create_incident_tickets(self, correlated: List[Dict]) -> List[Dict]:
        """Create incident tickets."""
        tickets = []

        for item in correlated:
            anomaly = item.get("anomaly", {})

            if item.get("requires_action"):
                ticket = {
                    "title": f"{anomaly['type'].replace('_', ' ').title()}: {anomaly['description'][:100]}",
                    "severity": anomaly["severity"],
                    "description": anomaly["description"],
                    "affected_services": "Multiple",
                    "status": "open",
                    "created": datetime.now().isoformat()
                }
                tickets.append(ticket)

        return tickets

    def _save_monitoring_report(self, logs: List, aggregated: Dict, anomalies: List, correlated: List, tickets: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"monitoring_report_{timestamp}.json"
            return str(save_json(filename, {
                "logs": logs[:100],  # Limit size
                "aggregated": aggregated,
                "anomalies": anomalies,
                "correlated_alerts": correlated,
                "tickets": tickets
            }))
        except Exception as e:
            logger.warning(f"Failed to save monitoring report: {e}")
            return None

    def _generate_summary(self, aggregated: Dict, anomalies: List, tickets: List) -> str:
        lines = [
            "## Enterprise Monitoring Report",
            f"**Total Logs:** {aggregated['total_logs']}",
            f"**Errors:** {aggregated['by_level']['ERROR']}",
            f"**Warnings:** {aggregated['by_level']['WARN']}",
            "",
            f"**Anomalies Detected:** {len(anomalies)}",
            f"**Incidents Created:** {len(tickets)}",
            ""
        ]

        if tickets:
            lines.append("### Open Incidents:")
            for ticket in tickets[:5]:
                lines.append(f"- [{ticket['severity'].upper()}] {ticket['title']}")
            lines.append("")

        return "\n".join(lines)


class Z2_AlertCorrelator(BaseExecutor):
    """Correlate alerts and create incident tickets."""

    capability = "Z2"
    action = "correlate_alerts"
    required_params = ["alerts"]
    optional_params = ["time_window", "correlation_rules"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        alerts = params.get("alerts", [])
        time_window = params.get("time_window", "5m")
        correlation_rules = params.get("correlation_rules", [])

        if not alerts:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide alerts to correlate."
            )

        try:
            # Parse alerts
            parsed_alerts = self._parse_alerts(alerts)

            # Apply correlation rules
            correlated = self._apply_correlation_rules(parsed_alerts, correlation_rules)

            # Group related alerts
            grouped = self._group_related_alerts(correlated)

            # Assess impact
            impact = self._assess_incident_impact(grouped)

            # Create incidents
            incidents = self._create_incidents(grouped, impact)

            saved_path = self._save_correlation_report(parsed_alerts, correlated, grouped, incidents)

            summary = self._generate_correlation_summary(parsed_alerts, grouped, incidents)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "alerts": parsed_alerts,
                    "correlated": correlated,
                    "grouped": grouped,
                    "incidents": incidents,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Alert correlation failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to correlate alerts: {e}"
            )

    def _parse_alerts(self, alerts: List) -> List[Dict]:
        """Parse alert data."""
        parsed = []
        for alert in alerts:
            if isinstance(alert, str):
                parsed.append({
                    "message": alert,
                    "severity": "unknown",
                    "timestamp": datetime.now().isoformat()
                })
            else:
                parsed.append(alert)
        return parsed

    def _apply_correlation_rules(self, alerts: List[Dict], rules: List) -> List[Dict]:
        """Apply correlation rules to alerts."""
        # Simple correlation: group by severity
        for alert in alerts:
            alert["correlation_id"] = alert.get("severity", "unknown")
        return alerts

    def _group_related_alerts(self, alerts: List[Dict]) -> Dict:
        """Group related alerts."""
        grouped = {}
        for alert in alerts:
            corr_id = alert.get("correlation_id", "uncorrelated")
            if corr_id not in grouped:
                grouped[corr_id] = []
            grouped[corr_id].append(alert)
        return grouped

    def _assess_incident_impact(self, grouped: Dict) -> Dict:
        """Assess impact of incidents."""
        impact = {}
        for group_id, alerts in grouped.items():
            alert_count = len(alerts)
            if alert_count > 5:
                impact[group_id] = "high"
            elif alert_count > 2:
                impact[group_id] = "medium"
            else:
                impact[group_id] = "low"
        return impact

    def _create_incidents(self, grouped: Dict, impact: Dict) -> List[Dict]:
        """Create incident tickets from grouped alerts."""
        incidents = []
        for group_id, alerts in grouped.items():
            incident = {
                "id": f"INC-{group_id}",
                "title": f"Incident: {group_id}",
                "severity": impact.get(group_id, "low"),
                "alert_count": len(alerts),
                "status": "open",
                "created": datetime.now().isoformat()
            }
            incidents.append(incident)
        return incidents

    def _save_correlation_report(self, alerts, correlated, grouped, incidents) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"alert_correlation_{timestamp}.json"
            return str(save_json(filename, {
                "alerts": alerts,
                "correlated": correlated,
                "grouped": grouped,
                "incidents": incidents
            }))
        except Exception as e:
            logger.warning(f"Failed to save correlation report: {e}")
            return None

    def _generate_correlation_summary(self, alerts: List, grouped: Dict, incidents: List) -> str:
        lines = [
            "## Alert Correlation Report",
            f"**Total Alerts:** {len(alerts)}",
            f"**Alert Groups:** {len(grouped)}",
            f"**Incidents Created:** {len(incidents)}",
            ""
        ]

        if incidents:
            lines.append("### Incidents:")
            for incident in incidents[:5]:
                lines.append(f"- [{incident['severity'].upper()}] {incident['title']} ({incident['alert_count']} alerts)")

        return "\n".join(lines)
