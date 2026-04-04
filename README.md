# 🐋 Container Doctor: Autonomous Docker SaaS Agent

**Container Doctor** is a production-grade, AI-driven Docker monitoring agent. Unlike standard infrastructure logs, Container Doctor leverages the **Gemini 2.5 Flash** LLM pipeline to actively read crashing container signatures, structurally diagnose root causes, generate explicit codebase fixes, and natively execute safe auto-restart loops to heal your infrastructure.

It acts as a self-hosted orchestrator dashboard allowing developers to monitor, segment, and repair generic Docker environments without manual log-diving.

## ✨ Key Features
- **Intelligent Diagnostics**: Generates JSON-formated payloads containing precise Root Causes, Code Level Fixes, Target Files, and Estimated Impact parameters for any broken container.
- **Auto-Healing**: Predicts if an anomaly is `auto_restart_safe` and executes remediation loops cautiously (tracking cache limits to prevent infinite crash-loops). 
- **Orchestrator-Style UI**: Synthesizes flat Docker containers into a grouped Hierarchical Tree mapping via **Namespaces** (Docker Networks) and **Pods** (Docker Compose Projects). 
- **Agent Tracking States**: Disconnect specific pods dynamically from the tracking API via a live PostgreSQL cache database.
- **Docker Hub Gateway**: Implements a strict session token Authentication Wall natively validating against Docker Hub's API registry. 
- **Instant Alerting**: Comprehensive payload delivery detailing exactly what broke routing directly to your internal **Slack Webhooks** or fallback **SMTP Emails**.

## 🛠 Tech Stack
| Component | Technology | Description |
|-----------|------------|-------------|
| **Backend API** | Python (Flask) / Docker-SDK | Primary loop executing log analytics and Docker API commands. |
| **Database Cache**| PostgreSQL | Persists incident tracking states and stores offline diagnostics. |
| **Agent Intel** | Google Gemini (2.5-Flash) | Deciphers stack traces into high-fidelity actionable `.json` logic. |
| **Web UI** | HTML / Inter-CSS / JS | Rich Dark-Mode Orchestrator styling with active asynchronous fetch APIs. |

---

## 📂 Codebase Understanding

### 1. `container_doctor.py`
The absolute core of the agent. This file runs dual operations:
1. **Flask App Server**: Runs a lightweight REST API bounded to a session-auth router (`@app.before_request`) exposing analytical endpoints to the UI.
2. **Infinite Monitor Thread**: A daemon process endlessly analyzing active containers. If errors are discovered (`detect_errors()`) and validated against caching limits (`is_new_error()`), it invokes `diagnose_with_gemini()`, stores the report inside PostgreSQL, and executes remediation tasks.

### 2. `dashboard.html` & `login.html`
Secure Javascript mapping environments serving as the single-page application orchestrating the ecosystem. Includes the Docker Hub Web-API proxy logic for UI Access.

### 3. `Dockerfile` & `docker-compose.yml`
Container Doctor maps external volumes `/var/run/docker.sock` allowing the internal script to modify siblings running on the physical host machine dynamically.

---

## 🚀 Setup & Environment Configuration

Ensure you have a `.env` configured exactly like this before deploying the Agent:
```env
GEMINI_API_KEY=AIzaSyCwuSsP...
TARGET_CONTAINERS=web,api,db
CHECK_INTERVAL=3
LOG_LINES=50
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
DATABASE_URL=postgres://user:pass@db:5432/mydb
SECRET_KEY=long_random_auth_string

# Optional
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=my_alert_bot@gmail.com
SMTP_PASS=my_app_password
SMTP_RECIPIENT=devops_team@domain.com
```

Deploy the network:
```bash
docker compose up -d --build
```
> Access your Gateway natively via `http://localhost:8080/`

---

## 🗄️ Database Architecture (PostgreSQL)

The Agent leverages a relational database resolving stateless tracking faults:
- **`events`**: Archives the granular system transitions (`container_down`, `restart_failed`, `resolved`) along with massive nested `JSONB` Gemini payloads for the UI dashboard.
- **`container_state`**: A time-series cache regulating aggressive auto-restarts to prevent infinite loops from permanently overloading system CPUs. 
- **`tracked_pods`**: A binary boolean cache persisting exactly which cluster segments you disconnected via the dashboard.

---

## 📡 Endpoints Overview

| Route | Method | Description |
|-------|--------|-------------|
| `/` | `GET` | Main UI Endpoint. Secures session tokens and redirects to `/login` if offline. |
| `/login` | `GET` | Returns `login.html` frontend gateway. |
| `/api/login` | `POST` | Intercepts Username/Password dict, testing validity across official Docker Hub Registries natively. |
| `/history` | `GET` | Fetches the last 50 system transitions from PostgreSQL for Dashboard timelines. |
| `/stats` | `GET` | Delivers real-time numerical arrays (`tracked_pods`, `broken_containers`) for visual KPI widgets. |
| `/pods` | `GET` | Extracts Docker Networks generating a massive, highly-nested hierarchical Namespace -> Pod tree for the Workloads explorer. |
| `/diagnostics/<name>` | `GET` | Securely queries the database fallback mapping yielding standard Gemini diagnostic structures for broken namespaces. |
| `/pods/track/<pod>` | `POST` | Toggles the active agent connection scope caching to PostgreSQL dynamically. |

---

## 🔮 Future Enhancements (Roadmap)

To push the Docker Agent into the absolute peak of System Admin utilization, the following enhancements could be drafted:
1. **Native Kubernetes Ingress Setup**: Transitioning the `docker.socket` binding over into a physical Helm chart managing `CRD` (Custom Resource Definitions) natively across minikube boundaries.
2. **Advanced Mitigation (Auto-Patching)**: Because Gemini now outputs `target_file` and `config_suggestions`, the Agent could theoretically clone a Git repo locally dynamically, edit the `Dockerfile` parameter directly, and trigger an explicit `docker compose build` executing the repair natively without humans!
3. **Hardware Analytics**: Utilizing `c.stats()` to push CPU and RAM Memory mapping onto the Dashboard via Charts.JS streams dynamically, warning users right before OOM (Out Of Memory) breaks transpire!
4. **Custom Role-Based Auth (RBAC)**: Generating multiple local Agent dashboards based on custom defined `View-Only` vs `Admin` permissions.
