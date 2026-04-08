# 🩺 Container Doctor: Enterprise AI-Sentinel & Observability Suite

**Container Doctor** is a production-grade, autonomous observability and auto-healing platform. It transforms fragmented container telemetry into a high-fidelity diagnostic stream, leveraging **Groq-Powered Llama-3 Reasoning**, **Persistent Learning RAG**, and **Real-time Dead Letter Queues (DLQ)** to secure distributed Docker clusters.

---

## 🏗️ 1. Architecture: The Autonomous Sentinel

The platform is built on a **Decoupled, Event-Driven Microservices Architecture**, optimized for high-throughput log ingestion and high-reasoning diagnostic loops.

### 🛰️ sensory Layer: Log Ingestor
- **Tech Stack**: Python 3.12, Docker SDK, Threading.
- **Logic**: A non-invasive probe mounting `/var/run/docker.sock`. It spawns parallel telemetry threads for every targeted container.
- **Telemetry Extraction**: Captures raw `stdout/stderr` and 64-bit precision resource stats (`cpu_delta`, `memory_usage_mb`, `blkio_read/write`).
- **Precision Loop**: Pushes JSON metadata to Kafka every 2s, ensuring 100% data fidelity for the dashboard.

### 🎡 Messaging Backbone: Kafka KRaft
- **Tech Stack**: Confluent Kafka (KRaft Mode).
- **Zookeeper-Free**: Optimized for low-latency message routing and simpler infrastructure management.
- **Topics & Partitioning**:
    - `container-logs`: Diagnostic ingestion.
    - `container-metrics`: Precision telemetry.
    - `container-dead-letters`: Escalation queue for undiagnosable AI incidents.

### 🧠 Reasoning Engine: Incident Processor
- **Tech Stack**: Groq Llama-3.1, Ollama, PGVector (HNSW Indexing).
- **Intelligence Tiers**:
    1.  **Rule Engine (Regex)**: Fast-path pattern matching for known critical signatures.
    2.  **Learning RAG (0ms Logic)**: Queries historical fixes in PGVector. If similarity > 85%, resolves instantly via "Recalled Memory".
    3.  **Deep Reasoning (Groq)**: Uses Llama-3.1-70B for high-fidelity failure analysis.
    4.  **Learning Logic**: Every validated Groq resolution is automatically vectorized and saved to RAG memory for future zero-latency recall.

---

## 🛠️ 2. High-Precision Telemetry Specifications

| Metric | Specification | Rationale |
| :--- | :--- | :--- |
| **CPU Usage** | Floating Point (%) | Captures sub-percent cycles to identify subtle thermal throttling. |
| **Memory** | Float (MB) | Precise allocation tracking to predict OOM (Out of Memory) hits. |
| **Disk I/O** | Float (MB R/W) | Identifies storage bottlenecks and silent write failures. |
| **Confidence** | Integer (%) | Quantifies AI reasoning certainty (DLQ trigger at < 85%). |

---

## 🛡️ 3. Security & Resilience Policies

### 🔐 Stateless Identity (JWT)
All Dashboard API endpoints (`/stats`, `/projects`, `/logs`) are protected by **RS256 JWT Authentication**. Tokens are issued on secure login and validated at the edge.

### 🛑 Stability Shield (Circuit Breaker)
The `RecoveryManager` prevents "Restart Storms" by:
- Enforcing a **5-minute cooldown** between remediation attempts.
- Requiring **Confidence > 85%** for automated restarts.
- Auto-escalating to the **DLQ** if the problem persists after remediation.

---

## 📜 4. Enterprise API Portal

For manual testing and DevOps integration, refer to the **[ENDPOINTS.md](file:///home/tulsi/container-doctor/ENDPOINTS.md)** portal. Key routes include:
- `GET /stats`: Aggregated Health & Latest Incident Hit.
- `GET /history?filter=dlq`: Access the Dead Letter Queue.
- `GET /diagnostics/<container>`: Deep AI Forensics Payload.

---

## 🚀 5. Deployment & Configuration

### 🔑 Environment Matrix
| Variable | Description | Value Requirement |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | High-speed AI Reasoning | gsk_A6... (Llama-3 Access) |
| `SLACK_WEBHOOK_URL` | Critical Alert Broadcast | Active Webhook URL |
| `DATABASE_URL` | Persistent Event Ledger | PostgreSQL w/ PGVector |

### 🛠️ Execution
```bash
# 1. Purge zombie port locks
fuser -k 8080/tcp

# 2. Ignite the cluster
docker compose up -d --build
```

---

*© 2026 Container Doctor - The Autonomous Observer for the Modern Cloud.*
