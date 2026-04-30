import os
import docker
import json
import time
from flask import Flask, jsonify, request, session, redirect, send_file
from flask_cors import CORS
from shared.db import SessionLocal, Event, Metric, ProjectState, ChatMessage, ChatKnowledge, init_db, get_now_ist
from shared.auth import generate_token, token_required
from sqlalchemy import desc, func, text, cast, Integer
from sentence_transformers import SentenceTransformer
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
embedder = SentenceTransformer('all-MiniLM-L6-v2')

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

@app.route("/api/system/health", methods=["GET"])
@token_required
def system_health():
    """
    Phase 47: Self-Monitoring Observability.
    """
    db = SessionLocal()
    try:
        # 1. Database Health
        db.execute(text("SELECT 1"))
        
        # 2. AI Metrics (Approximate from history)
        avg_confidence = db.query(func.avg(cast(Event.details['llm_confidence'].astext, Integer))).filter(Event.event_type == 'diagnosis').scalar() or 0
        
        # 3. RAG Hit Rate (Approximate)
        total_diag = db.query(Event).filter(Event.event_type == 'diagnosis').count()
        rag_hits = db.query(Event).filter(Event.event_type == 'diagnosis', Event.details['source'].astext == 'rag_cache').count()
        hit_rate = (rag_hits / total_diag * 100) if total_diag > 0 else 0
        
        return jsonify({
            "status": "healthy",
            "db": "connected",
            "ai_confidence_avg": round(float(avg_confidence), 2),
            "rag_hit_rate": f"{round(hit_rate, 1)}%",
            "timestamp": datetime.now(IST).isoformat()
        })
    except Exception as e:
        return jsonify({"status": "degraded", "error": str(e)}), 500
    finally:
        db.close()

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
            # Phase 40: JIT (Just-In-Time) Diagnosis
            try:
                client = get_docker_client()
                container = client.containers.get(container_name)
                # Fetch latest 100 lines for deep context analysis
                logs = container.logs(tail=100).decode('utf-8')
                
                # Re-run reasoning if broken but silent
                if container.status != "running" and logs:
                    from groq import Groq
                    api_key = os.getenv("GROQ_API_KEY", "")
                    if api_key:
                        groq_client = Groq(api_key=api_key)
                        prompt = f"Perform deep forensic analysis on these Docker logs from '{container_name}'. The container is down. Identify root_cause, severity, and a one-line suggested_fix bash command. Log data: {logs}"
                        chat = groq_client.chat.completions.create(
                            messages=[
                                {"role": "system", "content": "You are a Forensic Sentinel Agent. Return ONLY JSON with fields: root_cause, severity, suggested_fix, confidence_score."},
                                {"role": "user", "content": prompt}
                            ],
                            model="llama-3.1-8b-instant",
                            response_format={"type": "json_object"}
                        )
                        jit_diag = json.loads(chat.choices[0].message.content)
                        
                        # Persist JIT discovery to DB
                        event = Event(
                            container=container_name,
                            event_type="diagnosis",
                            status="open",
                            details={
                                "root_cause": jit_diag.get("root_cause", "Anomaly Detected"),
                                "suggested_fix": jit_diag.get("suggested_fix", "docker restart " + container_name),
                                "severity": jit_diag.get("severity", "high"),
                                "source": "jit_forensics",
                                "llm_confidence": jit_diag.get("confidence_score", 100)
                            }
                        )
                        db.add(event)
                        db.commit()
                        db.refresh(event)
                else:
                    # If still nothing, move to DLQ
                    dlq_event = Event(
                        container=container_name,
                        event_type="diagnosis",
                        status="dlq",
                        details={
                            "root_cause": "Failed to extract diagnostic payload.",
                            "suggested_fix": "Manual inspection required via terminal.",
                            "severity": "high",
                            "is_diagnosable": "false"
                        }
                    )
                    db.add(dlq_event)
                    db.commit()
                    return jsonify({"error": "Node undiagnosable. Incident moved to DLQ for human review."}), 404
            except Exception as e:
                print(f"JIT Analysis Failed: {e}")
                return jsonify({"error": f"Forensic engine failure: {str(e)}"}), 500

        if not event:
            return jsonify({"error": "No diagnostic payload available."}), 404
        
        # Return the structured JSON details
        details = event.details or {}
        return jsonify({
            "id": event.id,
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
        cwd = data.get("cwd", "/")
        
        # Generic Host Terminal (Phase 40)
        if container_name == "host":
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=cwd if os.path.exists(cwd) else None)
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

        # Phase 46: Security Shield (Blacklist)
        blacklist = ["rm -rf", "chmod 777", ":(){ :|:& };:", "dd if=", "> /dev/sda", "shutdown", "reboot"]
        for forbidden in blacklist:
            if forbidden in command.lower():
                return jsonify({"error": f"Security Violation: Command '{forbidden}' is restricted.", "status": "blocked"}), 403

        # Sub-container contextual shell
        container = client.containers.get(container_name)
        if container.status != "running":
            return jsonify({"error": f"Node '{container_name}' is offline. Start it first.", "status": "failed"}), 200

        result = container.exec_run(["/bin/sh", "-c", f"cd {cwd} && {command}"], environment={"TERM": "xterm"})
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
        cpu_limit = float(data.get("cpu", 0.5)) # Default to 0.5 cores
        
        client = get_docker_client()
        container = client.containers.get(name)
        
        # CPU Period/Quota calculation
        cpu_period = 100000
        cpu_quota = int(cpu_limit * cpu_period)
        
        # Update resources (Docker SDK)
        container.update(
            mem_limit=mem_limit, 
            memswap_limit=mem_limit,
            cpu_period=cpu_period,
            cpu_quota=cpu_quota
        )
        
        return jsonify({"success": True, "message": f"Resources updated for {name}: CPU={cpu_limit}, MEM={mem_limit}"})
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

@app.route("/api/chat", methods=["POST"])
@token_required
def chat_bot():
    """
    Phase 45: Senior DevOps SRE AI Assistant with RAG.
    """
    data = request.json
    user_query = data.get("query")
    if not user_query:
        return jsonify({"error": "Query is required"}), 400

    db = SessionLocal()
    try:
        # 1. RAG Cache Check
        query_embedding = embedder.encode(user_query).tolist()
        sim_match = db.query(
            ChatKnowledge, 
            ChatKnowledge.embedding.cosine_distance(query_embedding).label("distance")
        ).order_by("distance").first()

        # 85% similarity threshold (0.15 distance)
        if sim_match and sim_match.distance <= 0.15:
            answer = sim_match.ChatKnowledge.answer
            source = "rag_cache"
        else:
            # 2. LLM Fallback (Groq)
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                return jsonify({"error": "AI Engine offline (Missing API Key)"}), 503
            
            groq_client = Groq(api_key=api_key)
            system_prompt = (
                "You are a Senior DevOps SRE and Docker Expert. "
                "Provide technical, accurate, and highly structured advice using Markdown. "
                "Use bullet points for steps, bold text for key terms, and code blocks for commands. "
                "Ensure your response is easy to read and logically organized."
            )
            
            # Fetch recent history for context
            history = db.query(ChatMessage).order_by(desc(ChatMessage.timestamp)).limit(5).all()
            messages = [{"role": "system", "content": system_prompt}]
            for h in reversed(history):
                messages.append({"role": h.role, "content": h.content})
            messages.append({"role": "user", "content": user_query})

            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.1-8b-instant",
                temperature=0.2
            )
            answer = chat_completion.choices[0].message.content
            source = "groq_llama3"

            # 3. Learning Phase: Auto-update RAG if it's a new quality answer
            new_knowledge = ChatKnowledge(
                query=user_query,
                answer=answer,
                embedding=query_embedding
            )
            db.add(new_knowledge)

        # 4. Save to History
        db.add(ChatMessage(role="user", content=user_query))
        db.add(ChatMessage(role="assistant", content=answer))
        db.commit()

        return jsonify({
            "answer": answer,
            "source": source,
            "timestamp": datetime.now(IST).isoformat()
        })
    except Exception as e:
        print(f"Chat Engine Panic: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@app.route("/api/chat/history", methods=["GET"])
@token_required
def chat_history():
    db = SessionLocal()
    try:
        messages = db.query(ChatMessage).order_by(ChatMessage.timestamp).limit(50).all()
        return jsonify({
            "history": [{"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in messages]
        })
    finally:
        db.close()

if __name__ == "__main__":
    start_app()
