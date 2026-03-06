# Extended Workflows Integration Guide

This guide shows how the extended P-AZ+ workflows integrate with Eversale's existing systems.

## File Structure

```
agent/
├── workflows_extended.py          # New: P-AZ+ workflow executors
├── workflows_a_to_o.py            # Existing: A-O workflow executors
├── capability_router.py           # Updated: Now routes P-AZ+ patterns
├── planning_agent.py              # Compatible: Can compose extended workflows
├── workflows.py                   # Existing: Workflow engine
└── WORKFLOWS_EXTENDED_README.md   # New: Extended workflows documentation
```

## Integration Points

### 1. Capability Routing

The `CapabilityRouter` automatically detects extended workflow patterns:

```python
from agent.capability_router import route_to_capability

# User prompt with insurance keywords
result = route_to_capability("Process this insurance claim and check for fraud")

# Returns:
# CapabilityMatch(
#     capability='P',
#     capability_name='Insurance Claims & Policies',
#     confidence=0.8,
#     extracted_params={'claim_data': 'from_prompt'},
#     reasoning='Matched trigger: process.*claim; Keywords: insurance, claim'
# )
```

**Routing Patterns Added:**

| Capability | Trigger Patterns | Keywords |
|------------|-----------------|----------|
| P | `process.*claim`, `compare.*polic` | insurance, claim, policy, fraud |
| Q | `monitor.*account`, `check.*fraud` | bank, account, fraud, suspicious |
| R | `research.*vendors`, `find.*suppliers` | vendor, supplier, procurement |
| S-AE | (See capability_router.py) | ... |

### 2. Executor Registry

Extended executors follow the same pattern as A-O:

```python
# In workflows_extended.py
EXTENDED_WORKFLOW_EXECUTORS = {
    "P1": P1_ClaimsProcessor,
    "P2": P2_PolicyComparator,
    "Q1": Q1_AccountMonitor,
    "R1": R1_VendorResearcher,
    # ... more as implemented
}

# Get executor
from agent.workflows_extended import get_extended_workflow_executor

executor_class = get_extended_workflow_executor("P1")
if executor_class:
    executor = executor_class(browser=browser, context={})
    result = await executor.execute({"claim_data": "..."})
```

### 3. Planning Agent Integration

Extended workflows work with the Hierarchical Task Network planner:

```python
from agent.planning_agent import PlanningAgent, PlanTemplate

# Create a template that uses extended workflows
vendor_evaluation_template = PlanTemplate(
    template_id="vendor_eval_with_compliance",
    name="Vendor Evaluation + Compliance Check",
    category="procurement",
    required_params=["product_category"],
    step_templates=[
        {
            "template_id": 0,
            "name": "Research vendors",
            "task_type": "parallel",
            "action": "R1",  # Procurement workflow
            "arguments": {"product_category": "${product_category}"},
            "estimated_duration": 120.0
        },
        {
            "template_id": 1,
            "name": "Check compliance",
            "task_type": "sequential",
            "action": "V1",  # Audit & Compliance workflow (when implemented)
            "arguments": {"vendors": "${step_0.vendors}"},
            "depends_on": [0],
            "estimated_duration": 60.0
        }
    ]
)

# Use template
agent = PlanningAgent()
plan = vendor_evaluation_template.instantiate({
    "product_category": "cloud storage"
})

await agent.execute_plan(plan)
```

### 4. Workflow Engine Composition

Compose extended workflows into multi-step processes:

```python
from agent.workflows import Workflow, WorkflowEngine

# Create workflow using extended capabilities
insurance_workflow = Workflow(
    name="full_claim_review",
    description="Process claim and compare coverage"
)

insurance_workflow.add(
    name="process_claim",
    capability="P1",
    action="process_insurance_claim",
    params={"claim_data": "$claim_data"}
)

insurance_workflow.add(
    name="compare_policies",
    capability="P2",
    action="compare_policies",
    params={"policy_type": "$process_claim.incident_type"},
    depends_on=["process_claim"],
    condition="process_claim.recommendation.action == 'approve'"
)

# Execute
engine = WorkflowEngine(browser=browser)
result = await engine.run(insurance_workflow, {
    "claim_data": "Claim #12345: auto accident..."
})
```

