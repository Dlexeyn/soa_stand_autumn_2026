"""Orders: HTTP-слой на FastAPI. Логика — в пакете app/ (сборка — app/app.py).

Тела запросов разбираем сами (без pydantic-модели), потому что контракт требует
`400` на некорректное тело, а FastAPI по умолчанию отвечает `422`.
@TODO: Переопределить RequestValidationError для pydentic
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.app import Application
from app.settings import Settings
from app.util import log
from app.validation import parse_delivery, parse_order

settings = Settings.from_env()
container = Application(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=64))
    # /healthz начнёт отвечать только после создания схемы: сервер не принимает
    # соединения, пока lifespan не дошёл до yield.
    await asyncio.to_thread(container.wait_for_db)
    container.start_background()
    log("orders ready on", settings.port)
    yield


app = FastAPI(title="Orders", lifespan=lifespan)


def err(code, msg):
    return JSONResponse({"error": msg}, status_code=code)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/orders")
async def create_order(request: Request):
    parsed = parse_order(await request.body())
    if parsed is None:
        return err(400, "bad_request")
    try:
        oid, status = await container.orders.place_order(*parsed)
    except Exception as e:  # бд недоступна
        log("place order error", repr(e))
        return err(503, "unavailable")
    return JSONResponse({"id": oid, "status": status}, status_code=201)


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    try:
        o = await asyncio.to_thread(container.orders.load, order_id)
    except Exception as e:
        log("get order error", repr(e))
        return err(503, "unavailable")
    if o is None:
        return err(404, "not_found")
    return {"id": o["id"], "status": o["status"], "amount_cents": o["amount_cents"]}


@app.post("/webhooks/delivery")
async def delivery_webhook(request: Request):
    parsed = parse_delivery(await request.body())
    if parsed is None:
        return err(400, "bad_request")
    try:
        applied = await asyncio.to_thread(container.bonus.apply_delivery, *parsed)
    except Exception as e:  # не удалось сохранить — не подтверждаем, шина пришлёт снова
        log("delivery error", repr(e))
        return err(503, "unavailable")
    return {"status": "ok", "applied": applied}


@app.get("/users/{user_id}/bonus")
async def get_bonus(user_id: str):
    try:
        points = await asyncio.to_thread(container.bonus.get_bonus, user_id)
    except Exception as e:
        log("bonus error", repr(e))
        return err(503, "unavailable")
    return {"points": points}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="warning",
                access_log=False, timeout_graceful_shutdown=2)
