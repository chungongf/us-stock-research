# US Stock Research

A US-market port of the n8n "Stock Screener → Multi-Agent Research" workflow, as a small FastAPI web app for Railway.

**Flow:** Finviz screen → for each candidate: Yahoo Finance fundamentals, Google News headlines, latest 10-K (Risk Factors + MD&A) and latest earnings release (8-K Item 2.02 exhibits) from SEC EDGAR → three analyst agents run in parallel (fundamentals, news, filings) → investment-committee agent returns JSON → verdict rules (criteria violated or conviction below threshold ⇒ PASS) → stops at the first INVEST.

| n8n (India) | This app (US) |
|---|---|
| screener.in query + login cookie | Finviz filter codes (no login) |
| screener.in company page | Yahoo Finance via `yfinance` |
| BSE annual report PDF | 10-K / 20-F from SEC EDGAR |
| Concall transcript PDF | Earnings press release (8-K EX-99.x) from SEC EDGAR |
| Google News (IN) | Google News (US) |
| OpenAI node | OpenAI **or** Anthropic (`LLM_PROVIDER`) |

## Deploy on Railway

1. Push this folder to a GitHub repo.
2. In Railway: **New Project → Deploy from GitHub repo** and pick it. The `Dockerfile` and `railway.json` are detected automatically.
3. Under **Variables**, set:
   - `LLM_PROVIDER` = `openai` or `anthropic`
   - `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`, default `gpt-4.1`), **or** `ANTHROPIC_API_KEY` (optionally `ANTHROPIC_MODEL`, default `claude-opus-5`; `ANTHROPIC_EFFORT`, default `high`)
   - `SEC_USER_AGENT` = `YourAppName your@email.com` (SEC requires contact info)
   - `APP_PASSWORD` = any password. Strongly recommended: without it anyone with the URL can spend your API credits.
4. **Settings → Networking → Generate Domain**, then open the URL. The browser asks for a login; any username works with `APP_PASSWORD`.

Or with the CLI: `railway login`, `railway init`, `railway up`, then set the variables with `railway variables --set KEY=value`.

## Run locally

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
cp .env.example .env   # fill in keys, then export them into your shell
.venv/Scripts/uvicorn app.main:app --reload
```

## Using it

- **Finviz filters**: build a screen at <https://finviz.com/screener>, then copy the `f=` value from the URL (e.g. `cap_midover,fa_eps5years_o20,fa_sales5years_o10,ta_perf_52w10o,fa_debteq_u1`).
  - The default approximates the original: mid-cap and up, 5y EPS growth >20%, 5y sales growth >10%, 1y performance >+10%, debt/equity <1. There's no US equivalent of promoter pledging, so insider activity and short interest go to the analysts instead.
- **Sort**: Finviz `o=` value, e.g. `-marketcap`, `-perf52w`, `pe`.
- **Tickers**: fill this in to skip the screen and research specific stocks.
- API: `POST /api/run` with the same fields as JSON → `{"id"}`; poll `GET /api/jobs/{id}`.

## Notes and limits

- Each stock costs 4 LLM calls with large prompts (about 20–30k tokens each).
- Job history lives in memory and resets on each redeploy or restart.
- Finviz and Yahoo are unofficial scraped sources. If Railway's IPs get rate-limited or Finviz changes its markup, the screen fails with a clear error; entering tickers directly still works.
- Foreign ADRs (20-F filers) report earnings on 6-K, so their earnings-release section is marked NOT AVAILABLE and the agents are told so.
- AI-generated research, not investment advice.
