# Test Operations Manual: Container Doctor Sentinel v12.0

Follow this guide to verify the primary capabilities of the **Autonomous Sentinel** platform, including Groq-powered reasoning, Learning RAG persistence, and High-Precision Telemetry.

---

## 🧪 Scenario 1: Heartbeat Detection (Manual Stop)
**Objective**: Verify the system detects non-running containers via passive heartbeats and identifies the shutdown reason.

1.  **Action**: Open a terminal and run:
    ```bash
    docker stop api
    ```
2.  **Dashboard Observation**:
    - The **api** container state changes to `broken` in the Project Explorer.
    - The **In-Flight Insight** column displays: `CONTAINER SHUTDOWN`.
    - A new card appears in **Active Diagnostics** with the timestamp and suggested fix ("Start container").
3.  **Persistence Audit**: Go to **Event History** tab. You should see a `diagnosis` type event for container `api`.

---

## 🧠 Scenario 2: AI Forensics (Runtime Failure)
**Objective**: Verify that the AI extracts logs from a running container to identify application-level faults.

1.  **Action**: Inject a simulated error into the API container logs:
    ```bash
    docker exec api sh -c "echo 'CRITICAL ERROR: Connection to postgres-db failure: timeout' >> /proc/1/fd/2"
    ```
2.  **Dashboard Observation**:
    - Click **DEEP ANALYZE** on the **api** container.
    - **Expected Result**: AI identifies `Database Connection Failure` as the root cause.
    - **Source**: Should report `tier2_groq_llama3` (or tier 1 if RAG hits).
3.  **Status**: The diagnosis card will appear in the Overview grid with `high` severity.

---

## 🧬 Scenario 3: Learning RAG Memory Recall
**Objective**: Verify that the system "learns" and provides 0ms latency responses for recurring issues.

1.  **Action**: Repeat Scenario 2:
    ```bash
    docker exec api sh -c "echo 'CRITICAL ERROR: Connection to postgres-db failure: timeout' >> /proc/1/fd/2"
    ```
2.  **Dashboard Observation**:
    - Check the **Event History** or **Audit Data** for the new event.
    - **Expected Result**: The source should now report `rag_cache`.
    - **Outcome**: The system avoided a costly LLM call by remembering the previously verified diagnostic path.

---

## 📊 Scenario 4: High-Precision Telemetry Check
**Objective**: Verify the 64-bit precision telemetry backbone.

1.  **Action**: Observe the metric columns (**CPU**, **RAM**, **Disk IO**) in the Project Explorer.
2.  **Verification**:
    - Metrics should show decimal precision (e.g. `0.23%` instead of `0%`).
    - Refresh the dashboard and observe the counters updating every 5-10 seconds based on core state.

---

## 🚨 Scenario 5: Alerting & Notifications
**Objective**: Verify Slack/SMTP outbound delivery.

1.  **Action**: Check your configured Slack Webhook or Email inbox after Scenario 2.
2.  **Expected**: An alert containing the Container Name, Root Cause, and Fixed Suggestion should arrive within 30 seconds of the event.

---
**Status: Stability Lock ACTIVE | Reasoning: GROQ + RAG**
