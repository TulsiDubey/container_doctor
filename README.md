# 🩺 Container Doctor: Enterprise AI-Sentinel & Observability Suite

**Container Doctor** is a production-grade, autonomous observability and self-healing platform designed for modern, high-density Docker environments. It transforms raw container telemetry into a high-reasoning diagnostic stream, leveraging **Groq-Powered Llama-3 Reasoning**, **Persistent Learning RAG Memory**, and **Kafka-native Event Sourcing** to detect, analyze, and resolve system failures with zero human intervention.

---

## 🏗️ 1. System Working Architecture

The platform is built on a **Decoupled 5-Layer Distributed Architecture**, ensuring that monitoring overhead is near-zero while diagnostic reasoning is senior-SRE level.

### 📊 Architectural Flow Diagram
```mermaid
graph TD
    subgraph "Host Infrastructure"
        DS[Docker Socket /var/run/docker.sock]
    end

    subgraph "Sentinel Layer (Log Ingestor)"
        LI[Log Ingestor Service]
        DS --> LI
        LI -- "Logs" --> K_LOGS[Kafka Topic: container-logs]
        LI -- "Stats" --> K_METRICS[Kafka Topic: container-metrics]
        LI -- "Events" --> K_LOGS
    end

    subgraph "Messaging Backbone (Event Ledger)"
        K[Kafka KRaft Cluster]
    end

    subgraph "Intelligence Layer (Incident Processor)"
        IP[Incident Processor]
        K_LOGS --> IP
        K_METRICS --> IP
        
        IP -- "1. Vector Search" --> DB_V[PGVector RAG Cache]
        IP -- "2. Reasoning" --> GROQ[Groq Cloud: Llama-3.1-8b]
        IP -- "3. Fallback" --> OLLAMA[Local Ollama: Mistral]
        
        IP -- "Remediation" --> RM[Remediation Manager]
        RM -- "Fix Action" --> DS
    end

    subgraph "Persistence Layer"
        DB[(PostgreSQL 15)]
        IP --> DB
        DB_V -.-> DB
    end

    subgraph "Presentation Layer"
        API[Dashboard API Flask]
        D[Web Dashboard UI - Chart.js]
        API --> DB
        API --> DS
        D <--> API
    end
```

---

## 🧩 2. Component Deep-Dive

### 📡 A. Log Ingestor (The Sentinel Pulse)
The `log_ingestor` is the eyes and ears of the system. It runs as a low-overhead daemon that:
- **Mounts the Docker Socket**: Directly listens to `/var/run/docker.sock` using the Docker SDK.
- **Multi-Threaded Telemetry**:
    - **Log Streamer**: Attaches to `stdout/stderr` of all containers and pipes them to Kafka.
    - **Metric Sampler**: Polls real-time resource usage (CPU/RAM/Disk IO) with 0.01 precision.
    - **Event Monitor**: Detects `die`, `oom`, `kill`, and `start` events instantly.
- **Non-Invasive**: Unlike traditional sidecars, it does not inject agents into your application containers.

### 🧠 B. Incident Processor (The Reasoning Brain)
The `incident_processor` is where raw data turns into intelligence. It operates on a **3-Tier Analysis Pipeline**:
1.  **PGVector RAG Layer**: Converted logs are vectorized using `all-MiniLM-L6-v2`. If a similar log has been seen before (90%+ similarity), the system instantly applies the previous resolution.
2.  **Groq Reasoning Tier (Llama-3.1)**: If the issue is new, the payload is sent to Groq. The system prompt instructs the AI to return *only* a valid JSON diagnostic with root causes and specific bash remediation commands.
3.  **Local Fallback (Ollama)**: If the internet or cloud API is down, the system shifts logic to local Mistral models.

### 🛠️ C. Dashboard API (The Management Hub)
A high-performance Flask REST layer that:
- **State Hygiene**: On startup, it clears "Ghost" incidents if containers have manually returned to health.
- **Executive Shell Proxy**: Safely routes Docker CLI commands from the UI to the host socket.
- **Sentinel Autocomplete**: Uses Groq to suggest real-time commands in the terminal based on the container's active diagnostic context.

### 💾 D. Persistence Layer (The Time-Capsule)
- **Postgres + PGVector**: Stores every incident permanently. It doesn't just log errors; it stores *knowledge*.
- **Historical Metrics**: Stores resource usage trends used by Chart.js to render telemetry graphs.

---

## 🔄 3. Detailed Data Flow

1.  **CRASH**: A container (e.g., `api`) crashes due to a Segmentation Fault.
2.  **DETECTION**: `log_ingestor` catches the `die` event and the final line of logs.
3.  **INGESTION**: A JSON packet is pushed to Kafka: `{"container": "api", "log": "Segfault at 0x0... "}`.
4.  **ANALYSIS**: `incident_processor` picks it up. 
    - *Is it in RAG?* No. 
    - *Ask Groq?* Yes. 
