"""
ICP Keyword Helper - Maps Ideal Customer Profiles to search keywords

When user provides only an ICP category (e.g., "find ecommerce leads"),
this helper provides relevant keywords for Facebook Ads Library and Reddit searches.
"""

import yaml
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
import urllib.parse


class ICPKeywordHelper:
    """Helper for ICP-based keyword routing"""

    def __init__(self, config_path: str = None):
        """Load ICP keyword config"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "icp_keywords.yaml"

        self.config = {}
        self.categories = {}

        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f) or {}
            self.categories = self.config.get('icp_categories', {})
            logger.info(f"Loaded {len(self.categories)} ICP categories")
        except Exception as e:
            logger.warning(f"Could not load ICP keywords config: {e}")

    def get_keywords_for_icp(self, icp_name: str, include_secondary: bool = False) -> List[str]:
        """
        Get search keywords for an ICP category.

        Args:
            icp_name: Category name (e.g., 'ecommerce', 'saas')
            include_secondary: Include secondary keywords

        Returns:
            List of keywords to search
        """
        icp_name = icp_name.lower().strip()

        # Direct match
        if icp_name in self.categories:
            cat = self.categories[icp_name]
            keywords = list(cat.get('primary_keywords', []))
            if include_secondary:
                keywords.extend(cat.get('secondary_keywords', []))
            return keywords

        # Fuzzy match - check if ICP name is in category name or description
        for cat_name, cat_data in self.categories.items():
            if icp_name in cat_name or icp_name in cat_data.get('description', '').lower():
                keywords = list(cat_data.get('primary_keywords', []))
                if include_secondary:
                    keywords.extend(cat_data.get('secondary_keywords', []))
                return keywords

        # No match - return the input as-is (user's custom keyword)
        logger.debug(f"No ICP match for '{icp_name}', using as direct keyword")
        return [icp_name]

    def get_subreddits_for_icp(self, icp_name: str) -> List[str]:
        """Get relevant subreddits for an ICP category"""
        icp_name = icp_name.lower().strip()

        if icp_name in self.categories:
            return self.categories[icp_name].get('subreddits', [])

        # Fuzzy match
        for cat_name, cat_data in self.categories.items():
            if icp_name in cat_name or icp_name in cat_data.get('description', '').lower():
                return cat_data.get('subreddits', [])

        return []

    def build_fb_ads_url(self, keyword: str, country: str = "US") -> str:
        """
        Build a Facebook Ads Library URL with pre-set filters.

        Args:
            keyword: Search keyword
            country: Country code (default: US)

        Returns:
            Full URL with all parameters
        """
        encoded_keyword = urllib.parse.quote(keyword)
        return (
            f"https://www.facebook.com/ads/library/?"
            f"active_status=active&ad_type=all&country={country}"
            f"&is_targeted_country=false&media_type=all"
            f"&q={encoded_keyword}&search_type=keyword_unordered"
        )

    def build_reddit_search_url(self, subreddit: str, sort: str = "new", time_filter: str = "week") -> str:
        """
        Build a Reddit URL with recency filters.

        Args:
            subreddit: Subreddit name (without r/)
            sort: Sort method (new, top, hot)
            time_filter: Time filter for 'top' sort (hour, day, week, month, year, all)

        Returns:
            Full Reddit URL
        """
        subreddit = subreddit.lstrip('r/').lstrip('/')

        if sort == "top":
            return f"https://old.reddit.com/r/{subreddit}/top/?t={time_filter}"
        elif sort == "new":
            return f"https://old.reddit.com/r/{subreddit}/new/"
        else:
            return f"https://old.reddit.com/r/{subreddit}/{sort}/"

    def detect_icp_from_text(self, text: str) -> Optional[str]:
        """
        Detect ICP category from user input text.

        Args:
            text: User's request text

        Returns:
            Detected ICP category name or None
        """
        text_lower = text.lower()

        # Check each category
        for cat_name, cat_data in self.categories.items():
            # Check category name
            if cat_name in text_lower:
                return cat_name

            # Check primary keywords
            for keyword in cat_data.get('primary_keywords', []):
                if keyword.lower() in text_lower:
                    return cat_name

        return None

    def get_all_categories(self) -> List[str]:
        """Get list of all available ICP categories"""
        return list(self.categories.keys())

    def get_category_info(self, icp_name: str) -> Optional[Dict]:
        """Get full info for an ICP category"""
        return self.categories.get(icp_name.lower())


# Singleton instance
_helper_instance = None


def get_icp_helper() -> ICPKeywordHelper:
    """Get singleton ICP helper instance"""
    global _helper_instance
    if _helper_instance is None:
        _helper_instance = ICPKeywordHelper()
    return _helper_instance


# Convenience functions
def get_keywords(icp: str) -> List[str]:
    """Quick helper to get keywords for an ICP"""
    return get_icp_helper().get_keywords_for_icp(icp)


def get_fb_url(keyword: str, country: str = "US") -> str:
    """Quick helper to build FB Ads Library URL"""
    return get_icp_helper().build_fb_ads_url(keyword, country)


def get_reddit_url(subreddit: str, sort: str = "new") -> str:
    """Quick helper to build Reddit URL"""
    return get_icp_helper().build_reddit_search_url(subreddit, sort)