### 5. ReAct Loop Integration

Extended workflows are available as ReAct actions:

```python
# In agent/react_loop.py (conceptual)

class ExtendedActionsReActLoop:
    def __init__(self):
        self.actions = {
            **BASE_ACTIONS,
            **EXTENDED_ACTIONS  # From workflows_extended.py
        }

    async def execute_action(self, action: str, params: Dict):
        if action.startswith(("P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA", "AB", "AC", "AD", "AE")):
            # Route to extended workflow
            executor = get_extended_workflow_executor(action)
            return await executor(browser=self.browser).execute(params)
        else:
            # Route to standard action
            return await self.execute_standard_action(action, params)
```

## Usage Examples

### Example 1: Simple Extended Workflow

```python
# Direct executor usage
from agent.workflows_extended import P1_ClaimsProcessor

processor = P1_ClaimsProcessor(browser=browser)
result = await processor.execute({
    "claim_data": """
        Claim #12345
        Claimant: John Doe
        Amount: $5,000
        Date: 2024-12-01
        Type: Auto accident
    """,
    "auto_verify": True
})

print(result.message)  # Formatted summary
print(result.data["recommendation"])  # Action needed
```

### Example 2: Through Capability Router

```python
from agent.capability_router import route_to_capability
from agent.workflows_extended import get_extended_workflow_executor

# User types natural language
prompt = "Monitor my bank account for unusual activity"

# Route to appropriate workflow
match = route_to_capability(prompt)

if match and match.capability.startswith(("P", "Q", "R")):  # Extended workflows
    executor_class = get_extended_workflow_executor(match.capability + "1")
    executor = executor_class(browser=browser)

    result = await executor.execute({
        **match.extracted_params,
        "transactions": get_transaction_data()
    })
```

### Example 3: Composed Workflow

```python
from agent.workflows import Workflow, WorkflowEngine

# Multi-industry workflow
vendor_onboarding = Workflow(
    name="vendor_onboarding",
    description="Research vendor, check compliance, provision access"
)

vendor_onboarding.add(
    name="research",
    capability="R1",
    action="research_vendors",
    params={"product_category": "payment processing"}
)

vendor_onboarding.add(
    name="compliance_check",
    capability="V1",  # When implemented
    action="check_compliance",
    params={"vendor": "$research.ranked[0]", "requirements": ["PCI-DSS"]},
    depends_on=["research"]
)

vendor_onboarding.add(
    name="provision",
    capability="S1",  # When implemented
    action="provision_vendor_access",
    params={"vendor": "$research.ranked[0]"},
    depends_on=["compliance_check"],
    condition="compliance_check.compliant == True"
)

engine = WorkflowEngine(browser=browser)
result = await engine.run(vendor_onboarding)
```

## Migration Path for A-O Workflows

Existing A-O workflows continue to work unchanged:

```python
# Old code still works
from agent.executors.workflows_a_to_o import D1_CompanyResearch

executor = D1_CompanyResearch(browser=browser)
result = await executor.execute({"company": "Stripe"})
```

New code can mix A-O and P-AZ+:

```python
workflow = Workflow("sdr_with_compliance")

# A-O workflow
workflow.add(name="research", capability="D1", action="research_company", ...)

# P-AZ+ workflow
workflow.add(name="verify", capability="Q1", action="monitor_account", ...)
```

## Adding New Extended Workflows

### Step 1: Create Executor Class

