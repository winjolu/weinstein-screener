"""What the brokerage account actually holds, read straight from Webull.

The recommendation log was the only record of positions, and it was kept
by hand. It drifted, badly: it carried a TEAM cost basis of $103.32 (which
was actually ORKA's), a stop of $120 (actually $160), and no record that
ORKA had been stopped out at all. Three wrong answers in one session came
out of trusting it, including a confident description of TEAM as broken
and 45% below its highs while it was in fact doubling.

So the account is the source of truth and this module reads it. Nothing
here is a substitute for the recommendation log — that still records what
was *suggested* before the outcome was known, which is the only forward
evidence this project produces. This records what was *done*, which the
broker knows and I do not.

### Read-only, deliberately

Every call here is a GET. This module imports nothing that places,
replaces or cancels an order, and it should stay that way: the value of
an automated account reader is that it cannot do anything, so it can be
run on a schedule without anyone thinking about it first.

### On errors and credentials

The vendor SDK raises exceptions whose text contains the full signed
request, including `x-app-key` and `x-access-token`. Printing one of
those leaks live credentials into a terminal, a log file, or an
assistant transcript — which is exactly how it happened here. Every call
goes through `_call`, which sanitises the message before it can be
raised or logged.
"""
import datetime
import os
import re
import time

from . import db, rate_limit

# The account list gives several accounts and only one holds equities.
# Cached per process: it is stable and each lookup is a request.
_trade_client = None
_account_id = None

# One extra second between account-level calls. The documented limit is
# 300 requests per 60 seconds and `rate_limit` enforces the rate, but a
# burst of six account calls still came back 429 — the trading endpoints
# are stricter than the market-data ones the limit was measured on.
CALL_SPACING_SECONDS = 1.5

# Anything matching these is redacted out of an error before it travels.
_SECRET_PATTERNS = (
    re.compile(r'("?x-app-key"?\s*[:=]\s*"?)([^",\s}]+)', re.I),
    re.compile(r'("?x-access-token"?\s*[:=]\s*"?)([^",\s}]+)', re.I),
    re.compile(r'("?x-signature"?\s*[:=]\s*"?)([^",\s}]+)', re.I),
    re.compile(r'("?app_?secret"?\s*[:=]\s*"?)([^",\s}]+)', re.I),
)


def sanitise(text):
    """Strip credentials out of vendor error text.

    The SDK includes the whole signed request in its exception message.
    That message routinely ends up in a log or a terminal, and it carries
    a live access token when it does.
    """
    out = str(text)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(r"\1<redacted>", out)
    return out


class _SanitisingFilter(__import__("logging").Filter):
    """Redacts credentials out of every log record the SDK emits.

    Wrapping exceptions is not enough and this is why: the vendor SDK
    logs the entire signed request — headers included — through its own
    logger at ERROR level, *before* raising. That output goes straight to
    stderr and never passes through `_call`, so a 417 on a bad query
    parameter printed a live x-app-key and x-access-token to the terminal
    twice before anyone noticed. Filtering at the logger is the only
    place that catches it, because it is the only place the SDK's own
    output goes through.
    """

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return True
        cleaned = sanitise(message)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        return True


_LOG_FILTER = _SanitisingFilter()


def install_log_sanitiser():
    """Attach the redacting filter to every logger the SDK writes through.

    Idempotent, and called at import of this module and of data_fetch so
    that merely importing the client is enough to be safe. Attaches to the
    root logger as well, since the SDK creates loggers lazily by module
    name and a filter on a parent is not inherited by handlers already
    attached to a child.
    """
    import logging
    names = ["", "webull", "webull.core", "webull.core.client",
             "webull.core.http", "webull.core.http.initializer.token"]
    for name in names:
        logger = logging.getLogger(name)
        if _LOG_FILTER not in logger.filters:
            logger.addFilter(_LOG_FILTER)
        for handler in logger.handlers:
            if _LOG_FILTER not in handler.filters:
                handler.addFilter(_LOG_FILTER)


class BrokerError(RuntimeError):
    """A broker call failed, with the credentials taken out of the message."""


def _call(fn, *args, **kwargs):
    """Rate-limited, credential-safe wrapper around one API call."""
    rate_limit.acquire()
    try:
        response = fn(*args, **kwargs)
    except Exception as exc:                       # vendor SDK, broad by necessity
        raise BrokerError(
            f"{type(exc).__name__}: {sanitise(exc)[:400]}") from None
    try:
        return response.json()
    except Exception as exc:
        raise BrokerError(f"unparseable response: {sanitise(exc)[:200]}") from None


def _client():
    global _trade_client
    if _trade_client is None:
        from webull.core.client import ApiClient
        from webull.trade.trade_client import TradeClient
        key = os.environ.get("WEBULL_APP_KEY")
        secret = os.environ.get("WEBULL_APP_SECRET")
        if not key or not secret:
            raise BrokerError(
                "WEBULL_APP_KEY/WEBULL_APP_SECRET are not set — see .env.example")
        _trade_client = TradeClient(ApiClient(key, secret, "us"))
    return _trade_client


