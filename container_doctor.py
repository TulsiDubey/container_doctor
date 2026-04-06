import docker
import json
import time
import logging
import os
import requests
import smtplib
import psycopg2
from psycopg2.extras import RealDictCursor
from email.message import EmailMessage
from datetime import datetime, timedelta
from collections import defaultdict
from threading import Thread
from flask import Flask, jsonify, send_file, request, session, redirect
import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

docker_client = None

# --- Config ---
TARGET_CONTAINERS = os.getenv("TARGET_CONTAINERS", "").split(",")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10"))
LOG_LINES = int(os.getenv("LOG_LINES", "50"))
AUTO_FIX = os.getenv("AUTO_FIX", "true").lower() == "true"
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
MAX_DIAGNOSES = int(os.getenv("MAX_DIAGNOSES_PER_HOUR", "20"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_RECIPIENT = os.getenv("SMTP_RECIPIENT", "")

# --- State tracking (Rate limits only) ---
last_error_seen = {}
rate_limit_counter = defaultdict(int)
rate_limit_reset = datetime.now() + timedelta(hours=1)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "docker_agent_secure_default_key_991823")

@app.before_request
def require_login():
    protected_paths = ["/", "/stats", "/projects", "/history"]
    if request.path in protected_paths or request.path.startswith("/diagnostics") or request.path.startswith("/logs"):
        if not session.get("authenticated"):
            if request.path == "/":
                return redirect("/login")
            return jsonify({"error": "Unauthorized"}), 401

@app.route("/login")
def login_page():
    return send_file("login.html")

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
        logger.error(f"Docker Hub Login Failed: {str(e)}")
        return jsonify({"success": False, "error": "Invalid Docker Registry Credentials"}), 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# --- Database ---
db_queue = []

def flush_db_queue():
    global db_queue
    if not db_queue:
        return
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                to_remove = []
                for q in list(db_queue):
                    try:
                        if q['type'] == 'event':
                            cur.execute("INSERT INTO events (container, event, details, timestamp) VALUES (%s, %s, %s, %s)",
                                        (q['container'], q['event'], json.dumps(q['details']), q['timestamp']))
                        elif q['type'] == 'restart':
                            cur.execute("""
                                INSERT INTO container_state (container, restart_count, last_restart) 
                                VALUES (%s, 1, %s)
                                ON CONFLICT (container) DO UPDATE 
                                SET restart_count = container_state.restart_count + 1,
                                    last_restart = EXCLUDED.last_restart
                            """, (q['container'], q['timestamp']))
                        to_remove.append(q)
                    except Exception as loop_e:
                        logger.error(f"Failed to flush item: {loop_e}")
                        to_remove.append(q)
                
                for r in to_remove:
                    if r in db_queue:
                        db_queue.remove(r)
            conn.commit()
        except Exception as e:
            logger.error(f"DB Flush Error: {e}")
        finally:
            conn.close()

def get_db_connection():
    if not DATABASE_URL:
        # Fallback if unconfigured
        logger.warning("DATABASE_URL not set.")
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"DB Connect Error: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id SERIAL PRIMARY KEY,
                        container VARCHAR(255),
                        event VARCHAR(255),
                        details JSONB,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS container_state (
                        container VARCHAR(255) PRIMARY KEY,
                        restart_count INT DEFAULT 0,
                        last_restart TIMESTAMP
                    );
                """)
                cur.execute("DROP TABLE IF EXISTS tracked_pods;") # Cleanup old schema
                cur.execute("DROP TABLE IF EXISTS tracked_projects;") # Force refresh for naming sync
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tracked_projects (
                        project VARCHAR(255) PRIMARY KEY,
                        tracked BOOLEAN DEFAULT TRUE
                    );
                """)
            conn.commit()
        except Exception as e:
            logger.error(f"DB Init Error: {e}")
        finally:
            conn.close()

def init_db_with_retry():
    max_retries = 10
    for i in range(max_retries):
        try:
            init_db()
            logger.info("Database initialized successfully.")
            return
        except Exception as e:
            logger.error(f"DB Init attempt {i+1} failed: {e}")
            time.sleep(5)
    logger.error("DB Init failed after multiple retries.")

init_db_with_retry()

tracked_projects_cache = None

def get_tracked_projects():
    global tracked_projects_cache
    if tracked_projects_cache is not None:
        return tracked_projects_cache
    tracked_projects_cache = {}
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT project, tracked FROM tracked_projects")
                for row in cur.fetchall():
                    tracked_projects_cache[row[0]] = row[1]
        finally:
            conn.close()
    return tracked_projects_cache

