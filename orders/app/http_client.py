"""HTTP-клиент поверх http.client"""
import http.client
import json
from urllib.parse import urlsplit

# Всё, что означает «исход вызова неизвестен / соединения нет».
NET_ERRORS = (OSError, http.client.HTTPException, ValueError)


def http_call(base, method, path, body=None, headers=None, timeout=3.0):
    """Возвращает (status, raw_body). Бросает исключение из NET_ERRORS."""
    u = urlsplit(base)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
    try:
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        data = json.dumps(body).encode() if body is not None else None
        conn.request(method, (u.path.rstrip("/") + path), body=data, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, raw
    finally:
        conn.close()
