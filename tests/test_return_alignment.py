"""The arms carrying published conclusions must not credit return from
before the decision that bought it.

`market_core.lookahead` catches a rule that consults future bars.
Nothing caught a rule that decides correctly and then books the wrong
window, which is the failure that produced +19.48%/yr from the 200-day
rule — both the leaky and the lagged version pass truncation.

Measured once across all 237 arms: 475 of 1,608,633 trades violate this
(0.030%). The arms below carry every published survivorship and band
result and all of them are clean, so this is a regression guard rather
than a known-failing check. It fails the day a re-run reintroduces the
defect into a result I would otherwise quote.

Two families are deliberately excluded and named here rather than
silently skipped:

- `s1*_B_pit_all_*` were withdrawn for lost rows and are documented as
  such; they violate at 1.78%.
- The earliest exploratory arms (`study_*`, `gate_*`, `e1_*`, `e2_*`,
  `e3_*`, `v2_*`, `big_*`, `trail_*`, `partial_*`, `pivot_length=*`)
  recorded `as_of_date` as the run date rather than the decision date,
  so the invariant is not merely violated there, it is unmeasurable.
  Nothing published rests on them.

Skips when the local screener database is absent, in the same way as the
adjustment and cross-vendor tests — this guards results, and there are
no results to guard on a fresh clone.
"""
import os
import sqlite3
import unittest

from market_core import alignment

from screener import db

# Every arm behind a figure in docs/where-this-stands.md.
PUBLISHED_ARMS = (
    "w2_2005_R20", "w2_2005_M9",
    "w2_2010_R20", "w2_2010_M9",
    "w2_2021_R20", "w2_2021_M9",
    "w3_2010_R20", "w3_2010_M9",
    "w3_2021_R20", "w3_2021_M9",
    "t5b_band00", "t5b_band10", "t5b_band15", "t5b_band17",
    "t5b_band18", "t5b_band20", "t5b_band25", "t5b_band30",
    "t5c_thin1", "t5c_thin2", "t5c_thin3",
    "t3_d020", "t3_d050", "t3_d100", "t3_d150", "t3_d200",
)


def _trades(conn, arm):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(
        "SELECT * FROM backtest_trades WHERE parameter_set=?", (arm,))]


@unittest.skipUnless(os.path.exists(db.DB_PATH), "no local screener database")
class PublishedArmAlignmentTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(f"file:{db.DB_PATH}?mode=ro", uri=True)
        self.addCleanup(self.conn.close)

    def test_no_published_arm_credits_return_from_before_its_decision(self):
        offenders = []
        for arm in PUBLISHED_ARMS:
            trades = _trades(self.conn, arm)
            if not trades:
                continue
            summary = alignment.check(trades, raises=False)
            if summary["n"]:
                worst = max(summary["violations"], key=lambda v: v["days"])
                # The summary carries every offending trade, so reporting
                # it whole buries the answer under a 363,000-character
                # diff. Name the arm and the worst lead instead.
                offenders.append(
                    f"{arm}: {summary['n']}/{summary['total']} trades, "
                    f"worst {worst['days']}d")
        self.assertEqual(offenders, [], "misaligned arms: " + "; ".join(offenders))

    def test_the_arms_actually_exist_so_this_is_not_vacuous(self):
        """A test that passes because it examined nothing is worse than
        no test, because it reads as protection."""
        present = [a for a in PUBLISHED_ARMS if _trades(self.conn, a)]
        self.assertGreaterEqual(len(present), 20)

    def test_the_withdrawn_arms_still_violate(self):
        """Pins the contrast. If this ever passes, either the withdrawn
        arms were repaired without the docs being updated, or the check
        stopped detecting anything.
        """
        trades = _trades(self.conn, "s1r_B_pit_all_M9")
        if not trades:
            self.skipTest("withdrawn arm not present locally")
        summary = alignment.check(trades, raises=False)
        self.assertGreater(summary["n"], 100)


if __name__ == "__main__":
    unittest.main()
