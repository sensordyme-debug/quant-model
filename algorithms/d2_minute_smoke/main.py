# D-2 acceptance test: prove LEAN actually reads the IBKR minute bars we wrote.
#
# This is a data probe, not a strategy. It streams SPY at minute resolution across the
# whole backfill and asserts the properties an intraday sleeve depends on, then prints
# a PASS/FAIL block into engine-output.txt.
#
# It exists because of the D-1 lesson: a malformed factor file made LEAN return *zero
# bars* for a symbol with no error and no failed data request, and three symbols were
# silently dropped that way. File-level validation cannot catch that - only asking the
# engine what it sees can.
from AlgorithmImports import *


class D2MinuteSmokeAlgorithm(QCAlgorithm):
    """Hypothesis: the D-2 minute files stream through LEAN with full RTH coverage."""

    # A regular session is 390 minutes; a half day is 210. Anything shorter is a gap.
    FULL_SESSION = 390
    HALF_SESSION = 210

    def initialize(self):
        self.set_start_date(2020, 1, 2)
        self.set_end_date(2026, 9, 8)
        self.set_cash(100_000)
        self.symbol = self.add_equity("SPY", Resolution.MINUTE).symbol
        self.set_benchmark(self.symbol)

        self.bars = 0
        self.bars_today = 0
        self.sessions = 0
        self.short_sessions = []
        self.first_bar = None
        self.last_bar = None
        self.first_minute = {}   # HH:MM of the first bar of each session -> count
        self.last_minute = {}    # HH:MM of the last bar of each session -> count
        self.bad_ohlc = 0
        self.zero_volume = 0
        self.current_day = None
        self.day_open_time = None

    def on_data(self, data: Slice):
        bar = data.bars.get(self.symbol)
        if bar is None:
            return

        stamp = self.time  # LEAN stamps a minute bar at its close
        day = stamp.date()
        if day != self.current_day:
            self._close_session()
            self.current_day = day
            self.bars_today = 0
            self.day_open_time = stamp

        self.bars += 1
        self.bars_today += 1
        if self.first_bar is None:
            self.first_bar = stamp
        self.last_bar = stamp

        if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high
                and bar.low > 0):
            self.bad_ohlc += 1
        if bar.volume <= 0:
            self.zero_volume += 1

    def _close_session(self):
        if self.current_day is None:
            return
        self.sessions += 1
        if self.bars_today < self.HALF_SESSION:
            self.short_sessions.append(f"{self.current_day}({self.bars_today})")
        key_open = self.day_open_time.strftime("%H:%M")
        self.first_minute[key_open] = self.first_minute.get(key_open, 0) + 1
        key_close = self.last_bar.strftime("%H:%M")
        self.last_minute[key_close] = self.last_minute.get(key_close, 0) + 1

    def on_end_of_algorithm(self):
        self._close_session()

        full = self.sessions - len(self.short_sessions)
        checks = [
            ("bars streamed", self.bars > 600_000, f"{self.bars}"),
            ("sessions streamed", self.sessions > 1_600, f"{self.sessions}"),
            ("no short sessions", not self.short_sessions,
             f"{len(self.short_sessions)}: {', '.join(self.short_sessions[:6])}"),
            ("OHLC consistent", self.bad_ohlc == 0, f"{self.bad_ohlc} bad"),
            ("volume positive", self.zero_volume < self.bars * 0.01,
             f"{self.zero_volume} zero-volume bars"),
            ("session starts 09:31", self._dominant(self.first_minute) == "09:31",
             self._fmt(self.first_minute)),
            ("session ends 16:00", self._dominant(self.last_minute) == "16:00",
             self._fmt(self.last_minute)),
        ]
        passed = all(ok for _, ok, _ in checks)

        self.log("=" * 62)
        self.log("D-2 MINUTE DATA ACCEPTANCE")
        self.log(f"  range        {self.first_bar} .. {self.last_bar}")
        self.log(f"  sessions     {self.sessions} ({full} full)")
        self.log(f"  bars         {self.bars}  (mean {self.bars / max(self.sessions, 1):.1f}/session)")
        for name, ok, detail in checks:
            self.log(f"  [{'PASS' if ok else 'FAIL'}] {name:<22} {detail}")
        self.log(f"D-2 MINUTE DATA SMOKE: {'PASS' if passed else 'FAIL'}")
        self.log("=" * 62)

    @staticmethod
    def _dominant(counter):
        return max(counter, key=counter.get) if counter else None

    @staticmethod
    def _fmt(counter):
        top = sorted(counter.items(), key=lambda kv: -kv[1])[:3]
        return ", ".join(f"{k}x{v}" for k, v in top)
