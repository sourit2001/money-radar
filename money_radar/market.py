"""Public market-validation sources used alongside Reddit demand signals."""

from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
import re
import subprocess
import xml.etree.ElementTree as ET


PRODUCT_HUNT_FEED_URL = "https://www.producthunt.com/feed"
TOOLIFY_MOST_USED_URL = "https://www.toolify.ai/most-used"
TOOLIFY_NEW_URL = "https://www.toolify.ai/new"
JINA_READER_PREFIX = "https://r.jina.ai/http://www.toolify.ai"
ATOM_NS = "http://www.w3.org/2005/Atom"

# These are category-level observations, not product ideas to clone.  They
# provide the market-validation layer for an individual developer assessment.
AI_TOOL_WATCHLIST = (
    {
        "category": "AI 视频后期的可编辑交付层",
        "market_evidence": "主流视频工具已经把自动字幕、粗剪和生成式效果做成核心能力。",
        "solo_score": 4,
        "decision": "值得做",
        "entry": "只做一种创作流程的质检和编辑，例如口播视频的切点、字幕断行和样式复用。",
        "avoid": "不要做通用 AI 视频编辑器或一键生成视频平台。",
    },
    {
        "category": "AI 搜索可见性与品牌监测",
        "market_evidence": "生成式 AI 的整体使用持续扩大，品牌是否出现在 AI 回答中正在成为新的运营问题。",
        "solo_score": 4,
        "decision": "值得研究",
        "entry": "只做固定提示词的定时运行、结果存档和提及变化提醒。",
        "avoid": "不要一开始做完整 SEO 套件、爬虫基础设施或跨平台数据仓库。",
    },
    {
        "category": "垂直行业的 AI 跟进助手",
        "market_evidence": "AI CRM 已被大量产品验证，但小团队仍认为配置成本高、建议不可靠。",
        "solo_score": 4,
        "decision": "值得做",
        "entry": "选择一个行业和一个沟通渠道，只解决漏跟进、确认下一步和记录结果。",
        "avoid": "不要从通用 CRM、完整客户数据库或多渠道自动化开始。",
    },
    {
        "category": "小语种或离线的字幕编辑工作流",
        "market_evidence": "通用语音和视频产品覆盖广，但小语种、双语时间轴和本地工作流仍较弱。",
        "solo_score": 3,
        "decision": "先验证",
        "entry": "先交付可编辑初稿、双语对齐和字幕导出，不自行训练基础语音模型。",
        "avoid": "没有真实语料和首批创作者前，不要承诺高准确率。",
    },
)

AI_MARKET_SOURCES = (
    {
        "name": "Toolify Most Used AI",
        "url": TOOLIFY_MOST_USED_URL,
        "role": "月度访问量榜单：只用于验证同类工具是否已有网站流量。",
    },
    {
        "name": "a16z Top 100 Gen AI Apps",
        "url": "https://a16z.com/100-gen-ai-apps-6/",
        "role": "季度市场快照：确认消费者 AI 类别已有真实使用规模。",
    },
    {
        "name": "Similarweb 2026 Generative AI Landscape",
        "url": "https://www.similarweb.com/blog/marketing/geo/gen-ai-stats/",
        "role": "月度使用趋势：确认该类别不是一次性热度。",
    },
)


def parse_toolify_most_used(html_text: str) -> list[dict]:
    """Extract ranked Toolify tool links without inventing traffic figures.

    Toolify's page is a ranking page, not an API.  We retain only the name and
    public link; the report never treats a ranking position as proof of demand.
    """
    if "Markdown Content:" in html_text or "## Most Used AIs" in html_text:
        return parse_toolify_markdown(html_text, list_type="most_used")

    tools: list[dict] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'<a[^>]+href=["\'](?P<url>/tool/[^"\'#?]+)[^"\']*["\'][^>]*>'
        r'(?P<label>.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        name = _strip_html(match.group("label"))
        slug = match.group("url").rstrip("/").rsplit("/", 1)[-1]
        # A card can contain nested links; prefer a visible, compact label and
        # keep just one record per tool page.
        if not name or len(name) > 100 or slug in seen:
            continue
        seen.add(slug)
        tools.append({
            "id": slug, "name": name, "description": "",
            "url": f"https://www.toolify.ai{match.group('url')}",
            "source": "toolify", "list_type": "most_used", "rank": len(tools) + 1,
        })
    return tools


