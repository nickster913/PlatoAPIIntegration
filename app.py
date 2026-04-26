from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from plato.client import PlatoClient
from plato.exceptions import PlatoAPIError, PlatoAuthError, PlatoNotFoundError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = PlatoClient()
    logger.info("PlatoClient initialised (db=%s)", app.state.client._db)
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
    if exc.status_code == 504:
        return HTTPException(status_code=504, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/calendars")
async def list_calendars():
    try:
        return await _client().get_calendars()
    except PlatoAPIError as exc:
        logger.error("/calendars error: %s", exc)
        raise _http_error(exc)


@app.get("/slots")
async def get_slots(
    month: str,
    calendar_id: str = "LSG9",
    starttime: str = "09:00",
    endtime: str = "17:00",
    interval: int = 15,
):
    logger.info(
        "GET /slots month=%r calendar_id=%r starttime=%r endtime=%r interval=%r",
        month, calendar_id, starttime, endtime, interval,
    )
    try:
        slots = await _client().get_available_slots(
            month=month,
            calendar_ids=[calendar_id],
            start_time=starttime,
            end_time=endtime,
            interval=interval,
        )
        logger.info("GET /slots -> %d slots returned", len(slots))
        return [dt.isoformat() for dt in slots]
    except PlatoAPIError as exc:
        logger.error("GET /slots Plato error: %s", exc)
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
    logger.info(
        "POST /book patient_id=%r title=%r starttime=%r endtime=%r calendar_id=%r",
        body.patient_id, body.title, body.starttime, body.endtime, body.calendar_id,
    )
    try:
        result = await _client().create_appointment(
            patient_id=body.patient_id,
            title=body.title,
            description=body.description,
            start_time=body.starttime,
            end_time=body.endtime,
            calendar_id=body.calendar_id,
        )
        logger.info("POST /book -> success: %s", result)
        return result
    except PlatoAPIError as exc:
        logger.error("POST /book Plato error: %s", exc)
        raise _http_error(exc)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
