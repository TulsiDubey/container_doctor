import os
import docker
import json
from flask import Flask, jsonify, request, session, redirect, send_file
from flask_cors import CORS
from shared.db import SessionLocal, Event, Metric, init_db
from sqlalchemy import desc, func

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

# --- Auth ---

@app.before_request
def require_login():
    # Bypass auth for local development/testing
    if request.remote_addr in ["127.0.0.1", "localhost"]:
        session["authenticated"] = True
        return

    protected_paths = ["/", "/stats", "/projects", "/history"]
    if request.path in protected_paths or request.path.startswith("/diagnostics") or request.path.startswith("/logs"):
        if not session.get("authenticated"):
            if request.path == "/":
                return redirect("/login")
            return jsonify({"error": "Unauthorized"}), 401

@app.route("/login")
def login_page():
    return send_file(os.path.join(STATIC_DIR, "login.html"))

@app.route("/api/login", methods=["POST"])
def perform_login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    try:
        get_docker_client().login(username=username, password=password)
        session["authenticated"] = True
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# --- UI Assets ---

@app.route("/")
def dashboard():
    return send_file(os.path.join(STATIC_DIR, "dashboard.html"))

# --- Data Endpoints ---

@app.route("/stats")
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
            
        return jsonify({
            "total_projects": total_projects,
            "tracked_projects": total_projects, # Defaulting to all for simplicity
            "healthy_containers": healthy,
            "broken_containers": broken
        })
    finally:
        db.close()

@app.route("/projects")
def projects():
    db = SessionLocal()
    try:
        containers = get_docker_client().containers.list(all=True)
        namespaces = {}
        
        for c in containers:
            p_name = c.labels.get('com.docker.compose.project', 'standalone')
            
            # Use 'default' if network is missing
            networks = c.attrs.get('NetworkSettings', {}).get('Networks', {})
            ns_name = list(networks.keys())[0] if networks else "default"
            
            if ns_name not in namespaces:
                namespaces[ns_name] = {"namespace": ns_name, "projects": {}}
            
            if p_name not in namespaces[ns_name]["projects"]:
                namespaces[ns_name]["projects"][p_name] = {"name": p_name, "containers": [], "tracked": True}
            
            # Fetch latest metrics for this container
            latest_metric = db.query(Metric).filter(Metric.container == c.name).order_by(Metric.timestamp.desc()).first()
            cpu = f"{latest_metric.cpu_percent}%" if latest_metric else "0%"
            mem = f"{latest_metric.mem_usage_mb}MB" if latest_metric else "0MB"

            namespaces[ns_name]["projects"][p_name]["containers"].append({
                "id": c.short_id,
                "name": c.name,
                "project": p_name,
                "status": "running" if c.status == "running" else "broken",
                "health": "healthy" if c.status == "running" else "broken",
                "cpu": cpu,
                "ram": mem
            })
            
        # Transform into the list-of-namespaces format expected by frontend
        final_list = []
        for ns_id, ns_data in namespaces.items():
            proj_list = []
            for p_id, p_data in ns_data["projects"].items():
                proj_list.append(p_data)
            final_list.append({"namespace": ns_id, "projects": proj_list})
            
        return jsonify(final_list)
    finally:
        db.close()

@app.route("/history")
def history():
    db = SessionLocal()
    try:
        events = db.query(Event).filter(
            Event.event_type.in_(["diagnosis", "remediation_attempt", "decision_audit"])
        ).order_by(desc(Event.timestamp)).limit(100).all()
        
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
def get_logs(container_name):
    try:
        c = get_docker_client().containers.get(container_name)
        return c.logs(tail=100).decode('utf-8')
    except Exception as e:
        return str(e), 500

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080)