def parse_toolify_markdown(markdown: str, *, list_type: str) -> list[dict]:
    """Parse Toolify cards from a Jina Reader Markdown representation."""
    tools: list[dict] = []
    seen: set[str] = set()
    card = re.compile(
        r"^\[!\[Image\s+\d+(?::\s*(?P<name>[^\]]+))?\]\([^)]+\)\s*"
        r"(?P<label>.*?)\]\(https?://www\.toolify\.ai/tool/(?P<slug>[^)]+)\)",
        flags=re.MULTILINE,
    )
    for match in card.finditer(markdown):
        slug = match.group("slug").split("?", 1)[0].rstrip("/")
        if slug in seen:
            continue
        seen.add(slug)
        raw_name = match.group("name") or ""
        if raw_name:
            name = " ".join(raw_name.split())
        else:
            slug_parts = slug.split("-")
            if slug_parts and slug_parts[-1] in {"com", "io", "ai"}:
                slug_parts.pop()
            name = " ".join(part.upper() if part == "ai" else part.title() for part in slug_parts)
        label = " ".join(match.group("label").split())
        description = label[len(name):].strip(" :-") if label.lower().startswith(name.lower()) else label
        tools.append({
            "id": slug,
            "name": name,
            "description": description,
            "url": f"https://www.toolify.ai/tool/{slug}",
            "source": "toolify",
            "list_type": list_type,
            "rank": len(tools) + 1,
        })
    return tools


def parse_toolify_new_markdown(markdown: str) -> list[dict]:
    """Extract the newest Toolify cards shown before the Featured section."""
    section = markdown.split("## Featured*", 1)[0]
    card = re.compile(
        r"\[!\[Image\s+\d+\]\([^)]+\)\s+!\[Image\s+\d+:\s*(?P<name>[^\]]+)\]"
        r"\([^)]+\)\]\(https?://www\.toolify\.ai/tool/(?P<slug>[^)]+)\)"
    )
    tools: list[dict] = []
    for match in card.finditer(section):
        slug = match.group("slug").split("?", 1)[0].rstrip("/")
        tools.append({
            "id": slug, "name": " ".join(match.group("name").split()),
            "description": "", "url": f"https://www.toolify.ai/tool/{slug}",
            "source": "toolify", "list_type": "new", "rank": len(tools) + 1,
        })
    return tools


def parse_toolify_detail(markdown: str) -> dict:
    intro = re.search(r"Introduction:\s*\n\s*(?P<text>.+?)(?:\n\s*Added on:)", markdown, re.DOTALL)
    if not intro:
        intro = re.search(
            r"^Title:\s*[^:\n]+:\s*(?P<text>.+?)(?:\n\s*URL Source:)",
            markdown, re.MULTILINE | re.DOTALL,
        )
    if not intro:
        intro = re.search(
            r"^## What is [^?]+\?\s*\n\s*(?P<text>.+?)(?:\n\s*##)",
            markdown, re.MULTILINE | re.DOTALL,
        )
    visitors = re.search(r"Monthly Visitors:\s*\n\s*(?P<value>[^\n]+)", markdown)
    reviews = re.search(r"(?P<count>\d+)\s+Reviews", markdown)
    added = re.search(r"Added on:\s*\n\s*(?P<value>[^\n]+)", markdown)
    return {
        "description": " ".join(intro.group("text").split()) if intro else "",
        "monthly_visitors": visitors.group("value").strip() if visitors else "",
        "review_count": int(reviews.group("count")) if reviews else 0,
        "added_on": added.group("value").strip() if added else "",
    }


