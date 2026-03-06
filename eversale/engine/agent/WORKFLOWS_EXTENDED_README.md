# Extended Workflows (P-AZ+) - Usage Guide

This document describes the 16 new industry-specific workflow families added to Eversale, extending the original A-O capabilities to cover 31+ industries total.

## Overview

The extended workflows follow the same natural language pattern as the core A-O workflows. Users simply describe what they want, and the agent routes to the appropriate specialized workflow.

## Architecture

```
User Prompt
    ↓
CapabilityRouter (detects P-AZ+ patterns)
    ↓
workflows_extended.py (specialized executors)
    ↓
Browser Automation + LLM Reasoning
    ↓
Structured Output (JSON/CSV)
```

## Extended Workflows

### P - Insurance

**Capabilities:**
- **P1**: Claims Processing - Parse claims, verify info, detect fraud
- **P2**: Policy Comparison - Compare policies across providers

**Example Prompts:**
```
"Process this insurance claim and check for fraud"
"Analyze auto accident claim #12345"
"Compare home insurance policies from top 3 providers"
"Get quotes for $250k life insurance coverage"
```

**Output:**
- Claim assessment with completeness score
- Fraud risk indicators
- Recommendation (approve/investigate/request_info)
- Policy comparison matrix with pricing

---

### Q - Banking

**Capabilities:**
- **Q1**: Account Monitoring - Detect fraud and anomalies
- **Q2**: Transaction Analysis - Pattern analysis and categorization (TBD)

**Example Prompts:**
```
"Monitor my bank account for unusual activity"
"Flag suspicious transactions from last 30 days"
"Analyze spending patterns and detect anomalies"
"Check these transactions for fraud indicators"
```

**Output:**
- Statistical anomaly detection
- Fraud alerts with risk scores
- Merchant verification (online reputation check)
- Action-required alerts

---

### R - Procurement

**Capabilities:**
- **R1**: Vendor Research - Find and compare suppliers
- **R2**: RFP Analysis - Analyze vendor proposals (TBD)

**Example Prompts:**
```
"Research vendors for office furniture"
"Find and compare cloud storage providers"
"Evaluate suppliers for manufacturing equipment"
"Compare prices for SaaS project management tools"
```

**Output:**
- Vendor profiles with reputation scores
- Website and description extraction
- Ranked vendor list
- Comparison matrix

---

### S - Enterprise Admin

**Capabilities:**
- **S1**: User Provisioning - Automate user account setup (TBD)
- **S2**: SaaS Auditing - Audit SaaS subscriptions and access (TBD)

**Example Prompts:**
```
"Audit user access across all SaaS apps"
"Generate compliance report for user permissions"
"List all users with admin access"
"Provision new employee accounts"
```

---

### T - Contractor

**Capabilities:**
- **T1**: Permit Research - Find permit requirements (TBD)
- **T2**: License Verification - Verify contractor licenses (TBD)

**Example Prompts:**
```
"Find permit requirements for commercial renovation in Austin TX"
"Verify contractor license #12345 in California"
"Research building codes for residential addition"
```

---

### U - Recruiting Pipeline

**Capabilities:**
- **U1**: Candidate Sourcing - Find candidates on GitHub, LinkedIn (TBD)
- **U2**: Interview Scheduling - Automate interview coordination (TBD)

**Example Prompts:**
```
"Source Python developers from GitHub with 5+ years experience"
"Find ML engineers in San Francisco area"
"Schedule interviews with qualified candidates"
```

---

### V - Audit & Compliance

**Capabilities:**
- **V1**: Compliance Checking - Verify regulatory compliance (TBD)
- **V2**: Evidence Gathering - Build audit trails (TBD)

**Example Prompts:**
```
"Check GDPR compliance for our website"
"Build audit trail for Q4 2024"
"Verify SOX compliance for financial processes"
```

---

### W - Content Moderation

**Capabilities:**
- **W1**: Content Review - Review flagged content (TBD)
- **W2**: Policy Enforcement - Apply content policies (TBD)

**Example Prompts:**
```
"Review flagged user content and apply policy"
"Process moderation queue for community posts"
"Classify content by violation type"
```

---

### X - Inventory Reconciliation

**Capabilities:**
- **X1**: Stock Monitoring - Track inventory levels (TBD)
- **X2**: Reorder Automation - Generate reorder alerts (TBD)

**Example Prompts:**
```
"Monitor stock levels and generate reorder alerts"
"Reconcile warehouse inventory with database"
"Check for low-stock items across all locations"
```

---

### Y - Research Automation

**Capabilities:**
- **Y1**: Literature Review - Gather and analyze papers (TBD)
- **Y2**: Citation Management - Extract citations (TBD)

**Example Prompts:**
```
"Review recent papers on quantum computing"
"Gather citations for literature review on AI ethics"
"Summarize top 10 papers on transformer models"
```

---

### Z - Enterprise Monitoring

**Capabilities:**
- **Z1**: Log Aggregation - Collect logs from multiple services (TBD)
- **Z2**: Alert Correlation - Connect related alerts (TBD)

**Example Prompts:**
```
"Aggregate logs from all microservices"
"Correlate alerts and create incident tickets"
"Monitor system health across production environment"
```

---

### AA - Healthcare

**Capabilities:**
- **AA1**: Patient Lookup - Verify patient information (TBD)
- **AA2**: Insurance Verification - Check coverage (TBD)

**Example Prompts:**
```
"Verify patient insurance coverage for procedure"
"Schedule follow-up appointments for discharged patients"
"Check eligibility for Medicare claims"
```

---

### AB - Travel Management

