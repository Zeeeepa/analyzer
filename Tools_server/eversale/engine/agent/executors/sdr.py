"""
SDR Executors - Sales Development actions.

D1: Research prospects
D2: Write cold emails
D3: Send sequences
D4: Social profile research
D5: Build lead lists
D6: Update CRM
D7: Qualify leads
D8: Build outbound reports
D9: Social selling
D10: FB Ads Library extraction
"""

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

from .base import BaseExecutor, ActionResult, ActionStatus, ValidationResult


class D1_ResearchCompany(BaseExecutor):
    """Research a company - website, social, contacts, tech stack."""

    capability = "D1"
    action = "research_company"
    required_params = ["company"]
    optional_params = ["website", "depth"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        company = params["company"]
        website = params.get("website")

        research_data = {
            "company_name": company,
            "researched_at": datetime.now().isoformat(),
            "sources": [],
        }

        # Step 1: Search Google to find company website if not provided
        if not website and self.browser:
            try:
                search_url = f"https://www.google.com/search?q={company.replace(' ', '+')}+official+website"
                await self.browser.navigate(search_url)
                await asyncio.sleep(2)

                # Extract search results
                google_data = await self.browser.page.evaluate("""
                    () => {
                        const results = [];
                        const links = document.querySelectorAll('a[href]');
                        for (let link of links) {
                            const href = link.href;
                            if (href && !href.includes('google.') && !href.includes('youtube.') &&
                                href.startsWith('http') && !href.includes('webcache')) {
                                const text = link.textContent?.trim() || '';
                                if (text.length > 5) {
                                    results.push({url: href, text: text.slice(0, 100)});
                                }
                            }
                        }
                        return results.slice(0, 5);
                    }
                """)
                if google_data and len(google_data) > 0:
                    website = google_data[0].get('url')
                    research_data["google_results"] = google_data[:3]
                    research_data["sources"].append("Google")
            except Exception as e:
                logger.warning(f"Google search failed: {e}")

        # Fallback: guess website from company name
        if not website:
            clean_name = company.lower().replace(" ", "").replace(".", "")
            website = f"https://{clean_name}.com"

        research_data["website"] = website

        # Step 2: Research company website
        if self.browser and website:
            try:
                await self.browser.navigate(website)
                await asyncio.sleep(2)

                # Try extract_page_data_fast if available, otherwise fallback
                page_data = {}
                if hasattr(self.browser, 'extract_page_data_fast'):
                    page_data = await self.browser.extract_page_data_fast()

                if page_data and page_data.get("success"):
                    research_data["website_data"] = {
                        "title": page_data.get("title"),
                        "description": page_data.get("description", ""),
                        "emails": page_data.get("emails", []),
                        "phones": page_data.get("phones", []),
                        "social_profiles": page_data.get("socialProfiles", {}),
                        "tech_stack": page_data.get("techStack", []),
                        "company_info": page_data.get("companyInfo", {}),
                    }
                    research_data["sources"].append("website")

                    if page_data.get("cloudflare_blocked"):
                        research_data["warnings"] = ["Website blocked by Cloudflare"]
                else:
                    # Try to extract basic info even if fast extract failed
                    basic_info = await self.browser.page.evaluate("""
                        () => {
                            return {
                                title: document.title || '',
                                description: document.querySelector('meta[name="description"]')?.content || '',
                                h1: document.querySelector('h1')?.textContent?.trim() || '',
                                text: document.body?.innerText?.slice(0, 1000) || ''
                            };
                        }
                    """)
                    if basic_info:
                        research_data["website_data"] = basic_info
                        research_data["sources"].append("website")

            except Exception as e:
                logger.warning(f"Website research failed: {e}")
                research_data["errors"] = [f"Website: {str(e)}"]

        # Step 3: Try LinkedIn company search
        if self.browser:
            try:
                # Sanitize company name for LinkedIn URL
                import re
                company_slug = re.sub(r'[^a-z0-9-]', '', company.lower().replace(' ', '-').replace('&', 'and'))
                linkedin_url = f"https://www.linkedin.com/company/{company_slug}"
                await self.browser.navigate(linkedin_url)
                await asyncio.sleep(2)

                page_content = await self.browser.page.content()
                if "Sign in" not in page_content and "Join now" not in page_content:
                    linkedin_data = await self.browser.page.evaluate("""
                        () => {
                            return {
                                name: document.querySelector('h1')?.textContent?.trim() || '',
                                tagline: document.querySelector('.org-top-card-summary__tagline')?.textContent?.trim() || '',
                                followers: document.querySelector('.org-top-card-summary-info-list__info-item')?.textContent?.trim() || ''
                            };
                        }
                    """)
                    if linkedin_data.get('name'):
                        research_data["linkedin"] = linkedin_data
                        research_data["sources"].append("LinkedIn")
            except Exception as e:
                logger.debug(f"LinkedIn search skipped: {e}")

        # Generate summary
        summary = self._generate_summary(research_data)

        return ActionResult(
            status=ActionStatus.SUCCESS if research_data.get("sources") else ActionStatus.PARTIAL,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data=research_data,
            message=summary,
            next_actions=["D2_WriteColdEmail", "D4_LinkedInSearch"]
        )

    def _generate_summary(self, data: Dict) -> str:
        """Generate human-readable summary."""
        lines = [f"**Research: {data['company_name']}**"]

        if "website_data" in data:
            wd = data["website_data"]
            if wd.get("emails"):
                lines.append(f"- Emails: {', '.join(wd['emails'][:3])}")
            if wd.get("phones"):
                lines.append(f"- Phone: {wd['phones'][0]}")
            if wd.get("tech_stack"):
                lines.append(f"- Tech: {', '.join(wd['tech_stack'][:5])}")
            if wd.get("social_profiles"):
                socials = list(wd["social_profiles"].keys())
                lines.append(f"- Social: {', '.join(socials)}")

        if data.get("warnings"):
            lines.append(f"- Warning: {data['warnings'][0]}")

        return "\n".join(lines)


class D2_WriteColdEmail(BaseExecutor):
    """Write a personalized cold email."""

    capability = "D2"
    action = "write_cold_email"
    required_params = ["company"]
    optional_params = ["recipient", "value_prop", "research", "tone", "cta"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        company = params["company"]
        recipient = params.get("recipient", "there")
        value_prop = params.get("value_prop", "help you grow your business")
        research = params.get("research", {})
        tone = params.get("tone", "professional")
        cta = params.get("cta", "a quick 15-minute chat this week")

        # Build personalization from research
        personalization = ""
        if research:
            if research.get("tech_stack"):
                tech = research["tech_stack"][0] if isinstance(research["tech_stack"], list) else research["tech_stack"]
                personalization = f"I noticed you're using {tech} - "
            elif research.get("website_data", {}).get("tech_stack"):
                tech = research["website_data"]["tech_stack"][0]
                personalization = f"I noticed you're using {tech} - "

        # Generate email
        if tone == "casual":
            email = self._generate_casual_email(recipient, company, value_prop, personalization, cta)
        else:
            email = self._generate_professional_email(recipient, company, value_prop, personalization, cta)

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data={
                "email": email,
                "company": company,
                "recipient": recipient,
            },
            message=f"**Draft Email for {company}:**\n\n{email['subject']}\n\n{email['body']}",
            next_actions=["D3_SendSequence", "A1_SendEmail"]
        )

    def _generate_professional_email(self, recipient, company, value_prop, personalization, cta):
        subject = f"Quick question about {company}"

        body = f"""Hi {recipient},

{personalization}I wanted to reach out because I think we could {value_prop}.

We've helped similar companies achieve [specific result], and I'd love to explore if we could do the same for {company}.

Would you be open to {cta}?

Best regards,
[Your name]"""

        return {"subject": subject, "body": body}

    def _generate_casual_email(self, recipient, company, value_prop, personalization, cta):
        subject = f"Hey from [Your Company]"

        body = f"""Hey {recipient}!

{personalization}Came across {company} and thought you might be interested in how we're helping companies {value_prop}.

No pressure at all - just thought it might be worth a quick chat if you're curious.

{cta.capitalize()}?

Cheers,
[Your name]"""

        return {"subject": subject, "body": body}


class D5_BuildLeadList(BaseExecutor):
    """Build a lead list from various sources."""

    capability = "D5"
    action = "build_lead_list"
    required_params = []
    optional_params = ["source", "industry", "count", "output_file"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        source = params.get("source", "fb_ads")
        industry = params.get("industry", "saas")
        count = params.get("count", 50)
        output_file = params.get("output_file")

        leads = []

        if source in ["fb_ads", "facebook"]:
            leads = await self._scrape_fb_ads(industry, count)
        elif source == "reddit":
            leads = await self._scrape_reddit(industry, count)
        else:
            # Default to FB Ads
            leads = await self._scrape_fb_ads(industry, count)

        # Auto-save to user's output folder
        saved_path = None
        if leads:
            saved_path = self._save_leads(leads)

        return ActionResult(
            status=ActionStatus.SUCCESS if leads else ActionStatus.PARTIAL,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data={
                "leads": leads,
                "count": len(leads),
                "source": source,
                "industry": industry,
                "saved_to": saved_path,
            },
            message=f"Found {len(leads)} leads from {source}" + (f"\nSaved to: {saved_path}" if saved_path else ""),
            next_actions=["D1_ResearchCompany", "D2_WriteColdEmail"]
        )

    async def _scrape_fb_ads(self, industry: str, count: int) -> List[Dict]:
        """Scrape Facebook Ads Library."""
        if not self.browser:
            return []

        try:
            url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q={industry}&search_type=keyword_unordered"
            await self.browser.navigate(url)
            await asyncio.sleep(3)

            # Scroll to load more
            for _ in range(min(count // 10, 5)):
                await self.browser.page.evaluate("window.scrollBy(0, 1000)")
                await asyncio.sleep(1)

            result = await self.browser.extract_fb_ads_batch()
            # ToolResult has .data dict with 'ads' key
            ads = result.data.get("ads", []) if result.success else []

            # Format as leads
            leads = []
            for ad in ads[:count]:
                lead = {
                    "name": ad.get("name", ""),
                    "website": ad.get("websiteUrl", ""),
                    "category": ad.get("category", ""),
                    "fb_page": ad.get("fbPageUrl", ""),
                    "source": "fb_ads",
                    "extracted_at": datetime.now().isoformat(),
                }
                if lead["name"]:
                    leads.append(lead)

            return leads

        except Exception as e:
            logger.error(f"FB Ads scrape failed: {e}")
            return []

    async def _scrape_reddit(self, industry: str, count: int) -> List[Dict]:
        """
        Scrape Reddit for warm leads using API (bypasses browser blocking).

        Uses reddit_api tool which leverages RSS/JSON APIs instead of browser automation.
        """
        try:
            # Map industry to subreddits
            subreddit_map = {
                "saas": "SaaS",
                "startup": "startups",
                "marketing": "marketing",
                "ecommerce": "ecommerce",
                "tech": "technology",
                "software": "software",
                "ai": "artificial",
                "sales": "sales",
                "b2b": "b2b",
            }
            subreddit = subreddit_map.get(industry.lower(), "Entrepreneur")

            # PRIMARY: Use reddit_api tool (no browser needed)
            if self.browser and hasattr(self.browser, 'reddit_api_fetch'):
                result = await self.browser.reddit_api_fetch({
                    "subreddit": subreddit,
                    "sort": "new",
                    "limit": min(count * 2, 100)  # Fetch extra to filter
                })

                if result.get("success") and result.get("posts"):
                    posts = result["posts"]
                    logger.info(f"[REDDIT API] Got {len(posts)} posts from r/{subreddit}")

                    # Filter for warm signals and format as leads
                    leads = self._filter_reddit_warm_leads(posts, count)
                    return leads

            # FALLBACK: Navigate (will auto-use API via playwright_direct)
            if self.browser:
                url = f"https://www.reddit.com/r/{subreddit}/new/"
                nav_result = await self.browser.navigate(url)

                # Check if API was used
                if nav_result.get("reddit_api_used") and nav_result.get("data"):
                    posts = nav_result["data"].get("posts", [])
                    if posts:
                        leads = self._filter_reddit_warm_leads(posts, count)
                        return leads

                # Browser fallback
                await asyncio.sleep(2)
                result = await self.browser.extract_reddit_posts_batch()
                # ToolResult has .data dict with 'posts' key
                posts = result.data.get("posts", []) if result.success else []

                leads = []
                for post in posts:
                    if post.get("hasWarmSignal") or post.get("warmSignalCategory"):
                        lead = {
                            "title": post.get("title", ""),
                            "author": post.get("author", ""),
                            "subreddit": post.get("subreddit", subreddit),
                            "url": post.get("url", ""),
                            "warm_signal": post.get("warmSignalCategory", ""),
                            "intent": post.get("intentCategory", ""),
                            "source": "reddit",
                            "extracted_at": datetime.now().isoformat(),
                        }
                        leads.append(lead)

                return leads[:count]

            return []

        except Exception as e:
            logger.error(f"Reddit scrape failed: {e}")
            return []

    def _filter_reddit_warm_leads(self, posts: List[Dict], count: int) -> List[Dict]:
        """Filter Reddit posts for warm signals and convert to leads."""
        warm_keywords = [
            "looking for", "need", "recommend", "help", "advice", "best",
            "solution", "suggestions", "alternatives", "budget", "cost",
            "my company", "our team", "my business", "founder", "ceo",
            "looking to buy", "looking to hire", "frustrated", "problem"
        ]

        leads = []
        for post in posts:
            # Handle both dict and object posts
            if hasattr(post, 'title'):
                title = post.title
                author = post.author
                subreddit = post.subreddit
                permalink = post.permalink
                selftext = getattr(post, 'selftext', '')
                score = getattr(post, 'score', 0)
            else:
                title = post.get("title", "")
                author = post.get("author", "")
                subreddit = post.get("subreddit", "")
                permalink = post.get("permalink", "")
                selftext = post.get("selftext", "")
                score = post.get("score", 0)

            text_lower = f"{title} {selftext}".lower()

            # Check for warm signals
            detected_signals = [kw for kw in warm_keywords if kw in text_lower]

            if detected_signals:
                lead = {
                    "title": title[:100],
                    "author": author,
                    "subreddit": subreddit,
                    "url": permalink if permalink.startswith("http") else f"https://reddit.com{permalink}",
                    "warm_signal": ", ".join(detected_signals[:3]),
                    "score": score,
                    "source": "reddit_api",
                    "extracted_at": datetime.now().isoformat(),
                }
                leads.append(lead)

        # Sort by number of warm signals detected
        leads.sort(key=lambda x: len(x.get("warm_signal", "").split(",")), reverse=True)

        return leads[:count]

    def _save_leads(self, leads: List[Dict], filepath: str = None):
        """Save leads to CSV in user's output folder."""
        if not leads:
            return None

        # Use cross-platform output folder
        try:
            from ..output_path import save_csv
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"leads_{timestamp}.csv"
            path = save_csv(filename, leads)
            logger.info(f"Saved {len(leads)} leads to {path}")
            return str(path)
        except ImportError:
            # Fallback to provided path
            if not filepath:
                filepath = f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

            Path(filepath).parent.mkdir(parents=True, exist_ok=True)

            all_keys = set()
            for lead in leads:
                all_keys.update(lead.keys())

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
                writer.writeheader()
                writer.writerows(leads)

            logger.info(f"Saved {len(leads)} leads to {filepath}")
            return filepath


class D4_LinkedInSearch(BaseExecutor):
    """Search LinkedIn for people."""

    capability = "D4"
    action = "linkedin_search"
    required_params = []  # Flexible - accepts query, name, or target
    optional_params = ["query", "name", "filters"]
    requires_login = ["linkedin"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        # Accept multiple parameter names for flexibility
        query = params.get("query", "") or params.get("name", "") or params.get("target", "")

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error="Browser not available"
            )

        try:
            # Check if logged in
            from ..service_integrations import LinkedInIntegration
            linkedin = LinkedInIntegration(self.browser)

            is_logged_in = await linkedin.check_login()
            if not is_logged_in:
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    error="Not logged into LinkedIn",
                    message="Please log into LinkedIn first at https://www.linkedin.com/login"
                )

            # Search
            result = await linkedin.search_people(query)

            if result.get("success"):
                people = result.get("people", [])
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    data={"people": people, "count": len(people)},
                    message=f"Found {len(people)} people matching '{query}'",
                    next_actions=["D1_ResearchCompany", "D2_WriteColdEmail"]
                )
            else:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    error=result.get("error", "Search failed")
                )

        except Exception as e:
            logger.error(f"LinkedIn search failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e)
            )


class D7_QualifyLead(BaseExecutor):
    """Qualify a lead based on criteria."""

    capability = "D7"
    action = "qualify_lead"
    required_params = ["lead"]
    optional_params = ["criteria"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        lead = params["lead"]
        criteria = params.get("criteria", {})

        # Default scoring criteria
        score = 0
        reasons = []

        # Check website presence
        if lead.get("website"):
            score += 20
            reasons.append("Has website")

        # Check email presence
        if lead.get("emails") or lead.get("email"):
            score += 15
            reasons.append("Has email")

        # Check social presence
        if lead.get("social_profiles") or lead.get("linkedin"):
            score += 15
            reasons.append("Has social profiles")

        # Check tech stack (indicates sophistication)
        tech = lead.get("tech_stack", [])
        if tech:
            score += 10
            if any(t in ["React", "Next.js", "Vue", "Angular"] for t in tech):
                score += 10
                reasons.append("Modern tech stack")

        # Check if active advertiser
        if lead.get("source") == "fb_ads":
            score += 20
            reasons.append("Active advertiser")

        # Check warm signals from Reddit
        if lead.get("warm_signal") or lead.get("hasWarmSignal"):
            score += 25
            reasons.append(f"Warm signal: {lead.get('warm_signal', 'detected')}")

        # Determine qualification
        if score >= 70:
            qualification = "HOT"
        elif score >= 50:
            qualification = "WARM"
        elif score >= 30:
            qualification = "COOL"
        else:
            qualification = "COLD"

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data={
                "lead": lead,
                "score": score,
                "qualification": qualification,
                "reasons": reasons,
            },
            message=f"Lead qualified as **{qualification}** (Score: {score}/100)\nReasons: {', '.join(reasons)}"
        )


class D3_SendSequence(BaseExecutor):
    """Send email sequences and follow-ups."""

    capability = "D3"
    action = "send_sequence"
    required_params = ["recipient"]
    optional_params = ["template", "sequence_steps", "delay_days"]
    requires_login = ["gmail", "outlook"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        recipient = params["recipient"]
        template = params.get("template", "default")
        sequence_steps = params.get("sequence_steps", 3)
        delay_days = params.get("delay_days", [0, 3, 7])

        # Build sequence plan
        sequence = []
        for i in range(sequence_steps):
            step = {
                "step": i + 1,
                "recipient": recipient,
                "delay_days": delay_days[i] if i < len(delay_days) else delay_days[-1] * (i + 1),
                "template": f"{template}_step{i+1}",
                "status": "pending"
            }
            sequence.append(step)

        # In a real implementation, this would integrate with email service
        # For now, we generate the sequence plan
        summary = f"""## Email Sequence Created

**Recipient:** {recipient}
**Steps:** {sequence_steps}
**Template:** {template}

### Sequence Plan:
"""
        for step in sequence:
            summary += f"- Step {step['step']}: Send after {step['delay_days']} days\n"

        summary += "\n_Note: Actual sending requires email service integration_"

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data={"sequence": sequence, "recipient": recipient},
            message=summary,
            next_actions=["D2_WriteColdEmail"]
        )


class D6_UpdateCRM(BaseExecutor):
    """Update CRM with contact and activity data."""

    capability = "D6"
    action = "update_crm"
    required_params = ["contact"]
    optional_params = ["crm", "action_type", "notes"]
    requires_login = ["hubspot", "salesforce"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        contact = params["contact"]
        crm = params.get("crm", "hubspot")
        action_type = params.get("action_type", "update")
        notes = params.get("notes", "")

        # Parse contact if string
        if isinstance(contact, str):
            # Try to extract contact info
            import re
            contact_data = {"raw": contact}

            email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', contact)
            if email:
                contact_data["email"] = email.group()

            # Look for name (first capitalized words)
            name = re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', contact)
            if name:
                contact_data["name"] = name.group()

            contact = contact_data

        # Generate CRM update record
        update_record = {
            "crm": crm,
            "action": action_type,
            "contact": contact,
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
            "status": "queued"
        }

        summary = f"""## CRM Update Queued

**CRM:** {crm.title()}
**Action:** {action_type}
**Contact:** {contact.get('name', contact.get('email', 'Unknown'))}
"""
        if notes:
            summary += f"**Notes:** {notes}\n"

        summary += "\n_Note: Actual CRM integration requires service connection_"

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data=update_record,
            message=summary
        )


class D8_OutboundReport(BaseExecutor):
    """Generate outbound activity reports."""

    capability = "D8"
    action = "outbound_report"
    required_params = []
    optional_params = ["period", "metrics", "activities"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        period = params.get("period", "week")
        metrics = params.get("metrics", ["emails_sent", "replies", "meetings_booked"])
        activities = params.get("activities", [])

        # If activities provided, calculate real metrics
        if activities:
            report_data = self._calculate_metrics(activities)
        else:
            # Generate sample report structure
            report_data = {
                "period": period,
                "emails_sent": 0,
                "emails_opened": 0,
                "replies_received": 0,
                "positive_replies": 0,
                "meetings_booked": 0,
                "leads_qualified": 0,
                "conversion_rate": "0%",
                "reply_rate": "0%",
            }

        # Generate report
        report = f"""## Outbound Activity Report

**Period:** {period.title()}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

### Key Metrics

| Metric | Value |
|--------|-------|
| Emails Sent | {report_data.get('emails_sent', 0)} |
| Emails Opened | {report_data.get('emails_opened', 0)} |
| Replies Received | {report_data.get('replies_received', 0)} |
| Positive Replies | {report_data.get('positive_replies', 0)} |
| Meetings Booked | {report_data.get('meetings_booked', 0)} |
| Leads Qualified | {report_data.get('leads_qualified', 0)} |

### Performance

- **Reply Rate:** {report_data.get('reply_rate', '0%')}
- **Conversion Rate:** {report_data.get('conversion_rate', '0%')}

### Recommendations

1. Focus on high-performing templates
2. Optimize send times based on open rates
3. Follow up on warm leads within 24 hours
"""

        # Save report
        saved_path = None
        try:
            from ..output_path import save_output
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"outbound_report_{period}_{timestamp}.md"
            saved_path = str(save_output(filename, report))
        except ImportError:
            pass

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data=report_data,
            message=report + (f"\n\n**Saved to:** {saved_path}" if saved_path else "")
        )

    def _calculate_metrics(self, activities: List[Dict]) -> Dict:
        """Calculate metrics from activity data."""
        metrics = {
            "emails_sent": 0,
            "emails_opened": 0,
            "replies_received": 0,
            "positive_replies": 0,
            "meetings_booked": 0,
            "leads_qualified": 0,
        }

        for activity in activities:
            activity_type = activity.get("type", "").lower()
            if "sent" in activity_type or "email" in activity_type:
                metrics["emails_sent"] += 1
            if "open" in activity_type:
                metrics["emails_opened"] += 1
            if "reply" in activity_type:
                metrics["replies_received"] += 1
                if activity.get("sentiment") == "positive":
                    metrics["positive_replies"] += 1
            if "meeting" in activity_type or "booked" in activity_type:
                metrics["meetings_booked"] += 1
            if "qualified" in activity_type:
                metrics["leads_qualified"] += 1

        # Calculate rates
        if metrics["emails_sent"] > 0:
            metrics["reply_rate"] = f"{(metrics['replies_received'] / metrics['emails_sent'] * 100):.1f}%"
            metrics["conversion_rate"] = f"{(metrics['meetings_booked'] / metrics['emails_sent'] * 100):.1f}%"
        else:
            metrics["reply_rate"] = "0%"
            metrics["conversion_rate"] = "0%"

        return metrics


class D9_SocialSelling(BaseExecutor):
    """Social selling and engagement on LinkedIn/Twitter."""

    capability = "D9"
    action = "social_selling"
    required_params = []
    optional_params = ["platform", "target", "message", "action_type"]
    requires_login = ["linkedin", "twitter"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        platform = params.get("platform", "linkedin")
        target = params.get("target", "")
        message = params.get("message", "")
        action_type = params.get("action_type", "engage")

        # Generate engagement plan
        plan = {
            "platform": platform,
            "target": target,
            "action_type": action_type,
            "timestamp": datetime.now().isoformat(),
            "status": "queued"
        }

        summary = f"""## Social Selling Action Queued

**Platform:** {platform.title()}
**Target:** {target}
**Action:** {action_type}
"""
        if message:
            summary += f"**Message:** {message[:100]}\n"

        summary += "\n_Note: Actual social platform integration requires service connection_"

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data=plan,
            message=summary
        )


class D10_FBAdsExtraction(BaseExecutor):
    """Extract leads from Facebook Ads Library."""

    capability = "D10"
    action = "fb_ads_extraction"
    required_params = []
    optional_params = ["search_term", "limit", "country", "prompt"]

    def _extract_search_term_from_prompt(self, prompt: str) -> Optional[str]:
        """Extract search term from prompt if not explicitly provided."""
        import re

        # Try quoted terms first (most reliable)
        quoted = re.findall(r'["\']([^"\']{3,})["\']', prompt)
        if quoted:
            return quoted[0]

        # Try "search X" pattern
        search_match = re.search(r'search\s+(?!fb\s|facebook\s|meta\s|ads\s)([a-zA-Z][^;,]+?)(?:\s*[;,]|$)', prompt, re.I)
        if search_match:
            return search_match.group(1).strip()

        # Try "for X" pattern
        for_match = re.search(r'for\s+([a-zA-Z][^;,]+?)(?:\s*[;,]|$)', prompt, re.I)
        if for_match:
            return for_match.group(1).strip()

        # Try "keywords: X" pattern
        kw_match = re.search(r'keywords?[:\s]+([^;,]+?)(?:\s*[;,]|$)', prompt, re.I)
        if kw_match:
            return kw_match.group(1).strip()

        return None

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        search_term = params.get("search_term")

        # If no search_term provided, try to extract from prompt
        if not search_term or search_term == "marketing":
            prompt = params.get("prompt", "")
            extracted = self._extract_search_term_from_prompt(prompt)
            if extracted:
                search_term = extracted
                logger.info(f"[D10] Extracted search term from prompt: {search_term}")
            else:
                search_term = search_term or "marketing"  # Keep default only as last resort

        limit = params.get("limit", 20)
        country = params.get("country", "US")

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error="Browser not available"
            )

        try:
            # Build FB Ads Library URL
            import urllib.parse
            encoded_term = urllib.parse.quote(search_term)
            url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={country}&q={encoded_term}&search_type=keyword_unordered"

            logger.info(f"[D10] Navigating to FB Ads Library: {search_term}")
            await self.browser.navigate(url)
            await asyncio.sleep(3)

            # Scroll to load more ads
            for _ in range(min(limit // 10, 5)):
                await self.browser.page.evaluate("window.scrollBy(0, 1000)")
                await asyncio.sleep(1)

            # Extract ads using the browser's FB ads extraction tool
            result = await self.browser.extract_fb_ads_batch()

            if not result.success:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    error=result.error or "Failed to extract FB ads"
                )

            ads = result.data.get("ads", [])[:limit]

            # Format as leads
            leads = []
            for ad in ads:
                lead = {
                    "name": ad.get("name", ""),
                    "website": ad.get("websiteUrl", ""),
                    "category": ad.get("category", ""),
                    "fb_page": ad.get("fbPageUrl", ""),
                    "source": "fb_ads",
                    "search_term": search_term,
                    "extracted_at": datetime.now().isoformat(),
                }
                if lead["name"]:
                    leads.append(lead)

            # Save to CSV
            output_file = None
            if leads:
                output_file = self._save_leads_csv(leads, search_term)

            summary = f"""## Facebook Ads Extraction Complete

**Search Term:** {search_term}
**Country:** {country}
**Ads Found:** {len(leads)}
"""
            if output_file:
                summary += f"**Saved to:** {output_file}\n"

            return ActionResult(
                status=ActionStatus.SUCCESS if leads else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "leads": leads,
                    "count": len(leads),
                    "search_term": search_term,
                    "output_file": output_file
                },
                message=summary,
                next_actions=["D1_ResearchCompany", "D7_QualifyLead"]
            )

        except Exception as e:
            logger.error(f"[D10] FB Ads extraction failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e)
            )

    def _save_leads_csv(self, leads: List[Dict], search_term: str) -> str:
        """Save leads to CSV file."""
        try:
            from ..output_path import save_csv
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"fb_ads_{search_term.replace(' ', '_')}_{timestamp}.csv"
            path = save_csv(filename, leads)
            logger.info(f"Saved {len(leads)} leads to {path}")
            return str(path)
        except ImportError:
            # Fallback
            filename = f"fb_ads_{search_term.replace(' ', '_')}.csv"
            Path(filename).parent.mkdir(parents=True, exist_ok=True)

            all_keys = set()
            for lead in leads:
                all_keys.update(lead.keys())

            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
                writer.writeheader()
                writer.writerows(leads)

            logger.info(f"Saved {len(leads)} leads to {filename}")
            return filename


# Registry of all SDR executors
SDR_EXECUTORS = {
    "D1": D1_ResearchCompany,
    "D2": D2_WriteColdEmail,
    "D3": D3_SendSequence,
    "D4": D4_LinkedInSearch,
    "D5": D5_BuildLeadList,
    "D6": D6_UpdateCRM,
    "D7": D7_QualifyLead,
    "D8": D8_OutboundReport,
    "D9": D9_SocialSelling,
    "D10": D10_FBAdsExtraction,
}


def get_sdr_executor(capability: str, browser=None, context=None) -> Optional[BaseExecutor]:
    """Get an SDR executor by capability code."""
    executor_class = SDR_EXECUTORS.get(capability)
    if executor_class:
        return executor_class(browser=browser, context=context)
    return None