```python
# In workflows_extended.py

class S1_UserProvisioner(BaseExecutor):
    """Provision user accounts across SaaS platforms."""

    capability = "S1"
    action = "provision_user"
    required_params = ["user_info"]
    optional_params = ["platforms"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        user_info = params.get("user_info")
        platforms = params.get("platforms", ["github", "slack", "gsuite"])

        try:
            results = []

            for platform in platforms:
                result = await self._provision_on_platform(platform, user_info)
                results.append(result)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"results": results},
                message=f"Provisioned user on {len(results)} platforms"
            )
        except Exception as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Provisioning failed: {e}"
            )

    async def _provision_on_platform(self, platform: str, user_info: Dict) -> Dict:
        # Implementation
        if platform == "github":
            await self.browser.navigate("https://github.com/orgs/YOUR_ORG/people")
            # ... create user
        # ...
        return {"platform": platform, "status": "success"}
```

### Step 2: Register Executor

```python
# In workflows_extended.py

EXTENDED_WORKFLOW_EXECUTORS = {
    # ... existing
    "S1": S1_UserProvisioner,
}
```

### Step 3: Add Routing Patterns

```python
# In capability_router.py

CAPABILITY_PATTERNS = {
    # ... existing
    'S': {
        'name': 'Enterprise Admin & SaaS Management',
        'triggers': [
            r'provision\s+users?',
            r'create\s+(?:user\s+)?accounts?',
            r'add\s+users?\s+to',
        ],
        'keywords': ['provision', 'user', 'account', 'saas', 'enterprise'],
        'param_extractor': lambda p: {'user_info': 'from_prompt'},
    },
}
```

### Step 4: Test

```python
# Test direct execution
from agent.workflows_extended import S1_UserProvisioner

provisioner = S1_UserProvisioner(browser=browser)
result = await provisioner.execute({
    "user_info": {
        "name": "John Doe",
        "email": "john@example.com",
        "role": "developer"
    },
    "platforms": ["github", "slack"]
})

# Test via routing
from agent.capability_router import route_to_capability

match = route_to_capability("Provision new user john@example.com")
assert match.capability == "S"
```

## Testing Extended Workflows

```python
import pytest
from agent.workflows_extended import P1_ClaimsProcessor

@pytest.mark.asyncio
async def test_claims_processing():
    processor = P1_ClaimsProcessor(browser=None)  # No browser for unit test

    result = await processor.execute({
        "claim_data": "Claim #123: $1000 damage",
        "auto_verify": False
    })

    assert result.status == ActionStatus.SUCCESS
    assert "claim_number" in result.data["claim"]
    assert "recommendation" in result.data
```

## Performance Considerations

Extended workflows support:

1. **Parallel Execution**: Multiple vendors researched simultaneously
2. **Batch Processing**: Process 100 claims in one pass
3. **Caching**: Cache vendor lookups for 1 hour
4. **Rate Limiting**: Respect per-domain rate limits

```python
# Parallel vendor research
from agent.parallel import BatchProcessor

processor = BatchProcessor(
    executor_class=R1_VendorResearcher,
    max_concurrent=5
)

results = await processor.process_batch([
    {"product_category": "cloud storage"},
    {"product_category": "crm software"},
    {"product_category": "accounting tools"},
])
```

## Monitoring & Observability

Track extended workflow usage:

```python
from agent.workflows_extended import EXTENDED_WORKFLOW_EXECUTORS

# Get statistics
stats = {}
for capability, executor_class in EXTENDED_WORKFLOW_EXECUTORS.items():
    stats[capability] = {
        "name": executor_class.__name__,
        "runs": executor_class.execution_count if hasattr(executor_class, 'execution_count') else 0
    }
```

## Future Extensions

Planned extended workflows (AF-ZZ):

- **AF**: Legal Discovery - Document review automation
- **AG**: Medical Coding - ICD/CPT code extraction
- **AH**: Supply Chain - Logistics optimization
- **AI**: Quality Assurance - Automated testing
- ... (24+ more industries)

## Support

For questions or issues with extended workflows:

1. Check `WORKFLOWS_EXTENDED_README.md` for detailed workflow documentation
2. Review example prompts in `workflows_extended.py`
3. Test routing with `capability_router.py`
4. Examine planning integration in `planning_agent.py`
