"""
Business Executors - Fast browser-based workflows for all use cases.

E: E-commerce (Amazon, product research)
F: Real Estate (Zillow, Redfin comps)
H: Logistics (FedEx, UPS tracking)
L: HR/Recruiting (LinkedIn research)
M: Education (Wikipedia, quiz generation)
O: IT/Engineering (Stack Overflow, error lookup)
"""

import asyncio
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger

from .base import BaseExecutor, ActionResult, ActionStatus


class E1_AmazonProductResearch(BaseExecutor):
    """Research products on Amazon - extract listings, prices, ratings."""

    capability = "E1"
    action = "amazon_product_research"
    required_params = ["query"]
    optional_params = ["count", "category"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        query = params.get("query", "wireless earbuds")
        count = params.get("count", 10)

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available",
            )

        products = []
        try:
            # Navigate to Amazon search
            search_query = query.replace(" ", "+")
            url = f"https://www.amazon.com/s?k={search_query}"
            await self.browser.navigate(url)
            await asyncio.sleep(3)

            # Check for login wall or CAPTCHA
            page_text = await self.browser.page.content()
            if "Enter the characters you see below" in page_text:
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    data={},
                    message="Amazon CAPTCHA detected. Please solve it in the browser and try again.",
                )

            # Extract product data using JavaScript
            products = await self.browser.page.evaluate("""
                () => {
                    const items = [];
                    const productCards = document.querySelectorAll('[data-component-type="s-search-result"]');

                    productCards.forEach((card, index) => {
                        if (index >= 20) return;

                        const titleEl = card.querySelector('h2 a span') || card.querySelector('.a-text-normal');
                        const priceWhole = card.querySelector('.a-price-whole');
                        const priceFraction = card.querySelector('.a-price-fraction');
                        const ratingEl = card.querySelector('.a-icon-star-small span') || card.querySelector('.a-icon-alt');
                        const reviewsEl = card.querySelector('[data-csa-c-func-deps="aui-da-a-popover"]') ||
                                         card.querySelector('.a-size-base.s-underline-text');
                        const imageEl = card.querySelector('.s-image');
                        const linkEl = card.querySelector('h2 a') || card.querySelector('.a-link-normal');

                        const title = titleEl ? titleEl.textContent.trim() : '';
                        let price = '';
                        if (priceWhole) {
                            price = '$' + priceWhole.textContent.replace(',', '').trim();
                            if (priceFraction) price += priceFraction.textContent.trim();
                        }

                        const rating = ratingEl ? (ratingEl.textContent.match(/(\d+\.?\d*)\s*out\s*of/i)?.[1] || ratingEl.textContent.match(/[\\d.]+/)?.[0] || '') : '';
                        const reviews = reviewsEl ? reviewsEl.textContent.replace(/[^\\d,]/g, '').replace(/^,+|,+$/g, '') : '';
                        const image = imageEl ? imageEl.src : '';
                        const link = linkEl ? 'https://amazon.com' + linkEl.getAttribute('href') : '';

                        if (title) {
                            items.push({
                                title: title.substring(0, 150),
                                price,
                                rating,
                                reviews,
                                image,
                                link: link.substring(0, 200),
                                position: index + 1
                            });
                        }
                    });

                    return items;
                }
            """)

            products = products[:count]

            # Save results
            saved_path = None
            if products:
                saved_path = self._save_results(products, f"amazon_{query.replace(' ', '_')}")

            summary = self._generate_summary(products, query)

            return ActionResult(
                status=ActionStatus.SUCCESS if products else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"products": products, "query": query, "count": len(products)},
                message=summary + (f"\n\nSaved to: {saved_path}" if saved_path else ""),
                next_actions=["E2_CompetitorAnalysis"]
            )

        except Exception as e:
            logger.error(f"Amazon research failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to research Amazon: {e}",
            )

    def _generate_summary(self, products: List[Dict], query: str) -> str:
        lines = [f"## Amazon Product Research: {query}", f"Found {len(products)} products\n"]

        for i, p in enumerate(products[:5], 1):
            lines.append(f"**{i}. {p.get('title', 'Unknown')[:60]}...**")
            lines.append(f"   Price: {p.get('price', 'N/A')} | Rating: {p.get('rating', 'N/A')}/5 | Reviews: {p.get('reviews', 'N/A')}")

        if len(products) > 5:
            lines.append(f"\n...and {len(products) - 5} more products")

        return "\n".join(lines)

    def _save_results(self, products: List[Dict], prefix: str) -> Optional[str]:
        try:
            from ..output_path import save_csv
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{prefix}_{timestamp}.csv"
            return str(save_csv(filename, products))
        except Exception as e:
            logger.warning(f"Failed to save: {e}")
            return None


