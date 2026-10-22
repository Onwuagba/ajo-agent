import time


class Clock:
    """Wall clock with an offset so the demo and the tests can move time without sleeping. Values are epoch milliseconds."""

    def __init__(self, start_ms: int | None = None):
        self._fixed = start_ms
        self._offset = 0

    def now(self) -> int:
        return (self._fixed if self._fixed is not None else int(time.time() * 1000)) + self._offset

    def advance(self, minutes: float = 0, hours: float = 0, days: float = 0) -> int:
        self._offset += int((minutes * 60 + hours * 3600 + days * 86400) * 1000)
        return self.now()

    def set(self, ms: int) -> None:
        """Freeze the clock at an exact instant (demo and tests)."""
        self._fixed, self._offset = ms, 0
