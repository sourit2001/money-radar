"""Deterministic market-opportunity clustering for saved Reddit posts.

This is intentionally explainable: every opportunity is made from source
posts, visible evidence counts, and a small set of domain patterns.  It is a
first step beyond ranking individual posts; it does not pretend that one loud
thread proves a market.
"""

from __future__ import annotations

import re
from collections import Counter

from .filters import assess_opportunity


CLUSTER_PATTERNS = (
    ("video postproduction", (("video",), ("subtitle", "subtitles", "caption", "captions", "dubbing", "transcription", "transcribe"))),
    ("regional personal-finance data access", (("bank", "banks", "banking", "credit card", "credit cards"), ("personal finance", "budget", "budgeting", "expense", "expenses", "net worth"))),
    ("ai brand visibility tracking", (("brand", "brand tracking", "brand visibility"), ("chatgpt", "ai visibility", "prompt", "prompts", "llm"))),
    ("client reporting", (("client report", "client reports", "client reporting", "customer report", "agency report"), ("metrics", "dashboard", "dashboards", "slides", "spreadsheet", "spreadsheets", "export"))),
    ("invoice reconciliation", (("invoice reconciliation", "reconcile invoices", "stripe reconciliation", "quickbooks reconciliation"), ("accounting", "bookkeeping", "spreadsheet", "manual", "software"))),
    ("irregular-income budgeting", (("irregular income", "variable income", "freelance income", "income budgeting"), ("budget", "budgeting", "paycheck", "cash flow"))),
    ("supplier spreadsheet cleanup", (("supplier spreadsheet", "vendor spreadsheet", "inventory spreadsheet", "inventory management"), ("excel", "csv", "import", "cleanup", "mobile"))),
    ("lead and CRM workflow", (("crm", "sales pipeline", "lead management", "deal follow-up", "deal follow up"), ("lead", "prospect", "deal", "follow-up", "follow up"))),
)

