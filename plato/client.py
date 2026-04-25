from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from .config import PlatoSettings, settings as default_settings
from .exceptions import PlatoAPIError, PlatoAuthError, PlatoNotFoundError
from .models import (
    Appointment,
    AppointmentRequest,
    Calendar,
    OnlineBookingCalendar,
    OnlineBookingSlot,
    SlotsRequest,
)

logger = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3


class PlatoClient:
    def __init__(self, settings: PlatoSettings | None = None) -> None:
        cfg = settings or default_settings
        self._base_url = cfg.base_url.rstrip("/")
        self._db = cfg.db_name
        self._http = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {cfg.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def __aenter__(self) -> PlatoClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._http.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{self._db}/{path.lstrip('/')}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = self._url(path)
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            if attempt > 0:
                wait = 2**attempt
                logger.warning(
                    "Retry %d/%d for %s %s (waiting %ds)",
                    attempt,
                    _MAX_RETRIES,
                    method,
                    url,
                    wait,
                )
                await asyncio.sleep(wait)

            try:
                response = await self._http.request(method, url, **kwargs)
            except httpx.RequestError as exc:
                last_error = PlatoAPIError(f"Network error: {exc}")
                logger.error("Request error for %s %s: %s", method, url, exc)
                continue

            if response.status_code in (401, 403):
                raise PlatoAuthError(
                    f"Authentication failed ({response.status_code})",
                    status_code=response.status_code,
                )
            if response.status_code == 404:
                raise PlatoNotFoundError(
                    f"Not found: {path}", status_code=404
                )
            if response.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                last_error = PlatoAPIError(
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )
                continue
            if response.status_code >= 400:
                raise PlatoAPIError(
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )

            logger.debug("%s %s -> %d", method, url, response.status_code)
            return response.json()

        raise last_error or PlatoAPIError(f"Request failed after {_MAX_RETRIES} retries")

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    async def get_calendars(self) -> list[Calendar]:
        """Fetch available calendars from system setup."""
        data = await self._request("GET", "systemsetup")
        raw: list[Any] = data if isinstance(data, list) else data.get("calendars", [data])
        return [Calendar.model_validate(c) for c in raw]

    async def get_available_slots(
        self,
        month: str,
        calendar_ids: list[str],
        start_time: str = "09:00",
        end_time: str = "17:00",
        interval: int = 15,
        simultaneous: int = 1,
        min_days: int = 1,
        max_days: int = 90,
    ) -> list[datetime]:
        """Return available appointment slots for the given month and calendars.

        Args:
            month: Month string in Plato format, e.g. "Sep 2026".
            calendar_ids: Calendar IDs to check for conflicts.
            start_time: Earliest slot time (HH:MM).
            end_time: Latest slot time (HH:MM).
            interval: Slot duration in minutes.
            simultaneous: Max overlapping appointments per slot.
            min_days: Minimum days ahead for booking.
            max_days: Maximum days ahead for booking.
        """
        payload = SlotsRequest(
            month=month,
            check_for_conflicts=calendar_ids,
            starttime=start_time,
            endtime=end_time,
            interval=interval,
            simultaneous=simultaneous,
            min_days=min_days,
            max_days=max_days,
        )
        data = await self._request("POST", "appointment/slots", json=payload.model_dump())
        raw: list[Any] = data if isinstance(data, list) else data.get("slots", [])

        result: list[datetime] = []
        for slot in raw:
            raw_str = (
                slot
                if isinstance(slot, str)
                else (slot.get("datetime") or slot.get("time") or str(slot))
            )
            try:
                result.append(datetime.fromisoformat(raw_str))
            except (ValueError, TypeError):
                logger.warning("Could not parse slot datetime: %r", raw_str)
        return result

    async def create_appointment(
        self,
        patient_id: str,
        title: str,
        description: str,
        start_time: str,
        end_time: str,
        calendar_id: str,
    ) -> Appointment:
        """Book an appointment into a calendar.

        Args:
            patient_id: Patient UUID.
            title: Appointment title (typically patient name).
            description: Appointment description / procedure.
            start_time: Start datetime string "YYYY-MM-DD HH:MM:SS".
            end_time: End datetime string "YYYY-MM-DD HH:MM:SS".
            calendar_id: Calendar ID (mapped to Plato's 'color' field).
        """
        payload = AppointmentRequest(
            patient_id=patient_id,
            title=title,
            description=description,
            starttime=start_time,
            endtime=end_time,
            color=calendar_id,
        )
        data = await self._request("POST", "appointment", json=payload.model_dump())
        return Appointment.model_validate(data)

    async def get_online_booking_calendars(self) -> list[OnlineBookingCalendar]:
        """List calendars available for online booking."""
        data = await self._request("GET", "onlineapptbooking/list")
        raw: list[Any] = data if isinstance(data, list) else data.get("calendars", [data])
        return [OnlineBookingCalendar.model_validate(c) for c in raw]

    async def get_online_booking_slots(
        self,
        calendar_id: str,
        month: str,
    ) -> list[OnlineBookingSlot]:
        """Get available slots for an online booking calendar.

        Args:
            calendar_id: Calendar to query.
            month: Month in YYYY-MM format.
        """
        data = await self._request(
            "GET",
            "onlineapptbooking/slots",
            params={"calendar_id": calendar_id, "month": month},
        )
        raw: list[Any] = data if isinstance(data, list) else data.get("slots", [data])
        return [OnlineBookingSlot.model_validate(s) for s in raw]
