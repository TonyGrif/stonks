# stonks

Dockerized stock tracker. Reads a YAML config, fetches data via `yfinance` on per-ticker schedules, stores results in PostgreSQL.

## Stack

- **Scheduler**: APScheduler (embedded in app, one process)
- **Data source**: yfinance (Yahoo Finance, no API key needed)
- **Database**: PostgreSQL 16
- **Package manager**: uv (`pyproject.toml` + `uv.lock`)
- **Orchestration**: Docker Compose

## Running locally

```bash
cp .env.example .env   # fill in credentials
docker compose up
```

View live logs:
```bash
docker compose logs -f app
```

Log files are written to `logs/stonks.log` (daily rotation, 7-day retention).

## Adding or changing a ticker

Edit `config.yaml`, then restart the app container:
```bash
docker compose restart app
```

No rebuild needed — `config.yaml` is mounted as a volume.

## Trigger an immediate fetch on startup

In `config.yaml`, set `settings.run_on_startup: true`. All tickers will fetch once immediately when the app starts, before the schedule takes over. Useful for recovering missed data after downtime.

## Supported fields

| Field | Source |
|---|---|
| `open`, `high`, `low`, `close`, `volume` | `Ticker.history()` |
| `market_cap`, `pe_ratio`, `forward_pe`, `dividend_yield`, `beta`, `eps`, `52_week_high`, `52_week_low` | `Ticker.info` |
| `dividends` | `Ticker.dividends` |

## Database

Connect to query data:
```bash
docker compose exec postgres psql -U stocks -d stocks
SELECT symbol, fetched_at, field, value FROM prices ORDER BY fetched_at DESC LIMIT 20;
```

## Dependency management

```bash
# Add a dependency
uv add <package>

# Regenerate lockfile after editing pyproject.toml
uv lock
```

## Airflow migration path

When analysis/model-building workflows are needed:
1. Add Airflow containers to `docker-compose.yml`
2. Convert per-ticker APScheduler jobs → Airflow DAG `PythonOperator` tasks
3. `src/fetcher.py` and `src/db.py` are unchanged — they become task callables
4. APScheduler cron expressions map 1:1 to Airflow `CronTrigger`
