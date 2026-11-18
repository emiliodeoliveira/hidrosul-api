from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Observation(BaseModel):
    station_code: str
    timestamp: datetime
    level_m: float | None = None
    discharge_m3s: float | None = None
    source: str


class Station(BaseModel):
    code: str
    name: str
    basin: str
    river: str
    latitude: float
    longitude: float
    warning_level_m: float | None = None


class Forecast(BaseModel):
    time: datetime
    temperature_c: float | None = None
    precipitation_mm: float | None = None
    precipitation_probability_percent: float | None = None


class ForecastResponse(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    hourly: list[Forecast]
    source: Literal["open-meteo"] = "open-meteo"


class AlarmTest(BaseModel):
    station_code: str = Field(min_length=1)
    level_m: float = Field(ge=0)
