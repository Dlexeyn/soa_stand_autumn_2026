"""Исходящие события (transactional outbox)."""
import threading
import time

from .breaker import Breaker
from .clients import EventBusClient
from .http_client import NET_ERRORS
from .settings import Settings
from .store import Store
from .util import backoff, log


def enqueue_order_paid(run, order_id, now):
    """Поставить событие order.paid в очередь."""
    run(
        "INSERT INTO outbox (event_id, order_id, occurred_at, next_attempt_at, created_at)"
        " VALUES (?,?,?,?,?) ON CONFLICT (event_id) DO NOTHING",
        ("evt-paid-" + order_id, order_id, now, now, now),
    )


class OutboxPublisher:
    def __init__(self, settings: Settings, store: Store, bus: EventBusClient):
        self.s = settings
        self.store = store
        self.bus = bus
        self.breaker = Breaker(settings)
        self.sem = threading.BoundedSemaphore(settings.bus_concurrency)
        self.inflight = set()
        self.lock = threading.Lock()

    def loop(self):
        while True:
            time.sleep(self.s.tick)
            try:
                if not self.breaker.can_try():
                    continue
                rows = self.store.execute(
                    "SELECT event_id, order_id, occurred_at FROM outbox"
                    " WHERE sent=0 AND next_attempt_at<=? ORDER BY created_at LIMIT 64",
                    (time.time(),), "all",
                )
                for row in rows:
                    with self.lock:
                        if row[0] in self.inflight:
                            continue
                        self.inflight.add(row[0])
                    threading.Thread(target=self.publish_one, args=(row,), daemon=True).start()
            except Exception as e:
                log("publish loop error", repr(e))

    def publish_one(self, row):
        eid, oid, occurred = row
        try:
            if not self.sem.acquire(blocking=False):
                return
            try:
                if not self.breaker.allow():
                    return
                try:
                    st, _ = self.bus.publish_order_paid(eid, oid, occurred)
                except NET_ERRORS:
                    self.breaker.failure(net=True)
                    self._retry_later(eid)
                    return
                if 200 <= st < 300:
                    self.breaker.success()
                    # Упадём до этого UPDATE — событие уйдёт ещё раз с тем же id: ок.
                    self.store.execute("UPDATE outbox SET sent=1 WHERE event_id=?", (eid,))
                else:
                    self.breaker.failure(net=True)
                    self._retry_later(eid)
            finally:
                self.sem.release()
        except Exception as e:
            log("publish error", eid, repr(e))
        finally:
            with self.lock:
                self.inflight.discard(eid)

    def _retry_later(self, eid):
        self.store.execute(
            "UPDATE outbox SET attempts=attempts+1, next_attempt_at=? WHERE event_id=?",
            (time.time() + backoff(1), eid),
        )
