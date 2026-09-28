"""US stock screen via Finviz (free tier, HTML)."""
import html as htmllib
import re

import httpx

from ..config import BROWSER_UA

FINVIZ_URL = "https://finviz.com/screener"
PAGE_SIZE = 20


def run_screen(filters: str, order: str, limit: int) -> list[dict]:
    filters = re.sub(r"\s+", "", filters or "")
    out: list[dict] = []
    seen: set[str] = set()
    with httpx.Client(headers={"User-Agent": BROWSER_UA}, timeout=60, follow_redirects=True) as c:
        start = 1
        while len(out) < limit:
            r = c.get(FINVIZ_URL, params={"v": "111", "f": filters, "o": order, "r": start})
            r.raise_for_status()
            html = r.text
            table = html[html.find("screener_table"):] if "screener_table" in html else html
            # Each result row's ticker cell carries data-boxover-ticker / data-boxover-company attributes.
            found_on_page = 0
            for m in re.finditer(r'data-boxover-ticker="([^"]+)"\s*data-boxover-company="([^"]*)"', table):
                sym, name = m.group(1).strip(), htmllib.unescape(m.group(2)).strip()
                # Skip repeat rows and extra share classes of the same company (GOOGL/GOOG, PBR/PBR-A).
                if sym in seen or (name and name in seen):
                    continue
                seen.update({sym, name})
                found_on_page += 1
                out.append({"rank": len(out) + 1, "symbol": sym, "name": name or sym})
            if found_on_page < PAGE_SIZE:
                break
            start += PAGE_SIZE
    if not out:
        raise RuntimeError(
            "Finviz returned no stocks. Check the filter codes (copy the f= value from a "
            "finviz.com screener URL), or enter tickers directly."
        )
    for o in out:
        o["url"] = f"https://finviz.com/quote?t={o['symbol']}"
    return out[:limit]


def from_tickers(tickers: str, limit: int) -> list[dict]:
    syms = [t.strip().upper() for t in re.split(r"[,\s]+", tickers or "") if t.strip()]
    uniq = list(dict.fromkeys(syms))[:limit]
    return [
        {"rank": i + 1, "symbol": s, "name": s, "url": f"https://finviz.com/quote?t={s}"}
        for i, s in enumerate(uniq)
    ]