class H1_ShipmentTracker(BaseExecutor):
    """Track shipments on FedEx, UPS, USPS."""

    capability = "H1"
    action = "track_shipment"
    required_params = ["tracking_number"]
    optional_params = ["carrier"]

    CARRIER_URLS = {
        "fedex": "https://www.fedex.com/fedextrack/?trknbr={}",
        "ups": "https://www.ups.com/track?loc=en_US&tracknum={}",
        "usps": "https://tools.usps.com/go/TrackConfirmAction?tLabels={}",
    }

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        tracking = params.get("tracking_number", "").strip()
        carrier = params.get("carrier", "").lower()

        if not tracking:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide a tracking number.",
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available",
            )

        # Auto-detect carrier if not specified
        if not carrier:
            carrier = self._detect_carrier(tracking)

        results = []
        try:
            if carrier in self.CARRIER_URLS:
                url = self.CARRIER_URLS[carrier].format(tracking)
                await self.browser.navigate(url)
                await asyncio.sleep(3)

                # Extract tracking info
                info = await self._extract_tracking_info(carrier)
                info["tracking_number"] = tracking
                info["carrier"] = carrier.upper()
                results.append(info)
            else:
                # Try all carriers
                for c, url_template in self.CARRIER_URLS.items():
                    url = url_template.format(tracking)
                    await self.browser.navigate(url)
                    await asyncio.sleep(3)
                    info = await self._extract_tracking_info(c)
                    if info.get("status"):
                        info["tracking_number"] = tracking
                        info["carrier"] = c.upper()
                        results.append(info)
                        break

            summary = self._generate_summary(results)

            return ActionResult(
                status=ActionStatus.SUCCESS if results else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"tracking_results": results},
                message=summary,
            )

        except Exception as e:
            logger.error(f"Tracking failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to track shipment: {e}",
            )

    def _detect_carrier(self, tracking: str) -> str:
        """Detect carrier from tracking number format."""
        tracking = tracking.replace(" ", "").upper()

        # UPS: 1Z followed by 16 alphanumeric (check first for specificity)
        if tracking.startswith("1Z") and len(tracking) == 18:
            return "ups"
        # USPS: 20-22 digits (check before FedEx to avoid overlap)
        if len(tracking) in [20, 22] and tracking.isdigit():
            return "usps"
        # FedEx: 12-15 digits (more specific range to avoid USPS overlap)
        if 12 <= len(tracking) <= 15 and tracking.isdigit():
            return "fedex"

        return ""  # Return empty if unable to detect

    async def _extract_tracking_info(self, carrier: str) -> Dict:
        """Extract tracking info from current page."""
        try:
            if carrier == "fedex":
                return await self.browser.page.evaluate("""
                    () => {
                        const status = document.querySelector('.shipment-status-progress__status-text, .travel-history__status')?.textContent?.trim() || '';
                        const location = document.querySelector('.shipment-status-progress__location, .travel-history__location')?.textContent?.trim() || '';
                        const date = document.querySelector('.shipment-status-progress__date, .travel-history__date')?.textContent?.trim() || '';
                        const delivery = document.querySelector('.delivery-date-text, .estimated-delivery')?.textContent?.trim() || '';
                        return { status, location, date, estimated_delivery: delivery };
                    }
                """)
            elif carrier == "ups":
                return await self.browser.page.evaluate("""
                    () => {
                        const status = document.querySelector('.ups-txt_size_xlg, .st_App-header h1')?.textContent?.trim() || '';
                        const delivery = document.querySelector('.ups-txt_size_lg.ups-txt_ctl_bold, .del_date')?.textContent?.trim() || '';
                        return { status, estimated_delivery: delivery };
                    }
                """)
            else:  # USPS
                return await self.browser.page.evaluate("""
                    () => {
                        const status = document.querySelector('.delivery_status, .tb-status')?.textContent?.trim() || '';
                        const date = document.querySelector('.tb-date')?.textContent?.trim() || '';
                        return { status, date };
                    }
                """)
        except Exception as e:
            logger.warning(f"Tracking extraction failed: {e}")
            return {}

    def _generate_summary(self, results: List[Dict]) -> str:
        if not results:
            return "No tracking information found. Please verify the tracking number."

        lines = ["## Shipment Tracking Results\n"]
        for r in results:
            lines.append(f"**{r.get('carrier', 'Unknown')}** - {r.get('tracking_number', '')}")
            lines.append(f"Status: {r.get('status', 'Unknown')}")
            if r.get('estimated_delivery'):
                lines.append(f"Estimated Delivery: {r.get('estimated_delivery')}")
            if r.get('location'):
                lines.append(f"Location: {r.get('location')}")
            lines.append("")

        return "\n".join(lines)


