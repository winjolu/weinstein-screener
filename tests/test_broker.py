"""The account is the source of truth; the hand-kept log was not.

Trusting the recommendation log produced three wrong answers in one
session: a cost basis belonging to a different ticker, a stop $40 out of
date, and a position that had been stopped out with no exit recorded.
"""
import unittest

from screener import broker


class SanitiseTest(unittest.TestCase):
    """The SDK puts the whole signed request in its exception text.

    One of those messages reached a terminal with a live access token in
    it, which is the reason this function exists.

    Every value below is a deliberate fake. The first draft of this file
    used the real key and token that had just leaked, which would have
    committed live credentials to a public repository — a test for a
    redaction function is the last place they belong.
    """

    def test_an_access_token_is_removed(self):
        out = broker.sanitise('{"x-access-token": "0000deadbeef0000cafe11"}')
        self.assertNotIn("0000deadbeef0000cafe11", out)
        self.assertIn("redacted", out)

    def test_an_app_key_is_removed(self):
        out = broker.sanitise('"x-app-key": "ffffffffffffffffffffffffffffffff"')
        self.assertNotIn("ffffffffffffffffffffffffffffffff", out)

    def test_a_signature_is_removed(self):
        out = broker.sanitise('"x-signature": "AAAAfakesignatureAAAA="')
        self.assertNotIn("AAAAfakesignatureAAAA", out)

    def test_case_and_quoting_variants_are_caught(self):
        for text in ('X-App-Key=abc123secret',
                     'x-app-key: abc123secret',
                     '"X-ACCESS-TOKEN": "abc123secret"'):
            self.assertNotIn("abc123secret", broker.sanitise(text))

    def test_ordinary_text_survives(self):
        self.assertEqual(broker.sanitise("HTTP 429 Too many requests"),
                         "HTTP 429 Too many requests")

    def test_the_useful_part_of_an_error_is_kept(self):
        out = broker.sanitise('TOO_MANY_REQUESTS "x-app-key": "secret" 429')
        self.assertIn("TOO_MANY_REQUESTS", out)
        self.assertIn("429", out)
        self.assertNotIn("secret", out)


class LogFilterTest(unittest.TestCase):
    """Sanitising exceptions was not enough.

    The SDK logs the entire signed request through its own logger at
    ERROR level before raising, so a 417 on a bad query parameter printed
    a live app key and access token to the terminal twice. The filter has
    to sit on the logger, which is the only place that output passes
    through.
    """

    def test_a_record_with_credentials_is_redacted(self):
        import logging
        broker.install_log_sanitiser()
        record = logging.LogRecord(
            "webull.core.client", logging.ERROR, __file__, 1,
            'Request: {"x-app-key": "%s", "x-access-token": "%s"}',
            ("ffffffffffffffffffffffffffffffff", "0000deadbeef0000cafe11"), None)
        for f in logging.getLogger("webull.core.client").filters:
            f.filter(record)
        out = record.getMessage()
        self.assertNotIn("ffffffffffffffffffffffffffffffff", out)
        self.assertNotIn("0000deadbeef0000cafe11", out)
        self.assertIn("redacted", out)

    def test_an_ordinary_record_is_untouched(self):
        import logging
        broker.install_log_sanitiser()
        record = logging.LogRecord("webull.core.client", logging.INFO,
                                   __file__, 1, "fetching %s bars", (200,), None)
        for f in logging.getLogger("webull.core.client").filters:
            f.filter(record)
        self.assertEqual(record.getMessage(), "fetching 200 bars")

    def test_installing_twice_does_not_stack_filters(self):
        import logging
        before = len(logging.getLogger("webull.core.client").filters)
        broker.install_log_sanitiser()
        broker.install_log_sanitiser()
        self.assertEqual(len(logging.getLogger("webull.core.client").filters), before)


class NumberTest(unittest.TestCase):
    def test_strings_are_read_as_numbers(self):
        self.assertEqual(broker._number("103.32"), 103.32)

    def test_junk_is_none_rather_than_zero(self):
        """Zero would silently drop a position out of every total."""
        self.assertIsNone(broker._number("n/a"))
        self.assertIsNone(broker._number(None))


