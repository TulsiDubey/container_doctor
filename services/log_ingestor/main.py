import docker
import json
import os
import threading
import time
from confluent_kafka import Producer
from shared.db import SessionLocal, ProjectState
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))

# --- Cache for Tracking ---
untracked_projects_cache = set()
last_cache_update = datetime.now() - timedelta(minutes=1)

def update_tracking_cache():
    global untracked_projects_cache, last_cache_update
    if (datetime.now() - last_cache_update).seconds < 30:
        return
    
    try:
        with SessionLocal() as db:
            untracked = db.query(ProjectState.project_name).filter(ProjectState.is_tracked == False).all()
            untracked_projects_cache = set(p[0] for p in untracked)
            last_cache_update = datetime.now()
    except Exception as e:
        print(f"Failed to update tracking cache: {e}")

def is_project_tracked(project_name):
    update_tracking_cache()
    return project_name not in untracked_projects_cache

# --- Config ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_LOGS = "container-logs"
KAFKA_TOPIC_METRICS = "container-metrics"
TARGET_CONTAINERS = os.getenv("TARGET_CONTAINERS", "").split(",")

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")

# --- Resilient Producer Wrapper ---
class ResilientProducer:
    def __init__(self):
        self.producer = None
        self.local_buffer = [] 
        self.max_buffer = 1000
        self.connect()

    def connect(self):
        try:
            conf = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'client.id': 'log_ingestor',
                'acks': 'all',
                'retries': 5,
                'socket.timeout.ms': 5000,
            }
            self.producer = Producer(conf)
            print("Connected to Kafka Bus.")
        except Exception as e:
            print(f"Kafka Connection Failed: {e}. Ingestor operating in BUFFER mode.")
            self.producer = None

    def produce(self, topic, key, value):
        if self.producer:
            try:
                self.producer.produce(topic, key=key, value=value, callback=delivery_report)
                self.producer.poll(0)
                # Flush buffer if we just reconnected
                if self.local_buffer:
                    print(f"Flushing {len(self.local_buffer)} buffered events...")
                    for t, k, v in self.local_buffer:
                        self.producer.produce(t, key=k, value=v)
                    self.local_buffer = []
            except Exception:
                self._buffer_event(topic, key, value)
        else:
            self._buffer_event(topic, key, value)

    def _buffer_event(self, topic, key, value):
        if len(self.local_buffer) < self.max_buffer:
            self.local_buffer.append((topic, key, value))
        
    def flush(self):
        if self.producer:
            self.producer.flush()

resilient_producer = ResilientProducer()

# --- Global Shared Client ---
_docker_client = None
def get_client():
    global _docker_client
    try:
        if _docker_client is None:
            _docker_client = docker.from_env()
        else:
            _docker_client.ping()
    except Exception:
        _docker_client = docker.from_env()
    return _docker_client

def stream_container_logs(container_name):
    print(f"Starting log stream for: {container_name}")
    while True:
        try:
            client = get_client()
            container = client.containers.get(container_name)
            project_name = container.labels.get('com.docker.compose.project', 'standalone')
            
            # Phase 48: Tracking Enforcement
            if not is_project_tracked(project_name):
                # Only print occasionally to reduce log noise
                if int(time.time()) % 60 == 0:
                    print(f"⏸️ [INGESTOR] Project '{project_name}' is de-linked. Monitoring paused.")
                time.sleep(10)
                continue

            for line in container.logs(stream=True, follow=True, tail=10):
                log_line = line.decode('utf-8').strip()
                if not log_line: continue
                
                payload = {
                    "container": container_name,
                    "project": container.labels.get('com.docker.compose.project', 'standalone'),
                    "log": log_line,
                    "timestamp": datetime.now(IST).isoformat()
                }
                resilient_producer.produce(KAFKA_TOPIC_LOGS, container_name, json.dumps(payload))
        except Exception as e:
            print(f"Log Stream Error ({container_name}): {e}. Retrying...")
            time.sleep(10)

