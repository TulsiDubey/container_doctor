#!/bin/bash
# --- CONTAINER DOCTOR LOCAL DEV LAUNCHER ---

# 🛡️ Reliability Watchdog: Kill orphaned microservices
echo "🧹 Cleaning up existing services..."
pkill -9 -f "python3 services/log_ingestor" || true
pkill -9 -f "python3 services/incident_processor" || true
pkill -9 -f "python3 services/dashboard_api" || true
sleep 2

export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export DATABASE_URL=postgresql://tulsi1:Tulsi%402211@localhost:5433/mydb
export OLLAMA_HOST=http://localhost:11434
export TARGET_CONTAINERS=web,api,db
export GEMINI_API_KEY=AIzaSyCwuSsPomoqGACzm8t4HH_BgFOdd3KoI0Y
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Ensure virtualenv is active or deps are installed
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

echo "🚀 Starting Microservices in LOCAL mode..."

# Launch Ingestor
python3 services/log_ingestor/main.py > log_ingestor.log 2>&1 &
echo "✔ Log Ingestor started (Background)"

# Launch Processor
python3 services/incident_processor/engine.py > incident_processor.log 2>&1 &
echo "✔ Incident Processor started (Background)"

# Launch Dashboard API
python3 services/dashboard_api/app.py > dashboard_api.log 2>&1 &
echo "✔ Dashboard API started (Background)"

echo "---"
echo "Dashboard: http://localhost:8080"
echo "Logs saved to *.log files. Use CTRL+C to stop all services."

# Trap for cleanup
trap "kill 0" EXIT
wait
