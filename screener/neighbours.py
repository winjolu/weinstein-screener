"""Ranking setups by what similar ones did before.

For a candidate, find the historical setups closest to it and use their
outcomes. No training, no parametric assumptions, and interpretable in a
way the checklist is not: "this resembles these twenty, of which six ran
more than 50%."

Four things would each silently fake a result here, so each is handled
explicitly rather than trusted:

**Same-ticker neighbours.** The same stock at adjacent weeks produces
near-identical vectors with near-identical outcomes. Left in, the model
retrieves its own memories, scores beautifully, and has learned nothing.
Excluded.

**Scale.** Relative strength runs 0-100, turnover runs to millions,
booleans are 0 or 1. Unscaled, distance is whichever column has the
largest units. Standardised on fit-set statistics only.

**Missing values.** My first pass dropped any feature with a single gap
anywhere, which threw out relative strength — the one feature with a
monotone gradient in all three windows — over 50 missing rows in 6,151.
Now imputed to the fit-set median per feature, with the gap recorded.

**The target.** Returns here are violently right-skewed: the top 5% of
trades carry 88-144% of profit. The mean of k neighbours is dominated by
whether one happened to be a monster, so what gets predicted is the
*share of neighbours that exceeded a threshold* — tail probability,
which is how this strategy actually earns.

The bar is not "beats random". It is "beats ranking on relative strength
alone", because a neighbour search that merely rediscovers RS has added
complexity and nothing else.
"""
import math
import statistics

EXCLUDED = frozenset({"ticker", "entry_date", "return_pct", "parameter_set",
                      "conditions_met"})


def feature_names(rows):
    """Numeric feature columns present in at least one row."""
    names = set()
    for row in rows:
        for key, value in row.items():
            if key in EXCLUDED:
                continue
            if isinstance(value, bool) or isinstance(value, (int, float)):
                names.add(key)
    return sorted(names)


def _raw(row, names):
    out = []
    for name in names:
        value = row.get(name)
        if isinstance(value, bool):
            value = 1.0 if value else 0.0
        out.append(float(value) if isinstance(value, (int, float)) else None)
    return out


class Index:
    """A fitted neighbour index. Fit on the past, query with the present."""

    def __init__(self, fit_rows, names=None, threshold_pct=50.0, k=25):
        self.names = names or feature_names(fit_rows)
        self.threshold_pct = threshold_pct
        self.k = k

        raw = [_raw(r, self.names) for r in fit_rows]
        # Median rather than mean: these distributions are skewed enough
        # that a mean would place imputed rows somewhere no real setup sits.
        self.medians = []
        for col in range(len(self.names)):
            seen = [v[col] for v in raw if v[col] is not None]
            self.medians.append(statistics.median(seen) if seen else 0.0)

        filled = [[v if v is not None else self.medians[c] for c, v in enumerate(row)]
                  for row in raw]
        self.centres = [statistics.mean(col) for col in zip(*filled)] if filled else []
        self.scales = []
        for col in zip(*filled) if filled else []:
            spread = statistics.pstdev(col)
            # A constant feature contributes no information; a zero scale
            # would divide by zero and a tiny one would make noise dominate.
            self.scales.append(spread if spread > 1e-9 else 1.0)

        self.rows = fit_rows
        self.vectors = [self._encode_filled(row) for row in filled]

    def _encode_filled(self, filled):
        return [(v - c) / s for v, c, s in zip(filled, self.centres, self.scales)]

    def encode(self, row):
        raw = _raw(row, self.names)
        filled = [v if v is not None else self.medians[c] for c, v in enumerate(raw)]
        return self._encode_filled(filled)

    def neighbours(self, row, exclude_ticker=True):
        """The k closest fitted rows, nearest first."""
        target = self.encode(row)
        ticker = row.get("ticker")
        scored = []
        for other, vector in zip(self.rows, self.vectors):
            if exclude_ticker and ticker and other.get("ticker") == ticker:
                continue
            distance = sum((a - b) ** 2 for a, b in zip(target, vector))
            scored.append((distance, other))
        scored.sort(key=lambda pair: pair[0])
        return [other for _, other in scored[:self.k]]

    def tail_probability(self, row, exclude_ticker=True):
        """Share of neighbours that beat the threshold. 0.0 if none found."""
        found = self.neighbours(row, exclude_ticker=exclude_ticker)
        if not found:
            return 0.0
        hits = sum(1 for other in found
                   if (other.get("return_pct") or 0) > self.threshold_pct)
        return hits / len(found)

    def rank(self, rows, exclude_ticker=True):
        """Rows ordered best first by neighbour tail probability."""
        scored = [(self.tail_probability(r, exclude_ticker), r) for r in rows]
        scored.sort(key=lambda pair: -pair[0])
        return [row for _, row in scored]


def top_decile_mean(ranked, fraction=0.1):
    """Mean realised return of the best-ranked slice.

    The score that matters for a ranking: a rule that orders signals
    usefully should put the good ones at the top, and that is visible in
    what the top slice actually returned.
    """
    if not ranked:
        return float("nan")
    cut = max(int(len(ranked) * fraction), 1)
    returns = [r["return_pct"] for r in ranked[:cut] if r.get("return_pct") is not None]
    return statistics.mean(returns) if returns else float("nan")
