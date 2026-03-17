# Planner - Multi-Step Lookahead Planning

## Overview

The Planner module implements tree-based planning that thinks multiple steps ahead before acting. Instead of reactive "next action" thinking, it builds a tree of possible futures, simulates them, and picks the best path.

**File**: `/mnt/c/ev29/agent/planner.py` (1,218 lines, 40KB)

## Key Features

1. **Tree Expansion**: Explores multiple possible action sequences
2. **Outcome Simulation**: Predicts results using world knowledge
3. **Path Scoring**: Rates paths by success probability + mission alignment + efficiency
4. **Early Pruning**: Cuts bad branches to save compute
5. **Replanning**: Adapts when reality diverges from prediction
6. **Depth Control**: Configurable lookahead (3-5 steps default)
7. **Contingency Planning**: Backup plans for risky steps
8. **Plan Caching**: Reuses plans for similar situations
9. **Event Integration**: Publishes/subscribes via EventBus
10. **Persistence**: Saves plans to SQLite database

## Architecture

```
Goal + Current State
        ↓
    Tree Expansion (breadth-first, max depth 5-10)
        ↓
    Multiple Paths (up to 5 branches per node)
        ↓
    Simulation (predict outcomes using world model)
        ↓
    Scoring (success × alignment × efficiency)
        ↓
    Pruning (cut paths <20% score)
        ↓
    Best Plan Selection
        ↓
    Contingency Generation (for risky steps)
        ↓
    Execution + Replanning (on surprises)
```

## Data Structures

### PlannedAction
```python
@dataclass
class PlannedAction:
    action_type: str              # "navigate", "click", "extract", etc.
    parameters: Dict[str, Any]    # Action-specific parameters
    expected_duration: float      # Estimated seconds
    success_probability: float    # Predicted success rate (0-1)
    status: ActionStatus          # planned/in_progress/completed/failed
```

### PredictedOutcome
```python
@dataclass
class PredictedOutcome:
    success_probability: float    # Overall probability of success
    expected_results: Dict        # What we expect to achieve
    confidence: float             # How confident in prediction
    failure_modes: List[str]      # Potential ways this could fail
    resource_cost: float          # Estimated tokens/time
```

### ActionPlan
```python
@dataclass
class ActionPlan:
    plan_id: str                  # Unique identifier
    goal: str                     # What we're trying to achieve
    steps: List[PlannedAction]    # Sequence of actions
    expected_outcome: PredictedOutcome
    confidence: float             # Overall confidence
    score: float                  # Overall score (higher = better)
    contingencies: Dict[str, ActionPlan]  # Backup plans
```

### PlanTree
```python
@dataclass
class PlanTree:
    root: PlanNode               # Starting state
    goal: str                    # What we're trying to achieve
    max_depth: int               # Maximum lookahead
    nodes: Dict[str, PlanNode]   # All nodes in tree
```

## Usage Examples

### Basic Planning

```python
from agent.planner import Planner
from agent.organism_core import EventBus
from agent.llm_client import LLMClient

# Initialize
event_bus = EventBus()
llm_client = LLMClient(config)
planner = Planner(
    event_bus=event_bus,
    llm_client=llm_client,
    mission_goal="Complete tasks efficiently",
)

# Create plan
plan = await planner.plan(
    goal="Find Python books on books.toscrape.com",
    current_state="Browser ready, no page loaded",
    depth=5,
    context={"tools": ["navigate", "search", "extract"]},
)

print(f"Plan: {plan.plan_id}")
print(f"Steps: {len(plan.steps)}")
print(f"Confidence: {plan.confidence:.2f}")

for i, action in enumerate(plan.steps):
    print(f"{i+1}. {action.action_type}({action.parameters})")
```

### Execution with Replanning

```python
# Set as active plan
planner.active_plan = plan

# Execute steps
for action in plan.steps:
    try:
        # Execute action
        result = await execute_action(action)

        # Publish success event
        await event_bus.publish(OrganismEvent(
            event_type=EventType.ACTION_COMPLETE,
            source="executor",
            data={"action": action.action_type, "result": result}
        ))

    except Exception as e:
        # Action failed - trigger replan
        new_plan = await planner.replan(
            new_observation=f"Action failed: {e}",
            current_plan=plan,
        )
        plan = new_plan  # Switch to new plan
```

### Tree Expansion (Advanced)

```python
# Manually expand planning tree
tree = await planner.expand_tree(
    goal="Extract contact info from website",
    current_state="On homepage",
    depth=3,
    context={"tools": ["click", "extract", "scroll"]},
)

print(f"Tree nodes: {len(tree.nodes)}")
print(f"Leaf nodes: {len(tree.get_leaf_nodes())}")

# Get best path
best_path = tree.get_best_path()
for action in best_path:
    print(f"- {action.action_type}")
```

### Outcome Simulation

