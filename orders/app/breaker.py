"""Circuit breaker: не даёт заваливать недоступного соседа запросами."""
import threading
import time

from .settings import Settings

class Breaker:
    """closed -> (N неудач подряд) -> open -> (пауза) -> half-open (1 проба)."""

    CLOSED, OPEN, HALF = "closed", "open", "half"

    def __init__(self, settings: Settings):
        self.s = settings
        self.lock = threading.Lock()
        self.state = self.CLOSED
        self.fails = 0.0
        self.open_until = 0.0
        self.cooldown = settings.breaker_base
        self.probing = False

    def can_try(self):
        with self.lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN:
                return time.time() >= self.open_until
            return not self.probing

    def allow(self):
        with self.lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN:
                if time.time() >= self.open_until:
                    self.state = self.HALF
                    self.probing = True
                    return True
                return False
            if not self.probing:
                self.probing = True
                return True
            return False

    def success(self):
        with self.lock:
            self.state = self.CLOSED
            self.fails = 0.0
            self.cooldown = self.s.breaker_base
            self.probing = False

    def failure(self, net=True):
        with self.lock:
            if self.state == self.CLOSED:
                self.fails += 1.0 if net else self.s.http_err_weight
                if self.fails >= self.s.breaker_threshold:
                    self.state = self.OPEN
                    self.open_until = time.time() + self.cooldown
            elif self.state == self.HALF:
                if net:
                    self.cooldown = min(self.cooldown * 2, self.s.breaker_max)
                self.state = self.OPEN
                self.open_until = time.time() + self.cooldown
                self.probing = False
            # state == OPEN: запоздавший ответ старого запроса — игнорируем
