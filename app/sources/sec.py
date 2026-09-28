"""10-K / 20-F and earnings-release text from SEC EDGAR (free, official)."""
import functools
import re
import warnings

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..config import SEC_USER_AGENT

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ANNUAL_FORMS = ("10-K", "20-F", "40-F")

# (start heading, end heading) per section. Headings are matched at the start of a line;
# 10-K items first, then the 20-F equivalents for foreign filers.
MDNA_PATTERNS = [
    (r"item\s*7\.?\s*[\-–—:]?\s*management[’']?s\s+discussion", r"item\s*7a\.?|item\s*8\.?\s*financial"),
    (r"item\s*5\.?\s*[\-–—:]?\s*operating\s+and\s+financial\s+review", r"item\s*6\.?\s*[\-–—:]?\s*directors"),
]
RISK_PATTERNS = [
    (r"item\s*1a\.?\s*[\-–—:]?\s*risk\s+factors", r"item\s*1b\.?|item\s*1c\.?|item\s*2\.?\s*[\-–—:]?\s*propert"),
    (r"(?:item\s*3\.?\s*)?d\.?\s*risk\s+factors", r"item\s*4\.?\s*[\-–—:]?\s*information\s+on"),
    (r"risk\s+factors[ \t]*$", r"item\s*4\.?\s*[\-–—:]?\s*information\s+on"),
]


def _client() -> httpx.Client:
    if not SEC_USER_AGENT:
        raise RuntimeError("SEC_USER_AGENT is not set (e.g. 'MyStockApp you@example.com').")
    return httpx.Client(
        headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=90, follow_redirects=True,
    )


@functools.lru_cache(maxsize=1)
def _ticker_map() -> dict[str, int]:
    with _client() as c:
        data = c.get("https://www.sec.gov/files/company_tickers.json").json()
    return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _section(text: str, patterns: list[tuple[str, str]], max_chars: int) -> str:
    """Longest run from a line-start heading to the next end heading; this skips the table of
    contents and in-text cross-references."""
    for start_pat, end_pat in patterns:
        best = ""
        for m in re.finditer(r"(?im)^[ \t]*" + start_pat, text):
            e = re.search(r"(?im)^[ \t]*(?:" + end_pat + ")", text[m.end():])
            chunk = text[m.start(): m.end() + (e.start() if e else max_chars)]
            if len(chunk) > len(best):
                best = chunk
        if len(best) > 2000:
            return best[:max_chars]
    return ""


def _archive(cik: int, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"


def _exhibit_urls(c: httpx.Client, cik: int, accession: str) -> list[tuple[str, str]]:
    """(type, url) for each EX-99.x document, read from the filing's index page."""
    html = c.get(f"{_archive(cik, accession)}/{accession}-index.htm").text
    out = []
    for row in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html):
        href = re.search(r'href="(/Archives/[^"]+\.html?)"', row)
        typ = re.search(r">\s*(EX-99[.\d]*)\s*<", row)
        if href and typ:
            out.append((typ.group(1), "https://www.sec.gov" + href.group(1)))
    return out


def get_filings(symbol: str, max_chars: int) -> dict:
    out = {"annualReportText": "NOT AVAILABLE", "annualReportLabel": "", "annualReportUrl": "",
           "earningsText": "NOT AVAILABLE", "earningsLabel": "", "earningsUrl": ""}
    cik = _ticker_map().get(symbol.upper().replace(".", "-"))
    if not cik:
        return out
    with _client() as c:
        recent = c.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
        rows = [dict(zip(recent.keys(), vals)) for vals in zip(*recent.values())]

        annual = next((r for r in rows if r["form"] in ANNUAL_FORMS), None)
        if annual:
            url = f"{_archive(cik, annual['accessionNumber'])}/{annual['primaryDocument']}"
            text = _html_to_text(c.get(url).text)
            risks = _section(text, RISK_PATTERNS, max_chars // 2)
            mdna = _section(text, MDNA_PATTERNS, max_chars)
            body = (f"[RISK FACTORS]\n{risks or 'not found'}\n\n[MD&A]\n{mdna or 'not found'}"
                    if (mdna or risks) else text[:max_chars])
            out.update(annualReportText=body, annualReportUrl=url,
                       annualReportLabel=f"{annual['form']} for period {annual.get('reportDate') or ''}, "
                                         f"filed {annual['filingDate']}")

        # Domestic filers publish results as 8-K Item 2.02 with the press release as EX-99.x.
        release = next((r for r in rows if r["form"] == "8-K" and "2.02" in (r.get("items") or "")), None)
        if release:
            exhibits = _exhibit_urls(c, cik, release["accessionNumber"])
            parts, budget = [], max_chars
            for typ, url in exhibits:
                if budget <= 0:
                    break
                t = _html_to_text(c.get(url).text)[:budget]
                parts.append(f"[{typ}]\n{t}")
                budget -= len(t)
            if parts:
                out.update(earningsText="\n\n".join(parts), earningsUrl=exhibits[0][1],
                           earningsLabel=f"8-K Item 2.02 earnings release, filed {release['filingDate']}")
    return out
