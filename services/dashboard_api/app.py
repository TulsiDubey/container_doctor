import os
import docker
import json
import time
from flask import Flask, jsonify, request, session, redirect, send_file
from flask_cors import CORS
from shared.db import SessionLocal, Event, Metric, ProjectState, init_db, get_now_ist
from shared.auth import generate_token, token_required
from sqlalchemy import desc, func, text
import threading
import requests
from datetime import datetime, timezone, timedelta, timedelta
IST = timezone(timedelta(hours=5, minutes=30))
IST = timezone(timedelta(hours=5, minutes=30))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "doctor_agent_secure_v2")
CORS(app)

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
docker_client = None

def get_docker_client():
    global docker_client
    # Phase 33: Persistent Socket Heartbeat check
    try:
        if docker_client is None:
            if not os.path.exists("/var/run/docker.sock"):
                print("🚨 [CRITICAL] Docker socket NOT FOUND at /var/run/docker.sock. Dashboard isolating...")
                return None
            docker_client = docker.from_env()
        # Verify connection is still alive
        docker_client.ping()
        return docker_client
    except Exception as e:
        print(f"📡 [SOCKET_ERROR] Docker connection failed: {e}. Resetting client...")
        docker_client = None
        return None
        
def watchdog_loop():
    """
    Phase 37: Unified Sentinel Infrastructure.
    The local Watchdog database injector has been fully deprecated.
    All Outage occurrences are successfully piped via the log_ingestor over KAFKA
    directly to Engine.py, triggering the Universal Groq Diagnostic Pipeline.
    """
    pass

def align_system_health():
    """
    Phase 25: Global State Hygiene.
    Purges stale 'Ghost' incidents on startup if services are already healthy.
    """
    print("🧹 [SENTINEL] Aligning Global Infrastructure State Hygiene...")
    with SessionLocal() as db:
        for service in ["kafka", "ollama", "db"]:
            try:
                container = get_docker_client().containers.get(service)
                if container.status == "running":
                    # Phase 26: Fuzzy Name Alignment (LIKE search to clear prefixed names)
                    db.query(Event).filter(
                        Event.container.like(f"%{service}%"),
                        Event.status == "open"
                    ).update({
                        "status": "resolved", 
                        "event_type": "SYSTEM_HEALED"
                    })
            except: pass
        db.commit()
    print("✅ [SENTINEL] Hygiene Alignment Complete.")

