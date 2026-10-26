"""Клиенты соседних сервисов. Возвращают (status, body); при сетевой ошибке бросают
исключение из NET_ERRORS."""
from datetime import datetime, timezone
from urllib.parse import quote

from .http_client import http_call
from .settings import Settings


class PaymentClient:
    def __init__(self, s: Settings):
        self.base = s.payment_url
        self.timeout =  s.pay_timeout

    def get_charges(self, order_id):
        """GET /payments?order_id=12345"""
        return http_call(self.base, "GET", "/payments?order_id=" + quote(order_id, safe=""),
                         timeout=self.timeout)

    def charge(self, order_id, amount_cents):
        """POST /payments. order_id - Idempotency-Key."""
        return http_call(
            self.base, "POST", "/payments",
            {"order_id": order_id, "amount_cents": amount_cents, "currency": "RUB"},
            headers={"Idempotency-Key": order_id}, timeout=self.timeout,
        )


class InventoryClient:
    def __init__(self, s: Settings):
        self.base = s.inventory_url
        self.timeout = s.inv_timeout

    def reserve(self, order_id, items):
        return http_call(self.base, "POST", "/reservations",
                         {"order_id": order_id, "items": items}, timeout=self.timeout)

    def release(self, order_id):
        return http_call(self.base, "DELETE", "/reservations/" + quote(order_id, safe=""),
                         timeout=self.timeout)


class EventBusClient:
    def __init__(self, s: Settings):
        self.base = s.events_url
        self.timeout = s.bus_timeout

    def publish_order_paid(self, event_id, order_id, occurred_at):
        """POST /events"""
        return http_call(
            self.base, "POST", "/events",
            {"id": event_id, "type": "order.paid", "order_id": order_id,
             "occurred_at": datetime.fromtimestamp(occurred_at, timezone.utc)
             .strftime("%Y-%m-%dT%H:%M:%SZ")},
            timeout=self.timeout,
        )
