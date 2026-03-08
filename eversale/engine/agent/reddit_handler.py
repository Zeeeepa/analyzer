"""
Reddit-Specific Handler for Desktop Agent

Reddit aggressively blocks browser automation (including patchright/stealth).
This module provides workarounds using Reddit's public data surfaces:

1. RSS feeds (/.rss) - No auth, lightweight, good for posts
2. JSON API (/.json) - No auth, full metadata, good for structured data
3. old.reddit.com - Lighter JS, easier to scrape
4. Alternative frontends (Redlib, Teddit) - Proxy RSS/data
5. PullPush API - Historical/archived data

Usage:
    handler = RedditHandler()

    # For subreddit posts
    posts = await handler.get_subreddit("python", sort="hot", limit=25)

    # For user posts/comments
    user_data = await handler.get_user("spez", data_type="submitted")

    # For specific post + comments
    post = await handler.get_post("r/python/comments/abc123/title")

    # Search (via RSS or JSON)
    results = await handler.search("machine learning", subreddit="python")

Sources:
- RSS: https://www.reddit.com/r/{sub}/.rss
- JSON: https://www.reddit.com/r/{sub}.json (rate limited ~10 req/min unauthenticated)
- old.reddit: Less JS, same data
- Redlib: https://github.com/redlib-org/redlib (self-hosted alternative frontend)
- PullPush: https://pullpush.io/ (historical archive, ~15 req/min soft limit)
"""

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote_plus, urljoin, urlparse

import httpx
from loguru import logger

from .social_lead_criteria import count_keyword_matches

# Rate limiting - tuned for speed while respecting Reddit's 60 req/min limit
_LAST_REQUEST_TIME: Dict[str, float] = {}
_RATE_LIMITS = {
    "json": 1.0,      # 60 req/min = 1 req/s, using 1.0s for safety
    "rss": 0.5,       # RSS is more lenient, can go faster
    "pullpush": 1.0,  # Match Reddit's rate limit
    "old": 0.75,      # old.reddit.com can handle faster requests
}

# Concurrency control for parallel requests
_REQUEST_SEMAPHORE: Optional[asyncio.Semaphore] = None
_MAX_CONCURRENT_REQUESTS = 3  # Max parallel Reddit API requests

# Response cache with TTL
_RESPONSE_CACHE: Dict[str, tuple] = {}  # url -> (data, timestamp)
_CACHE_TTL = 120  # 2 minutes - Reddit data doesn't change that fast


@dataclass
class RedditPost:
    """Structured Reddit post data"""
    title: str
    author: str
    subreddit: str
    url: str
    permalink: str
    score: int = 0
    num_comments: int = 0
    created_utc: float = 0
    selftext: str = ""
    is_self: bool = False
    thumbnail: str = ""
    flair: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "author": self.author,
            "subreddit": self.subreddit,
            "url": self.url,
            "permalink": self.permalink,
            "score": self.score,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc,
            "selftext": self.selftext,
            "is_self": self.is_self,
            "thumbnail": self.thumbnail,
            "flair": self.flair,
        }


@dataclass
class RedditComment:
    """Structured Reddit comment data"""
    author: str
    body: str
    score: int = 0
    created_utc: float = 0
    permalink: str = ""
    parent_id: str = ""
    depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "author": self.author,
            "body": self.body,
            "score": self.score,
            "created_utc": self.created_utc,
            "permalink": self.permalink,
            "parent_id": self.parent_id,
            "depth": self.depth,
        }


