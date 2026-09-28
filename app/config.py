import os

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

# SEC requires a descriptive User-Agent with contact info: "AppName your@email.com"
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# "openai" or "anthropic". Defaults to whichever key is present (OpenAI first).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower() or (
    "openai" if OPENAI_API_KEY else "anthropic"
)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")
ANTHROPIC_EFFORT = os.getenv("ANTHROPIC_EFFORT", "high")  # low | medium | high | xhigh | max

# Optional: protects the UI/API with HTTP Basic auth (username "admin").
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()

MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "1"))

DEFAULTS = {
    # Finviz filter codes, comma-separated. Build one at finviz.com/screener.ashx and
    # copy the `f=` value from the URL.
    "filters": "cap_midover,fa_eps5years_o20,fa_sales5years_o10,ta_perf_52w10o,fa_debteq_u1",
    "order": "-marketcap",  # Finviz `o=` value; leading "-" = descending
    "tickers": "",  # optional comma-separated list; skips the screen when set
    "userCriteria": "",
    "maxStocksToEvaluate": 3,
    "horizonYears": 3,
    "minConviction": 7,
    "maxDocChars": 30000,
}
