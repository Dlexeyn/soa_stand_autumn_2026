"""DDL: схема базы Orders"""

SCHEMA = [
    # orders
    """CREATE TABLE IF NOT EXISTS orders (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        items           TEXT NOT NULL,
        amount_cents    BIGINT NOT NULL,
        status          TEXT NOT NULL,            -- pending | paid | rejected
        stage           TEXT NOT NULL,            -- new | reserved | declined | done
        attempts        INTEGER NOT NULL DEFAULT 0,
        pay_sent        INTEGER NOT NULL DEFAULT 0, -- запрос на оплату уходил (исход мог быть неизвестен)
        charge_id       TEXT,
        next_attempt_at DOUBLE PRECISION NOT NULL,
        created_at      DOUBLE PRECISION NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS orders_due ON orders (status, next_attempt_at)",
    # outbox
    """CREATE TABLE IF NOT EXISTS outbox (
        event_id        TEXT PRIMARY KEY,
        order_id        TEXT NOT NULL,
        occurred_at     DOUBLE PRECISION NOT NULL,
        sent            INTEGER NOT NULL DEFAULT 0,
        attempts        INTEGER NOT NULL DEFAULT 0,
        next_attempt_at DOUBLE PRECISION NOT NULL,
        created_at      DOUBLE PRECISION NOT NULL
    )""",
    # outbox_due, индекс нужен для поиска событий, которые пора отправлять (sent=0 и next_attempt_at <= now)
    "CREATE INDEX IF NOT EXISTS outbox_due ON outbox (sent, next_attempt_at)",
    """CREATE TABLE IF NOT EXISTS processed_events (
        event_id   TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL,
        points     BIGINT NOT NULL,
        created_at DOUBLE PRECISION NOT NULL
    )""",
    # bonus
    """CREATE TABLE IF NOT EXISTS bonus (
        user_id TEXT PRIMARY KEY,
        points  BIGINT NOT NULL
    )""",
]
