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


class SecurityTypeTest(unittest.TestCase):
    """Stage analysis assumes a price series driven by a business.

    Every fixture here is a real instrument with its real fields, because
    the whole point of this classifier is that the plausible-sounding
    rules fail on real data: filtering on the margin requirement deletes
    ordinary community banks, and matching the Nasdaq fifth letter turns
    Alphabet's Class A into an Alphabet preferred.
    """

    def _inst(self, symbol, name, margin="0.5", fractionable=True, **kw):
        base = {"symbol": symbol, "name": name, "status": "OC",
                "exchange_code": "NSQ", "margin_requirement_long": margin,
                "fractionable": fractionable, "etf_leveraged_factor": None,
                "crypto_etf": None, "single_stock_etf": None}
        base.update(kw)
        return base

    def _classify(self, instruments):
        return universe.classify_security_types(instruments)

    # --- preferreds by exchange notation -------------------------------

    def test_the_pr_infix_marks_a_preferred(self):
        got = self._classify([
            self._inst("ARR", "ARMOUR RESIDENTIAL REIT INC"),
            self._inst("ARR PRC", "ARMOUR RESIDENTIAL REIT INC", margin="1.0",
                       fractionable=False),
        ])
        self.assertEqual(got["ARR"], "common")
        self.assertEqual(got["ARR PRC"], "preferred")

    def test_a_liquid_preferred_is_still_a_preferred(self):
        """JPM's preferreds are marginable, so a tradability test alone
        would wave them through. The notation has to stand on its own."""
        got = self._classify([
            self._inst("JPM", "JPMORGAN CHASE & CO"),
            self._inst("JPM PRC", "JPMORGAN CHASE & CO", margin="0.5", fractionable=False),
        ])
        self.assertEqual(got["JPM PRC"], "preferred")

    # --- preferreds by Nasdaq suffix -----------------------------------

    def test_a_five_letter_sibling_on_full_margin_is_a_preferred(self):
        got = self._classify([
            self._inst("AGNC", "AGNC INVT CORP"),
            self._inst("AGNCL", "AGNC INVT CORP", margin="1.0", fractionable=False),
        ])
        self.assertEqual(got["AGNCL"], "preferred")

    def test_alphabet_class_a_is_not_an_alphabet_preferred(self):
        """GOOGL matches the suffix pattern exactly and is common stock."""
        got = self._classify([
            self._inst("GOOG", "ALPHABET INC"),
            self._inst("GOOGL", "ALPHABET INC"),
        ])
        self.assertEqual(got["GOOGL"], "common")

    def test_share_class_suffixes_are_never_preferred(self):
        got = self._classify([
            self._inst("CENT", "CENTRAL GARDEN & PET CO"),
            self._inst("CENTA", "CENTRAL GARDEN & PET CO", margin="1.0"),
            self._inst("UONE", "URBAN ONE INC"),
            self._inst("UONEK", "URBAN ONE INC", margin="1.0"),
        ])
        self.assertEqual(got["CENTA"], "common")
        self.assertEqual(got["UONEK"], "common")

    def test_a_five_letter_name_without_a_sibling_is_common(self):
        got = self._classify([self._inst("CMCSA", "COMCAST CORP")])
        self.assertEqual(got["CMCSA"], "common")

    def test_a_shared_prefix_is_not_enough_without_a_shared_name(self):
        """Otherwise any four-letter ticker captures unrelated five-letter
        ones that happen to start the same way."""
        got = self._classify([
            self._inst("SAND", "SANDSTORM GOLD LTD"),
            self._inst("SANDL", "SOME OTHER COMPANY INC", margin="1.0", fractionable=False),
        ])
        self.assertEqual(got["SANDL"], "common")

    # --- the false positive that made margin unusable alone ------------

    def test_an_illiquid_bank_on_full_margin_stays_common(self):
        """GCBC, LARK, SBFG and ATLO are ordinary community banks that
        carry a 100% margin requirement. They're precisely the small-cap
        Stage 2 names this screener exists to surface, so a margin-based
        filter would delete the tool's whole reason for existing."""
        for symbol, name in (("GCBC", "GREENE COUNTY BANCORP INC"),
                             ("LARK", "LANDMARK BANCORP INC"),
                             ("ATLO", "AMES NATIONAL CORP")):
            got = self._classify([self._inst(symbol, name, margin="1.0", fractionable=False)])
            self.assertEqual(got[symbol], "common", f"{symbol} must survive")

    # --- units, warrants, rights ---------------------------------------

    def test_spac_units_and_warrants_are_separated_from_the_common(self):
        got = self._classify([
            self._inst("AACB", "ARTIUS II ACQUISITION INC"),
            self._inst("AACBU", "ARTIUS II ACQUISITION INC", margin="1.0", fractionable=False),
            self._inst("AACBW", "ARTIUS II ACQUISITION INC", margin="1.0", fractionable=False),
            self._inst("AACBR", "ARTIUS II ACQUISITION INC", margin="1.0", fractionable=False),
        ])
        self.assertEqual(got["AACB"], "common")
        self.assertEqual(got["AACBU"], "unit")
        self.assertEqual(got["AACBW"], "warrant")
        self.assertEqual(got["AACBR"], "right")

    # --- funds ----------------------------------------------------------

    def test_a_closed_end_fund_is_classified_as_a_fund(self):
        """RVT leaves etf_leveraged_factor empty but carries crypto_etf,
        which is what separates a pooled product from a real company."""
        got = self._classify([
            self._inst("RVT", "Royce Small-Cap Trust", crypto_etf=False),
        ])
        self.assertEqual(got["RVT"], "fund")

    def test_a_bank_with_trust_in_its_name_is_not_a_fund(self):
        got = self._classify([self._inst("HTB", "HOMETRUST BANCSHARES INC")])
        self.assertEqual(got["HTB"], "common")

    def test_an_etf_is_a_fund(self):
        got = self._classify([
            self._inst("QQQ", "Invesco QQQ Trust", etf_leveraged_factor="0",
                       crypto_etf=False, single_stock_etf=False),
        ])
        self.assertEqual(got["QQQ"], "fund")

    # --- what a scan actually admits ------------------------------------

    def test_only_common_is_screened_by_default(self):
        self.assertEqual(universe.wanted_types(), {"common"})

    def test_funds_and_non_common_are_separate_opt_ins(self):
        self.assertEqual(universe.wanted_types(include_funds=True), {"common", "fund"})
        self.assertNotIn("fund", universe.wanted_types(include_non_common=True))
        self.assertIn("preferred", universe.wanted_types(include_non_common=True))
