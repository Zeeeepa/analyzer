#!/usr/bin/env python3
"""
Task Decomposition Engine
Breaks complex tasks into atomic operations that CANNOT fail
Goal: Make every subtask so simple that 14B model succeeds 100%
"""

from typing import List, Dict, Any
from loguru import logger
import re


class TaskDecomposer:
    """
    Decomposes complex tasks into atomic, fail-proof operations
    """

    def __init__(self):
        # Library of atomic operations (simple tasks model can't fail at)
        self.atomic_operations = {
            'navigate': self._decompose_navigation,
            'search': self._decompose_search,
            'extract': self._decompose_extraction,
            'fill_form': self._decompose_form_filling,
            'click': self._decompose_clicking,
            'scrape': self._decompose_scraping,
        }

    def decompose(self, task: str) -> List[Dict[str, Any]]:
        """
        Break task into atomic steps
        Returns list of simple, fail-proof operations
        """

        task_lower = task.lower()

        # Detect task type
        if 'search' in task_lower and ('facebook' in task_lower or 'ads' in task_lower):
            return self._decompose_facebook_ads_search(task)
        elif 'extract' in task_lower or 'get' in task_lower:
            return self._decompose_extraction_task(task)
        elif 'fill' in task_lower or 'form' in task_lower:
            return self._decompose_form_task(task)
        elif 'navigate' in task_lower or 'go to' in task_lower:
            return self._decompose_navigation_task(task)
        else:
            # Generic decomposition
            return self._decompose_generic_task(task)

    def _decompose_facebook_ads_search(self, task: str) -> List[Dict[str, Any]]:
        """
        Facebook Ads search broken into atomic steps
        Each step is so simple it cannot fail
        """

        # Extract keyword
        keyword_match = re.search(r'["\']([^"\']+)["\']', task)
        keyword = keyword_match.group(1) if keyword_match else 'unknown'

        return [
            {
                'step': 1,
                'action': 'verify_starting_state',
                'description': 'Confirm browser is ready',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': 'document.readyState'
                    }, 'expected': 'complete'}
                ],
                'success_criteria': 'Ready state is complete',
                'fallback': 'Wait 2 seconds and retry'
            },
            {
                'step': 2,
                'action': 'navigate_to_ads_library',
                'description': 'Go to Facebook Ads Library homepage',
                'operations': [
                    {'function': 'playwright_navigate', 'arguments': {
                        'url': 'https://www.facebook.com/ads/library'
                    }}
                ],
                'success_criteria': 'URL contains facebook.com/ads/library',
                'fallback': 'Try alternate URL: https://facebook.com/ads/library'
            },
            {
                'step': 3,
                'action': 'wait_for_page_load',
                'description': 'Wait for page to fully load',
                'operations': [
                    {'wait': 3000},  # Wait 3 seconds
                    {'function': 'playwright_screenshot', 'arguments': {}},
                ],
                'success_criteria': 'Page loaded, screenshot taken',
                'fallback': 'Wait additional 5 seconds'
            },
            {
                'step': 4,
                'action': 'verify_search_box_exists',
                'description': 'Confirm search input is present',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '''
                            document.querySelector('input[aria-label*="Search"], input[placeholder*="Search"]') !== null
                        '''
                    }}
                ],
                'success_criteria': 'Search box found',
                'fallback': 'Take screenshot and locate search box manually'
            },
            {
                'step': 5,
                'action': 'fill_search_box',
                'description': f'Type "{keyword}" into search',
                'operations': [
                    {'function': 'playwright_fill', 'arguments': {
                        'selector': 'input[aria-label*="Search"], input[placeholder*="Search"]',
                        'value': keyword
                    }}
                ],
                'success_criteria': f'Search box contains "{keyword}"',
                'fallback': 'Try clicking search box first, then typing'
            },
            {
                'step': 6,
                'action': 'verify_text_entered',
                'description': 'Confirm text was entered correctly',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': f'''
                            document.querySelector('input[aria-label*="Search"], input[placeholder*="Search"]').value === '{keyword}'
                        '''
                    }}
                ],
                'success_criteria': 'Input value matches keyword',
                'fallback': 'Clear and re-type'
            },
            {
                'step': 7,
                'action': 'submit_search',
                'description': 'Click search button or press Enter',
                'operations': [
                    {'function': 'playwright_press', 'arguments': {
                        'key': 'Enter'
                    }}
                ],
                'success_criteria': 'Search submitted',
                'fallback': 'Click submit button instead'
            },
            {
                'step': 8,
                'action': 'wait_for_results',
                'description': 'Wait for search results to load',
                'operations': [
                    {'wait': 3000},
                    {'function': 'playwright_screenshot', 'arguments': {}},
                ],
                'success_criteria': 'Results visible',
                'fallback': 'Wait longer if needed'
            },
            {
                'step': 9,
                'action': 'verify_results_loaded',
                'description': 'Confirm results are displayed',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '''
                            document.querySelectorAll('[role="article"], .ad-card, [data-testid*="ad"]').length > 0
                        '''
                    }}
                ],
                'success_criteria': 'At least one ad result found',
                'fallback': 'Take screenshot for manual verification'
            },
            {
                'step': 10,
                'action': 'extract_results',
                'description': 'Get ad data from page',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '''
                            Array.from(document.querySelectorAll('[role="article"], .ad-card'))
                                .slice(0, 10)
                                .map(ad => ({
                                    text: ad.textContent.slice(0, 100),
                                    links: Array.from(ad.querySelectorAll('a'))
                                        .map(a => a.href)
                                        .filter(h => h && !h.includes('facebook.com'))
                                }))
                        '''
                    }}
                ],
                'success_criteria': 'Data extracted',
                'fallback': 'Extract visible text only'
            }
        ]

    def _decompose_navigation_task(self, task: str) -> List[Dict[str, Any]]:
        """Simple navigation broken into atomic steps"""

        # Extract URL
        url_match = re.search(r'(https?://[^\s]+|[a-z0-9-]+\.[a-z]{2,})', task, re.I)
        url = url_match.group(1) if url_match else ''

        if not url.startswith('http'):
            url = f'https://{url}'

        return [
            {
                'step': 1,
                'action': 'prepare_navigation',
                'description': 'Verify browser ready',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '({ready: document.readyState, url: window.location.href})'
                    }}
                ],
                'success_criteria': 'Browser ready',
                'fallback': 'None - always succeeds'
            },
            {
                'step': 2,
                'action': 'navigate',
                'description': f'Go to {url}',
                'operations': [
                    {'function': 'playwright_navigate', 'arguments': {'url': url}}
                ],
                'success_criteria': f'URL is {url}',
                'fallback': 'Try with www. prefix or https://'
            },
            {
                'step': 3,
                'action': 'verify_loaded',
                'description': 'Confirm page loaded',
                'operations': [
                    {'wait': 2000},
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': 'document.title'
                    }}
                ],
                'success_criteria': 'Title retrieved',
                'fallback': 'Take screenshot'
            }
        ]

    def _decompose_extraction_task(self, task: str) -> List[Dict[str, Any]]:
        """Data extraction broken into atomic steps"""

        return [
            {
                'step': 1,
                'action': 'take_snapshot',
                'description': 'Screenshot current page',
                'operations': [
                    {'function': 'playwright_screenshot', 'arguments': {}}
                ],
                'success_criteria': 'Screenshot taken',
                'fallback': 'None'
            },
            {
                'step': 2,
                'action': 'get_page_info',
                'description': 'Extract basic page information',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '''
                            ({
                                title: document.title,
                                url: window.location.href,
                                text_length: document.body.innerText.length,
                                links_count: document.querySelectorAll('a').length
                            })
                        '''
                    }}
                ],
                'success_criteria': 'Basic info extracted',
                'fallback': 'Return partial data'
            },
            {
                'step': 3,
                'action': 'extract_content',
                'description': 'Get requested content',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '''
                            ({
                                headings: Array.from(document.querySelectorAll('h1, h2, h3'))
                                    .map(h => h.textContent.trim()),
                                paragraphs: Array.from(document.querySelectorAll('p'))
                                    .slice(0, 5)
                                    .map(p => p.textContent.trim()),
                                main_content: document.querySelector('main, article, .content')?.innerText.slice(0, 1000) || document.body.innerText.slice(0, 1000)
                            })
                        '''
                    }}
                ],
                'success_criteria': 'Content extracted',
                'fallback': 'Return full page text'
            }
        ]

    def _decompose_generic_task(self, task: str) -> List[Dict[str, Any]]:
        """Generic task decomposition"""

        return [
            {
                'step': 1,
                'action': 'understand_context',
                'description': 'Get current page state',
                'operations': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '''
                            ({
                                url: window.location.href,
                                title: document.title,
                                forms: document.querySelectorAll('form').length,
                                buttons: document.querySelectorAll('button').length,
                                inputs: document.querySelectorAll('input').length
                            })
                        '''
                    }}
                ],
                'success_criteria': 'Context understood',
                'fallback': 'Take screenshot'
            },
            {
                'step': 2,
                'action': 'execute_task',
                'description': task,
                'operations': [],  # Will be filled by model
                'success_criteria': 'Task completed',
                'fallback': 'Report what was attempted'
            }
        ]

    def _decompose_navigation(self, url: str) -> List[Dict[str, Any]]:
        """Atomic navigation steps"""
        return self._decompose_navigation_task(f"Go to {url}")

    def _decompose_search(self, query: str, site: str = '') -> List[Dict[str, Any]]:
        """Atomic search steps"""
        if 'facebook' in site.lower():
            return self._decompose_facebook_ads_search(f"Search Facebook Ads for '{query}'")
        # Add other search decompositions...
        return []

    def _decompose_extraction(self, target: str) -> List[Dict[str, Any]]:
        """Atomic extraction steps"""
        return self._decompose_extraction_task(f"Extract {target}")

    def _decompose_form_filling(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Atomic form filling steps"""
        return self._decompose_form_task(f"Fill form with data")

    def _decompose_clicking(self, selector: str) -> List[Dict[str, Any]]:
        """Atomic clicking steps"""
        return [
            {'step': 1, 'action': 'verify_element', 'operations': []},
            {'step': 2, 'action': 'click_element', 'operations': []},
            {'step': 3, 'action': 'verify_click_worked', 'operations': []}
        ]

    def _decompose_scraping(self, target: str) -> List[Dict[str, Any]]:
        """Atomic scraping steps"""
        return self._decompose_extraction_task(f"Scrape {target}")


# Singleton
task_decomposer = TaskDecomposer()
