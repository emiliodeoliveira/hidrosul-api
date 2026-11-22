import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.models import AlertSubscription, AlarmTest, ForecastResponse, Observation, Station
from app.providers import (
    HydrowebProvider,
    InmetProvider,
    OpenMeteoProvider,
    OnsProvider,
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
            "open-meteo",
            "ons",
            "inmet",
        ],
        "hydrological_fallback": [],
        "reservoirs": ["ons"],
        "meteorological": ["inmet", "open-meteo"],
        "status": [
            "open-meteo: operacional",
            "ons: dados abertos de reservatórios; não substitui telemetria fluvial",
            "inmet: dados meteorológicos por estação",
            "ana-hidroweb: desativada até a configuração de token",
            "sala-rs: desativada até disponibilização de uma fonte alternativa",
        ],
    }


@app.get("/api/v1/stations", response_model=list[Station])
async def stations() -> list[Station]:
    return STATIONS


@app.get("/api/v1/reservoirs")
async def reservoirs() -> list[dict[str, str]]:
    try:
        return await OnsProvider().reservoirs()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Dados do ONS indisponíveis") from exc


@app.get("/api/v1/reservoirs/{reservoir_code}/observations", response_model=list[Observation])
async def reservoir_observations(
    reservoir_code: str,
    days: int = Query(default=7, ge=1, le=365),
) -> list[Observation]:
    try:
        items = await OnsProvider().observations(reservoir_code, days)
        if items:
            return [Observation.model_validate(item) for item in items]
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Dados do ONS indisponíveis") from exc
    raise HTTPException(status_code=404, detail="Nenhuma observação encontrada")


@app.get("/api/v1/stations/{station_code}/observations", response_model=list[Observation])
async def observations(
    station_code: str,
    days: int = Query(default=7, ge=1, le=365),
    source: Literal["disabled"] = "disabled",
) -> list[Observation]:
    raise HTTPException(
        status_code=503,
        detail="Telemetria fluvial desativada: ANA/HidroWeb requer token e nenhuma fonte alternativa foi configurada",
    )


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


@app.get("/api/v1/weather/observations")
async def weather_observations(
    station_code: str = Query(default="A801"),
    days: int = Query(default=7, ge=1, le=365),
) -> list[dict[str, str | float | None]]:
    try:
        items = await InmetProvider().observations(station_code, days)
        if items:
            return items
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Observações meteorológicas do INMET indisponíveis") from exc
    raise HTTPException(status_code=404, detail="Nenhuma observação meteorológica encontrada")


@app.post("/api/v1/alerts/subscriptions")
async def subscribe_alert(subscription: AlertSubscription) -> dict[str, str | bool]:
    email = subscription.email.strip() if subscription.email else ""
    phone = subscription.phone.strip() if subscription.phone else ""
    if not email and not phone:
        raise HTTPException(
            status_code=422,
            detail="Informe um e-mail ou telefone.",
        )

    storage_path = Path(
        os.getenv("HIDROSUL_SUBSCRIPTION_FILE", "subscriptions.json")
    )
    subscriptions = []
    if storage_path.exists():
        try:
            subscriptions = json.loads(storage_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            subscriptions = []

    record = subscription.model_dump(mode="json")
    record["email"] = email or None
    record["phone"] = phone or None
    record["created_at"] = datetime.now(timezone.utc).isoformat()

    for existing in subscriptions:
        if (
            existing.get("city") == subscription.city
            and (existing.get("email") == email or existing.get("phone") == phone)
            and existing.get("condition") == subscription.condition
        ):
            return {
                "subscribed": True,
                "message": f"Inscrição já cadastrada para {subscription.city}.",
            }

    subscriptions.append(record)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(
        json.dumps(subscriptions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "subscribed": True,
        "message": f"Inscrição criada para {subscription.city}.",
    }


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
