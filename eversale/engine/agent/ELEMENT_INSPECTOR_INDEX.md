# Element Inspector - File Index

Quick navigation to all Element Inspector files and documentation.

## Core Files

| File | Lines | Purpose | Import Path |
|------|-------|---------|-------------|
| **element_inspector.py** | 917 | Core analysis engine | `from agent.element_inspector import ElementInspector` |
| **smart_selector.py** | 624 | High-level API | `from agent.smart_selector import SmartSelector` |

## Documentation

| File | Lines | Audience | Purpose |
|------|-------|----------|---------|
| **ELEMENT_INSPECTOR_QUICK_START.md** | 150 | All users | 30-second intro, quick examples |
| **ELEMENT_INSPECTOR_README.md** | 446 | All users | Complete documentation |
| **ELEMENT_INSPECTOR_INTEGRATION.md** | 444 | Developers | Integration guide |
| **ELEMENT_INSPECTOR_INDEX.md** | This file | All users | File navigation |

## Examples and Tests

| File | Lines | Purpose |
|------|-------|---------|
| **element_inspector_example.py** | 396 | 10 usage examples |
| **test_element_inspector.py** | 442 | Full test suite |

## Quick Links

### For New Users
1. Start here: [ELEMENT_INSPECTOR_QUICK_START.md](./ELEMENT_INSPECTOR_QUICK_START.md)
2. Run examples: `python agent/element_inspector_example.py`
3. Try it yourself:
   ```python
   from agent.smart_selector import SmartSelector
   selector = SmartSelector(page)
   await selector.click("Submit button")
   ```

### For Developers
1. Read: [ELEMENT_INSPECTOR_README.md](./ELEMENT_INSPECTOR_README.md)
2. Integration: [ELEMENT_INSPECTOR_INTEGRATION.md](./ELEMENT_INSPECTOR_INTEGRATION.md)
3. Run tests: `pytest agent/test_element_inspector.py -v`

### For Advanced Usage
1. Deep inspection: See `ElementInspector` class in [element_inspector.py](./element_inspector.py)
2. Custom integrations: See patterns in [ELEMENT_INSPECTOR_INTEGRATION.md](./ELEMENT_INSPECTOR_INTEGRATION.md)
3. Performance tuning: See optimization section in [ELEMENT_INSPECTOR_README.md](./ELEMENT_INSPECTOR_README.md)

## Module Hierarchy

```
agent/
├── element_inspector.py          ← Core engine (low-level API)
├── smart_selector.py             ← High-level API (use this)
├── visual_targeting.py           ← Integrated (Moondream)
├── humanization/
│   ├── bezier_cursor.py         ← Integrated (human clicks)
│   └── human_typer.py           ← Integrated (human typing)
├── browser_manager.py            ← Integration point
├── react_loop.py                 ← Integration point
└── mcp/
    └── playwright_tools.py       ← Integration point
```

## Class Hierarchy

```
SmartSelector                     ← High-level API (start here)
├── Uses: ElementInspector        ← Element analysis
├── Uses: VisualTargeting         ← Moondream vision
└── Uses: Humanization            ← BezierCursor, HumanTyper

ElementInspector                  ← Low-level API (advanced)
├── Returns: ElementSnapshot      ← 40+ properties
├── Returns: SelectorQualityReport← Best selector
├── Returns: DynamicAnalysis      ← React/Vue detection
└── Returns: Diagnosis Dict       ← Interaction failures
```

## API Quick Reference

### SmartSelector (Recommended)

```python
from agent.smart_selector import SmartSelector

selector = SmartSelector(page)

# Click
result = await selector.click("Submit button")

# Fill
result = await selector.fill("Email input", "user@example.com")

# Extract list
items = await selector.extract_list("First product")

# Wait
result = await selector.wait_for_element("Success message", timeout=10.0)

# Get text
text = await selector.get_element_text("Title")

# Verify exists
exists = await selector.verify_element_exists("Login button")
```

### ElementInspector (Advanced)

```python
from agent.element_inspector import ElementInspector

inspector = ElementInspector(page)

# Inspect
snapshot = await inspector.inspect_element('#submit-btn')

# Analyze quality
quality = await inspector.analyze_selector_quality(snapshot)

# Check dynamic
dynamic = await inspector.is_element_dynamic('#submit-btn')

# Diagnose failure
diagnosis = await inspector.diagnose_interaction_failure('#submit-btn')

# Get ancestry
ancestry = await inspector.get_element_ancestry('#submit-btn', depth=5)

# Get siblings
siblings = await inspector.get_similar_siblings('li:first-child')

# Full report
await inspect_and_report(page, '#submit-btn')
```

## Data Classes

### ElementSnapshot (40+ properties)

```python
@dataclass
class ElementSnapshot:
    # Basic
    tag_name: str
    id: Optional[str]
    classes: List[str]
    attributes: Dict[str, str]

    # Text
    inner_text: str
    text_content: str
    value: Optional[str]
    placeholder: Optional[str]

    # Position
    bounding_box: Dict[str, float]
    is_in_viewport: bool

    # Visibility
    is_visible: bool
    is_displayed: bool
    opacity: float

    # Interactability
    is_enabled: bool
    is_readonly: bool
    accepts_pointer: bool
    is_focusable: bool
    is_editable: bool

    # Accessibility
    role: Optional[str]
    aria_label: Optional[str]
    aria_describedby: Optional[str]
    tabindex: Optional[int]

    # Hierarchy
    parent_tag: str
    child_count: int
    sibling_index: int

    # Styles
    z_index: str
    position: str
    overflow: str
    display: str

    # Framework
    has_react_fiber: bool
    has_vue_instance: bool
    has_angular_scope: bool

    # Stability
    has_stable_id: bool
    has_stable_classes: bool
    likely_dynamic: bool
```