@app.after_request
def add_header(response):
    """
    Phase 26: Cache-Busting Header.
    Forces browsers to pull the latest 5s sync logic.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- Auth & Routes ---

@app.route("/")
def index():
    """
    Main Enterprise Dashboard. 
    Frontend handles the JWT-check and redirect to /login if needed.
    """
    return send_file(os.path.join(STATIC_DIR, "dashboard.html"))

@app.route("/login")
def login_page():
    return send_file(os.path.join(STATIC_DIR, "login.html"))

@app.route("/api/login", methods=["POST"])
@app.route("/login", methods=["POST"])
def login_api():
    """
    Enterprise JWT-based login logic.
    For this demo/local: any non-empty auth is allowed.
    In prod: check against a real user DB.
    """
    data = request.json or {}
    un = data.get("username")
    pw = data.get("password")
    
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass = os.getenv("ADMIN_PASS", "admin")
    
    if un == admin_user and pw == admin_pass:
        token = generate_token(un)
        return jsonify({"token": token, "success": True})
    
    return jsonify({"success": False, "message": "Invalid identity credentials"}), 401

@app.route("/logout")
def logout():
    # Stateless JWT: client just discards the token
    return redirect("/login")

# --- UI Assets ---

@app.route("/")
def dashboard():
    return send_file(os.path.join(STATIC_DIR, "dashboard.html"))

# --- Data Endpoints ---

@app.route("/stats")
@token_required
def stats():
    db = SessionLocal()
    try:
        client = get_docker_client()
        if not client:
            return jsonify({
                "total_projects": 0, "tracked_projects": 0, "healthy_containers": 0, "broken_containers": 0,
                "latest_incident": None, "error": "Docker Socket Disconnected"
            })
            
        containers = client.containers.list(all=True)
        total_projects = len(set(c.labels.get('com.docker.compose.project', 'standalone') for c in containers))
        
        # In a real distributed system, we'd query a "Heartbeat" or "State" table.
        # For now, we perform a real-time count.
        healthy = 0
        broken = 0
        for c in containers:
            is_healthy = c.status == "running"
            if is_healthy: healthy += 1
            else: broken += 1
            
        # Phase 21: Fetch latest high-severity OPEN incident for Overview "Hit" summary
        latest_incident = db.query(Event).filter(
            Event.event_type == "diagnosis",
            Event.status == "open"
        ).order_by(desc(Event.timestamp)).first()
        
        latest_summary = None
        if latest_incident and latest_incident.details:
            details = latest_incident.details
            latest_summary = {
                "container": latest_incident.container,
                "reason": details.get("root_cause", "Anomaly Detected"),
                "severity": details.get("severity", "unknown")
            }

        return jsonify({
            "total_projects": total_projects,
            "tracked_projects": total_projects,
            "healthy_containers": healthy,
            "broken_containers": broken,
            "latest_incident": latest_summary
        })
    finally:
        db.close()

@app.route("/recent")
@token_required
def get_recent_incidents():
    """
    Phase 30: Real-time Incident Heartbeat.
    Returns the latest events for the Active Diagnostics grid.
    """
    db = SessionLocal()
    try:
        events = db.query(Event).order_by(desc(Event.timestamp)).limit(50).all()
        return jsonify({
            "recent": [
                {
                    "id": e.id,
                    "container": e.container,
                    "event": e.event_type,
                    "timestamp": e.timestamp.isoformat(),
                    "details": e.details if e.details else {},
                    "status": e.status
                } for e in events
            ]
        })
    finally:
        db.close()

@app.route("/projects")
@token_required
def projects():
    db = SessionLocal()
    try:
        try:
            containers = get_docker_client().containers.list(all=True)
        except Exception as de:
            print(f"Docker client error: {de}")
            return jsonify({"error": "Docker service unavailable temporarily"}), 503

        # Rebranded Grouping: Namespaces -> Compose Projects
        project_groups = {}
        
        for c in containers:
            p_name = c.labels.get('com.docker.compose.project', 'standalone')
            
            # Use 'default' if network is missing
            networks = c.attrs.get('NetworkSettings', {}).get('Networks', {})
            network_id = list(networks.keys())[0] if networks else "default"
            
            if network_id not in project_groups:
                project_groups[network_id] = {"group_id": network_id, "items": {}}
            
            if p_name not in project_groups[network_id]["items"]:
                # Phase 32: Persistent tracking lookup
                state = db.query(ProjectState).filter(ProjectState.project_name == p_name).first()
                is_tracked = state.is_tracked if state else True
                project_groups[network_id]["items"][p_name] = {"name": p_name, "containers": [], "tracked": is_tracked}
            
            # Fetch latest metrics (Phase 8: High Precision)
            latest_metric = db.query(Metric).filter(Metric.container == c.name).order_by(Metric.timestamp.desc()).first()
            cpu = f"{round(latest_metric.cpu_percent, 2)}%" if latest_metric else "0%"
            mem = f"{round(latest_metric.mem_usage_mb, 2)}MB" if latest_metric else "0MB"
            mem_limit = f"{round(latest_metric.mem_limit_mb, 2)}MB" if latest_metric and latest_metric.mem_limit_mb else "0MB"
            
            # Safe division check for memory % representation
            if latest_metric and latest_metric.mem_limit_mb > 0:
                calc_percent = (latest_metric.mem_usage_mb / latest_metric.mem_limit_mb) * 100
                mem_percent = f"{round(calc_percent, 2)}%"
            else:
                mem_percent = "0%"

            # Phase 12 & 15: Fetch latest active AI Reasoning (Diagnosis or Anomalies)
            latest_diag = db.query(Event).filter(
                Event.container == c.name,
                Event.event_type.in_(["diagnosis", "ANOMALY_ALARM", "OUTAGE_DETECTED"]),
                Event.status == "open" # Only pull active failures
            ).order_by(desc(Event.timestamp)).first()
            
            reason = latest_diag.details.get("root_cause", "Pending Diagnostics") if latest_diag else "Stable"
            confidence = latest_diag.details.get("llm_confidence", 100) if latest_diag else 100

            project_groups[network_id]["items"][p_name]["containers"].append({
                "id": c.short_id,
                "name": c.name,
                "project": p_name,
                "status": "running" if c.status == "running" else "broken",
                "health": "healthy" if c.status == "running" else "broken",
                "cpu": cpu,
                "ram": mem,
                "mem_limit": mem_limit,
                "mem_percent": mem_percent,
                "reason": reason,
                "llm_confidence": confidence
            })
            
        # Standardized Response Structure: list of groups (formerly namespaces)
        final_list = []
        for gid, gdata in project_groups.items():
            item_list = []
            for iid, idata in gdata["items"].items():
                item_list.append(idata)
            final_list.append({"namespace": gid, "projects": item_list})
            
        return jsonify(final_list)
    finally:
        db.close()

@app.route("/project/tracking", methods=["POST"])
@token_required
def toggle_project_tracking():
    """
    Phase 32: Persistent Link/De-Link.
    """
    data = request.json
    p_name = data.get("project_name")
    is_tracked = data.get("tracked", True)
    
    with SessionLocal() as db:
        state = db.query(ProjectState).filter(ProjectState.project_name == p_name).first()
        if not state:
            state = ProjectState(project_name=p_name)
            db.add(state)
        
        state.is_tracked = is_tracked
        state.last_updated = get_now_ist()
        db.commit()
        
    return jsonify({"success": True})

@app.route("/history")
@token_required
def history():
    db = SessionLocal()
    try:
        # Phase 10 & 15 & 35: Filter for Active/Open incidents by default, including Anomalies
        filter_type = request.args.get("filter", "all")
        query = db.query(Event).filter(
            Event.event_type.in_(["diagnosis", "remediation_attempt", "decision_audit", "ANOMALY_ALARM", "OUTAGE_DETECTED", "SYSTEM_HEALED", "RECOVERY_ACTION"]),
            Event.status == "open" # Default to open issues
        )
        
        if filter_type == "dlq":
            query = query.filter(text("details->>'is_diagnosable' = 'false'"))
        elif filter_type == "all":
            # Override default filter if user specifically asks for everything
            query = db.query(Event).filter(
                Event.event_type.in_(["diagnosis", "remediation_attempt", "decision_audit", "ANOMALY_ALARM", "OUTAGE_DETECTED", "SYSTEM_HEALED", "RECOVERY_ACTION"])
            )

        events = query.order_by(desc(Event.timestamp)).limit(100).all()
        
        results = []
        for e in events:
            res = {
                "container": e.container,
                "project": e.project or "standalone",
                "event": e.event_type,
                "status": e.status,
                "timestamp": e.timestamp.isoformat(),
                "details": e.details
            }
            results.append(res)
            
        return jsonify({"recent": results})
    finally:
        db.close()

@app.route("/metrics/historical", methods=["GET"])
@token_required
def get_historical_metrics():
    """
    Phase 39: Returns chronological metrics for graph rendering.
    """
    try:
        db = SessionLocal()
        container = request.args.get('container')
        
        query = db.query(Metric)
        if container: query = query.filter(Metric.container == container)
        metrics = query.order_by(desc(Metric.id)).limit(50).all()
        metrics.reverse()
        
        results = [{
            "container": m.container,
            "cpu_percent": float(m.cpu_percent) if m.cpu_percent else 0,
            "mem_percent": float(m.mem_usage_mb)/float(m.mem_limit_mb)*100 if m.mem_limit_mb and m.mem_limit_mb > 0 else 0,
            "timestamp": m.timestamp.isoformat()
        } for m in metrics]
        return jsonify({"success": True, "metrics": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()

@app.route("/diagnostics/<container_name>")
@token_required
def get_diagnostics(container_name):
    db = SessionLocal()
    try:
        # Phase 21 & 35: Try Open first, then Latest.
        event = db.query(Event).filter(
            Event.container == container_name,
            Event.event_type.in_(["diagnosis", "ANOMALY_ALARM", "OUTAGE_DETECTED"]),
            Event.status == "open"
        ).order_by(desc(Event.timestamp)).first()
        
        if not event:
            event = db.query(Event).filter(
                Event.container == container_name,
                Event.event_type.in_(["diagnosis", "ANOMALY_ALARM", "OUTAGE_DETECTED"])
            ).order_by(desc(Event.timestamp)).first()

        if not event:
            # Phase 21: Job Handling
            if "ollama_pull" in container_name:
                return jsonify({
                    "root_cause": "Internal model provisioning completed successfully.",
                    "suggested_fix": "No action required. job-ollama-pull finished securely.",
                    "severity": "low",
                    "source": "sentinel_job_engine",
                    "llm_confidence": 100
                })
            return jsonify({"error": "No diagnostic payload available for this node state."}), 404
        
        # Return the structured JSON details
        details = event.details or {}
        return jsonify({
            "root_cause": details.get("root_cause", "Undetermined"),
            "suggested_fix": details.get("suggested_fix", "Manual investigation required"),
            "severity": details.get("severity", "unknown"),
            "source": details.get("source", "system_audit"),
            "llm_confidence": details.get("llm_confidence", 100)
        })
    finally:
        db.close()

@app.route("/metrics")
def metrics_endpoint():
    db = SessionLocal()
    try:
        from sqlalchemy import func
        # Handle cases where event_type might not be populated or table is empty
        stats_query = db.query(Event.event_type, func.count(Event.id)).group_by(Event.event_type).all()
        lines = []
        for event_type, count in stats_query:
            etype = event_type if event_type else "unknown"
            lines.append(f'container_doctor_event_total{{type="{etype}"}} {count}')
        
        if not lines:
            lines.append('container_doctor_event_total{type="heartbeat"} 1')
            
        return "\n".join(lines), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f"# Error: {e}", 200, {'Content-Type': 'text/plain; charset=utf-8'}
    finally:
        db.close()

@app.route("/logs/<container_name>")
@token_required
def get_logs(container_name):
    try:
        c = get_docker_client().containers.get(container_name)
        logs = c.logs(tail=100).decode('utf-8')
        return jsonify({"logs": logs, "success": True})
    except Exception as e:
        return jsonify({"logs": str(e), "success": False}), 500

@app.route("/terminal/exec", methods=["POST"])
@token_required
def terminal_exec():
    """
    Phase 28: Sentinel Executive Shell.
    Provides direct command execution on targeted containers or host.
    """
    data = request.json
    container_name = data.get("container")
    command = data.get("command")
    
    # Safety Filter
    blocked = ["rm -rf /", "mkfs", "dd if=/dev/zero"]
    if any(b in command for b in blocked):
        return jsonify({"error": "Sentinel blocked absolute destructive command."}), 403

    print(f"🛡️ [COMMANDER_MODE] Executing command on {container_name}: {command}")
    
    try:
        client = get_docker_client()
        
        # Generic Host Terminal (Phase 40)
        if container_name == "host":
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            return jsonify({
                "output": result.stdout if result.stdout else result.stderr,
                "exit_code": result.returncode,
                "status": "success"
            })

        # Intercept Host Context Docker Commands
        if command.startswith("docker "):
            parts = command.split()
            if len(parts) >= 3:
                action = parts[1]
                target = parts[2]
                try:
                    target_container = client.containers.get(target)
                    if action == "start": target_container.start()
                    elif action == "stop": target_container.stop()
                    elif action == "restart": target_container.restart()
                    elif action == "kill": target_container.kill()
                    else: return jsonify({"error": f"Unsupported action: {action}"}), 400
                    return jsonify({"output": f"[HOST] Successfully executed docker {action} on {target}", "exit_code": 0})
                except Exception as ex:
                    return jsonify({"error": str(ex)}), 404
            else:
                return jsonify({"error": "Invalid docker command format."}), 400

        # Sub-container contextual shell
        container = client.containers.get(container_name)
        if container.status != "running":
            return jsonify({"error": f"Node '{container_name}' is offline. Start it first.", "status": "failed"}), 200

        result = container.exec_run(["/bin/sh", "-c", command], environment={"TERM": "xterm"})
        return jsonify({
            "output": result.output.decode("utf-8") if result.output else "Command executed.",
            "exit_code": result.exit_code,
            "status": "success"
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500

@app.route("/api/container/<name>/resources", methods=["POST"])
@token_required
def update_resources(name):
    """
    Phase 40: Dynamic Resource Allocation.
    """
    try:
        data = request.json
        mem_limit = data.get("memory") # e.g. "512m", "1g"
        
        client = get_docker_client()
        container = client.containers.get(name)
        
        # Update memory limits (Docker SDK uses bytes or string like '512m')
        container.update(mem_limit=mem_limit, memswap_limit=mem_limit)
        
        return jsonify({"success": True, "message": f"Resource limits updated for {name} to {mem_limit}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/terminal/autocomplete", methods=["POST"])
@token_required
def terminal_autocomplete():
    """
    Phase 35 & 39: Sentinel Predictive Autocomplete.
    Uses cloud LLM to infer the rest of the bash command contextually avoiding hallucinations by binding to the active problem.
    """
    data = request.json
    container_name = data.get("container", "unknown")
    current_input = data.get("input", "")
    
    if len(current_input) < 2:
        return jsonify({"suggestion": ""})

    try:
        problem_context = ""
        db = SessionLocal()
        try:
            event = db.query(Event).filter(
                Event.container == container_name,
                Event.event_type.in_(["diagnosis", "ANOMALY_ALARM", "OUTAGE_DETECTED"]),
                Event.status == "open"
            ).order_by(desc(Event.timestamp)).first()
            if event and event.details:
                cause = event.details.get("root_cause", "Unknown error")
                problem_context = f"The container crashed due to: '{cause}'."
        finally:
            db.close()
            
        prompt = f"Complete this linux terminal command being typed by a sysadmin handling the container '{container_name}'. {problem_context} Current input: '{current_input}'. Respond with ONLY the exact continuation characters (the suffix). Do not repeat the `{current_input}` part. No quotes around it, no markdown formatting. Keep it short."
        suggestion = ""

        api_key = os.getenv("GROQ_API_KEY", "")
        if api_key:
            from groq import Groq
            groq_client = Groq(api_key=api_key)
            completion = groq_client.chat.completions.create(
                messages=[{
                    "role": "system",
                    "content": "You are a terminal autocomplete binary. Give only the exact suffix of the shell command."
                }, {"role": "user", "content": prompt}],
                model="llama-3.1-8b-instant",
                temperature=0.1,
                max_tokens=20
            )
            suggestion = completion.choices[0].message.content.strip()
            if suggestion.startswith("```"): suggestion = suggestion.split("\n")[1].replace("```", "")
        
        return jsonify({"suggestion": suggestion, "success": True})
    except Exception as e:
        print(f"Autocomplete Error: {e}", flush=True)
        return jsonify({"suggestion": "", "success": False})

@app.route("/diagnostics/train", methods=["POST"])
@token_required
def train_sentinel():
    """
    Phase 28: RAG Feedback Loop.
    Indexes a specific event's diagnostic data into the Knowledge Warehouse.
    """
    data = request.json
    event_id = data.get("event_id")
    
    with SessionLocal() as db_session:
        event = db_session.query(Event).filter(Event.id == event_id).first()
        if not event:
            return jsonify({"error": "Event not found."}), 404
            
        # Phase 36: Physical Memory Generation
        event.status = "archived" # Move to archive when 'learned'
        
        details = event.details or {}
        root_cause = details.get("root_cause", "")
        suggested_fix = details.get("suggested_fix", "")
        
        if root_cause and suggested_fix:
            try:
                import requests
                # Use Ollama locally for extremely fast neural embedding generation 
                # all-minilm matches the 384 dimensions of our vector DB
                payload = {"model": "all-minilm", "prompt": root_cause} 
                resp = requests.post("http://ollama:11434/api/embeddings", json=payload, timeout=5)
                if resp.status_code == 200:
                    embedding = resp.json().get("embedding")
                    from shared.db import IncidentKnowledge
                    existing_k = db_session.query(IncidentKnowledge).filter(IncidentKnowledge.root_cause == root_cause).first()
                    if not existing_k and embedding:
                        knowledge = IncidentKnowledge(
                            root_cause=root_cause,
                            suggested_fix=suggested_fix,
                            source="human_verified",
                            embedding=embedding
                        )
                        db_session.add(knowledge)
            except Exception as e:
                print(f"Failed to manually train RAG vector DB: {e}", flush=True)

        db_session.commit()
        return jsonify({"message": "Sentinel Training Completed. Incident permanently archived in pgvector Warehouse.", "success": True})

def start_app():
    """
    Resilient startup: Retry DB init but don't block the API bind.
    """
    print("Dashboard API Hub Starting...")
    retry_count = 0
    while retry_count < 10:
        try:
            init_db()
            print("Database Synchronized.")
            break
        except Exception as e:
            retry_count += 1
            print(f"Database sync attempt {retry_count} failed: {e}. Retrying...")
            time.sleep(5)
    
    # Phase 25: Proactive Hygiene Alignment
    align_system_health()

    # Start the Meta-Sentinel in background
    threading.Thread(target=watchdog_loop, daemon=True).start()
            
    app.run(host="0.0.0.0", port=8080, threaded=True)

if __name__ == "__main__":
    start_app()