OPPORTUNITY_ANALYSIS = {
    "video postproduction": {
        "use_case": "创作者把口播或多语言视频交付为可发布的成片、字幕和配音版本。",
        "pain": "AI 能快速产出初稿，但字幕时间轴、断行、说话人和剪点仍需大量手工校对；用户需要可编辑而不是黑盒的一键生成。",
        "alternatives": "CapCut 等 AI 视频编辑器、通用字幕工具、手动调整 SRT，以及本地 Whisper/TTS 工作流。",
        "build": "先做字幕与时间轴的质检/编辑层：导入视频和 SRT，标记风险剪点与断行，支持双语字幕和导出；不重做视频编辑器或训练模型。",
        "research_reason": "同一交付流程在 4 条独立原帖中反复出现，且用户不是要更多生成能力，而是要修正 AI 初稿的编辑能力。",
        "scale_status": "已验证大类需求：视频 AI 工具已有持续使用；但这个细分切口的独立用户规模仍需用应用评论验证。",
        "growth_status": "增长待量化：生成式视频是活跃赛道，但目前没有这一个细分的连续月度增速。",
        "verification_label": "已验证方向，细分待验证",
    },
    "regional personal-finance data access": {
        "use_case": "用户希望自动汇总本地银行和信用卡流水，再导出 CSV 或进入自己的预算表。",
        "pain": "通用个人财务应用在本地银行连接、数据导出或长期可用性上无法满足需求；用户被迫手工下载和整理流水。",
        "alternatives": "银行 App 手工下载、Excel、现有预算 App，以及付费后才开放导出的聚合工具。",
        "build": "不要做通用记账 App；先选一个国家和 2–3 家银行，做稳定的流水导入、清洗和 CSV/API 导出。",
        "research_reason": "英国和新西兰用户分别提出相同的“本地银行连接 + 自动导出/预算”任务，其中一位明确表示愿意为合适方案付费。",
        "scale_status": "用户规模未验证：两条独立需求证明问题存在，但不足以推断国家级用户量。",
        "growth_status": "增长未验证：需要补充当地 Open Banking 覆盖、同类 App 下载量和评论趋势。",
        "verification_label": "高价值待验证",
    },
    "ai brand visibility tracking": {
        "use_case": "小团队定期查询多个 AI 产品，记录品牌是否被提及，并观察结果变化。",
        "pain": "固定提示词需要每天人工重复，结果难以比较；现有工具要么像传统 SEO 看板，要么价格对小团队过高。",
        "alternatives": "手工在 ChatGPT 等工具重复提问、电子表格、传统排名跟踪器，以及月费较高的 AI 可见性平台。",
        "build": "做极简监测器：保存固定提示词、定时执行、保留回答快照并提示提及变化；先不做完整 SEO 平台。",
        "research_reason": "用户给出了完整的高频手工流程、明确替代方案和价格上限（不接受每月 200 美元）。",
        "scale_status": "用户规模未验证：目前是一条高质量需求，不能据此声称已有大量用户。",
        "growth_status": "有大类增长信号：生成式 AI 使用持续扩大，但该细分是否增长需要继续查看同类产品的流量和评论。",
        "verification_label": "高价值待验证",
    },
    "client reporting": {
        "use_case": "代理商或小型企业定期整理客户指标，并把数据交付成报告或演示文稿。",
        "pain": "数据需要在多个工具之间复制，报告制作重复、耗时，而且不同工具之间经常无法同步。",
        "alternatives": "电子表格、手工复制粘贴、客户管理工具和现有报表工具的组合。",
        "build": "做一个面向小型代理商的客户报告工具：连接常用数据源，自动生成固定模板，并支持客户确认和导出。",
    },
    "invoice reconciliation": {
        "use_case": "小企业或财务人员定期核对发票、付款和账务记录。",
        "pain": "发票、付款和账目之间需要反复人工核对，容易遗漏，也很难快速发现异常。",
        "alternatives": "会计软件、电子表格、手工下载账单后逐条核对。",
        "build": "先做一个窄版发票核对工具：导入账单和发票，自动标记金额、日期和供应商不一致的记录。",
    },
    "irregular-income budgeting": {
        "use_case": "自由职业者或收入不固定的人安排预算、储蓄和每月支出。",
        "pain": "大多数预算应用假设每月收入固定，无法很好地处理收入波动和不确定的到账时间。",
        "alternatives": "通用预算应用、电子表格、记账软件和手工估算。",
        "build": "做一个只解决不固定收入预算的工具：按收入区间规划支出，并显示低收入月份的安全预算。",
    },
    "supplier spreadsheet cleanup": {
        "use_case": "采购、库存或运营人员定期处理不同供应商发来的表格和库存数据。",
        "pain": "每个供应商的字段、格式和命名都不同，导入前需要反复清理、转换和检查。",
        "alternatives": "Excel、电子表格模板、手工复制粘贴、脚本和通用库存软件。",
        "build": "做一个供应商表格清洗工具：保存每个供应商的映射规则，自动清理字段并输出统一格式。",
    },
    "lead and CRM workflow": {
        "use_case": "销售人员或小企业持续跟进线索、客户和未完成的交易。",
        "pain": "线索分散在不同工具中，跟进依赖手工记录，容易忘记下一步，也难以知道哪些交易正在流失。",
        "alternatives": "CRM、电子表格、邮件提醒、手工复制粘贴和多个销售工具的组合。",
        "build": "做一个极简的线索跟进工具：自动汇总待跟进客户，记录下一步动作，并提醒即将沉默的交易。",
    },
    "content production workflow": {
        "use_case": "设计师、创作者或小团队持续制作、更新和发布内容。",
        "pain": "内容本身不难，但整理、更新、发布、版本管理和多端适配让维护成本很高。",
        "alternatives": "Notion、Figma、网站构建器、表格和手工维护的发布流程。",
        "build": "做一个内容优先的发布工具：用简单文档维护内容，同时自动生成作品集、案例页或多平台版本。",
    },
}

