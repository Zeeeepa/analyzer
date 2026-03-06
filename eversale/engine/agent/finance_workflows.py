"""
Finance & Banking Workflows - Extracted from workflows_extended.py

Contains finance-focused workflow executors:
- P1_ClaimsProcessor: Insurance claims processing (Workflow P)
- P2_PolicyComparator: Insurance policy comparison
- Q1_AccountMonitor: Bank account monitoring (Workflow Q)
- Q2_FraudDetector: Transaction fraud detection

Reduces workflows_extended.py by ~985 lines.
"""

import asyncio
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger

from .executors.base import BaseExecutor, ActionResult, ActionStatus


# ============ P) INSURANCE ============

class P1_ClaimsProcessor(BaseExecutor):
    """Process insurance claims, verify details, and track status."""

    capability = "P1"
    action = "process_insurance_claim"
    required_params = ["claim_data"]
    optional_params = ["claim_type", "auto_verify"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        claim_data = params.get("claim_data", "")
        claim_type = params.get("claim_type", "general")
        auto_verify = params.get("auto_verify", True)

        if not claim_data:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide claim data to process."
            )

        try:
            # Parse claim details
            claim = self._parse_claim(claim_data)

            # Verify claimant info via web if browser available
            if auto_verify and self.browser and claim.get("claimant"):
                claim = await self._verify_claimant(claim)

            # Assess claim validity
            assessment = self._assess_claim(claim)

            # Check for fraud indicators
            fraud_check = self._check_fraud_indicators(claim)

            # Generate recommendation
            recommendation = self._generate_recommendation(claim, assessment, fraud_check)

            # Save results
            saved_path = self._save_results(claim, assessment, fraud_check, recommendation)

            summary = self._generate_summary(claim, assessment, recommendation)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "claim": claim,
                    "assessment": assessment,
                    "fraud_check": fraud_check,
                    "recommendation": recommendation,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Claims processing failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to process claim: {e}"
            )

    def _parse_claim(self, data: str) -> Dict:
        """Parse claim data."""
        claim = {"raw": data}

        # Extract claim number
        claim_num = re.search(r'claim\s*#?\s*:?\s*([A-Z0-9\-]+)', data, re.IGNORECASE)
        if claim_num:
            claim["claim_number"] = claim_num.group(1)

        # Extract claimant name
        name = re.search(r'claimant\s*:?\s*([A-Za-z\s]+)', data, re.IGNORECASE)
        if name:
            claim["claimant"] = name.group(1).strip()

        # Extract amount
        amount = re.search(r'\$[\d,]+(?:\.\d{2})?', data)
        if amount:
            claim["amount"] = amount.group(0)

        # Extract date
        date = re.search(r'(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})', data)
        if date:
            claim["date"] = date.group(1)

        # Extract incident type
        incident_keywords = {
            "auto": ["car", "vehicle", "auto", "collision", "accident"],
            "home": ["home", "property", "house", "damage", "theft"],
            "health": ["medical", "health", "hospital", "treatment"],
            "life": ["life", "death", "beneficiary"]
        }

        for incident_type, keywords in incident_keywords.items():
            if any(kw in data.lower() for kw in keywords):
                claim["incident_type"] = incident_type
                break

        return claim

    async def _verify_claimant(self, claim: Dict) -> Dict:
        """Verify claimant information online."""
        claimant = claim.get("claimant", "")
        try:
            await self.browser.navigate(f"https://www.google.com/search?q={claimant.replace(' ', '+')}")
            await asyncio.sleep(1)

            page_text = await self.browser.page.content()
            claim["claimant_verified"] = claimant.lower() in page_text.lower()
        except Exception as e:
            logger.debug(f"Failed to verify claimant: {e}")
            claim["claimant_verified"] = None

        return claim

    def _assess_claim(self, claim: Dict) -> Dict:
        """Assess claim validity and completeness."""
        assessment = {
            "completeness": 0.0,
            "issues": [],
            "missing_fields": []
        }

        required_fields = ["claim_number", "claimant", "amount", "date", "incident_type"]
        present_fields = sum(1 for f in required_fields if f in claim)
        assessment["completeness"] = present_fields / len(required_fields)

        for field in required_fields:
            if field not in claim:
                assessment["missing_fields"].append(field)

        # Check amount reasonableness
        if "amount" in claim:
            amount_str = claim["amount"].replace("$", "").replace(",", "")
            try:
                amount = float(amount_str)
                if amount > 100000:
                    assessment["issues"].append("High claim amount - requires review")
                elif amount < 0:
                    assessment["issues"].append("Invalid negative amount")
            except Exception as e:
                logger.debug(f"Failed to parse claim amount: {e}")
                assessment["issues"].append("Invalid amount format")

        return assessment

    def _check_fraud_indicators(self, claim: Dict) -> Dict:
        """Check for fraud indicators."""
        fraud_check = {
            "risk_level": "low",
            "indicators": [],
            "score": 0
        }

        # High amount claims
        if "amount" in claim:
            amount_str = claim["amount"].replace("$", "").replace(",", "")
            try:
                if float(amount_str) > 50000:
                    fraud_check["indicators"].append("High value claim")
                    fraud_check["score"] += 2
            except Exception as e:
                logger.debug(f"Failed to parse amount for fraud check: {e}")
                pass

        # Recent incident date
        if "date" in claim:
            if "2024" in claim["date"] or "2025" in claim["date"]:
                fraud_check["indicators"].append("Very recent incident")
                fraud_check["score"] += 1

        # Determine risk level
        if fraud_check["score"] >= 4:
            fraud_check["risk_level"] = "high"
        elif fraud_check["score"] >= 2:
            fraud_check["risk_level"] = "medium"

        return fraud_check

    def _generate_recommendation(self, claim: Dict, assessment: Dict, fraud_check: Dict) -> Dict:
        """Generate processing recommendation."""
        recommendation = {
            "action": "review",
            "priority": "medium",
            "reason": []
        }

        # Auto-approve low risk, complete claims
        if assessment["completeness"] == 1.0 and fraud_check["risk_level"] == "low":
            recommendation["action"] = "approve"
            recommendation["priority"] = "low"
            recommendation["reason"].append("Complete information, low risk")

        # Require manual review for high risk
        elif fraud_check["risk_level"] == "high":
            recommendation["action"] = "investigate"
            recommendation["priority"] = "high"
            recommendation["reason"].append("Fraud indicators detected")

        # Request more info if incomplete
        elif assessment["completeness"] < 0.8:
            recommendation["action"] = "request_info"
            recommendation["priority"] = "medium"
            recommendation["reason"].append(f"Missing: {', '.join(assessment['missing_fields'])}")

        return recommendation

    def _save_results(self, claim: Dict, assessment: Dict, fraud_check: Dict, recommendation: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"insurance_claim_{timestamp}.json"
            return str(save_json(filename, {
                "claim": claim,
                "assessment": assessment,
                "fraud_check": fraud_check,
                "recommendation": recommendation
            }))
        except Exception as e:
            logger.error(f"Failed to save claim processing report: {e}")
            return None

    def _generate_summary(self, claim: Dict, assessment: Dict, recommendation: Dict) -> str:
        lines = [
            "## Insurance Claim Processing",
            f"**Claim Number:** {claim.get('claim_number', 'N/A')}",
            f"**Claimant:** {claim.get('claimant', 'N/A')}",
            f"**Amount:** {claim.get('amount', 'N/A')}",
            f"**Type:** {claim.get('incident_type', 'N/A')}",
            "",
            f"**Completeness:** {assessment['completeness']*100:.0f}%",
            f"**Recommendation:** {recommendation['action'].upper()}",
            f"**Priority:** {recommendation['priority'].upper()}",
        ]

        if recommendation["reason"]:
            lines.append(f"\n**Reason:** {', '.join(recommendation['reason'])}")

        return "\n".join(lines)


class P2_PolicyComparator(BaseExecutor):
    """Compare insurance policies across providers."""

    capability = "P2"
    action = "compare_policies"
    required_params = ["policy_type"]
    optional_params = ["providers", "coverage_amount"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        policy_type = params.get("policy_type", "auto")
        providers = params.get("providers", ["geico", "progressive", "state_farm"])
        coverage_amount = params.get("coverage_amount", 100000)

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available for policy comparison"
            )

        try:
            quotes = []

            # Get quotes from each provider
            for provider in providers:
                quote = await self._get_provider_quote(provider, policy_type, coverage_amount)
                if quote:
                    quotes.append(quote)

            # Compare and rank
            comparison = self._compare_quotes(quotes)

            # Generate recommendation
            recommendation = self._recommend_policy(comparison)

            saved_path = self._save_comparison(quotes, comparison, recommendation)

            summary = self._generate_summary(quotes, recommendation)

            return ActionResult(
                status=ActionStatus.SUCCESS if quotes else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "quotes": quotes,
                    "comparison": comparison,
                    "recommendation": recommendation,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Policy comparison failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to compare policies: {e}"
            )

    async def _get_provider_quote(self, provider: str, policy_type: str, coverage: int) -> Optional[Dict]:
        """Get quote from insurance provider."""
        try:
            url = f"https://www.{provider}.com"
            await self.browser.navigate(url)
            await asyncio.sleep(2)

            quote = {
                "provider": provider,
                "policy_type": policy_type,
                "coverage": coverage,
                "monthly_premium": None,
                "deductible": None,
                "features": []
            }

            page_text = await self.browser.page.content()

            # Look for price patterns
            prices = re.findall(r'\$(\d+)(?:/mo|\/month)', page_text)
            if prices:
                quote["monthly_premium"] = f"${prices[0]}/mo"

            return quote
        except Exception as e:
            logger.warning(f"Failed to get quote from {provider}: {e}")
            return None

    def _compare_quotes(self, quotes: List[Dict]) -> Dict:
        """Compare quotes and calculate scores."""
        comparison = {
            "total_quotes": len(quotes),
            "by_provider": {},
            "best_value": None
        }

        for quote in quotes:
            provider = quote["provider"]
            comparison["by_provider"][provider] = quote

        return comparison

    def _recommend_policy(self, comparison: Dict) -> Dict:
        """Recommend best policy."""
        return {
            "recommended_provider": "Review quotes to determine best fit",
            "reason": "Compare coverage, premium, and deductible based on your needs",
            "next_steps": [
                "Review detailed coverage terms",
                "Check customer reviews",
                "Verify provider ratings"
            ]
        }

    def _save_comparison(self, quotes: List, comparison: Dict, recommendation: Dict) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"policy_comparison_{timestamp}.json"
            return str(save_json(filename, {
                "quotes": quotes,
                "comparison": comparison,
                "recommendation": recommendation
            }))
        except Exception as e:
            logger.error(f"Failed to save policy comparison: {e}")
            return None

    def _generate_summary(self, quotes: List, recommendation: Dict) -> str:
        lines = [
            "## Insurance Policy Comparison",
            f"**Quotes Collected:** {len(quotes)}",
            ""
        ]

        for quote in quotes:
            lines.append(f"### {quote['provider'].title()}")
            if quote.get("monthly_premium"):
                lines.append(f"- Premium: {quote['monthly_premium']}")
            lines.append("")

        lines.append(f"**Recommendation:** {recommendation.get('recommended_provider')}")

        return "\n".join(lines)


# ============ Q) BANKING ============

class Q1_AccountMonitor(BaseExecutor):
    """Monitor bank accounts for unusual activity and fraud."""

    capability = "Q1"
    action = "monitor_account"
    required_params = ["transactions"]
    optional_params = ["alert_threshold", "days_lookback"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        transactions = params.get("transactions", "")
        alert_threshold = params.get("alert_threshold", 1000)
        days_lookback = params.get("days_lookback", 30)

        if not transactions:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide transaction data to monitor."
            )

        try:
            # Parse transactions
            txns = self._parse_transactions(transactions)

            # Analyze patterns
            analysis = self._analyze_patterns(txns, alert_threshold)

            # Detect anomalies
            anomalies = self._detect_anomalies(txns)

            # Check for fraud indicators
            fraud_alerts = self._check_fraud(txns, anomalies)

            # Verify suspicious merchants if browser available
            if self.browser and fraud_alerts:
                fraud_alerts = await self._verify_merchants(fraud_alerts)

            # Generate alerts
            alerts = self._generate_alerts(fraud_alerts, anomalies)

            saved_path = self._save_monitoring_report(analysis, anomalies, fraud_alerts, alerts)

            summary = self._generate_summary(analysis, fraud_alerts, alerts)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "analysis": analysis,
                    "anomalies": anomalies,
                    "fraud_alerts": fraud_alerts,
                    "alerts": alerts,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Account monitoring failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to monitor account: {e}"
            )

    def _parse_transactions(self, data: str) -> List[Dict]:
        """Parse transaction data."""
        txns = []
        for line in data.split('\n'):
            if not line.strip():
                continue

            txn = {"raw": line}

            # Extract date
            date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})', line)
            if date_match:
                txn["date"] = date_match.group(1)

            # Extract amount
            amount_match = re.search(r'[-+]?\$?([\d,]+\.?\d*)', line)
            if amount_match:
                try:
                    txn["amount"] = float(amount_match.group(1).replace(',', ''))
                except Exception as e:
                    logger.debug(f"Failed to parse transaction amount: {e}")
                    pass

            # Extract merchant
            merchant_match = re.search(r'([A-Za-z][A-Za-z\s&]+?)(?:\s+\$|\s+\d)', line)
            if merchant_match:
                txn["merchant"] = merchant_match.group(1).strip()

            # Extract location if present
            location_match = re.search(r'([A-Z]{2})\s*$', line)
            if location_match:
                txn["location"] = location_match.group(1)

            txns.append(txn)

        return txns

    def _analyze_patterns(self, txns: List[Dict], threshold: float) -> Dict:
        """Analyze spending patterns."""
        analysis = {
            "total_transactions": len(txns),
            "total_spent": 0,
            "largest_transaction": 0,
            "avg_transaction": 0,
            "by_merchant": {},
            "by_location": {}
        }

        amounts = []
        for txn in txns:
            amount = txn.get("amount", 0)
            amounts.append(amount)
            analysis["total_spent"] += amount

            if amount > analysis["largest_transaction"]:
                analysis["largest_transaction"] = amount

            merchant = txn.get("merchant", "Unknown")
            analysis["by_merchant"][merchant] = analysis["by_merchant"].get(merchant, 0) + 1

            location = txn.get("location", "Unknown")
            analysis["by_location"][location] = analysis["by_location"].get(location, 0) + 1

        if amounts:
            analysis["avg_transaction"] = analysis["total_spent"] / len(amounts)

        return analysis

    def _detect_anomalies(self, txns: List[Dict]) -> List[Dict]:
        """Detect anomalous transactions."""
        anomalies = []

        amounts = [t.get("amount", 0) for t in txns if t.get("amount")]
        if not amounts:
            return anomalies

        avg = sum(amounts) / len(amounts)
        std = (sum((a - avg) ** 2 for a in amounts) / len(amounts)) ** 0.5

        for txn in txns:
            amount = txn.get("amount", 0)

            # Statistical anomaly
            if abs(amount - avg) > 2 * std:
                txn["anomaly_type"] = "statistical_outlier"
                anomalies.append(txn)

            # Duplicate transactions
            similar = [t for t in txns if
                      t.get("merchant") == txn.get("merchant") and
                      abs(t.get("amount", 0) - amount) < 1 and
                      t.get("date") == txn.get("date")]
            if len(similar) > 1:
                txn["anomaly_type"] = "possible_duplicate"
                if txn not in anomalies:
                    anomalies.append(txn)

        return anomalies

    def _check_fraud(self, txns: List[Dict], anomalies: List[Dict]) -> List[Dict]:
        """Check for fraud indicators."""
        fraud_alerts = []

        fraud_keywords = ['international', 'wire transfer', 'cash advance', 'atm withdrawal']

        for txn in txns:
            fraud_score = 0
            indicators = []

            # High amount
            if txn.get("amount", 0) > 500:
                fraud_score += 2
                indicators.append("High amount")

            # Unusual merchant
            merchant = txn.get("merchant", "").lower()
            if any(kw in merchant for kw in fraud_keywords):
                fraud_score += 1
                indicators.append("Risky merchant type")

            # Foreign location
            location = txn.get("location", "")
            if location and location not in ["US", "USA", ""]:
                fraud_score += 2
                indicators.append("Foreign transaction")

            if fraud_score >= 3:
                txn["fraud_score"] = fraud_score
                txn["fraud_indicators"] = indicators
                fraud_alerts.append(txn)

        return fraud_alerts

    async def _verify_merchants(self, fraud_alerts: List[Dict]) -> List[Dict]:
        """Verify suspicious merchants online."""
        for alert in fraud_alerts[:3]:
            merchant = alert.get("merchant", "")
            if merchant:
                try:
                    await self.browser.navigate(f"https://www.google.com/search?q={merchant.replace(' ', '+')}+scam+fraud")
                    await asyncio.sleep(1)

                    page_text = await self.browser.page.content()
                    alert["merchant_reputation"] = "suspicious" if "scam" in page_text.lower() or "fraud" in page_text.lower() else "clean"
                except Exception as e:
                    logger.debug(f"Failed to check merchant reputation: {e}")
                    pass

        return fraud_alerts

    def _generate_alerts(self, fraud_alerts: List[Dict], anomalies: List[Dict]) -> List[Dict]:
        """Generate user alerts."""
        alerts = []

        if fraud_alerts:
            alerts.append({
                "severity": "high",
                "type": "fraud",
                "message": f"{len(fraud_alerts)} potentially fraudulent transactions detected",
                "action_required": "Review and report if unauthorized"
            })

        if anomalies:
            alerts.append({
                "severity": "medium",
                "type": "anomaly",
                "message": f"{len(anomalies)} unusual transactions detected",
                "action_required": "Verify these transactions"
            })

        return alerts

    def _save_monitoring_report(self, analysis: Dict, anomalies: List, fraud_alerts: List, alerts: List) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"account_monitoring_{timestamp}.json"
            return str(save_json(filename, {
                "analysis": analysis,
                "anomalies": anomalies,
                "fraud_alerts": fraud_alerts,
                "alerts": alerts
            }))
        except Exception as e:
            logger.error(f"Failed to save account monitoring report: {e}")
            return None

    def _generate_summary(self, analysis: Dict, fraud_alerts: List, alerts: List) -> str:
        lines = [
            "## Account Monitoring Report",
            f"**Transactions Analyzed:** {analysis['total_transactions']}",
            f"**Total Spent:** ${abs(analysis['total_spent']):,.2f}",
            f"**Average Transaction:** ${abs(analysis['avg_transaction']):,.2f}",
            ""
        ]

        if fraud_alerts:
            lines.append(f"**FRAUD ALERTS:** {len(fraud_alerts)} suspicious transactions")
            for alert in fraud_alerts[:3]:
                lines.append(f"- {alert.get('merchant', 'Unknown')}: ${alert.get('amount', 0):.2f}")
            lines.append("")

        if alerts:
            lines.append("### Action Required:")
            for alert in alerts:
                lines.append(f"- [{alert['severity'].upper()}] {alert['message']}")

        return "\n".join(lines)


