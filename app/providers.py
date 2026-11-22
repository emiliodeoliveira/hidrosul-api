import os
import csv
import io
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


class OnsProvider:
    name = "ons"

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "ONS_BASE_URL",
            "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/dados_hidrologicos_di",
        ).rstrip("/")

    async def reservoirs(self) -> list[dict[str, Any]]:
        year = datetime.now().year
        url = f"{self.base_url}/DADOS_HIDROLOGICOS_RES_{year}.csv"
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        reader = csv.DictReader(io.StringIO(response.text), delimiter=";")
        reservoirs: dict[str, dict[str, Any]] = {}
        for item in reader:
            code = str(item.get("id_reservatorio", "")).strip()
            name = str(item.get("nom_reservatorio", "")).strip()
            if code and code not in reservoirs:
                reservoirs[code] = {
                    "code": code,
                    "name": name,
                    "basin": str(item.get("nom_bacia", "")).strip(),
                    "subsystem": str(item.get("nom_subsistema", "")).strip(),
                }
        return list(reservoirs.values())

    async def observations(self, reservoir_code: str, days: int) -> list[dict[str, Any]]:
        year = datetime.now().year
        url = f"{self.base_url}/DADOS_HIDROLOGICOS_RES_{year}.csv"
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        cutoff = datetime.now().date() - timedelta(days=days)
        normalized = []
        reader = csv.DictReader(io.StringIO(response.text), delimiter=";")
        for item in reader:
            if str(item.get("id_reservatorio", "")).strip() != reservoir_code:
                continue
            date_value = str(item.get("din_instante", "")).strip()
            level_value = str(item.get("val_nivelmontante", "")).strip()
            if not date_value or not level_value:
                continue
            observed_at = datetime.strptime(date_value, "%Y-%m-%d").date()
            if observed_at < cutoff:
                continue
            discharge_value = str(item.get("val_vazaodefluente", "")).strip()
            normalized.append({
                "station_code": reservoir_code,
                "timestamp": datetime.combine(observed_at, datetime.min.time()).isoformat(),
                "level_m": float(level_value.replace(",", ".")),
                "discharge_m3s": (
                    float(discharge_value.replace(",", "."))
                    if discharge_value
                    else None
                ),
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
        url = (
            f"{self.base_url}/estacao/dados/"
            f"{station_code}/{start.isoformat()}/{end.isoformat()}"
        )
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