class M1_WikipediaResearch(BaseExecutor):
    """Research topics on Wikipedia and generate quizzes."""

    capability = "M1"
    action = "wikipedia_research"
    required_params = []  # Flexible - accepts topic, query, or target
    optional_params = ["topic", "query", "num_questions", "quiz_type"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        # Accept multiple parameter names for flexibility
        topic = params.get("topic", "") or params.get("query", "") or params.get("target", "")
        num_questions = params.get("num_questions", 10)
        quiz_type = params.get("quiz_type", "multiple_choice")

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available",
            )

        try:
            # Navigate to Wikipedia
            search_topic = topic.replace(" ", "_")
            url = f"https://en.wikipedia.org/wiki/{search_topic}"
            await self.browser.navigate(url)
            await asyncio.sleep(2)

            # Check if page exists
            page_text = await self.browser.page.content()
            if "Wikipedia does not have an article" in page_text:
                # Try search instead
                url = f"https://en.wikipedia.org/w/index.php?search={topic.replace(' ', '+')}"
                await self.browser.navigate(url)
                await asyncio.sleep(2)

            # Extract article content
            content = await self.browser.page.evaluate("""
                () => {
                    const article = document.querySelector('#mw-content-text .mw-parser-output');
                    if (!article) return { title: '', content: '', sections: [] };

                    const title = document.querySelector('#firstHeading')?.textContent || '';

                    // Get all paragraphs
                    const paragraphs = Array.from(article.querySelectorAll('p'))
                        .map(p => p.textContent.trim())
                        .filter(t => t.length > 50);

                    // Get section headings
                    const sections = Array.from(article.querySelectorAll('h2 .mw-headline, h3 .mw-headline'))
                        .map(h => h.textContent.trim())
                        .slice(0, 10);

                    // Get key facts from infobox
                    const infobox = document.querySelector('.infobox');
                    const facts = [];
                    if (infobox) {
                        const rows = infobox.querySelectorAll('tr');
                        rows.forEach(row => {
                            const label = row.querySelector('th')?.textContent?.trim();
                            const value = row.querySelector('td')?.textContent?.trim();
                            if (label && value && value.length < 100) {
                                facts.push({ label, value });
                            }
                        });
                    }

                    return {
                        title,
                        content: paragraphs.slice(0, 10).join('\\n\\n'),
                        sections,
                        facts: facts.slice(0, 15)
                    };
                }
            """)

            # Generate quiz questions from content
            quiz = self._generate_quiz(content, num_questions, quiz_type)

            # Save quiz
            saved_path = self._save_quiz(quiz, topic)

            summary = self._generate_summary(content, quiz)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "topic": topic,
                    "article": content,
                    "quiz": quiz,
                    "saved_to": saved_path
                },
                message=summary,
            )

        except Exception as e:
            logger.error(f"Wikipedia research failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to research Wikipedia: {e}",
            )

    def _generate_quiz(self, content: Dict, num_questions: int, quiz_type: str) -> List[Dict]:
        """Generate quiz questions from Wikipedia content."""
        questions = []
        facts = content.get("facts", [])

        # Generate fact-based questions
        for i, fact in enumerate(facts[:num_questions]):
            if quiz_type == "multiple_choice":
                q = {
                    "number": i + 1,
                    "question": f"What is the {fact['label'].lower()} of {content.get('title', 'this subject')}?",
                    "correct_answer": fact["value"],
                    "type": "fact"
                }
            else:  # fill in blank
                q = {
                    "number": i + 1,
                    "question": f"The {fact['label'].lower()} is ________.",
                    "correct_answer": fact["value"],
                    "type": "fill_blank"
                }
            questions.append(q)

        # Add section-based questions
        sections = content.get("sections", [])
        for i, section in enumerate(sections[:num_questions - len(questions)]):
            q = {
                "number": len(questions) + 1,
                "question": f"What topic does the section '{section}' cover?",
                "correct_answer": section,
                "type": "comprehension"
            }
            questions.append(q)

        return questions[:num_questions]

    def _save_quiz(self, quiz: List[Dict], topic: str) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"quiz_{topic.replace(' ', '_')}_{timestamp}.json"
            return str(save_json(filename, {"topic": topic, "questions": quiz}))
        except Exception as e:
            logger.warning(f"Failed to save quiz: {e}")
            return None

    def _generate_summary(self, content: Dict, quiz: List[Dict]) -> str:
        lines = [
            f"## Wikipedia Research: {content.get('title', 'Unknown')}",
            "",
            f"**Sections Found:** {len(content.get('sections', []))}",
            f"**Key Facts:** {len(content.get('facts', []))}",
            f"**Quiz Questions Generated:** {len(quiz)}",
            "",
            "### Sample Questions:",
        ]

        for q in quiz[:3]:
            lines.append(f"{q['number']}. {q['question']}")
            lines.append(f"   Answer: {q['correct_answer'][:50]}...")
            lines.append("")

        return "\n".join(lines)


