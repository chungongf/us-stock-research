"""Fundamentals from Yahoo Finance (yfinance), rendered as compact text for the LLM."""
import pandas as pd
import yfinance as yf

INFO_FIELDS = [
    ("longName", "Name"), ("sector", "Sector"), ("industry", "Industry"),
    ("country", "Country"), ("fullTimeEmployees", "Employees"),
    ("marketCap", "Market cap"), ("enterpriseValue", "Enterprise value"),
    ("currentPrice", "Price"), ("fiftyTwoWeekLow", "52w low"), ("fiftyTwoWeekHigh", "52w high"),
    ("trailingPE", "P/E (TTM)"), ("forwardPE", "P/E (fwd)"), ("trailingPegRatio", "PEG"),
    ("priceToBook", "P/B"), ("priceToSalesTrailing12Months", "P/S"),
    ("enterpriseToEbitda", "EV/EBITDA"), ("enterpriseToRevenue", "EV/Revenue"),
    ("grossMargins", "Gross margin"), ("operatingMargins", "Operating margin"),
    ("profitMargins", "Net margin"), ("returnOnEquity", "ROE"), ("returnOnAssets", "ROA"),
    ("revenueGrowth", "Revenue growth (yoy, qtr)"), ("earningsGrowth", "Earnings growth (yoy, qtr)"),
    ("totalCash", "Cash"), ("totalDebt", "Total debt"), ("debtToEquity", "Debt/Equity (%)"),
    ("currentRatio", "Current ratio"), ("freeCashflow", "Free cash flow (TTM)"),
    ("operatingCashflow", "Operating cash flow (TTM)"),
    ("dividendYield", "Dividend yield"), ("payoutRatio", "Payout ratio"),
    ("heldPercentInsiders", "Insider ownership"), ("heldPercentInstitutions", "Institutional ownership"),
    ("shortPercentOfFloat", "Short % of float"), ("beta", "Beta"),
    ("targetMeanPrice", "Analyst target (mean)"), ("recommendationKey", "Analyst consensus"),
    ("numberOfAnalystOpinions", "# analysts"),
]

INCOME_ROWS = ["Total Revenue", "Gross Profit", "Operating Income", "EBITDA", "Net Income",
               "Diluted EPS", "Diluted Average Shares"]
BALANCE_ROWS = ["Cash And Cash Equivalents", "Accounts Receivable", "Inventory", "Total Assets",
                "Goodwill", "Total Debt", "Stockholders Equity", "Retained Earnings"]
CASHFLOW_ROWS = ["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
                 "Stock Based Compensation", "Repurchase Of Capital Stock",
                 "Cash Dividends Paid", "Issuance Of Debt", "Repayment Of Debt"]
QUARTER_ROWS = ["Total Revenue", "Operating Income", "Net Income", "Diluted EPS"]


PCT_FIELDS = {"grossMargins", "operatingMargins", "profitMargins", "returnOnEquity", "returnOnAssets",
              "revenueGrowth", "earningsGrowth", "payoutRatio", "heldPercentInsiders",
              "heldPercentInstitutions", "shortPercentOfFloat"}


def _fmt_info(key, v):
    if key in PCT_FIELDS and isinstance(v, (int, float)):
        return f"{v * 100:.1f}%"
    if key == "dividendYield" and isinstance(v, (int, float)):
        return f"{v:.2f}%"  # yfinance already reports this one in percent
    return _fmt(v)


def _fmt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a"
    if isinstance(v, (int, float)) and abs(v) >= 1e6:
        return f"{v / 1e6:,.1f}M"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _table(df: pd.DataFrame, rows: list[str], label: str) -> str:
    if df is None or df.empty:
        return ""
    present = [r for r in rows if r in df.index]
    if not present:
        return ""
    sub = df.loc[present].copy()
    sub.columns = [c.strftime("%Y-%m") if hasattr(c, "strftime") else str(c) for c in sub.columns]
    sub = sub.map(_fmt)
    return f"### {label} (USD, M = millions; most recent first)\n{sub.to_string()}"


def _returns(t: yf.Ticker) -> str:
    try:
        h = t.history(period="5y", auto_adjust=True)["Close"].dropna()
    except Exception:
        return ""
    if h.empty:
        return ""
    last = h.iloc[-1]
    parts = []
    for label, days in [("1y", 365), ("3y", 365 * 3), ("5y", 365 * 5)]:
        past = h[h.index <= h.index[-1] - pd.Timedelta(days=days)]
        if not past.empty:
            parts.append(f"{label}: {(last / past.iloc[-1] - 1) * 100:+.1f}%")
    return "### PRICE RETURNS (total, adjusted)\n" + ", ".join(parts) if parts else ""


def _insiders(t: yf.Ticker) -> str:
    try:
        ip = t.insider_purchases
        if ip is not None and not ip.empty:
            return "### INSIDER ACTIVITY (last 6 months)\n" + ip.to_string(index=False)
    except Exception:
        pass
    return ""


def get_fundamentals(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass

    sections = []
    kv = [f"{label}: {_fmt_info(k, info.get(k))}" for k, label in INFO_FIELDS if info.get(k) is not None]
    if kv:
        sections.append("### OVERVIEW & KEY RATIOS\n" + "\n".join(kv))
    if info.get("longBusinessSummary"):
        sections.append("### BUSINESS DESCRIPTION\n" + info["longBusinessSummary"])

    for attr, rows, label in [
        ("income_stmt", INCOME_ROWS, "INCOME STATEMENT (annual)"),
        ("quarterly_income_stmt", QUARTER_ROWS, "QUARTERLY RESULTS"),
        ("balance_sheet", BALANCE_ROWS, "BALANCE SHEET (annual)"),
        ("cashflow", CASHFLOW_ROWS, "CASH FLOW (annual)"),
    ]:
        try:
            s = _table(getattr(t, attr), rows, label)
            if s:
                sections.append(s)
        except Exception:
            pass

    for s in (_returns(t), _insiders(t)):
        if s:
            sections.append(s)

    text = "\n\n".join(sections)
    if len(text) > 28000:
        text = text[:28000] + "\n…[truncated]"
    return {
        "name": info.get("longName") or info.get("shortName") or symbol,
        "shortName": info.get("shortName") or symbol,
        "fundamentals": text or "NOT AVAILABLE",
    }
