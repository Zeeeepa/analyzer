# API-to-WebChat Middleware Optimization Strategy

## 🎯 Overview

This document outlines the optimization strategy for the universal API-to-WebChat middleware system using @foxruv/iris. The middleware converts any API format (OpenAI, Anthropic, Gemini, Custom) to web chat interactions and back, with intelligent routing, scaling, and processing.

---

## 📊 System Components Requiring Optimization

### 1. API Gateway - Format Detection & Conversion

**Current Challenge:**
- Manual format detection rules with ~85% accuracy
- Fixed timeout values causing either latency or failures
- One-size-fits-all batch processing

**Optimization Targets:**

| Parameter | Current | Target | Impact |
|-----------|---------|--------|--------|
| `request_timeout` | 5s fixed | 1-30s optimized | -60% timeout errors |
| `batch_size` | 10 fixed | 1-100 optimized | +40% throughput |
| `format_confidence_threshold` | 0.8 | 0.7-0.99 | +10% accuracy |

**AI Components to Optimize:**
- **Format Detection Prompt:** Identify API format from request structure
- **Format Conversion Logic:** Transform between API formats

**Expected Improvements:**
- Detection accuracy: 85% → 95%+
- Detection latency: 50ms → 20ms
- False positive rate: 15% → 5%

---

### 2. Load Balancer - Intelligent Routing

**Current Challenge:**
- Simple round-robin routing ignores endpoint capabilities
- Static health check intervals waste resources
- Circuit breaker thresholds too aggressive or too lenient
- Priority routing not optimized for cost/performance balance

**Optimization Targets:**

| Parameter | Current | Target | Impact |
|-----------|---------|--------|--------|
| `health_check_interval` | 30s fixed | 10-120s | -50% overhead |
| `circuit_breaker_failures` | 5 fixed | 3-20 | Better resilience |
| `circuit_breaker_timeout` | 60s fixed | 30-300s | Faster recovery |
| `priority_weight_multiplier` | 2.0 fixed | 1.0-5.0 | +30% efficiency |
| `session_affinity_ttl` | 30min fixed | 5-60min | Better stickiness |

**AI Components to Optimize:**
- **Capability Matching Prompt:** Match request requirements to best endpoint
- **Load Balancing Decision Logic:** Route based on current system state
- **Cost Optimization Logic:** Balance cost vs performance tradeoffs

**Expected Improvements:**
- Request distribution: +30% better utilization
- Endpoint utilization: 60% → 85%
- Failover time: 2s → <1s
- Cost per request: -20%

---

### 3. Auto-Scaler - Dynamic Resource Allocation

**Current Challenge:**
- Reactive scaling causes under/over-provisioning
- Fixed thresholds don't account for traffic patterns
- Cooldown periods either too short (thrashing) or too long (waste)
- No predictive scaling based on time-of-day patterns

**Optimization Targets:**

| Parameter | Current | Target | Impact |
|-----------|---------|--------|--------|
| `scale_up_threshold` | 80% fixed | 60-90% | Faster response |
| `scale_down_threshold` | 20% fixed | 10-40% | Less waste |
| `cooldown_minutes` | 5 fixed | 1-10 | Better adaptation |
| `min_instances` | 2 fixed | 1-5 | Cost savings |
| `max_instances` | 50 fixed | 10-200 | Burst capacity |

**AI Components to Optimize:**
- **Scaling Decision Prompt:** When to scale up/down/maintain
- **Predictive Scaling Logic:** Anticipate load based on patterns
- **Cost-Aware Scaling:** Consider budget constraints

**Expected Improvements:**
- Scale-up response time: 5min → <2min
- Over-provisioning: -40%
- Under-provisioning events: -70%
- Cost savings: 20-30%

---

### 4. Response Processor - Extraction & Normalization

**Current Challenge:**
- Single extraction method (DOM) fails on dynamic sites
- Fixed retry logic doesn't adapt to failure types
- Format conversion has blind spots for edge cases

**Optimization Targets:**

| Parameter | Current | Target | Impact |
|-----------|---------|--------|--------|
| `extraction_timeout` | 5s fixed | 1-15s | +15% success |
| `retry_attempts` | 3 fixed | 1-5 | Better reliability |
| `retry_backoff` | 2x fixed | 1.5-3.0x | Optimized timing |

**AI Components to Optimize:**
- **Response Normalization Prompt:** Convert web responses to API format
- **Tool Call Mapping Logic:** Map API tools to web interface actions
- **Extraction Method Selection:** Choose DOM/Network/Vision/Text based on context

**Expected Improvements:**
- Extraction success rate: 90% → 98%
- Format conversion accuracy: 95% → 99%+
- P99 latency: 5s → <3s

---

### 5. Error Handler - Diagnosis & Recovery

**Current Challenge:**
- Generic error messages don't help debugging
- No intelligent retry decisions
- Missing alternate endpoint selection logic

**AI Components to Optimize:**
- **Error Diagnosis Prompt:** Identify root cause and suggest fixes
- **Retry Decision Logic:** When to retry vs failover
- **Alternate Endpoint Selection:** Choose best fallback option

**Expected Improvements:**
- First-attempt resolution: 60% → 85%
- Manual intervention needed: -60%
- Mean time to recovery: -50%

---

## 🧠 Optimization Approaches

### Approach 1: Bayesian Optimization (Ax Platform)

**Best For:** Numeric parameters with expensive evaluations

**Components:**
- API Gateway timeouts and thresholds
- Load Balancer routing weights
- Auto-Scaler thresholds and limits
- Response Processor timing parameters

