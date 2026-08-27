"""Static configuration for the local Reddit radar."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "money_radar.sqlite3"
PUBLIC_DIR = PROJECT_ROOT / "public"

CHANNELS = {
    "entrepreneurship": {
        "label": "Entrepreneurship",
        "subreddits": [
            "Entrepreneur",
            "startups",
            "smallbusiness",
            "sideproject",
            "SaaS",
            "solopreneur",
        ],
    },
    "ai_saas_automation": {
        "label": "AI / SaaS / Automation",
        "subreddits": [
            "ChatGPT",
            "artificial",
            "LocalLLaMA",
            "Automation",
            "NoCode",
            "webdev",
        ],
    },
    "finance": {
        "label": "Finance / Investing / Saving",
        "subreddits": [
            "personalfinance",
            "investing",
            "povertyfinance",
            "financialindependence",
            "sidehustle",
        ],
    },
    "productivity": {
        "label": "Productivity / Tools / Workflow",
        "subreddits": [
            "productivity",
            "Notion",
            "excel",
            "freelance",
            "marketing",
            "dataanalysis",
        ],
    },
}

SUBREDDIT_TO_CHANNEL = {
    subreddit.lower(): channel
    for channel, details in CHANNELS.items()
    for subreddit in details["subreddits"]
}

DEMAND_PATTERNS = {
    "help": [
        "help",
        "how do i",
        "how can i",
        "need help",
        "struggling",
        "stuck",
        "can't figure out",
        "can someone help",
    ],
    "tool_search": [
        "tool for",
        "software for",
        "app for",
        "looking for a tool",
        "looking for an app",
        "looking for software",
        "looking for a platform",
        "looking for a solution",
        "recommend",
        "recommendation",
        "alternative to",
        "best way to",
        "does this exist",
        "i want to pay for",
        "i would like to pay for",
        "i'd pay for",
        "willing to pay for",
    ],
    "pain": [
        "hate",
        "annoying",
        "frustrating",
        "manual",
        "takes too long",
        "waste of time",
        "too expensive",
        "pain",
    ],
    "opportunity": [
        "wish there was",
        "is there a way",
        "workaround",
        "i built a spreadsheet",
        "spreadsheet for",
        "automate",
        "automation",
    ],
}

# Precision-first filtering vocabulary. A post must contain more than a
# generic request for help: it needs explicit product/workflow intent plus
# evidence of a concrete, recurring or professional problem.
STRONG_INTENT_PHRASES = [
    "tool for", "software for", "app for", "looking for a tool",
    "looking for an app", "looking for software", "looking for a platform",
    "looking for a solution", "alternative to", "does this exist",
    "i want to pay for", "i would like to pay for", "i'd pay for",
    "willing to pay for",
]

EXPLICIT_OPPORTUNITY_PHRASES = [
    "wish there was", "is there a way", "workaround", "how to automate",
    "can i automate", "could i automate", "i built a spreadsheet",
    "spreadsheet for",
]

FAILED_ATTEMPT_TERMS = [
    "i've tried", "i have tried", "tried several", "tried multiple",
    "none of them", "nothing works", "doesn't work", "didn't work",
    "can't get", "cannot get", "still doing this manually",
]

WORKFLOW_TERMS = [
    "automate", "automation", "manual process", "manually", "workflow",
    "spreadsheet", "spreadsheets", "copying", "copy and paste", "data entry", "reporting",
    "dashboard", "tracking", "sync", "integration", "export", "import",
]

# Money Radar focuses on digital products an individual developer can ship.
# Physical-goods requests can also contain the word "tool" and need excluding.
DIGITAL_SOLUTION_TERMS = [
    "software", "app", "platform", "saas", "api", "browser extension",
    "chrome extension", "desktop app", "web app", "integration", "plugin",
    "workflow", "automation", "automate", "dashboard", "crm", "editor", "sync",
    "spreadsheet", "tracking",
]

PROBLEM_CONTEXT_TERMS = [
    "business", "client", "customer", "invoice", "supplier", "team",
    "employee", "agency", "freelance", "budget", "income", "expense",
    "analytics", "metrics", "lead", "crm", "inventory", "subscription",
]

RECURRING_TERMS = [
    "every day", "every week", "every month", "daily", "weekly", "monthly",
    "repeatedly", "repetitive", "each time",
]

PROMOTIONAL_TITLE_PATTERNS = [
    "share your startup", "weekly thread", "quarterly post", "feedback friday",
    "hiring/seeking/offering", "product hunt", "i built", "i made", "we built",
    "launched", "introducing", "here's how", "part 2:", "my side project",
    "case study", "lessons learned", "for hire", "ultimate guide",
    "complete guide", "announcement", "before i launch", "would you pay for",
    "here's what", "my results", "upgrade to", "software engineer job",
    "built ", "quick answer",
    "looking for software engineer",
    "unemployed software engineer", "software engineer opportunities",
]

SUPPLY_POST_MARKERS = [
    "i built", "i made", "i shipped", "i created", "i launched",
    "we built", "we made", "we shipped", "we launched", "i've made",
    "my app", "my tool", "open source", "github.com", "product hunt",
    "i'm the developer", "i am the developer", "i ended up building",
    "actively developing", "feedback and bug reports", "releases and commits",
    "our platform", "our software", "our solution", "book a demo",
    "contact us", "learn more at",
    "we recently launched", "launched the beta", "test it here",
    "disclosure: i'm part", "introducing ", "built specifically for",
    "i build ai automation", "for context, i'm building",
    "i'm now building", "im now building",
    "i'll reply with", "let's see how many", "drop your setup",
    "what are you actually running", "the best crm for", "customer success manager",
    "rating across", "if you're searching for",
]

MIN_OPPORTUNITY_SCORE = 5

# Search queries for cross-subreddit demand discovery via Reddit search RSS.
SEARCH_QUERIES = [
    '("looking for software" OR "looking for an app" OR "looking for a tool")',
    '("I want to pay for" OR "I would like to pay for" OR "I\'d pay for" OR "willing to pay for")',
    '("does anyone know" OR "has anyone found") AND (software OR tool OR workflow)',
    '("I have tried" OR "tried several" OR "none of them") AND (software OR tool OR OCR)',
    '("manual process" OR "currently using a spreadsheet" OR "takes too long") AND (automate OR workflow OR software)',
]

# Engagement thresholds.  RSS posts may arrive without score/comment data,
# so these only apply when structured stats are available.
MIN_COMMENTS = 5
MIN_SCORE = 10

# Fetch timing — Reddit RSS has strict rate limits.
FETCH_DELAY = 65  # stay outside Reddit's observed one-request-per-minute limit
COOLDOWN_429 = 60  # seconds to wait after a 429 response

# Browser-like User-Agent for curl requests.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
