# HidroSul Backend

Backend Python do HidroSul. A API normaliza dados públicos hidrológicos e meteorológicos e pode publicar alarmes por webhook.

## Fontes públicas

| Fonte | Uso | Autenticação |
|---|---|---|
| ONS | Dados hidráulicos de reservatórios | Dados abertos; sem chave |
| INMET | Observações meteorológicas por estação | Dados públicos |
| Open-Meteo | Previsão e precipitação por coordenadas | Sem chave |
| ANA/HidroWeb | Níveis e vazões históricas | Desativada: requer sessão/token |
| Sala de Situação do RS | Estações fluviais do estado | Desativada até haver uma fonte alternativa |
| SGB/CPRM | Hidrologia e hidrogeologia | Em breve: avaliar serviços e arquivos disponíveis |

## Diagnóstico das fontes

- `saladesituacao.rs.gov.br` deixou de resolver por DNS nesta infraestrutura. A aplicação não contém dados simulados como substituto.
- O endpoint atual do HidroWeb responde `401 Unauthorized`, portanto o consumo não funciona sem autenticação válida ou outro contrato público autorizado.
- INMET fornece dados meteorológicos, não níveis fluviais. Configure uma estação meteorológica separada; não use o código hidrológico da ANA.
- Open-Meteo está operacional e fornece previsão meteorológica por coordenadas.
- ONS está operacional para dados hidráulicos de reservatórios, mas não substitui a telemetria fluvial do Guaíba ou dos rios dos Sinos.
- Não há uma substituta aberta confirmada para as observações diárias/fluviais das estações ANA nesta configuração.

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
- `GET /api/v1/reservoirs`
- `GET /api/v1/reservoirs/{reservoir_code}/observations?days=7`
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
