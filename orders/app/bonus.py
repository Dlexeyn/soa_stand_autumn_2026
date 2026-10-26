"""Бонусы."""
import time

from .store import Store

class BonusService:
    def __init__(self, store: Store):
        self.store = store

    def apply_delivery(self, event_id, user_id, points) -> bool:
        """Начислить бонусы ровно один раз на событие. True, если начислено сейчас."""
        def work(run):
            n = run(
                "INSERT INTO processed_events (event_id, user_id, points, created_at)"
                " VALUES (?,?,?,?) ON CONFLICT (event_id) DO NOTHING",
                (event_id, user_id, points, time.time()),
            )
            if n == 1:
                run(
                    "INSERT INTO bonus (user_id, points) VALUES (?,?)"
                    " ON CONFLICT (user_id) DO UPDATE SET points = bonus.points + excluded.points",
                    (user_id, points),
                )
            return n == 1

        return self.store.transaction(work)

    def get_bonus(self, user_id) -> int:
        r = self.store.execute("SELECT points FROM bonus WHERE user_id=?", (user_id,), "one")
        return int(r[0]) if r else 0