**Configuration:**
```yaml
strategy: ['ax', 'grid']
trials: 50
initialization_trials: 10
```

**Expected Time:** 2-4 hours with synthetic workload

---

### Approach 2: Prompt Optimization (DSPy + MIPROv2)

**Best For:** AI decision-making components

**Components:**
- Format detection reasoning
- Capability matching logic
- Error diagnosis explanations
- Scaling decision rationale

**Configuration:**
```yaml
strategy: ['dspy', 'grid']
num_candidates: 10
teacher_model: "gpt-4"
student_model: "gpt-3.5-turbo"
```

**Expected Time:** 4-6 hours with training examples

---

### Approach 3: Combined Optimization

**Best For:** Full system optimization

**Workflow:**
1. **Phase 1 (Week 1):** Collect 24-48h of production telemetry
2. **Phase 2 (Week 1):** Run Bayesian optimization on numeric parameters
3. **Phase 3 (Week 2):** Run prompt optimization on AI components
4. **Phase 4 (Week 2):** A/B test optimized vs baseline (10% traffic split)
5. **Phase 5 (Week 3):** Full rollout with monitoring

**Configuration:**
```yaml
strategy: ['ax', 'dspy', 'grid']
```

**Expected Time:** 3 weeks (1 week active work, 2 weeks monitoring)

---

## 📈 Success Metrics

### Primary Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| **Throughput** | 100 req/s | 150-200 req/s | Load testing |
| **P99 Latency** | 5000ms | <3000ms | APM tooling |
| **Error Rate** | 5% | <2% | Error logs |
| **Cost per Request** | $0.001 | $0.0007 | Billing data |

### Secondary Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Format Detection Accuracy | 85% | >95% | Manual validation |
| Endpoint Utilization | 60% | >80% | Monitoring |
| Auto-Scale Response Time | 5min | <2min | System logs |
| First-Attempt Success Rate | 90% | >98% | Request tracking |

### Drift Metrics

| Metric | Threshold | Action |
|--------|-----------|--------|
| Accuracy Degradation | >15% drop | Re-optimize prompts |
| Latency Increase | >20% increase | Re-tune parameters |
| Cost Increase | >10% increase | Review routing logic |

---

## 🔄 Continuous Optimization Workflow

### Weekly
- Review AgentDB telemetry for drift indicators
- Check primary metrics against targets
- Adjust traffic splits if A/B testing

### Monthly
- Run incremental optimization on worst-performing component
- Update training data with recent examples
- Review and update success criteria

### Quarterly
- Full system re-optimization
- Evaluate new optimization strategies (newer DSPy versions, etc.)
- Update baseline metrics

---

## 🛠️ Tools & Infrastructure

### Required Tools

| Tool | Purpose | Installation |
|------|---------|--------------|
| **@foxruv/iris** | Optimization orchestration | `npm install @foxruv/iris@latest` |
| **AgentDB** | Telemetry tracking | Auto-installed with Iris |
| **DSPy** (optional) | Prompt optimization | `pip install dspy-ai` |
| **Ax Platform** (optional) | Bayesian optimization | `pip install ax-platform` |

### Configuration Files

```
Libraries/API/
├── iris-middleware-config.yaml       # Optimization configuration
├── dspy_signatures.py                # AI component signatures
├── OPTIMIZATION_STRATEGY.md          # This document
└── OPTIMIZATION_PLAYBOOK.md          # Step-by-step execution guide
```

### Telemetry Setup

**Minimal (.env):**
```bash
PROJECT_ID=analyzer
IRIS_AUTO_INVOKE=true
```

**Enable Tracking:**
```bash
npx iris telemetry enable
```

**Data Collected:**
- Request latency per component
- Format detection accuracy
- Endpoint selection success rates
- Scaling events and timing
- Error rates by type

---

## 🚨 Important Considerations

### Before Starting Optimization

1. **Baseline Measurement:** Run system for 24-48h to collect baseline metrics
2. **Synthetic Workload:** Prepare realistic test workload (100 req/s, 5min duration)
3. **Rollback Plan:** Ensure quick rollback to current configuration
4. **Monitoring:** Set up dashboards to track optimization impact

### During Optimization

1. **Isolation:** Optimize one component at a time initially
2. **Validation:** Validate improvements with synthetic workload before production
3. **Documentation:** Record all configuration changes and results
4. **Checkpoints:** Save intermediate results after each optimization phase

### After Optimization

1. **A/B Testing:** Start with 10% traffic to optimized configuration
2. **Monitoring:** Watch for unexpected side effects
3. **Gradual Rollout:** Increase traffic gradually (10% → 25% → 50% → 100%)
4. **Documentation:** Update runbooks with new optimal configurations

---

## 📚 Related Documentation

- **OPTIMIZATION_PLAYBOOK.md** - Step-by-step execution guide
- **REQUIREMENTS.md** - Full system requirements and success criteria
- **REPOS.md** - Repository analysis and implementation gaps
- **.iris/learning/skills/optimization.md** - Iris optimization skill
- **IRIS_QUICKSTART.md** - Quick start guide for Iris

---

## 🎯 Next Steps

1. **Read this document thoroughly** to understand optimization strategy
2. **Review OPTIMIZATION_PLAYBOOK.md** for step-by-step execution
3. **Set up telemetry** as documented above
4. **Collect baseline metrics** for 24-48 hours
5. **Start with single component** (recommend: API Gateway format detection)
6. **Expand systematically** to other components

---

**Last Updated:** 2025-12-14  
**Version:** 1.0  
**Status:** Draft - Ready for Review

