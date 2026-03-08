"""
Service Integrations - Browser-based automation for various services.

All integrations use Playwright with an isolated persistent browser profile
(~/.eversale/browser-profile) so login sessions stay intact without touching
your normal Chrome profile.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import asyncio
from loguru import logger

from .playwright_direct import PlaywrightClient


class ServiceIntegration:
    """Base class for service integrations."""

    def __init__(self, browser: PlaywrightClient):
        self.browser = browser

    async def check_login(self) -> bool:
        """Check if user is logged in. Override in subclasses."""
        return True

    async def ensure_logged_in(self) -> bool:
        """Ensure user is logged in, return False if login needed."""
        return await self.check_login()


class GmailIntegration(ServiceIntegration):
    """Gmail automation via browser."""

    BASE_URL = "https://mail.google.com"

    async def check_login(self) -> bool:
        """Check if logged into Gmail."""
        try:
            await self.browser.navigate(self.BASE_URL)
            # Check for inbox indicators
            result = await self.browser.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    return text.includes('inbox') || text.includes('compose') || text.includes('starred');
                }
            """)
            return result
        except Exception as e:
            logger.debug(f"Gmail login check failed: {e}")
            return False

    async def get_inbox_summary(self, max_emails: int = 10) -> Dict[str, Any]:
        """Get summary of recent inbox emails."""
        try:
            await self.browser.navigate(self.BASE_URL)
            await asyncio.sleep(2)

            result = await self.browser.page.evaluate(f"""
                () => {{
                    const emails = [];
                    // Gmail uses table rows for emails
                    const rows = document.querySelectorAll('tr.zA');

                    rows.forEach((row, i) => {{
                        if (i >= {max_emails}) return;

                        const sender = row.querySelector('.yX .yW span')?.innerText || '';
                        const subject = row.querySelector('.y6 span')?.innerText || '';
                        const snippet = row.querySelector('.y2')?.innerText || '';
                        const isUnread = row.classList.contains('zE');
                        const isStarred = row.querySelector('[data-tooltip="Starred"]') !== null;

                        if (sender || subject) {{
                            emails.push({{ sender, subject, snippet, isUnread, isStarred }});
                        }}
                    }});

                    return {{
                        emails,
                        totalUnread: document.querySelector('.bsU')?.innerText || '0',
                        success: true
                    }};
                }}
            """)
            return result
        except Exception as e:
            return {"error": str(e), "emails": []}

    async def draft_reply(self, subject: str, body: str) -> Dict[str, Any]:
        """Create a draft reply (opens compose window)."""
        try:
            # Click compose button - uses visual fallback if selector fails
            await self.browser.click('[gh="cm"]', "the Compose button to write a new email")
            await asyncio.sleep(1)

            # Fill in subject if provided
            if subject:
                await self.browser.fill('[name="subjectbox"]', subject, "the Subject input field")

            # Fill in body
            await self.browser.fill('[role="textbox"][aria-label*="Message"]', body, "the email message body text area")

            return {"success": True, "message": "Draft created in Gmail"}
        except Exception as e:
            return {"error": str(e)}


class GoogleCalendarIntegration(ServiceIntegration):
    """Google Calendar automation."""

    BASE_URL = "https://calendar.google.com"

    async def check_login(self) -> bool:
        """Check if logged into Google Calendar."""
        try:
            await self.browser.navigate(self.BASE_URL)
            result = await self.browser.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    return text.includes('today') || text.includes('week') || text.includes('month');
                }
            """)
            return result
        except Exception as e:
            logger.debug(f"Google Calendar login check failed: {e}")
            return False

    async def get_todays_events(self) -> Dict[str, Any]:
        """Get today's calendar events."""
        try:
            await self.browser.navigate(self.BASE_URL)
            await asyncio.sleep(2)

            result = await self.browser.page.evaluate("""
                () => {
                    const events = [];
                    // Calendar events are typically in specific containers
                    document.querySelectorAll('[data-eventid]').forEach(el => {
                        const title = el.querySelector('[data-eventchip]')?.innerText ||
                                     el.innerText?.split('\\n')[0] || '';
                        const time = el.querySelector('[data-eventtime]')?.innerText || '';

                        if (title) {
                            events.push({ title, time });
                        }
                    });

                    return { events, date: new Date().toDateString(), success: true };
                }
            """)
            return result
        except Exception as e:
            return {"error": str(e), "events": []}


