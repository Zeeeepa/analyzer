"""
Agentic Workflows - Browser-based automation for all business tasks (A-O)
These workflows use Playwright to actually DO the work, not just parse text.
Works like the SDR system - real browser automation.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json

# ============================================================================
# WORKFLOW DEFINITIONS - Each defines steps for the agent to execute
# ============================================================================

@dataclass
class WorkflowStep:
    action: str  # navigate, extract, click, fill, search, ask_login, save
    target: str  # URL, selector, or description
    description: str
    fallback: str = ""  # What to do if step fails

@dataclass
class AgenticWorkflow:
    name: str
    description: str
    requires_login: List[str]  # Sites that need login
    steps: List[WorkflowStep]
    output_format: str  # csv, json, text, email

# ============================================================================
# A) ADMIN - EMAIL INBOX PROCESSING
# ============================================================================

WORKFLOW_EMAIL_INBOX = AgenticWorkflow(
    name="email_inbox_processing",
    description="Read inbox emails, summarize, identify action items, draft replies",
    requires_login=["gmail.com", "outlook.com", "mail.yahoo.com"],
    steps=[
        WorkflowStep(
            action="ask_login",
            target="email",
            description="Ask user which email provider and ensure they're logged in"
        ),
        WorkflowStep(
            action="navigate",
            target="https://mail.google.com OR https://outlook.live.com",
            description="Navigate to user's email inbox"
        ),
        WorkflowStep(
            action="check_login",
            target="inbox, compose button",
            description="Verify logged in - look for inbox elements. If login wall, ask user to login"
        ),
        WorkflowStep(
            action="extract_emails",
            target="email list",
            description="""Use playwright_snapshot to see inbox. Extract for each email:
            - Sender name and email
            - Subject line
            - Preview text
            - Date/time
            - Is it unread?
            - Has attachments?"""
        ),
        WorkflowStep(
            action="analyze_each",
            target="top 15 emails",
            description="""For each email, click to open and analyze:
            - What is this email about? (1 sentence summary)
            - Does it need a reply? (yes/no)
            - Priority level (high/medium/low)
            - Action type: reply, forward, archive, schedule, none
            - If needs reply, draft a response"""
        ),
        WorkflowStep(
            action="save_results",
            target="email_summary.csv",
            description="Save results: sender, subject, summary, needs_action, priority, draft_reply"
        )
    ],
    output_format="csv"
)

# ============================================================================
# B) BACK-OFFICE - SPREADSHEET CLEANING WITH WEB ENRICHMENT
# ============================================================================

WORKFLOW_SPREADSHEET = AgenticWorkflow(
    name="spreadsheet_cleaning",
    description="Clean spreadsheet data and enrich with web lookups",
    requires_login=["docs.google.com"],
    steps=[
        WorkflowStep(
            action="input",
            target="spreadsheet_url or file",
            description="Get spreadsheet URL (Google Sheets) or ask user to paste data"
        ),
        WorkflowStep(
            action="navigate",
            target="Google Sheets URL",
            description="If Google Sheets URL provided, navigate to it"
        ),
        WorkflowStep(
            action="extract_data",
            target="spreadsheet content",
            description="Extract all data from spreadsheet using playwright_get_text or snapshot"
        ),
        WorkflowStep(
            action="analyze_columns",
            target="column headers",
            description="""Identify column types:
            - Names (normalize capitalization)
            - Emails (validate format, lowercase)
            - Phones (normalize to standard format)
            - Addresses (can lookup/verify)
            - Company names (can lookup on LinkedIn/Google)
            - Dates (normalize to YYYY-MM-DD)"""
        ),
        WorkflowStep(
            action="enrich_web",
            target="company names, domains",
            description="""For company columns, optionally enrich:
            - Search company on Google/LinkedIn
            - Get company website, size, industry
            - Verify company exists"""
        ),
        WorkflowStep(
            action="validate_emails",
            target="email column",
            description="Check email format, optionally verify domain exists"
        ),
        WorkflowStep(
            action="deduplicate",
            target="all rows",
            description="Find and flag duplicate entries based on email or name+company"
        ),
        WorkflowStep(
            action="save_results",
            target="cleaned_data.csv",
            description="Output cleaned, normalized, deduplicated CSV"
        )
    ],
    output_format="csv"
)

# ============================================================================
# C) CUSTOMER OPS - SUPPORT TICKET HANDLING
# ============================================================================

WORKFLOW_SUPPORT_TICKETS = AgenticWorkflow(
    name="support_ticket_classification",
    description="Classify support tickets and draft replies using knowledge base",
    requires_login=["zendesk.com", "freshdesk.com", "intercom.com", "helpscout.com"],
    steps=[
        WorkflowStep(
            action="ask_login",
            target="support platform",
            description="Ask user which support platform (Zendesk, Freshdesk, Intercom, etc.)"
        ),
        WorkflowStep(
            action="navigate",
            target="support platform URL",
            description="Navigate to the support ticket dashboard"
        ),
        WorkflowStep(
            action="check_login",
            target="ticket list",
            description="Verify logged in. If login wall, ask user to login first"
        ),
        WorkflowStep(
            action="extract_tickets",
            target="open tickets",
            description="""For each open/pending ticket extract:
            - Ticket ID
            - Customer name/email
            - Subject
            - Full message content
            - Created date
            - Current status"""
        ),
        WorkflowStep(
            action="classify_ticket",
            target="each ticket",
            description="""Analyze and classify each ticket:
            - Category: billing, technical, general, complaint, feature_request, refund
            - Priority: urgent, high, medium, low
            - Sentiment: angry, frustrated, neutral, happy
            - Complexity: simple (template reply), complex (needs human)"""
        ),
        WorkflowStep(
            action="search_knowledge_base",
            target="ticket keywords",
            description="""For each ticket, search for solutions:
            - If platform has KB, search it
            - Search Google for common solutions
            - Look for similar resolved tickets"""
        ),
        WorkflowStep(
            action="draft_reply",
            target="each ticket",
            description="""Draft appropriate reply:
            - Match tone to customer sentiment
            - Include solution from knowledge base
            - For angry customers: apologize first, then solve
            - For billing: include specific account details
            - For technical: include step-by-step instructions"""
        ),
        WorkflowStep(
            action="save_results",
            target="tickets_processed.csv",
            description="Output: ticket_id, category, priority, sentiment, suggested_reply"
        )
    ],
    output_format="csv"
)

# ============================================================================
# D) SALES/SDR - Already implemented in main system
# ============================================================================

WORKFLOW_SDR_PROSPECTING = AgenticWorkflow(
    name="sdr_prospecting",
    description="Research companies, find contacts, generate personalized outreach",
    requires_login=["linkedin.com", "facebook.com"],
    steps=[
        WorkflowStep(
            action="get_icp",
            target="user input",
            description="Ask user for ICP: industry, company size, job titles, location"
        ),
        WorkflowStep(
            action="search_companies",
            target="LinkedIn, Google, Crunchbase",
            description="""Find target companies:
            - LinkedIn company search
            - Google search: "[industry] companies [location]"
            - Crunchbase for startups
            - Facebook Ads Library for advertisers"""
        ),
        WorkflowStep(
            action="find_contacts",
            target="each company",
            description="""For each company find decision makers:
            - LinkedIn people search at company
            - Look for titles: CEO, CTO, VP Sales, Head of Marketing
            - Get: name, title, LinkedIn URL"""
        ),
        WorkflowStep(
            action="get_contact_info",
            target="company website",
            description="""Visit company website:
            - Find contact page, about page
            - Extract emails, phone numbers
            - Use playwright_extract_page_fast"""
        ),
        WorkflowStep(
            action="research_prospect",
            target="each contact",
            description="""Research for personalization:
            - Recent LinkedIn posts
            - Company news
            - Funding announcements
            - Job postings (indicates growth)"""
        ),
        WorkflowStep(
            action="generate_outreach",
            target="each prospect",
            description="""Create personalized email:
            - Reference something specific about them
            - Connect to their pain points
            - Clear value proposition
            - Single CTA"""
        ),
        WorkflowStep(
            action="save_results",
            target="prospects.csv",
            description="Output: name, title, company, email, linkedin, personalized_email"
        )
    ],
    output_format="csv"
)

# ============================================================================
# E) E-COMMERCE - PRODUCT RESEARCH & DESCRIPTION
# ============================================================================

WORKFLOW_ECOMMERCE_PRODUCT = AgenticWorkflow(
    name="ecommerce_product_creation",
    description="Research competitors and create optimized product listings",
    requires_login=["amazon.com (for seller central)", "shopify admin"],
    steps=[
        WorkflowStep(
            action="get_product_info",
            target="user input",
            description="Get product details: name, category, specs, images, price point"
        ),
        WorkflowStep(
            action="search_competitors",
            target="Amazon, Google Shopping",
            description="""Research competing products:
            - Search Amazon for similar products
            - Note: top-selling items, their titles, bullet points
            - Extract: price range, key features highlighted
            - Look at customer reviews for pain points"""
        ),
        WorkflowStep(
            action="analyze_keywords",
            target="Google, Amazon search",
            description="""Find SEO keywords:
            - Search Google for product category
            - Note autocomplete suggestions
            - Look at "People also ask"
            - Check Amazon search suggestions"""
        ),
        WorkflowStep(
            action="analyze_reviews",
            target="competitor reviews",
            description="""From competitor reviews extract:
            - What customers love (use in benefits)
            - What customers complain about (address in your listing)
            - Keywords customers use"""
        ),
        WorkflowStep(
            action="generate_title",
            target="product title",
            description="""Create SEO title:
            - Include main keyword
            - Brand name + Product name + Key feature + Size/Color
            - Under 200 characters
            - Front-load important keywords"""
        ),
        WorkflowStep(
            action="generate_bullets",
            target="bullet points",
            description="""Create 5 bullet points:
            - Lead with benefit, then feature
            - Include keywords naturally
            - Address competitor weaknesses
            - Use CAPS for key terms"""
        ),
        WorkflowStep(
            action="generate_description",
            target="product description",
            description="""Create compelling description:
            - Tell a story / paint a picture
            - Include all keywords
            - Address pain points from reviews
            - End with call to action"""
        ),
        WorkflowStep(
            action="generate_faq",
            target="FAQ section",
            description="""Create FAQ from:
            - Common questions in competitor reviews
            - "People also ask" from Google
            - Pre-emptive objection handling"""
        ),
        WorkflowStep(
            action="save_results",
            target="product_listing.json",
            description="Output: title, bullets, description, faq, keywords"
        )
    ],
    output_format="json"
)

# ============================================================================
# F) REAL ESTATE - INSPECTION & LISTING
# ============================================================================

WORKFLOW_REAL_ESTATE = AgenticWorkflow(
    name="real_estate_listing",
    description="Research comps, analyze inspection, create MLS listing",
    requires_login=["zillow.com", "realtor.com", "redfin.com"],
    steps=[
        WorkflowStep(
            action="get_property_info",
            target="user input",
            description="Get property: address, beds, baths, sqft, lot size, year built"
        ),
        WorkflowStep(
            action="get_inspection_report",
            target="user input",
            description="Get inspection report text or key findings"
        ),
        WorkflowStep(
            action="search_comps",
            target="Zillow, Redfin",
            description="""Find comparable properties:
            - Search Zillow/Redfin for address
            - Find recently sold homes nearby (same beds/baths)
            - Note: sale prices, days on market, price/sqft
            - Extract: 3-5 best comps"""
        ),
        WorkflowStep(
            action="analyze_neighborhood",
            target="Zillow, Google",
            description="""Research neighborhood:
            - Schools (ratings from Zillow)
            - Walk score, transit score
            - Nearby amenities
            - Crime data if available
            - Recent development news"""
        ),
        WorkflowStep(
            action="analyze_inspection",
            target="inspection report",
            description="""From inspection report:
            - Major concerns (structural, electrical, plumbing)
            - Minor issues (cosmetic, maintenance)
            - Positive findings (new roof, updated systems)
            - Estimated repair costs"""
        ),
        WorkflowStep(
            action="suggest_price",
            target="pricing analysis",
            description="""Calculate suggested price:
            - Average of comp prices per sqft
            - Adjust for: condition, updates, lot size
            - Subtract major repair costs
            - Range: low (quick sale) to high (aspirational)"""
        ),
        WorkflowStep(
            action="generate_listing",
            target="MLS description",
            description="""Create MLS listing:
            - Compelling headline
            - Highlight best features
            - Mention neighborhood benefits
            - Address condition honestly but positively
            - Include relevant keywords for search"""
        ),
        WorkflowStep(
            action="save_results",
            target="listing.json",
            description="Output: headline, description, price_suggestion, comps, inspection_summary"
        )
    ],
    output_format="json"
)

# ============================================================================
# G) LEGAL - CONTRACT ANALYSIS (Document-based + Web verification)
# ============================================================================

WORKFLOW_CONTRACT_ANALYSIS = AgenticWorkflow(
    name="contract_analysis",
    description="Extract and verify contract details, identify risks",
    requires_login=[],  # Mostly document-based
    steps=[
        WorkflowStep(
            action="get_contract",
            target="user input",
            description="Get contract text (paste or file)"
        ),
        WorkflowStep(
            action="extract_parties",
            target="contract text",
            description="""Extract all parties:
            - Full legal names
            - Addresses
            - Roles (Client, Vendor, Licensor, etc.)"""
        ),
        WorkflowStep(
            action="verify_companies",
            target="Google, LinkedIn, state registries",
            description="""Verify each company:
            - Search Google for company
            - Check if they exist, legitimate
            - Look for any red flags (lawsuits, complaints)
            - Note: This is optional verification"""
        ),
        WorkflowStep(
            action="extract_dates",
            target="contract text",
            description="""Find all dates:
            - Effective date
            - Expiration/term end
            - Payment due dates
            - Notice periods
            - Renewal dates"""
        ),
        WorkflowStep(
            action="extract_money",
            target="contract text",
            description="""Find all financial terms:
            - Contract value
            - Payment amounts
            - Payment schedule
            - Penalties/late fees
            - Cap on liability"""
        ),
        WorkflowStep(
            action="extract_obligations",
            target="contract text",
            description="""List each party's obligations:
            - What must Party A do?
            - What must Party B do?
            - Deadlines for each"""
        ),
        WorkflowStep(
            action="identify_risks",
            target="contract text",
            description="""Flag potential risks:
            - Unlimited liability
            - Auto-renewal clauses
            - Non-compete restrictions
            - IP ownership issues
            - Termination penalties
            - Unusual terms"""
        ),
        WorkflowStep(
            action="save_results",
            target="contract_analysis.json",
            description="Output: parties, dates, amounts, obligations, risks"
        )
    ],
    output_format="json"
)

# ============================================================================
# H) LOGISTICS - SHIPMENT TRACKING
# ============================================================================

WORKFLOW_LOGISTICS = AgenticWorkflow(
    name="logistics_tracking",
    description="Track shipments across carriers, detect delays, suggest actions",
    requires_login=["fedex.com", "ups.com", "usps.com", "dhl.com"],
    steps=[
        WorkflowStep(
            action="get_tracking_numbers",
            target="user input",
            description="Get list of tracking numbers with carrier names"
        ),
        WorkflowStep(
            action="track_each",
            target="carrier websites",
            description="""For each tracking number:
            - Navigate to carrier tracking page (FedEx, UPS, USPS, DHL)
            - Enter tracking number
            - Extract: current status, location, expected delivery, history"""
        ),
        WorkflowStep(
            action="detect_delays",
            target="tracking data",
            description="""Identify delayed shipments:
            - Status contains: exception, delay, hold, weather
            - Expected date passed without delivery
            - Stuck at same location > 24 hours"""
        ),
        WorkflowStep(
            action="analyze_patterns",
            target="all shipments",
            description="""Look for patterns:
            - Common delay locations
            - Carrier-specific issues
            - Route problems"""
        ),
        WorkflowStep(
            action="generate_actions",
            target="delayed shipments",
            description="""For each delay, suggest action:
            - Contact carrier (include phone number)
            - File claim if lost
            - Notify customer
            - Arrange replacement shipment"""
        ),
        WorkflowStep(
            action="save_results",
            target="shipping_report.csv",
            description="Output: tracking_id, carrier, status, eta, is_delayed, action_needed"
        )
    ],
    output_format="csv"
)

# ============================================================================
# I) INDUSTRIAL - MAINTENANCE LOG ANALYSIS
# ============================================================================

WORKFLOW_MAINTENANCE = AgenticWorkflow(
    name="maintenance_analysis",
    description="Analyze maintenance logs, research solutions, predict issues",
    requires_login=[],
    steps=[
        WorkflowStep(
            action="get_logs",
            target="user input",
            description="Get maintenance log data (paste, file, or CMMS export)"
        ),
        WorkflowStep(
            action="parse_entries",
            target="log data",
            description="""Parse each entry:
            - Date/time
            - Equipment ID/name
            - Issue description
            - Action taken
            - Technician
            - Parts used"""
        ),
        WorkflowStep(
            action="identify_recurring",
            target="all entries",
            description="""Find recurring issues:
            - Same equipment, similar issue
            - Group by equipment and issue type
            - Calculate frequency"""
        ),
        WorkflowStep(
            action="research_solutions",
            target="Google, manufacturer sites",
            description="""For recurring issues, research:
            - Search "[equipment] [issue] solution"
            - Look for manufacturer bulletins
            - Find common root causes
            - Check if recalls/known issues exist"""
        ),
        WorkflowStep(
            action="analyze_root_causes",
            target="recurring issues",
            description="""Determine root causes:
            - Overheating: cooling, ventilation, overload
            - Vibration: alignment, balance, bearings
            - Leaks: seals, gaskets, corrosion
            - Electrical: connections, aging, environment"""
        ),
        WorkflowStep(
            action="generate_recommendations",
            target="each issue pattern",
            description="""Create actionable recommendations:
            - Immediate fixes needed
            - Preventive maintenance changes
            - Parts to stock
            - Training needs
            - Equipment to replace"""
        ),
        WorkflowStep(
            action="save_results",
            target="maintenance_report.json",
            description="Output: issues, root_causes, recommendations, priority_actions"
        )
    ],
    output_format="json"
)

# ============================================================================
# J) FINANCE - TRANSACTION CATEGORIZATION
# ============================================================================

WORKFLOW_FINANCE = AgenticWorkflow(
    name="transaction_processing",
    description="Categorize transactions, verify vendors, detect anomalies",
    requires_login=["bank websites", "accounting software"],
    steps=[
        WorkflowStep(
            action="get_transactions",
            target="user input or bank site",
            description="Get transaction data (CSV export or navigate to bank)"
        ),
        WorkflowStep(
            action="parse_transactions",
            target="transaction data",
            description="""Parse each transaction:
            - Date
            - Description
            - Amount (debit/credit)
            - Current category (if any)"""
        ),
        WorkflowStep(
            action="categorize_each",
            target="each transaction",
            description="""Categorize intelligently:
            - Payroll: salary, wages, bonus
            - Rent: lease, property management
            - Utilities: electric, gas, water, internet
            - Software: SaaS, subscriptions
            - Travel: airlines, hotels, rideshare
            - Marketing: ads, promotions
            - Professional: legal, accounting
            - Supplies: office supplies, equipment"""
        ),
        WorkflowStep(
            action="verify_vendors",
            target="unknown vendors",
            description="""For unrecognized vendors:
            - Search Google for vendor name
            - Determine what they sell/do
            - Categorize appropriately
            - Flag if suspicious"""
        ),
        WorkflowStep(
            action="detect_anomalies",
            target="all transactions",
            description="""Flag anomalies:
            - Unusually large amounts (> 2x average)
            - Round numbers over $5000
            - Duplicate transactions
            - Weekend transactions (for B2B)
            - New vendors with large amounts"""
        ),
        WorkflowStep(
            action="generate_summary",
            target="all data",
            description="""Create summary:
            - Total income vs expenses
            - Breakdown by category
            - Month-over-month comparison
            - Anomalies requiring review"""
        ),
        WorkflowStep(
            action="save_results",
            target="financial_report.csv",
            description="Output: categorized transactions, summary, anomaly flags"
        )
    ],
    output_format="csv"
)

# ============================================================================
# K) MARKETING - ANALYTICS ANALYSIS
# ============================================================================

WORKFLOW_MARKETING = AgenticWorkflow(
    name="marketing_analytics",
    description="Analyze marketing data, research benchmarks, suggest experiments",
    requires_login=["analytics.google.com", "ads.google.com", "business.facebook.com"],
    steps=[
        WorkflowStep(
            action="ask_platform",
            target="user input",
            description="Ask which analytics platform: Google Analytics, Facebook Ads, etc."
        ),
        WorkflowStep(
            action="navigate",
            target="analytics platform",
            description="Navigate to analytics dashboard"
        ),
        WorkflowStep(
            action="check_login",
            target="dashboard",
            description="Verify logged in. If login wall, ask user to login"
        ),
        WorkflowStep(
            action="extract_metrics",
            target="dashboard",
            description="""Extract key metrics:
            - Traffic/Sessions
            - Users (new vs returning)
            - Bounce rate
            - Conversion rate
            - Revenue
            - Top pages/campaigns
            - Traffic sources"""
        ),
        WorkflowStep(
            action="get_comparison",
            target="previous period",
            description="Get same metrics for previous period (last month, last year)"
        ),
        WorkflowStep(
            action="research_benchmarks",
            target="Google search",
            description="""Search for industry benchmarks:
            - "[industry] average conversion rate"
            - "[industry] bounce rate benchmark"
            - Compare your metrics to industry"""
        ),
        WorkflowStep(
            action="analyze_trends",
            target="all metrics",
            description="""Identify trends and insights:
            - What's improving? Why?
            - What's declining? Why?
            - Which channels perform best?
            - Where are drop-offs?"""
        ),
        WorkflowStep(
            action="suggest_experiments",
            target="improvement areas",
            description="""Suggest A/B tests:
            - For low conversion: test CTAs, forms, pricing
            - For high bounce: test headlines, page speed, content
            - For low traffic: test SEO, ads, social"""
        ),
        WorkflowStep(
            action="save_results",
            target="marketing_report.json",
            description="Output: metrics, trends, benchmarks, recommendations, experiments"
        )
    ],
    output_format="json"
)

# ============================================================================
# L) HR - RESUME/CANDIDATE RESEARCH
# ============================================================================

WORKFLOW_HR_RECRUITING = AgenticWorkflow(
    name="candidate_research",
    description="Research candidates, verify credentials, score fit",
    requires_login=["linkedin.com"],
    steps=[
        WorkflowStep(
            action="get_requirements",
            target="user input",
            description="""Get job requirements:
            - Required skills
            - Years of experience
            - Education level
            - Nice-to-have skills
            - Location requirements"""
        ),
        WorkflowStep(
            action="get_resumes",
            target="user input",
            description="Get candidate resumes (paste text or provide LinkedIn URLs)"
        ),
        WorkflowStep(
            action="parse_resume",
            target="each resume",
            description="""Extract from each resume:
            - Name, email, phone
            - Current title and company
            - Work history with dates
            - Skills listed
            - Education
            - Certifications"""
        ),
        WorkflowStep(
            action="research_linkedin",
            target="each candidate",
            description="""Research on LinkedIn:
            - Find their profile
            - Verify employment history
            - Check connections/recommendations
            - Look for activity/posts"""
        ),
        WorkflowStep(
            action="verify_companies",
            target="employment history",
            description="""Verify past employers:
            - Do companies exist?
            - Reasonable job progression?
            - Flag any inconsistencies"""
        ),
        WorkflowStep(
            action="score_fit",
            target="each candidate",
            description="""Score against requirements:
            - Required skills match (0-40 pts)
            - Experience years (0-30 pts)
            - Education match (0-20 pts)
            - Nice-to-have skills (0-10 pts)
            - Calculate total fit score"""
        ),
        WorkflowStep(
            action="generate_questions",
            target="each candidate",
            description="""Generate interview questions:
            - Technical questions based on claimed skills
            - Behavioral questions for experience gaps
            - Questions about career transitions"""
        ),
        WorkflowStep(
            action="save_results",
            target="candidates.csv",
            description="Output: name, fit_score, skills_match, experience, concerns, questions"
        )
    ],
    output_format="csv"
)

# ============================================================================
# M) EDUCATION - QUIZ/STUDY MATERIAL CREATION
# ============================================================================

WORKFLOW_EDUCATION = AgenticWorkflow(
    name="educational_content",
    description="Create quizzes and study materials with web research",
    requires_login=[],
    steps=[
        WorkflowStep(
            action="get_content",
            target="user input",
            description="Get educational content (chapter text, topic name, or textbook section)"
        ),
        WorkflowStep(
            action="identify_concepts",
            target="content",
            description="""Identify key concepts:
            - Main topics
            - Key terms to define
            - Important facts
            - Relationships between concepts"""
        ),
        WorkflowStep(
            action="research_topic",
            target="Google, Wikipedia, Khan Academy",
            description="""Research topic online:
            - Find additional explanations
            - Get examples
            - Find common misconceptions
            - Get related topics"""
        ),
        WorkflowStep(
            action="generate_questions",
            target="key concepts",
            description="""Create varied questions:
            - Multiple choice (4 options each)
            - True/False
            - Fill in the blank
            - Short answer
            - Mix difficulty: easy, medium, hard"""
        ),
        WorkflowStep(
            action="create_answer_key",
            target="questions",
            description="""For each question:
            - Correct answer
            - Explanation of why it's correct
            - Why other options are wrong (for MC)
            - Reference to source material"""
        ),
        WorkflowStep(
            action="create_study_guide",
            target="all content",
            description="""Create study guide:
            - Summary of each concept
            - Key terms with definitions
            - Important formulas/facts
            - Study tips
            - Additional resources"""
        ),
        WorkflowStep(
            action="save_results",
            target="quiz_materials.json",
            description="Output: quiz, answer_key, study_guide"
        )
    ],
    output_format="json"
)

# ============================================================================
# N) GOVERNMENT - FORM PROCESSING
# ============================================================================

WORKFLOW_GOVERNMENT = AgenticWorkflow(
    name="government_form_processing",
    description="Extract form data and validate against requirements",
    requires_login=["irs.gov (for some forms)"],
    steps=[
        WorkflowStep(
            action="get_form",
            target="user input",
            description="Get form content (paste text or specify form type)"
        ),
        WorkflowStep(
            action="identify_form_type",
            target="form content",
            description="""Identify form type:
            - W-2, W-4, 1099
            - I-9, I-130
            - Business licenses
            - Permit applications"""
        ),
        WorkflowStep(
            action="lookup_requirements",
            target="IRS.gov, official sites",
            description="""Research form requirements:
            - Search for form instructions
            - Find required fields
            - Understand validation rules
            - Get filing deadlines"""
        ),
        WorkflowStep(
            action="extract_fields",
            target="form content",
            description="""Extract all fields:
            - Field name
            - Value entered
            - Field type (text, date, SSN, etc.)
            - Required vs optional"""
        ),
        WorkflowStep(
            action="validate_fields",
            target="extracted data",
            description="""Validate each field:
            - Required fields present?
            - Correct format (SSN: XXX-XX-XXXX)?
            - Dates valid?
            - Numbers make sense?
            - Cross-field validation"""
        ),
        WorkflowStep(
            action="flag_issues",
            target="validation results",
            description="""Flag problems:
            - Missing required fields
            - Invalid formats
            - Inconsistent data
            - Potential errors"""
        ),
        WorkflowStep(
            action="save_results",
            target="form_data.json",
            description="Output: structured JSON with all fields, validation results, issues"
        )
    ],
    output_format="json"
)

# ============================================================================
# O) IT/ENGINEERING - LOG ANALYSIS
# ============================================================================

WORKFLOW_IT_LOGS = AgenticWorkflow(
    name="log_analysis",
    description="Analyze logs, research errors, create tickets",
    requires_login=["jira.atlassian.com", "github.com"],
    steps=[
        WorkflowStep(
            action="get_logs",
            target="user input",
            description="Get log file content (paste or file path)"
        ),
        WorkflowStep(
            action="parse_logs",
            target="log content",
            description="""Parse log entries:
            - Timestamp
            - Log level (ERROR, WARN, INFO)
            - Source/module
            - Message
            - Stack trace if present"""
        ),
        WorkflowStep(
            action="aggregate_errors",
            target="ERROR entries",
            description="""Group similar errors:
            - Normalize messages (remove IDs, timestamps)
            - Count occurrences
            - Find first and last occurrence
            - Identify affected components"""
        ),
        WorkflowStep(
            action="research_errors",
            target="top errors",
            description="""For top 5 errors, research:
            - Search Stack Overflow
            - Search GitHub issues
            - Look for known bugs
            - Find documented solutions"""
        ),
        WorkflowStep(
            action="identify_patterns",
            target="all logs",
            description="""Find patterns:
            - Error bursts (many errors in short time)
            - Cascading failures
            - Periodic issues
            - Resource exhaustion signs"""
        ),
        WorkflowStep(
            action="generate_tickets",
            target="each major issue",
            description="""Create Jira ticket for each:
            - Title: Clear description
            - Type: Bug, Incident, Task
            - Priority: based on frequency/impact
            - Description: error, count, affected, probable cause
            - Suggested fix from research"""
        ),
        WorkflowStep(
            action="save_results",
            target="log_analysis.json",
            description="Output: error_summary, patterns, jira_tickets"
        )
    ],
    output_format="json"
)

# ============================================================================
# WORKFLOW REGISTRY
# ============================================================================

WORKFLOWS = {
    "A_email": WORKFLOW_EMAIL_INBOX,
    "B_spreadsheet": WORKFLOW_SPREADSHEET,
    "C_tickets": WORKFLOW_SUPPORT_TICKETS,
    "D_sdr": WORKFLOW_SDR_PROSPECTING,
    "E_ecommerce": WORKFLOW_ECOMMERCE_PRODUCT,
    "F_real_estate": WORKFLOW_REAL_ESTATE,
    "G_contracts": WORKFLOW_CONTRACT_ANALYSIS,
    "H_logistics": WORKFLOW_LOGISTICS,
    "I_maintenance": WORKFLOW_MAINTENANCE,
    "J_finance": WORKFLOW_FINANCE,
    "K_marketing": WORKFLOW_MARKETING,
    "L_hr": WORKFLOW_HR_RECRUITING,
    "M_education": WORKFLOW_EDUCATION,
    "N_government": WORKFLOW_GOVERNMENT,
    "O_it_logs": WORKFLOW_IT_LOGS,
}

def get_workflow(workflow_id: str) -> Optional[AgenticWorkflow]:
    """Get workflow by ID"""
    return WORKFLOWS.get(workflow_id)

def get_workflow_prompt(workflow_id: str) -> str:
    """Generate a prompt that guides the agent through the workflow"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        return f"Unknown workflow: {workflow_id}"

    prompt = f"""
WORKFLOW: {workflow.name}
DESCRIPTION: {workflow.description}

SITES THAT MAY REQUIRE LOGIN: {', '.join(workflow.requires_login) if workflow.requires_login else 'None'}

EXECUTE THESE STEPS IN ORDER:

"""
    for i, step in enumerate(workflow.steps, 1):
        prompt += f"""
STEP {i}: {step.action.upper()}
Target: {step.target}
Instructions: {step.description}
"""
        if step.fallback:
            prompt += f"If this fails: {step.fallback}\n"

    prompt += f"""

OUTPUT FORMAT: {workflow.output_format}

IMPORTANT:
- Use Playwright tools to browse websites
- If you hit a login wall, STOP and ask user to login first
- Extract REAL data from the browser, never make up data
- Save results to file when done
"""
    return prompt

def list_workflows() -> Dict[str, str]:
    """List all available workflows"""
    return {
        wf_id: wf.description
        for wf_id, wf in WORKFLOWS.items()
    }
