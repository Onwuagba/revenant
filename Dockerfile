# Stage 1: build the console (React + Vite).
FROM node:20-slim AS console
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: API (FastAPI) + the built console served from the same origin.
FROM python:3.12-slim AS base
WORKDIR /app
COPY backend /app/backend
COPY examples /app/examples
COPY .kiro/steering /app/.kiro/steering
RUN pip install --no-cache-dir -e "/app/backend[web,mcp]" uvicorn
COPY --from=console /web/dist /app/console
ENV PYTHONPATH=/app \
    REVENANT_CONSOLE_DIR=/app/console \
    REVENANT_DATABASE_URL=sqlite+pysqlite:////tmp/revenant.db
EXPOSE 8000
# Render sets $PORT; default 8000 elsewhere (docker compose keeps working behind Caddy).
CMD ["sh", "-c", "uvicorn revenant.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
