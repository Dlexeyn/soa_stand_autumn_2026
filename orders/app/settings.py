"""Конфигурация из переменных окружения"""
import os
from dataclasses import dataclass


def _f(name, default):
    return float(os.environ.get(name, default))


def _url(name, default):
    return os.environ.get(name, default).rstrip("/")


@dataclass(frozen=True)
class Settings:
    # контракт со стендом
    port: int = 8080
    database_url: str = ""
    payment_url: str = "http://mocks:8080"
    inventory_url: str = "http://mocks:8080"
    events_url: str = "http://mocks:8080"

    # время ответа
    # Сколько POST /orders ждёт исхода заказа до ответа `pending` (лимит — 1 c).
    response_budget: float = 0.7

    # Payment / Inventory
    # Таймаут вызова Payment должен быть больше самой долгой «медленной» оплаты (S3: 2 c)
    pay_timeout: float = 8.0
    inv_timeout: float = 3.0
    # Не больше стольких одновременных запросов к Payment.
    pay_concurrency: int = 8

    # шина событий
    bus_timeout: float = 3.0
    bus_concurrency: int = 8

    # circuit breaker
    breaker_threshold: int = 5
    breaker_base: float = 1.0
    breaker_max: float = 8.0
    # Вес ответа 5xx относительно сетевого сбоя (1.0): 5 / 0.34 ≈ 15 подряд.
    http_err_weight: float = 0.34

    # фоновые циклы
    # Задержка первого фонового захвата заказа (пока его ведёт обработчик POST).
    first_pickup_delay: float = 1.0
    tick: float = 0.2

    # хранение служебных записей (секунды)
    outbox_sent_ttl: float = 3600
    processed_ttl: float = 7 * 86400

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            port=int(os.environ.get("PORT", d.port)),
            database_url=os.environ.get("DATABASE_URL", d.database_url),
            payment_url=_url("PAYMENT_URL", d.payment_url),
            inventory_url=_url("INVENTORY_URL", d.inventory_url),
            events_url=_url("EVENTS_URL", d.events_url),
            response_budget=_f("RESPONSE_BUDGET", d.response_budget),
            pay_timeout=_f("PAY_TIMEOUT", d.pay_timeout),
            inv_timeout=_f("INV_TIMEOUT", d.inv_timeout),
            pay_concurrency=int(_f("PAY_CONCURRENCY", d.pay_concurrency)),
            bus_timeout=_f("BUS_TIMEOUT", d.bus_timeout),
            bus_concurrency=int(_f("BUS_CONCURRENCY", d.bus_concurrency)),
            breaker_threshold=int(_f("BREAKER_THRESHOLD", d.breaker_threshold)),
            breaker_base=_f("BREAKER_BASE", d.breaker_base),
            breaker_max=_f("BREAKER_MAX", d.breaker_max),
            http_err_weight=_f("HTTP_ERR_WEIGHT", d.http_err_weight),
            outbox_sent_ttl=_f("OUTBOX_SENT_TTL", d.outbox_sent_ttl),
            processed_ttl=_f("PROCESSED_TTL", d.processed_ttl),
        )