STOPWORDS = {
    "about", "after", "also", "any", "app", "better", "can", "does", "for", "from",
    "have", "help", "how", "i", "is", "it", "looking", "need", "of", "on", "or",
    "please", "recommend", "software", "some", "that", "the", "this", "to", "tool",
    "use", "using", "what", "with", "would", "you", "your",
}


def _text(post: dict) -> str:
    body = (post.get("selftext") or "")[:600]
    return " ".join((post.get("title") or "", body)).lower()


def _term_present(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text) is not None


def _cluster_key(post: dict) -> str:
    text = _text(post)
    for key, groups in CLUSTER_PATTERNS:
        if all(any(_term_present(text, term) for term in group) for group in groups):
            return key
    # Unknown concepts remain individual signals until a stronger repeated
    # pattern is known. This is safer than grouping unrelated posts around
    # generic words such as "tool", "best", or "software".
    return f"signal:{post.get('reddit_id') or post.get('permalink') or id(post)}"


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _sentences(post: dict) -> list[str]:
    """Keep source-faithful, readable evidence excerpts from a post."""
    text = " ".join(str(post.get("selftext") or "").split())
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if len(sentence.strip()) >= 24
    ]


def _first_evidence_sentence(post: dict, patterns: tuple[str, ...]) -> str | None:
    for sentence in _sentences(post):
        lowered = sentence.lower()
        if any(re.search(pattern, lowered) for pattern in patterns):
            return sentence
    return None


def _source_evidence(posts: list[dict]) -> dict[str, list[dict]]:
    """Extract quotes, never inferred claims, for the daily report."""
    pattern_sets = {
        "pain": (r"\bmanual(?:ly)?\b", r"takes? (?:a )?long", r"drown", r"difficult", r"messy", r"annoying", r"frustrat"),
        "alternative": (r"\bi (?:am|['’]m) (?:currently )?using\b", r"\bi (?:have )?tried\b", r"\btools? (?:like|such as)\b", r"\busing\b"),
        "failure": (r"\bbut\b", r"\bnone (?:of|work)\b", r"\bdoesn['’]t work\b", r"\bno longer\b", r"\blocked\b", r"\bmanual(?:ly)?\b", r"\btoo expensive\b"),
        "payment_willingness": (r"\bhappy to pay\b", r"\bwilling to pay\b", r"\bi(?: would|['’]d) pay\b", r"\bi want to pay\b", r"\bi(?: would|['’]d) subscribe\b"),
        "price_ceiling": (r"\bno (?:huge )?.{0,35}\$\d+", r"\bnot .{0,35}\$\d+", r"\btoo expensive\b", r"\bcan['’]t afford\b", r"\bdon['’]t want to pay\b"),
    }
    evidence = {kind: [] for kind in pattern_sets}
    seen: set[tuple[str, str]] = set()
    for post in posts:
        for kind, patterns in pattern_sets.items():
            quote = _first_evidence_sentence(post, patterns)
            if not quote:
                continue
            fingerprint = (kind, quote.lower())
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            evidence[kind].append({
                "quote": quote,
                "permalink": post.get("permalink") or post.get("url") or "",
                "title": post.get("title") or "Reddit 原帖",
            })
    return {kind: values[:3] for kind, values in evidence.items()}


def _workaround(post: dict) -> str | None:
    text = _text(post)
    if _has_any(text, ("spreadsheet", "excel", "google sheet")):
        return "spreadsheet or manual spreadsheet work"
    if _has_any(text, ("copy and paste", "copying", "data entry", "manually")):
        return "manual copy/paste or data entry"
    if _has_any(text, ("tried several", "tried multiple", "nothing works", "doesn't work", "none of them")):
        return "several existing tools, with no satisfactory result"
    return None


