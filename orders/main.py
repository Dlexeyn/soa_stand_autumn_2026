import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.app import Application
from app.settings import Settings
from app.util import log
from app.models import OrderCreated, OrderRequest, Order, DeliveryConfirmed, Bonus

settings = Settings.from_env()
container = Application(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=64))
    await asyncio.to_thread(container.wait_for_db)
    container.start_background()
    log("orders ready on", settings.port)
    yield


app = FastAPI(title="Orders", lifespan=lifespan)


def err(code, msg) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=code)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # для возврата 400 вместо 422 (по умолчанию в pydentic)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": "Некорректное тело запроса",
            "errors": exc.errors()
        },
    )


@app.post("/orders", status_code=201, response_model=OrderCreated)
async def create_order(order: OrderRequest):
    try:
        oid, status = await container.orders.place_order(
            order.user_id, [it.model_dump() for it in order.items], order.amount_cents()
        )
    except Exception as e:  # бд недоступна
        log("place order error", repr(e))
        return err(503, "unavailable")
    return {"id": oid, "status": status}


@app.get("/orders/{order_id}", response_model=Order)
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
async def delivery_webhook(event: DeliveryConfirmed):
    try:
        applied = await asyncio.to_thread(
            container.bonus.apply_delivery,
            event.id,
            event.user_id,
            event.bonus_points
        )
    except Exception as e:  # не удалось сохранить — не подтверждаем, шина пришлёт снова
        log("delivery error", repr(e))
        return err(503, "unavailable")
    return {"status": "ok", "applied": applied}


@app.get("/users/{user_id}/bonus", response_model=Bonus)
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
