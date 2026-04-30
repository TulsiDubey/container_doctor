#!/bin/bash
# 🧪 Container Doctor: Chaos Simulation Suite
# Use this script to validate the Sentinel system's response to infrastructure failures.

echo "🩺 Starting Chaos Simulation for Container Doctor..."

function simulate_crash() {
    echo "🚨 Simulating Container Crash: 'api'..."
    docker kill api
}

function simulate_oom() {
    echo "📉 Simulating Memory Pressure: 'web'..."
    # In a real OOM, the kernel kills it. We'll inject a fake log signature.
    docker exec -it dashboard_api python3 -c "from shared.db import SessionLocal, Event; from datetime import datetime; db=SessionLocal(); e=Event(container='web', event_type='diagnosis', details={'root_cause': 'Memory Leak / OOM', 'severity': 'high', 'suggested_fix': 'docker restart web', 'is_diagnosable': 'true'}); db.add(e); db.commit(); print('OOM Event Injected.')"
}

function simulate_log_error() {
    echo "📝 Injecting Segmentation Fault log into 'api'..."
    # We'll use the log ingestor's Kafka topic directly if possible, or just kill with specific exit code
    docker stop api
    docker run --name api_fail --rm nginx sh -c "echo 'Segmentation fault (core dumped)' && exit 139"
}

function simulate_kafka_lag() {
    echo "⏳ Simulating Kafka Latency..."
    # Pause the processor to let logs accumulate
    docker pause incident_processor
    sleep 5
    echo "Resuming processor to observe batch handling..."
    docker unpause incident_processor
}

echo "1) Simulate Container Crash"
echo "2) Simulate OOM (Event Injection)"
echo "3) Simulate Log Error (Segfault)"
echo "4) Simulate Kafka Lag"
echo "q) Quit"

read -p "Select a failure mode: " choice

case $choice in
    1) simulate_crash ;;
    2) simulate_oom ;;
    3) simulate_log_error ;;
    4) simulate_kafka_lag ;;
    q) exit 0 ;;
    *) echo "Invalid choice." ;;
esac

echo "✅ Chaos Injection Complete. Check the Dashboard for reaction."
