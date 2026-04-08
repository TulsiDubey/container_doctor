# 🩺 Container Doctor: Enterprise API Portal

This portal provides documentation for all available REST and Telemetry endpoints for manual testing and integration.

## 🔐 Identity & Authentication

All sensitive endpoints require a **JWT (JSON Web Token)** in the `Authorization` header.

### 1. Extraction (Terminal)
To get a valid token for `curl` testing:
```bash
TOKEN=$(curl -s -X POST -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password"}' \
  http://localhost:8080/api/login | jq -r .token)
echo $TOKEN
```

---

## 📊 Core Monitoring Endpoints

### 1. Fleet Stats (Overview)
**Endpoint**: `GET /stats`
**Description**: Aggregated health summary (Total, Tracked, Healthy, Broken).
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/stats
```

### 2. Project Explorer (Hierarchy)
**Endpoint**: `GET /projects`
**Description**: 360-degree container resource mapping with Disk I/O.
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/projects
```

### 3. Event Ledger (Audit Trail)
**Endpoint**: `GET /history`
**Description**: Recent infrastructure events, diagnoses, and remediation attempts.
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/history
```

---

## 🩺 AI & Diagnostics

### 1. Deep Analysis Payload
**Endpoint**: `GET /diagnostics/<container_name>`
**Description**: Retrieves the most recent AI-driven root cause and suggested fix.
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/diagnostics/api
```

### 2. Live Log Streaming
**Endpoint**: `GET /logs/<container_name>`
**Description**: Standardized JSON log stream for the dashboard.
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/logs/log_ingestor
```

---

## 📈 Platform Metrics (Prometheus Format)

**Endpoint**: `GET /metrics`
**Description**: OpenMetrics compatible telemetry for external scrapers.
```bash
curl http://localhost:8080/metrics
```

---

## 🛠️ Performance & Manual Verification

### 1. Verify Real-time Telemetry
Monitor the `log_ingestor` output to confirm Disk IO and CPU precision:
```bash
docker logs log_ingestor --tail 20
```

### 2. Verify AI Reasoning Path
Check the `incident_processor` logs for LLM tier selection (Local vs Cloud):
```bash
docker logs incident_processor --tail 30
```