class O1_StackOverflowSearch(BaseExecutor):
    """Search Stack Overflow for error solutions."""

    capability = "O1"
    action = "stackoverflow_search"
    required_params = []  # Flexible - accepts error, query, or target
    optional_params = ["error", "query", "language", "count"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        # Accept multiple parameter names for flexibility
        error = params.get("error", "") or params.get("query", "") or params.get("target", "")
        language = params.get("language", "")
        count = params.get("count", 5)

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available",
            )

        try:
            # Build search query
            query = error
            if language:
                query = f"[{language}] {error}"

            search_url = f"https://stackoverflow.com/search?q={query.replace(' ', '+')}"
            await self.browser.navigate(search_url)
            await asyncio.sleep(3)

            # Check for CAPTCHA
            page_text = await self.browser.page.content()
            if "Human verification" in page_text or "CAPTCHA" in page_text or "Are you a human" in page_text:
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    data={"error": "captcha"},
                    message="Stack Overflow CAPTCHA detected. Please complete the verification in the browser, then try again."
                )

            # Extract search results - try multiple selectors for robustness
            results = await self.browser.page.evaluate("""
                () => {
                    const questions = [];

                    // Try multiple selector patterns
                    const selectors = [
                        '.s-post-summary',
                        '.question-summary',
                        '[data-searchsession]',
                        '.search-result'
                    ];

                    let items = [];
                    for (const sel of selectors) {
                        items = document.querySelectorAll(sel);
                        if (items.length > 0) break;
                    }

                    items.forEach((item, index) => {
                        if (index >= 10) return;

                        // Try multiple title selectors
                        const titleEl = item.querySelector('.s-post-summary--content-title a') ||
                                       item.querySelector('.result-link a') ||
                                       item.querySelector('h3 a') ||
                                       item.querySelector('a.question-hyperlink');

                        const excerptEl = item.querySelector('.s-post-summary--content-excerpt') ||
                                         item.querySelector('.excerpt') ||
                                         item.querySelector('.summary');

                        const votesEl = item.querySelector('.s-post-summary--stats-item-number') ||
                                       item.querySelector('.vote-count-post');

                        const title = titleEl?.textContent?.trim() || '';
                        const link = titleEl?.href || '';
                        const excerpt = excerptEl?.textContent?.trim() || '';
                        const votes = votesEl?.textContent?.trim() || '0';

                        if (title) {
                            questions.push({ title, link, excerpt, votes, answers: '0', tags: [] });
                        }
                    });

                    return questions;
                }
            """)

            results = results[:count]

            # Get top answer for first result
            top_answer = None
            if results and results[0].get("link"):
                top_answer = await self._get_top_answer(results[0]["link"])

            summary = self._generate_summary(error, results, top_answer)

            return ActionResult(
                status=ActionStatus.SUCCESS if results else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "error": error,
                    "results": results,
                    "top_answer": top_answer,
                },
                message=summary,
            )

        except Exception as e:
            logger.error(f"Stack Overflow search failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to search Stack Overflow: {e}",
            )

    async def _get_top_answer(self, question_url: str) -> Optional[Dict]:
        """Get the top answer from a question page."""
        try:
            await self.browser.navigate(question_url)
            await asyncio.sleep(2)

            answer = await self.browser.page.evaluate("""
                () => {
                    const accepted = document.querySelector('.accepted-answer .s-prose');
                    const topAnswer = document.querySelector('.answer .s-prose');
                    const answerEl = accepted || topAnswer;

                    if (!answerEl) return null;

                    // Get code blocks
                    const codeBlocks = Array.from(answerEl.querySelectorAll('pre code'))
                        .map(c => c.textContent.trim())
                        .slice(0, 3);

                    // Get text content
                    const text = answerEl.textContent.substring(0, 500).trim();

                    const votesEl = answerEl.closest('.answer')?.querySelector('.js-vote-count');
                    const votes = votesEl?.textContent?.trim() || '0';

                    return { text, code_blocks: codeBlocks, votes, is_accepted: !!accepted };
                }
            """)

            return answer

        except Exception as e:
            logger.warning(f"Failed to get answer: {e}")
            return None

    def _generate_summary(self, error: str, results: List[Dict], top_answer: Optional[Dict]) -> str:
        lines = [
            f"## Stack Overflow: {error[:50]}...",
            f"Found {len(results)} related questions\n",
        ]

        if top_answer:
            lines.append("### Top Solution:")
            lines.append(f"{'✓ Accepted Answer' if top_answer.get('is_accepted') else 'Top Voted'} ({top_answer.get('votes', 0)} votes)")
            lines.append("")

            if top_answer.get("code_blocks"):
                lines.append("```")
                lines.append(top_answer["code_blocks"][0][:300])
                lines.append("```")
            else:
                lines.append(top_answer.get("text", "")[:300] + "...")
            lines.append("")

        lines.append("### Related Questions:")
        for i, r in enumerate(results[:5], 1):
            lines.append(f"{i}. **{r.get('title', '')[:60]}...**")
            lines.append(f"   Votes: {r.get('votes', 0)} | Answers: {r.get('answers', 0)} | Tags: {', '.join(r.get('tags', [])[:3])}")

        return "\n".join(lines)


