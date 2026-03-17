"""
Training Task Generator - Creates diverse tasks for self-play training.

Like AlphaGo generating game positions, this generates web automation tasks
of varying complexity for the agent to practice on.

FREE WILL MODE:
- Novelty seeking: Prefers tasks different from recent ones
- Curiosity: Re-tries failed tasks with mutations
- Exploration: Random creative tasks
- Anti-circle: Tracks what's been tried, avoids repetition
"""

import random
import hashlib
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TrainingTask:
    """A task for the agent to practice on."""
    prompt: str
    domain: str
    difficulty: str  # easy, medium, hard
    category: str  # navigation, extraction, form, search, multi-step
    expected_skills: List[str]  # Skills this should exercise
    success_criteria: str  # How to evaluate success


class TaskGenerator:
    """
    Generates training tasks of varying difficulty and type.

    Principles:
    1. Start simple, increase complexity
    2. Cover all skill areas
    3. Include edge cases and failure scenarios
    4. Mix real-world and synthetic tasks
    """

    # Safe practice domains (public sites, no login required)
    PRACTICE_DOMAINS = [
        'wikipedia.org',
        'news.ycombinator.com',
        'reddit.com',
        'github.com',
        'stackoverflow.com',
        'imdb.com',
        'weather.com',
        'quotes.toscrape.com',  # Practice scraping site
        'books.toscrape.com',   # Practice scraping site
        'httpbin.org',          # API testing
        'example.com',          # Simple baseline
        'crunchbase.com',       # Company data (public pages)
        'producthunt.com',      # Product listings
        'ycombinator.com',      # Startup directory
    ]

    # SDR-specific practice sites (public company directories)
    SDR_PRACTICE_SITES = [
        'crunchbase.com/discover/organization.companies',
        'producthunt.com/products',
        'ycombinator.com/companies',
        'github.com/trending',
        'news.ycombinator.com/show',
    ]

    # HIGH PRIORITY: Core SDR domains
    PRIORITY_DOMAINS = {
        'reddit': [
            'old.reddit.com',  # Less JS, more reliable
            'reddit.com',
            'reddit.com/r/sales',
            'reddit.com/r/startups',
            'reddit.com/r/entrepreneur',
        ],
        'linkedin': [
            # LinkedIn blocks scrapers, but we can practice patterns on similar sites
            'linkedin.com/company/google',  # Public company pages work
            'linkedin.com/jobs',  # Job search is public
            # Workarounds - sites with similar structure
            'wellfound.com',  # AngelList - similar to LinkedIn for startups
            'glassdoor.com/Explore/top-companies',  # Company profiles
        ],
        'facebook_ads': [
            'facebook.com/ads/library',  # The actual ads library
            'facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=all',
        ]
    }

    # Task templates by category and difficulty
    TASK_TEMPLATES = {
        'navigation': {
            'easy': [
                ("Go to {domain} and take a screenshot", ['navigate', 'screenshot']),
                ("Visit {domain} and tell me the page title", ['navigate', 'extract']),
                ("Navigate to {domain}", ['navigate']),
            ],
            'medium': [
                ("Go to {domain} and find the search bar", ['navigate', 'locate_element']),
                ("Visit {domain} and scroll to the bottom of the page", ['navigate', 'scroll']),
                ("Go to {domain} and click on the first link", ['navigate', 'click']),
            ],
            'hard': [
                ("Go to {domain}, find the navigation menu, and list all menu items", ['navigate', 'extract', 'multiple_elements']),
                ("Navigate to {domain} and extract all external links", ['navigate', 'extract', 'filter']),
            ]
        },
        'extraction': {
            'easy': [
                ("Go to {domain} and extract the main heading", ['navigate', 'extract_text']),
                ("Visit {domain} and get the page description", ['navigate', 'extract']),
            ],
            'medium': [
                ("Go to {domain} and extract all article titles", ['navigate', 'extract', 'multiple']),
                ("Visit {domain} and save a screenshot of the main content area", ['navigate', 'screenshot', 'selector']),
                ("Go to books.toscrape.com and extract the titles and prices of the first 5 books", ['navigate', 'extract', 'structured_data']),
            ],
            'hard': [
                ("Go to quotes.toscrape.com and extract all quotes with their authors, save to CSV", ['navigate', 'extract', 'csv', 'pagination']),
                ("Visit news.ycombinator.com and extract the top 10 posts with titles, points, and links", ['navigate', 'extract', 'structured_data', 'multiple']),
                ("Go to books.toscrape.com, navigate through categories, and extract book data", ['navigate', 'click', 'extract', 'multi_step']),
            ]
        },
        'search': {
            'easy': [
                ("Go to wikipedia.org and search for 'Python programming'", ['navigate', 'search', 'type']),
                ("Visit github.com and search for 'machine learning'", ['navigate', 'search']),
            ],
            'medium': [
                ("Go to stackoverflow.com, search for 'async python', and extract the first result title", ['navigate', 'search', 'extract']),
                ("Search on reddit.com for 'artificial intelligence' and list the first 3 posts", ['navigate', 'search', 'extract', 'multiple']),
            ],
            'hard': [
                ("Go to news.ycombinator.com, search for 'AI', filter by new, and extract titles", ['navigate', 'search', 'filter', 'extract']),
                ("Search wikipedia for 'Neural network', go to the page, extract the introduction paragraph", ['navigate', 'search', 'click', 'extract']),
            ]
        },
        'interaction': {
            'easy': [
                ("Go to {domain} and click on any article link", ['navigate', 'click']),
                ("Visit {domain} and hover over the main navigation", ['navigate', 'hover']),
            ],
            'medium': [
                ("Go to httpbin.org/forms/post and fill in the form with test data", ['navigate', 'fill_form', 'type']),
                ("Visit quotes.toscrape.com and navigate to page 2 using pagination", ['navigate', 'click', 'pagination']),
            ],
            'hard': [
                ("Go to books.toscrape.com, add a book to cart (if possible), take screenshot of cart", ['navigate', 'click', 'multi_step', 'screenshot']),
                ("Visit quotes.toscrape.com, navigate through 3 pages, extract all quotes", ['navigate', 'click', 'extract', 'loop']),
            ]
        },
        'error_recovery': {
            'easy': [
                ("Try to navigate to nonexistent.fake.domain and handle the error gracefully", ['navigate', 'error_handling']),
            ],
            'medium': [
                ("Go to httpbin.org/status/404 and report what you observe", ['navigate', 'error_handling', 'report']),
                ("Navigate to httpbin.org/delay/10 with a 5 second timeout and handle it", ['navigate', 'timeout', 'error_handling']),
            ],
            'hard': [
                ("Go to httpbin.org/status/500, retry 3 times, then try httpbin.org as fallback", ['navigate', 'retry', 'fallback', 'error_handling']),
            ]
        },
        'analysis': {
            'easy': [
                ("Go to {domain} and describe what you see in 2-3 sentences", ['navigate', 'analyze', 'summarize']),
            ],
            'medium': [
                ("Visit {domain}, analyze the page structure, and identify the main content areas", ['navigate', 'analyze', 'structure']),
                ("Go to {domain} and evaluate how user-friendly the navigation is", ['navigate', 'analyze', 'evaluate']),
            ],
            'hard': [
                ("Go to {domain}, compare its layout to a typical site structure, identify improvements", ['navigate', 'analyze', 'compare', 'recommend']),
                ("Visit two news sites and compare their headline presentation styles", ['navigate', 'compare', 'multi_site']),
            ]
        },
        # NEW: SDR-specific tasks (closer to real use case)
        'sdr_prospecting': {
            'easy': [
                ("Go to ycombinator.com/companies and take a screenshot of the company list", ['navigate', 'screenshot']),
                ("Visit producthunt.com and identify where product names are displayed", ['navigate', 'analyze']),
            ],
            'medium': [
                ("Go to ycombinator.com/companies, extract the names of the first 5 companies visible", ['navigate', 'extract', 'multiple']),
                ("Visit github.com/trending and extract repository names and star counts", ['navigate', 'extract', 'structured_data']),
                ("Go to news.ycombinator.com/show, extract titles and point counts for top 5 posts", ['navigate', 'extract', 'multiple']),
            ],
            'hard': [
                ("Go to ycombinator.com/companies, filter by a category if possible, and extract company data", ['navigate', 'filter', 'extract', 'multi_step']),
                ("Visit producthunt.com, find today's top products, extract names and taglines", ['navigate', 'filter', 'extract', 'time_based']),
                ("Go to github.com/trending, extract repo info, then visit one repo and get description", ['navigate', 'extract', 'click', 'multi_page']),
            ]
        },
        'data_entry': {
            'easy': [
                ("Go to httpbin.org/forms/post and identify all form fields", ['navigate', 'analyze']),
            ],
            'medium': [
                ("Go to httpbin.org/forms/post and fill the customer name field with 'Test User'", ['navigate', 'type', 'fill_form']),
                ("Visit httpbin.org/forms/post and complete all text fields with test data", ['navigate', 'fill_form', 'multiple_fields']),
            ],
            'hard': [
                ("Go to httpbin.org/forms/post, fill all fields, submit, and verify submission worked", ['navigate', 'fill_form', 'submit', 'verify']),
            ]
        },
        'table_extraction': {
            'easy': [
                ("Go to wikipedia.org/wiki/List_of_countries_by_population_(United_Nations) and identify the main table", ['navigate', 'locate_element']),
            ],
            'medium': [
                ("Visit wikipedia.org/wiki/List_of_countries_by_GDP_(nominal) and extract the top 5 countries", ['navigate', 'extract', 'table']),
                ("Go to books.toscrape.com and extract title + price for all visible books", ['navigate', 'extract', 'multiple']),
            ],
            'hard': [
                ("Go to wikipedia.org, find a table with numerical data, extract it and save to CSV", ['navigate', 'search', 'extract', 'csv']),
                ("Visit books.toscrape.com, navigate multiple pages, extract all book data", ['navigate', 'pagination', 'extract', 'multi_page']),
            ]
        },
        # PRIORITY: Reddit tasks
        'reddit': {
            'easy': [
                ("Go to old.reddit.com and take a screenshot of the front page", ['navigate', 'screenshot']),
                ("Visit reddit.com/r/startups and identify the post listing area", ['navigate', 'analyze']),
                ("Go to reddit.com and extract the titles of the first 3 posts", ['navigate', 'extract']),
            ],
            'medium': [
                ("Go to old.reddit.com/r/sales and extract post titles and vote counts for top 5 posts", ['navigate', 'extract', 'multiple']),
                ("Visit reddit.com/r/entrepreneur, sort by top of the week if possible, extract titles", ['navigate', 'filter', 'extract']),
                ("Go to reddit.com/r/startups and extract post titles, authors, and comment counts", ['navigate', 'extract', 'structured_data']),
            ],
            'hard': [
                ("Go to reddit.com/r/sales, find posts mentioning 'cold email', extract titles and links", ['navigate', 'search', 'extract', 'filter']),
                ("Visit old.reddit.com/r/startups, navigate to a specific post, extract all top-level comments", ['navigate', 'click', 'extract', 'multi_step']),
                ("Go to reddit.com/r/entrepreneur, extract top 10 posts with titles, scores, comment counts, save to CSV", ['navigate', 'extract', 'csv', 'multiple']),
            ]
        },
        # PRIORITY: LinkedIn-style tasks (using public pages + workaround sites)
        'linkedin_style': {
            'easy': [
                ("Go to linkedin.com/jobs and take a screenshot", ['navigate', 'screenshot']),
                ("Visit wellfound.com (AngelList) and identify where company names are listed", ['navigate', 'analyze']),
                ("Go to glassdoor.com and find the company search feature", ['navigate', 'locate_element']),
            ],
            'medium': [
                ("Go to linkedin.com/jobs, search for 'sales', extract first 5 job titles", ['navigate', 'search', 'extract']),
                ("Visit wellfound.com/companies, extract company names from the first page", ['navigate', 'extract', 'multiple']),
                ("Go to glassdoor.com/Explore/top-companies and extract company names and ratings", ['navigate', 'extract', 'structured_data']),
            ],
            'hard': [
                ("Go to linkedin.com/company/google, extract company description and employee count if visible", ['navigate', 'extract', 'company_data']),
                ("Visit wellfound.com, search for 'AI startups', extract company names and descriptions", ['navigate', 'search', 'extract', 'filter']),
                ("Go to linkedin.com/jobs, search for 'SDR', filter by location if possible, extract job data", ['navigate', 'search', 'filter', 'extract']),
            ]
        },
        # PRIORITY: Facebook Ads Library tasks - using FAST extraction tools
        'facebook_ads': {
            'easy': [
                ("Go to https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US and use playwright_extract_fb_ads to get advertiser list", ['navigate', 'fast_extract']),
                ("Navigate to FB Ads Library for 'software' and count how many advertisers have website URLs using playwright_extract_fb_ads", ['navigate', 'fast_extract', 'count']),
            ],
            'medium': [
                ("Go to https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=shopify, use playwright_extract_fb_ads, report count and first 3 advertiser names", ['navigate', 'fast_extract', 'report']),
                ("Navigate to FB Ads Library for 'ecommerce', extract all advertisers in ONE call, filter those with websiteUrl", ['navigate', 'fast_extract', 'filter']),
            ],
            'hard': [
                ("Go to FB Ads Library for 'CRM', use playwright_extract_fb_ads, visit first advertiser website, use playwright_extract_page_fast to get contact info", ['navigate', 'fast_extract', 'multi_site', 'fast_contact']),
                ("Navigate to FB Ads Library for 'saas', extract advertisers, visit top 3 with websites, get preferredContact from each using playwright_extract_page_fast, save CSV", ['navigate', 'fast_extract', 'batch_contact', 'csv']),
            ]
        },
        # PRIORITY: Reddit warm-prospect tasks - using FAST extraction
        'reddit_warm': {
            'easy': [
                ("Go to https://old.reddit.com/r/entrepreneur/new/ and use playwright_extract_reddit to get all posts with warm signals", ['navigate', 'fast_extract']),
                ("Navigate to old.reddit.com/r/sales/new, use playwright_extract_reddit, report warmCount", ['navigate', 'fast_extract', 'report']),
            ],
            'medium': [
                ("Go to old.reddit.com/r/startups/new, use playwright_extract_reddit, filter for isWarm=true, list usernames", ['navigate', 'fast_extract', 'filter']),
                ("Navigate to old.reddit.com/r/SaaS/new, extract all posts, report which have 'recommend' or 'looking for' in warmSignals", ['navigate', 'fast_extract', 'warm_analysis']),
            ],
            'hard': [
                ("Go to old.reddit.com/r/entrepreneur/new, use playwright_extract_reddit, filter warm prospects, save CSV with username, profileUrl, title, warmSignals", ['navigate', 'fast_extract', 'filter', 'csv']),
                ("Navigate to old.reddit.com/r/ecommerce/new, extract posts, filter warmCount > 0, format as prospect list with engagement scores", ['navigate', 'fast_extract', 'scoring', 'csv']),
            ]
        }
    }

    # Self-evaluation tasks - agent reviews its own work
    SELF_EVAL_TEMPLATES = [
        "Review the previous task execution and identify what could be improved",
        "Analyze the selectors used in the last task - were they optimal?",
        "Evaluate the extraction accuracy - was any data missed?",
        "Review error handling - was recovery appropriate?",
        "Assess efficiency - could fewer steps have achieved the same result?",
    ]

    # Meta-learning tasks - agent improves its own strategies
    META_LEARNING_TEMPLATES = [
        "Based on recent successes, what patterns should be added to the playbook?",
        "What strategies consistently failed and should be removed?",
        "Which domains need more specific strategies?",
        "What error recovery patterns have been most effective?",
    ]

    # Priority categories get more training time
    PRIORITY_CATEGORIES = ['reddit', 'reddit_warm', 'linkedin_style', 'facebook_ads', 'sdr_prospecting']
    PRIORITY_WEIGHT = 3  # 3x more likely to be selected

    # Creative task mutations - combine actions in new ways
    CREATIVE_MUTATIONS = [
        "and take a screenshot of the results",
        "and save the data to a CSV file",
        "and count how many items you found",
        "and describe what you observe",
        "and click on the first result",
        "and scroll down to see more",
        "and try a different search term if no results",
        "and extract any email addresses visible",
        "and note any error messages",
        "and compare to what you expected",
    ]

    # Completely novel/creative exploration tasks
    EXPLORATION_TASKS = [
        ("Go to {domain} and find something interesting that wasn't asked for", ['explore', 'discover']),
        ("Visit {domain} and identify potential improvements to the page", ['analyze', 'creative']),
        ("Go to {domain} and try to break something (safely)", ['test', 'edge_case']),
        ("Navigate to {domain} using an unusual method", ['creative', 'navigate']),
        ("Go to {domain} and extract data in a format you haven't tried before", ['creative', 'extract']),
        ("Visit {domain} and find hidden or less obvious content", ['explore', 'discover']),
        ("Go to {domain} and describe it as if explaining to someone who can't see", ['analyze', 'describe']),
    ]

    def __init__(self, difficulty_distribution: Dict[str, float] = None):
        """
        Initialize with difficulty distribution.

        Args:
            difficulty_distribution: {'easy': 0.3, 'medium': 0.5, 'hard': 0.2}
        """
        self.difficulty_distribution = difficulty_distribution or {
            'easy': 0.3,
            'medium': 0.5,
            'hard': 0.2
        }
        self.task_history = []
        self.category_counts = {cat: 0 for cat in self.TASK_TEMPLATES.keys()}

        # FREE WILL: Anti-circle tracking
        self.tried_task_hashes: Set[str] = set()  # Fingerprints of tried tasks
        self.failed_tasks: List[TrainingTask] = []  # Tasks to retry with mutations
        self.recent_categories: List[str] = []  # Last N categories (for novelty)
        self.recent_domains: List[str] = []  # Last N domains
        self.exploration_rate = 0.15  # 15% chance of pure exploration
        self.mutation_rate = 0.20  # 20% chance of mutating a task
        self.curiosity_rate = 0.10  # 10% chance of retrying failed task

    def _hash_task(self, prompt: str) -> str:
        """Create fingerprint of task to detect repeats."""
        # Normalize and hash
        normalized = prompt.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def _is_novel(self, task: TrainingTask) -> bool:
        """Check if task is sufficiently different from recent tasks."""
        task_hash = self._hash_task(task.prompt)

        # Exact repeat?
        if task_hash in self.tried_task_hashes:
            return False

        # Same category too many times recently?
        if self.recent_categories.count(task.category) >= 3:
            return False

        # Same domain too many times recently?
        if self.recent_domains.count(task.domain) >= 4:
            return False

        return True

    def _record_task(self, task: TrainingTask):
        """Record task for anti-circle tracking."""
        self.tried_task_hashes.add(self._hash_task(task.prompt))

        self.recent_categories.append(task.category)
        if len(self.recent_categories) > 10:
            self.recent_categories.pop(0)

        self.recent_domains.append(task.domain)
        if len(self.recent_domains) > 15:
            self.recent_domains.pop(0)

    def record_failure(self, task: TrainingTask):
        """Record a failed task for curiosity-driven retry."""
        if len(self.failed_tasks) < 20:  # Keep last 20 failures
            self.failed_tasks.append(task)

    def _mutate_task(self, task: TrainingTask) -> TrainingTask:
        """Mutate a task to try it differently."""
        mutation = random.choice(self.CREATIVE_MUTATIONS)
        new_prompt = task.prompt.rstrip('.') + ', ' + mutation

        return TrainingTask(
            prompt=new_prompt,
            domain=task.domain,
            difficulty=task.difficulty,
            category=task.category,
            expected_skills=task.expected_skills + ['mutation'],
            success_criteria=task.success_criteria + " (mutated)"
        )

    def _generate_exploration_task(self) -> TrainingTask:
        """Generate a completely novel exploration task."""
        template, skills = random.choice(self.EXPLORATION_TASKS)
        domain = random.choice(self.PRACTICE_DOMAINS + list(self.PRIORITY_DOMAINS.get('reddit', [])))
        prompt = template.format(domain=domain)

        return TrainingTask(
            prompt=prompt,
            domain=domain,
            difficulty='hard',
            category='exploration',
            expected_skills=skills,
            success_criteria="Discover something new or interesting"
        )

    def _retry_failed_with_variation(self) -> TrainingTask:
        """Retry a failed task with a different approach."""
        if not self.failed_tasks:
            return self._generate_exploration_task()

        failed = random.choice(self.failed_tasks)

        # Create variation
        variations = [
            f"Try again: {failed.prompt} (use a different approach)",
            f"Alternative method: {failed.prompt.replace('Go to', 'Navigate to')}",
            f"{failed.prompt} - if the first method fails, try scrolling first",
            f"{failed.prompt} - wait for page to fully load before acting",
        ]

        new_prompt = random.choice(variations)

        return TrainingTask(
            prompt=new_prompt,
            domain=failed.domain,
            difficulty=failed.difficulty,
            category=failed.category,
            expected_skills=failed.expected_skills + ['retry', 'alternative'],
            success_criteria=failed.success_criteria + " (retry)"
        )

    def generate_task(self,
                      preferred_category: str = None,
                      preferred_difficulty: str = None,
                      avoid_recent: bool = True) -> TrainingTask:
        """
        Generate a single training task with FREE WILL.

        Features:
        - 15% pure exploration (creative new tasks)
        - 10% curiosity (retry failed tasks differently)
        - 20% mutation (add twists to base tasks)
        - Anti-circle: Never exact repeats, varies categories/domains
        - Quarantine: Skips unreliable/blocked sites
        """
        # Import quarantine checker
        from training.negative_examples import get_negative_store
        negative_store = get_negative_store()

        # FREE WILL: Random exploration
        if random.random() < self.exploration_rate:
            task = self._generate_exploration_task()
            # Check quarantine
            if not self._is_quarantined(task, negative_store):
                self._record_task(task)
                self.task_history.append(task)
                return task

        # FREE WILL: Curiosity - retry failures with variation
        if random.random() < self.curiosity_rate and self.failed_tasks:
            task = self._retry_failed_with_variation()
            # Check quarantine
            if not self._is_quarantined(task, negative_store):
                self._record_task(task)
                self.task_history.append(task)
                return task

        # Generate base task (with retries for novelty AND quarantine)
        max_attempts = 15  # Increased to handle quarantine rejections
        for attempt in range(max_attempts):
            task = self._generate_base_task(preferred_category, preferred_difficulty)

            # Check novelty AND quarantine
            is_novel = self._is_novel(task) or attempt == max_attempts - 1
            is_safe = not self._is_quarantined(task, negative_store)

            if is_novel and is_safe:
                break

        # FREE WILL: Mutation - add creative twists
        if random.random() < self.mutation_rate:
            task = self._mutate_task(task)

        # Record for anti-circle
        self._record_task(task)
        self.task_history.append(task)

        # Track category counts
        if task.category in self.category_counts:
            self.category_counts[task.category] += 1

        return task

    def _is_quarantined(self, task: TrainingTask, negative_store) -> bool:
        """Check if task's domain is quarantined."""
        import re
        # Extract domain from prompt
        url_match = re.search(r'(?:https?://)?(?:www\.)?([a-z0-9\-]+\.[a-z]{2,})', task.prompt.lower())
        if url_match:
            domain = url_match.group(1)
            if negative_store.is_site_quarantined(domain):
                return True

        # Also check task.domain field
        if task.domain and negative_store.is_site_quarantined(task.domain):
            return True

        return False

    def _generate_base_task(self,
                            preferred_category: str = None,
                            preferred_difficulty: str = None) -> TrainingTask:
        """Generate a standard task from templates."""
        # Select difficulty
        if preferred_difficulty:
            difficulty = preferred_difficulty
        else:
            difficulty = random.choices(
                list(self.difficulty_distribution.keys()),
                weights=list(self.difficulty_distribution.values())
            )[0]

        # Select category (weighted towards priority categories, avoiding recent)
        if preferred_category and preferred_category in self.TASK_TEMPLATES:
            category = preferred_category
        else:
            # Build weighted list - priority categories get more weight
            # But reduce weight for recently used categories
            weighted_categories = []
            for cat in self.TASK_TEMPLATES.keys():
                weight = self.PRIORITY_WEIGHT if cat in self.PRIORITY_CATEGORIES else 1
                # Reduce weight if used recently (anti-circle)
                recent_count = self.recent_categories.count(cat)
                weight = max(1, weight - recent_count)
                weighted_categories.extend([cat] * weight)
            category = random.choice(weighted_categories)

        # Get templates for this category and difficulty
        templates = self.TASK_TEMPLATES.get(category, {}).get(difficulty, [])
        if not templates:
            # Fallback to medium difficulty
            templates = self.TASK_TEMPLATES.get(category, {}).get('medium', [])

        if not templates:
            # Ultimate fallback
            templates = [("Go to wikipedia.org and take a screenshot", ['navigate', 'screenshot'])]

        # Select template
        template, skills = random.choice(templates)

        # Select domain (prefer domains not used recently)
        available_domains = [d for d in self.PRACTICE_DOMAINS if d not in self.recent_domains[-5:]]
        if not available_domains:
            available_domains = self.PRACTICE_DOMAINS
        domain = random.choice(available_domains)

        # Format prompt
        prompt = template.format(domain=domain)

        # Generate success criteria
        success_criteria = self._generate_success_criteria(category, skills)

        return TrainingTask(
            prompt=prompt,
            domain=domain,
            difficulty=difficulty,
            category=category,
            expected_skills=skills,
            success_criteria=success_criteria
        )

    def generate_batch(self, count: int, ensure_variety: bool = True) -> List[TrainingTask]:
        """
        Generate a batch of diverse tasks.

        Args:
            count: Number of tasks to generate
            ensure_variety: Ensure coverage of all categories
        """
        tasks = []

        if ensure_variety:
            # First pass: one of each category
            categories = list(self.TASK_TEMPLATES.keys())
            random.shuffle(categories)

            for cat in categories[:min(count, len(categories))]:
                tasks.append(self.generate_task(preferred_category=cat))

            # Fill remaining with random
            while len(tasks) < count:
                tasks.append(self.generate_task())
        else:
            tasks = [self.generate_task() for _ in range(count)]

        return tasks

    def generate_progressive_curriculum(self,
                                        total_tasks: int,
                                        start_easy: bool = True) -> List[TrainingTask]:
        """
        Generate tasks that progressively increase in difficulty.
        Like curriculum learning - start easy, get harder.

        Args:
            total_tasks: Total number of tasks
            start_easy: Whether to start with easy tasks
        """
        tasks = []

        # Define progression
        phases = [
            (0.0, 0.3, {'easy': 0.7, 'medium': 0.3, 'hard': 0.0}),  # Phase 1: Mostly easy
            (0.3, 0.6, {'easy': 0.3, 'medium': 0.5, 'hard': 0.2}),  # Phase 2: Mixed
            (0.6, 1.0, {'easy': 0.1, 'medium': 0.4, 'hard': 0.5}),  # Phase 3: Mostly hard
        ]

        for i in range(total_tasks):
            progress = i / total_tasks

            # Find current phase
            for start, end, distribution in phases:
                if start <= progress < end:
                    self.difficulty_distribution = distribution
                    break

            tasks.append(self.generate_task())

        return tasks

    def generate_self_eval_task(self) -> str:
        """Generate a self-evaluation task."""
        return random.choice(self.SELF_EVAL_TEMPLATES)

    def generate_meta_learning_task(self) -> str:
        """Generate a meta-learning task for strategy improvement."""
        return random.choice(self.META_LEARNING_TEMPLATES)

    def generate_adversarial_task(self) -> TrainingTask:
        """
        Generate a challenging task designed to find weaknesses.
        These are edge cases and unusual scenarios.
        """
        adversarial_tasks = [
            TrainingTask(
                prompt="Go to a page that redirects multiple times and extract the final URL",
                domain="httpbin.org",
                difficulty="hard",
                category="error_recovery",
                expected_skills=['navigate', 'redirect_handling', 'extract'],
                success_criteria="Successfully follow redirects and report final destination"
            ),
            TrainingTask(
                prompt="Go to httpbin.org/html and extract text from dynamically nested elements",
                domain="httpbin.org",
                difficulty="hard",
                category="extraction",
                expected_skills=['navigate', 'extract', 'complex_selectors'],
                success_criteria="Extract structured content from complex HTML"
            ),
            TrainingTask(
                prompt="Navigate to a slow-loading page and wait for all content to appear",
                domain="httpbin.org",
                difficulty="hard",
                category="interaction",
                expected_skills=['navigate', 'wait', 'timing'],
                success_criteria="Properly wait for content without premature extraction"
            ),
            TrainingTask(
                prompt="Go to quotes.toscrape.com, scroll to load more content, extract all visible quotes",
                domain="quotes.toscrape.com",
                difficulty="hard",
                category="extraction",
                expected_skills=['navigate', 'scroll', 'extract', 'infinite_scroll'],
                success_criteria="Handle dynamic content loading"
            ),
        ]

        task = random.choice(adversarial_tasks)
        self.task_history.append(task)
        return task

    def _generate_success_criteria(self, category: str, skills: List[str]) -> str:
        """Generate success criteria based on task type."""
        criteria_map = {
            'navigation': "Page successfully loaded and accessible",
            'extraction': "Data extracted matches visible content",
            'search': "Search executed and results retrieved",
            'interaction': "Element interaction completed without errors",
            'error_recovery': "Errors handled gracefully with appropriate response",
            'analysis': "Analysis is accurate and insightful",
        }

        base = criteria_map.get(category, "Task completed successfully")

        if 'screenshot' in skills:
            base += ", screenshot captured"
        if 'csv' in skills:
            base += ", data saved to CSV"
        if 'multiple' in skills:
            base += ", multiple items processed"

        return base

    def get_stats(self) -> Dict:
        """Get task generation statistics."""
        return {
            'total_generated': len(self.task_history),
            'by_category': dict(self.category_counts),
            'by_difficulty': {
                'easy': sum(1 for t in self.task_history if t.difficulty == 'easy'),
                'medium': sum(1 for t in self.task_history if t.difficulty == 'medium'),
                'hard': sum(1 for t in self.task_history if t.difficulty == 'hard'),
            }
        }

    def reset_history(self):
        """Reset task history for new training session."""
        self.task_history = []
        self.category_counts = {cat: 0 for cat in self.TASK_TEMPLATES.keys()}
