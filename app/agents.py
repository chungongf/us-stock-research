"""The four research agents and the verdict rules (ported from the n8n workflow)."""
import asyncio
import json
import re

from .llm import complete


def fundamental_prompt(ctx: dict) -> str:
    return f"""You are a buy-side equity analyst covering US-listed companies. Analyse the fundamentals of {ctx['name']} ({ctx['symbol']}) for a {ctx['horizon']}-year holding period.

YAHOO FINANCE DATA:
{ctx['fundamentals']}

Cover: business quality and moat; growth durability (revenue & earnings trend, consistency); margins; ROE/ROA and returns on capital; debt and balance-sheet strength; cash-flow conversion (operating cash flow and FCF vs net income); working capital (receivables and inventory vs revenue); stock-based compensation and share count trend (dilution vs buybacks); insider ownership and insider buying/selling; institutional ownership and short interest; valuation vs growth (P/E, forward P/E, PEG, EV/EBITDA, FCF yield).
Call out red flags explicitly (e.g. earnings growing but cash flow weak, receivables outpacing revenue, heavy SBC, rising share count, large goodwill, heavy insider selling, high short interest).
Use only numbers present in the data; never invent figures.
End with:
Fundamental score: X/10
Summary: 3 bullets"""


def news_prompt(ctx: dict) -> str:
    return f"""You are a market-news analyst. Below are recent news headlines for {ctx['name']} ({ctx['symbol']}).

HEADLINES (date | title):
{ctx['newsText']}

Identify: business catalysts (contracts, product launches, capacity, M&A, guidance changes, buybacks); government policy / regulatory tailwinds or headwinds (tariffs, FDA, FTC/DOJ antitrust, subsidies, rates); governance or management issues (SEC or DOJ investigations, restatements, auditor changes, short-seller reports, class actions, executive departures, heavy insider selling); sector-level trends.
You only have headlines, not full articles. Say so where it limits confidence, and do not speculate beyond what they indicate.
End with:
News sentiment: Positive / Neutral / Negative
Governance red flags: Yes/No (with detail)
Policy stance: Tailwind / Neutral / Headwind"""


def filings_prompt(ctx: dict) -> str:
    return f"""You are a forensic analyst reviewing management disclosures for {ctx['name']} ({ctx['symbol']}).

ANNUAL REPORT EXCERPT ({ctx['annualReportLabel'] or 'latest 10-K'}): Risk Factors and Management's Discussion & Analysis
{ctx['annualReportText']}

LATEST EARNINGS RELEASE ({ctx['earningsLabel'] or '8-K'}):
{ctx['earningsText']}

Assess: management's strategy and outlook/guidance for the next {ctx['horizon']} years; capex, buybacks, M&A and capital-allocation plans; track record vs past guidance (if visible); tone and credibility (specific vs vague, over-promising, heavy reliance on non-GAAP adjustments); risks management acknowledges; related-party transactions, contingent liabilities, litigation, material weaknesses, going-concern language or restatements; customer concentration.
If a document is NOT AVAILABLE, say so and base the view on what exists.
End with:
Management quality: X/10
Key takeaways: 3 bullets"""


def committee_prompt(ctx: dict, fund: str, news: str, filings: str) -> str:
    h = ctx["horizon"]
    return f"""You are the investment committee chair. Decide whether {ctx['name']} ({ctx['symbol']}) is a good investment for a {h}-year horizon.

INVESTOR'S CRITERIA (must all hold):
{ctx['criteriaText']}

REPORT 1 - FUNDAMENTALS
{fund}

REPORT 2 - NEWS & SENTIMENT
{news}

REPORT 3 - 10-K & MANAGEMENT COMMENTARY
{filings}

Decision rules:
- "INVEST" only if there is a credible path to strong returns over {h} years AND no serious governance/accounting red flags AND no investor criterion is contradicted by the evidence.
- If any investor criterion is clearly violated, verdict is "PASS". Use met=null when evidence is insufficient to judge.
- Be sceptical: momentum screens often surface expensive stocks, so weigh valuation seriously.
- Missing data lowers conviction; never assume positives.

Respond with ONLY a JSON object, no markdown fences, no extra text:
{{"verdict":"INVEST or PASS","conviction":<integer 1-10>,"summary":"<2-3 sentences: why it is or isn't a good {h}-year investment>","thesis":["..."],"catalysts":["..."],"risks":["..."],"valuation_view":"...","criteria_check":[{{"criterion":"...","met":true,"evidence":"..."}}]}}
If no investor criteria were specified, return "criteria_check": []."""


def parse_verdict(raw: str, min_conviction: int) -> dict:
    try:
        m = re.search(r"\{[\s\S]*\}", re.sub(r"```json|```", "", raw))
        v = json.loads(m.group(0))
    except Exception:
        v = {"verdict": "PASS", "conviction": 0, "summary": "Could not parse committee output.", "raw": raw}
    v["verdict"] = str(v.get("verdict") or "PASS").upper().strip()
    try:
        v["conviction"] = int(float(v.get("conviction") or 0))
    except (TypeError, ValueError):
        v["conviction"] = 0
    failed = [c for c in (v.get("criteria_check") or []) if c.get("met") is False]
    if v["verdict"] == "INVEST" and failed:
        v["verdict"] = "PASS"
        v["downgradeReason"] = "Violates criteria: " + "; ".join(str(c.get("criterion")) for c in failed)
    elif v["verdict"] == "INVEST" and v["conviction"] < min_conviction:
        v["verdict"] = "PASS"
        v["downgradeReason"] = f"Conviction {v['conviction']} below threshold {min_conviction}"
    return v


async def run_agents(ctx: dict, min_conviction: int, log) -> dict:
    log(f"{ctx['symbol']}: running fundamental, news and filings analysts in parallel")
    fund, news, filings = await asyncio.gather(
        complete(fundamental_prompt(ctx)),
        complete(news_prompt(ctx)),
        complete(filings_prompt(ctx)),
    )
    log(f"{ctx['symbol']}: investment committee deciding")
    raw = await complete(committee_prompt(ctx, fund, news, filings))
    verdict = parse_verdict(raw, min_conviction)
    return {"verdict": verdict, "reports": {"fundamentals": fund, "news": news, "filings": filings}}
