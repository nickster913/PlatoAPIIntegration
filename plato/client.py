from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import PlatoSettings, settings as default_settings
from .exceptions import PlatoAPIError, PlatoAuthError, PlatoNotFoundError
from .models import AppointmentRequest, Calendar

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
            # 10s to establish connection, 60s to receive response
            timeout=httpx.Timeout(60.0, connect=10.0),
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
            except httpx.TimeoutException as exc:
                # Don't retry timeouts — Plato is slow; retrying just multiplies the wait
                logger.error("Timeout calling %s %s after attempt %d: %s", method, url, attempt + 1, exc)
                raise PlatoAPIError(f"Plato API timed out ({method} {url})", status_code=504)
            except httpx.RequestError as exc:
                last_error = PlatoAPIError(f"Network error: {exc}")
                logger.error("Network error for %s %s: %s", method, url, exc)
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
                logger.warning(
                    "HTTP %d from Plato (attempt %d), retrying: %s",
                    response.status_code, attempt + 1, response.text[:200],
                )
                last_error = PlatoAPIError(
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )
                continue
            if response.status_code >= 400:
                logger.error(
                    "HTTP %d from Plato %s %s: %s",
                    response.status_code, method, url, response.text[:500],
                )
                raise PlatoAPIError(
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )

            logger.info("%s %s -> %d", method, url, response.status_code)
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

    async def get_appointments(self, **params: Any) -> list[dict[str, Any]]:
        """Fetch existing appointments from Plato."""
        data = await self._request("GET", "appointment", params=params or None)
        raw: list[Any] = data if isinstance(data, list) else data.get("appointments", [data])
        return raw

    async def create_appointment(
        self,
        patient_id: str,
        title: str,
        description: str,
        start_time: str,
        end_time: str,
        color: str,
    ) -> dict[str, Any]:
        """Book an appointment into a calendar.

        Args:
            patient_id: Patient UUID.
            title: Appointment title (typically patient name).
            description: Appointment description / procedure.
            start_time: Start datetime string "YYYY-MM-DD HH:MM:SS".
            end_time: End datetime string "YYYY-MM-DD HH:MM:SS".
            color: Calendar ID (Plato's field name for calendar).
        """
        payload = AppointmentRequest(
            patient_id=patient_id,
            title=title,
            description=description,
            starttime=start_time,
            endtime=end_time,
            color=color,
        )
        return await self._request("POST", "appointment", json=payload.model_dump())
