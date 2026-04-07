FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/log_ingestor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/log_ingestor/ ./services/log_ingestor/

CMD ["python", "services/log_ingestor/main.py"]
