# Webull OpenAPI — Reference Index

Source: https://developer.webull.com/apis/llms.txt
Fetched: 2026-07-20

## Getting Started
- Welcome: https://developer.webull.com/apis/docs.md
- Getting Started: https://developer.webull.com/apis/docs/getting-started.md
- SDKs and Tools: https://developer.webull.com/apis/docs/sdk.md

## Authentication
- Overview (App Key/Secret, digest signature): https://developer.webull.com/apis/docs/authentication/overview.md
- Signature (HMAC-SHA1): https://developer.webull.com/apis/docs/authentication/signature.md
- Token lifecycle: https://developer.webull.com/apis/docs/authentication/token.md
- Registered application name: "weinsteinScreener" — Webull's developer
  portal doesn't allow hyphens in application names, so this is the
  camelCase form of this project's name, used only at registration.

## Market Data API
- Overview: https://developer.webull.com/apis/docs/market-data-api/overview.md
- Historical Bars, multi-symbol: https://developer.webull.com/apis/docs/reference/historical-bars.md
- Historical Bars, single symbol: https://developer.webull.com/apis/docs/reference/bars.md
- Top Gainers/Losers: https://developer.webull.com/apis/docs/reference/get-gainers-losers.md
- Market Sectors: https://developer.webull.com/apis/docs/reference/get-market-sectors.md
- 52 Week High/Low: https://developer.webull.com/apis/docs/reference/get-week-52-high-low.md

## Trading API
- Overview: https://developer.webull.com/apis/docs/trade-api/overview.md
- Accounts: https://developer.webull.com/apis/docs/trade-api/account.md
- Stocks (order placement/mod/cancel): https://developer.webull.com/apis/docs/trade-api/stock.md

## Base URLs (Production)
| API | Service | Host |
|---|---|---|
| Trading API | HTTP API | api.webull.com |
| Market Data API | HTTP API | broker-api.webull.com |
| Market Data API | Streaming (MQTT) | data-api.webull.com |

## Notes / corrections (2026-07-20)
- Webull's built-in chart "RSI" is Wilder's RSI (momentum oscillator),
  NOT Weinstein/Mansfield relative strength. Do not confuse these.
- Webull's Script Editor is a Pine-Script-inspired proprietary
  language, NOT Pine Script. Not portable. No VS Code/Cursor plugin.
- Use the official Market Data API and Trading API only. Do not use
  unofficial/reverse-engineered packages.

## Confirmed request limits (2026-07-26)
All measured against the live API, not read off a page — several
contradict what I'd assumed.

- **Batch bars take at most 20 symbols per call.** Anything larger is
  rejected with "symbols size must be between 1 and 20". Fetching one
  symbol at a time therefore spends 5% of each call's capacity, which
  is what the screener did until I checked.
- **Rate limit is 300 requests per 60 seconds**, i.e. 5/sec — half what
  I had assumed. screener/rate_limit.py throttles against this.
- **Bars cap at count=1200 on every timespan**, daily and weekly alike.
  Requesting more fails with ILLEGAL_PARAMETER 417 — the request is
  refused outright, not truncated to the maximum. For daily bars that's
  about 4.75 years; for weekly it's about 23 years, and 1200 returns
  1,199 weekly SPY bars reaching back to 2003-08-08, which is the
  practical limit on how far any backtest can go.

  I had this recorded for daily bars and the code still didn't honour
  it, which cost more than not knowing would have. `run_backtest` sizes
  its daily sector request to span the whole test window, so any
  backtest starting more than ~3.3 years back threw on every sector
  fetch, hit a bare `except`, and ran to completion with condition 5
  unresolved at every checkpoint — output identical in shape to a good
  run. `data_fetch._capped()` now clamps every count and says so.
  Documenting a limit isn't the same as enforcing one.
- **The instrument endpoint returns 1,000 records per call** and
  paginates on last_instrument_id. The full listed universe is 64,358
  instruments across 65 pages — my first page cap of 40 silently
  truncated it and made the market look a third smaller than it is.
- **Instrument metadata distinguishes funds from common stock**: the
  ETF-specific fields (etf_leveraged_factor, crypto_etf,
  single_stock_etf) are populated for pooled products and absent for
  ordinary shares. Filtering on the field beats matching on the name,
  which misclassifies REITs and other legitimate trusts. Test all three
  fields, not just the leverage factor — that one is ETF-specific, so
  closed-end funds leave it empty and read as ordinary stock. `crypto_etf`
  is the one that separates them: present-but-false on a CEF, absent on
  a real company.
- **There is no security-type field.** Nothing distinguishes a preferred
  share, a SPAC unit or a warrant from common stock, and preferreds
  carry their parent company's full profile including its sector. The
  only signals are the symbol conventions (` PR<letter>`, five-letter
  Nasdaq suffixes) plus `margin_requirement_long` as corroboration —
  see `universe.classify_security_types`. Note that
  `margin_requirement_long` tracks illiquidity, not type: ordinary
  small-cap banks sit at 100% alongside every preferred.
- **A company's sector arrives as an "industries" list**, broadest entry
  first — not a "sector" or "industry" field. ETFs carry an empty list,
  which is legitimate rather than an error.
- **get_market_sectors returns a bare array**, not an object wrapping a
  "result" key.
- **Bars come back newest-first and are split-adjusted** — verified
  across a 10:1 split, which shows no artificial gap.

## Script Editor cross-symbol references (2026-07-20)
- CONFIRMED: Webull's Script Editor (metrix framework) does NOT
  support fetching a second symbol's price data within a
  CustomIndicator. Cross-symbol references are not available.
  I can't build Mansfield RS, or any relative-strength-vs-index
  indicator, natively in Webull. This path is closed, not just
  unverified. Confirmed directly by Vega AI (Webull's script
  assistant), not inferred.