def set_project_tracking(project, tracked):
    global tracked_projects_cache
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO tracked_projects (project, tracked) VALUES (%s, %s) ON CONFLICT (project) DO UPDATE SET tracked = EXCLUDED.tracked", (project, tracked))
            conn.commit()
            if tracked_projects_cache is not None:
                tracked_projects_cache[project] = tracked
        finally:
            conn.close()

def record_event(container_name, event_type, details):
    timestamp = datetime.now()
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO events (container, event, details, timestamp) VALUES (%s, %s, %s, %s)",
                    (container_name, event_type, json.dumps(details), timestamp)
                )
            conn.commit()
            flush_db_queue()
        except Exception as e:
            logger.error(f"DB Record Event Error: {e}")
            db_queue.append({'type': 'event', 'container': container_name, 'event': event_type, 'details': details, 'timestamp': timestamp})
        finally:
            conn.close()
    else:
        db_queue.append({'type': 'event', 'container': container_name, 'event': event_type, 'details': details, 'timestamp': timestamp})

def check_can_restart(container_name):
    conn = get_db_connection()
    if not conn:
        return True
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM container_state WHERE container = %s", (container_name,))
            row = cur.fetchone()
            if not row:
                return True
            last_restart = row['last_restart']
            if last_restart and last_restart > datetime.now() - timedelta(hours=1):
                return False
            return True
    finally:
        conn.close()

def record_restart(container_name):
    timestamp = datetime.now()
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO container_state (container, restart_count, last_restart) 
                    VALUES (%s, 1, %s)
                    ON CONFLICT (container) DO UPDATE 
                    SET restart_count = container_state.restart_count + 1,
                        last_restart = EXCLUDED.last_restart
                """, (container_name, timestamp, timestamp))
            conn.commit()
            flush_db_queue()
        except Exception as e:
            db_queue.append({'type': 'restart', 'container': container_name, 'timestamp': timestamp})
        finally:
            conn.close()
    else:
        db_queue.append({'type': 'restart', 'container': container_name, 'timestamp': timestamp})

def get_restart_count(container_name):
    count = 0
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT restart_count FROM container_state WHERE container = %s", (container_name,))
                row = cur.fetchone()
                count = row['restart_count'] if row else 0
        finally:
            conn.close()
            
    count += len([q for q in db_queue if q['type'] == 'restart' and q['container'] == container_name])
    return count


def get_docker_client():
    global docker_client
    if docker_client is None:
        docker_client = docker.from_env()
    return docker_client

def get_container_logs(container_name):
    try:
        container = get_docker_client().containers.get(container_name)
        logs = container.logs(
            tail=LOG_LINES,
            timestamps=True
        ).decode("utf-8")
        return logs
    except:
        return None

def detect_errors(logs):
    error_patterns = [
        "error","exception","traceback","failed","crash",
        "fatal","panic","out of memory","killed","timeout",
        "permission denied","errno","500","302"
    ]
    logs_lower = logs.lower()
    return [p for p in error_patterns if p in logs_lower]

error_cache = {}

def is_new_error(container_name, error_patterns):
    pattern_key = ','.join(sorted(error_patterns))
    key = f"{container_name}:{pattern_key}"
    if key in error_cache:
        if datetime.now() < error_cache[key]:
            return False
    error_cache[key] = datetime.now() + timedelta(hours=1)
    return True

def check_rate_limit():
    global rate_limit_counter, rate_limit_reset

    if datetime.now() > rate_limit_reset:
        rate_limit_counter.clear()
        rate_limit_reset = datetime.now() + timedelta(hours=1)

    return sum(rate_limit_counter.values()) < MAX_DIAGNOSES

def diagnose_with_gemini(container_name, logs, error_patterns):
    if not check_rate_limit():
        return None

    rate_limit_counter[container_name] += 1

    prompt = f"""
Container: {container_name}
Errors: {error_patterns}
Logs:
{logs}

