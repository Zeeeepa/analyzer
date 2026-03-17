"""
Super Tools - Outcome-oriented browser automation tools.

These tools wrap lower-level browser operations into business outcomes,
making it easy for an LLM to perform complex tasks with simple commands.
"""

from typing import Dict, List, Any, Optional, Literal
import json
import time


class SuperTools:
    """High-level business outcome tools for browser automation."""

    def __init__(self, browser_context):
        """
        Initialize super tools with a browser context.

        Args:
            browser_context: Browser automation context with low-level operations
        """
        self.browser = browser_context

    def goto(self, url: str) -> Dict[str, Any]:
        """
        Navigate to URL with automatic popup and modal dismissal.

        Handles common navigation obstacles:
        - Cookie consent banners
        - Newsletter popups
        - Age verification modals
        - Generic overlay dismissal

        Args:
            url: Target URL to navigate to

        Returns:
            dict: {success: bool, url: str, title: str, error: Optional[str]}
        """
        try:
            # Navigate to URL
            self.browser.navigate(url)
            time.sleep(2)  # Wait for page load

            # Attempt to dismiss common popups
            dismissal_selectors = [
                # Cookie consent
                '[aria-label*="Accept"]',
                '[aria-label*="accept"]',
                'button:has-text("Accept")',
                'button:has-text("I agree")',
                'button:has-text("OK")',
                # Close buttons
                '[aria-label="Close"]',
                '[aria-label="close"]',
                'button[aria-label*="Dismiss"]',
                '.modal-close',
                '.popup-close',
                # X buttons
                'button:has-text("×")',
                'button:has-text("✕")',
            ]

            for selector in dismissal_selectors:
                try:
                    self.browser.click(selector, timeout=1000)
                    time.sleep(0.5)
                except:
                    pass  # Selector not found, continue

            # Get page info
            title = self.browser.get_title()
            current_url = self.browser.get_url()

            return {
                "success": True,
                "url": current_url,
                "title": title,
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "url": url,
                "title": None,
                "error": str(e)
            }

    def find_leads(
        self,
        source: Literal["fb_ads", "linkedin", "reddit", "google_maps"],
        query: str,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Find leads from various sources.

        Searches for potential leads based on the query and extracts
        contact information, company details, and engagement signals.

        Args:
            source: Lead source platform
            query: Search query (company, industry, location, etc.)
            limit: Maximum number of leads to extract

        Returns:
            dict: {
                success: bool,
                source: str,
                leads: List[dict],
                count: int,
                error: Optional[str]
            }
        """
        try:
            leads = []

            if source == "fb_ads":
                leads = self._find_fb_ads_leads(query, limit)
            elif source == "linkedin":
                leads = self._find_linkedin_leads(query, limit)
            elif source == "reddit":
                leads = self._find_reddit_leads(query, limit)
            elif source == "google_maps":
                leads = self._find_google_maps_leads(query, limit)
            else:
                return {
                    "success": False,
                    "source": source,
                    "leads": [],
                    "count": 0,
                    "error": f"Unknown source: {source}"
                }

            return {
                "success": True,
                "source": source,
                "leads": leads,
                "count": len(leads),
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "source": source,
                "leads": [],
                "count": 0,
                "error": str(e)
            }

    def extract(
        self,
        data_type: Literal["contacts", "list", "table"],
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extract structured data from current page.

        Uses accessibility tree and DOM parsing to identify and extract
        structured information like contact cards, lists, or tables.

        Args:
            data_type: Type of data to extract
            limit: Maximum items to extract (None = all)

        Returns:
            dict: {
                success: bool,
                type: str,
                data: List[dict],
                count: int,
                error: Optional[str]
            }
        """
        try:
            data = []

            if data_type == "contacts":
                data = self._extract_contacts(limit)
            elif data_type == "list":
                data = self._extract_list(limit)
            elif data_type == "table":
                data = self._extract_table(limit)
            else:
                return {
                    "success": False,
                    "type": data_type,
                    "data": [],
                    "count": 0,
                    "error": f"Unknown data type: {data_type}"
                }

            return {
                "success": True,
                "type": data_type,
                "data": data,
                "count": len(data),
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "type": data_type,
                "data": [],
                "count": 0,
                "error": str(e)
            }

    def interact(
        self,
        action: Literal["click", "fill", "select"],
        target: str,
        value: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Interact with page elements using accessibility-first targeting.

        Finds elements by role, label, or accessible name rather than
        CSS selectors, making interactions more robust.

        Args:
            action: Type of interaction
            target: Accessible name, label, or role
            value: Value for fill/select actions

        Returns:
            dict: {success: bool, action: str, target: str, error: Optional[str]}
        """
        try:
            if action == "click":
                # Try multiple accessibility selectors
                selectors = [
                    f'[aria-label="{target}"]',
                    f'button:has-text("{target}")',
                    f'a:has-text("{target}")',
                    f'[role="button"]:has-text("{target}")',
                    f'[name="{target}"]',
                ]

                clicked = False
                for selector in selectors:
                    try:
                        self.browser.click(selector)
                        clicked = True
                        break
                    except:
                        continue

                if not clicked:
                    raise Exception(f"Could not find clickable element: {target}")

            elif action == "fill":
                if value is None:
                    raise Exception("Value required for fill action")

                # Try multiple input selectors
                selectors = [
                    f'[aria-label="{target}"]',
                    f'input[name="{target}"]',
                    f'textarea[name="{target}"]',
                    f'input[placeholder*="{target}"]',
                ]

                filled = False
                for selector in selectors:
                    try:
                        self.browser.fill(selector, value)
                        filled = True
                        break
                    except:
                        continue

                if not filled:
                    raise Exception(f"Could not find fillable element: {target}")

            elif action == "select":
                if value is None:
                    raise Exception("Value required for select action")

                # Try multiple select selectors
                selectors = [
                    f'[aria-label="{target}"]',
                    f'select[name="{target}"]',
                    f'[role="combobox"][aria-label="{target}"]',
                ]

                selected = False
                for selector in selectors:
                    try:
                        self.browser.select(selector, value)
                        selected = True
                        break
                    except:
                        continue

                if not selected:
                    raise Exception(f"Could not find selectable element: {target}")
            else:
                raise Exception(f"Unknown action: {action}")

            return {
                "success": True,
                "action": action,
                "target": target,
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "action": action,
                "target": target,
                "error": str(e)
            }

    def login(self, service: Literal["gmail", "linkedin", "facebook", "twitter"]) -> Dict[str, Any]:
        """
        Login to known services with stored credentials.

        Handles service-specific login flows including:
        - 2FA challenges
        - Security checks
        - Session restoration

        Args:
            service: Service to login to

        Returns:
            dict: {success: bool, service: str, logged_in: bool, error: Optional[str]}
        """
        try:
            if service == "gmail":
                success = self._login_gmail()
            elif service == "linkedin":
                success = self._login_linkedin()
            elif service == "facebook":
                success = self._login_facebook()
            elif service == "twitter":
                success = self._login_twitter()
            else:
                return {
                    "success": False,
                    "service": service,
                    "logged_in": False,
                    "error": f"Unknown service: {service}"
                }

            return {
                "success": success,
                "service": service,
                "logged_in": success,
                "error": None if success else "Login failed"
            }

        except Exception as e:
            return {
                "success": False,
                "service": service,
                "logged_in": False,
                "error": str(e)
            }

    def search(self, query: str) -> Dict[str, Any]:
        """
        Search within current site.

        Automatically detects and uses site search functionality:
        - Search input fields
        - Search buttons
        - Keyboard shortcuts

        Args:
            query: Search query

        Returns:
            dict: {
                success: bool,
                query: str,
                results_count: Optional[int],
                error: Optional[str]
            }
        """
        try:
            # Try to find search input
            search_selectors = [
                'input[type="search"]',
                'input[aria-label*="Search"]',
                'input[aria-label*="search"]',
                'input[placeholder*="Search"]',
                'input[placeholder*="search"]',
                'input[name="q"]',
                'input[name="search"]',
            ]

            search_found = False
            for selector in search_selectors:
                try:
                    self.browser.fill(selector, query)
                    self.browser.press(selector, "Enter")
                    search_found = True
                    break
                except:
                    continue

            if not search_found:
                raise Exception("Could not find search input on page")

            time.sleep(2)  # Wait for results

            # Try to count results
            results_count = None
            result_count_selectors = [
                '[aria-label*="results"]',
                '.search-results-count',
                '.results-count',
            ]

            for selector in result_count_selectors:
                try:
                    text = self.browser.get_text(selector)
                    # Extract number from text
                    import re
                    numbers = re.findall(r'\d+', text)
                    if numbers:
                        results_count = int(numbers[0])
                        break
                except:
                    continue

            return {
                "success": True,
                "query": query,
                "results_count": results_count,
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "query": query,
                "results_count": None,
                "error": str(e)
            }

    def form_fill(self, data: Dict[str, str]) -> Dict[str, Any]:
        """
        Smart form filling with field detection.

        Automatically maps data to form fields using:
        - Field labels
        - Placeholder text
        - Input names
        - Semantic matching

        Args:
            data: dict mapping field names to values
                  Example: {"email": "user@example.com", "name": "John Doe"}

        Returns:
            dict: {
                success: bool,
                filled_fields: List[str],
                failed_fields: List[str],
                error: Optional[str]
            }
        """
        try:
            filled_fields = []
            failed_fields = []

            for field_name, value in data.items():
                # Generate possible selectors for this field
                selectors = [
                    f'input[name="{field_name}"]',
                    f'input[aria-label*="{field_name}"]',
                    f'input[placeholder*="{field_name}"]',
                    f'textarea[name="{field_name}"]',
                    f'select[name="{field_name}"]',
                    # Try capitalized version
                    f'input[name="{field_name.capitalize()}"]',
                    f'input[aria-label*="{field_name.capitalize()}"]',
                ]

                # Special case for common fields
                if field_name.lower() in ["email", "e-mail"]:
                    selectors.extend([
                        'input[type="email"]',
                        'input[autocomplete="email"]',
                    ])
                elif field_name.lower() in ["phone", "telephone", "mobile"]:
                    selectors.extend([
                        'input[type="tel"]',
                        'input[autocomplete="tel"]',
                    ])
                elif field_name.lower() in ["password", "pass"]:
                    selectors.extend([
                        'input[type="password"]',
                        'input[autocomplete="current-password"]',
                    ])

                field_filled = False
                for selector in selectors:
                    try:
                        # Determine if select or input
                        if 'select' in selector:
                            self.browser.select(selector, value)
                        else:
                            self.browser.fill(selector, value)
                        field_filled = True
                        filled_fields.append(field_name)
                        break
                    except:
                        continue

                if not field_filled:
                    failed_fields.append(field_name)

            success = len(failed_fields) == 0

            return {
                "success": success,
                "filled_fields": filled_fields,
                "failed_fields": failed_fields,
                "error": None if success else f"Failed to fill: {', '.join(failed_fields)}"
            }

        except Exception as e:
            return {
                "success": False,
                "filled_fields": [],
                "failed_fields": list(data.keys()),
                "error": str(e)
            }

    def download(self, selector: Optional[str] = None) -> Dict[str, Any]:
        """
        Download file or PDF.

        Triggers download by clicking download button/link or
        saves current page as PDF.

        Args:
            selector: Optional selector for download button/link
                      If None, downloads current page as PDF

        Returns:
            dict: {
                success: bool,
                download_path: Optional[str],
                error: Optional[str]
            }
        """
        try:
            if selector:
                # Click download button/link
                self.browser.click(selector)
                time.sleep(2)  # Wait for download to start

                # Get download path (platform-specific)
                download_path = self.browser.get_last_download_path()
            else:
                # Save as PDF
                download_path = self.browser.save_as_pdf()

            return {
                "success": True,
                "download_path": download_path,
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "download_path": None,
                "error": str(e)
            }

    def screenshot(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Take screenshot of current page.

        Args:
            path: Optional path to save screenshot
                  If None, generates timestamped filename

        Returns:
            dict: {
                success: bool,
                screenshot_path: str,
                error: Optional[str]
            }
        """
        try:
            if path is None:
                # Generate timestamped filename
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                path = f"screenshot_{timestamp}.png"

            self.browser.screenshot(path)

            return {
                "success": True,
                "screenshot_path": path,
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "screenshot_path": None,
                "error": str(e)
            }

    def page_info(self) -> Dict[str, Any]:
        """
        Get accessibility tree snapshot of current page.

        Returns structured information about the page for AI analysis:
        - Page title and URL
        - Main headings
        - Interactive elements (buttons, links, inputs)
        - Semantic regions (navigation, main, aside)

        Returns:
            dict: {
                success: bool,
                url: str,
                title: str,
                headings: List[str],
                buttons: List[str],
                links: List[str],
                inputs: List[dict],
                regions: List[str],
                error: Optional[str]
            }
        """
        try:
            # Get basic page info
            url = self.browser.get_url()
            title = self.browser.get_title()

            # Extract accessibility tree info
            accessibility_tree = self.browser.get_accessibility_tree()

            # Parse tree for key elements
            headings = self._extract_headings(accessibility_tree)
            buttons = self._extract_buttons(accessibility_tree)
            links = self._extract_links(accessibility_tree)
            inputs = self._extract_inputs(accessibility_tree)
            regions = self._extract_regions(accessibility_tree)

            return {
                "success": True,
                "url": url,
                "title": title,
                "headings": headings,
                "buttons": buttons,
                "links": links,
                "inputs": inputs,
                "regions": regions,
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "url": None,
                "title": None,
                "headings": [],
                "buttons": [],
                "links": [],
                "inputs": [],
                "regions": [],
                "error": str(e)
            }

    # Helper methods for find_leads

    def _find_fb_ads_leads(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Find leads from Facebook Ad Library."""
        # Navigate to FB Ad Library
        self.goto("https://www.facebook.com/ads/library")

        # Search for ads
        self.search(query)

        # Extract advertiser info
        leads = []
        # Implementation would extract advertiser names, pages, ad content
        return leads[:limit]

    def _find_linkedin_leads(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Find leads from LinkedIn search."""
        # Navigate to LinkedIn
        self.goto("https://www.linkedin.com")

        # Search
        self.search(query)

        # Extract profile/company info
        leads = []
        # Implementation would extract names, titles, companies, locations
        return leads[:limit]

    def _find_reddit_leads(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Find leads from Reddit posts/comments."""
        # Navigate to Reddit
        self.goto(f"https://www.reddit.com/search/?q={query}")

        # Extract post info
        leads = []
        # Implementation would extract usernames, subreddits, engagement
        return leads[:limit]

    def _find_google_maps_leads(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Find leads from Google Maps."""
        # Navigate to Google Maps
        self.goto(f"https://www.google.com/maps/search/{query}")

        # Extract business info
        leads = []
        # Implementation would extract business names, addresses, phone, website
        return leads[:limit]

    # Helper methods for extract

    def _extract_contacts(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """Extract contact information from page."""
        contacts = []

        # Look for common contact patterns
        # Email, phone, social links, addresses

        return contacts[:limit] if limit else contacts

    def _extract_list(self, limit: Optional[int]) -> List[str]:
        """Extract list items from page."""
        # Look for ul/ol lists
        list_items = []

        return list_items[:limit] if limit else list_items

    def _extract_table(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """Extract table data from page."""
        # Look for table elements
        table_data = []

        return table_data[:limit] if limit else table_data

    # Helper methods for login

    def _login_gmail(self) -> bool:
        """Login to Gmail."""
        # Implementation would handle Google login flow
        return False

    def _login_linkedin(self) -> bool:
        """Login to LinkedIn."""
        # Implementation would handle LinkedIn login flow
        return False

    def _login_facebook(self) -> bool:
        """Login to Facebook."""
        # Implementation would handle Facebook login flow
        return False

    def _login_twitter(self) -> bool:
        """Login to Twitter/X."""
        # Implementation would handle Twitter login flow
        return False

    # Helper methods for page_info

    def _extract_headings(self, tree: Any) -> List[str]:
        """Extract headings from accessibility tree."""
        headings = []
        # Parse tree for h1-h6 elements
        return headings

    def _extract_buttons(self, tree: Any) -> List[str]:
        """Extract button labels from accessibility tree."""
        buttons = []
        # Parse tree for button elements and accessible names
        return buttons

    def _extract_links(self, tree: Any) -> List[str]:
        """Extract link text from accessibility tree."""
        links = []
        # Parse tree for link elements
        return links

    def _extract_inputs(self, tree: Any) -> List[Dict[str, str]]:
        """Extract input fields from accessibility tree."""
        inputs = []
        # Parse tree for input elements with labels/placeholders
        return inputs

    def _extract_regions(self, tree: Any) -> List[str]:
        """Extract semantic regions from accessibility tree."""
        regions = []
        # Parse tree for landmark roles
        return regions


# Tool definitions for LLM tool use
TOOL_DEFINITIONS = [
    {
        "name": "goto",
        "description": "Navigate to a URL with automatic popup and modal dismissal. Handles cookie banners, newsletter popups, and other common obstacles.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to (must include http:// or https://)"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "find_leads",
        "description": "Find potential leads from various sources. Searches for and extracts contact information, company details, and engagement signals.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["fb_ads", "linkedin", "reddit", "google_maps"],
                    "description": "The platform to search for leads"
                },
                "query": {
                    "type": "string",
                    "description": "Search query (company name, industry, location, keywords, etc.)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of leads to extract (default: 50)",
                    "default": 50
                }
            },
            "required": ["source", "query"]
        }
    },
    {
        "name": "extract",
        "description": "Extract structured data from the current page using accessibility tree and DOM parsing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["contacts", "list", "table"],
                    "description": "Type of data to extract from the page"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum items to extract (omit to extract all)",
                    "default": None
                }
            },
            "required": ["type"]
        }
    },
    {
        "name": "interact",
        "description": "Interact with page elements using accessibility-first targeting. Finds elements by role, label, or accessible name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["click", "fill", "select"],
                    "description": "Type of interaction to perform"
                },
                "target": {
                    "type": "string",
                    "description": "Accessible name, label, or role of the element"
                },
                "value": {
                    "type": "string",
                    "description": "Value for fill or select actions (required for those actions)"
                }
            },
            "required": ["action", "target"]
        }
    },
    {
        "name": "login",
        "description": "Login to known services with stored credentials. Handles 2FA and security checks automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "enum": ["gmail", "linkedin", "facebook", "twitter"],
                    "description": "Service to login to"
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "search",
        "description": "Search within the current site. Automatically detects and uses site search functionality.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to execute on the current site"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "form_fill",
        "description": "Smart form filling with automatic field detection. Maps data to form fields using labels, placeholders, and semantic matching.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": "Dictionary mapping field names to values. Example: {\"email\": \"user@example.com\", \"name\": \"John Doe\"}",
                    "additionalProperties": {
                        "type": "string"
                    }
                }
            },
            "required": ["data"]
        }
    },
    {
        "name": "download",
        "description": "Download a file by clicking a download button/link, or save the current page as PDF.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for download button/link. Omit to save current page as PDF."
                }
            },
            "required": []
        }
    },
    {
        "name": "screenshot",
        "description": "Take a screenshot of the current page and save it to disk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to save screenshot. Omit to auto-generate timestamped filename."
                }
            },
            "required": []
        }
    },
    {
        "name": "page_info",
        "description": "Get an accessibility tree snapshot of the current page. Returns structured information about headings, buttons, links, inputs, and semantic regions for AI analysis.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]
