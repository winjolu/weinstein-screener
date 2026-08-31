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


if __name__ == "__main__":
    unittest.main()
