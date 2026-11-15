FROM python:3.12-slim AS base
WORKDIR /app
COPY backend /app/backend
COPY examples /app/examples
COPY .kiro/steering /app/.kiro/steering
RUN pip install --no-cache-dir -e "/app/backend[web,mcp]" uvicorn
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "revenant.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
