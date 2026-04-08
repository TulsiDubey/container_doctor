FROM python:3.12-slim

WORKDIR /app

# Removed apt-get block to bypass unstable network dependencies.
# Using binary wheels for confluent-kafka and docker SDK.

COPY services/log_ingestor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/log_ingestor/ ./services/log_ingestor/

CMD ["python", "services/log_ingestor/main.py"]
