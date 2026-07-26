"""Client-side throttle for the market data API.

The documented ceiling is 300 requests per 60 seconds, i.e. 5 per second.
That never mattered while every call fetched a single symbol, but once
bar fetches are batched the caller issues them in tight bursts and will
hit the limit for real.

This is a sliding-window limiter rather than a fixed one-per-200ms sleep:
the quota is defined over a window, so what matters is how many calls
landed in the last 60 seconds, not the gap between any two. A fixed sleep
would also throw away the headroom that exists when a burst follows a
quiet period.
"""
import threading
import time

MAX_CALLS = 300
WINDOW_SECONDS = 60.0

# Leave a little of the quota unused. Client and server disagree slightly
# about when a window starts, and being throttled costs far more than the
# handful of calls this holds back.
SAFETY_MARGIN = 0.9


class RateLimiter:
    """Blocks until a call can be made without breaching the window."""

    def __init__(self, max_calls=MAX_CALLS, window_seconds=WINDOW_SECONDS, safety_margin=SAFETY_MARGIN):
        self._limit = max(1, int(max_calls * safety_margin))
        self._window = window_seconds
        self._calls = []
        self._lock = threading.Lock()

    def acquire(self):
        """Records a call, sleeping first if the window is already full."""
        while True:
            with self._lock:
                now = time.monotonic()
                cutoff = now - self._window
                self._calls = [t for t in self._calls if t > cutoff]

                if len(self._calls) < self._limit:
                    self._calls.append(now)
                    return

                # Wait for the oldest call to age out of the window.
                sleep_for = self._calls[0] - cutoff
            time.sleep(max(sleep_for, 0.01))

    def snapshot(self):
        """Calls currently inside the window, for progress reporting."""
        with self._lock:
            cutoff = time.monotonic() - self._window
            self._calls = [t for t in self._calls if t > cutoff]
            return len(self._calls), self._limit


# One shared limiter per process — the quota is per credential, not per
# call site, so every caller has to draw from the same budget.
_limiter = RateLimiter()


def acquire():
    _limiter.acquire()


def snapshot():
    return _limiter.snapshot()