def stream_container_stats(container_name):
    print(f"Starting metrics stream for: {container_name}")
    while True:
        try:
            client = get_client()
            container = client.containers.get(container_name)
            project_name = container.labels.get('com.docker.compose.project', 'standalone')
            
            # Phase 48: Tracking Enforcement
            if not is_project_tracked(project_name):
                time.sleep(60)
                continue

            for stats in container.stats(decode=True):
                try:
                    cpu_stats = stats.get('cpu_stats', {})
                    precpu_stats = stats.get('precpu_stats', {})
                    mem_stats = stats.get('memory_stats', {})
                    
                    cpu_usage = cpu_stats.get('cpu_usage', {}).get('total_usage', 0)
                    precpu_usage = precpu_stats.get('cpu_usage', {}).get('total_usage', 0)
                    system_cpu = cpu_stats.get('system_cpu_usage', 0)
                    presystem_cpu = precpu_stats.get('system_cpu_usage', 0)
                    
                    cpu_delta = cpu_usage - precpu_usage
                    system_delta = system_cpu - presystem_cpu
                    
                    cpu_percent = 0.0
                    if system_delta > 0.0:
                        percpu = cpu_stats.get('cpu_usage', {}).get('percpu_usage')
                        num_cpus = len(percpu) if percpu else 1
                        cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0

                    blkio = stats.get('blkio_stats', {})
                    disk_read = 0
                    disk_write = 0
                    io_stats = blkio.get('io_service_bytes_recursive') or blkio.get('io_service_bytes') or []
                    for entry in io_stats:
                        if entry.get('op') == 'Read': disk_read += entry.get('value', 0)
                        elif entry.get('op') == 'Write': disk_write += entry.get('value', 0)

                    payload = {
                        "container": container_name,
                        "cpu_percent": round(cpu_percent, 2),
                        "mem_usage_mb": round(mem_stats.get('usage', 0) / (1024 * 1024), 2),
                        "mem_limit_mb": round(mem_stats.get('limit', 1) / (1024 * 1024), 2),
                        "disk_read_mb": round(disk_read / (1024 * 1024), 2),
                        "disk_write_mb": round(disk_write / (1024 * 1024), 2),
                        "timestamp": datetime.now(IST).isoformat()
                    }
                    resilient_producer.produce(KAFKA_TOPIC_METRICS, container_name, json.dumps(payload))
                except Exception: pass
                time.sleep(2)
        except Exception as e:
            print(f"Stats Stream Error ({container_name}): {e}. Retrying...")
            time.sleep(10)

def monitor_docker_events():
    print("📡 [SENTINEL] Event Monitor Active.")
    while True:
        try:
            client = get_client()
            filters = {"event": ["stop", "die", "kill", "start"], "type": "container"}
            for event in client.events(decode=True, filters=filters):
                container_name = event.get("Actor", {}).get("Attributes", {}).get("name")
                action = event.get("Action")
                project = event.get("Actor", {}).get("Attributes", {}).get("com.docker.compose.project", "standalone")
                
                if action in ["stop", "die", "kill"]:
                    payload = {
                        "container": container_name,
                        "project": project,
                        "log": f"[SYSTEM_HEAL] Container transitioned to: {action} (Event-Detected)",
                        "timestamp": datetime.now(IST).isoformat()
                    }
                    resilient_producer.produce(KAFKA_TOPIC_LOGS, container_name, json.dumps(payload))
                elif action == "start":
                    payload = {
                        "container": container_name,
                        "project": project,
                        "log": f"[SYSTEM_HEALED] Container returned to running.",
                        "status": "resolved",
                        "timestamp": datetime.now(IST).isoformat()
                    }
                    resilient_producer.produce(KAFKA_TOPIC_LOGS, container_name, json.dumps(payload))
        except Exception as e:
            print(f"Event Monitor Error: {e}. Retrying...")
            time.sleep(5)

def main():
    print("Log Ingestor v35.0 (Stability Shield: ON)")
    
    # Spawn Threads Once
    spawned_containers = set()
    
    # 1. Start Event Monitor
    threading.Thread(target=monitor_docker_events, daemon=True).start()
    
    while True:
        try:
            client = get_client()
            # 2. Dynamic Container Discovery
            for container in client.containers.list(all=True):
                if container.name not in spawned_containers:
                    threading.Thread(target=stream_container_stats, args=(container.name,), daemon=True).start()
                    if container.name in TARGET_CONTAINERS:
                        threading.Thread(target=stream_container_logs, args=(container.name,), daemon=True).start()
                    spawned_containers.add(container.name)
            
            # 3. Heartbeat Pulse
            resilient_producer.flush()
            time.sleep(10)
        except Exception as e:
            print(f"Main Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
