FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Reuse shared requirements or create dashboard specific
COPY shared/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install flask flask-cors

COPY services/dashboard_api/ ./services/dashboard_api/
COPY dashboard.html .
COPY login.html .
COPY shared/ ./shared/

ENV PYTHONPATH=/app
CMD ["python", "services/dashboard_api/app.py"]
