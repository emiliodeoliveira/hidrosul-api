import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class HydrowebProvider:
    name = "ana-hidroweb"

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "HIDROWEB_BASE_URL",
            "https://www.snirh.gov.br/hidroweb/rest/api",
        ).rstrip("/")

    async def observations(self, station_code: str, days: int) -> list[dict[str, Any]]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        url = f"{self.base_url}/documento/gerarTelemetricas"
        params = {
            "codigosEstacoes": station_code,
            "tipoArquivo": 2,
            "periodoInicial": start.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "periodoFinal": end.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

        data = response.json()
        if isinstance(data, dict):
            data = data.get("medicoes", data.get("observations", []))
        if not isinstance(data, list):
            return []

        normalized = []
        for item in data:
            timestamp = item.get("horDataHora") or item.get("timestamp") or item.get("date")
            level = item.get("horNivelAdotado")
            if timestamp is None or level is None:
                continue
            normalized.append({
                "station_code": str(station_code),
                "timestamp": timestamp,
                "level_m": float(level) / 100,
                "discharge_m3s": None,
                "source": self.name,
            })
        return normalized


class SalaRsProvider:
    name = "sala-rs"

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "SALA_RS_BASE_URL",
            "https://saladesituacao.rs.gov.br",
        ).rstrip("/")

    async def observations(self, station_code: str, days: int) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/station/ana/{station_code}"
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        payload = response.json()
        if isinstance(payload, dict):
            payload = payload.get("observations", payload.get("data", payload))
        if isinstance(payload, dict):
            payload = list(payload.values())
        if not isinstance(payload, list):
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        normalized = []
        for item in payload:
            timestamp = item.get("horDataHora") or item.get("timestamp") or item.get("date")
            level = item.get("horNivelAdotado")
            if timestamp is None or level is None:
                continue
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed < cutoff:
                continue
            normalized.append({
                "station_code": str(station_code),
                "timestamp": parsed.isoformat(),
                "level_m": float(level) / 100,
                "discharge_m3s": item.get("horVazao") if item.get("horVazao") is not None else None,
                "source": self.name,
            })
        return normalized


class InmetProvider:
    name = "inmet"

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "INMET_BASE_URL",
            "https://apitempo.inmet.gov.br",
        ).rstrip("/")

    async def observations(self, station_code: str, days: int) -> list[dict[str, Any]]:
        end = datetime.now().date()
        start = end - timedelta(days=days)
        url = f"{self.base_url}/estacao/dados/{station_code}"
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, list):
            return []

        normalized = []
        for item in payload:
            date_value = item.get("DT_MEDICAO") or item.get("data")
            hour_value = item.get("HR_MEDICAO") or item.get("hora") or "0000"
            if not date_value:
                continue
            date_text = str(date_value)
            hour_text = str(hour_value).zfill(4)
            timestamp = datetime.fromisoformat(
                f"{date_text}T{hour_text[:2]}:{hour_text[2:]}:00"
            )
            if timestamp.date() < start:
                continue
            normalized.append({
                "station_code": str(station_code),
                "timestamp": timestamp.isoformat(),
                "level_m": None,
                "discharge_m3s": None,
                "source": self.name,
            })
        return normalized


class OpenMeteoProvider:
    name = "open-meteo"

    async def forecast(
        self,
        latitude: float,
        longitude: float,
        days: int,
    ) -> dict[str, Any]:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,precipitation,precipitation_probability",
            "forecast_days": days,
            "timezone": "America/Sao_Paulo",
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
        payload = response.json()

        times = payload.get("hourly", {}).get("time", [])
        temperatures = payload.get("hourly", {}).get("temperature_2m", [])
        precipitation = payload.get("hourly", {}).get("precipitation", [])
        probabilities = payload.get("hourly", {}).get("precipitation_probability", [])
        hourly = []
        for index, time in enumerate(times):
            hourly.append({
                "time": datetime.fromisoformat(time).isoformat(),
                "temperature_c": temperatures[index] if index < len(temperatures) else None,
                "precipitation_mm": precipitation[index] if index < len(precipitation) else None,
                "precipitation_probability_percent": probabilities[index] if index < len(probabilities) else None,
            })

        return {
            "latitude": payload["latitude"],
            "longitude": payload["longitude"],
            "timezone": payload["timezone"],
            "hourly": hourly,
            "source": self.name,
        }
