"""EDGAR identity resolution.

Nothing here touches the network. The shapes below are trimmed copies of
real responses — General Motors Co really did first file in 2009-07-16,
and Lehman's 25-NSE filings really are dated October 2008 — because a
fixture invented from memory tests my memory rather than the parser.

The parsing detail that matters most is `_oldest_filing_date`. EDGAR
splits a filer's history: the last thousand or so filings sit in
`recent`, everything older is in archived index files listed under
`files`. Reading only `recent` dates a long-lived company far too late,
and dating a company too late means failing to flag contamination that
is really present — the error runs in the dangerous direction.
"""
import os
import tempfile
import unittest

from screener import db, edgar


GM_SUBMISSIONS = {
    "name": "General Motors Co",
    "formerNames": [],
    "filings": {
        "recent": {"form": ["10-K", "8-K"], "filingDate": ["2024-01-30", "2023-10-24"]},
        "files": [{"filingFrom": "2009-07-16", "filingTo": "2015-01-01"}],
    },
}

LEHMAN_SUBMISSIONS = {
    "name": "LEHMAN BROTHERS HOLDINGS INC. PLAN TRUST",
    "formerNames": [{"name": "LEHMAN BROTHERS HOLDINGS INC"}],
    "filings": {
        "recent": {
            "form": ["15-12B", "25-NSE", "25-NSE", "8-K"],
            "filingDate": ["2012-03-06", "2009-03-18", "2008-10-15", "2008-09-15"],
        },
        "files": [{"filingFrom": "1994-03-09", "filingTo": "2008-01-01"}],
    },
}

TICKER_MAP = {
    "0": {"ticker": "GM", "cik_str": 1467858, "title": "General Motors Co"},
    "1": {"ticker": "LEH", "cik_str": 806085, "title": "Lehman Brothers"},
}


class _StubbedEdgar(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._prev_path = db.DB_PATH
        db.DB_PATH = os.path.join(self._dir.name, "data", "test.db")
        db._schema_ready_for = None

        self._prev_get = edgar._get_json
        self._prev_map = edgar._ticker_map
        edgar._ticker_map = None
        self.requests = []
        os.environ["SEC_USER_AGENT"] = "test-suite nobody@example.com"

        def fake_get(url):
            self.requests.append(url)
            if "company_tickers" in url:
                return TICKER_MAP
            if "1467858" in url:
                return GM_SUBMISSIONS
            if "0000806085" in url or "806085" in url:
                return LEHMAN_SUBMISSIONS
            raise AssertionError(f"unexpected request: {url}")

        edgar._get_json = fake_get

    def tearDown(self):
        edgar._get_json = self._prev_get
        edgar._ticker_map = self._prev_map
        db.DB_PATH = self._prev_path
        db._schema_ready_for = None
        self._dir.cleanup()


class IdentityParsingTest(_StubbedEdgar):
    def test_first_filing_comes_from_the_archive_not_the_recent_block(self):
        # GM's recent filings start in 2023; its real first filing is
        # 2009-07-16 and lives in the archived index. Reading `recent`
        # alone would date the company 14 years late and silently pass
        # contaminated 2008 bars as legitimate.
        identity = edgar.company_identity("GM")
        self.assertEqual(identity["first_filing_date"], "2009-07-16")

    def test_the_cik_is_resolved_from_the_ticker_map(self):
        self.assertEqual(edgar.company_identity("GM")["cik"], 1467858)

    def test_a_lowercase_ticker_resolves(self):
        self.assertEqual(edgar.company_identity("gm")["ticker"], "GM")

    def test_former_names_are_captured(self):
        identity = edgar.company_identity("LEH")
        self.assertIn("LEHMAN BROTHERS HOLDINGS INC", identity["former_names"])

    def test_the_delisting_notice_is_the_most_recent_form_25(self):
        # Lehman filed 25-NSE twice. The later one is the operative date.
        identity = edgar.company_identity("LEH")
        self.assertEqual(identity["delisted_date"], "2009-03-18")
        self.assertEqual(identity["delisting_form"], "25-NSE")

    def test_deregistration_is_not_mistaken_for_delisting(self):
        # Lehman's most recent filing of the two kinds is a 15-12B in
        # 2012. Form 15 is deregistration and comes after; treating it as
        # the delisting date would be wrong by three years.
        self.assertEqual(edgar.company_identity("LEH")["delisted_date"], "2009-03-18")

    def test_a_still_listed_company_has_no_delisting_date(self):
        self.assertIsNone(edgar.company_identity("GM")["delisted_date"])

    def test_an_unknown_ticker_returns_a_blank_identity_rather_than_raising(self):
        # ETFs and foreign issues have no SEC filer at all. That is an
        # answer, not an error, and it must be recordable so it isn't
        # looked up again on every subsequent run.
        identity = edgar.company_identity("NOSUCHTICKER")
        self.assertIsNone(identity["cik"])
        self.assertEqual(identity["ticker"], "NOSUCHTICKER")


class ResolveIdentitiesTest(_StubbedEdgar):
    def test_resolving_writes_through_to_the_cache(self):
        edgar.resolve_identities(["GM"])
        self.assertEqual(db.get_cached_identity("GM")["cik"], 1467858)

    def test_a_second_run_makes_no_requests(self):
        # The entire purpose of the table. Resolving the universe is one
        # request per symbol; doing it twice is the cost being avoided.
        edgar.resolve_identities(["GM"])
        before = len(self.requests)
        fetched = edgar.resolve_identities(["GM"])
        self.assertEqual(fetched, 0)
        self.assertEqual(len(self.requests), before)

    def test_one_failing_symbol_does_not_abandon_the_rest(self):
        def flaky(url):
            if "1467858" in url:
                raise ConnectionError("boom")
            if "company_tickers" in url:
                return TICKER_MAP
            return LEHMAN_SUBMISSIONS
        edgar._get_json = flaky
        noted = []
        fetched = edgar.resolve_identities(["GM", "LEH"], progress=noted.append)
        self.assertEqual(fetched, 1)
        self.assertIsNotNone(db.get_cached_identity("LEH"))
        self.assertTrue(any("GM" in m for m in noted))

    def test_a_missing_user_agent_stops_everything(self):
        # SEC refuses these outright. Swallowing it per-symbol would turn
        # a configuration error into thousands of silent failures and an
        # empty cache that looks like a clean result.
        def refuse(url):
            raise edgar.MissingUserAgent("no contact address")
        edgar._get_json = refuse
        with self.assertRaises(edgar.MissingUserAgent):
            edgar.resolve_identities(["GM"])


class ContaminationReportTest(_StubbedEdgar):
    def test_a_recycled_ticker_is_reported_with_its_bar_count(self):
        edgar.resolve_identities(["GM"])
        bars = {"GM": [{"time": "2007-03-19T00:00:00.000+00:00"},
                       {"time": "2008-05-30T00:00:00.000+00:00"},
                       {"time": "2011-01-03T00:00:00.000+00:00"}]}
        found = edgar.contaminated_symbols(bars)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["symbol"], "GM")
        self.assertEqual(found[0]["bars_before"], 2)
        self.assertEqual(found[0]["earliest_bar"], "2007-03-19")

    def test_a_clean_symbol_is_absent_from_the_report(self):
        edgar.resolve_identities(["GM"])
        bars = {"GM": [{"time": "2011-01-03T00:00:00.000+00:00"}]}
        self.assertEqual(edgar.contaminated_symbols(bars), [])


