"""
Site selector configuration for structured data extraction.

This module contains CSS selector patterns for known websites,
enabling accurate structured extraction without LLM guessing.
"""

from typing import Dict, Any, Optional


# Known site patterns mapped to CSS selectors for extraction
SITE_PATTERNS: Dict[str, Dict[str, Any]] = {
    # Hacker News
    "news.ycombinator.com": {
        "item_selector": ".athing",
        "field_selectors": {
            "title": ".titleline > a",
            "link": ".titleline > a@href",
            "rank": ".rank"
        },
        "limit": 30
    },

    # Amazon (any TLD)
    "amazon.": {
        "item_selector": "[data-component-type='s-search-result']",
        "field_selectors": {
            "title": "h2 a span",
            "price": ".a-price .a-offscreen",
            "rating": ".a-icon-star-small .a-icon-alt",
            "link": "h2 a@href"
        },
        "limit": 20
    },

    # eBay (any TLD)
    "ebay.": {
        "item_selector": ".s-item",
        "field_selectors": {
            "title": ".s-item__title",
            "price": ".s-item__price",
            "shipping": ".s-item__shipping",
            "link": ".s-item__link@href"
        },
        "limit": 20
    },

    # GitHub Trending (multiple fallback selectors for 2024/2025 layout)
    "github.com/trending": {
        "item_selector": "article.Box-row, div[data-hpc] > article, .Box-row",
        "field_selectors": {
            "repo": "h2 a@href, h1 a@href, .h3 a@href",
            "name": "h2 a, h1 a, .h3 a",
            "description": "p.col-9, p.my-1, p.color-fg-muted",
            "language": "[itemprop='programmingLanguage'], span[itemprop='programmingLanguage']",
            "stars": ".Link--muted.d-inline-block.mr-3, .octicon-star + span, a[href*='stargazers']"
        },
        "limit": 25
    },

    # Reddit - New Design (heavy JS, often blocked)
    "reddit.com": {
        "item_selector": "shreddit-post, article.Post",
        "field_selectors": {
            "title": "@post-title, h3[slot='title'], a[slot='full-post-link']",
            "author": "@author, a[href*='/user/']",
            "subreddit": "@subreddit-prefixed-name, a[href*='/r/']"
        },
        "limit": 15,
        "notes": "New Reddit is heavily JS-dependent and blocks automation. Prefer RSS/JSON API."
    },

    # Reddit - Old Design (lightweight, more reliable for scraping)
    "old.reddit.com": {
        "item_selector": ".thing.link, .link",
        "field_selectors": {
            "title": "a.title, p.title a",
            "author": ".author, a.author",
            "subreddit": ".subreddit, a.subreddit",
            "score": ".score.unvoted, .score",
            "comments": ".comments, a.comments",
            "time": "time@datetime, time@title",
            "link": "a.title@href"
        },
        "limit": 25,
        "notes": "old.reddit.com is lighter and more reliable for scraping"
    },

    # Reddit Comments Page
    "reddit.com/comments": {
        "item_selector": ".thing.comment, .Comment",
        "field_selectors": {
            "author": ".author, a[href*='/user/']",
            "body": ".usertext-body, div[data-testid='comment']",
            "score": ".score, span[id*='score']",
            "time": "time@datetime"
        },
        "limit": 50
    },

    # LinkedIn job listings
    "linkedin.com/jobs": {
        "item_selector": ".jobs-search-results__list-item, .job-card-container",
        "field_selectors": {
            "title": ".job-card-list__title, .job-card-container__link",
            "company": ".job-card-container__company-name, .artdeco-entity-lockup__subtitle",
            "location": ".job-card-container__metadata-item, .job-card-container__metadata-wrapper",
            "link": "a@href"
        },
        "limit": 25
    },

    # LinkedIn people search
    "linkedin.com/search/results/people": {
        "item_selector": ".reusable-search__result-container, .search-result__wrapper, li.reusable-search__result-container",
        "field_selectors": {
            "name": ".entity-result__title-text a span span:first-child, .app-aware-link span[dir='ltr'] span[aria-hidden='true']",
            "title": ".entity-result__primary-subtitle, .entity-result__summary",
            "company": ".entity-result__secondary-subtitle",
            "profile_link": "a.app-aware-link@href, .entity-result__title-text a@href",
            "location": ".entity-result__secondary-subtitle + div"
        },
        "limit": 25
    },

    # LinkedIn company search
    "linkedin.com/search/results/companies": {
        "item_selector": ".reusable-search__result-container",
        "field_selectors": {
            "name": ".entity-result__title-text a span span:first-child",
            "industry": ".entity-result__primary-subtitle",
            "location": ".entity-result__secondary-subtitle",
            "company_link": "a.app-aware-link@href"
        },
        "limit": 25
    },

    # Twitter/X posts
    "twitter.com": {
        "item_selector": "[data-testid='tweet'], article",
        "field_selectors": {
            "author": "[data-testid='User-Name'] span, .css-1qaijid",
            "text": "[data-testid='tweetText'], .css-1jxf684",
            "time": "time@datetime"
        },
        "limit": 20
    },

    "x.com": {
        "item_selector": "[data-testid='tweet'], article",
        "field_selectors": {
            "author": "[data-testid='User-Name'] span",
            "text": "[data-testid='tweetText']",
            "time": "time@datetime"
        },
        "limit": 20
    },

    # Product Hunt (React structure with multiple fallback selectors for 2024/2025)
    "producthunt.com": {
        "item_selector": "[data-test='post-item'], div[class*='styles_item'], div[class*='post-item'], section[class*='post'], article, div[class*='PostItem'], main section > div > div",
        "field_selectors": {
            "name": "[data-test='post-name'], a[class*='title'], h3 a, h2 a, strong a, [class*='productName'], a[href^='/posts/']",
            "tagline": "[data-test='tagline'], p[class*='tagline'], [class*='description'], div[class*='Tagline']",
            "votes": "[data-test='vote-button'] span, button[class*='vote'] span, [class*='voteCount'], [class*='upvote']",
            "link": "a[href^='/posts/']@href, a[data-test='post-name']@href"
        },
        "limit": 20
    },

    # Craigslist listings
    "craigslist.org": {
        "item_selector": ".result-row, .cl-static-search-result",
        "field_selectors": {
            "title": ".result-title, .titlestring",
            "price": ".result-price, .priceinfo",
            "location": ".result-hood, .meta",
            "link": "a@href"
        },
        "limit": 50
    },

    # Zillow property listings
    "zillow.com": {
        "item_selector": "[data-test='property-card'], .list-card",
        "field_selectors": {
            "price": "[data-test='property-card-price'], .list-card-price",
            "address": "address, .list-card-addr",
            "beds": "[data-test='property-card-bed']",
            "baths": "[data-test='property-card-bath']",
            "link": "a@href"
        },
        "limit": 40
    },

    # Indeed job listings
    "indeed.com": {
        "item_selector": ".job_seen_beacon, .jobsearch-ResultsList > li",
        "field_selectors": {
            "title": ".jobTitle span, h2.jobTitle",
            "company": ".companyName, [data-testid='company-name']",
            "location": ".companyLocation",
            "salary": ".salary-snippet-container, .metadata .attribute_snippet"
        },
        "limit": 25
    },

    # Yelp business listings
    "yelp.com": {
        "item_selector": "[data-testid='serp-ia-card'], .container__09f24__mpR8_",
        "field_selectors": {
            "name": "h3 a, .css-19v1rkv",
            "rating": "[aria-label*='star rating']@aria-label",
            "category": ".priceCategory, .css-11bijt4"
        },
        "limit": 20
    },

    # Stack Overflow questions (2024/2025 redesign)
    "stackoverflow.com": {
        "item_selector": ".s-post-summary, .js-post-summary, [id^='question-summary-']",
        "field_selectors": {
            "title": ".s-post-summary--content-title a, .s-link, h3 a, a.question-hyperlink",
            "votes": ".s-post-summary--stats-item-number, .vote-count-post, .js-vote-count",
            "answers": ".s-post-summary--stats-item-number:nth-child(2), .status strong",
            "link": "h3 a@href, .s-post-summary--content-title a@href, a.question-hyperlink@href"
        },
        "limit": 30
    },

    # Etsy product listings
    "etsy.com": {
        "item_selector": ".wt-grid__item-xs-6, .v2-listing-card",
        "field_selectors": {
            "title": ".v2-listing-card__title, h3",
            "price": ".currency-value, .lc-price span",
            "shop": ".v2-listing-card__shop, .wt-text-caption"
        },
        "limit": 40
    },

    # Google search results
    "google.com/search": {
        "item_selector": ".g, [data-sokoban-container]",
        "field_selectors": {
            "title": "h3",
            "snippet": ".VwiC3b, [data-sncf]",
            "link": "a@href"
        },
        "limit": 10
    },

    # Yahoo Finance stock quotes
    "finance.yahoo.com/quote": {
        "item_selector": "[data-testid='quote-statistics'], #quote-summary",
        "field_selectors": {
            "price": "[data-field='regularMarketPrice'], [data-test='qsp-price']",
            "change": "[data-field='regularMarketChange']",
            "change_percent": "[data-field='regularMarketChangePercent']",
            "prev_close": "[data-field='regularMarketPreviousClose']",
            "open": "[data-field='regularMarketOpen']",
            "volume": "[data-field='regularMarketVolume']",
            "market_cap": "[data-field='marketCap']",
            "pe_ratio": "[data-field='trailingPE']",
            "eps": "[data-field='epsTrailingTwelveMonths']",
            "dividend": "[data-field='dividendYield']",
            "52w_high": "[data-field='fiftyTwoWeekHigh']",
            "52w_low": "[data-field='fiftyTwoWeekLow']"
        },
        "limit": 1
    },

    # GreatSchools school ratings
    "greatschools.org": {
        "item_selector": ".school-card, .search-result-card",
        "field_selectors": {
            "name": ".school-name, h3",
            "rating": ".rs-gs-rating__number, .circle-rating--large",
            "grades": ".school-info, .grade-range",
            "address": ".school-address, .address"
        },
        "limit": 20
    },

    # OSHA regulations
    "osha.gov": {
        "item_selector": ".standard-link, .regulation-link, li",
        "field_selectors": {
            "title": "a",
            "number": ".standard-number",
            "link": "a@href"
        },
        "limit": 30
    },

    # Wikipedia articles
    "wikipedia.org": {
        "item_selector": "#mw-content-text p, .mw-parser-output > p",
        "field_selectors": {
            "text": "p",
            "heading": "h2 .mw-headline, h3 .mw-headline"
        },
        "limit": 10
    },

    # USA.gov benefits
    "usa.gov": {
        "item_selector": ".usa-card, .card, article",
        "field_selectors": {
            "title": "h2, h3, .card-title",
            "description": "p, .card-body",
            "link": "a@href"
        },
        "limit": 20
    },

    # Books to Scrape (test site for e-commerce)
    "books.toscrape.com": {
        "item_selector": ".product_pod, article.product_pod",
        "field_selectors": {
            "title": "h3 a@title, h3 a",
            "price": ".price_color, .product_price .price_color",
            "availability": ".availability, .instock",
            "rating": ".star-rating@class",
            "link": "h3 a@href"
        },
        "limit": 20
    },

    # YouTube video results
    "youtube.com": {
        "item_selector": "ytd-video-renderer, ytd-rich-item-renderer, #contents ytd-video-renderer",
        "field_selectors": {
            "title": "#video-title, #title a, a#video-title",
            "channel": "#channel-name a, .ytd-channel-name a, #text.ytd-channel-name",
            "views": "#metadata-line span:first-child, .ytd-video-meta-block span",
            "link": "#video-title@href, a#video-title@href"
        },
        "limit": 20
    },

    # DuckDuckGo search results
    "duckduckgo.com": {
        "item_selector": "article[data-testid='result'], .result",
        "field_selectors": {
            "title": "h2 a, .result__title a",
            "snippet": "[data-result='snippet'], .result__snippet",
            "link": "h2 a@href, .result__title a@href"
        },
        "limit": 10
    },

    # Bing search results
    "bing.com": {
        "item_selector": ".b_algo, #b_results > li.b_algo",
        "field_selectors": {
            "title": "h2 a, .b_algo h2 a",
            "snippet": ".b_caption p, .b_algoSlug",
            "link": "h2 a@href"
        },
        "limit": 10
    },

    # Medium articles
    "medium.com": {
        "item_selector": "article, div[data-post-id], .postArticle",
        "field_selectors": {
            "title": "h2, h3, .graf--title",
            "author": "[data-testid='authorName'], .postMetaInline-authorLockup a",
            "summary": "p.graf--p:first-of-type, h4.graf--subtitle",
            "link": "a[data-action='open-post']@href, h2 a@href"
        },
        "limit": 15
    },

    # Hacker News (alternative patterns)
    "ycombinator.com": {
        "item_selector": ".athing, tr.athing",
        "field_selectors": {
            "title": ".titleline > a, .storylink",
            "link": ".titleline > a@href, .storylink@href",
            "rank": ".rank"
        },
        "limit": 30
    },

    # Google Maps search results
    "google.com/maps": {
        "item_selector": "div[role='article'], a[href*='/maps/place/']",
        "field_selectors": {
            "business_name": "div[aria-label]:first-of-type, .fontHeadlineSmall, div.fontHeadlineLarge",
            "address": "div[aria-label*='Address'], .fontBodyMedium",
            "phone": "div[aria-label*='Phone'], button[aria-label*='Phone']",
            "website": "a[aria-label*='Website']@href",
            "rating": "span[role='img'][aria-label*='stars']@aria-label",
            "reviews": "span[aria-label*='reviews']",
            "url": "a[href*='/maps/place/']@href"
        },
        "limit": 20
    }
}


