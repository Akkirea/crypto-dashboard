# Crypto Market Dashboard

Read-only crypto market intelligence dashboard for Binance public market data.

Phase 1 intentionally contains no API keys, no private exchange clients, and no order placement code.

## Stack

- Backend: Python, FastAPI, asyncio, websockets, asyncpg
- Frontend: Next.js, TypeScript, TailwindCSS, TradingView lightweight-charts
- Local infra: Docker Compose, PostgreSQL

## Run Locally

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health
- Market health: http://localhost:8000/health/market-data

## Read-Only Boundary

This project only connects to Binance public WebSocket streams:

- trades
- best bid/ask
- 1m candles
- 5m candles

It does not load exchange credentials and does not implement execution, balances, accounts, or order placement.

## Local Development Without Docker

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install ".[dev]"
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```
