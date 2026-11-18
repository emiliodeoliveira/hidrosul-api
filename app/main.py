import os
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.models import AlarmTest, ForecastResponse, Observation, Station
from app.providers import (
    HydrowebProvider,
    InmetProvider,
    OpenMeteoProvider,
    SalaRsProvider,
)

app = FastAPI(
    title="HidroSul API",
    version="0.1.0",
    description="API normalizada para monitoramento hidrológico do Rio Grande do Sul.",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("HIDROSUL_CORS_ORIGINS", "http://localhost:4200").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

STATIONS = [
    Station(
        code="87242000",
        name="Guaíba",
        basin="Guaíba",
        river="Rio Guaíba",
        latitude=-30.0346,
        longitude=-51.2177,
        warning_level_m=3.0,
    ),
    Station(
        code="87380000",
        name="Campo Bom",
        basin="Rio dos Sinos",
        river="Rio dos Sinos",
        latitude=-29.6789,
        longitude=-51.0608,
    ),
    Station(
        code="87382000",
        name="São Leopoldo",
        basin="Rio dos Sinos",
        river="Rio dos Sinos",
        latitude=-29.7601,
        longitude=-51.1469,
    ),
]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "hidrosul-backend"}


@app.get("/api/v1/sources")
async def sources() -> dict[str, list[str]]:
    return {
        "sources": [
            "ana-hidroweb",
            "sala-rs",
            "inmet",
            "open-meteo",
        ]
    }


@app.get("/api/v1/stations", response_model=list[Station])
async def stations() -> list[Station]:
    return STATIONS


@app.get("/api/v1/stations/{station_code}/observations", response_model=list[Observation])
async def observations(
    station_code: str,
    days: int = Query(default=7, ge=1, le=365),
    source: Literal["auto", "ana-hidroweb", "sala-rs", "inmet"] = "auto",
) -> list[Observation]:
    providers = {
        "sala-rs": SalaRsProvider(),
        "ana-hidroweb": HydrowebProvider(),
        "inmet": InmetProvider(),
    }

    order = list(providers) if source == "auto" else [source]
    errors = []
    for provider_name in order:
        try:
            items = await providers[provider_name].observations(station_code, days)
            if items:
                return [Observation.model_validate(item) for item in items]
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"{provider_name}: {type(exc).__name__}")

    if errors:
        raise HTTPException(
            status_code=502,
            detail=f"Dados indisponíveis nas fontes configuradas ({'; '.join(errors)})",
        )
    raise HTTPException(status_code=404, detail="Nenhuma observação encontrada")


@app.get("/api/v1/weather/forecast", response_model=ForecastResponse)
async def weather_forecast(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    days: int = Query(default=7, ge=1, le=16),
) -> ForecastResponse:
    try:
        payload = await OpenMeteoProvider().forecast(latitude, longitude, days)
        return ForecastResponse.model_validate(payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Previsão meteorológica indisponível") from exc


@app.post("/api/v1/alarms/test")
async def alarm_test(alarm: AlarmTest) -> dict[str, str | bool]:
    webhook_url = os.getenv("ALARM_WEBHOOK_URL")
    if not webhook_url:
        return {"published": False, "message": "ALARM_WEBHOOK_URL não configurada"}

    payload = {
        "event": "hidrosul_alarm_test",
        "station_code": alarm.station_code,
        "level_m": alarm.level_m,
        "message": f"Alarme de teste: estação {alarm.station_code} atingiu {alarm.level_m:.2f} m",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
    return {"published": True, "message": "Alarme enviado"}
