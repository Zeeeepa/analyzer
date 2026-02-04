# API-to-WebChat Middleware Optimization Playbook

## 🎯 Purpose

This playbook provides step-by-step instructions for optimizing the API-to-WebChat middleware system. Follow this guide to improve throughput by 50-100%, reduce costs by 30%, and decrease error rates from 5% to <2%.

---

## 📋 Prerequisites

### System Requirements
- Node.js 18+ installed
- Python 3.8+ installed (optional, for advanced optimization)
- Access to production or staging environment
- Ability to generate synthetic load (100 req/s minimum)

### Access Requirements
- Write access to repository
- Deployment permissions for configuration changes
- Monitoring dashboard access

### Time Requirements
- **Quick Optimization:** 4-6 hours (single component)
- **Full Optimization:** 2-3 weeks (all components)
- **Ongoing Monitoring:** 1 hour/week

---

## Phase 1: Preparation (Day 1)

### Step 1.1: Install Iris

```bash
cd /path/to/analyzer
npm install @foxruv/iris@latest
```

**Expected Output:**
```
added 460 packages in 48s
```

**Verify Installation:**
```bash
npx iris --version
npx iris health
```

**Expected Health Check:**
```
✅ .iris/ folder present
✅ AgentDB installed
✅ Learning folder configured
✅ TypeScript DSPy available
```

---

### Step 1.2: Configure Environment

Create or update `.env`:

```bash
# Iris Configuration (Required)
PROJECT_ID=analyzer
IRIS_AUTO_INVOKE=true

# Optional: Enable Federated Learning
# FOXRUV_SUPABASE_URL=<provided_by_foxruv>
# FOXRUV_SUPABASE_SERVICE_ROLE_KEY=<provided_by_foxruv>

# Optional: Install Python Dependencies for Advanced Optimization
# Uncomment after running: pip install dspy-ai ax-platform
# ENABLE_DSPY=true
# ENABLE_AX=true
```

**Verify Configuration:**
```bash
npx iris config show
```

---

### Step 1.3: Enable Telemetry

```bash
npx iris telemetry enable
```

**What This Does:**
- Creates local SQLite database at `data/telemetry.db`
- Begins tracking all middleware operations
- Stores metrics for optimization analysis

**Verify Telemetry:**
```bash
npx iris telemetry status
```

**Expected Output:**
```
✅ Telemetry enabled
📊 Database: data/telemetry.db
📈 Metrics tracked: 0 (waiting for traffic)
```

---

### Step 1.4: Collect Baseline Metrics

**Run Production Traffic for 24-48 Hours**

During this period, the system will collect:
- Request latencies by component
- Format detection accuracy rates
- Endpoint selection patterns
- Scaling events and timing
- Error rates by type and stage

**Monitor Collection:**
```bash
# Check telemetry status every few hours
npx iris telemetry status

# View sample data
npx iris telemetry view --limit 10
```

**Minimum Data Requirements:**
- At least 10,000 requests processed
- All endpoint types exercised
- Representation of peak and off-peak traffic
- Examples of error conditions

---

## Phase 2: Discovery & Analysis (Day 2)

### Step 2.1: Discover AI Functions

```bash
npx iris discover Libraries/API
```

**Expected Output:**
```
🔍 IRIS Discovery - Scanning Libraries/API

📊 AI_FUNCTION (118 discovered)
  ⚠️  generate_fix_for_error (80% confidence)
  ⚠️  _generate_summary (80% confidence)
  ⚠️  generate_terminal_report (80% confidence)
  ... and 115 more

📈 Telemetry Coverage: 0% (0/118)
```

**Action Required:**
Review the list and identify which functions are part of the middleware system:
- Format detection functions
- Routing decision functions
- Scaling decision functions
- Error handling functions

---

### Step 2.2: Analyze Baseline Performance

```bash
npx iris evaluate
```

**Expected Output:**
```
📊 Project Health Report

Metrics Summary:
- Total Requests: 12,450
- Avg Latency: 450ms (P99: 5200ms)
- Error Rate: 5.2%
- Format Detection Accuracy: 84%

Optimization Opportunities:
1. API Gateway (format detection) - 20% improvement potential
2. Load Balancer (routing) - 15% improvement potential
3. Auto-Scaler (timing) - 30% improvement potential
```