def _analysis_for(key: str, posts: list[dict]) -> dict:
    analysis = OPPORTUNITY_ANALYSIS.get(key)
    if analysis:
        return {
            "research_reason": "已出现可复核的用户需求，仍需要补充竞争产品与评论证据。",
            "scale_status": "用户规模未验证。",
            "growth_status": "增长未验证。",
            "verification_label": "高价值待验证",
            **analysis,
        }
    return {
        "use_case": "多个用户在相似场景下寻找工具或替代方案。",
        "pain": "当前证据还不足以确认具体的、可重复的问题。",
        "alternatives": "原帖中提到的现有工具或手工做法。",
        "build": "暂不建议开发，先继续收集相同场景下的独立原文。",
        "research_reason": "当前只有初步线索，无法确认是否为可重复需求。",
        "scale_status": "用户规模未验证。",
        "growth_status": "增长未验证。",
        "verification_label": "继续观察",
    }


def _title(key: str, posts: list[dict]) -> str:
    if key in {name for name, _ in CLUSTER_PATTERNS}:
        return f"{key.title()} Tools"
    return "Early market signal"


def build_opportunities(posts: list[dict], limit: int = 50) -> list[dict]:
    posts = [
        post for post in posts
        if assess_opportunity(post).eligible
    ]
    groups: dict[str, list[dict]] = {}
    for post in posts:
        groups.setdefault(_cluster_key(post), []).append(post)

    opportunities: list[dict] = []
    for key, cluster in groups.items():
        texts = [_text(post) for post in cluster]
        subreddits = sorted({post.get("subreddit") for post in cluster if post.get("subreddit")})
        channels = sorted({post.get("channel") for post in cluster if post.get("channel")})
        workaround_counts = Counter(
            workaround for post in cluster if (workaround := _workaround(post))
        )
        source_evidence = _source_evidence(cluster)
        paid_count = len(source_evidence["payment_willingness"])
        price_ceiling_count = len(source_evidence["price_ceiling"])
        failed_count = sum(
            1 for text in texts if _has_any(text, ("tried", "nothing works", "doesn't work", "still doing", "manual"))
        )
        pain_count = sum(
            1 for post in cluster if post.get("signal") in {"pain", "opportunity"}
        )
        frequency = min(5, len(cluster))
        breadth = min(3, len(subreddits))
        evidence_score = frequency + breadth + min(2, paid_count) + min(2, failed_count)
        market_score = min(10, evidence_score + (1 if pain_count else 0))
        evidence_level = "strong" if len(cluster) >= 3 else "emerging" if len(cluster) >= 2 else "signal"
        gap = (
            f"Users commonly fall back to {workaround_counts.most_common(1)[0][0]}."
            if workaround_counts
            else "The posts contain a demand signal, but the current workaround is not yet clear."
        )
        sorted_posts = sorted(
            cluster,
            key=lambda post: (
                int(post.get("value_score") or 0),
                int(post.get("num_comments") or 0),
                int(post.get("score") or 0),
            ),
            reverse=True,
        )
        representative = sorted_posts[:5]
        opportunity_title = _title(key, cluster)
        if key.startswith("signal:"):
            opportunity_title = f"Early signal: {cluster[0].get('title') or 'unclassified demand'}"
        opportunities.append({
            "key": key,
            "title": opportunity_title,
            "post_count": len(cluster),
            "subreddits": subreddits,
            "channels": channels,
            "market_score": market_score,
            "evidence_level": evidence_level,
            "paid_signal_count": paid_count,
            "price_ceiling_count": price_ceiling_count,
            "failed_solution_count": failed_count,
            "pain_signal_count": pain_count,
            "direct_signal_count": sum(
                1 for post in cluster if assess_opportunity(post).tier == "direct"
            ),
            "current_workaround": gap,
            "why_now": f"Found in {len(cluster)} saved post{'s' if len(cluster) != 1 else ''} across {len(subreddits)} communit{'ies' if len(subreddits) != 1 else 'y'}.",
            "next_action": "Read the representative threads and test whether the same job appears in at least 3 independent conversations.",
            "analysis": _analysis_for(key, cluster),
            "source_evidence": source_evidence,
            "posts": sorted_posts,
            "representative_posts": representative,
        })

    return sorted(
        opportunities,
        key=lambda item: (item["market_score"], item["post_count"], item["paid_signal_count"]),
        reverse=True,
    )[:limit]