### SelectorQualityReport

```python
@dataclass
class SelectorQualityReport:
    recommended_selector: str
    confidence: float  # 0.0 to 1.0
    strategy: SelectorStrategy
    alternatives: List[Tuple[str, float, SelectorStrategy]]
    warnings: List[str]
    stability_score: float
```

### SmartSelectorResult

```python
@dataclass
class SmartSelectorResult:
    success: bool
    method: str  # 'visual', 'selector', 'fallback'
    selector: Optional[str]
    coordinates: Optional[Tuple[int, int]]
    confidence: float
    issues: List[str]
    suggestions: List[str]
```

## Selector Strategies

```python
class SelectorStrategy(Enum):
    ID = "id"                    # Priority 1: #submit-btn
    ARIA_LABEL = "aria-label"    # Priority 2: [aria-label="Submit"]
    DATA_TESTID = "data-testid"  # Priority 3: [data-testid="submit"]
    TEXT_CONTENT = "text-content"# Priority 4: button:has-text("Submit")
    CLASS = "class"              # Priority 5: .submit-button
    TAG_STRUCTURE = "tag-structure" # Priority 6: form > button:nth-child(2)
    XPATH = "xpath"              # Priority 7: //button[text()="Submit"]
```

## Usage Patterns

### Pattern 1: Simple Click

```python
selector = SmartSelector(page)
result = await selector.click("Submit button")
```

### Pattern 2: Click with Fallback

```python
result = await selector.click(
    "Submit button",
    fallback_selectors=['#submit', 'button[type="submit"]']
)
```

### Pattern 3: Diagnose on Failure

```python
result = await selector.click("Submit button")

if not result.success:
    print(f"Issues: {result.issues}")
    print(f"Try: {result.suggestions}")
```

### Pattern 4: Deep Analysis

```python
inspector = ElementInspector(page)
snapshot = await inspector.inspect_element('#submit-btn')
quality = await inspector.analyze_selector_quality(snapshot)

print(f"Best: {quality.recommended_selector}")
print(f"Confidence: {quality.confidence:.0%}")
```

### Pattern 5: List Extraction

```python
items = await selector.extract_list("First product card", max_items=50)

for item in items:
    print(f"{item['index']}: {item['text']}")
```

## Testing

```bash
# Run all tests
pytest agent/test_element_inspector.py -v

# Run specific test
pytest agent/test_element_inspector.py::TestElementInspector::test_basic_inspection -v

# Run with output
pytest agent/test_element_inspector.py -v -s

# Run examples
python agent/element_inspector_example.py
```

## Performance

| Operation | Time | Caching |
|-----------|------|---------|
| `inspect_element()` | ~50ms | Snapshot can be cached |
| `analyze_selector_quality()` | ~10ms | Results can be cached |
| `is_element_dynamic()` | ~2s | Configurable duration |
| `diagnose_interaction_failure()` | ~60ms | - |
| `smart_selector.click()` | ~100ms | Selector mode |
| `smart_selector.click()` | ~600ms | Visual mode |

## Troubleshooting

| Issue | Solution | Reference |
|-------|----------|-----------|
| Element not found | Use `diagnose_interaction_failure()` | [README](./ELEMENT_INSPECTOR_README.md#troubleshooting) |
| Visual targeting slow | Use `prefer_visual=False` | [README](./ELEMENT_INSPECTOR_README.md#performance) |
| Selectors breaking | Use `analyze_selector_quality()` | [README](./ELEMENT_INSPECTOR_README.md#selector-quality) |
| Import errors | Install dependencies: `pip install playwright loguru` | [Integration Guide](./ELEMENT_INSPECTOR_INTEGRATION.md#troubleshooting) |

## Related Modules

| Module | Path | Integration |
|--------|------|-------------|
| Visual Targeting | `agent/visual_targeting.py` | Used by SmartSelector |
| Bezier Cursor | `agent/humanization/bezier_cursor.py` | Used for clicks |
| Human Typer | `agent/humanization/human_typer.py` | Used for fills |
| Browser Manager | `agent/browser_manager.py` | Attach inspector to pages |
| ReAct Loop | `agent/react_loop.py` | Use SmartSelector for actions |
| MCP Tools | `mcp/playwright_tools.py` | Enhance with inspection |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-07 | Initial release with 6 files, 3,269 lines |

## Support

1. Check [Quick Start](./ELEMENT_INSPECTOR_QUICK_START.md)
2. Read [Full Documentation](./ELEMENT_INSPECTOR_README.md)
3. Review [Examples](./element_inspector_example.py)
4. Run [Tests](./test_element_inspector.py)
5. Check [Integration Guide](./ELEMENT_INSPECTOR_INTEGRATION.md)

## License

Part of Eversale Agent - see main LICENSE file.

---

**Quick Start**: [ELEMENT_INSPECTOR_QUICK_START.md](./ELEMENT_INSPECTOR_QUICK_START.md)

**Full Docs**: [ELEMENT_INSPECTOR_README.md](./ELEMENT_INSPECTOR_README.md)

**Integration**: [ELEMENT_INSPECTOR_INTEGRATION.md](./ELEMENT_INSPECTOR_INTEGRATION.md)