Return pure JSON without any markdown formatting:
{{
  "root_cause": "Detailed explanation of the issue.",
  "severity": "low|medium|high",
  "suggested_fix": "High level fix.",
  "auto_restart_safe": true,
  "config_suggestions": ["ENV_VAR=value"],
  "likely_recurring": true,
  "estimated_impact": "Details of impact.",
  "target_file": "/path/example.py",
  "exact_changes": "Change X to Y"
}}
"""

    try:
        res = model.generate_content(prompt)
        txt = res.text
        return json.loads(txt[txt.find("{"):txt.rfind("}")+1])
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None

def apply_fix(container_name, diagnosis):
    if not AUTO_FIX:
        return False
    if not diagnosis.get("auto_restart_safe"):
        return False
    
    if not check_can_restart(container_name):
        return False

    try:
        c = get_docker_client().containers.get(container_name)
        c.restart()
        record_restart(container_name)

        record_event(container_name, "restart", {
            "reason": diagnosis.get("root_cause")
        })

        return True
    except Exception as e:
        record_event(container_name, "restart_failed", {"error": str(e)})
        return False

def get_container_infrastructure(container_name):
    try:
        c = get_docker_client().containers.get(container_name)
        project = c.labels.get('com.docker.compose.project', 'standalone')
        networks = c.attrs.get('NetworkSettings', {}).get('Networks', {})
        namespace = list(networks.keys())[0] if networks else "default-net"
        return namespace, project
    except:
        return "Unknown", "Unknown"

def send_slack_alert(container_name, diagnosis, extra=""):
    if not SLACK_WEBHOOK:
        return
    namespace, project = get_container_infrastructure(container_name)
    try:
        requests.post(SLACK_WEBHOOK, json={
            "text":
            f"🚨 *Container Doctor Alert: {container_name}*\n"
            f"• *Namespace/Cluster*: `{namespace}`\n"
            f"• *Docker project*: `{project}`\n\n"
            f"*Severity*: {str(diagnosis.get('severity', 'Unknown')).upper()}\n"
            f"*Root Cause*: {diagnosis.get('root_cause', 'N/A')}\n"
            f"*Suggested Fix*: {diagnosis.get('suggested_fix', 'N/A')}\n"
            f"*Impact*: {diagnosis.get('estimated_impact', 'N/A')}\n"
            f"*Safe to Auto-Restart*: {diagnosis.get('auto_restart_safe', 'Unknown')}\n"
            f"*Configurations Needed*: {diagnosis.get('config_suggestions', [])}\n"
            f"_{extra}_"
        })
    except:
        pass

def send_email_alert(container_name, diagnosis):
    if not SMTP_SERVER or not SMTP_RECIPIENT:
        return
    namespace, project = get_container_infrastructure(container_name)
    try:
        msg = EmailMessage()
        sev_label = "HIGH SEVERITY Alert" if diagnosis.get('severity') != "resolved" else "RESOLVED Alert"
        msg['Subject'] = f"{sev_label}: {container_name} [{project}]"
        msg['From'] = SMTP_USER
        msg['To'] = SMTP_RECIPIENT
        msg.set_content(
            f"Docker Agent Diagnostic Report\n"
            f"=================================\n"
            f"Container: {container_name}\n"
            f"Namespace: {namespace}\n"
            f"project Group: {project}\n\n"
            f"Severity: {str(diagnosis.get('severity', 'Unknown')).upper()}\n\n"
            f"Root Cause:\n{diagnosis.get('root_cause', 'N/A')}\n\n"
            f"Recommended Fix:\n{diagnosis.get('suggested_fix', 'N/A')}\n\n"
            f"Expected Impact:\n{diagnosis.get('estimated_impact', 'N/A')}\n\n"
            f"Auto-Restart Safe: {diagnosis.get('auto_restart_safe', 'Unknown')}\n"
            f"Likely Recurring: {diagnosis.get('likely_recurring', 'Unknown')}\n"
            f"Configuration Fixes: {diagnosis.get('config_suggestions', [])}\n\n"
            f"Target Code File: {diagnosis.get('target_file', 'None')}\n"
            f"Exact Changes Required:\n{diagnosis.get('exact_changes', 'None')}\n"
        )
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
    except Exception as e:
        logger.error(f"SMTP Error: {e}")

# ------------- ROUTES -------------

@app.route("/")
def index():
    return send_file("dashboard.html")

@app.route("/health")
def health():
    containers_status = {}

    for name in TARGET_CONTAINERS:
        name = name.strip()
        if not name:
            continue
        try:
            c = get_docker_client().containers.get(name)
            c.reload()
            containers_status[name] = {
                "status": c.status,
                "restarts": get_restart_count(name)
            }
        except:
            containers_status[name] = {
                "status": "not_found",
                "restarts": 0
            }

    events_count = len([q for q in db_queue if q['type'] == 'event'])
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM events")
                events_count += cur.fetchone()[0]
        finally:
            conn.close()

    return jsonify({
        "containers": containers_status,
        "events": events_count,
        "timestamp": datetime.now().isoformat()
    })

from flask import request

@app.route("/history")
def history():
    conn = get_db_connection()
    recent = []
    
    mem_events = [q for q in db_queue if q['type'] == 'event']
    events_count = len(mem_events)

    target_date = request.args.get('date', None)
    
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if target_date:
                    cur.execute("SELECT COUNT(*) as count FROM events WHERE DATE(timestamp) = %s", (target_date,))
                else:
                    cur.execute("SELECT COUNT(*) as count FROM events")
                events_count += cur.fetchone()['count']

                if target_date:
                    cur.execute("SELECT container, event, details, timestamp FROM events WHERE DATE(timestamp) = %s ORDER BY timestamp DESC LIMIT 50", (target_date,))
                else:    
                    cur.execute("SELECT container, event, details, timestamp FROM events ORDER BY timestamp DESC LIMIT 50")
                for row in cur.fetchall():
                    item = dict(row)
                    item['timestamp'] = item['timestamp'].isoformat()
                    recent.append(item)
        except Exception as e:
            logger.error(f"DB History Error: {e}")
        finally:
            conn.close()

    for m in mem_events:
        # Simple date filtering for in-memory queue
        if target_date and not m['timestamp'].isoformat().startswith(target_date):
            continue
        recent.append({
            'container': m['container'],
            'event': m['event'],
            'details': m['details'],
            'timestamp': m['timestamp'].isoformat()
        })
    recent.sort(key=lambda x: str(x['timestamp']), reverse=True)
    recent = recent[:50]

    return jsonify({
        "total_events": events_count,
        "recent": recent
    })


@app.route("/stats")
def stats():
    try:
        tp = get_tracked_projects()
        containers = get_docker_client().containers.list(all=True)
        total_projects = len(set(c.labels.get('com.docker.compose.project', 'standalone') for c in containers))
        tracked = sum(1 for p, t in tp.items() if t)
        
        healthy = 0
        broken = 0
        for c in containers:
            status = "healthy"
            diagnostics = incident_state.get(c.name, {})
            if c.status in ["exited", "dead", "created"] or diagnostics.get("status") == "broken":
                status = "broken"
            if status == "healthy":
                healthy += 1
            else:
                broken += 1
                
        return jsonify({
            "total_projects": total_projects,
            "tracked_projects": tracked,
            "healthy_containers": healthy,
            "broken_containers": broken
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/projects")
def projects():
    try:
        tp = get_tracked_projects()
        # Orchestrator grouping: Namespace -> project (Project) -> Containers
        namespaces = {}

        for c in get_docker_client().containers.list(all=True):
            project = c.labels.get('com.docker.compose.project', 'standalone')
            
            networks = c.attrs.get('NetworkSettings', {}).get('Networks', {})
            namespace = list(networks.keys())[0] if networks else "default-net"
            
            if project not in tp:
                set_project_tracking(project, True)
                tp = get_tracked_projects()
                
            if namespace not in namespaces:
                namespaces[namespace] = {}
                
            if project not in namespaces[namespace]:
                namespaces[namespace][project] = {
                    "name": project,
                    "tracked": tp.get(project, True),
                    "containers": []
                }
                
            status = "healthy"
            diagnostics = incident_state.get(c.name, {})
            if c.status in ["exited", "dead", "created"] or diagnostics.get("status") == "broken":
                status = "broken"
                
            namespaces[namespace][project]["containers"].append({
                "name": c.name,
                "status": c.status,
                "health": status,
                "project": ', '.join(c.image.tags) if c.image.tags else c.image.short_id
            })
            
        payload = []
        for ns, projects_dict in namespaces.items():
            payload.append({
                "namespace": ns,
                "projects": list(projects_dict.values())
            })
            
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/projects/track/<project>", methods=["POST"])
def toggle_project_tracking(project):
    try:
        data = request.json
        tracked = data.get('tracked', True)
        set_project_tracking(project, tracked)
        return jsonify({"project": project, "tracked": tracked})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/diagnostics/<container_name>")
def get_diagnosis(container_name):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Look for explicit Gemini Diagnosis
                cur.execute("SELECT details FROM events WHERE container = %s AND event = 'diagnosis' ORDER BY timestamp DESC LIMIT 1", (container_name,))
                row = cur.fetchone()
                if row:
                    return jsonify(row['details'])
                
                # 2. Fallback to generic System Errors if Gemini didn't fire
                cur.execute("SELECT event, details FROM events WHERE container = %s AND event IN ('restart_failed', 'status_check_failed', 'container_down') ORDER BY timestamp DESC LIMIT 1", (container_name,))
                sys_row = cur.fetchone()
                if sys_row:
                    err_text = sys_row['details'].get('error', sys_row['details'].get('status', 'Unknown system failure'))
                    fallback = {
                        "root_cause": f"System Check Failed ({sys_row['event']}): {err_text}",
                        "severity": "high",
                        "suggested_fix": "Review Docker daemon logs, check port allocations, or verify project architecture.",
                        "auto_restart_safe": False,
                        "config_suggestions": ["Restart Docker Service", "Check Port Bindings"],
                        "likely_recurring": True,
                        "estimated_impact": "Container failed to initialize or mount."
                    }
                    return jsonify(fallback)

                return jsonify({"error": "No diagnostics found"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
    return jsonify({"error": "DB disconnected"}), 500

@app.route("/logs/<container_name>")
def current_logs(container_name):
    try:
        c = get_docker_client().containers.get(container_name)
        logs = c.logs(tail=100, timestamps=True).decode("utf-8")
        return jsonify({"container": container_name, "logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


incident_state = {}

def monitor_containers():
    # Wait for DB to be initialized and accessible
    time.sleep(5)
    global incident_state
    
    while True:
        try:
            containers = get_docker_client().containers.list(all=True)
        except Exception as e:
            logger.error(f"Failed to fetch docker containers: {e}")
            time.sleep(5)
            continue

        for c in containers:
            container_name = c.name
            project = c.labels.get('com.docker.compose.project', 'standalone')
            
            tp = get_tracked_projects()
            if project not in tp:
                set_project_tracking(project, True)
                tp = get_tracked_projects()
                
            if not tp.get(project, True):
                continue # Skip untracked projects from engaging with Gemini or Auto-restarts.

            # CONTAINER DOWN DETECTION
            try:
                c.reload()

                if c.status in ["exited", "dead", "created"]:
                    incident_state[container_name] = {'status': 'broken', 'healthy_checks': 0}
                    logger.warning(f"Detected status {c.status} for {container_name}")

                    record_event(container_name, "container_down", {
                        "status": c.status
                    })

                    if check_can_restart(container_name):
                        c.restart()
                        record_restart(container_name)
                        rcount = get_restart_count(container_name)
                        logger.info(f"Restart count for {container_name}: {rcount}")
                        record_event(container_name, "auto_restart", {
                            "status": "success",
                            "restart_count": rcount
                        })
                    else:
                        logger.warning(f"Skipping restart (loop prevention) for {container_name}")
                        send_slack_alert(
                            container_name, 
                            {"severity": "medium", "root_cause": "Container stuck in crash loop. Auto-restart skipped.", "suggested_fix": "Manual intervention required."}, 
                            extra="Loop Prevented"
                        )
                    continue
            except Exception as e:
                logger.error(f"Status check failed for {container_name}: {e}")
                record_event(container_name, "status_check_failed", {"error": str(e)})
                continue

            logs = get_container_logs(container_name)
            if logs is None:
                continue

            error_patterns = detect_errors(logs)
            is_new = False
            if error_patterns:
                is_new = is_new_error(container_name, error_patterns)

            # If no errors OR the errors are completely stale (already processed)
            if not error_patterns or not is_new:
                if incident_state.get(container_name, {}).get('status') == 'broken':
                    incident_state.setdefault(container_name, {})['healthy_checks'] += 1
                    if incident_state[container_name]['healthy_checks'] >= 3:
                        incident_state[container_name] = {'status': 'healthy', 'healthy_checks': 0}
                        record_event(container_name, "resolved", {"message": "Container has recovered and is healthy."})
                        send_slack_alert(container_name, {"severity": "low", "root_cause": "System healed.", "estimated_impact": "None"}, extra="RESOLVED: Healthy Again! 🟢")
                        send_email_alert(container_name, {"severity": "resolved", "root_cause": "State Recovered", "suggested_fix": "None", "config_suggestions": [], "target_file": "", "exact_changes": "", "estimated_impact": "Operations restored."})
                if not is_new and error_patterns:
                    continue # Skip Gemini for stale errors
                continue
            
            incident_state[container_name] = {'status': 'broken', 'healthy_checks': 0}

            logger.warning(f"Errors detected in {container_name}: {error_patterns}")
            # Silently handle the patterns without logging them directly into History

            diagnosis = diagnose_with_gemini(container_name, logs, error_patterns)
            if not diagnosis:
                continue

            record_event(container_name, "diagnosis", diagnosis)
            logger.info(f"{container_name}: {diagnosis.get('severity')}")

            fixed = False
            if diagnosis.get("severity") == "high":
                fixed = apply_fix(container_name, diagnosis)

            sev = diagnosis.get("severity", "").lower()
            if sev in ["medium", "high"]:
                send_slack_alert(
                    container_name, diagnosis,
                    extra="Auto-restarted" if fixed else ""
                )

            if sev == "high":
                send_email_alert(container_name, diagnosis)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080), daemon=True).start()
    monitor_containers()