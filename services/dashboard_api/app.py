import os
import docker
import json
import time
from flask import Flask, jsonify, request, session, redirect, send_file
from flask_cors import CORS
from shared.db import SessionLocal, Event, Metric, init_db
from shared.auth import generate_token, token_required
from sqlalchemy import desc, func, text

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "doctor_agent_secure_v2")
CORS(app)

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
docker_client = None

def get_docker_client():
    global docker_client
    if docker_client is None:
        docker_client = docker.from_env()
    return docker_client

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
    
    if un and pw:
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
        containers = get_docker_client().containers.list(all=True)
        total_projects = len(set(c.labels.get('com.docker.compose.project', 'standalone') for c in containers))
        
        # In a real distributed system, we'd query a "Heartbeat" or "State" table.
        # For now, we perform a real-time count.
        healthy = 0
        broken = 0
        for c in containers:
            is_healthy = c.status == "running"
            if is_healthy: healthy += 1
            else: broken += 1
            
        # Phase 10: Fetch latest high-severity incident for Overview "Hit" summary
        latest_incident = db.query(Event).filter(
            Event.event_type == "diagnosis"
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
                project_groups[network_id]["items"][p_name] = {"name": p_name, "containers": [], "tracked": True}
            
            # Fetch latest metrics (Phase 8: High Precision)
            latest_metric = db.query(Metric).filter(Metric.container == c.name).order_by(Metric.timestamp.desc()).first()
            cpu = f"{round(latest_metric.cpu_percent, 2)}%" if latest_metric else "0%"
            mem = f"{round(latest_metric.mem_usage_mb, 2)}MB" if latest_metric else "0MB"
            disk_read = f"{round(latest_metric.disk_read_mb, 2)}MB" if latest_metric else "0MB"
            disk_write = f"{round(latest_metric.disk_write_mb, 2)}MB" if latest_metric else "0MB"

            # Phase 12 & 15: Fetch latest active AI Reasoning
            latest_diag = db.query(Event).filter(
                Event.container == c.name,
                Event.event_type == "diagnosis",
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
                "disk_read": disk_read,
                "disk_write": disk_write,
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

@app.route("/history")
@token_required
def history():
    db = SessionLocal()
    try:
        # Phase 10 & 15: Filter for Active/Open incidents by default
        filter_type = request.args.get("filter", "all")
        query = db.query(Event).filter(
            Event.event_type.in_(["diagnosis", "remediation_attempt", "decision_audit"]),
            Event.status == "open" # Default to open issues
        )
        
        if filter_type == "dlq":
            query = query.filter(text("details->>'is_diagnosable' = 'false'"))
        elif filter_type == "all":
            # Override default filter if user specifically asks for everything
            query = db.query(Event).filter(Event.event_type.in_(["diagnosis", "remediation_attempt"]))

        events = query.order_by(desc(Event.timestamp)).limit(100).all()
        
        results = []
        for e in events:
            res = {
                "container": e.container,
                "project": e.project or "standalone",
                "event": e.event_type,
                "timestamp": e.timestamp.isoformat(),
                "details": e.details
            }
            results.append(res)
            
        return jsonify({"recent": results})
    finally:
        db.close()

@app.route("/diagnostics/<container_name>")
@token_required
def get_diagnostics(container_name):
    db = SessionLocal()
    try:
        # Fetch the latest AI-driven diagnosis for this container
        event = db.query(Event).filter(
            Event.container == container_name,
            Event.event_type == "diagnosis"
        ).order_by(desc(Event.timestamp)).first()

        if not event:
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
            
    app.run(host="0.0.0.0", port=8080, threaded=True)

if __name__ == "__main__":
    start_app()
