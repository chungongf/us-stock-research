"""Screen -> gather data per candidate -> agents -> stop at the first INVEST."""
import asyncio

from .agents import run_agents
from .sources import fundamentals, news, screener, sec

DISCLAIMER = "AI-generated research, not investment advice. Verify before acting."


async def _safe(label: str, fn, *args, log, default):
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as e:
        log(f"  {label} unavailable: {e}")
        return default


async def build_context(cand: dict, cfg: dict, log) -> dict:
    sym = cand["symbol"]
    log(f"{sym}: fetching fundamentals, 10-K, earnings release")
    max_chars = int(cfg["maxDocChars"])
    fund, filings = await asyncio.gather(
        _safe("fundamentals", fundamentals.get_fundamentals, sym, log=log,
              default={"name": cand["name"], "shortName": cand["name"], "fundamentals": "NOT AVAILABLE"}),
        _safe("SEC filings", sec.get_filings, sym, max_chars, log=log, default={}),
    )
    headlines = await _safe("news", news.get_news, fund["shortName"], sym, log=log, default="NOT AVAILABLE")
    criteria = (cfg.get("userCriteria") or "").strip()
    return {
        "symbol": sym,
        "name": fund["name"],
        "url": cand["url"],
        "horizon": int(cfg["horizonYears"]),
        "criteriaText": criteria or "None specified. Use general investing judgement.",
        "fundamentals": fund["fundamentals"],
        "newsText": headlines,
        "annualReportText": filings.get("annualReportText", "NOT AVAILABLE"),
        "annualReportLabel": filings.get("annualReportLabel", ""),
        "annualReportUrl": filings.get("annualReportUrl", ""),
        "earningsText": filings.get("earningsText", "NOT AVAILABLE"),
        "earningsLabel": filings.get("earningsLabel", ""),
        "earningsUrl": filings.get("earningsUrl", ""),
    }


async def run(cfg: dict, log) -> dict:
    limit = max(1, min(int(cfg["maxStocksToEvaluate"]), 50))
    if (cfg.get("tickers") or "").strip():
        candidates = screener.from_tickers(cfg["tickers"], limit)
        log(f"Using {len(candidates)} ticker(s) you entered")
    else:
        log("Running Finviz screen")
        candidates = await asyncio.to_thread(screener.run_screen, cfg["filters"], cfg["order"], limit)
        log(f"Screen returned: {', '.join(c['symbol'] for c in candidates)}")

    evaluated = []
    for cand in candidates:
        ctx = await build_context(cand, cfg, log)
        result = await run_agents(ctx, int(cfg["minConviction"]), log)
        v = result["verdict"]
        entry = {
            "stock": ctx["name"], "symbol": ctx["symbol"], "verdict": v["verdict"],
            "conviction": v["conviction"], "reason": v.get("downgradeReason") or v.get("summary"),
            "details": v, "reports": result["reports"],
            "sources": {"finviz": ctx["url"], "annualReport": ctx["annualReportUrl"],
                        "earningsRelease": ctx["earningsUrl"]},
        }
        evaluated.append(entry)
        log(f"{ctx['symbol']}: {v['verdict']} (conviction {v['conviction']})")
        if v["verdict"] == "INVEST":
            return {
                "result": "INVEST", "stock": ctx["name"], "symbol": ctx["symbol"],
                "conviction": v["conviction"], "why": v.get("summary"), "thesis": v.get("thesis"),
                "catalysts": v.get("catalysts"), "risks": v.get("risks"),
                "valuation_view": v.get("valuation_view"), "criteria_check": v.get("criteria_check"),
                "evaluated": evaluated, "disclaimer": DISCLAIMER,
            }
    return {
        "result": "NO_QUALIFYING_STOCK",
        "message": f"None of the {len(evaluated)} evaluated stock(s) cleared the bar. Increase "
                   "maxStocksToEvaluate, relax criteria, or lower minConviction.",
        "evaluated": evaluated, "disclaimer": DISCLAIMER,
    }
