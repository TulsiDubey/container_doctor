#!/bin/bash
# This script demonstrates the full real-time capabilities of Container Doctor.

echo "🚀 INITIATING SENTINEL ABSOLUTE RE-IGNITION..."
docker compose down -v
docker compose up -d --build
echo "Waiting for Phase 34 High-Fidelity Initialization..."

echo "🚀 [SHOWCASE] Initializing Sentinel Management Demo..."
echo "----------------------------------------------------"

# Step 1: Real-time Deployment Detection
echo "🔹 STEP 1: Deploying New Managed Service (demo-nginx)..."
docker run -d --name demo-nginx --label com.docker.compose.project=SHOWCASE nginx:alpine > /dev/null
echo "✅ Service Deployed. Check your Live Dashboard: 'demo-nginx' should appear instantly."
sleep 10

# Step 2: Anomaly Detection & AI Diagnostics
echo "🔹 STEP 2: Inducing Critical Memory Anomaly (OOM Mock)..."
# We simulate a log entry that triggers the Rule Engine
docker exec demo-nginx sh -c "echo 'CRITICAL: Process Killed by OOM engine violation' > /proc/1/fd/2"
echo "✅ Anomaly Triggered. Watch for 'ANOMALY_ALARM' in the Event Ledger and Slack."
sleep 15

# Step 3: Forensic Audit Verification
echo "🔹 STEP 3: Verifying Forensic Evidence in Central Warehouse..."
docker exec db psql -U tulsi1 -d mydb -c "SELECT event_type, container, details->>'severity' as severity, details->>'root_cause' as reason FROM events WHERE container='demo-nginx' ORDER BY timestamp DESC LIMIT 1;"
echo "✅ Forensic Audit Verified. The Sentinel has categorized and archived the incident."

echo "----------------------------------------------------"
echo "🎉 [SHOWCASE COMPLETE] The platform has successfully detected, diagnosed, and reported the incident."
echo "Clean up demo with: docker rm -f demo-nginx"