# Interactive element selectors for common sites
# Used when generic selector descriptions like "search box" are passed
SITE_INTERACTION_SELECTORS: Dict[str, Dict[str, list]] = {
    "google.com": {
        "search_input": [
            'textarea[name="q"]',
            'input[name="q"]',
            'textarea[aria-label*="Search"]',
            'textarea.gLFyf',
            '#APjFqb',
            'input[aria-label*="Search"]',
        ],
        "search_button": [
            'input[name="btnK"]',
            'button[aria-label*="Search"]',
            'input[type="submit"]',
            '.FPdoLc input[type="submit"]',
        ],
    },
    "bing.com": {
        "search_input": [
            '#sb_form_q',
            'input[name="q"]',
            'textarea[name="q"]',
        ],
        "search_button": [
            '#sb_form_go',
            '#search_icon',
        ],
    },
    "duckduckgo.com": {
        "search_input": [
            '#searchbox_input',
            'input[name="q"]',
        ],
        "search_button": [
            'button[aria-label="Search"]',
            '[type="submit"]',
        ],
    },
    "linkedin.com": {
        "search_input": [
            'input[aria-label*="Search"]',
            '.search-global-typeahead__input',
            '#global-nav-search input',
        ],
    },
    "twitter.com": {
        "search_input": [
            'input[aria-label*="Search"]',
            'input[data-testid="SearchBox_Search_Input"]',
        ],
    },
    "x.com": {
        "search_input": [
            'input[aria-label*="Search"]',
            'input[data-testid="SearchBox_Search_Input"]',
        ],
    },
    "youtube.com": {
        "search_input": [
            'input#search',
            'input[name="search_query"]',
        ],
        "search_button": [
            '#search-icon-legacy',
            'button#search-button',
        ],
    },
    "amazon.": {
        "search_input": [
            '#twotabsearchtextbox',
            'input[name="field-keywords"]',
        ],
        "search_button": [
            '#nav-search-submit-button',
            'input[type="submit"]',
        ],
    },
    "facebook.com": {
        "search_input": [
            'input[aria-label*="Search"]',
            'input[placeholder*="Search"]',
        ],
    },
    "stackoverflow.com": {
        "search_input": [
            'input[name="q"]',
            'input.s-input__search',
            '#search input',
            'input[placeholder*="Search"]',
        ],
    },
    "reddit.com": {
        "search_input": [
            'input[name="q"]',
            '#search-input',
            'input[placeholder*="Search"]',
        ],
    },
    "wikipedia.org": {
        "search_input": [
            '#searchInput',
            'input[name="search"]',
            'input[placeholder*="Search"]',
        ],
        "search_button": [
            '#searchButton',
            'button[type="submit"]',
        ],
    },
}


