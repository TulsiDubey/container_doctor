# 🩺 Container Doctor: Enterprise AI-Sentinel & Observability Suite

**Container Doctor** is a production-grade, autonomous observability and self-healing platform designed for modern, high-density Docker environments. It transforms raw container telemetry into a high-reasoning diagnostic stream, leveraging **Groq-Powered Llama-3 Reasoning**, **Persistent Learning RAG Memory**, and **Kafka-native Event Sourcing** to detect, analyze, and resolve system failures with zero human intervention.

---

## 🎯 1. Overview (Project Summary)

In distributed systems, silent container failures and log-bloat make manual debugging impossible. **Container Doctor** acts as an autonomous SRE (Site Reliability Engineer) that constantly probes your fleet, extracts high-precision metrics, and applies multi-tier AI logic to maintain 99.9% uptime.

---

## 🚀 2. Problem Statement

Traditional monitoring (Prometheus/Grafana) tells you *when* a system is down, but not *why*.
- **Log Overload**: Sifting through millions of logs during a crash is slow and error-prone.
- **Manual Debugging**: DevOps engineers spend hours identifying root causes of recurring issues.
- **Slow Remediation**: Non-intelligent systems restart containers indiscriminately, often missing the underlying architectural fault.

---

## 💡 3. Solution (Our Approach)

We bridge the gap between "Monitoring" and "Sentience":
- **Kafka Backbone**: High-throughput log streaming ensures no telemetry is lost.
- **Hybrid AI Architecture**: Combines fast Rule-Engines with deep Groq-LLM reasoning.
- **RAG Learning**: The system "remembers" every verified fix, enabling 0ms latency for recurring failures.
- **Autonomous Remediation**: Intelligent Decision Engine triggers safe restarts and Slack alerts only when confidence is >85%.

---

## 🏗️ 4. System Architecture

The platform operates across four decoupled logical layers:

### The Sentience Layers:
1.  **Ingestion Layer**: `log_ingestor` mounts the Docker socket and streams logs/stats to Kafka.
2.  **Messaging Layer**: `Kafka (KRaft)` acts as the event-sourced truth ledger and buffer.
3.  **Processing Layer**: `incident_processor` applies the 3-Tier AI logic (Rules → RAG → Groq).
4.  **Presentation Layer**: `dashboard_api` + `Vanilla CSS Frontend` provides 64-bit precision visibility.

---

## 🔄 5. Workflow (Step-by-Step)

1.  **Telemetry Capture**: Raw logs and metrics are extracted via the host's `/var/run/docker.sock`.
2.  **Streaming**: JSON packets are pushed to `container-logs` and `container-metrics` topics.
3.  **Analysis Induction**: The `incident_processor` consumes packets and initiates the Reasoning Loop.
4.  **Rule Match**: Checks against `patterns.yaml` for known critical regular expressions.
5.  **RAG Lookup**: If no rule matches, searches the **PGVector Knowledge Base** for historical signatures.
6.  **AI Deep-Dive**: If still unresolved, the payload is sent to **Groq (Llama-3.1-70B)** for forensic analysis.
7.  **Auto-Remediation**: The Decision Engine executes a validated fix (e.g., Restart) and updates Slack.
8.  **Learning Persistence**: The result is vectorized and saved as new "Recall Memory" in Postgres.

---

## 🧠 6. AI Architecture (CORE SECTION)

We implement a **Multi-Model Orchestration** strategy:

| Intelligence Tier | Technology | Purpose | Latency |
| :--- | :--- | :--- | :--- |
| **Tier 0: Fast Path** | Regex Engine | Immediate critical signature matching | < 1ms |
| **Tier 1: Persistence** | PGVector RAG | Zero-call recall of previously analyzed issues | 2-5ms |
| **Tier 2: Reasoning** | Groq Llama-3.1 | Senior SRE level forensic analysis & fixing | 400ms |
| **Tier 3: Offline/Local** | Ollama (Mistral) | Fallback logic for air-gapped or offline periods | 2-5s |

---

## 🧩 7. Features

- ✅ **Real-Time Heartbeat Detection**: Detects manual stops and silent exits instantly.
- ✅ **Groq-Powered Diagnostics**: Root cause analysis with file-level remediation suggestions.
- ✅ **Persistent RAG (Recall)**: The sentinel learns from every failure, becoming faster over time.
- ✅ **High-Precision Stats**: Telemetry rounded to 0.01 precision (CPU, RAM, Disk I/O).
- ✅ **Slack & SMTP Notifications**: Real-time alerts with severity branding.
- ✅ **Dead Letter Queue (DLQ)**: Low-confidence incidents are routed for human-in-the-loop review.
- ✅ **Scalable Backbone**: Kafka-KRaft architecture handles thousands of message/sec.

---

## 📊 8. API Endpoints

