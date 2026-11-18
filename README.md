# HidroSul Backend

Backend Python do HidroSul. A API normaliza dados públicos hidrológicos e meteorológicos e pode publicar alarmes por webhook.

## Fontes públicas

| Fonte | Uso | Autenticação |
|---|---|---|
| ANA/HidroWeb | Níveis e vazões históricas | Pode exigir sessão/token dependendo do recurso |
| Sala de Situação do RS | Estações fluviais do estado | Pública; endpoint pode mudar |
| INMET | Observações meteorológicas por estação | Pública |
| Open-Meteo | Previsão e precipitação por coordenadas | Sem chave |

Esta aplicação não deve armazenar chaves em código. Configure variáveis de ambiente em `.env`.

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[test]"
```

## Execução

```bash
uvicorn app.main:app --reload --port 8000
```

Documentação: `http://localhost:8000/docs`

## API

- `GET /health`
- `GET /api/v1/sources`
- `GET /api/v1/stations`
- `GET /api/v1/stations/{station_code}/observations?days=7&source=auto`
- `GET /api/v1/weather/forecast?latitude=-30.0346&longitude=-51.2177&days=7`
- `POST /api/v1/alarms/test`

Resposta normalizada:

```json
{
  "station_code": "87242000",
  "timestamp": "2026-11-17T21:00:00-03:00",
  "level_m": 2.14,
  "source": "sala-rs"
}
```

## Docker

```bash
docker build -t hidrosul-backend .
docker run --env-file .env.example -p 8000:8000 hidrosul-backend
```
