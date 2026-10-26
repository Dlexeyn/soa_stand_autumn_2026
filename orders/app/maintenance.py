"""Уборка служебных таблиц"""
import time

from .settings import Settings
from .store import Store
from .util import log


def cleanup_loop(settings: Settings, store: Store, period: float = 60.0):
    """Раз в `period` секунд:
    - outbox: удалить уже отправленные события старше outbox_sent_ttl;
    - processed_events: удалить записи старше processed_ttl (шина повторяет доставку,
      пока не получит 2xx, поэтому по истечении такого срока ключ дедупликации не нужен).
    """
    while True:
        time.sleep(period)
        try:
            now = time.time()
            store.execute("DELETE FROM outbox WHERE sent=1 AND created_at<?",
                          (now - settings.outbox_sent_ttl,))
            store.execute("DELETE FROM processed_events WHERE created_at<?",
                          (now - settings.processed_ttl,))
        except Exception as e:
            log("cleanup error", repr(e))
