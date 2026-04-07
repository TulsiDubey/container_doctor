FROM python:3.12-slim

WORKDIR /app

# Install build deps for confluent-kafka and sentence-transformers
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    cmake \
    python3-dev \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/incident_processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model for the RAG layer
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy shared code (must use context and relative path or bind mount)
# In CI/CD, we'd copy common utils, but here we'll 
# copy the entire context and use python -m or PYTHONPATH.
COPY services/incident_processor/ ./services/incident_processor/
COPY shared/ ./shared/
COPY rules/ ./rules/

ENV PYTHONPATH=/app
CMD ["python", "services/incident_processor/engine.py"]