Refer to **[ENDPOINTS.md](file:///home/tulsi/container-doctor/ENDPOINTS.md)** for full documentation.

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/login` | `POST` | Issues Stateless JWT for admin access. |
| `/stats` | `GET` | High-level pulse (Healthy vs Broken counts). |
| `/projects` | `GET` | Detailed grouping of containers with AI "In-Flight Insights". |
| `/history` | `GET` | Full event ledger (Filterable by `diagnosis`, `remediation`). |
| `/diagnostics/<name>` | `GET` | Deep AI payload for a specific node failure. |

---

## 💾 9. Database Design

We leverage **PostgreSQL 15** with the **PGVector** extension for hybrid data storage.

### Core Tables:
- **`events`**: The immutable ledger of system actions (Diagnoses, Restarts, DLQ hits).
- **`metrics`**: Time-series repository for high-precision resource tracking.
- **`incident_knowledge`**: The vector memory store containing `(embedding, root_cause, suggested_fix)`.

---

## 🔐 10. Environment Variables (.env)

Configuration is managed via a centralized `.env` file:

```env
# AI & Reasoning
GROQ_API_KEY=gsk_...           # Required for Tier 2 Reasoning
OLLAMA_HOST=http://ollama:11434 # Required for Tier 3 Fallback

# Notification
SLACK_WEBHOOK_URL=https://hooks...
SMTP_SERVER=...

# Security
JWT_SECRET=your_32_byte_key
```

---

## ⚙️ 11. Installation & Setup

Ensure Docker and Docker Compose (V2) are installed.

```bash
# 1. Clone & Configure
git clone <repository_url>
cd container-doctor
cp .env.example .env # Add your GROQ_API_KEY

# 2. Ignite the Sentinel
docker compose up -d --build

# 3. Access the Dashboard
# Open http://localhost:8080 (admin/password)
```

---

## 🧪 12. Testing Scenarios

Refer to **[TEST_GUIDE.md](file:///home/tulsi/container-doctor/TEST_GUIDE.md)** for detailed walkthroughs.

1.  **Scenario: Silent Shutdown**: `docker stop api` -> Observe **In-Flight Insight** update to "SHUTDOWN".
2.  **Scenario: Application Error**: Inject a DB error into logs -> Observe **Groq reasoning** identifies the cause.
3.  **Scenario: RAG Recall**: Repeat Scenario 2 -> Observe source changes to `rag_cache` with 0ms latency.

---

## 📈 13. Performance & Scalability

- **Non-Invasive Ingestion**: We mount the Unix socket, avoiding overhead on application containers.
- **Distributed workers**: The Analysis loop can be horizontally scaled by adding more `incident_processor` replicas.
- **Vector Indexing**: HNSW indexing in PGVector ensures RAG searches remain O(1) even with millions of historical issues.

---

## ⚠️ 14. Limitations

- **Log Density**: System accuracy depends on the quality of application logs (requires `stderr` output).
- **Resource Usage**: Running `ollama` locally requires 4GB+ RAM.
- **LLM Token Limits**: Very large log files (>10k lines) are truncated for LLM safety.

---

## 🚀 15. Future Enhancements

- 🌐 **Kubernetes (K8s) Operator**: Native support for Pod-level sentience.
- 📉 **Predictive Analytics**: Using LSTM models to predict failures before they happen.
- 🔒 **eBPF Integration**: Moving log capture into the kernel for zero-overhead observability.
- 🌍 **Multi-Region Sync**: Synchronizing RAG memories across global clusters.

---

## 🧠 16. Key Learnings

- Developing event-driven systems with **Kafka KRaft**.
- Implementing **Vector Similarity Search (RAG)** for DevOps automation.
- Managing 64-bit telemetry streams with millisecond precision.
- Building **Self-Healing Infrastructure** using hybrid AI models.

---

## 🧑‍💻 17. Tech Stack

- **Backend**: Python 3.12, Flask, SQLAlchemy.
- **Backbone**: Kafka KRaft, PostgreSQL + PGVector.
- **AI**: Groq (Llama 3.1), Sentence-Transformers, Ollama.
- **Frontend**: Vanilla HTML5/CSS3 (Glassmorphism), Vanilla JS.
- **Infra**: Docker, Docker Compose, Docker SDK.

---

## 📷 18. Screenshots

> [!TIP]
> **Dashboard View**: Real-time project explorer with "In-Flight Insight" columns.
> **Diagnostic View**: Deep analysis modal showing Groq-determined root cause and severity.
> Note: Here the screenshots is attched while testing
Login
<img width="579" height="505" alt="image" src="https://github.com/user-attachments/assets/0d6c4668-8797-4eed-8aa7-686de0a262e8" />
Dashboard
<img width="1860" height="1048" alt="image" src="https://github.com/user-attachments/assets/578a211b-5f03-4f12-b320-90e628cab62d" />
Container-Overview
<img width="1860" height="1048" alt="image" src="https://github.com/user-attachments/assets/55845920-9d01-4515-a07d-fbd85ea67da5" />
De-Link Project
<img width="1860" height="1048" alt="image" src="https://github.com/user-attachments/assets/5bb7e79d-938b-4940-97bb-4e9c517b58b5" />
Live-logs
<img width="1860" height="1048" alt="image" src="https://github.com/user-attachments/assets/34f71051-1af0-4169-890a-0df488086145" />
Event-history and suggestions
<img width="1860" height="1048" alt="image" src="https://github.com/user-attachments/assets/61d4d15b-ad89-4a57-a356-d1d10643663c" />
Slack alert
<img width="1860" height="1048" alt="image" src="https://github.com/user-attachments/assets/a12dda23-2f39-498b-adf1-33ec9853414b" />

---

## 📚 19. References

- [Confluent Kafka Documentation](https://docs.confluent.io/)
- [PGVector Specification](https://github.com/pgvector/pgvector)
- [Groq API Reference](https://console.groq.com/docs)
- [Docker SDK for Python](https://docker-py.readthedocs.io/)

---

## 🤝 20. Contributors

**Project Lead**: Autonomous AI-Sentinel Development Team.

---

# 🔥 Why this project is unique?
Unlike generic log aggregators, **Container Doctor** is *actionable*. It doesn't just store data—it **analyzes** with Llama-3 reasoning, **learns** with RAG memory, and **heals** with autonomous decisions.

---
*© 2026 Container Doctor - Sentinel v14.0 - Sentience in Infrastructure.*