def _fetch_text(url: str, *, timeout: int) -> str:
    try:
        result = subprocess.run(
            ["curl", "-sSL", "--compressed", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Timeout fetching {url}") from exc
    if result.returncode:
        raise RuntimeError(f"Unable to fetch {url}")
    return result.stdout


def fetch_toolify_list(url: str, *, list_type: str, timeout: int = 40) -> list[dict]:
    """Fetch Toolify directly, falling back to a read-only text representation."""
    try:
        direct = _fetch_text(url, timeout=min(timeout, 20))
    except RuntimeError:
        direct = ""
    tools = parse_toolify_most_used(direct) if list_type == "most_used" else []
    if tools:
        return tools
    if list_type == "most_used":
        markdown = _fetch_text(f"{JINA_READER_PREFIX}/most-used", timeout=timeout)
        return parse_toolify_markdown(markdown, list_type=list_type)
    # /new is occasionally challenged even through the reader. Toolify's
    # homepage contains the same newest cards before its Featured section.
    markdown = _fetch_text(f"{JINA_READER_PREFIX}/", timeout=timeout)
    tools = parse_toolify_new_markdown(markdown)[:10]

    def enrich(tool: dict) -> tuple[str, dict]:
        detail = _fetch_text(f"{JINA_READER_PREFIX}/tool/{tool['id']}", timeout=timeout)
        return tool["id"], parse_toolify_detail(detail)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(enrich, tool) for tool in tools[:6]]
        details = {}
        for future in as_completed(futures):
            try:
                tool_id, detail = future.result()
            except RuntimeError:
                continue
            details[tool_id] = detail
    for tool in tools:
        tool.update(details.get(tool["id"], {}))
    # The first cards are the ones rendered in the daily brief. Retry them
    # sequentially if a concurrent reader request was throttled.
    for tool in tools[:3]:
        if tool.get("description"):
            continue
        try:
            detail = _fetch_text(f"{JINA_READER_PREFIX}/tool/{tool['id']}", timeout=timeout)
        except RuntimeError:
            continue
        tool.update(parse_toolify_detail(detail))
    return tools


def fetch_toolify_most_used(*, timeout: int = 40) -> list[dict]:
    return fetch_toolify_list(TOOLIFY_MOST_USED_URL, list_type="most_used", timeout=timeout)


def fetch_toolify_new(*, timeout: int = 40) -> list[dict]:
    return fetch_toolify_list(TOOLIFY_NEW_URL, list_type="new", timeout=timeout)


def _strip_html(value: str) -> str:
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()
    return re.sub(r"\s*Discussion\s*\|\s*Link\s*$", "", text, flags=re.IGNORECASE)


def _has_term(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text) is not None


def parse_product_hunt_feed(xml_text: str) -> list[dict]:
    """Parse Product Hunt's public Atom feed without an API token."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    products: list[dict] = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        entry_id = (entry.findtext(f"{{{ATOM_NS}}}id") or "").rsplit("/", 1)[-1]
        title = (entry.findtext(f"{{{ATOM_NS}}}title") or "").strip()
        content = entry.findtext(f"{{{ATOM_NS}}}content") or ""
        published = entry.findtext(f"{{{ATOM_NS}}}published") or ""
        link = ""
        for link_element in entry.findall(f"{{{ATOM_NS}}}link"):
            if link_element.get("rel") in (None, "alternate"):
                link = link_element.get("href") or ""
                break
        if title and link:
            products.append({
                "id": entry_id,
                "title": title,
                "name": title,
                "description": _strip_html(content),
                "url": link,
                "published": published,
                "source": "product_hunt",
                "rank": len(products) + 1,
            })
    return products


def fetch_product_hunt_feed(*, timeout: int = 20) -> list[dict]:
    """Fetch the public Product Hunt feed; comments require a token separately."""
    result = subprocess.run(
        ["curl", "-sSL", "--max-time", str(timeout), PRODUCT_HUNT_FEED_URL],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
    )
    if result.returncode:
        raise RuntimeError("Unable to fetch the public Product Hunt feed.")
    return parse_product_hunt_feed(result.stdout)


def _translate(text: str, translator) -> str:
    if not text:
        return ""
    try:
        return translator(text)
    except (ImportError, RuntimeError, ValueError):
        return ""


def render_market_preview(
    products: list[dict], *, toolify_tools: list[dict] | None = None, translator=None
) -> str:
    """Render a source-faithful market-validation preview in Chinese."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Money Radar 外部市场验证预览",
        "",
        f"> {generated_at} · Product Hunt 公开 feed 只说明产品正在发布，不把它直接当成用户需求。",
        "",
        "## 一、近期 Product Hunt 产品（原文与中文翻译）",
        "",
    ]
    if not products:
        lines.extend(["本次没有读取到 Product Hunt 公开产品。", ""])
    for index, product in enumerate(products[:8], start=1):
        title = product["title"]
        description = product["description"]
        title_zh = _translate(title, translator) if translator else ""
        description_zh = _translate(description, translator) if translator else ""
        lines.extend([
            f"### {index}. [{title}]({product['url']})",
            "",
            *([f"**中文名称**：{title_zh}", ""] if title_zh and title_zh != title else []),
            "**英文介绍**",
            "",
            description or "（公开 feed 未提供介绍。）",
            "",
            "**中文翻译**",
            "",
            description_zh or "（中文翻译暂未生成。）",
            "",
            "**个人开发者判断**：只作为市场观察，不建议仅凭产品发布去模仿开发；需要继续读取评论或独立用户抱怨后才可进入机会池。",
            "",
        ])

    lines.extend(["## 二、Toolify 最常用 AI（只作流量验证）", ""])
    if toolify_tools is None:
        lines.extend(["本次未读取 Toolify 榜单；不把静态链接当作实时榜单证据。", ""])
    elif not toolify_tools:
        lines.extend(["Toolify 页面已读取，但没有解析出可引用的工具卡片。", ""])
    else:
        lines.extend([
            "以下仅说明这些工具出现在 Toolify 的 Most Used 页面；不代表它们解决了本日报中的具体痛点。",
            "",
            "、".join(f"[{tool['name']}]({tool['url']})" for tool in toolify_tools[:12]),
            "",
        ])
    lines.extend(["## 三、AI 工具榜单映射出的个人开发机会", ""])
    for item in AI_TOOL_WATCHLIST:
        lines.extend([
            f"### {item['category']} · 可行性 {item['solo_score']}/5 · {item['decision']}",
            "",
            f"- **市场验证**：{item['market_evidence']}",
            f"- **个人开发切口**：{item['entry']}",
            f"- **不要做**：{item['avoid']}",
            "",
        ])
    lines.extend([
        "## 四、进入正式机会日报的条件",
        "",
        "Product Hunt 评论、Reddit 原帖或软件评论中，需要至少出现一个明确的使用场景、现有替代方案和未被满足的缺口；单纯的发布、点赞或榜单排名都不够。",
        "",
    ])
    return "\n".join(lines)


