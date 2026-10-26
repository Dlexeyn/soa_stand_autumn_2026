"""Разбор и проверка тел запросов вместо pydentic. Контракт требует 400 на некорректное тело
(FastAPI/pydantic по умолчанию отвечал бы 422), поэтому разбираем вручную."""
import json


def parse_order(raw):
    """Возвращает {user_id, items, amount} или None, если тело некорректно."""
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    uid, items = d.get("user_id"), d.get("items")
    if not isinstance(uid, str) or not uid.strip():
        return None
    if not isinstance(items, list) or not items:
        return None
    amount, clean = 0, []
    for it in items:
        if not isinstance(it, dict):
            return None
        sku, qty, price = it.get("sku"), it.get("qty"), it.get("price_cents")
        if not isinstance(sku, str) or not sku.strip():
            return None
        if type(qty) is not int or qty < 1:
            return None
        if type(price) is not int or price < 0:
            return None
        amount += qty * price
        clean.append({"sku": sku, "qty": qty, "price_cents": price})
    if amount < 1 or amount > 2**62:
        return None
    return uid, clean, amount


def parse_delivery(raw):
    """Возвращает {event_id, user_id, points} | None (некорректное тело)."""
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    eid, uid, pts = d.get("id"), d.get("user_id"), d.get("bonus_points")
    if not isinstance(eid, str) or not eid or len(eid) > 256:
        return None
    if not isinstance(uid, str) or not uid:
        return None
    if type(pts) is not int or pts < 1:
        return None
    return eid, uid, pts