class UserAgentTest(unittest.TestCase):
    def test_a_blank_user_agent_is_refused_before_any_request(self):
        prev = os.environ.get("SEC_USER_AGENT")
        os.environ["SEC_USER_AGENT"] = "   "
        try:
            with self.assertRaises(edgar.MissingUserAgent):
                edgar._user_agent()
        finally:
            if prev is None:
                os.environ.pop("SEC_USER_AGENT", None)
            else:
                os.environ["SEC_USER_AGENT"] = prev


if __name__ == "__main__":
    unittest.main()


class RecyclingGapTest(_StubbedEdgar):
    """The CIK test alone is not enough.

    On the real universe it flagged 605 symbols and 91% were corporate
    reorganisations — XOM, BlackRock, Bunge — where a company
    re-registered as a new legal entity and the same business kept
    trading under the same ticker without a break. A new CIK is not a
    new company. Genuine recycling leaves a trading gap; a reorganisation
    does not.
    """

    def _bars(self, dates):
        return [{"time": f"{d}T00:00:00.000+00:00"} for d in dates]

    def test_a_reorganisation_is_not_reported(self):
        # Continuous weekly bars straddling the new filing date.
        edgar.resolve_identities(["GM"])
        bars = {"GM": self._bars(["2009-07-03", "2009-07-10", "2009-07-24"])}
        self.assertEqual(edgar.contaminated_symbols(bars), [])

    def test_a_real_gap_is_reported(self):
        edgar.resolve_identities(["GM"])
        bars = {"GM": self._bars(["2007-03-16", "2007-03-23", "2011-01-07"])}
        found = edgar.contaminated_symbols(bars)
        self.assertEqual(len(found), 1)
        self.assertGreater(found[0]["gap_days"], 120)

    def test_the_raw_cik_finding_is_still_reachable(self):
        # Worth being able to see how much the gap test is removing.
        edgar.resolve_identities(["GM"])
        bars = {"GM": self._bars(["2009-07-03", "2009-07-10", "2009-07-24"])}
        self.assertEqual(len(edgar.contaminated_symbols(bars, min_gap_days=0)), 1)

    def test_history_entirely_before_the_filer_is_not_silently_passed(self):
        # No bars after the cutoff means no gap can be computed. That is
        # not evidence of innocence, so it must not slip through the
        # default filter as though it were clean.
        edgar.resolve_identities(["GM"])
        bars = {"GM": self._bars(["2007-03-16", "2007-03-23"])}
        self.assertEqual(edgar.contaminated_symbols(bars), [])
        self.assertEqual(len(edgar.contaminated_symbols(bars, min_gap_days=0)), 1)
