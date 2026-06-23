# stonks

A Dockerized stock tracker that fetches data from Yahoo Finance on configurable per-ticker schedules and stores it in PostgreSQL.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Compose

## Setup

```bash
git clone <repo-url> && cd stonks
cp .env.example .env
```

Edit `.env` with your database credentials:

```dotenv
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=stocks
POSTGRES_USER=stocks
POSTGRES_PASSWORD=yourpassword
```

## Starting the tracker

```bash
docker compose up -d
```

This starts two containers:

| Container | Role |
|---|---|
| `stonks-postgres-1` | PostgreSQL 16 database |
| `stonks-app-1` | Python scheduler (fetches + stores data) |

Watch live output:

```bash
docker compose logs -f app
```

## Configuration

All tickers and schedules are controlled by `config.yaml`. Changes take effect after restarting the app container — no rebuild needed.

```yaml
settings:
  run_on_startup: false   # set true to fetch all tickers immediately on start

tickers:
  - symbol: AAPL
    schedule: "0 16 * * 1-5"       # cron expression — market close, weekdays
    fields: [open, high, low, close, volume, market_cap, pe_ratio]

  - symbol: SPY
    schedule: "*/30 9-16 * * 1-5"  # every 30 min during market hours
    fields: [open, high, low, close, volume]
```

**Adding a ticker:**

1. Add an entry to `config.yaml`
2. `docker compose restart app`

**Supported fields:**

| Field | Source |
|---|---|
| `open`, `high`, `low`, `close`, `volume` | Daily OHLCV via `Ticker.history()` |
| `market_cap`, `pe_ratio`, `forward_pe`, `dividend_yield`, `beta`, `eps`, `52_week_high`, `52_week_low` | Fundamentals via `Ticker.info` |
| `dividends` | Most recent dividend via `Ticker.dividends` |

**`run_on_startup`:** When set to `true`, all tickers fetch once immediately when the app starts before handing off to the schedule. Useful for recovering data after downtime.

## Viewing data

Open a SQL prompt against the running database:

```bash
docker compose exec postgres psql -U stocks -d stocks
```

**Most recent fetch per ticker:**

```sql
SELECT symbol, fetched_at, field, value
FROM prices
ORDER BY fetched_at DESC
LIMIT 50;
```

**Latest close price per ticker:**

```sql
SELECT symbol, MAX(fetched_at) AS fetched_at, value AS close
FROM prices
WHERE field = 'close'
GROUP BY symbol, value
ORDER BY symbol;
```

**All data for a specific ticker:**

```sql
SELECT fetched_at, field, value
FROM prices
WHERE symbol = 'AAPL'
ORDER BY fetched_at DESC, field;
```

**Field history over time:**

```sql
SELECT fetched_at, value
FROM prices
WHERE symbol = 'AAPL' AND field = 'close'
ORDER BY fetched_at DESC;
```

## Running tests

Tests run against a separate `stocks_test` database spun up automatically:

```bash
docker compose --profile test run --rm test
```

## Stopping the tracker

Stop containers without removing data:

```bash
docker compose down
```

## Deleting everything

Remove containers **and** the database volume (all stored data is permanently deleted):

```bash
docker compose down -v
```

To also remove the built images:

```bash
docker compose down -v --rmi all
```
