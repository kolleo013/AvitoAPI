import os
import secrets
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
CAFE_TOKEN = os.getenv("CAFE_TOKEN", "local-demo-token")
app = FastAPI(title="Демо-кафе", version="1.0.0")


def cafe_access(x_cafe_token: Annotated[str, Header()] = ""):
    if not secrets.compare_digest(x_cafe_token.encode(), CAFE_TOKEN.encode()):
        raise HTTPException(401, "Неверный токен заведения")


async def kitchen_request(method, path):
    try:
        async with httpx.AsyncClient(base_url=API_URL, timeout=5) as client:
            response = await client.request(method, path, headers={"X-Cafe-Token": CAFE_TOKEN})
    except httpx.RequestError as error:
        raise HTTPException(503, "Основной сервис временно недоступен") from error
    if response.is_error:
        raise HTTPException(response.status_code, response.json().get("detail", "Ошибка API"))
    return response.json()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/orders", dependencies=[Depends(cafe_access)])
async def orders():
    return await kitchen_request("GET", "/partner/orders")


@app.post("/orders/{order_id}/accept", dependencies=[Depends(cafe_access)])
async def accept(order_id: str):
    return await kitchen_request("POST", f"/partner/orders/{order_id}/accept")