class Q2_FraudDetector(BaseExecutor):
    """Detect suspicious transactions and fraud patterns."""

    capability = "Q2"
    action = "detect_fraud"
    required_params = ["transactions"]
    optional_params = ["risk_threshold", "verify_online"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        transactions = params.get("transactions", "")
        risk_threshold = params.get("risk_threshold", 0.7)
        verify_online = params.get("verify_online", True)

        if not transactions:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide transaction data for fraud detection."
            )

        try:
            # Parse transactions
            txns = self._parse_transactions(transactions)

            # Score each transaction for fraud risk
            scored_txns = self._score_fraud_risk(txns)

            # Identify high-risk patterns
            patterns = self._identify_fraud_patterns(scored_txns)

            # Verify suspicious merchants online if browser available
            if verify_online and self.browser and patterns:
                patterns = await self._verify_merchants_online(patterns)

            # Generate fraud report
            report = self._generate_fraud_report(scored_txns, patterns, risk_threshold)

            # Create alerts for high-risk transactions
            alerts = self._create_fraud_alerts(scored_txns, patterns, risk_threshold)

            saved_path = self._save_fraud_report(scored_txns, patterns, alerts)

            summary = self._generate_summary(scored_txns, patterns, alerts, risk_threshold)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "transactions": scored_txns,
                    "patterns": patterns,
                    "report": report,
                    "alerts": alerts,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Fraud detection failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to detect fraud: {e}"
            )

    def _parse_transactions(self, data: str) -> List[Dict]:
        """Parse transaction data."""
        txns = []
        for line in data.split('\n'):
            if not line.strip():
                continue

            txn = {"raw": line}

            # Extract date
            date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})', line)
            if date_match:
                txn["date"] = date_match.group(1)

            # Extract amount
            amount_match = re.search(r'[-+]?\$?([\d,]+\.?\d*)', line)
            if amount_match:
                try:
                    txn["amount"] = float(amount_match.group(1).replace(',', ''))
                except Exception as e:
                    logger.debug(f"Failed to parse fraud detection transaction amount: {e}")
                    pass

            # Extract merchant
            merchant_match = re.search(r'([A-Za-z][A-Za-z\s&]+?)(?:\s+\$|\s+\d)', line)
            if merchant_match:
                txn["merchant"] = merchant_match.group(1).strip()

            # Extract location
            location_match = re.search(r'([A-Z]{2})\s*$', line)
            if location_match:
                txn["location"] = location_match.group(1)

            txns.append(txn)

        return txns

    def _score_fraud_risk(self, txns: List[Dict]) -> List[Dict]:
        """Score each transaction for fraud risk (0-1)."""
        scored = []

        # Calculate baseline statistics
        amounts = [t.get("amount", 0) for t in txns if t.get("amount")]
        avg_amount = sum(amounts) / len(amounts) if amounts else 0

        merchants_seen = {}
        locations_seen = {}

        for txn in txns:
            risk_score = 0.0
            risk_factors = []

            amount = txn.get("amount", 0)
            merchant = txn.get("merchant", "Unknown")
            location = txn.get("location", "")

            # Factor 1: Unusually large amount (0-0.3)
            if avg_amount > 0 and amount > avg_amount * 3:
                factor = min(0.3, (amount / (avg_amount * 3)) * 0.3)
                risk_score += factor
                risk_factors.append(f"Large amount (${amount:.2f})")

            # Factor 2: New/unknown merchant (0-0.2)
            if merchant not in merchants_seen:
                risk_score += 0.2
                risk_factors.append("New merchant")
            merchants_seen[merchant] = merchants_seen.get(merchant, 0) + 1

            # Factor 3: Foreign location (0-0.2)
            if location and location not in ["US", "CA", ""]:
                risk_score += 0.2
                risk_factors.append(f"Foreign location ({location})")

            # Factor 4: Round numbers (often fraud) (0-0.15)
            if amount > 0 and amount % 100 == 0:
                risk_score += 0.15
                risk_factors.append("Round amount")

            # Factor 5: Suspicious keywords (0-0.15)
            suspicious_keywords = ["bitcoin", "crypto", "wire", "transfer", "gift card"]
            if any(kw in merchant.lower() for kw in suspicious_keywords):
                risk_score += 0.15
                risk_factors.append("Suspicious merchant type")

            txn["fraud_risk_score"] = min(1.0, risk_score)
            txn["risk_factors"] = risk_factors
            scored.append(txn)

        return scored

    def _identify_fraud_patterns(self, txns: List[Dict]) -> List[Dict]:
        """Identify fraud patterns across transactions."""
        patterns = []

        # Pattern 1: Rapid sequence of transactions
        merchant_counts = {}
        for txn in txns:
            merchant = txn.get("merchant", "Unknown")
            merchant_counts[merchant] = merchant_counts.get(merchant, 0) + 1

        for merchant, count in merchant_counts.items():
            if count >= 3:
                patterns.append({
                    "type": "rapid_sequence",
                    "merchant": merchant,
                    "count": count,
                    "severity": "high" if count >= 5 else "medium"
                })

        # Pattern 2: Escalating amounts
        sorted_txns = sorted(txns, key=lambda t: t.get("date", ""))
        for i in range(len(sorted_txns) - 2):
            amounts = [sorted_txns[i].get("amount", 0),
                      sorted_txns[i+1].get("amount", 0),
                      sorted_txns[i+2].get("amount", 0)]
            if amounts[0] < amounts[1] < amounts[2] and amounts[2] > amounts[0] * 2:
                patterns.append({
                    "type": "escalating_amounts",
                    "amounts": amounts,
                    "severity": "high"
                })

        # Pattern 3: Geographic anomalies
        locations = [t.get("location", "") for t in txns if t.get("location")]
        if len(set(locations)) > 5:
            patterns.append({
                "type": "multiple_locations",
                "locations": list(set(locations)),
                "count": len(set(locations)),
                "severity": "medium"
            })

        return patterns

    async def _verify_merchants_online(self, patterns: List[Dict]) -> List[Dict]:
        """Verify suspicious merchants online."""
        for pattern in patterns:
            if pattern["type"] == "rapid_sequence":
                merchant = pattern.get("merchant")
                if merchant and self.browser:
                    try:
                        await self.browser.navigate(f"https://www.google.com/search?q={merchant}+scam+fraud")
                        await asyncio.sleep(2)
                        page_text = await self.browser.get_text("body")

                        if "scam" in page_text.lower() or "fraud" in page_text.lower():
                            pattern["verified_suspicious"] = True
                            pattern["severity"] = "critical"
                    except Exception as e:
                        logger.debug(f"Failed to verify suspicious pattern: {e}")
                        pass

        return patterns

    def _generate_fraud_report(self, txns: List[Dict], patterns: List[Dict], threshold: float) -> Dict:
        """Generate comprehensive fraud report."""
        high_risk = [t for t in txns if t.get("fraud_risk_score", 0) >= threshold]

        return {
            "total_transactions": len(txns),
            "high_risk_count": len(high_risk),
            "patterns_detected": len(patterns),
            "total_risk_exposure": sum(t.get("amount", 0) for t in high_risk),
            "risk_level": "CRITICAL" if len(high_risk) > 5 else "HIGH" if len(high_risk) > 2 else "MEDIUM"
        }

    def _create_fraud_alerts(self, txns: List[Dict], patterns: List[Dict], threshold: float) -> List[Dict]:
        """Create actionable fraud alerts."""
        alerts = []

        for txn in txns:
            if txn.get("fraud_risk_score", 0) >= threshold:
                alerts.append({
                    "type": "high_risk_transaction",
                    "merchant": txn.get("merchant", "Unknown"),
                    "amount": txn.get("amount", 0),
                    "risk_score": txn.get("fraud_risk_score", 0),
                    "factors": txn.get("risk_factors", []),
                    "action": "BLOCK" if txn.get("fraud_risk_score", 0) >= 0.9 else "REVIEW"
                })

        for pattern in patterns:
            if pattern.get("severity") in ["high", "critical"]:
                alerts.append({
                    "type": "fraud_pattern",
                    "pattern": pattern["type"],
                    "severity": pattern["severity"],
                    "action": "INVESTIGATE"
                })

        return alerts

    def _save_fraud_report(self, txns: List[Dict], patterns: List[Dict], alerts: List[Dict]) -> Optional[str]:
        try:
            from .output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"fraud_detection_{timestamp}.json"
            return str(save_json(filename, {
                "transactions": txns,
                "patterns": patterns,
                "alerts": alerts
            }))
        except Exception as e:
            logger.error(f"Failed to save fraud detection report: {e}")
            return None

    def _generate_summary(self, txns: List[Dict], patterns: List[Dict], alerts: List[Dict], threshold: float) -> str:
        high_risk = [t for t in txns if t.get("fraud_risk_score", 0) >= threshold]

        lines = [
            "## Fraud Detection Report",
            f"**Transactions Analyzed:** {len(txns)}",
            f"**High-Risk Transactions:** {len(high_risk)}",
            f"**Patterns Detected:** {len(patterns)}",
            f"**Total Alerts:** {len(alerts)}",
            ""
        ]

        if alerts:
            lines.append("### Critical Alerts:")
            for alert in alerts[:5]:
                if alert["type"] == "high_risk_transaction":
                    lines.append(f"[{alert['action']}] {alert['merchant']}: ${alert['amount']:.2f} (risk: {alert['risk_score']:.2f})")
                else:
                    lines.append(f"[{alert['severity'].upper()}] Pattern: {alert['pattern']}")

        return "\n".join(lines)