class RedditHandler:
    """
    Handler for Reddit data extraction without browser automation.

    Implements multiple fallback strategies:
    1. JSON API (most data, rate limited)
    2. RSS feeds (lightweight, less data)
    3. old.reddit.com scraping (fallback)
    4. Alternative frontends (Redlib instances)
    5. PullPush archive API (historical data)
    """

    # Public Redlib instances (fallback for when reddit.com blocks)
    REDLIB_INSTANCES = [
        "https://safereddit.com",
        "https://libreddit.kavin.rocks",
        "https://reddit.invak.id",
        "https://lr.artemislena.eu",
    ]

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        timeout: float = 30.0,
        use_old_reddit: bool = True,
        redlib_instance: Optional[str] = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.use_old_reddit = use_old_reddit
        self.redlib_instance = redlib_instance

        # HTTP client with realistic headers
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self, endpoint_type: str = "json"):
        """Apply rate limiting between requests"""
        min_interval = _RATE_LIMITS.get(endpoint_type, 3.0)
        last_time = _LAST_REQUEST_TIME.get(endpoint_type, 0)
        elapsed = time.time() - last_time

        if elapsed < min_interval:
            wait_time = min_interval - elapsed
            await asyncio.sleep(wait_time)

        _LAST_REQUEST_TIME[endpoint_type] = time.time()

    def _build_reddit_url(self, path: str, use_old: bool = None) -> str:
        """Build Reddit URL with optional old.reddit prefix"""
        if use_old is None:
            use_old = self.use_old_reddit

        base = "https://old.reddit.com" if use_old else "https://www.reddit.com"

        # Clean path
        path = path.strip("/")
        if path.startswith("r/"):
            path = path
        elif path.startswith("u/") or path.startswith("user/"):
            path = path
        else:
            path = f"r/{path}"

        return f"{base}/{path}"

    # =========================================================================
    # JSON API Methods (/.json endpoints)
    # =========================================================================

    async def get_subreddit_json(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
        time_filter: str = "all",
        after: str = None,
    ) -> Dict[str, Any]:
        """
        Get subreddit posts via JSON API.

        Args:
            subreddit: Subreddit name (without r/)
            sort: hot, new, top, rising, controversial
            limit: Max posts (up to 100)
            time_filter: For top/controversial: hour, day, week, month, year, all
            after: Pagination token

        Returns:
            Dict with posts and pagination info
        """
        await self._rate_limit("json")

        client = await self._get_client()

        # Build URL
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        params = {"limit": min(limit, 100), "raw_json": 1}

        if sort in ("top", "controversial"):
            params["t"] = time_filter
        if after:
            params["after"] = after

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            posts = []
            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                posts.append(RedditPost(
                    title=post_data.get("title", ""),
                    author=post_data.get("author", "[deleted]"),
                    subreddit=post_data.get("subreddit", subreddit),
                    url=post_data.get("url", ""),
                    permalink=f"https://reddit.com{post_data.get('permalink', '')}",
                    score=post_data.get("score", 0),
                    num_comments=post_data.get("num_comments", 0),
                    created_utc=post_data.get("created_utc", 0),
                    selftext=post_data.get("selftext", ""),
                    is_self=post_data.get("is_self", False),
                    thumbnail=post_data.get("thumbnail", ""),
                    flair=post_data.get("link_flair_text", ""),
                ))

            return {
                "success": True,
                "posts": posts,
                "after": data.get("data", {}).get("after"),
                "before": data.get("data", {}).get("before"),
                "source": "json_api",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning(f"Subreddit r/{subreddit} is private or quarantined")
                return {"success": False, "error": f"r/{subreddit} is private/quarantined", "posts": [], "is_private": True}
            if e.response.status_code == 429:
                logger.warning("Reddit JSON API rate limited - falling back to RSS")
                try:
                    return await self.get_subreddit_rss(subreddit, sort=sort, limit=limit)
                except Exception as rss_err:
                    # RSS also failed - return graceful error instead of crash
                    logger.warning(f"RSS fallback also failed: {rss_err}")
                    return {"success": False, "error": "Rate limited (all sources)", "posts": []}
            elif e.response.status_code in (502, 503, 504):
                # Transient error - wait and retry once
                await asyncio.sleep(2)
                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    posts = []
                    for child in data.get("data", {}).get("children", []):
                        post_data = child.get("data", {})
                        posts.append(RedditPost(
                            title=post_data.get("title", ""),
                            author=post_data.get("author", "[deleted]"),
                            subreddit=post_data.get("subreddit", subreddit),
                            url=post_data.get("url", ""),
                            permalink=f"https://reddit.com{post_data.get('permalink', '')}",
                            score=post_data.get("score", 0),
                            num_comments=post_data.get("num_comments", 0),
                            created_utc=post_data.get("created_utc", 0),
                            selftext=post_data.get("selftext", ""),
                            is_self=post_data.get("is_self", False),
                            thumbnail=post_data.get("thumbnail", ""),
                            flair=post_data.get("link_flair_text", ""),
                        ))
                    return {"success": True, "posts": posts, "source": "json_api_retry"}
                except Exception:
                    return await self.get_subreddit_rss(subreddit, sort=sort, limit=limit)
            raise
        except Exception as e:
            logger.error(f"Reddit JSON API error: {e}")
            return {"success": False, "error": str(e), "posts": []}

    async def get_post_json(
        self,
        permalink: str,
        comment_sort: str = "best",
        comment_limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Get a specific post with comments via JSON API.

        Args:
            permalink: Post permalink (e.g., /r/python/comments/xyz/title/)
            comment_sort: best, top, new, controversial, old, qa
            comment_limit: Max comments to fetch

        Returns:
            Dict with post and comments
        """
        await self._rate_limit("json")

        client = await self._get_client()

        # Clean permalink
        if permalink.startswith("https://"):
            permalink = urlparse(permalink).path
        permalink = permalink.strip("/")
        if not permalink.endswith(".json"):
            permalink = f"{permalink}.json"

        url = f"https://www.reddit.com/{permalink}"
        params = {"sort": comment_sort, "limit": comment_limit, "raw_json": 1}

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            # First element is post, second is comments
            post_data = data[0]["data"]["children"][0]["data"] if data else {}

            post = RedditPost(
                title=post_data.get("title", ""),
                author=post_data.get("author", "[deleted]"),
                subreddit=post_data.get("subreddit", ""),
                url=post_data.get("url", ""),
                permalink=f"https://reddit.com{post_data.get('permalink', '')}",
                score=post_data.get("score", 0),
                num_comments=post_data.get("num_comments", 0),
                created_utc=post_data.get("created_utc", 0),
                selftext=post_data.get("selftext", ""),
                is_self=post_data.get("is_self", False),
            )

            # Parse comments recursively
            comments = []
            if len(data) > 1:
                self._parse_comments(
                    data[1].get("data", {}).get("children", []),
                    comments,
                    depth=0
                )

            return {
                "success": True,
                "post": post,
                "comments": comments,
                "source": "json_api",
            }

        except Exception as e:
            logger.error(f"Reddit post JSON error: {e}")
            return {"success": False, "error": str(e)}

    def _parse_comments(
        self,
        children: List[Dict],
        comments: List[RedditComment],
        depth: int = 0,
        max_depth: int = 20  # Prevent stack overflow on deeply nested threads
    ):
        """Recursively parse comment tree with depth limit"""
        if depth > max_depth:
            return  # Stop recursion to prevent stack overflow
        for child in children:
            if child.get("kind") != "t1":  # Skip non-comment entries
                continue

            data = child.get("data", {})

            comments.append(RedditComment(
                author=data.get("author", "[deleted]"),
                body=data.get("body", ""),
                score=data.get("score", 0),
                created_utc=data.get("created_utc", 0),
                permalink=f"https://reddit.com{data.get('permalink', '')}",
                parent_id=data.get("parent_id", ""),
                depth=depth,
            ))

            # Recurse into replies (with depth limit)
            replies = data.get("replies")
            if replies and isinstance(replies, dict) and depth < max_depth:
                self._parse_comments(
                    replies.get("data", {}).get("children", []),
                    comments,
                    depth=depth + 1,
                    max_depth=max_depth
                )

    async def get_user_json(
        self,
        username: str,
        data_type: str = "overview",  # overview, submitted, comments
        sort: str = "new",
        limit: int = 25,
    ) -> Dict[str, Any]:
        """Get user's posts/comments via JSON API"""
        await self._rate_limit("json")

        client = await self._get_client()

        url = f"https://www.reddit.com/user/{username}/{data_type}.json"
        params = {"sort": sort, "limit": min(limit, 100), "raw_json": 1}

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            items = []
            for child in data.get("data", {}).get("children", []):
                kind = child.get("kind")
                item_data = child.get("data", {})

                if kind == "t3":  # Post
                    items.append({
                        "type": "post",
                        "data": RedditPost(
                            title=item_data.get("title", ""),
                            author=username,
                            subreddit=item_data.get("subreddit", ""),
                            url=item_data.get("url", ""),
                            permalink=f"https://reddit.com{item_data.get('permalink', '')}",
                            score=item_data.get("score", 0),
                            num_comments=item_data.get("num_comments", 0),
                            created_utc=item_data.get("created_utc", 0),
                            selftext=item_data.get("selftext", ""),
                        )
                    })
                elif kind == "t1":  # Comment
                    items.append({
                        "type": "comment",
                        "data": RedditComment(
                            author=username,
                            body=item_data.get("body", ""),
                            score=item_data.get("score", 0),
                            created_utc=item_data.get("created_utc", 0),
                            permalink=f"https://reddit.com{item_data.get('permalink', '')}",
                        )
                    })

            return {
                "success": True,
                "username": username,
                "items": items,
                "after": data.get("data", {}).get("after"),
                "source": "json_api",
            }

        except Exception as e:
            logger.error(f"Reddit user JSON error: {e}")
            return {"success": False, "error": str(e), "items": []}

    # =========================================================================
    # RSS Feed Methods (/.rss endpoints) - More reliable, less data
    # =========================================================================

    async def get_subreddit_rss(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
    ) -> Dict[str, Any]:
        """
        Get subreddit posts via RSS feed.

        More reliable than JSON (less rate limiting) but less metadata.
        """
        await self._rate_limit("rss")

        client = await self._get_client()

        # RSS URL patterns
        if sort == "hot":
            url = f"https://www.reddit.com/r/{subreddit}/.rss"
        else:
            url = f"https://www.reddit.com/r/{subreddit}/{sort}/.rss"

        try:
            response = await client.get(url)
            response.raise_for_status()

            # Parse RSS/Atom feed
            root = ET.fromstring(response.text)

            # Handle both RSS and Atom namespaces
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            posts = []
            entries = root.findall(".//atom:entry", ns) or root.findall(".//item")

            for entry in entries[:limit]:
                # Atom format
                title = entry.find("atom:title", ns)
                link = entry.find("atom:link", ns)
                author = entry.find("atom:author/atom:name", ns)
                published = entry.find("atom:published", ns)
                content = entry.find("atom:content", ns)

                # Fallback to RSS format
                if title is None:
                    title = entry.find("title")
                if link is None:
                    link = entry.find("link")
                if author is None:
                    author = entry.find("author")
                if published is None:
                    published = entry.find("pubDate")
                if content is None:
                    content = entry.find("description")

                # Extract subreddit from author (format: /u/author or /r/subreddit)
                author_text = author.text if author is not None else ""
                if author_text.startswith("/u/"):
                    author_text = author_text[3:]

                # Get link href (Atom) or text (RSS)
                link_url = ""
                if link is not None:
                    link_url = link.get("href", "") or link.text or ""

                posts.append(RedditPost(
                    title=title.text if title is not None else "",
                    author=author_text,
                    subreddit=subreddit,
                    url=link_url,
                    permalink=link_url,
                    selftext=content.text if content is not None else "",
                ))

            return {
                "success": True,
                "posts": posts,
                "source": "rss_feed",
            }

        except Exception as e:
            logger.error(f"Reddit RSS error: {e}")
            return {"success": False, "error": str(e), "posts": []}

    async def get_user_rss(
        self,
        username: str,
        data_type: str = "submitted",  # submitted, comments
    ) -> Dict[str, Any]:
        """Get user's posts/comments via RSS feed"""
        await self._rate_limit("rss")

        client = await self._get_client()

        url = f"https://www.reddit.com/user/{username}/{data_type}/.rss"

        try:
            response = await client.get(url)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            items = []
            entries = root.findall(".//atom:entry", ns) or root.findall(".//item")

            for entry in entries:
                title = entry.find("atom:title", ns) or entry.find("title")
                link = entry.find("atom:link", ns) or entry.find("link")
                content = entry.find("atom:content", ns) or entry.find("description")

                link_url = ""
                if link is not None:
                    link_url = link.get("href", "") or link.text or ""

                items.append({
                    "title": title.text if title is not None else "",
                    "url": link_url,
                    "content": content.text if content is not None else "",
                })

            return {
                "success": True,
                "username": username,
                "items": items,
                "source": "rss_feed",
            }

        except Exception as e:
            logger.error(f"Reddit user RSS error: {e}")
            return {"success": False, "error": str(e), "items": []}

    # =========================================================================
    # Search Methods
    # =========================================================================

    async def search(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
    ) -> Dict[str, Any]:
        """
        Search Reddit via JSON API.

        Args:
            query: Search query
            subreddit: Limit to specific subreddit (optional)
            sort: relevance, hot, top, new, comments
            time_filter: hour, day, week, month, year, all
            limit: Max results
        """
        await self._rate_limit("json")

        client = await self._get_client()

        if subreddit:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            params = {"q": query, "restrict_sr": "on"}
        else:
            url = "https://www.reddit.com/search.json"
            params = {"q": query}

        params.update({
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 100),
            "raw_json": 1,
        })

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            posts = []
            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                posts.append(RedditPost(
                    title=post_data.get("title", ""),
                    author=post_data.get("author", "[deleted]"),
                    subreddit=post_data.get("subreddit", ""),
                    url=post_data.get("url", ""),
                    permalink=f"https://reddit.com{post_data.get('permalink', '')}",
                    score=post_data.get("score", 0),
                    num_comments=post_data.get("num_comments", 0),
                    created_utc=post_data.get("created_utc", 0),
                    selftext=post_data.get("selftext", ""),
                ))

            return {
                "success": True,
                "query": query,
                "posts": posts,
                "source": "json_api",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Reddit search rate limited")
            return {"success": False, "error": str(e), "posts": []}
        except Exception as e:
            logger.error(f"Reddit search error: {e}")
            return {"success": False, "error": str(e), "posts": []}

    # =========================================================================
    # Commenter Extraction Methods
    # =========================================================================

    async def find_commenters(
        self,
        subreddit: str,
        query: str,
        max_posts: int = 10,
        max_comments_per_post: int = 50,
        min_score: int = 1,
        after_utc: Optional[int] = None,
        before_utc: Optional[int] = None,
        icp_keywords: Optional[List[str]] = None,
        require_keyword_match: bool = False,
    ) -> Dict[str, Any]:
        """
        Find active commenters from posts matching a query.

        Returns users who commented (not just post authors) with their engagement metrics.

        Args:
            subreddit: Subreddit to search in
            query: Search query to find posts
            max_posts: Maximum posts to scan for comments
            max_comments_per_post: Maximum comments to fetch per post
            min_score: Minimum comment score to include

        Returns:
            Dict with commenters sorted by engagement (total_score * comment_count)
        """
        try:
            # 1. Search for posts matching query
            logger.info(f"Searching r/{subreddit} for '{query}' (max {max_posts} posts)")
            search_result = await self.search(query, subreddit=subreddit, limit=max_posts)

            if not search_result.get("success"):
                return {
                    "success": False,
                    "error": search_result.get("error", "Search failed"),
                    "commenters": [],
                    "total_found": 0,
                }

            # 2. For each post, fetch comments (PARALLELIZED for speed)
            all_commenters = {}  # username -> {score, comment_count, sample_comments}
            posts_scanned = 0
            now_utc = int(time.time())

            async def fetch_post_comments(post):
                """Fetch comments for a single post (parallelizable)"""
                try:
                    post_created_utc = int(getattr(post, "created_utc", 0) or 0)
                    if after_utc and post_created_utc and post_created_utc < after_utc:
                        return None
                    if before_utc and post_created_utc and post_created_utc > before_utc:
                        return None

                    # Rate limit to avoid throttling
                    await self._rate_limit("json")

                    # Get post with comments
                    post_result = await self.get_post_json(
                        post.permalink,
                        comment_limit=max_comments_per_post
                    )

                    if not post_result.get("success"):
                        return None

                    return {"post": post, "comments": post_result.get("comments", [])}

                except Exception as e:
                    logger.warning(f"Failed to get comments for post {post.permalink}: {e}")
                    return None

            # Fetch all post comments in parallel (respecting rate limits via _rate_limit)
            posts = search_result.get("posts", [])
            post_results = await asyncio.gather(
                *[fetch_post_comments(post) for post in posts],
                return_exceptions=True
            )

            # Process results
            for result in post_results:
                if result is None or isinstance(result, Exception):
                    continue

                posts_scanned += 1
                post = result["post"]
                comments = result["comments"]

                for comment in comments:
                    # Skip deleted/invalid users
                    if not comment.author or comment.author in ["[deleted]", "AutoModerator"]:
                        continue

                    # Skip bots
                    if comment.author.lower().endswith("bot"):
                        continue

                    # Filter by score
                    if comment.score < min_score:
                        continue

                    comment_created_utc = int(getattr(comment, "created_utc", 0) or 0)
                    if after_utc and comment_created_utc and comment_created_utc < after_utc:
                        continue
                    if before_utc and comment_created_utc and comment_created_utc > before_utc:
                        continue

                    keyword_match_count = 0
                    matched_keywords: List[str] = []
                    if icp_keywords:
                        keyword_match_count, matched_keywords = count_keyword_matches(comment.body or "", icp_keywords)
                        if require_keyword_match and keyword_match_count <= 0:
                            continue

                    username = comment.author

                    # Initialize commenter entry
                    if username not in all_commenters:
                        all_commenters[username] = {
                            "username": username,
                            "total_score": 0,
                            "comment_count": 0,
                            "sample_comments": [],
                            "profile_url": f"https://www.reddit.com/user/{username}",
                            "icp_match_score": 0,
                            "matched_keywords": set(),
                            "newest_comment_utc": 0,
                        }

                    # Aggregate metrics
                    all_commenters[username]["total_score"] += comment.score
                    all_commenters[username]["comment_count"] += 1
                    all_commenters[username]["icp_match_score"] += (keyword_match_count * 12) + min(comment.score, 10)
                    if matched_keywords:
                        all_commenters[username]["matched_keywords"].update(matched_keywords)
                    if comment_created_utc and comment_created_utc > all_commenters[username]["newest_comment_utc"]:
                        all_commenters[username]["newest_comment_utc"] = comment_created_utc

                    # Store sample comments (max 3)
                    if len(all_commenters[username]["sample_comments"]) < 3:
                        all_commenters[username]["sample_comments"].append({
                            "body": comment.body[:200],
                            "score": comment.score,
                            "post_title": post.title[:100],
                            "post_url": post.permalink,
                            "comment_url": comment.permalink,
                            "created_utc": comment_created_utc,
                            "matched_keywords": matched_keywords,
                        })

            # 3. Finalize + sort (prefer ICP match when keywords provided)
            for data in all_commenters.values():
                newest = int(data.get("newest_comment_utc") or 0)
                if newest:
                    age_days = (now_utc - newest) / 86400
                    if age_days <= 3:
                        data["icp_match_score"] += 15
                    elif age_days <= 7:
                        data["icp_match_score"] += 8
                    elif age_days <= 14:
                        data["icp_match_score"] += 3

                data["matched_keywords"] = sorted(list(data.get("matched_keywords", set())), key=lambda s: s.lower())

            sorted_commenters = sorted(
                all_commenters.values(),
                key=lambda x: (
                    x.get("icp_match_score", 0) if icp_keywords else 0,
                    x.get("total_score", 0) * max(x.get("comment_count", 1), 1),
                    x.get("newest_comment_utc", 0),
                ),
                reverse=True
            )

            logger.info(f"Found {len(sorted_commenters)} commenters from {posts_scanned} posts")

            return {
                "success": True,
                "commenters": sorted_commenters,
                "total_found": len(sorted_commenters),
                "posts_scanned": posts_scanned,
                "query": query,
                "subreddit": subreddit,
                "after_utc": after_utc,
                "before_utc": before_utc,
                "icp_keywords": icp_keywords or [],
            }

        except Exception as e:
            logger.error(f"Error finding commenters: {e}")
            return {
                "success": False,
                "error": str(e),
                "commenters": [],
                "total_found": 0,
            }

    async def find_users_by_interest(
        self,
        topic_keywords: List[str],
        subreddits: List[str],
        min_engagement: int = 5,
        max_posts_per_search: int = 5,
    ) -> List[Dict]:
        """
        Find users who actively discuss a topic across subreddits.

        Aggregates engagement metrics across multiple searches to identify
        users who consistently engage with specific topics.

        Args:
            topic_keywords: Keywords to search for
            subreddits: Subreddits to search in
            min_engagement: Minimum comment score to include
            max_posts_per_search: Maximum posts to scan per keyword/subreddit combo

        Returns:
            List of users sorted by total engagement score
        """
        interested_users = {}

        try:
            total_searches = len(subreddits) * len(topic_keywords)
            logger.info(f"Scanning {len(subreddits)} subreddits with {len(topic_keywords)} keywords ({total_searches} searches)")

            for subreddit in subreddits:
                for keyword in topic_keywords:
                    try:
                        # Rate limit between searches
                        await self._rate_limit("json")

                        result = await self.find_commenters(
                            subreddit=subreddit,
                            query=keyword,
                            max_posts=max_posts_per_search,
                            min_score=min_engagement
                        )

                        if not result.get("success"):
                            continue

                        # Aggregate commenter data
                        for commenter in result.get("commenters", []):
                            username = commenter["username"]

                            if username not in interested_users:
                                interested_users[username] = {
                                    "username": username,
                                    "profile_url": commenter["profile_url"],
                                    "total_score": 0,
                                    "comment_count": 0,
                                    "subreddits": set(),
                                    "keywords": set(),
                                    "sample_comments": []
                                }

                            # Aggregate scores
                            interested_users[username]["total_score"] += commenter["total_score"]
                            interested_users[username]["comment_count"] += commenter["comment_count"]
                            interested_users[username]["subreddits"].add(subreddit)
                            interested_users[username]["keywords"].add(keyword)

                            # Add sample comments (max 5 total)
                            if len(interested_users[username]["sample_comments"]) < 5:
                                for sample in commenter.get("sample_comments", []):
                                    if len(interested_users[username]["sample_comments"]) < 5:
                                        interested_users[username]["sample_comments"].append({
                                            **sample,
                                            "keyword": keyword,
                                            "subreddit": subreddit
                                        })

                    except Exception as e:
                        logger.warning(f"Error searching '{keyword}' in r/{subreddit}: {e}")
                        continue

            # Convert sets to lists for JSON serialization
            for user_data in interested_users.values():
                user_data["subreddits"] = list(user_data["subreddits"])
                user_data["keywords"] = list(user_data["keywords"])

            # Sort by total engagement
            sorted_users = sorted(
                interested_users.values(),
                key=lambda x: x["total_score"],
                reverse=True
            )

            logger.info(f"Found {len(sorted_users)} interested users across {len(subreddits)} subreddits")

            return sorted_users

        except Exception as e:
            logger.error(f"Error finding users by interest: {e}")
            return []

    # =========================================================================
    # PullPush Archive API (for historical/deleted content)
    # =========================================================================

    async def search_pullpush(
        self,
        query: str,
        subreddit: Optional[str] = None,
        author: Optional[str] = None,
        after: Optional[int] = None,  # Unix timestamp
        before: Optional[int] = None,
        limit: int = 100,
        content_type: str = "submission",  # submission or comment
    ) -> Dict[str, Any]:
        """
        Search historical Reddit data via PullPush API.

        PullPush is a Pushshift successor that archives Reddit content.
        Rate limits: ~15 req/min soft, ~30 req/min hard

        Args:
            query: Search query (full text search)
            subreddit: Filter by subreddit
            author: Filter by author
            after: Only posts after this Unix timestamp
            before: Only posts before this Unix timestamp
            limit: Max results (up to 100)
            content_type: submission or comment
        """
        await self._rate_limit("pullpush")

        client = await self._get_client()

        if content_type == "submission":
            url = "https://api.pullpush.io/reddit/search/submission/"
        else:
            url = "https://api.pullpush.io/reddit/search/comment/"

        params = {"q": query, "size": min(limit, 100)}

        if subreddit:
            params["subreddit"] = subreddit
        if author:
            params["author"] = author
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            items = []
            for item in data.get("data", []):
                if content_type == "submission":
                    items.append(RedditPost(
                        title=item.get("title", ""),
                        author=item.get("author", "[deleted]"),
                        subreddit=item.get("subreddit", ""),
                        url=item.get("url", ""),
                        permalink=f"https://reddit.com{item.get('permalink', '')}",
                        score=item.get("score", 0),
                        num_comments=item.get("num_comments", 0),
                        created_utc=item.get("created_utc", 0),
                        selftext=item.get("selftext", ""),
                    ))
                else:
                    items.append(RedditComment(
                        author=item.get("author", "[deleted]"),
                        body=item.get("body", ""),
                        score=item.get("score", 0),
                        created_utc=item.get("created_utc", 0),
                        permalink=item.get("permalink", ""),
                    ))

            return {
                "success": True,
                "items": items,
                "source": "pullpush_api",
            }

        except Exception as e:
            logger.error(f"PullPush API error: {e}")
            return {"success": False, "error": str(e), "items": []}

    # =========================================================================
    # Redlib Alternative Frontend (fallback when reddit.com blocks)
    # =========================================================================

    async def get_via_redlib(
        self,
        path: str,
        instance: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get Reddit data via Redlib alternative frontend.

        Redlib proxies Reddit without JS, useful when reddit.com blocks.
        """
        client = await self._get_client()

        instance = instance or self.redlib_instance or self.REDLIB_INSTANCES[0]

        # Try JSON endpoint first
        json_url = f"{instance}/{path.strip('/')}.json"

        try:
            response = await client.get(json_url)
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json(),
                "source": f"redlib:{instance}",
            }
        except Exception as e:
            logger.debug(f"Redlib JSON failed: {e}")

        # Fallback to HTML (would need parsing)
        html_url = f"{instance}/{path.strip('/')}"
        try:
            response = await client.get(html_url)
            response.raise_for_status()
            return {
                "success": True,
                "html": response.text,
                "source": f"redlib:{instance}",
            }
        except Exception as e:
            logger.error(f"Redlib failed: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # High-Level Unified Methods (with automatic fallback)
    # =========================================================================

    async def get_subreddit(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get subreddit posts with automatic fallback.

        Tries: JSON API -> RSS -> Redlib
        """
        # Try JSON first (most data)
        result = await self.get_subreddit_json(subreddit, sort=sort, limit=limit, **kwargs)
        if result.get("success") and result.get("posts"):
            return result

        # Fallback to RSS
        logger.info(f"Falling back to RSS for r/{subreddit}")
        result = await self.get_subreddit_rss(subreddit, sort=sort, limit=limit)
        if result.get("success") and result.get("posts"):
            return result

        # Last resort: Redlib
        logger.info(f"Falling back to Redlib for r/{subreddit}")
        return await self.get_via_redlib(f"r/{subreddit}/{sort}")

    async def get_user(
        self,
        username: str,
        data_type: str = "submitted",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get user data with automatic fallback.

        Tries: JSON API -> RSS -> PullPush
        """
        # Try JSON first
        result = await self.get_user_json(username, data_type=data_type, **kwargs)
        if result.get("success") and result.get("items"):
            return result

        # Fallback to RSS
        logger.info(f"Falling back to RSS for u/{username}")
        result = await self.get_user_rss(username, data_type=data_type)
        if result.get("success") and result.get("items"):
            return result

        # Last resort: PullPush archive
        logger.info(f"Falling back to PullPush for u/{username}")
        content_type = "submission" if data_type == "submitted" else "comment"
        return await self.search_pullpush("", author=username, content_type=content_type)

    async def get_post(
        self,
        permalink: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Get specific post with comments"""
        return await self.get_post_json(permalink, **kwargs)


# =============================================================================
# URL Detection & Routing
# =============================================================================

def is_reddit_url(url: str) -> bool:
    """Check if URL is a Reddit URL"""
    if not url:
        return False

    reddit_domains = [
        "reddit.com",
        "old.reddit.com",
        "new.reddit.com",
        "www.reddit.com",
        "np.reddit.com",
        "redd.it",
    ]

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return any(rd in domain for rd in reddit_domains)
    except Exception:
        return False


def parse_reddit_url(url: str) -> Dict[str, Any]:
    """
    Parse a Reddit URL into components.

    Returns:
        Dict with:
        - type: subreddit, post, user, search, frontpage
        - subreddit: subreddit name (if applicable)
        - post_id: post ID (if post URL)
        - username: username (if user URL)
        - query: search query (if search URL)
        - sort: sort type if present
    """
    result = {"type": "unknown", "original_url": url}

    try:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")

        if not parts or parts[0] == "":
            result["type"] = "frontpage"
        elif parts[0] == "r" and len(parts) >= 2:
            result["subreddit"] = parts[1]

            if len(parts) >= 4 and parts[2] == "comments":
                result["type"] = "post"
                result["post_id"] = parts[3]
                if len(parts) >= 5:
                    result["slug"] = parts[4]
            elif len(parts) >= 3 and parts[2] == "search":
                result["type"] = "search"
                # Parse query from URL params
                from urllib.parse import parse_qs
                params = parse_qs(parsed.query)
                result["query"] = params.get("q", [""])[0]
            elif len(parts) >= 3:
                result["type"] = "subreddit"
                result["sort"] = parts[2]
            else:
                result["type"] = "subreddit"
        elif parts[0] in ("u", "user") and len(parts) >= 2:
            result["type"] = "user"
            result["username"] = parts[1]
            if len(parts) >= 3:
                result["data_type"] = parts[2]  # submitted, comments, etc.
        elif parts[0] == "search":
            result["type"] = "search"
            from urllib.parse import parse_qs
            params = parse_qs(parsed.query)
            result["query"] = params.get("q", [""])[0]

    except Exception as e:
        logger.debug(f"Failed to parse Reddit URL: {e}")

    return result


# =============================================================================
# Convenience Function for Integration
# =============================================================================

async def fetch_reddit_data(url: str, use_cache: bool = True) -> Dict[str, Any]:
    """
    Fetch Reddit data from any Reddit URL.

    Automatically detects URL type and uses appropriate method.
    Returns structured data without browser automation.

    Args:
        url: Reddit URL to fetch
        use_cache: Whether to use cached responses (default True, 2min TTL)

    Usage:
        data = await fetch_reddit_data("https://reddit.com/r/python/hot")
        data = await fetch_reddit_data("https://reddit.com/r/python/comments/xyz/title")
        data = await fetch_reddit_data("https://www.reddit.com/user/spez")
    """
    if not is_reddit_url(url):
        return {"success": False, "error": "Not a Reddit URL"}

    # Check cache first
    cache_key = url.lower().rstrip("/")
    if use_cache and cache_key in _RESPONSE_CACHE:
        cached_data, cached_time = _RESPONSE_CACHE[cache_key]
        if time.time() - cached_time < _CACHE_TTL:
            logger.debug(f"Cache hit for {url}")
            return {**cached_data, "cached": True}
        else:
            # Expired, remove from cache
            del _RESPONSE_CACHE[cache_key]

    parsed = parse_reddit_url(url)
    handler = RedditHandler()

    try:
        result = None
        if parsed["type"] == "subreddit":
            result = await handler.get_subreddit(
                parsed["subreddit"],
                sort=parsed.get("sort", "hot"),
            )
        elif parsed["type"] == "post":
            permalink = f"/r/{parsed['subreddit']}/comments/{parsed['post_id']}"
            if "slug" in parsed:
                permalink += f"/{parsed['slug']}"
            result = await handler.get_post(permalink)
        elif parsed["type"] == "user":
            result = await handler.get_user(
                parsed["username"],
                data_type=parsed.get("data_type", "submitted"),
            )
        elif parsed["type"] == "search":
            result = await handler.search(
                parsed.get("query", ""),
                subreddit=parsed.get("subreddit"),
            )
        elif parsed["type"] == "frontpage":
            result = await handler.get_subreddit_json("popular")
        else:
            return {"success": False, "error": f"Unknown URL type: {parsed['type']}"}

        # Cache successful results
        if result and result.get("success") and use_cache:
            _RESPONSE_CACHE[cache_key] = (result, time.time())
            # Limit cache size to 100 entries
            if len(_RESPONSE_CACHE) > 100:
                oldest_key = min(_RESPONSE_CACHE, key=lambda k: _RESPONSE_CACHE[k][1])
                del _RESPONSE_CACHE[oldest_key]

        return result
    finally:
        await handler.close()


# =============================================================================
# Format Reddit Data for Agent Display
# =============================================================================

def format_reddit_posts(posts: List[RedditPost], max_posts: int = 10) -> str:
    """Format Reddit posts for agent display"""
    lines = []

    for i, post in enumerate(posts[:max_posts], 1):
        score_str = f"[{post.score:+d}]" if post.score else ""
        comments_str = f"({post.num_comments} comments)" if post.num_comments else ""

        lines.append(f"{i}. {score_str} {post.title}")
        lines.append(f"   r/{post.subreddit} | u/{post.author} {comments_str}")
        lines.append(f"   {post.permalink}")

        if post.selftext:
            # Truncate long self text
            preview = post.selftext[:200].replace("\n", " ")
            if len(post.selftext) > 200:
                preview += "..."
            lines.append(f"   > {preview}")

        lines.append("")

    return "\n".join(lines)


def format_reddit_comments(comments: List[RedditComment], max_comments: int = 20) -> str:
    """Format Reddit comments for agent display"""
    lines = []

    for comment in comments[:max_comments]:
        indent = "  " * comment.depth
        score_str = f"[{comment.score:+d}]" if comment.score else ""

        lines.append(f"{indent}{score_str} u/{comment.author}:")

        # Truncate long comments
        body = comment.body[:300].replace("\n", " ")
        if len(comment.body) > 300:
            body += "..."

        lines.append(f"{indent}  {body}")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# ICP-Based Reddit Profile URL Extraction
# =============================================================================

# Default ICP signal patterns for B2B lead identification
ICP_SIGNAL_PATTERNS = {
    "business_owner": [
        # Strong ownership signals
        "i run", "i own", "my agency", "my store", "my app", "my saas",
        "my company", "my business", "my startup", "founded", "co-founder",
        "ceo", "founder", "owner", "running a", "started a", "launched",
        "built a", "we run", "our agency", "our company", "our business",
        "bootstrapped", "quit my job", "full-time on",
        # Additional ownership signals
        "i'm the owner", "business owner", "agency owner", "we launched",
        "our team", "my team", "i founded", "we founded", "i started",
        "we started", "running my own", "own a", "operate a", "managing a"
    ],
    "revenue_signals": [
        "mrr", "arr", "revenue", "making $", "hit $", "crossed $",
        "monthly revenue", "annual revenue", "profit", "sales",
        "$k/month", "$k mrr", "six figures", "seven figures",
        "8 figures", "profitable", "break even", "cash flow",
        "run rate", "ltv", "paying user", "first sale",
        # Additional revenue signals
        "making money", "generating revenue", "profit margin", "revenue growth",
        "making 6 figures", "making 7 figures", "revenue stream", "income from"
    ],
    "client_signals": [
        "my clients", "our clients", "client work", "working with clients",
        "client base", "customer", "users", "subscribers", "paying customers",
        "b2b clients", "enterprise client", "smb client", "inbound lead",
        "closed a deal", "signed a client", "onboarded", "churn",
        # Additional client signals
        "clientele", "customer base", "client acquisition", "landing clients",
        "finding clients", "client retention", "lost a client", "won a client"
    ],
    "operations_signals": [
        "hiring", "looking to hire", "team of", "employees", "contractors",
        "outsourcing", "scaling", "growing", "operations", "processes",
        "offshore", "virtual assistant", "va", "sop", "automation",
        # Additional operations signals
        "expanding team", "building a team", "my staff", "our staff",
        "delegating", "systems and processes", "workflow automation"
    ],
    "ad_spend_signals": [
        "ad spend", "running ads", "facebook ads", "google ads", "paid ads",
        "marketing budget", "advertising", "roas", "cpa", "cpc",
        "meta ads", "linkedin ads", "tiktok ads", "spend on ads", "ad account",
        # Additional ad spend signals
        "advertising budget", "paid traffic", "paid marketing", "ad campaigns",
        "media buying", "spent $", "investing in ads"
    ],
    "pain_points": [
        "struggling with", "frustrated", "challenge", "problem with",
        "need help", "looking for solution", "any recommendations",
        "how do you", "what tool", "what software", "hate", "tired of",
        "biggest issue", "main problem", "stuck on", "can't figure out",
        # Additional pain points
        "nightmare dealing with", "wasting time on", "inefficient",
        "manual process", "too much time", "bottleneck"
    ],
    "buying_intent": [
        "looking for", "recommend", "best tool", "best software",
        "need a", "trying to find", "shopping for", "comparing",
        "budget for", "willing to pay", "invest in", "switch to",
        # Additional buying intent
        "planning to buy", "ready to purchase", "evaluating", "considering",
        "which service", "which tool", "alternatives to", "better than",
        "worth the investment", "roi on", "price point"
    ]
}

# Exclusion patterns (students, hobbyists, non-buyers, spam)
ICP_EXCLUSION_PATTERNS = [
    "student", "learning", "just started learning", "beginner",
    "hobby", "side project for fun", "just curious", "hypothetical",
    "theoretical", "school project", "university", "college assignment",
    # Spam/self-promotion patterns
    "check out my", "follow me", "dm me", "click here", "link in bio",
    "check my profile", "visit my site", "[removed]", "[deleted]",
    # Low-intent patterns
    "thinking about starting", "maybe one day", "just an idea",
    "if i had the money", "when i win the lottery", "in my dreams"
]


@dataclass
class ICPMatch:
    """Represents a Reddit user matching an ICP"""
    username: str
    profile_url: str
    match_score: int
    quality_score: float  # NEW: 0-100 quality rating
    signals_found: List[str]
    source_post_title: str
    source_subreddit: str
    warm_signal: str = ""  # NEW: Best warm signal snippet


def _calculate_user_quality_score(
    user_data: Dict,
    post_content: str,
    signals: List[str]
) -> Tuple[float, str]:
    """
    Calculate user quality score (0-100) based on engagement metrics.

    Factors:
    - Content length (longer = more engaged)
    - Signal diversity (multiple signal types = better)
    - Post quality (detailed vs generic)
    - Subreddit reputation (relevant subs = better)

    Returns (quality_score, warm_signal_snippet)
    """
    quality_score = 0.0

    # 1. Content Length Quality (0-25 points)
    content_length = len(post_content)
    if content_length > 800:
        quality_score += 25  # Very detailed, engaged user
    elif content_length > 400:
        quality_score += 20  # Good detail
    elif content_length > 200:
        quality_score += 15  # Moderate detail
    elif content_length > 100:
        quality_score += 10  # Some detail
    else:
        quality_score += 5   # Minimal content

    # 2. Signal Diversity (0-25 points)
    unique_signal_categories = len(set(s.split(":")[0] for s in signals if ":" in s))
    if unique_signal_categories >= 4:
        quality_score += 25  # Excellent signal diversity
    elif unique_signal_categories >= 3:
        quality_score += 20  # Good diversity
    elif unique_signal_categories >= 2:
        quality_score += 15  # Moderate diversity
    else:
        quality_score += 10  # Single signal type

    # 3. Post Count Quality (0-20 points)
    # Multiple relevant posts = more engaged/legitimate
    post_count = len(user_data.get("posts", []))
    if post_count >= 3:
        quality_score += 20  # Very engaged user
    elif post_count >= 2:
        quality_score += 15  # Engaged user
    else:
        quality_score += 10  # Single post

    # 4. Total Match Score (0-30 points)
    # Normalize total_score to 0-30 range
    total_score = user_data.get("total_score", 0)
    normalized = min(30, (total_score / 100) * 30)
    quality_score += normalized

    # 5. Extract best warm signal (most meaningful snippet)
    warm_signal = _extract_warm_signal(post_content, signals)

    return min(100.0, quality_score), warm_signal


def _extract_warm_signal(text: str, signals: List[str]) -> str:
    """
    Extract the most meaningful warm signal snippet from text.

    Prioritizes:
    1. Business owner statements
    2. Revenue/client mentions
    3. Pain points with context
    4. Buying intent
    """
    # Priority signal patterns
    warm_patterns = [
        # Business owner (highest priority)
        (r"(i (?:run|own|founded|started|launched|built) (?:a|an|my) [^.]{5,80})", 40),
        (r"((?:my|our) (?:company|business|agency|startup|saas|app) [^.]{5,80})", 40),
        (r"(we (?:run|launched|built|started) [^.]{5,80})", 40),
        # Revenue signals
        (r"((?:making|hit|crossed|generating) \$[^.]{5,60})", 35),
        (r"((?:mrr|revenue|profit) (?:is|of|at) [^.]{5,60})", 35),
        # Client signals
        (r"((?:my|our) clients? [^.]{5,60})", 30),
        (r"((?:signed|closed|landed|lost) (?:a|the) (?:client|deal) [^.]{5,60})", 30),
        # Pain points with context
        (r"((?:struggling|frustrated|challenge) with [^.]{5,80})", 25),
        (r"(need help (?:with|finding) [^.]{5,60})", 25),
        # Buying intent
        (r"(looking for (?:a|an|the|some) [^.]{5,60})", 20),
        (r"((?:budget|willing to pay) (?:for|$) [^.]{5,60})", 20),
    ]

    best_snippet = ""
    best_priority = 0

    for pattern, priority in warm_patterns:
        matches = re.finditer(pattern, text.lower())
        for match in matches:
            if priority > best_priority:
                best_priority = priority
                snippet = match.group(1).strip()
                # Clean up and truncate
                snippet = snippet[:150]
                if len(snippet) > 147:
                    snippet = snippet[:147] + "..."
                best_snippet = snippet

    # Fallback: use first strong signal if no pattern matched
    if not best_snippet and signals:
        # Get the signal with highest value category
        priority_categories = ["business_owner", "revenue_signals", "client_signals", "buying_intent"]
        for cat in priority_categories:
            for sig in signals:
                if sig.startswith(cat + ":"):
                    pattern = sig.split(": ", 1)[1] if ": " in sig else ""
                    # Find context around this pattern
                    if pattern in text.lower():
                        idx = text.lower().index(pattern)
                        start = max(0, idx - 20)
                        end = min(len(text), idx + len(pattern) + 80)
                        best_snippet = text[start:end].strip()
                        if best_snippet.startswith(" "):
                            best_snippet = "..." + best_snippet
                        if len(best_snippet) > 147:
                            best_snippet = best_snippet[:147] + "..."
                        break
            if best_snippet:
                break

    return best_snippet


async def find_icp_profile_urls(
    icp_description: str,
    target_count: int = 20,
    subreddits: List[str] = None,
    search_keywords: List[str] = None,
    custom_signals: Dict[str, List[str]] = None,
    exclude_patterns: List[str] = None,
    deep_scan: bool = False,
    min_score: int = 30,  # RAISED from 20 to 30 for higher quality
) -> Dict[str, Any]:
    """
    Find Reddit users matching an ICP and return their profile URLs.

    This function searches Reddit for users who match the given ICP criteria
    based on their posts and comments, returning only profile URLs.

    QUALITY OVER QUANTITY - Improvements:
    - Enhanced ICP signal patterns (business owner, buyer intent, pain points)
    - Quality scoring based on content length, signal diversity, engagement
    - Warm signal extraction (meaningful snippets, not generic comments)
    - Spam/self-promotion filtering
    - Results sorted by quality_score first, then match_score
    - Higher min_score threshold (30) to ensure quality leads

    Args:
        icp_description: Description of the ideal customer profile
        target_count: Number of profile URLs to find
        subreddits: List of subreddits to search (auto-detected if not provided)
        search_keywords: Keywords to search for (extracted from ICP if not provided)
        custom_signals: Additional signal patterns to look for
        exclude_patterns: Patterns that disqualify a user
        deep_scan: If True, also check user's recent post history for more signals
        min_score: Minimum score threshold (default 30, raised from 20 for quality)

    Returns:
        Dict with profile_urls list, quality_scores, warm_signals, and metadata
    """
    handler = RedditHandler()

    try:
        # Parse ICP description to extract signals and subreddits
        icp_lower = icp_description.lower()

        # Auto-detect subreddits based on ICP
        if not subreddits:
            subreddits = _detect_subreddits_for_icp(icp_lower)

        # Extract keywords from ICP
        if not search_keywords:
            search_keywords = _extract_keywords_from_icp(icp_lower)

        # Merge custom signals with defaults
        signal_patterns = {**ICP_SIGNAL_PATTERNS}
        if custom_signals:
            signal_patterns.update(custom_signals)

        # Merge exclusion patterns
        exclusions = list(ICP_EXCLUSION_PATTERNS)
        if exclude_patterns:
            exclusions.extend(exclude_patterns)

        # Collect matching users - aggregate scores across multiple posts
        user_scores: Dict[str, Dict] = {}  # username -> {score, signals, posts}
        posts_scanned = 0

        async def process_post(post, source_subreddit: str):
            """Process a single post and update user scores."""
            # Handle both dataclass and dict
            if hasattr(post, 'author'):
                author = post.author
                title = post.title
                selftext = getattr(post, 'selftext', '')
                post_subreddit = getattr(post, 'subreddit', source_subreddit)
                created_utc = getattr(post, 'created_utc', 0)
                score_val = getattr(post, 'score', 0)
            else:
                author = post.get("author", "")
                title = post.get("title", "")
                selftext = post.get("selftext", "")
                post_subreddit = post.get("subreddit", source_subreddit)
                created_utc = post.get("created_utc", 0)
                score_val = post.get("score", 0)

            # Skip deleted/invalid users and bots
            if not author or author == "[deleted]" or author.lower().endswith("bot"):
                return
            if author.lower() in ("automoderator", "autotldr"):
                return

            # Combine title and body for signal detection
            full_text = f"{title} {selftext}".lower()

            # Check exclusions first
            if any(excl in full_text for excl in exclusions):
                return

            # Score the user based on ICP signals
            score, signals = _score_icp_match(full_text, signal_patterns, icp_lower)

            # Recency bonus: posts from last 7 days get +10
            if created_utc:
                age_days = (time.time() - created_utc) / 86400
                if age_days < 7:
                    score += 10
                elif age_days < 30:
                    score += 5

            # Engagement bonus: high-scoring posts suggest active user
            if score_val > 50:
                score += 5
            elif score_val > 10:
                score += 2

            if score >= min_score:
                if author not in user_scores:
                    user_scores[author] = {
                        "total_score": 0,
                        "signals": set(),
                        "posts": [],
                        "best_subreddit": post_subreddit,
                        "best_title": title[:100],
                        "best_content": full_text  # NEW: Store for quality scoring
                    }

                # Aggregate: add scores (diminishing returns after 3 posts)
                post_count = len(user_scores[author]["posts"])
                if post_count < 3:
                    user_scores[author]["total_score"] += score
                else:
                    user_scores[author]["total_score"] += score * 0.5  # Diminishing

                user_scores[author]["signals"].update(signals)
                user_scores[author]["posts"].append({
                    "title": title[:60],
                    "subreddit": post_subreddit,
                    "score": score
                })

                # Keep best source for display
                if score > user_scores[author].get("best_score", 0):
                    user_scores[author]["best_score"] = score
                    user_scores[author]["best_subreddit"] = post_subreddit
                    user_scores[author]["best_title"] = title[:100]
                    user_scores[author]["best_content"] = full_text  # Update with best content

        # PHASE 1: Search subreddits (sequential to respect rate limits)
        # Fetch "new" from top subreddits first
        for subreddit in subreddits[:5]:
            if len(user_scores) >= target_count * 3:
                break

            try:
                result = await handler.get_subreddit(subreddit, sort="new", limit=75)
                if result.get("success"):
                    posts = result.get("posts", [])
                    posts_scanned += len(posts)
                    for post in posts:
                        await process_post(post, "")
            except Exception:
                pass

        # Fetch "hot" from top 2 subreddits for different content
        for subreddit in subreddits[:2]:
            if len(user_scores) >= target_count * 3:
                break

            try:
                result = await handler.get_subreddit(subreddit, sort="hot", limit=50)
                if result.get("success"):
                    posts = result.get("posts", [])
                    posts_scanned += len(posts)
                    for post in posts:
                        await process_post(post, "")
            except Exception:
                pass

        # PHASE 2: Keyword search if we need more
        search_results = []
        if len(user_scores) < target_count * 2 and search_keywords:
            for keyword in search_keywords[:3]:
                if len(user_scores) >= target_count * 2:
                    break
                try:
                    result = await handler.search(keyword, limit=40)
                    if result.get("success"):
                        search_results.append(result)
                except Exception:
                    pass

            for result in search_results:
                for post in result.get("posts", []):
                    await process_post(post, "")

        # PHASE 3: Deep scan - check user history for top candidates
        if deep_scan and user_scores:
            # Get top 10 candidates for deeper analysis
            top_candidates = sorted(
                user_scores.keys(),
                key=lambda u: user_scores[u]["total_score"],
                reverse=True
            )[:10]

            for username in top_candidates:
                try:
                    user_result = await handler.get_user(username, data_type="submitted", limit=10)
                    if user_result.get("success"):
                        for item in user_result.get("items", [])[:10]:
                            post_data = item.get("data", item)
                            await process_post(post_data, "")
                except Exception:
                    continue

        # Build final matches with quality scoring
        matches = []
        for username, data in user_scores.items():
            # Calculate quality score for this user
            quality_score, warm_signal = _calculate_user_quality_score(
                user_data=data,
                post_content=data.get("best_content", ""),
                signals=list(data["signals"])
            )

            matches.append(ICPMatch(
                username=username,
                profile_url=f"https://www.reddit.com/user/{username}",
                match_score=int(data["total_score"]),
                quality_score=quality_score,
                signals_found=list(data["signals"])[:5],
                source_post_title=data.get("best_title", ""),
                source_subreddit=data.get("best_subreddit", ""),
                warm_signal=warm_signal
            ))

        # Sort by QUALITY SCORE (not just match score) and take top N
        # This prioritizes QUALITY over QUANTITY
        sorted_matches = sorted(
            matches,
            key=lambda x: (x.quality_score, x.match_score),  # Quality first, then match score
            reverse=True
        )[:target_count]

        # Extract just the profile URLs
        profile_urls = [m.profile_url for m in sorted_matches]

        return {
            "success": True,
            "profile_urls": profile_urls,
            "count": len(profile_urls),
            "formatted_output": "\n".join(profile_urls),
            "matches": [
                {
                    "username": m.username,
                    "profile_url": m.profile_url,
                    "score": m.match_score,
                    "quality_score": m.quality_score,  # NEW: Quality rating
                    "warm_signal": m.warm_signal,  # NEW: Best warm signal
                    "signals": m.signals_found,
                    "source": f"r/{m.source_subreddit}"
                }
                for m in sorted_matches
            ],
            "metadata": {
                "subreddits_searched": subreddits[:6],
                "posts_scanned": posts_scanned,
                "unique_users_found": len(user_scores),
                "icp_description": icp_description[:200],
                "deep_scan": deep_scan,
                "avg_quality_score": sum(m.quality_score for m in sorted_matches) / len(sorted_matches) if sorted_matches else 0
            }
        }

    except Exception as e:
        logger.error(f"ICP profile URL extraction failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "profile_urls": [],
            "count": 0
        }

    finally:
        await handler.close()


def _detect_subreddits_for_icp(icp_text: str) -> List[str]:
    """Auto-detect relevant subreddits based on ICP description."""
    subreddit_mapping = {
        # Tech / SaaS
        "agency": ["agency", "marketing", "Entrepreneur", "digital_marketing", "DigitalMarketing"],
        "ecommerce": ["ecommerce", "shopify", "dropship", "FulfillmentByAmazon", "AmazonSeller"],
        "saas": ["SaaS", "startups", "EntrepreneurRideAlong", "microsaas", "indiehackers"],
        "startup": ["startups", "Entrepreneur", "smallbusiness", "indiehackers"],
        "software": ["SaaS", "startups", "webdev", "SideProject"],
        "app": ["SaaS", "startups", "androiddev", "iOSProgramming"],
        # Marketing
        "marketing": ["marketing", "digital_marketing", "PPC", "SEO", "DigitalMarketing"],
        "seo": ["SEO", "bigseo", "TechSEO", "marketing"],
        "ads": ["PPC", "FacebookAds", "googleads", "marketing"],
        # Services
        "real estate": ["realestateinvesting", "RealEstate", "CommercialRealEstate", "realtors"],
        "consultant": ["consulting", "Entrepreneur", "freelance", "smallbusiness"],
        "coach": ["lifecoaching", "Entrepreneur", "coaching", "PersonalTraining"],
        "accountant": ["Accounting", "smallbusiness", "Entrepreneur"],
        "bookkeeper": ["Bookkeeping", "smallbusiness", "Accounting"],
        # Medical / Professional
        "dentist": ["Dentistry", "dentists", "smallbusiness"],
        "doctor": ["medicine", "Physicians", "smallbusiness"],
        "lawyer": ["LawFirm", "lawyers", "smallbusiness"],
        "therapist": ["therapists", "privatepractice", "smallbusiness"],
        # Retail / Hospitality
        "restaurant": ["restaurateur", "KitchenConfidential", "smallbusiness"],
        "cafe": ["cafe", "Coffee", "smallbusiness"],
        "gym": ["gymowners", "personaltraining", "fitness"],
        "salon": ["Salons", "hairstylist", "smallbusiness"],
        # Online
        "content creator": ["NewTubers", "content_marketing", "Blogging", "YouTube"],
        "developer": ["webdev", "SideProject", "startups", "indiehackers"],
        "freelance": ["freelance", "Upwork", "WorkOnline", "forhire"],
        "dropship": ["dropship", "ecommerce", "Entrepreneur"],
        # E-commerce specific
        "amazon": ["FulfillmentByAmazon", "AmazonSeller", "AmazonFBA"],
        "shopify": ["shopify", "ecommerce", "dropship"],
        "etsy": ["EtsySellers", "Etsy", "smallbusiness"],
    }

    detected = []
    for key, subs in subreddit_mapping.items():
        if key in icp_text:
            detected.extend(subs)

    # Default subreddits if none detected
    if not detected:
        detected = ["Entrepreneur", "smallbusiness", "startups", "marketing"]

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for s in detected:
        if s not in seen:
            seen.add(s)
            unique.append(s)

    return unique


def _extract_keywords_from_icp(icp_text: str) -> List[str]:
    """Extract search keywords from ICP description."""
    # Common business keywords to look for
    keyword_patterns = [
        "agency", "ecommerce", "saas", "startup", "consultant",
        "coach", "freelance", "store", "shop", "business",
        "revenue", "clients", "customers", "mrr", "growth"
    ]

    found = []
    for kw in keyword_patterns:
        if kw in icp_text:
            found.append(kw)

    return found[:5] if found else ["business", "entrepreneur"]


def _score_icp_match(
    text: str,
    signal_patterns: Dict[str, List[str]],
    icp_description: str
) -> Tuple[int, List[str]]:
    """
    Score how well a post matches the ICP with improved quality filtering.

    Returns (score, list of signals found)
    """
    score = 0
    signals_found = []

    # Track unique signal types found (for quality bonus)
    signal_types_found = set()

    # Check each signal category
    for category, patterns in signal_patterns.items():
        category_matched = False
        for pattern in patterns:
            if pattern in text:
                # Weight different signal types (HIGHER scores for business signals)
                if category == "business_owner":
                    score += 30  # Increased from 25 - most important
                elif category == "revenue_signals":
                    score += 25  # Increased from 20 - strong buying power
                elif category == "client_signals":
                    score += 20  # Increased from 15 - active business
                elif category == "operations_signals":
                    score += 20  # Increased from 15 - scaling business
                elif category == "ad_spend_signals":
                    score += 15  # Increased from 10 - has marketing budget
                elif category == "pain_points":
                    score += 12  # Increased from 10 - has problems to solve
                elif category == "buying_intent":
                    score += 18  # Increased from 15 - actively shopping

                signals_found.append(f"{category}: {pattern}")
                signal_types_found.add(category)
                category_matched = True
                break  # Only count once per category

    # Quality bonus: Multiple signal types = more confident match
    if len(signal_types_found) >= 3:
        score += 20  # Strong multi-signal match
    elif len(signal_types_found) >= 2:
        score += 10  # Good dual-signal match

    # Bonus for ICP-specific keywords in the text
    icp_keywords = icp_description.split()
    for word in icp_keywords:
        if len(word) > 4 and word in text:
            score += 5

    # Content quality signals
    text_length = len(text)
    if text_length > 500:
        score += 10  # Substantial, detailed post
    elif text_length > 200:
        score += 5   # Moderate detail

    # Filter out generic/low-quality phrases
    generic_phrases = ["thanks", "lol", "yeah", "okay", "cool", "nice", "good post"]
    if any(phrase == text.strip() for phrase in generic_phrases):
        score = max(0, score - 20)  # Penalize generic responses

    return score, signals_found


def format_icp_profile_urls(profile_urls: List[str]) -> str:
    """
    Format profile URLs for clean output (one per line, no extras).

    This produces the exact output format requested:
    https://www.reddit.com/user/USERNAME1
    https://www.reddit.com/user/USERNAME2
    ...
    """
    return "\n".join(profile_urls)
