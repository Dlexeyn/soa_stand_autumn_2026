"""Сервис заказов: асинхронный приём POST /orders.
    1. new order -> reserved -> paid
    2. new order -> reserved -> declined -> rejected (если банк отказал, резерв снят)
"""
import asyncio
import json
import threading
import time
import uuid

from .breaker import Breaker
from .clients import InventoryClient, PaymentClient
from .http_client import NET_ERRORS
from .outbox import enqueue_order_paid
from .settings import Settings
from .store import Store
from .util import backoff, log

COLS = "id, user_id, items, amount_cents, status, stage, attempts, pay_sent, charge_id"
COL_NAMES = COLS.replace(" ", "").split(",")


class OrderService:
    def __init__(self, settings: Settings, store: Store, payment: PaymentClient, inventory: InventoryClient):
        self.s = settings
        self.store = store
        self.payment = payment
        self.inventory = inventory
        self.breaker = Breaker(settings)
        self.pay_sem = threading.BoundedSemaphore(settings.pay_concurrency)
        self.ilock = threading.Lock()
        self.inflight = set()    # заказы, которые прямо сейчас ведёт какой-то поток
        self.waiters = {}        # order_id -> (event loop, asyncio.Event) для POST /orders

    def load(self, oid):
        r = self.store.execute(f"SELECT {COLS} FROM orders WHERE id=?", (oid,), "one")
        return None if r is None else dict(zip(COL_NAMES, r))

    def create(self, user_id, items, amount):
        oid = str(uuid.uuid4())
        now = time.time()
        self.store.execute(
            "INSERT INTO orders (id, user_id, items, amount_cents, status, stage,"
            " next_attempt_at, created_at) VALUES (?,?,?,?,'pending','new',?,?)",
            (oid, user_id, json.dumps(items), amount, now + self.s.first_pickup_delay, now),
        )
        return oid

    def set_stage(self, o, stage):
        self.store.execute("UPDATE orders SET stage=? WHERE id=?", (stage, o["id"]))
        o["stage"] = stage

    def finish(self, o, status, charge_id):
        """Терминальный статус"""
        now = time.time()

        def work(run):
            n = run(
                "UPDATE orders SET status=?, stage='done', charge_id=? WHERE id=? AND status='pending'",
                (status, charge_id, o["id"]),
            )
            if n and status == "paid":
                enqueue_order_paid(run, o["id"], now)

        self.store.transaction(work)
        o["status"] = status

    def retry_later(self, o):
        o["attempts"] += 1
        self.store.execute(
            "UPDATE orders SET attempts=?, next_attempt_at=? WHERE id=?",
            (o["attempts"], time.time() + backoff(o["attempts"]), o["id"]),
        )

    # вызовы соседей
    def reserve(self, o):
        items = [{"sku": i["sku"], "qty": i["qty"]} for i in json.loads(o["items"])]
        try:
            st, _ = self.inventory.reserve(o["id"], items)
            return st in (200, 201)
        except NET_ERRORS:
            return False

    def release(self, o):
        try:
            st, _ = self.inventory.release(o["id"])
            return 200 <= st < 300
        except NET_ERRORS:
            return False

    def pay(self, o):
        """Возвращает ('paid', charge_id) | ('declined', None) | ('failed', None) | ('denied', None)

        denied — вызов не делали (нет слота или breaker открыт), заказ ничем не «наказан».
        """
        if not self.pay_sem.acquire(blocking=False):
            return "denied", None
        try:
            if not self.breaker.allow():
                return "denied", None
            try:
                # Раньше уже слали запрос на оплату, а исход не знаем (таймаут /
                # обрыв / 5xx): сначала спрашиваем банк, нет ли списания.
                if o["pay_sent"]:
                    st, raw = self.payment.get_charges(o["id"])
                    if st != 200:
                        self.breaker.failure(net=False)
                        return "failed", None
                    for c in json.loads(raw):
                        if c.get("status") == "captured":
                            self.breaker.success()
                            return "paid", c.get("charge_id")
                    # списания нет — можно (повторно) отправлять запрос на оплату
                else:
                    # Фиксируем намерение ДО отправки: если сервис упадёт посреди
                    # запроса, после рестарта мы будем знать, что исход неизвестен.
                    self.store.execute("UPDATE orders SET pay_sent=1 WHERE id=?", (o["id"],))
                    o["pay_sent"] = 1

                st, raw = self.payment.charge(o["id"], o["amount_cents"])
                if st in (200, 201):
                    self.breaker.success()
                    try:
                        return "paid", json.loads(raw).get("charge_id")
                    except ValueError:
                        return "paid", None
                if st == 402:
                    self.breaker.success()  # банк жив, просто отказал
                    return "declined", None
                self.breaker.failure(net=False)
                return "failed", None
            except NET_ERRORS:
                self.breaker.failure(net=True)
                return "failed", None
        finally:
            self.pay_sem.release()

    def step(self, oid):
        o = self.load(oid)
        if o is None or o["status"] != "pending":
            return
        while True:
            stage = o["stage"]
            if stage == "new":
                if not self.reserve(o):
                    self.retry_later(o)
                    return
                self.set_stage(o, "reserved")
            elif stage == "reserved":
                kind, charge = self.pay(o)
                if kind == "paid":
                    self.finish(o, "paid", charge)
                    return
                if kind == "declined":
                    # Банк отказал: деньги не взяты. Дальше — снять резерв.
                    self.set_stage(o, "declined")
                    continue
                if kind == "failed":
                    self.retry_later(o)
                return  # failed / denied
            elif stage == "declined":
                if not self.release(o):
                    self.retry_later(o)
                    return
                self.finish(o, "rejected", None)
                return
            else:
                return

    def run(self, oid):
        with self.ilock:
            if oid in self.inflight:
                return
            self.inflight.add(oid)
        try:
            self.step(oid)
        except Exception as e:  # заказ подберёт диспетчер
            log("step error", oid, repr(e))
        finally:
            with self.ilock:
                self.inflight.discard(oid)
            w = self.waiters.pop(oid, None)
            if w is not None:
                loop, ev = w
                try:
                    loop.call_soon_threadsafe(ev.set)
                except RuntimeError:  # цикл событий уже закрыт
                    pass

    def spawn(self, oid):
        threading.Thread(target=self.run, args=(oid,), daemon=True).start()

    def dispatch_loop(self):
        """Дожимает заказы, до которых не дошёл обработчик POST (ошибки соседей, рестарт)."""
        while True:
            time.sleep(self.s.tick)
            try:
                sql = "SELECT id FROM orders WHERE status='pending' AND next_attempt_at<=?"
                if not self.breaker.can_try():
                    # банк «лежит» — не трогаем заказы, ждущие оплаты
                    sql += " AND stage<>'reserved'"
                # Сначала заказы, по которым оплата уже уходила
                sql += " ORDER BY pay_sent DESC, next_attempt_at LIMIT 64"
                for (oid,) in self.store.execute(sql, (time.time(),), "all"):
                    with self.ilock:
                        busy = oid in self.inflight
                    if not busy:
                        self.spawn(oid)
            except Exception as e:
                log("dispatch error", repr(e))

    # API
    async def place_order(self, user_id, items, amount):
        """Записать заказ и подождать исход не дольше response_budget; иначе — pending."""
        loop = asyncio.get_running_loop()
        oid = await asyncio.to_thread(self.create, user_id, items, amount)
        ev = asyncio.Event()
        self.waiters[oid] = (loop, ev)
        self.spawn(oid)
        try:
            await asyncio.wait_for(ev.wait(), self.s.response_budget)
        except asyncio.TimeoutError:
            pass
        self.waiters.pop(oid, None)
        o = await asyncio.to_thread(self.load, oid)
        return oid, (o["status"] if o else "pending")
