import os
import secrets
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "data" / "kitchen.db")))
CAFE_TOKEN = os.getenv("CAFE_TOKEN", "local-demo-token")
RESTAURANT_ID = 1


@contextmanager
def database():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@asynccontextmanager
async def lifespan(app):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.execute("PRAGMA journal_mode = WAL")
        # Миграция повторно запускается безопасно, существующие заказы сохраняются.
        db.executescript((ROOT / "migrations" / "001_initial.sql").read_text())
    yield


app = FastAPI(title="Авито.Кухня", version="1.0.0", lifespan=lifespan)


class ItemInput(BaseModel):
    dish_id: int = Field(gt=0, strict=True)
    quantity: int = Field(gt=0, le=100, strict=True)


class OrderInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    customer_id: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=300)
    items: list[ItemInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_dishes(self):
        if len({item.dish_id for item in self.items}) != len(self.items):
            raise ValueError("Объедините одинаковые блюда в одну позицию")
        return self


class Dish(BaseModel):
    id: int
    restaurant_id: int
    name: str
    price_kopecks: int
    available: bool


class OrderItem(BaseModel):
    dish_id: int
    name: str
    price_kopecks: int
    quantity: int


class Order(BaseModel):
    id: str
    restaurant_id: int
    customer_id: str
    address: str
    status: str
    total_kopecks: int
    created_at: str
    items: list[OrderItem]


def cafe_access(x_cafe_token: Annotated[str, Header()] = ""):
    if not secrets.compare_digest(x_cafe_token.encode(), CAFE_TOKEN.encode()):
        raise HTTPException(401, "Неверный токен заведения")


def read_order(db, order_id):
    row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Заказ не найден")
    result = dict(row)
    result["items"] = [
        dict(item)
        for item in db.execute(
            "SELECT dish_id, name, price_kopecks, quantity FROM order_items WHERE order_id = ?",
            (order_id,),
        )
    ]
    return result


@app.get("/health")
def health():
    with database() as db:
        db.execute("SELECT 1 FROM restaurants LIMIT 1")
    return {"status": "ok"}


@app.get("/menu", response_model=list[Dish])
def menu():
    with database() as db:
        return [dict(row) for row in db.execute("SELECT * FROM dishes ORDER BY id")]


@app.post("/orders", response_model=Order, status_code=201)
def create_order(payload: OrderInput):
    order_id = str(uuid4())
    with database() as db:
        # Проверка меню и запись заказа происходят в одной транзакции.
        db.execute("BEGIN IMMEDIATE")
        items = []
        total = 0
        for item in payload.items:
            dish = db.execute("SELECT * FROM dishes WHERE id = ?", (item.dish_id,)).fetchone()
            if dish is None:
                raise HTTPException(404, f"Блюдо {item.dish_id} не найдено")
            if not dish["available"]:
                raise HTTPException(409, f"Блюдо {item.dish_id} временно недоступно")
            total += dish["price_kopecks"] * item.quantity
            items.append((order_id, dish["id"], dish["name"], dish["price_kopecks"], item.quantity))
        # Цена берётся из меню и фиксируется в заказе в целых копейках.
        db.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                order_id,
                RESTAURANT_ID,
                payload.customer_id,
                payload.address,
                "pending",
                total,
                datetime.now(UTC).isoformat(),
            ),
        )
        db.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", items)
        return read_order(db, order_id)


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    with database() as db:
        return read_order(db, order_id)


@app.get("/partner/orders", response_model=list[Order], dependencies=[Depends(cafe_access)])
def partner_orders(status: Annotated[str, Query(pattern="^(pending|accepted)$")] = "pending"):
    with database() as db:
        rows = db.execute(
            "SELECT id FROM orders WHERE restaurant_id = ? AND status = ? ORDER BY created_at",
            (RESTAURANT_ID, status),
        ).fetchall()
        return [read_order(db, row["id"]) for row in rows]


@app.post(
    "/partner/orders/{order_id}/accept", response_model=Order, dependencies=[Depends(cafe_access)]
)
def accept_order(order_id: str):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        order = read_order(db, order_id)
        if order["restaurant_id"] != RESTAURANT_ID:
            raise HTTPException(404, "Заказ не найден")
        # Повторное подтверждение возвращает тот же результат.
        db.execute("UPDATE orders SET status = 'accepted' WHERE id = ?", (order_id,))
        return read_order(db, order_id)
