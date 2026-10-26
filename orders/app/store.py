"""Хранилище: одно соединение с Postgres"""
import threading
import psycopg

from .schema import SCHEMA


class Store:
    def __init__(self, url):
        self.url = url
        self.lock = threading.Lock()
        self.conn = None

    def _connect(self):
        self.conn = psycopg.connect(self.url, autocommit=True, connect_timeout=5)

    def execute(self, sql, params=(), fetch=None):
        sql = sql.replace("?", "%s")
        with self.lock:
            for attempt in (0, 1):
                try:
                    if self.conn is None:
                        self._connect()
                    cur = self.conn.execute(sql, params)
                    if fetch == "one":
                        return cur.fetchone()
                    if fetch == "all":
                        return cur.fetchall()
                    return cur.rowcount
                except Exception:
                    try:
                        if self.conn is not None:
                            self.conn.close()
                    except Exception:
                        pass
                    self.conn = None
                    if attempt == 1:
                        raise

    def transaction(self, fn):
        """fn(run) выполняется в одной транзакции; run(sql, params) -> rowcount.
        Исключение внутри fn откатывает всё."""
        with self.lock:
            for attempt in (0, 1):
                try:
                    if self.conn is None:
                        self._connect()
                    conn = self.conn
                    with conn.transaction():
                        return fn(
                            lambda sql, params=(): conn.execute(sql.replace("?", "%s"), params).rowcount
                        )
                except Exception:
                    try:
                        if self.conn is not None:
                            self.conn.close()
                    except Exception:
                        pass
                    self.conn = None
                    if attempt == 1:
                        raise

    def init_schema(self):
        for stmt in SCHEMA:
            self.execute(stmt)