def get_interaction_selectors(url: str, element_type: str = "search_input") -> list:
    """
    Get interaction selectors for a site based on URL.

    Args:
        url: The current page URL
        element_type: Type of element ("search_input", "search_button", etc.)

    Returns:
        List of CSS selectors to try, ordered by priority
    """
    if not url:
        return []

    url_lower = url.lower()
    for site_pattern, selectors in SITE_INTERACTION_SELECTORS.items():
        if site_pattern in url_lower:
            return selectors.get(element_type, [])

    return []


def get_site_selectors(url: str) -> Optional[Dict[str, Any]]:
    """
    Get CSS selectors for a known site to enable accurate structured extraction.

    Args:
        url: The URL to check against known patterns

    Returns:
        Dictionary with selector configuration if site is recognized, None otherwise.
        Structure:
        {
            "item_selector": str,           # CSS selector for item containers
            "field_selectors": dict,        # Field name -> CSS selector mapping
            "limit": int                    # Maximum items to extract
        }

    Example:
        >>> selectors = get_site_selectors("https://news.ycombinator.com")
        >>> print(selectors["item_selector"])
        '.athing'
        >>> print(selectors["field_selectors"]["title"])
        '.titleline > a'
    """
    if not url:
        return None

    # Check if URL matches any known pattern
    url_lower = url.lower()
    for pattern, selectors in SITE_PATTERNS.items():
        if pattern in url_lower:
            return selectors

    return None
