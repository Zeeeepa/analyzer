# Reddit Commenter Extraction - Usage Guide

This guide explains how to use the new `find_commenters()` and `find_users_by_interest()` methods added to the RedditHandler.

## Overview

The RedditHandler now includes two new methods for extracting engaged users from Reddit comments:

1. **find_commenters()** - Find users who commented on posts matching a query
2. **find_users_by_interest()** - Find users interested in topics across multiple subreddits

## Method 1: find_commenters()

Extract users who actively comment on posts about a specific topic.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `subreddit` | str | required | Subreddit to search in |
| `query` | str | required | Search query to find posts |
| `max_posts` | int | 10 | Maximum posts to scan |
| `max_comments_per_post` | int | 50 | Maximum comments per post |
| `min_score` | int | 1 | Minimum comment score to include |

### Returns

```python
{
    "success": True,
    "commenters": [
        {
            "username": "username",
            "profile_url": "https://reddit.com/user/username",
            "total_score": 358,
            "comment_count": 8,
            "sample_comments": [
                {
                    "body": "comment text...",
                    "score": 45,
                    "post_title": "post title..."
                }
            ]
        }
    ],
    "total_found": 63,
    "posts_scanned": 5,
    "query": "marketing agency",
    "subreddit": "Entrepreneur"
}
```

### Example Usage

```python
import asyncio
from engine.agent.reddit_handler import RedditHandler

async def find_agency_owners():
    handler = RedditHandler()

    try:
        result = await handler.find_commenters(
            subreddit="Entrepreneur",
            query="marketing agency",
            max_posts=10,
            max_comments_per_post=50,
            min_score=2
        )

        print(f"Found {result['total_found']} engaged commenters")

        for commenter in result['commenters'][:10]:
            print(f"u/{commenter['username']}")
            print(f"  Score: {commenter['total_score']}")
            print(f"  Comments: {commenter['comment_count']}")
            print(f"  Profile: {commenter['profile_url']}")
            print()

    finally:
        await handler.close()

asyncio.run(find_agency_owners())
```

## Method 2: find_users_by_interest()

Find users who consistently discuss topics across multiple subreddits.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `topic_keywords` | List[str] | required | Keywords to search for |
| `subreddits` | List[str] | required | Subreddits to search in |
| `min_engagement` | int | 5 | Minimum comment score |
| `max_posts_per_search` | int | 5 | Max posts per keyword/subreddit |

### Returns

```python
[
    {
        "username": "username",
        "profile_url": "https://reddit.com/user/username",
        "total_score": 1011,
        "comment_count": 5,
        "subreddits": ["Entrepreneur", "startups"],
        "keywords": ["saas", "startup"],
        "sample_comments": [
            {
                "body": "comment text...",
                "score": 200,
                "post_title": "post title...",
                "keyword": "saas",
                "subreddit": "Entrepreneur"
            }
        ]
    }
]
```

### Example Usage

```python
import asyncio
from engine.agent.reddit_handler import RedditHandler

async def find_saas_founders():
    handler = RedditHandler()

    try:
        users = await handler.find_users_by_interest(
            topic_keywords=["saas", "startup", "bootstrapped"],
            subreddits=["Entrepreneur", "startups", "SaaS"],
            min_engagement=3,
            max_posts_per_search=5
        )

        print(f"Found {len(users)} interested users")

        for user in users[:20]:
            print(f"u/{user['username']}")
            print(f"  Score: {user['total_score']}")
            print(f"  Comments: {user['comment_count']}")
            print(f"  Active in: {', '.join(user['subreddits'])}")
            print(f"  Topics: {', '.join(user['keywords'])}")
            print(f"  Profile: {user['profile_url']}")
            print()

    finally:
        await handler.close()

asyncio.run(find_saas_founders())
```

## Use Cases

### 1. Lead Generation

Find potential customers discussing pain points:

```python
result = await handler.find_commenters(
    subreddit="smallbusiness",
    query="need help with accounting",
    max_posts=20,
    min_score=1
)
```

### 2. Influencer Outreach

Find active community members:

```python
users = await handler.find_users_by_interest(
    topic_keywords=["content marketing", "SEO"],
    subreddits=["marketing", "SEO", "content_marketing"],
    min_engagement=5
)
```

### 3. Market Research

Identify engaged users in a niche:

```python
result = await handler.find_commenters(
    subreddit="vegan",
    query="protein powder",
    max_posts=15,
    min_score=2
)
```

### 4. Product Feedback

Find users interested in your product category:

```python
users = await handler.find_users_by_interest(
    topic_keywords=["project management", "productivity tool"],
    subreddits=["productivity", "startups", "Entrepreneur"],
    min_engagement=3
)
```

## Best Practices

### Rate Limiting

The methods automatically handle Reddit's rate limits, but for best results:

- Keep `max_posts` <= 10 for initial searches
- Use `min_score` >= 2 to filter low-quality comments
- Add delays between multiple calls

### Engagement Sorting

