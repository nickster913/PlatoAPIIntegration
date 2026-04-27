from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from plato.client import PlatoClient
from plato.config import PlatoSettings
from plato.exceptions import PlatoAPIError, PlatoAuthError, PlatoNotFoundError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_SETTINGS = PlatoSettings(
    base_url="https://test.platomedical.com/api",
    token="test-token",
    db_name="testdb",
)
BASE = "https://test.platomedical.com/api/testdb"


@pytest.fixture
def client() -> PlatoClient:
    return PlatoClient(settings=TEST_SETTINGS)


# ---------------------------------------------------------------------------
# get_calendars
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_calendars_returns_list(client: PlatoClient) -> None:
    respx.get(f"{BASE}/systemsetup").mock(
        return_value=httpx.Response(
            200,
            json=[{"color": "LSG9", "name": "Dr. Smith"}, {"color": "AB3X", "name": "Room 2"}],
        )
    )
    calendars = await client.get_calendars()
    assert len(calendars) == 2
    assert calendars[0].color == "LSG9"
    assert calendars[1].color == "AB3X"


@pytest.mark.asyncio
@respx.mock
async def test_get_calendars_wrapped_response(client: PlatoClient) -> None:
    respx.get(f"{BASE}/systemsetup").mock(
        return_value=httpx.Response(200, json={"calendars": [{"color": "LSG9"}]})
    )
    calendars = await client.get_calendars()
    assert calendars[0].color == "LSG9"


# ---------------------------------------------------------------------------
# get_appointments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_appointments_returns_list(client: PlatoClient) -> None:
    payload = [
        {"_id": "appt-1", "title": "John Doe", "starttime": "2026-09-15 09:00:00"},
        {"_id": "appt-2", "title": "Jane Smith", "starttime": "2026-09-15 10:00:00"},
    ]
    respx.get(f"{BASE}/appointment").mock(return_value=httpx.Response(200, json=payload))
    appointments = await client.get_appointments()
    assert len(appointments) == 2
    assert appointments[0]["_id"] == "appt-1"
    assert appointments[1]["title"] == "Jane Smith"


@pytest.mark.asyncio
@respx.mock
async def test_get_appointments_wrapped_response(client: PlatoClient) -> None:
    respx.get(f"{BASE}/appointment").mock(
        return_value=httpx.Response(200, json={"appointments": [{"_id": "appt-1"}]})
    )
    appointments = await client.get_appointments()
    assert len(appointments) == 1
    assert appointments[0]["_id"] == "appt-1"


# ---------------------------------------------------------------------------
# create_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_create_appointment_happy_path(client: PlatoClient) -> None:
    expected = {
        "_id": "appt-123",
        "patient_id": "10CACFF1-9685-274C-A357-C4B20EBD369E",
        "title": "John Doe",
        "description": "Initial consult",
        "starttime": "2026-09-15 09:00:00",
        "endtime": "2026-09-15 09:15:00",
        "color": "LSG9",
    }
    respx.post(f"{BASE}/appointment").mock(
        return_value=httpx.Response(200, json=expected)
    )
    result = await client.create_appointment(
        patient_id="10CACFF1-9685-274C-A357-C4B20EBD369E",
        title="John Doe",
        description="Initial consult",
        start_time="2026-09-15 09:00:00",
        end_time="2026-09-15 09:15:00",
        color="LSG9",
    )
    assert result["_id"] == "appt-123"
    assert result["color"] == "LSG9"


@pytest.mark.asyncio
@respx.mock
async def test_create_appointment_sends_color_in_payload(client: PlatoClient) -> None:
    import json

    route = respx.post(f"{BASE}/appointment").mock(
        return_value=httpx.Response(200, json={"_id": "x"})
    )
    await client.create_appointment(
        patient_id="pid",
        title="Jane",
        description="Checkup",
        start_time="2026-09-15 10:00:00",
        end_time="2026-09-15 10:30:00",
        color="AB3X",
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload["color"] == "AB3X"
    assert "calendar_id" not in payload


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_auth_error_on_401(client: PlatoClient) -> None:
    respx.get(f"{BASE}/systemsetup").mock(return_value=httpx.Response(401))
    with pytest.raises(PlatoAuthError) as exc_info:
        await client.get_calendars()
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
@respx.mock
async def test_auth_error_on_403(client: PlatoClient) -> None:
    respx.get(f"{BASE}/systemsetup").mock(return_value=httpx.Response(403))
    with pytest.raises(PlatoAuthError) as exc_info:
        await client.get_calendars()
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
@respx.mock
async def test_not_found_error_on_404(client: PlatoClient) -> None:
    respx.get(f"{BASE}/systemsetup").mock(return_value=httpx.Response(404))
    with pytest.raises(PlatoNotFoundError) as exc_info:
        await client.get_calendars()
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@respx.mock
async def test_api_error_on_400(client: PlatoClient) -> None:
    respx.post(f"{BASE}/appointment").mock(
        return_value=httpx.Response(400, json={"error": "Bad request"})
    )
    with pytest.raises(PlatoAPIError) as exc_info:
        await client.create_appointment(
            patient_id="p", title="t", description="d",
            start_time="2026-09-15 09:00:00", end_time="2026-09-15 09:15:00",
            color="LSG9",
        )
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_retries_on_429_then_succeeds(client: PlatoClient) -> None:
    route = respx.get(f"{BASE}/appointment").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json=[]),
        ]
    )
    with patch("asyncio.sleep", new_callable=AsyncMock):
        appointments = await client.get_appointments()
    assert appointments == []
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_retries_on_500_then_succeeds(client: PlatoClient) -> None:
    route = respx.get(f"{BASE}/systemsetup").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json=[{"color": "LSG9"}]),
        ]
    )
    with patch("asyncio.sleep", new_callable=AsyncMock):
        calendars = await client.get_calendars()
    assert len(calendars) == 1
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_raises_after_max_retries_exhausted(client: PlatoClient) -> None:
    respx.get(f"{BASE}/systemsetup").mock(return_value=httpx.Response(503))
    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(PlatoAPIError) as exc_info:
            await client.get_calendars()
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
@respx.mock
async def test_no_retry_on_auth_error(client: PlatoClient) -> None:
    route = respx.get(f"{BASE}/systemsetup").mock(return_value=httpx.Response(401))
    with pytest.raises(PlatoAuthError):
        await client.get_calendars()
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_network_error_retries(client: PlatoClient) -> None:
    route = respx.get(f"{BASE}/systemsetup").mock(
        side_effect=[
            httpx.ConnectError("connection refused"),
            httpx.ConnectError("connection refused"),
            httpx.Response(200, json=[{"color": "LSG9"}]),
        ]
    )
    with patch("asyncio.sleep", new_callable=AsyncMock):
        calendars = await client.get_calendars()
    assert calendars[0].color == "LSG9"
    assert route.call_count == 3