class UnprotectedTest(unittest.TestCase):
    def setUp(self):
        self.held = [{"ticker": "TEAM"}, {"ticker": "ORBX"}, {"ticker": "SPY"}]

    def test_a_position_with_a_live_stop_is_protected(self):
        orders = [{"ticker": "TEAM", "side": "SELL",
                   "order_type": "STOP_LOSS", "status": "SUBMITTED"}]
        out = [p["ticker"] for p in broker.unprotected(self.held, orders)]
        self.assertNotIn("TEAM", out)
        self.assertIn("ORBX", out)

    def test_a_stop_limit_still_counts_as_protection(self):
        """It is weak protection, which `stop_limit_orders` reports
        separately — but it is not an absence of one."""
        orders = [{"ticker": "TEAM", "side": "SELL",
                   "order_type": "STOP_LOSS_LIMIT", "status": "SUBMITTED"}]
        self.assertNotIn("TEAM",
                         [p["ticker"] for p in broker.unprotected(self.held, orders)])

    def test_a_cancelled_stop_protects_nothing(self):
        orders = [{"ticker": "TEAM", "side": "SELL",
                   "order_type": "STOP_LOSS", "status": "CANCELLED"}]
        self.assertIn("TEAM",
                      [p["ticker"] for p in broker.unprotected(self.held, orders)])

    def test_a_filled_stop_protects_nothing(self):
        orders = [{"ticker": "TEAM", "side": "SELL",
                   "order_type": "STOP_LOSS", "status": "FILLED"}]
        self.assertIn("TEAM",
                      [p["ticker"] for p in broker.unprotected(self.held, orders)])

    def test_a_buy_order_is_not_protection(self):
        """A resting buy limit is not a stop, and counting it as one
        would report a naked position as covered."""
        orders = [{"ticker": "TEAM", "side": "BUY",
                   "order_type": "LIMIT", "status": "SUBMITTED"}]
        self.assertIn("TEAM",
                      [p["ticker"] for p in broker.unprotected(self.held, orders)])

    def test_a_buy_stop_is_not_protection_either(self):
        """A buy-stop is an entry order, not an exit. It carries the
        STOP prefix, so only the side check separates it from real
        protection — and dropping that check passed every other test
        here until this one existed.
        """
        orders = [{"ticker": "TEAM", "side": "BUY",
                   "order_type": "STOP_LOSS", "status": "SUBMITTED"}]
        self.assertIn("TEAM",
                      [p["ticker"] for p in broker.unprotected(self.held, orders)])

    def test_everything_is_unprotected_when_there_are_no_orders(self):
        self.assertEqual(len(broker.unprotected(self.held, [])), 3)


class StopLimitTest(unittest.TestCase):
    def test_a_stop_limit_is_flagged(self):
        orders = [{"ticker": "TEAM", "order_type": "STOP_LOSS_LIMIT",
                   "status": "SUBMITTED"}]
        self.assertEqual(len(broker.stop_limit_orders(orders)), 1)

    def test_a_plain_stop_is_not(self):
        orders = [{"ticker": "DELL", "order_type": "STOP_LOSS",
                   "status": "SUBMITTED"}]
        self.assertEqual(broker.stop_limit_orders(orders), [])

    def test_a_cancelled_stop_limit_is_not_a_live_risk(self):
        orders = [{"ticker": "TEAM", "order_type": "STOP_LOSS_LIMIT",
                   "status": "CANCELLED"}]
        self.assertEqual(broker.stop_limit_orders(orders), [])


class AccountIdTest(unittest.TestCase):
    def test_an_empty_env_value_is_not_treated_as_configured(self):
        """WEBULL_ACCOUNT_ID is present and empty in .env. Reading it as
        a usable value is what made the first attempt fail with no
        obvious cause."""
        import os
        previous = os.environ.get("WEBULL_ACCOUNT_ID")
        os.environ["WEBULL_ACCOUNT_ID"] = "   "
        self.addCleanup(lambda: os.environ.__setitem__("WEBULL_ACCOUNT_ID",
                                                       previous or ""))
        broker._account_id = "discovered-id"
        self.assertEqual(broker.account_id(), "discovered-id")


