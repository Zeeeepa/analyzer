# Natural Language Triggers - Quick Reference

Quick reference for all natural language commands available in the Eversale CLI agent.

---

## UI-TARS Enhanced Features

### System-2 Reasoning (Deliberate Thinking)
```
"use system-2 reasoning"
"enable system-2"
"use thought and reflection"
"think before acting"
"use deliberate reasoning"
```

### Screenshot with Context (History Management)
```
"screenshot with context"
"use conversation context"
"enable context management"
"keep screenshot history"
```

### Smart Retry (Tiered Timeouts)
```
"retry with tiered timeouts"
"use tiered retry"
"enable smart retry"
"retry with backoff"
```

### Coordinate Normalization (0-1000 Range)
```
"normalize coordinates"
"use normalized coordinates"
"enable coordinate normalization"
"use 0-1000 range"
```

---

## Basic Actions

### Navigation
```
"go to google.com"
"open https://github.com"
"navigate to facebook.com"
```

### Click
```
"click Login button"
"click on Submit"
"press Continue button"
```

### Type/Input
```
"type 'hello' in text field"
"enter 'user@example.com' in email"
"fill username with 'admin'"
```

### Search
```
"search for python tutorials"
"find AI courses"
"google machine learning"
```

### Screenshots
```
"take screenshot"
"capture screen"
"screenshot"
```

### Scroll
```
"scroll down"
"scroll up"
"scroll to bottom"
```

### Wait
```
"wait 5 seconds"
"pause for 3 seconds"
"wait"
```

### Browser Controls
```
"go back"
"go forward"
"refresh"
"close tab"
```

---

## Workflows (Deterministic - No LLM Needed)

### Facebook Ads Library
```
"search facebook ads for marketing agencies"
"fb ads library search for real estate"
```

### LinkedIn
```
"search linkedin for AI engineers"
"find on linkedin data scientists"
```

### Reddit
```
"search reddit for programming advice"
"find on reddit warm leads"
```

### Google Maps
```
"google maps search for coffee shops"
"find businesses near me"
```

### Gmail
```
"open gmail"
"check gmail inbox"
```

---

## Data Extraction

```
"extract data from page"
"scrape listings"
"collect information"
```

---

## Combined Commands

### Multi-step with Features
```
"use system-2 reasoning and go to facebook.com"
"screenshot with context then click Login"
"enable smart retry and search linkedin for developers"
```

### Sequential Actions
```
"go to gmail then take screenshot"
"open facebook and scroll down"
"navigate to google.com then search for AI"
```

---

## Tips

1. **Be specific** - "click Login button" is better than "click button"
2. **Use quotes** for exact text - "type 'hello world' in search box"
3. **Enable features first** - "use system-2" before complex tasks
4. **Combine wisely** - Features + actions work together

---

## Common Patterns

| Pattern | Example | Result |
|---------|---------|--------|
| go to [url] | "go to github.com" | Navigate |
| click [element] | "click Login" | Click |
| type [text] in [field] | "type 'test' in search" | Type |
| search for [query] | "search for AI" | Search |
| [action] then [action] | "go to x.com then screenshot" | Sequential |
| use [feature] and [action] | "use system-2 and click" | Feature + Action |

---

## Testing Your Commands

Run the test suite to see all supported patterns:
```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_nl_triggers.py
```

---

## More Examples

### E-commerce
```
"go to amazon.com"
"search for wireless headphones"
"click first product"
"scroll down to reviews"
"screenshot with context"
```

### Social Media
```
"open facebook ads library"
"search facebook ads for fitness products"
"extract advertisers"
```

### Professional
```
"use system-2 reasoning"
"search linkedin for software engineers in NYC"
"extract profiles"
```

### Local Business
```
"google maps search for restaurants in Chicago"
"extract business listings"
```

---

## Related Files

- Full documentation: `/mnt/c/ev29/cli/engine/agent/NL_TRIGGERS_SUMMARY.md`
- Test suite: `/mnt/c/ev29/cli/engine/agent/test_nl_triggers.py`
- Parser code: `/mnt/c/ev29/cli/engine/agent/command_parser.py`
- Templates: `/mnt/c/ev29/cli/engine/agent/action_templates.py`
- Router: `/mnt/c/ev29/cli/engine/agent/intelligent_task_router.py`
