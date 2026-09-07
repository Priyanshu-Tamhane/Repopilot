FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY api ./api
COPY agents ./agents
COPY retrieval ./retrieval
COPY inference ./inference
COPY execution ./execution
COPY evaluation ./evaluation
COPY observability ./observability

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