```python
# Simulate a specific action sequence
test_path = [
    PlannedAction("navigate", {"url": "example.com"}, 3.0, 0.95),
    PlannedAction("search", {"query": "Python"}, 1.5, 0.85),
    PlannedAction("extract", {}, 2.0, 0.8),
]

outcome = await planner.simulate_path(test_path, "Starting state")

print(f"Success probability: {outcome.success_probability:.2f}")
print(f"Confidence: {outcome.confidence:.2f}")
print(f"Potential failures: {outcome.failure_modes}")
```

## Integration Points

### Event Bus (organism_core.py)
- **Subscribes to**:
  - `ACTION_COMPLETE` - Updates plan progress
  - `ACTION_FAILED` - Triggers replanning
  - `SURPRISE` - Considers replanning if confidence drops

- **Publishes**:
  - `PREDICTION_MADE` - When plan created
  - `STRATEGY_UPDATED` - When replanning occurs

### LLM Client (llm_client.py)
- Used for action generation (if available)
- Used for outcome prediction enhancement
- Falls back to heuristics if unavailable

### Uncertainty Tracker (uncertainty_tracker.py)
- Optional integration for confidence scoring
- Can influence pruning decisions

### Mission Keeper (mission_keeper.py)
- Mission goal used for alignment scoring
- Plans scored based on how well they serve mission

## Configuration

```python
# Planning parameters
DEFAULT_DEPTH = 5          # Default lookahead depth
MAX_DEPTH = 10            # Maximum depth to prevent runaway
MAX_BRANCHES = 5          # Maximum branches per node
SIMULATION_TIMEOUT = 30.0  # Seconds for simulation
REPLAN_THRESHOLD = 0.3    # If confidence drops below this, replan

# Scoring weights
SCORE_SUCCESS_PROB = 0.4   # Weight for success probability
SCORE_MISSION_ALIGN = 0.3  # Weight for mission alignment
SCORE_EFFICIENCY = 0.2     # Weight for efficiency (fewer steps)
SCORE_UNCERTAINTY = 0.1    # Weight for uncertainty reduction

# Pruning thresholds
PRUNE_MIN_SUCCESS = 0.1    # Prune paths with <10% success
PRUNE_MIN_SCORE = 0.2      # Prune paths with <20% overall score
```

## Performance

- **Tree expansion**: ~50 nodes/second (without LLM)
- **Simulation**: ~100 paths/second (heuristic), ~5 paths/second (with LLM)
- **Caching**: Plans cached by goal+state hash, instant retrieval
- **Database**: SQLite persistence, minimal overhead (~10ms/plan)
- **Memory**: ~1KB per plan, ~100 bytes per tree node

## Database Schema

```sql
CREATE TABLE plans (
    plan_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    plan_data TEXT NOT NULL,    -- JSON serialized plan
    score REAL,
    confidence REAL,
    created_at REAL,
    status TEXT
);

CREATE TABLE plan_outcomes (
    plan_id TEXT,
    outcome TEXT,
    success INTEGER,
    actual_duration REAL,
    recorded_at REAL,
    FOREIGN KEY (plan_id) REFERENCES plans(plan_id)
);
```

Database location: `/mnt/c/ev29/memory/planner.db`

## World Model

The planner uses a simple world model for outcome prediction:

```python
class SimpleWorldModel:
    # Default success rates per action type
    action_success_rates = {
        "navigate": 0.95,
        "click": 0.85,
        "fill": 0.9,
        "extract": 0.8,
        "search": 0.85,
        "wait": 0.99,
    }
```

For production use, replace with learned world model that improves from experience.

## Error Handling

The planner handles errors gracefully:

1. **LLM unavailable**: Falls back to heuristic action generation
2. **Empty tree**: Returns empty plan with 0.0 confidence
3. **All paths pruned**: Selects least-bad option
4. **Simulation timeout**: Uses cached/heuristic predictions
5. **Database errors**: Logs but continues operation

## Statistics

```python
stats = planner.get_stats()
# Returns:
{
    "plans_created": 10,
    "plans_completed": 7,
    "plans_abandoned": 2,
    "replans": 3,
    "cache_size": 15,
    "active_plan": "plan_1234567890_abc123",
}
```

## Future Enhancements

1. **Learned World Model**: Replace heuristics with model that learns from outcomes
2. **Monte Carlo Tree Search**: Use MCTS for more sophisticated tree exploration
3. **Parallel Simulation**: Simulate multiple paths concurrently
4. **Cost Models**: Factor in actual resource costs (API tokens, time, money)
5. **Multi-Agent Planning**: Coordinate plans across multiple agents
6. **Hierarchical Planning**: Break complex goals into sub-goals
7. **Explanation Generation**: Explain why plan was chosen over alternatives

## Testing

Run standalone test:
```bash
cd /mnt/c/ev29
python3 -m agent.planner
```

This will create a sample plan and demonstrate all features.

## License

Part of Eversale AI Employee project.

