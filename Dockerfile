# ---- UI build ---------------------------------------------------------------------------
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- API + static UI ----------------------------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.lock backend/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r backend/requirements.lock
COPY backend/app backend/app
COPY inputs inputs
COPY --from=ui /ui/dist frontend/dist
RUN useradd --system --uid 10001 app && mkdir -p /data && chown app /data
USER app
ENV DATABASE_PATH=/data/assistant.sqlite3 \
    KNOWLEDGE_PATH=/app/inputs/knowledge.md \
    WORK_ORDERS_PATH=/app/inputs/work_orders.json \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn", "--factory", "app.main:app_factory", "--host", "0.0.0.0", "--port", "8000"]
