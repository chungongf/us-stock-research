"""Recent headlines from Google News RSS (US edition)."""
import html
import re
import xml.etree.ElementTree as ET

import httpx

from ..config import BROWSER_UA


def get_news(name: str, symbol: str, limit: int = 25) -> str:
    # Drop suffixes like "Inc." / "Corporation" so the query matches how headlines name the company.
    short = re.sub(r"[,.]?\s+(inc|corp|corporation|co|company|ltd|plc|holdings|group|n\.?v|s\.?a)\.?$", "",
                   name, flags=re.I).strip()
    q = f'"{short}" OR {symbol} stock'
    r = httpx.get(
        "https://news.google.com/rss/search",
        params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"},
        headers={"User-Agent": BROWSER_UA}, timeout=60, follow_redirects=True,
    )
    r.raise_for_status()
    items = ET.fromstring(r.content).findall("./channel/item")[:limit]
    lines = []
    for it in items:
        date = (it.findtext("pubDate") or "")[5:16]
        title = html.unescape(it.findtext("title") or "").strip()
        lines.append(f"- {date} | {title}")
    return "\n".join(lines) if lines else "NOT AVAILABLE"