# ============ HELPER FUNCTIONS ============

def calculate_risk_score(transactions: List[Dict], weights: Dict[str, float] = None) -> float:
    """Calculate overall risk score for a set of transactions."""
    if weights is None:
        weights = {
            "amount": 0.3,
            "frequency": 0.2,
            "location": 0.2,
            "merchant": 0.3
        }

    total_score = 0.0

    if not transactions:
        return 0.0

    # Amount factor
    amounts = [t.get("amount", 0) for t in transactions]
    avg_amount = sum(amounts) / len(amounts) if amounts else 0
    high_amounts = sum(1 for a in amounts if a > avg_amount * 2)
    amount_score = min(1.0, high_amounts / len(transactions)) if transactions else 0
    total_score += amount_score * weights["amount"]

    # Frequency factor
    dates = [t.get("date", "") for t in transactions if t.get("date")]
    unique_dates = len(set(dates))
    freq_score = min(1.0, len(transactions) / (unique_dates + 1)) if unique_dates else 0
    total_score += freq_score * weights["frequency"]

    return min(1.0, total_score)


def generate_fraud_alert(transaction: Dict, risk_score: float) -> Dict:
    """Generate a standardized fraud alert from a transaction."""
    severity = "critical" if risk_score >= 0.9 else "high" if risk_score >= 0.7 else "medium"

    return {
        "timestamp": datetime.now().isoformat(),
        "transaction_id": transaction.get("id", "unknown"),
        "merchant": transaction.get("merchant", "Unknown"),
        "amount": transaction.get("amount", 0),
        "risk_score": risk_score,
        "severity": severity,
        "recommended_action": "BLOCK" if severity == "critical" else "REVIEW",
        "factors": transaction.get("risk_factors", [])
    }
