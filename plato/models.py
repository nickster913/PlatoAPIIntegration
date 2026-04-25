from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Calendar(BaseModel):
    # Plato uses 'color' as the calendar identifier throughout the API
    color: str
    name: str | None = None
    model_config = ConfigDict(extra="allow")


class SlotsRequest(BaseModel):
    month: str
    check_for_conflicts: list[str]
    starttime: str
    endtime: str
    interval: int
    simultaneous: int
    min_days: int
    max_days: int
    type: str = "fixed"


class AppointmentRequest(BaseModel):
    patient_id: str
    title: str
    description: str
    starttime: str
    endtime: str
    color: str  # calendar ID — Plato's naming for this field


class Appointment(BaseModel):
    id: str | None = None
    patient_id: str | None = None
    title: str | None = None
    description: str | None = None
    starttime: str | None = None
    endtime: str | None = None
    color: str | None = None
    model_config = ConfigDict(extra="allow")


class OnlineBookingCalendar(BaseModel):
    id: str | None = None
    name: str | None = None
    model_config = ConfigDict(extra="allow")


class OnlineBookingSlot(BaseModel):
    datetime: str | None = None
    model_config = ConfigDict(extra="allow")
