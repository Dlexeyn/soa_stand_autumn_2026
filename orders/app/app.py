"""Сборка приложения: создаёт объекты, связывает зависимости, запускает фоновые циклы."""
import threading
import time

from .bonus import BonusService
from .clients import EventBusClient, InventoryClient, PaymentClient
from .maintenance import cleanup_loop
from .orders import OrderService
from .outbox import OutboxPublisher
from .settings import Settings
from .store import Store
from .util import log


class Application:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = Store(settings.database_url)
        self.orders = OrderService(
            settings, self.store, PaymentClient(settings), InventoryClient(settings)
        )
        self.publisher = OutboxPublisher(settings, self.store, EventBusClient(settings))
        self.bonus = BonusService(self.store)

    def wait_for_db(self, timeout=100):
        """Создание схемы"""
        deadline = time.time() + timeout
        while True:
            try:
                self.store.init_schema()
                return
            except Exception as e:
                if time.time() > deadline:
                    raise
                log("waiting for database:", repr(e))
                time.sleep(1)

    def start_background(self):
        for target in (
            self.orders.dispatch_loop,      # дожимает заказы
            self.publisher.loop,            # публикует события из outbox
            lambda: cleanup_loop(self.settings, self.store),
        ):
            threading.Thread(target=target, daemon=True).start()