5.  **DIAGNOSIS**: Groq returns: `{"root_cause": "Memory Leak", "suggested_fix": "docker restart api"}`.
6.  **HEALING**: The system marks the incident as `open` in the DB and triggers a Slack alert.
7.  **VISUALIZATION**: The Dashboard shows a pulsing red alert with the "Audit Data" button.
8.  **INTERACTION**: The SRE opens the "Executive Shell". The AI suggests `docker logs api --tail 50` via Autocomplete based on the crash context.

---

## 💾 3. Deep-Dive Persistence (Database Schema)

We leverage **PostgreSQL 15** with the **PGVector** extension. The system moves away from ephemeral logging to **Permanent Knowledge Accumulation**.

### A. Operational Events (`events` table)
| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL | Primary Key. |
| `container` | VARCHAR | Target node name (e.g., `api`). |
| `project` | VARCHAR | Compose project mapping. |
| `event_type` | VARCHAR | `diagnosis`, `remediation_attempt`, `ANOMALY_ALARM`, `SYSTEM_HEALED`. |
| `status` | VARCHAR | `open`, `resolved`, `dlq`. |
| `details` | JSONB | High-fidelity AI payload (source, severity, fix, confidence). |
| `timestamp` | DATETIME | IST (Indian Standard Time) normalized. |

### B. High-Precision Metrics (`metrics` table)
| Field | Type | Description |
| :--- | :--- | :--- |
| `cpu_percent` | NUMERIC(5,2) | 64-bit precision CPU usage. |
| `mem_usage_mb` | FLOAT | Absolute memory consumption. |
| `mem_limit_mb` | FLOAT | Node memory ceiling. |
| `disk_read_mb` | FLOAT | Historical I/O throughput. |

### C. RAG Memory (`incident_knowledge` table)
| Field | Type | Description |
| :--- | :--- | :--- |
| `log_signature` | TEXT | Raw log trace (Source of truth). |
| `embedding` | VECTOR(384) | 384-dimensional semantic representation. |
| `root_cause` | TEXT | Validated reasoning from Groq. |
| `suggested_fix` | TEXT | Confirmed bash remediation command. |

---

## 🔬 4. AI Model Benchmarking (`AI_Model_Comparison.xlsx`)

The repository includes a detailed comparison of models used across tiers:
- **Groq Llama-3.1-8b**: Selected for low-latency (400ms) deep reasoning.
- **Ollama Mistral**: High-reliability local fallback.
- **all-MiniLM-L6-v2**: Optimized for fast vector embeddings on CPU.

---

## 🛠️ 8. Operational Lifecycle (Step-by-Step Flow)

This diagram details exactly how the system discovers containers and maintains state from login to real-time charting.

```mermaid
sequenceDiagram
    participant User as 👤 User (UI)
    participant Dashboard as 🖥️ Web Dashboard
    participant API as ⚙️ Dashboard API
    participant Docker as 🐳 Docker Socket
    participant Kafka as 🏗️ Kafka Bus
    participant DB as 💾 PostgreSQL (PGVector)

    Note over User, DB: 1. Authentication Phase
    User->>API: POST /login (Credentials)
    API->>API: shared/auth.py (JWT Issue)
    API-->>User: Bearer Token

    Note over User, DB: 2. Discovery & Discovery Phase
    Dashboard->>API: GET /projects (with JWT)
    API->>Docker: containers.list(all=True)
    Docker-->>API: Namespaces, Labels, Statuses
    API->>DB: Lookup ProjectState (Linked/De-Linked)
    DB-->>API: is_tracked flags
    
    Note over User, DB: 3. Hydration Phase (Data Sync)
    API->>DB: Query LATEST Metric (CPU/RAM)
    API->>DB: Query ACTIVE Incident (Diagnosis)
    DB-->>API: 64-bit Precision Segments
    API-->>Dashboard: Unified JSON Tree

    Note over User, DB: 4. Real-time Telemetry (Pulse)
    Docker->>Kafka: log_ingestor (Event/Metric Stream)
    Kafka->>DB: incident_processor (SQL Persist)
    Dashboard->>API: GET /metrics/historical (Interval 5s)
    API->>DB: Fetch last 50 Metric ticks
    DB-->>API: Time-series Array
    API-->>Dashboard: Render Chart.js
```

---

## ⚙️ 9. Setup & Deployment

```bash
# Ignite the Sentinel Cluster
docker compose up -d --build

# Verify Connectivity
docker ps # Ensure all services (Log-Ingestor, Kafka, Processor, DB, API) are healthy

# Monitoring Live Telemetry
docker logs -f log_ingestor
```

---

## 🏆 9. Why Container Doctor?
Unlike generic log aggregators, **Container Doctor** is *actionable*. It doesn't just store data; it **analyzes** with Llama-3 reasoning, **learns** with RAG memory, and **heals** with autonomous decisions.

---
*© 2026 Container Doctor - Sentinel v14.0 - Sentience in Infrastructure.*