class HubSpotIntegration(ServiceIntegration):
    """HubSpot CRM automation."""

    BASE_URL = "https://app.hubspot.com"

    async def check_login(self) -> bool:
        """Check if logged into HubSpot."""
        try:
            await self.browser.navigate(self.BASE_URL)
            await asyncio.sleep(2)
            result = await self.browser.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    return text.includes('contacts') || text.includes('deals') ||
                           text.includes('dashboard') || text.includes('companies');
                }
            """)
            return result
        except Exception as e:
            logger.debug(f"HubSpot login check failed: {e}")
            return False

    async def search_contacts(self, query: str) -> Dict[str, Any]:
        """Search for contacts in HubSpot."""
        try:
            # Navigate to contacts
            await self.browser.navigate(f"{self.BASE_URL}/contacts")
            await asyncio.sleep(2)

            # Use the search box - with visual fallback
            await self.browser.fill('[data-test-id="search-input"]', query, "the search input box")
            await self.browser.page.keyboard.press("Enter")
            await asyncio.sleep(2)

            # Extract results
            result = await self.browser.page.evaluate("""
                () => {
                    const contacts = [];
                    document.querySelectorAll('table tbody tr').forEach(row => {
                        const name = row.querySelector('td:nth-child(1)')?.innerText || '';
                        const email = row.querySelector('td:nth-child(2)')?.innerText || '';
                        const company = row.querySelector('td:nth-child(3)')?.innerText || '';

                        if (name) {
                            contacts.push({ name, email, company });
                        }
                    });
                    return { contacts, success: true };
                }
            """)
            return result
        except Exception as e:
            return {"error": str(e), "contacts": []}

    async def get_deals_pipeline(self) -> Dict[str, Any]:
        """Get deals pipeline summary."""
        try:
            await self.browser.navigate(f"{self.BASE_URL}/deals")
            await asyncio.sleep(2)

            result = await self.browser.page.evaluate("""
                () => {
                    const stages = [];
                    document.querySelectorAll('[data-test-id="deal-board-column"]').forEach(col => {
                        const stageName = col.querySelector('[data-test-id="column-header"]')?.innerText || '';
                        const dealCount = col.querySelectorAll('[data-test-id="deal-card"]').length;
                        stages.push({ stageName, dealCount });
                    });
                    return { stages, success: true };
                }
            """)
            return result
        except Exception as e:
            return {"error": str(e), "stages": []}


class ShopifyIntegration(ServiceIntegration):
    """Shopify admin automation."""

    async def check_login(self) -> bool:
        """Check if logged into Shopify admin."""
        try:
            # User needs to provide their store URL
            result = await self.browser.page.evaluate("""
                () => {
                    const url = window.location.href;
                    return url.includes('admin.shopify.com') ||
                           url.includes('myshopify.com/admin');
                }
            """)
            return result
        except Exception as e:
            logger.debug(f"Shopify login check failed: {e}")
            return False

    async def get_orders_summary(self, store_url: str) -> Dict[str, Any]:
        """Get recent orders summary."""
        try:
            await self.browser.navigate(f"{store_url}/admin/orders")
            await asyncio.sleep(2)

            result = await self.browser.page.evaluate("""
                () => {
                    const orders = [];
                    document.querySelectorAll('[data-testid="order-row"]').forEach(row => {
                        const orderNumber = row.querySelector('[data-testid="order-name"]')?.innerText || '';
                        const customer = row.querySelector('[data-testid="customer-name"]')?.innerText || '';
                        const total = row.querySelector('[data-testid="order-total"]')?.innerText || '';
                        const status = row.querySelector('[data-testid="order-status"]')?.innerText || '';

                        if (orderNumber) {
                            orders.push({ orderNumber, customer, total, status });
                        }
                    });
                    return { orders, success: true };
                }
            """)
            return result
        except Exception as e:
            return {"error": str(e), "orders": []}

    async def get_products(self, store_url: str) -> Dict[str, Any]:
        """Get products list."""
        try:
            await self.browser.navigate(f"{store_url}/admin/products")
            await asyncio.sleep(2)

            result = await self.browser.page.evaluate("""
                () => {
                    const products = [];
                    document.querySelectorAll('[data-testid="product-row"]').forEach(row => {
                        const title = row.querySelector('[data-testid="product-title"]')?.innerText || '';
                        const status = row.querySelector('[data-testid="product-status"]')?.innerText || '';
                        const inventory = row.querySelector('[data-testid="product-inventory"]')?.innerText || '';

                        if (title) {
                            products.push({ title, status, inventory });
                        }
                    });
                    return { products, success: true };
                }
            """)
            return result
        except Exception as e:
            return {"error": str(e), "products": []}


class LinkedInIntegration(ServiceIntegration):
    """LinkedIn automation for research."""

    BASE_URL = "https://www.linkedin.com"

    async def check_login(self) -> bool:
        """Check if logged into LinkedIn."""
        try:
            await self.browser.navigate(f"{self.BASE_URL}/feed")
            await asyncio.sleep(2)
            result = await self.browser.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    return text.includes('home') && text.includes('my network');
                }
            """)
            return result
        except Exception as e:
            logger.debug(f"LinkedIn login check failed: {e}")
            return False

    async def search_people(self, query: str) -> Dict[str, Any]:
        """
        Search for people on LinkedIn with Google fallback.

        Strategy:
        1. Try direct LinkedIn search
        2. If blocked/requires login, search Google for: "site:linkedin.com/in [query]"
        3. Extract LinkedIn profile URLs from Google results
        """
        try:
            search_url = f"{self.BASE_URL}/search/results/people/?keywords={query}"
            await self.browser.navigate(search_url)
            await asyncio.sleep(3)

            # Try direct extraction
            result = await self.browser.page.evaluate("""
                () => {
                    const people = [];
                    document.querySelectorAll('.reusable-search__result-container').forEach(card => {
                        const name = card.querySelector('.entity-result__title-text a')?.innerText?.trim() || '';
                        const title = card.querySelector('.entity-result__primary-subtitle')?.innerText?.trim() || '';
                        const location = card.querySelector('.entity-result__secondary-subtitle')?.innerText?.trim() || '';
                        const profileUrl = card.querySelector('.entity-result__title-text a')?.href || '';

                        if (name) {
                            people.push({ name, title, location, profileUrl });
                        }
                    });
                    return { people: people.slice(0, 10), success: true };
                }
            """)

            # Check if we got results
            if result.get("people") and len(result["people"]) > 0:
                return result

            # Check if blocked/login required
            page_text = await self.browser.page.evaluate("() => document.body.innerText.toLowerCase()")
            if "sign in" in page_text or "join now" in page_text:
                logger.info(f"[LinkedIn] Login required - trying Google fallback for: {query}")

                # Fallback: Google search for LinkedIn profiles
                from urllib.parse import quote_plus
                google_query = f"site:linkedin.com/in {query}"
                google_url = f"https://www.google.com/search?q={quote_plus(google_query)}"

                await self.browser.navigate(google_url)
                await asyncio.sleep(2)

                # Extract LinkedIn URLs from Google results
                google_result = await self.browser.page.evaluate("""
                    () => {
                        const people = [];
                        const seen = new Set();

                        document.querySelectorAll('a[href]').forEach(a => {
                            const href = a.href || '';
                            const text = (a.innerText || '').trim();

                            // Only include actual LinkedIn profile URLs
                            if (href.includes('linkedin.com/in/')) {
                                const match = href.match(/linkedin\\.com\\/in\\/([^\\/\\?&]+)/);
                                if (match && !seen.has(match[1])) {
                                    seen.add(match[1]);

                                    // Clean up name from Google result
                                    let name = text.replace(' - LinkedIn', '').replace(' | LinkedIn', '').trim();

                                    // Skip if name is too short or looks like UI text
                                    if (name.length > 2 && !name.toLowerCase().includes('cached')) {
                                        people.push({
                                            name: name,
                                            title: '',
                                            location: '',
                                            profileUrl: 'https://www.linkedin.com/in/' + match[1],
                                            source: 'google_fallback'
                                        });
                                    }
                                }
                            }
                        });

                        return { people: people.slice(0, 10), success: true };
                    }
                """)

                if google_result.get("people") and len(google_result["people"]) > 0:
                    logger.info(f"[LinkedIn] Google fallback found {len(google_result['people'])} profiles")
                    return google_result

                logger.warning("[LinkedIn] Google fallback found no results")
                return {"error": "LinkedIn login required and Google fallback found no results", "people": []}

            return result

        except Exception as e:
            logger.error(f"[LinkedIn] Search failed: {e}")
            return {"error": str(e), "people": []}

    async def get_profile_info(self, profile_url: str) -> Dict[str, Any]:
        """Get information from a LinkedIn profile."""
        try:
            await self.browser.navigate(profile_url)
            await asyncio.sleep(2)

            result = await self.browser.page.evaluate("""
                () => {
                    const name = document.querySelector('.text-heading-xlarge')?.innerText || '';
                    const headline = document.querySelector('.text-body-medium')?.innerText || '';
                    const location = document.querySelector('.text-body-small.inline')?.innerText || '';
                    const about = document.querySelector('#about + div')?.innerText || '';

                    const experience = [];
                    document.querySelectorAll('#experience + div li').forEach(exp => {
                        const title = exp.querySelector('.t-bold span')?.innerText || '';
                        const company = exp.querySelector('.t-normal span')?.innerText || '';
                        experience.push({ title, company });
                    });

                    return { name, headline, location, about, experience: experience.slice(0, 5), success: true };
                }
            """)
            return result
        except Exception as e:
            return {"error": str(e)}