class F1_ZillowPropertySearch(BaseExecutor):
    """Search Zillow for property comps and pricing."""

    capability = "F1"
    action = "zillow_search"
    required_params = ["location"]
    optional_params = ["beds", "baths", "price_max"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        location = params.get("location", "")
        beds = params.get("beds", 3)
        baths = params.get("baths", 2)
        price_max = params.get("price_max")

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available",
            )

        try:
            # Build Zillow search URL
            location_slug = location.lower().replace(" ", "-").replace(",", "")
            url = f"https://www.zillow.com/{location_slug}/"

            # Add filters
            if beds or baths:
                url += f"?searchQueryState=%7B%22filterState%22%3A%7B%22beds%22%3A%7B%22min%22%3A{beds}%7D%2C%22baths%22%3A%7B%22min%22%3A{baths}%7D%7D%7D"

            await self.browser.navigate(url)
            await asyncio.sleep(4)

            # Check for CAPTCHA
            page_text = await self.browser.page.content()
            if "Please verify you're a human" in page_text or "captcha" in page_text.lower():
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    data={},
                    message="Zillow CAPTCHA detected. Please solve it in the browser and try again.",
                )

            # Extract listings
            listings = await self.browser.page.evaluate("""
                () => {
                    const properties = [];
                    const cards = document.querySelectorAll('[data-test="property-card"], .list-card');

                    cards.forEach((card, index) => {
                        if (index >= 15) return;

                        const priceEl = card.querySelector('[data-test="property-card-price"], .list-card-price');
                        const addressEl = card.querySelector('[data-test="property-card-addr"], .list-card-addr');
                        const detailsEl = card.querySelector('[data-test="property-card-details"], .list-card-details');
                        const linkEl = card.querySelector('a[data-test="property-card-link"], .list-card-link');

                        const price = priceEl?.textContent?.trim() || '';
                        const address = addressEl?.textContent?.trim() || '';
                        const details = detailsEl?.textContent?.trim() || '';
                        const link = linkEl?.href || '';

                        // Parse beds/baths from details - handle decimals too
                        const bedsMatch = details.match(/(\\d+(?:\\.\\d+)?)\\s*(?:bd|bed|bedroom)/i);
                        const bathsMatch = details.match(/(\\d+(?:\\.\\d+)?)\\s*(?:ba|bath|bathroom)/i);
                        const sqftMatch = details.match(/([\\d,]+)\\s*(?:sqft|sq\\s*ft|square\\s*feet)/i);

                        if (price || address) {
                            properties.push({
                                price,
                                address,
                                beds: bedsMatch ? bedsMatch[1] : '',
                                baths: bathsMatch ? bathsMatch[1] : '',
                                sqft: sqftMatch ? sqftMatch[1] : '',
                                link,
                                details
                            });
                        }
                    });

                    return properties;
                }
            """)

            # Calculate average price for comps
            avg_price = self._calculate_avg_price(listings)

            # Save results
            saved_path = None
            if listings:
                saved_path = self._save_results(listings, f"zillow_{location.replace(' ', '_')}")

            summary = self._generate_summary(location, listings, avg_price)

            return ActionResult(
                status=ActionStatus.SUCCESS if listings else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "location": location,
                    "listings": listings,
                    "avg_price": avg_price,
                    "count": len(listings)
                },
                message=summary + (f"\n\nSaved to: {saved_path}" if saved_path else ""),
            )

        except Exception as e:
            logger.error(f"Zillow search failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to search Zillow: {e}",
            )

    def _calculate_avg_price(self, listings: List[Dict]) -> Optional[int]:
        """Calculate average price from listings."""
        prices = []
        for l in listings:
            price_str = l.get("price", "").replace("$", "").replace(",", "").replace("+", "").strip()

            try:
                # Handle K/M suffixes with decimals (e.g., "1.5M", "450K")
                if "M" in price_str.upper():
                    price_num = float(re.sub(r'[^\d.]', '', price_str))
                    price = int(price_num * 1000000)
                elif "K" in price_str.upper():
                    price_num = float(re.sub(r'[^\d.]', '', price_str))
                    price = int(price_num * 1000)
                else:
                    price = int(re.sub(r'[^\d]', '', price_str))

                if price > 10000:  # Filter out unrealistic values
                    prices.append(price)
            except:
                pass

        return int(sum(prices) / len(prices)) if prices else None

    def _save_results(self, listings: List[Dict], prefix: str) -> Optional[str]:
        try:
            from ..output_path import save_csv
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{prefix}_{timestamp}.csv"
            return str(save_csv(filename, listings))
        except Exception as e:
            logger.warning(f"Failed to save: {e}")
            return None

    def _generate_summary(self, location: str, listings: List[Dict], avg_price: Optional[int]) -> str:
        lines = [
            f"## Zillow Property Search: {location}",
            f"Found {len(listings)} properties",
        ]

        if avg_price:
            lines.append(f"**Average Price:** ${avg_price:,}")

        lines.append("\n### Top Listings:")

        for i, l in enumerate(listings[:5], 1):
            lines.append(f"{i}. **{l.get('price', 'N/A')}** - {l.get('address', 'Unknown')[:40]}")
            lines.append(f"   {l.get('beds', '?')} bed | {l.get('baths', '?')} bath | {l.get('sqft', '?')} sqft")

        return "\n".join(lines)