def market_validation_for(
    posts: list[dict], products: list[dict], *, toolify_tools: list[dict] | None = None
) -> dict:
    """Return only market evidence that matches the candidate's actual job."""
    text = " ".join(
        f"{post.get('title', '')} {post.get('selftext', '')}" for post in posts
    ).lower()
    # A category must match a complete job, rather than a loose word.  For
    # example, a fullscreen question that happens to mention "video" is not
    # evidence for a video-postproduction opportunity.
    has = lambda *terms: any(_has_term(text, term) for term in terms)
    topic = None
    if has("video") and has("subtitle", "subtitles", "caption", "captions", "dubbing", "transcription", "transcribe"):
        topic = "AI 视频后期的可编辑交付层"
    elif has("crm") or (has("follow up", "follow-up") and has("lead", "client", "customer", "prospect")):
        topic = "垂直行业的 AI 跟进助手"
    elif has("tibetan", "bilingual") and has("subtitle", "subtitles", "speech recognition", "transcription"):
        topic = "小语种或离线的字幕编辑工作流"
    elif has("brand", "brand visibility") and has("chatgpt", "ai visibility", "prompt", "prompts", "llm"):
        topic = "AI 搜索可见性与品牌监测"
    watch = next((item for item in AI_TOOL_WATCHLIST if item["category"] == topic), None)
    topic_terms = {
        "AI 视频后期的可编辑交付层": ("video", "subtitle", "caption", "dubbing", "editing"),
        "垂直行业的 AI 跟进助手": ("crm", "follow", "sales"),
        "小语种或离线的字幕编辑工作流": ("tibetan", "bilingual", "subtitle", "speech"),
        "AI 搜索可见性与品牌监测": ("brand", "visibility", "prompt", "llm", "chatgpt"),
    }.get(topic, ())
    # Product names whose primary workflow is unambiguous enough to be used
    # as a category match.  This is deliberately a short allowlist: a famous
    # generic model or a loose keyword is not enough.
    topic_tool_names = {
        "AI 视频后期的可编辑交付层": ("capcut", "descript", "veed", "invideo"),
        "小语种或离线的字幕编辑工作流": ("capcut", "descript", "veed"),
        "AI 搜索可见性与品牌监测": (),
        "垂直行业的 AI 跟进助手": (),
    }.get(topic, ())
    matching_products = [
        product for product in products
        if topic_terms and any(_has_term(
            f"{product.get('title', '')} {product.get('description', '')}".lower(), term
        ) for term in topic_terms)
    ][:2]
    def tool_matches(tool: dict) -> bool:
        tool_text = f"{tool.get('name', '')} {tool.get('description', '')}".lower()
        if topic == "垂直行业的 AI 跟进助手":
            return _has_term(tool_text, "crm") or (
                _has_term(tool_text, "sales")
                and any(_has_term(tool_text, term) for term in ("customer", "lead", "follow"))
            )
        return bool(topic_terms) and (
            any(_has_term(tool_text, term) for term in topic_terms)
            or tool.get("name", "").lower() in topic_tool_names
        )

    matching_toolify = [tool for tool in (toolify_tools or []) if tool_matches(tool)][:3]
    return {
        "watch": watch,
        "sources": AI_MARKET_SOURCES if watch else (),
        "products": matching_products,
        "toolify_tools": matching_toolify,
        "toolify_checked": toolify_tools is not None,
    }
