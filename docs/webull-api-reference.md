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

## Script Editor cross-symbol references (2026-07-20)
- CONFIRMED: Webull's Script Editor (metrix framework) does NOT
  support fetching a second symbol's price data within a
  CustomIndicator. Cross-symbol references are not available.
  I can't build Mansfield RS, or any relative-strength-vs-index
  indicator, natively in Webull. This path is closed, not just
  unverified. Confirmed directly by Vega AI (Webull's script
  assistant), not inferred.