Commenters are sorted by `total_score * comment_count` which measures:
- **High score, few comments** = Popular occasional commenter
- **Low score, many comments** = Active but less upvoted
- **High score, many comments** = Highly engaged quality contributor

### Error Handling

Always wrap calls in try/except and close the handler:

```python
handler = RedditHandler()
try:
    result = await handler.find_commenters(...)
except Exception as e:
    print(f"Error: {e}")
finally:
    await handler.close()
```

## Performance Notes

### Typical Response Times

| Operation | Posts | Comments | Time |
|-----------|-------|----------|------|
| find_commenters() | 5 | 20/post | ~30s |
| find_commenters() | 10 | 50/post | ~60s |
| find_users_by_interest() | 2x2 searches | 5/each | ~90s |

### Reddit API Limits

- JSON API: ~10 req/min (unauthenticated)
- Automatic rate limiting: 3s between requests
- Fallback to RSS if rate limited
- Cache: 2min TTL for repeated requests

## Integration with Existing Code

Both methods work seamlessly with existing RedditHandler features:

```python
handler = RedditHandler()

# Search for posts
posts = await handler.search("AI automation", subreddit="ChatGPT")

# Extract commenters from those posts
for post in posts['posts'][:3]:
    post_data = await handler.get_post_json(post.permalink)
    # Process comments...

# Or use the new method directly
commenters = await handler.find_commenters(
    subreddit="ChatGPT",
    query="AI automation",
    max_posts=3
)
```

## Filtering & Post-Processing

### Filter by Engagement

```python
result = await handler.find_commenters(...)

# High engagement users only
top_users = [
    c for c in result['commenters']
    if c['total_score'] * c['comment_count'] > 100
]
```

### Extract Profile URLs

```python
users = await handler.find_users_by_interest(...)

# Get just the profile URLs
profile_urls = [u['profile_url'] for u in users]

# Export to file
with open('reddit_leads.txt', 'w') as f:
    f.write('\n'.join(profile_urls))
```

### Cross-Reference Topics

```python
users = await handler.find_users_by_interest(
    topic_keywords=["saas", "marketing automation"],
    subreddits=["Entrepreneur", "marketing"]
)

# Find users who discussed BOTH topics
multi_topic = [
    u for u in users
    if len(u['keywords']) >= 2
]
```

## Troubleshooting

### Empty Results

If you get no results:
1. Try broader search queries
2. Lower `min_score` threshold
3. Increase `max_posts`
4. Check if subreddit has recent activity

### Rate Limit Errors

If you hit rate limits:
1. Reduce `max_posts` and `max_comments_per_post`
2. Add delays between calls: `await asyncio.sleep(5)`
3. Use RSS fallback (automatic)

### Deleted/Bot Accounts

Automatic filtering for:
- `[deleted]` users
- `AutoModerator`
- Usernames ending in "bot"

## Complete Example: Lead Finder

```python
import asyncio
from engine.agent.reddit_handler import RedditHandler

async def find_leads_for_saas_tool():
    """
    Find potential leads for a SaaS automation tool.
    Target: Small business owners discussing automation needs.
    """
    handler = RedditHandler()

    try:
        # Step 1: Find users discussing automation pain points
        print("Finding users discussing automation...")
        automation_users = await handler.find_users_by_interest(
            topic_keywords=["automation", "automate tasks", "productivity"],
            subreddits=["Entrepreneur", "smallbusiness", "SaaS"],
            min_engagement=3,
            max_posts_per_search=5
        )

        print(f"Found {len(automation_users)} users interested in automation")

        # Step 2: Filter for high engagement
        qualified_leads = [
            u for u in automation_users
            if u['total_score'] > 50 and u['comment_count'] > 2
        ]

        print(f"Qualified {len(qualified_leads)} high-engagement leads")

        # Step 3: Export results
        with open('automation_leads.csv', 'w') as f:
            f.write('Username,Profile URL,Total Score,Comments,Subreddits,Keywords\n')
            for lead in qualified_leads[:50]:
                f.write(f"{lead['username']},{lead['profile_url']},"
                       f"{lead['total_score']},{lead['comment_count']},"
                       f"\"{','.join(lead['subreddits'])}\","
                       f"\"{','.join(lead['keywords'])}\"\n")

        print("Results exported to automation_leads.csv")

        # Step 4: Show sample comments for top leads
        print("\nTop 5 leads with sample comments:")
        for i, lead in enumerate(qualified_leads[:5], 1):
            print(f"\n{i}. u/{lead['username']}")
            print(f"   Profile: {lead['profile_url']}")
            print(f"   Score: {lead['total_score']} | Comments: {lead['comment_count']}")
            if lead['sample_comments']:
                print(f"   Sample: {lead['sample_comments'][0]['body'][:100]}...")

    finally:
        await handler.close()

if __name__ == "__main__":
    asyncio.run(find_leads_for_saas_tool())
```

## Next Steps

See also:
- `/mnt/c/ev29/cli/test_reddit_commenters.py` - Test suite
- `/mnt/c/ev29/cli/engine/agent/reddit_handler.py` - Full implementation
- Reddit API docs: https://www.reddit.com/dev/api
