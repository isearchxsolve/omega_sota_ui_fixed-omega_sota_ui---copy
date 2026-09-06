FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY omega_agent/ ./omega_agent/
COPY test_omega_sota.py .
COPY pyproject.toml .

RUN pip install -e .

RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV OMEGA_DATA_DIR=/app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "omega_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
