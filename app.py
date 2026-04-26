from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from plato.client import PlatoClient
from plato.exceptions import PlatoAPIError, PlatoAuthError, PlatoNotFoundError


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = PlatoClient()
    yield
    await app.state.client.aclose()


app = FastAPI(title="Plato Medical API Gateway", version="1.0.0", lifespan=lifespan)


def _client() -> PlatoClient:
    return app.state.client


def _http_error(exc: PlatoAPIError) -> HTTPException:
    if isinstance(exc, PlatoAuthError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, PlatoNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/calendars")
async def list_calendars():
    try:
        return await _client().get_calendars()
    except PlatoAPIError as exc:
        raise _http_error(exc)


@app.get("/slots")
async def get_slots(
    month: str,
    calendar_id: str = "LSG9",
    starttime: str = "09:00",
    endtime: str = "17:00",
    interval: int = 15,
):
    try:
        slots = await _client().get_available_slots(
            month=month,
            calendar_ids=[calendar_id],
            start_time=starttime,
            end_time=endtime,
            interval=interval,
        )
        return [dt.isoformat() for dt in slots]
    except PlatoAPIError as exc:
        raise _http_error(exc)


class BookBody(BaseModel):
    patient_id: str
    title: str
    description: str
    starttime: str
    endtime: str
    calendar_id: str = "LSG9"


@app.post("/book")
async def book_appointment(body: BookBody):
    try:
        return await _client().create_appointment(
            patient_id=body.patient_id,
            title=body.title,
            description=body.description,
            start_time=body.starttime,
            end_time=body.endtime,
            calendar_id=body.calendar_id,
        )
    except PlatoAPIError as exc:
        raise _http_error(exc)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