def account_id(refresh=False):
    """The equities account, discovered rather than configured.

    `WEBULL_ACCOUNT_ID` overrides when set, but it is empty in practice
    and an empty string is not a usable default — treating it as one is
    why the first attempt at this failed with no obvious cause. The
    account list is asked instead, and the cash or margin equities
    account is picked out of the futures and crypto ones.
    """
    global _account_id
    configured = (os.environ.get("WEBULL_ACCOUNT_ID") or "").strip()
    if configured:
        return configured
    if _account_id and not refresh:
        return _account_id
    accounts = _call(_client().account_v2.get_account_list)
    if not isinstance(accounts, list) or not accounts:
        raise BrokerError("the account list came back empty")
    preferred = ("INDIVIDUAL_CASH", "INDIVIDUAL_MARGIN")
    ranked = sorted(
        accounts,
        key=lambda a: preferred.index(a.get("account_class"))
        if a.get("account_class") in preferred else len(preferred))
    _account_id = ranked[0]["account_id"]
    return _account_id


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def positions(account=None):
    """Everything currently held, as a list of plain dicts.

    Field names vary across the vendor's response shapes, so each value is
    read from several candidate keys rather than one. A missing quantity
    is left as None instead of defaulting to zero: a position that reads
    as zero shares silently disappears from every total downstream, which
    is the same class of fault as the `filled_quantity or total_quantity`
    bug that logged every stop as covering no shares.
    """
    data = _call(_client().account_v2.get_account_position,
                 account or account_id())
    items = data if isinstance(data, list) else (
        data.get("items") or data.get("positions") or [])
    out = []
    for item in items:
        symbol = (item.get("symbol")
                  or (item.get("instrument") or {}).get("symbol"))
        if not symbol:
            continue
        out.append({
            "ticker": symbol.upper(),
            "quantity": _number(item.get("quantity") or item.get("position")),
            "cost_basis": _number(item.get("cost_price")
                                  or item.get("costPrice")
                                  or item.get("average_cost")),
            "last_price": _number(item.get("last_price")
                                  or item.get("lastPrice")),
        })
    return out


def open_orders(account=None):
    """Working orders, flattened out of the combo shape the vendor returns.

    A stop is only protection while it is actually resting at the broker,
    so this reads what is live rather than what was once submitted.
    """
    data = _call(_client().order_v3.get_order_open, account or account_id())
    combos = data if isinstance(data, list) else (
        data.get("items") or data.get("orders") or [])
    out = []
    for combo in combos:
        for leg in (combo.get("orders") or combo.get("items") or [combo]):
            symbol = leg.get("symbol")
            if not symbol:
                continue
            out.append({
                "ticker": symbol.upper(),
                "side": leg.get("side"),
                "order_type": leg.get("order_type"),
                "stop_price": _number(leg.get("stop_price")),
                "limit_price": _number(leg.get("limit_price")),
                "quantity": _number(leg.get("total_quantity")
                                    or leg.get("filled_quantity")),
                "time_in_force": leg.get("time_in_force"),
                "status": leg.get("status"),
            })
    return out


def order_history(account=None):
    """Completed orders, for folding into the recommendation log."""
    data = _call(_client().order_v3.get_order_history, account or account_id())
    return data if isinstance(data, list) else (
        data.get("items") or data.get("orders") or [])


def unprotected(held, orders):
    """Positions with no live sell stop resting against them.

    The question worth asking every time the account is read, and the one
    a hand-kept log answered wrongly for weeks: ORBX sat 23% down with no
    stop while the log showed protection that had never been placed.
    """
    protected = {o["ticker"] for o in orders
                 if o.get("side") == "SELL"
                 and str(o.get("order_type", "")).startswith("STOP")
                 and o.get("status") not in ("CANCELLED", "FILLED")}
    return [p for p in held if p["ticker"] not in protected]


def stop_limit_orders(orders):
    """Live stops that are limit orders rather than market orders.

    A stop-limit stops protecting the moment price moves faster than its
    window. TEAM carried stop $160 against limit $150 — a $10 window on a
    name whose weekly range was $34 — so a fast reversal would have left
    the position entirely unsold.
    """
    return [o for o in orders
            if str(o.get("order_type", "")) == "STOP_LOSS_LIMIT"
            and o.get("status") not in ("CANCELLED", "FILLED")]


def sync(account=None, record=True):
    """Read the account and store a timestamped snapshot.

    :return: dict with `positions`, `orders`, `unprotected`,
        `stop_limits` and `taken_at`. Snapshots accumulate rather than
        overwrite, so what was held on a given day stays answerable —
        the same reasoning as `run_provenance`, applied to the account.
    """
    account = account or account_id()
    held = positions(account)
    time.sleep(CALL_SPACING_SECONDS)
    orders = open_orders(account)
    taken_at = datetime.datetime.now().isoformat(timespec="seconds")
    snapshot = {
        "taken_at": taken_at,
        "positions": held,
        "orders": orders,
        "unprotected": unprotected(held, orders),
        "stop_limits": stop_limit_orders(orders),
    }
    if record:
        db.save_broker_snapshot(snapshot)
    return snapshot


install_log_sanitiser()