**Document Baseline:**
Create a baseline report with:
- Current throughput (req/s)
- P50, P95, P99 latencies
- Error rate by type
- Cost per request
- Format detection accuracy

---

### Step 2.3: Identify Optimization Targets

**Review the optimization configuration:**
```bash
cat Libraries/API/iris-middleware-config.yaml
```

**Prioritize components based on:**
1. **Impact:** Which has the highest error rate or latency?
2. **Effort:** Which has the simplest optimization path?
3. **Risk:** Which has the lowest deployment risk?

**Recommended Order:**
1. API Gateway (format detection) - High impact, low risk
2. Response Processor - High impact, medium risk
3. Load Balancer - Medium impact, low risk
4. Auto-Scaler - High impact, high risk

---

## Phase 3: Single Component Optimization (Days 3-4)

### Step 3.1: Optimize API Gateway (Format Detection)

**Goal:** Improve format detection from 85% to 95%+ accuracy

**Review Configuration:**
```yaml
# In iris-middleware-config.yaml
targets:
  - name: "api_gateway"
    searchSpace:
      parameters:
        - name: "request_timeout"
          bounds: [1.0, 30.0]
        - name: "format_detection_confidence_threshold"
          bounds: [0.7, 0.99]

prompts:
  - name: "format_detection_prompt"
    initial: |
      Analyze the following API request and determine its format...
```

**Run Optimization:**
```bash
npx iris optimize \
  --config Libraries/API/iris-middleware-config.yaml \
  --target api_gateway \
  --strategy ax \
  --trials 30
```

**Expected Runtime:** 1-2 hours

**Monitor Progress:**
```bash
# In another terminal
tail -f .iris/logs/optimization.log
```

**Review Results:**
```bash
npx iris evaluate --component api_gateway
```

**Expected Output:**
```
🎉 Optimization Complete!

Best Configuration:
- request_timeout: 8.5s
- format_detection_confidence_threshold: 0.88

Performance Improvement:
- Accuracy: 84% → 93% (+9%)
- Latency: 50ms → 28ms (-44%)
- False Positives: 15% → 6% (-60%)

📁 Saved to: .iris/optimized/api_gateway.json
```

---

### Step 3.2: Validate Results

**A/B Test Setup:**

Update your middleware to read configuration from Iris:

```typescript
// Example: Load optimized configuration
import { loadOptimizedConfig } from '@foxruv/iris';

const config = await loadOptimizedConfig('api_gateway', {
  fallback: defaultConfig,
  abTestPercent: 10 // Start with 10% traffic
});
```

**Monitor A/B Test:**
```bash
npx iris telemetry compare \
  --variant baseline \
  --variant optimized \
  --duration 24h
```

**Decision Criteria:**
- ✅ Accuracy improvement >5%
- ✅ No latency regression >10%
- ✅ Error rate stable or improved
- ✅ No unexpected side effects

If all criteria met → Increase to 25% → 50% → 100%

---

### Step 3.3: Deploy Optimized Configuration

**Apply Configuration:**
```bash
# Update production configuration
npx iris deploy --component api_gateway --environment production
```

**Verify Deployment:**
```bash
# Check that new configuration is active
npx iris config show --component api_gateway --environment production
```

**Monitor Post-Deployment:**
```bash
# Watch metrics for 24 hours
npx iris telemetry watch --component api_gateway --duration 24h
```

---

## Phase 4: Multi-Component Optimization (Days 5-10)

### Step 4.1: Response Processor

**Goal:** Increase extraction success rate from 90% to 98%

```bash
npx iris optimize \
  --config Libraries/API/iris-middleware-config.yaml \
  --target response_processor \
  --strategy dspy \
  --examples training_data/response_processor.json
```

**Training Data Format:**
```json
[
  {
    "input": {
      "raw_response": "<html>...</html>",
      "target_format": "openai"
    },
    "output": {
      "normalized_response": "{...}",
      "extraction_method": "dom",
      "validation_errors": "none"
    }
  }
]
```

**Expected Runtime:** 2-3 hours

---

### Step 4.2: Load Balancer

**Goal:** Improve endpoint utilization from 60% to 85%

```bash
npx iris optimize \
  --config Libraries/API/iris-middleware-config.yaml \
  --target load_balancer \
  --strategy ax \
  --trials 40
```

**Expected Runtime:** 2-3 hours

---

### Step 4.3: Auto-Scaler

