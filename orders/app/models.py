"""
Описание моделей pydentic для схемы контракта
"""

from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
    StrictInt,
    StringConstraints,
    model_validator,
)

INT64_MAX = 2**63 - 1
MAX_AMOUNT_CENTS = 2**62

PositiveInt = Annotated[StrictInt, Field(ge=1, le=INT64_MAX)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0, le=INT64_MAX)]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class Status(str, Enum):
    paid = "paid"
    rejected = "rejected"
    pending = "pending"


class Item(BaseModel):
    sku: NonEmptyStr
    qty: PositiveInt
    price_cents: NonNegativeInt


class OrderRequest(BaseModel):
    user_id: NonEmptyStr
    items: Annotated[list[Item], Field(min_length=1)]

    def amount_cents(self) -> int:
        return sum(it.qty * it.price_cents for it in self.items)

    @model_validator(mode="after")
    def _check_amount(self) -> "OrderRequest":
        total = self.amount_cents()
        if not (1 <= total <= MAX_AMOUNT_CENTS):
            raise ValueError("amount_cents out of allowed range")
        return self


class OrderCreated(BaseModel):
    id: str
    status: Status


class Order(BaseModel):
    id: str
    status: Status
    amount_cents: int


class Bonus(BaseModel):
    points: Annotated[StrictInt, Field(ge=0)]


class DeliveryConfirmed(BaseModel):
    id: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    user_id: NonEmptyStr
    bonus_points: PositiveInt