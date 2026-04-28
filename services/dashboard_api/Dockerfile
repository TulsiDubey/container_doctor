FROM python:3.12-slim

WORKDIR /app

# Removed apt-get block to bypass unstable network dependencies. 
# Using binary wheels instead.

# Reuse shared requirements or create dashboard specific
COPY shared/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install flask flask-cors groq

COPY services/dashboard_api/ ./services/dashboard_api/
COPY shared/ ./shared/

ENV PYTHONPATH=/app
CMD ["python", "services/dashboard_api/app.py"]
