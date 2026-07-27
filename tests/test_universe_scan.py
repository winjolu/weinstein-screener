"""The universe scan's two silent-exclusion points.

Both functions here decide that something never gets looked at. A false
negative in either produces no error, no warning and no row — the ticker
simply isn't in the output, and nothing indicates it was ever considered.
That's the failure mode least likely to be noticed, so it's the one worth
testing hardest.

The prefilter in particular is meant to be a *necessary* condition: it may
discard only what genuinely cannot qualify. That claim is checked
exhaustively below rather than on a few hand-picked cases, because I
reasoned my way to a wrong answer once already on the swing rule and only
found it by testing against real numbers.
"""
import itertools
import math
import unittest

from screener import conditions as C
from screener import run_screener, universe

GATES = ("stage_setup", "price_above_ma", "market_stage")
NON_GATES = (
    "volume_confirmation", "rs_improving", "resistance_breakout",
    "pullback_quality", "risk_reward",
)
ALL_CONDITIONS = GATES + ("sector_strength",) + NON_GATES


def _result(met, failed, sector=None, fail_a_gate=False):
    """Builds a scored result with the requested tallies.

    Failures land on non-gate conditions unless fail_a_gate is set, so the
    hard-gate rule can be exercised separately from the arithmetic.
    """
    values = {}
    order = list(NON_GATES) + list(GATES) if not fail_a_gate else list(GATES) + list(NON_GATES)

    remaining_met, remaining_failed = met, failed
    for name in order:
        if remaining_failed:
            values[name] = False
            remaining_failed -= 1
        elif remaining_met:
            values[name] = True
            remaining_met -= 1
        else:
            values[name] = None
    values["sector_strength"] = sector

    return {"conditions": values, "scoring": C.score_conditions(values)}


class PrefilterIsNecessaryConditionTest(unittest.TestCase):
    """Exhaustive: anything the prefilter rejects must genuinely be
    incapable of qualifying, whichever way the sector lookup lands."""

    def test_never_discards_something_that_could_qualify(self):
        checked = 0
        for met, failed in itertools.product(range(9), repeat=2):
            if met + failed > 8:  # leave room for sector_strength
                continue
            result = _result(met, failed, sector=None)
            if result["scoring"]["blocking"]:
                continue
            checked += 1

            rejected = not run_screener._could_still_qualify(result)
            if not rejected:
                continue

            # Rejected. Prove no sector outcome could have rescued it.
            for sector_outcome in (True, False, None):
                values = dict(result["conditions"])
                values["sector_strength"] = sector_outcome
                self.assertFalse(
                    C.score_conditions(values)["actionable"],
                    f"prefilter discarded met={met} failed={failed}, but it "
                    f"becomes actionable when sector resolves to {sector_outcome}",
                )
        self.assertGreater(checked, 20, "exhaustive sweep covered too little ground")

    def test_admits_the_borderline_case_it_must_not_lose(self):
        # 7 met / 1 failed / sector pending -> 8 of 9 once sector lands,
        # which is exactly the threshold.
        self.assertTrue(run_screener._could_still_qualify(_result(7, 1, sector=None)))

    def test_rejects_when_two_have_already_failed(self):
        # Best case is 7 met of 9 resolved, and 9 resolved requires 8.
        self.assertFalse(run_screener._could_still_qualify(_result(6, 2, sector=None)))

    def test_rejects_when_too_little_would_resolve(self):
        # Four unknowns besides sector: only 6 could ever resolve, under
        # the evidence floor of 7.
        self.assertFalse(run_screener._could_still_qualify(_result(4, 0, sector=None)))

    def test_a_failed_hard_gate_is_fatal_regardless_of_score(self):
        result = _result(7, 1, sector=None, fail_a_gate=True)
        self.assertTrue(result["scoring"]["blocking"])
        self.assertFalse(run_screener._could_still_qualify(result))

    def test_does_not_over_credit_an_already_resolved_sector(self):
        """Crediting a pending sector unconditionally would count a tenth
        condition that doesn't exist.

        Picked so the bug actually changes the answer. Five met and one
        failed with the sector already in hand means only six conditions
        will ever resolve, under the evidence floor of seven — so this
        can't qualify. Adding a phantom sector on top lifts it to seven
        resolved and six met, which clears the bar spuriously.
        """
        result = _result(4, 1, sector=True)
        scoring = result["scoring"]
        self.assertEqual(scoring["resolved"], 6)
        self.assertLessEqual(scoring["resolved"], len(ALL_CONDITIONS))
        self.assertFalse(run_screener._could_still_qualify(result))


class FundDiscriminatorTest(unittest.TestCase):
    """ETF-specific fields are populated for pooled products and absent
    for ordinary shares. Matching on the name instead misclassifies
    REITs and anything else legitimately called a trust."""

    def _stock(self, **kw):
        base = {"symbol": "AAPL", "name": "APPLE INC", "status": "OC",
                "exchange_code": "NSQ", "etf_leveraged_factor": None,
                "crypto_etf": None, "single_stock_etf": None}
        base.update(kw)
        return base

    def _fund(self, **kw):
        base = {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "status": "OC",
                "exchange_code": "PSE", "etf_leveraged_factor": "0",
                "crypto_etf": False, "single_stock_etf": False}
        base.update(kw)
        return base

    def test_separates_stock_from_fund(self):
        self.assertFalse(universe.is_fund(self._stock()))
        self.assertTrue(universe.is_fund(self._fund()))

    def test_a_trust_in_the_name_does_not_make_it_a_fund(self):
        reit = self._stock(symbol="KIM", name="KIMCO REALTY TRUST")
        self.assertFalse(universe.is_fund(reit))

    def test_a_fund_without_telltale_naming_is_still_caught(self):
        self.assertTrue(universe.is_fund(self._fund(symbol="QWLD", name="Some Opaque Name")))


class ScreenableFilterTest(FundDiscriminatorTest):
    def test_keeps_a_tradable_major_exchange_stock(self):
        self.assertTrue(universe.is_screenable(self._stock()))

    def test_drops_untradable_status(self):
        self.assertFalse(universe.is_screenable(self._stock(status="NT")))

    def test_drops_otc_venues(self):
        for venue in ("PINL", "PK", "OTCID", "OTCB"):
            self.assertFalse(universe.is_screenable(self._stock(exchange_code=venue)), venue)

    def test_drops_leveraged_and_derivative_products(self):
        self.assertFalse(universe.is_screenable(self._fund(etf_leveraged_flag="YES")))
        self.assertFalse(universe.is_screenable(self._fund(single_stock_etf=True)))
        self.assertFalse(universe.is_screenable(self._fund(crypto_etf=True)))


if __name__ == "__main__":
    unittest.main()