**Capabilities:**
- **AB1**: Flight Monitoring - Track prices and delays (TBD)
- **AB2**: Itinerary Building - Automated trip planning (TBD)

**Example Prompts:**
```
"Monitor flight prices to Tokyo for March"
"Build itinerary for business trip to NYC next week"
"Track flight status for AA123"
```

---

### AC - Food Service

**Capabilities:**
- **AC1**: Menu Aggregation - Collect menu data (TBD)
- **AC2**: Supplier Pricing - Compare food supplier prices (TBD)

**Example Prompts:**
```
"Aggregate menu items from supplier catalogs"
"Compare produce pricing across vendors"
"Track inventory for restaurant supplies"
```

---

### AD - Non-Profit

**Capabilities:**
- **AD1**: Grant Searching - Find matching grants (TBD)
- **AD2**: Donor Research - Research potential donors (TBD)

**Example Prompts:**
```
"Search for grants matching our education mission"
"Research potential donors in tech industry"
"Track fundraising campaign performance"
```

---

### AE - Media & PR

**Capabilities:**
- **AE1**: Press Monitoring - Track media mentions (TBD)
- **AE2**: Journalist Outreach - Find and contact journalists (TBD)

**Example Prompts:**
```
"Monitor press mentions of our company"
"Find journalists covering AI/ML topics"
"Track coverage for product launch"
```

---

## Implementation Status

### ✅ Fully Implemented

- **P1**: Insurance Claims Processing
- **P2**: Insurance Policy Comparison
- **Q1**: Banking Account Monitoring
- **R1**: Procurement Vendor Research

### 🚧 Template Ready (Implementation Pending)

- S (Enterprise Admin)
- T (Contractor)
- U (Recruiting)
- V (Audit & Compliance)
- W (Content Moderation)
- X (Inventory)
- Y (Research Automation)
- Z (Enterprise Monitoring)
- AA (Healthcare)
- AB (Travel)
- AC (Food Service)
- AD (Non-Profit)
- AE (Media & PR)

## How to Extend

To add a new workflow capability:

1. **Define the Executor** in `workflows_extended.py`:
```python
class S1_UserProvisioner(BaseExecutor):
    capability = "S1"
    action = "provision_user"
    required_params = ["user_info"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        # Implementation here
        pass
```

2. **Add to Registry** at bottom of `workflows_extended.py`:
```python
EXTENDED_WORKFLOW_EXECUTORS = {
    ...
    "S1": S1_UserProvisioner,
}
```

3. **Add Routing Patterns** in `capability_router.py`:
```python
'S': {
    'name': 'Enterprise Admin',
    'triggers': [
        r'provision\s+users?',
        r'audit\s+access',
    ],
    'keywords': ['enterprise', 'admin', 'provision'],
    'param_extractor': lambda p: {},
},
```

4. **Test with Natural Language**:
```bash
./eversale "Provision new user account for john@example.com"
```

## Integration with Planning Agent

Extended workflows can be composed into multi-step plans:

```python
from agent.planning_agent import PlanningAgent

agent = PlanningAgent()

# Create plan for comprehensive vendor evaluation
plan = await agent.plan(
    "Find vendors for cloud storage, compare pricing, and verify compliance",
    context={"budget": 10000, "requirements": ["SOC2", "HIPAA"]}
)

# Execute plan
result = await agent.execute_plan(plan)
```

The planning agent will:
1. Decompose into R1 (vendor research), V1 (compliance check)
2. Execute in parallel where possible
3. Aggregate results
4. Generate recommendations

## Workflow Templates

Create reusable templates for common workflows:

```python
from agent.planning_agent import PlanTemplate

# Insurance claim workflow template
claim_template = PlanTemplate(
    template_id="insurance_claim_processing",
    name="Full Claim Processing",
    category="insurance",
    required_params=["claim_data"],
    step_templates=[
        {
            "name": "Parse claim",
            "action": "P1",
            "arguments": {"claim_data": "${claim_data}"}
        },
        {
            "name": "Verify claimant",
            "action": "web_search",
            "depends_on": [0]
        },
        {
            "name": "Generate report",
            "action": "generate_report",
            "depends_on": [0, 1]
        }
    ]
)

claim_template.save()
```

## Error Handling

Extended workflows follow these error handling patterns:

1. **BLOCKED**: Login required
   ```
   "Please login to [service] in the browser, then say 'continue'"
   ```

2. **PARTIAL**: Some data collected, some failed
   ```
   "Collected 3 of 5 vendor quotes. 2 vendors unavailable."
   ```

3. **FAILED**: Complete failure
   ```
   "Failed to process claim: Invalid claim number format"
   ```

## Performance Optimization

Extended workflows support:

- **Parallel Execution**: Research multiple vendors simultaneously
- **Batch Processing**: Process multiple claims in one run
- **Caching**: Reuse vendor research within session
- **Rate Limiting**: Respect site-specific rate limits

## Data Privacy & Security

Extended workflows handle sensitive data:

- **PII Masking**: SSN, credit cards masked in logs
- **Secure Storage**: Encrypted at rest
- **HIPAA Compliance**: Healthcare workflows follow HIPAA guidelines
- **PCI Compliance**: Banking workflows avoid storing card data

## Monitoring & Observability

Track workflow performance:

```python
# View workflow statistics
stats = agent.get_workflow_stats("P1")

{
    "total_runs": 150,
    "success_rate": 0.94,
    "avg_duration_ms": 12500,
    "fraud_detected": 8
}
```

## Contributing

To contribute new workflows:

1. Follow the BaseExecutor pattern
2. Include comprehensive docstrings
3. Add 3+ example prompts
4. Implement error handling
5. Add unit tests
6. Update this README

## License

Same as Eversale main project.
