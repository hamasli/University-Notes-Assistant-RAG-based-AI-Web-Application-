FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY README.md ./README.md

RUN uv venv && uv sync --no-dev

COPY app ./app
COPY data ./data

EXPOSE 8000


CMD [".venv/bin/fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]