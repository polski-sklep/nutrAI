FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "aiogram>=3.13" "anthropic>=0.40" "asyncpg>=0.29" "apscheduler>=3.10" "pillow>=10.4"

COPY nutrai ./nutrai
COPY scripts ./scripts
COPY sql ./sql

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
CMD ["python", "-m", "nutrai.bot"]