class ReadOnlyTest(unittest.TestCase):
    def test_this_module_cannot_place_an_order(self):
        """The value of an automated account reader is that it is unable
        to do anything, so it can run unattended."""
        import inspect
        source = inspect.getsource(broker)
        for forbidden in ("place_order", "cancel_order", "replace_order",
                          "place_option", "batch_place_order"):
            self.assertNotIn(forbidden, source)


class OrderHistoryTest(unittest.TestCase):
    """The endpoint answers an undated request with an empty list.

    No error, HTTP 200, nothing to notice — so the caller concludes the
    account has never had an order. TEAM showed as unprotected with
    apparently no order behind it; the stop was there, cancelled, and the
    undated call simply could not see it.
    """

    def setUp(self):
        self.calls = []
        self._real_call = broker._call
        self._real_client = broker._client
        self._real_account = broker.account_id
        broker.account_id = lambda *a, **k: "ACCT"
        self.addCleanup(setattr, broker, "_call", self._real_call)
        self.addCleanup(setattr, broker, "_client", self._real_client)
        self.addCleanup(setattr, broker, "account_id", self._real_account)

    def _vendor(self, rows):
        """Mimics the real endpoint: dates required, page size capped."""
        def call(fn, *args, **kwargs):
            self.calls.append(args)
            account, page_size, start, end = (list(args) + [None] * 4)[:4]
            if page_size and page_size > 100:
                raise broker.BrokerError("HTTP 417 invalid page_size")
            if not start or not end:
                return []
            return rows
        broker._call = call
        broker._client = lambda: type("C", (), {"order_v3": type("O", (), {
            "get_order_history": staticmethod(lambda *a, **k: None)})()})()

    def _team_stop(self, status="CANCELLED"):
        return [{"orders": [{"symbol": "TEAM", "side": "SELL",
                             "order_type": "STOP_LOSS_LIMIT", "stop_price": "160.00",
                             "limit_price": "150.00", "total_quantity": "10",
                             "filled_quantity": "0", "status": status,
                             "place_time_at": "2026-08-10T15:04:57.180Z",
                             "client_order_id": "abc"}]}]

    def test_a_date_range_is_always_sent(self):
        self._vendor(self._team_stop())
        broker.order_history()
        account, page_size, start, end = self.calls[0]
        self.assertEqual(account, "ACCT")
        self.assertTrue(start and end, "no date range was sent")
        self.assertLess(start, end)

    def test_the_page_size_is_capped_at_what_the_vendor_accepts(self):
        self._vendor(self._team_stop())
        broker.order_history(page_size=500)
        self.assertEqual(self.calls[0][1], 100)

    def test_legs_are_flattened_out_of_the_combo(self):
        self._vendor(self._team_stop())
        out = broker.order_history()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["ticker"], "TEAM")
        self.assertEqual(out[0]["stop_price"], 160.0)
        self.assertEqual(out[0]["limit_price"], 150.0)
        self.assertEqual(out[0]["status"], "CANCELLED")

    def test_an_empty_history_raises_rather_than_reading_as_fact(self):
        """An account with positions has an order history. Returning []
        lets a wrong call look like a true answer."""
        self._vendor([])
        with self.assertRaises(broker.EmptyHistory):
            broker.order_history()

    def test_an_empty_history_can_be_accepted_deliberately(self):
        self._vendor([])
        self.assertEqual(broker.order_history(strict=False), [])

    def test_a_cancelled_stop_is_visible_in_the_protection_history(self):
        """`unprotected` says a position has no stop. This says whether
        one was ever placed, which is the difference between an oversight
        and a stop that went away."""
        self._vendor(self._team_stop())
        hist = broker.protection_history("team")
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["status"], "CANCELLED")
        self.assertEqual(hist[0]["stop_price"], 160.0)

    def test_a_ticker_with_no_stops_returns_nothing(self):
        self._vendor(self._team_stop())
        self.assertEqual(broker.protection_history("NVDA"), [])


if __name__ == "__main__":
    unittest.main()