**Goal:** Reduce scale-up time from 5min to <2min

```bash
npx iris optimize \
  --config Libraries/API/iris-middleware-config.yaml \
  --target auto_scaler \
  --strategy ax \
  --trials 50
```

**⚠️ Important:** Auto-scaler changes are HIGH RISK. Use 5% A/B test initially.

**Expected Runtime:** 3-4 hours

---

## Phase 5: Prompt Optimization (Days 11-14)

### Step 5.1: Prepare Training Examples

For each AI component, collect 10-20 examples of:
- Input data
- Desired output
- Current output (if suboptimal)

**Example for Format Detection:**
```json
[
  {
    "input": {
      "request_body": "{\"messages\": [...], \"model\": \"gpt-4\"}",
      "request_headers": "{\"content-type\": \"application/json\"}"
    },
    "output": {
      "format": "openai",
      "confidence": 0.98,
      "reasoning": "Contains 'messages' array and 'model' field matching OpenAI spec"
    }
  }
]
```

**Save training data:**
```bash
mkdir -p training_data
# Create files: format_detection.json, capability_matching.json, etc.
```

---

### Step 5.2: Run DSPy Optimization

**Optimize all prompts:**
```bash
npx iris optimize \
  --config Libraries/API/iris-middleware-config.yaml \
  --strategy dspy \
  --examples training_data/ \
  --teleprompter MIPROv2 \
  --num-candidates 10
```

**Expected Runtime:** 4-6 hours

**Monitor Progress:**
- DSPy will generate 10 prompt candidates per component
- Each candidate is evaluated on validation set
- Best prompts are selected and saved

---

### Step 5.3: Review Optimized Prompts

```bash
# View optimized prompts
cat .iris/optimized/prompts/format_detection.txt
```

**Manual Review Checklist:**
- [ ] Prompt is clear and specific
- [ ] Instructions are actionable
- [ ] Examples are relevant
- [ ] No hallucination indicators
- [ ] Aligns with business logic

---

## Phase 6: System-Wide Validation (Days 15-17)

### Step 6.1: Integration Testing

**Create synthetic workload:**
```bash
npx iris test:synthetic \
  --duration 5min \
  --rps 100 \
  --config optimized
```

**Measure:**
- End-to-end latency
- Error rates
- Format detection accuracy
- Endpoint selection quality

**Compare to baseline:**
```bash
npx iris test:compare \
  --baseline baseline_results.json \
  --optimized optimized_results.json
```

---

### Step 6.2: Load Testing

**Stress test at 2x expected load:**
```bash
npx iris test:load \
  --duration 10min \
  --rps 200 \
  --config optimized
```

**Monitor for:**
- Memory leaks
- CPU spikes
- Connection pool exhaustion
- Database bottlenecks

---

### Step 6.3: Chaos Testing

**Test resilience:**
```bash
npx iris test:chaos \
  --scenario endpoint_failure \
  --config optimized
```

**Scenarios to test:**
- Endpoint failures (circuit breaker)
- Network latency spikes
- Database connection loss
- Rate limit violations

---

## Phase 7: Production Rollout (Days 18-21)

### Step 7.1: Deploy to Staging

```bash
npx iris deploy \
  --environment staging \
  --config optimized \
  --all-components
```

**Soak test for 48 hours:**
```bash
npx iris telemetry watch \
  --environment staging \
  --duration 48h \
  --alert-on-degradation
```

---

### Step 7.2: Production Canary (10%)

```bash
npx iris deploy \
  --environment production \
  --config optimized \
  --canary 10 \
  --all-components
```

**Monitor for 24 hours:**
- Primary metrics (throughput, latency, errors)
- Business metrics (conversion, revenue)
- Cost metrics (compute, API calls)

**Decision:** If metrics stable or improved → Proceed to 25%

---

### Step 7.3: Gradual Rollout

```bash
# Increase to 25%
npx iris deploy update --canary 25

# Wait 24h, monitor

# Increase to 50%
npx iris deploy update --canary 50

# Wait 24h, monitor

# Full rollout
npx iris deploy update --canary 100
```

---

### Step 7.4: Finalize Deployment

