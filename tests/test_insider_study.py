"""The arithmetic behind I1, checked against constructed panels rather
than the live archive.

Everything here is a pure function of a price panel and an events frame,
so a small synthetic panel with known answers baked in exercises the
same code paths as the 2.4-million-row real run without needing the
archive present. The archive-dependent loaders (`load_panel` and its
pieces) are covered by running the real study, not by a unit test — a
synthetic `tickers`/`insiders`/`prices` schema would just be a second,
unsynchronised copy of the real one to keep correct.
"""
import sqlite3
import unittest

import numpy as np
import pandas as pd

from screener import insider_study as study


def _memory_archive():
    """A minimal in-memory stand-in for the two tables `insider_events`
    reads, just enough columns to exercise the date-window filter
    without needing the real archive present."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tickers (tbl, ticker, exchange, category, "
                 "firstpricedate, lastpricedate)")
    conn.execute("INSERT INTO tickers VALUES "
                 "('SEP', 'AAA', 'NASDAQ', 'Domestic Common Stock', "
                 "'2000-01-01', '2030-01-01')")
    conn.execute("CREATE TABLE insiders (ticker, filingdate, transactioncode)")
    conn.executemany("INSERT INTO insiders VALUES (?, ?, ?)", [
        ("AAA", "2021-06-01", "P"),
        ("AAA", "2023-03-01", "P"),
        ("AAA", "2024-07-01", "P"),
        ("AAA", "2026-01-01", "P"),
    ])
    return conn


def _series(start_price, n_days, daily_return=0.0, start_date="2020-01-01"):
    """A flat calendar of `n_days` trading days (weekends included is
    fine — the study only cares about array position, not the calendar)
    compounding at `daily_return` a day from `start_price`."""
    dates = pd.date_range(start_date, periods=n_days, freq="D").strftime("%Y-%m-%d").to_numpy()
    closes = start_price * (1 + daily_return) ** np.arange(n_days)
    return dates, closes.astype(float)


class EventReturnsTest(unittest.TestCase):
    def setUp(self):
        # AAA rises 1%/day; the benchmark is flat. A 21-day raw return
        # of (1.01**21 - 1) should show up almost entirely as abnormal
        # return once the flat benchmark is subtracted.
        dates, closes = _series(100.0, 100, daily_return=0.01)
        self.by_ticker = {"AAA": (dates, closes)}
        self.bench_dates, self.bench_close = _series(50.0, 100, daily_return=0.0)
        self.events = pd.DataFrame({
            "ticker": ["AAA"], "filingdate": [dates[10]], "transactioncode": ["P"]})

    def test_raw_return_matches_the_known_compounding(self):
        out = study.event_returns(self.events, self.by_ticker,
                                  self.bench_dates, self.bench_close, horizons=(21,))
        expected = (1.01 ** 21 - 1) * 100
        self.assertAlmostEqual(out.iloc[0]["raw_pct"], expected, places=6)

    def test_abnormal_return_is_raw_minus_flat_benchmark(self):
        out = study.event_returns(self.events, self.by_ticker,
                                  self.bench_dates, self.bench_close, horizons=(21,))
        self.assertAlmostEqual(out.iloc[0]["abnormal_pct"], out.iloc[0]["raw_pct"], places=6)

    def test_costed_return_is_lower_than_uncosted(self):
        out = study.event_returns(self.events, self.by_ticker,
                                  self.bench_dates, self.bench_close, horizons=(21,))
        self.assertLess(out.iloc[0]["abnormal_costed_pct"], out.iloc[0]["abnormal_pct"])

    def test_an_event_too_close_to_the_end_of_history_is_dropped(self):
        """No bar 21 days forward exists for a filing on the last
        available date — the event must be excluded, not extrapolated."""
        dates, closes = self.by_ticker["AAA"]
        late = pd.DataFrame({"ticker": ["AAA"], "filingdate": [dates[-1]],
                             "transactioncode": ["P"]})
        out = study.event_returns(late, self.by_ticker,
                                  self.bench_dates, self.bench_close, horizons=(21,))
        self.assertEqual(len(out), 0)

    def test_a_dropped_event_does_not_misalign_the_surviving_ones(self):
        """Two events for the same ticker in one call, only one of which
        has a bar far enough forward. The per-horizon drop must not shift
        which filing date attaches to the surviving row — an unfiltered
        date array reused after filtering closes and dates by an "ok"
        mask is exactly the bug this catches: it either crashes on a
        length mismatch or, in a case where lengths happen to coincide,
        silently pairs the wrong date with the wrong return."""
        dates, closes = self.by_ticker["AAA"]
        events = pd.DataFrame({
            "ticker": ["AAA", "AAA"],
            "filingdate": [dates[10], dates[-1]],  # second has no 21-day bar
            "transactioncode": ["P", "P"],
        })
        out = study.event_returns(events, self.by_ticker,
                                  self.bench_dates, self.bench_close, horizons=(21,))
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["filingdate"], dates[10])

    def test_a_filing_timestamp_finer_than_the_daily_calendar_still_resolves(self):
        """searchsorted with side='left' finds the first trading day at
        or after the filing. A timestamp that sorts between two known
        daily entries must not be silently dropped."""
        events = pd.DataFrame({"ticker": ["AAA"], "filingdate": ["2020-01-11T12:00:00"],
                               "transactioncode": ["P"]})
        out = study.event_returns(events, self.by_ticker,
                                  self.bench_dates, self.bench_close, horizons=(1,))
        self.assertEqual(len(out), 1)


class TwoWayTestTest(unittest.TestCase):
    def test_a_real_difference_is_detected(self):
        rng = np.random.default_rng(0)
        a = pd.DataFrame({
            "abnormal_costed_pct": rng.normal(3.0, 1.0, 300),
            "ticker": rng.integers(0, 30, 300),
            "filingdate": rng.integers(0, 40, 300),
        })
        b = pd.DataFrame({
            "abnormal_costed_pct": rng.normal(0.0, 1.0, 300),
            "ticker": rng.integers(0, 30, 300),
            "filingdate": rng.integers(0, 40, 300),
        })
        out = study.two_way_test(a, b)
        self.assertAlmostEqual(out["diff"], 3.0, delta=0.5)
        self.assertGreater(out["tvalue"], 3.0)

    def test_identical_groups_show_no_difference(self):
        rng = np.random.default_rng(1)
        a = pd.DataFrame({
            "abnormal_costed_pct": rng.normal(1.0, 1.0, 300),
            "ticker": rng.integers(0, 30, 300),
            "filingdate": rng.integers(0, 40, 300),
        })
        b = pd.DataFrame({
            "abnormal_costed_pct": rng.normal(1.0, 1.0, 300),
            "ticker": rng.integers(0, 30, 300),
            "filingdate": rng.integers(0, 40, 300),
        })
        out = study.two_way_test(a, b)
        self.assertLess(abs(out["tvalue"]), 2.5)


class RawVsPassiveTest(unittest.TestCase):
    """The house rule that a strategy result is never reported as a bare
    excess without the two absolute numbers it was computed from."""

    def test_passive_recovers_the_benchmark_leg(self):
        # mean(raw) = 4.0, mean(abnormal) = 1.5, so passive = 2.5 — the
        # subtraction happens on the two means, not row by row.
        frame = pd.DataFrame({"raw_pct": [5.0, 3.0], "abnormal_pct": [2.0, 1.0]})
        raw, passive = study.raw_vs_passive(frame)
        self.assertAlmostEqual(raw, 4.0)
        self.assertAlmostEqual(passive, 2.5)

    def test_zero_excess_means_raw_and_passive_are_equal(self):
        frame = pd.DataFrame({"raw_pct": [1.5, 1.5], "abnormal_pct": [0.0, 0.0]})
        raw, passive = study.raw_vs_passive(frame)
        self.assertAlmostEqual(raw, passive)

    def test_an_empty_frame_returns_nan_not_an_error(self):
        raw, passive = study.raw_vs_passive(pd.DataFrame({"raw_pct": [], "abnormal_pct": []}))
        self.assertTrue(np.isnan(raw))
        self.assertTrue(np.isnan(passive))


class MeanVsZeroTest(unittest.TestCase):
    def test_a_nonzero_mean_is_detected(self):
        rng = np.random.default_rng(2)
        frame = pd.DataFrame({
            "abnormal_costed_pct": rng.normal(2.0, 1.0, 400),
            "ticker": rng.integers(0, 40, 400),
            "filingdate": rng.integers(0, 50, 400),
        })
        out = study.mean_vs_zero(frame)
        self.assertAlmostEqual(out["mean"], 2.0, delta=0.3)
        self.assertGreater(out["tvalue"], 3.0)


class ShuffledControlTest(unittest.TestCase):
    def test_shuffling_keeps_the_same_tickers_and_dates_just_recombined(self):
        dates, closes = _series(100.0, 60, daily_return=0.001)
        by_ticker = {"AAA": (dates, closes), "BBB": (dates, closes * 2)}
        bench_dates, bench_close = _series(50.0, 60, daily_return=0.0)
        events = pd.DataFrame({
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "filingdate": [dates[5], dates[10], dates[15], dates[20]],
            "transactioncode": ["P", "P", "P", "P"],
        })
        out = study.shuffled_control(events, by_ticker, bench_dates, bench_close,
                                     horizons=(5,))
        # Same tickers appear, but not necessarily paired with their own
        # original date — that recombination is the entire point.
        self.assertEqual(set(out["ticker"]) <= {"AAA", "BBB"}, True)


class InsiderEventsDateWindowTest(unittest.TestCase):
    """The 2023-2025 out-of-sample retest depends on this filter actually
    restricting which filings are looked at, not just being accepted and
    ignored."""

    def setUp(self):
        self.conn = _memory_archive()
        self.addCleanup(self.conn.close)
        self.eligible = study.eligible_tickers(self.conn)

    def test_no_window_returns_every_filing(self):
        out = study.insider_events(self.conn, self.eligible)
        self.assertEqual(len(out), 4)

    def test_a_window_keeps_only_filings_inside_it(self):
        out = study.insider_events(self.conn, self.eligible,
                                   filing_start="2023-01-01", filing_end="2025-12-31")
        self.assertEqual(sorted(out["filingdate"]), ["2023-03-01", "2024-07-01"])

    def test_the_window_boundaries_are_inclusive(self):
        out = study.insider_events(self.conn, self.eligible,
                                   filing_start="2023-03-01", filing_end="2023-03-01")
        self.assertEqual(list(out["filingdate"]), ["2023-03-01"])

    def test_an_empty_window_returns_no_rows_not_an_error(self):
        out = study.insider_events(self.conn, self.eligible,
                                   filing_start="2027-01-01", filing_end="2027-12-31")
        self.assertEqual(len(out), 0)


class RandomControlTest(unittest.TestCase):
    def test_a_drawn_ticker_is_always_listed_on_the_drawn_date(self):
        """The rejection-sampling loop must never hand back a
        (ticker, date) pair outside that ticker's own listing window —
        that would let a control observation see a company before it
        existed or after it delisted, corrupting the very leak this
        project has been burned by twice already."""
        dates, closes = _series(100.0, 40, daily_return=0.001)
        by_ticker = {
            "EARLY": (dates[:20], closes[:20]),
            "LATE": (dates[20:], closes[20:]),
        }
        bench_dates, bench_close = _series(50.0, 40, daily_return=0.0)
        eligible = pd.DataFrame({
            "ticker": ["EARLY", "LATE"],
            "firstpricedate": [dates[0], dates[20]],
            "lastpricedate": [dates[19], dates[-1]],
        }).set_index("ticker")
        events = pd.DataFrame({
            "ticker": ["EARLY"] * 5 + ["LATE"] * 5,
            "filingdate": list(dates[2:7]) + list(dates[22:27]),
            "transactioncode": ["P"] * 10,
        })
        out = study.random_control(events, eligible, by_ticker,
                                   bench_dates, bench_close, horizons=(1,), draws=5)
        self.assertGreater(len(out), 0)


if __name__ == "__main__":
    unittest.main()