class L1_LinkedInProfileSearch(BaseExecutor):
    """Search and research LinkedIn profiles."""

    capability = "L1"
    action = "linkedin_search"
    required_params = []  # Flexible - accepts name, query, or target
    optional_params = ["name", "query", "company", "title", "skills"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        # Accept multiple parameter names for flexibility
        name = params.get("name", "") or params.get("query", "") or params.get("target", "")
        company = params.get("company", "")
        title = params.get("title", "")

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available",
            )

        try:
            # Build LinkedIn search URL
            query_parts = [name]
            if company:
                query_parts.append(company)
            if title:
                query_parts.append(title)

            query = " ".join(query_parts)
            url = f"https://www.linkedin.com/search/results/people/?keywords={query.replace(' ', '%20')}"

            await self.browser.navigate(url)
            await asyncio.sleep(3)

            # Check for login wall
            page_text = await self.browser.page.content()
            if "Sign in" in page_text and "Join now" in page_text:
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    data={},
                    message="LinkedIn login required. Please login in the browser and try again.",
                )

            # Extract profiles
            profiles = await self.browser.page.evaluate("""
                () => {
                    const results = [];
                    const cards = document.querySelectorAll('.reusable-search__result-container, .search-result__wrapper');

                    cards.forEach((card, index) => {
                        if (index >= 10) return;

                        const nameEl = card.querySelector('.entity-result__title-text a span span:first-child, .search-result__title');
                        const titleEl = card.querySelector('.entity-result__primary-subtitle, .search-result__truncate');
                        const locationEl = card.querySelector('.entity-result__secondary-subtitle, .subline-level-2');
                        const linkEl = card.querySelector('.entity-result__title-text a, .search-result__result-link');

                        const profileName = nameEl?.textContent?.trim() || '';
                        const profileTitle = titleEl?.textContent?.trim() || '';
                        const location = locationEl?.textContent?.trim() || '';
                        const profileUrl = linkEl?.href || '';

                        if (profileName) {
                            results.push({
                                name: profileName,
                                title: profileTitle,
                                location,
                                linkedin_url: profileUrl.split('?')[0]
                            });
                        }
                    });

                    return results;
                }
            """)

            summary = self._generate_summary(name, profiles)

            return ActionResult(
                status=ActionStatus.SUCCESS if profiles else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "search_name": name,
                    "profiles": profiles,
                    "count": len(profiles)
                },
                message=summary,
            )

        except Exception as e:
            logger.error(f"LinkedIn search failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to search LinkedIn: {e}",
            )

    def _generate_summary(self, name: str, profiles: List[Dict]) -> str:
        lines = [
            f"## LinkedIn Search: {name}",
            f"Found {len(profiles)} profiles\n",
        ]

        for i, p in enumerate(profiles[:5], 1):
            lines.append(f"**{i}. {p.get('name', 'Unknown')}**")
            lines.append(f"   {p.get('title', 'N/A')}")
            lines.append(f"   Location: {p.get('location', 'N/A')}")
            lines.append("")

        return "\n".join(lines)


# Registry of all business executors
BUSINESS_EXECUTORS = {
    "E1": E1_AmazonProductResearch,
    "H1": H1_ShipmentTracker,
    "M1": M1_WikipediaResearch,
    "O1": O1_StackOverflowSearch,
    "F1": F1_ZillowPropertySearch,
    "L1": L1_LinkedInProfileSearch,
}


def get_business_executor(capability: str):
    """Get executor class by capability ID."""
    return BUSINESS_EXECUTORS.get(capability)