```bash
# Commit optimized configuration to repository
npx iris config export --output Libraries/API/optimized-config.yaml

# Update production deployment scripts
git add Libraries/API/optimized-config.yaml
git commit -m "Apply Iris optimization results

- API Gateway: 84% → 93% accuracy
- Load Balancer: 60% → 82% utilization
- Auto-Scaler: 5min → 1.8min scale-up
- Response Processor: 90% → 97% success rate

Total improvement:
- Throughput: +68%
- P99 Latency: 5200ms → 2800ms
- Error Rate: 5.2% → 1.8%
- Cost per request: -32%"
```

---

## Phase 8: Continuous Monitoring (Ongoing)

### Daily Monitoring

```bash
# Check for drift
npx iris health --check-drift
```

**Alert Thresholds:**
- Accuracy drop >5% → Warning
- Accuracy drop >15% → Critical (re-optimize)
- Latency increase >20% → Warning
- Error rate increase >50% → Critical

---

### Weekly Review

```bash
# Generate weekly report
npx iris report:weekly --email team@example.com
```

**Review:**
- Metrics vs targets
- Drift indicators
- Optimization opportunities
- Cost trends

---

### Monthly Optimization

```bash
# Identify worst-performing component
npx iris evaluate --rank-by improvement_potential

# Re-optimize top component
npx iris optimize --component <component> --incremental
```

---

## 🆘 Troubleshooting

### Optimization Not Improving Performance

**Possible Causes:**
1. Insufficient training data (<100 examples)
2. Search space too narrow
3. Evaluation metric misaligned with business goal

**Solutions:**
```bash
# Increase training data
npx iris data:generate --component api_gateway --count 500

# Widen search space
# Edit iris-middleware-config.yaml, increase bounds

# Re-run optimization
npx iris optimize --config updated-config.yaml
```

---

### Optimized Configuration Causes Regressions

**Immediate Action:**
```bash
# Rollback instantly
npx iris deploy rollback --environment production
```

**Root Cause Analysis:**
```bash
# Compare configurations
npx iris config diff --baseline production --optimized failed

# Review telemetry for anomalies
npx iris telemetry analyze --timerange rollback
```

---

### Telemetry Not Collecting Data

**Diagnosis:**
```bash
# Check telemetry status
npx iris telemetry status

# Check database
ls -lh data/telemetry.db

# Verify instrumentation
npx iris telemetry test
```

**Fix:**
```bash
# Re-enable telemetry
npx iris telemetry enable --force

# Restart application
```

---

## 📊 Success Criteria Checklist

### Component-Level Success

- [ ] **API Gateway**
  - [ ] Format detection accuracy >95%
  - [ ] Detection latency <30ms
  - [ ] False positive rate <5%

- [ ] **Load Balancer**
  - [ ] Endpoint utilization >80%
  - [ ] Failover time <1s
  - [ ] Cost per request reduced >20%

- [ ] **Auto-Scaler**
  - [ ] Scale-up response <2min
  - [ ] Over-provisioning reduced >30%
  - [ ] Cost savings >25%

- [ ] **Response Processor**
  - [ ] Extraction success >98%
  - [ ] Format accuracy >99%
  - [ ] P99 latency <3s

### System-Level Success

- [ ] **Performance**
  - [ ] Throughput increased >50%
  - [ ] P99 latency decreased >40%
  - [ ] Error rate <2%

- [ ] **Cost**
  - [ ] Cost per request reduced >30%
  - [ ] Infrastructure cost optimized
  - [ ] No unexpected cost spikes

- [ ] **Reliability**
  - [ ] No production incidents
  - [ ] Monitoring coverage >95%
  - [ ] Rollback procedures tested

---

## 📚 Reference Commands

```bash
# Installation
npm install @foxruv/iris@latest

# Configuration
npx iris config show
npx iris health

# Telemetry
npx iris telemetry enable
npx iris telemetry status
npx iris telemetry view --limit 100

# Discovery
npx iris discover Libraries/API

# Optimization
npx iris optimize --config iris-middleware-config.yaml
npx iris optimize --target api_gateway
npx iris optimize --strategy dspy --examples training_data/

# Evaluation
npx iris evaluate
npx iris evaluate --component api_gateway

# Deployment
npx iris deploy --environment production --canary 10
npx iris deploy update --canary 25
npx iris deploy rollback

# Monitoring
npx iris telemetry watch --duration 24h
npx iris health --check-drift
npx iris report:weekly
```

---

**Last Updated:** 2025-12-14  
**Version:** 1.0  
**Status:** Ready for Execution