class TrelloIntegration(ServiceIntegration):
    """Trello board automation."""

    BASE_URL = "https://trello.com"

    async def check_login(self) -> bool:
        """Check if logged into Trello."""
        try:
            await self.browser.navigate(self.BASE_URL)
            result = await self.browser.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    return text.includes('boards') || text.includes('workspaces');
                }
            """)
            return result
        except Exception as e:
            logger.debug(f"Trello login check failed: {e}")
            return False

    async def get_board_cards(self, board_url: str) -> Dict[str, Any]:
        """Get cards from a Trello board."""
        try:
            await self.browser.navigate(board_url)
            await asyncio.sleep(2)

            result = await self.browser.page.evaluate("""
                () => {
                    const lists = [];
                    document.querySelectorAll('.list').forEach(list => {
                        const listName = list.querySelector('.list-header-name')?.innerText || '';
                        const cards = [];

                        list.querySelectorAll('.list-card').forEach(card => {
                            const title = card.querySelector('.list-card-title')?.innerText || '';
                            cards.push({ title });
                        });

                        lists.push({ listName, cards });
                    });
                    return { lists, success: true };
                }
            """)
            return result
        except Exception as e:
            return {"error": str(e), "lists": []}


class SlackIntegration(ServiceIntegration):
    """Slack automation for status updates."""

    async def check_login(self) -> bool:
        """Check if logged into Slack (requires workspace URL)."""
        try:
            result = await self.browser.page.evaluate("""
                () => {
                    const url = window.location.href;
                    return url.includes('slack.com') &&
                           (document.body.innerText.includes('Channels') ||
                            document.body.innerText.includes('Direct messages'));
                }
            """)
            return result
        except Exception as e:
            logger.debug(f"Slack login check failed: {e}")
            return False

    async def post_message(self, channel: str, message: str) -> Dict[str, Any]:
        """Post a message to a Slack channel (opens message box)."""
        try:
            # This would need the workspace URL
            # Focus on the message input and type - uses visual fallback if selector fails
            await self.browser.fill('[data-qa="message_input"]', message, "the Slack message input box")
            return {"success": True, "message": "Message typed in Slack. Press Enter to send."}
        except Exception as e:
            return {"error": str(e)}


# Factory function to get the right integration
def get_integration(service_id: str, browser: PlaywrightClient) -> Optional[ServiceIntegration]:
    """Get the appropriate service integration."""
    integrations = {
        "gmail": GmailIntegration,
        "google_calendar": GoogleCalendarIntegration,
        "hubspot": HubSpotIntegration,
        "shopify": ShopifyIntegration,
        "linkedin": LinkedInIntegration,
        "trello": TrelloIntegration,
        "slack": SlackIntegration,
    }

    integration_class = integrations.get(service_id)
    if integration_class:
        return integration_class(browser)
    return None


# Convenience functions for common tasks
async def check_service_login(service_id: str, browser: PlaywrightClient) -> bool:
    """Check if logged into a service."""
    integration = get_integration(service_id, browser)
    if integration:
        return await integration.check_login()
    return False


async def get_gmail_inbox(browser: PlaywrightClient, max_emails: int = 10) -> Dict[str, Any]:
    """Get Gmail inbox summary."""
    gmail = GmailIntegration(browser)
    return await gmail.get_inbox_summary(max_emails)


async def search_hubspot_contacts(browser: PlaywrightClient, query: str) -> Dict[str, Any]:
    """Search HubSpot contacts."""
    hubspot = HubSpotIntegration(browser)
    return await hubspot.search_contacts(query)


async def research_linkedin_person(browser: PlaywrightClient, name: str) -> Dict[str, Any]:
    """Research a person on LinkedIn."""
    linkedin = LinkedInIntegration(browser)
    results = await linkedin.search_people(name)
    if results.get("people"):
        # Get first result's profile
        profile_url = results["people"][0].get("profileUrl")
        if profile_url:
            profile = await linkedin.get_profile_info(profile_url)
            results["profile_details"] = profile
    return results
