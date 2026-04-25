from __future__ import annotations

from datetime import datetime
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
# get_available_slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_available_slots_parses_iso_strings(client: PlatoClient) -> None:
    respx.post(f"{BASE}/appointment/slots").mock(
        return_value=httpx.Response(
            200,
            json=["2026-09-15T09:00:00", "2026-09-15T09:15:00", "2026-09-15T09:30:00"],
        )
    )
    slots = await client.get_available_slots(month="Sep 2026", calendar_ids=["LSG9"])
    assert len(slots) == 3
    assert slots[0] == datetime(2026, 9, 15, 9, 0, 0)


@pytest.mark.asyncio
@respx.mock
async def test_get_available_slots_wrapped_response(client: PlatoClient) -> None:
    respx.post(f"{BASE}/appointment/slots").mock(
        return_value=httpx.Response(
            200, json={"slots": [{"datetime": "2026-09-15T09:00:00"}]}
        )
    )
    slots = await client.get_available_slots(month="Sep 2026", calendar_ids=["LSG9"])
    assert len(slots) == 1
    assert slots[0] == datetime(2026, 9, 15, 9, 0, 0)


@pytest.mark.asyncio
@respx.mock
async def test_get_available_slots_sends_correct_payload(client: PlatoClient) -> None:
    route = respx.post(f"{BASE}/appointment/slots").mock(
        return_value=httpx.Response(200, json=[])
    )
    await client.get_available_slots(
        month="Sep 2026",
        calendar_ids=["LSG9"],
        start_time="08:00",
        end_time="18:00",
        interval=30,
        simultaneous=2,
        min_days=2,
        max_days=60,
    )
    body = route.calls.last.request.content
    import json

    payload = json.loads(body)
    assert payload["month"] == "Sep 2026"
    assert payload["check_for_conflicts"] == ["LSG9"]
    assert payload["starttime"] == "08:00"
    assert payload["endtime"] == "18:00"
    assert payload["interval"] == 30
    assert payload["simultaneous"] == 2
    assert payload["min_days"] == 2
    assert payload["max_days"] == 60
    assert payload["type"] == "fixed"


@pytest.mark.asyncio
@respx.mock
async def test_get_available_slots_skips_unparseable(client: PlatoClient) -> None:
    respx.post(f"{BASE}/appointment/slots").mock(
        return_value=httpx.Response(200, json=["2026-09-15T09:00:00", "not-a-date"])
    )
    slots = await client.get_available_slots(month="Sep 2026", calendar_ids=["LSG9"])
    assert len(slots) == 1


# ---------------------------------------------------------------------------
# create_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_create_appointment_happy_path(client: PlatoClient) -> None:
    expected = {
        "id": "appt-123",
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
    appt = await client.create_appointment(
        patient_id="10CACFF1-9685-274C-A357-C4B20EBD369E",
        title="John Doe",
        description="Initial consult",
        start_time="2026-09-15 09:00:00",
        end_time="2026-09-15 09:15:00",
        calendar_id="LSG9",
    )
    assert appt.id == "appt-123"
    assert appt.color == "LSG9"


@pytest.mark.asyncio
@respx.mock
async def test_create_appointment_maps_calendar_id_to_color(client: PlatoClient) -> None:
    import json

    route = respx.post(f"{BASE}/appointment").mock(
        return_value=httpx.Response(200, json={"id": "x"})
    )
    await client.create_appointment(
        patient_id="pid",
        title="Jane",
        description="Checkup",
        start_time="2026-09-15 10:00:00",
        end_time="2026-09-15 10:30:00",
        calendar_id="AB3X",
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload["color"] == "AB3X"
    assert "calendar_id" not in payload


# ---------------------------------------------------------------------------
# Online booking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_online_booking_calendars(client: PlatoClient) -> None:
    respx.get(f"{BASE}/onlineapptbooking/list").mock(
        return_value=httpx.Response(200, json=[{"id": "OB1", "name": "Online Booking"}])
    )
    cals = await client.get_online_booking_calendars()
    assert len(cals) == 1
    assert cals[0].id == "OB1"


@pytest.mark.asyncio
@respx.mock
async def test_get_online_booking_slots(client: PlatoClient) -> None:
    respx.get(f"{BASE}/onlineapptbooking/slots").mock(
        return_value=httpx.Response(
            200, json=[{"datetime": "2026-09-15T09:00:00"}, {"datetime": "2026-09-15T09:15:00"}]
        )
    )
    slots = await client.get_online_booking_slots(calendar_id="OB1", month="2026-09")
    assert len(slots) == 2
    assert slots[0].datetime == "2026-09-15T09:00:00"


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
            calendar_id="LSG9",
        )
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_retries_on_429_then_succeeds(client: PlatoClient) -> None:
    route = respx.post(f"{BASE}/appointment/slots").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json=[]),
        ]
    )
    with patch("asyncio.sleep", new_callable=AsyncMock):
        slots = await client.get_available_slots(month="Sep 2026", calendar_ids=["LSG9"])
    assert slots == []
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
