from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Calendar(BaseModel):
    # Plato uses 'color' as the calendar identifier throughout the API
    color: str
    name: str | None = None
    model_config = ConfigDict(extra="allow")


class AppointmentRequest(BaseModel):
    patient_id: str = ""
    title: str
    description: str
    starttime: str
    endtime: str
    color: str  # calendar ID — Plato's naming for this field
