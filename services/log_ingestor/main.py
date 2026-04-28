import docker
import json
import os
import threading
import time
from confluent_kafka import Producer
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))
IST = timezone(timedelta(hours=5, minutes=30))

# --- Config ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_LOGS = "container-logs"
KAFKA_TOPIC_METRICS = "container-metrics"
TARGET_CONTAINERS = os.getenv("TARGET_CONTAINERS", "").split(",")

def get_kafka_producer():
    conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'client.id': 'log_ingestor',
        # Reliability settings
        'acks': 'all',
        'retries': 5
    }
    return Producer(conf)

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")

def stream_container_logs(container_name, producer):
    client = docker.from_env()
    print(f"Starting log stream for: {container_name}")
    
    try:
        container = client.containers.get(container_name)
        # We start reaching the "now" to avoid re-ingesting historical logs on restart
        # but a small buffer is good for safety.
        for line in container.logs(stream=True, follow=True, tail=10):
            log_line = line.decode('utf-8').strip()
            if not log_line:
                continue
                
            # Metadata injection (Phase 5: Pure Local Sourcing)
            payload = {
                "container": container_name,
                "project": container.labels.get('com.docker.compose.project', 'standalone'),
                "project_cluster": list(container.attrs.get('NetworkSettings', {}).get('Networks', {}).keys())[0] if container.attrs.get('NetworkSettings', {}).get('Networks') else "default",
                "log": log_line,
                "timestamp": datetime.now(IST).isoformat()
            }
            
            producer.produce(
                KAFKA_TOPIC_LOGS, 
                key=container_name, 
                value=json.dumps(payload), 
                callback=delivery_report
            )
            producer.poll(0) # Serve delivery callbacks
            
    except Exception as e:
        print(f"Error streaming logs for {container_name}: {e}")
        time.sleep(20) # Backoff before retry
        stream_container_logs(container_name, producer)

def stream_container_stats(container_name, producer):
    client = docker.from_env()
    print(f"Starting metrics stream for: {container_name}")
    
    try:
        container = client.containers.get(container_name)
        # stats() is a generator yielding real-time resource usage
        for stats in container.stats(decode=True):
            # Safe extraction with defaults
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

                # Disk I/O Extraction (Phase 6: Hardened)
                blkio = stats.get('blkio_stats', {})
                disk_read = 0
                disk_write = 0
                
                # Check recursive first, then fallback to standard (depends on Docker version/driver)
                io_stats = blkio.get('io_service_bytes_recursive') or blkio.get('io_service_bytes') or []
                
                for entry in io_stats:
                    if entry.get('op') == 'Read':
                        disk_read += entry.get('value', 0)
                    elif entry.get('op') == 'Write':
                        disk_write += entry.get('value', 0)

                payload = {
                    "container": container_name,
                    "cpu_percent": round(cpu_percent, 2),
                    "mem_usage_mb": round(mem_stats.get('usage', 0) / (1024 * 1024), 2),
                    "mem_limit_mb": round(mem_stats.get('limit', 1) / (1024 * 1024), 2),
                    "disk_read_mb": round(disk_read / (1024 * 1024), 2),
                    "disk_write_mb": round(disk_write / (1024 * 1024), 2),
                    "timestamp": datetime.now(IST).isoformat()
                }
                
                producer.produce(
                    KAFKA_TOPIC_METRICS,
                    key=container_name,
                    value=json.dumps(payload),
                    callback=delivery_report
                )
            except (KeyError, TypeError) as e:
                print(f"Skipping malformed stats for {container_name}: {e}")
                
            producer.poll(0)
            time.sleep(2)
            
    except Exception as e:
        print(f"Error streaming stats for {container_name}: {e}")
        time.sleep(5)
        stream_container_stats(container_name, producer)
def monitor_docker_events(producer):
    """
    Phase 25: Event-Driven Ingestion.
    Listens to Docker events (stop/start/die) for instant reaction.
    """
    client = docker.from_env()
    print("📡 [LOG_INGESTOR] Event-Driven Sentinel Listening Activated.")
    
    # We filter for stop/die/start/kill events to ensure we only process relevant state changes
    filters = {"event": ["stop", "die", "kill", "start"], "type": "container"}
    
    for event in client.events(decode=True, filters=filters):
        try:
            container_id = event.get("id")
            container_name = event.get("Actor", {}).get("Attributes", {}).get("name")
            action = event.get("Action")
            
            # Remove leading slash if present
            if container_name.startswith("/"): container_name = container_name[1:]
            
            # Phase 37: Exempt Setup utility containers
            if "pull" in container_name or "setup" in container_name or "init" in container_name:
                continue
            
            # Full Architecture Dynamic Forwarding
            target_identity = container_name
            project = event.get("Actor", {}).get("Attributes", {}).get("com.docker.compose.project", "standalone")
            
            if action in ["stop", "die", "kill"]:
                try:
                    c = client.containers.get(container_name)
                    state = c.attrs.get("State", {})
                    exit_code = state.get("ExitCode", "unknown")
                    err_msg = state.get("Error", "No message provided.")
                    # Build an intelligent contextual payload for Groq
                    log_msg = f"[SYSTEM_HEAL] Container crashed. ExitCode: {exit_code}. Docker Error: {err_msg}."
                except:
                    log_msg = f"[SYSTEM_HEAL] Container unexpectedly transitioned to: {action}."
                    
                payload = {
                    "container": target_identity,
                    "project": project,
                    "log": log_msg,
                    "timestamp": datetime.now(IST).isoformat()
                }
                producer.produce(KAFKA_TOPIC_LOGS, key=target_identity, value=json.dumps(payload))
                print(f"🚨 [WATCHDOG] Outage logged for {target_identity}. Pumping to Groq Agent...")
                
            elif action == "start":
                payload = {
                    "container": target_identity,
                    "project": project,
                    "log": f"[SYSTEM_HEALED] Container returned to running via event ({container_name}).",
                    "status": "resolved",
                    "timestamp": datetime.now(IST).isoformat()
                }
                producer.produce(KAFKA_TOPIC_LOGS, key=target_identity, value=json.dumps(payload))
                
            producer.flush()
        except: pass

def main():
    print("Log Ingestor Service Starting (Stability Shield: ON)...")
    
    while True:
        try:
            producer = get_kafka_consumer_producer()
            
            client = docker.from_env()
            threads = []
            
            # Application Logs restrict to TARGET_CONTAINERS for noise reduction
            for name in TARGET_CONTAINERS:
                name = name.strip()
                if not name:
                    continue
                tl = threading.Thread(target=stream_container_logs, args=(name, producer), daemon=True)
                tl.start()
                threads.append(tl)

            # Phase 36: Real-Time Stats for ALL containers to match `docker ps`
            for c in client.containers.list(all=True):
                tm = threading.Thread(target=stream_container_stats, args=(c.name, producer), daemon=True)
                tm.start()
                threads.append(tm)
                
            # Phase 25: Event Monitor Thread
            te = threading.Thread(target=monitor_docker_events, args=(producer,), daemon=True)
            te.start()
            threads.append(te)
                
            # Phase 7 & 15: Proactive Health & Recovery Tracking
            client = docker.from_env()
            last_states = {} # Track states for recovery detection
            
            while True:
                for name in TARGET_CONTAINERS:
                    name = name.strip()
                    if not name: continue
                    
                    try:
                        c = client.containers.get(name)
                        current_status = c.status
                        last_status = last_states.get(name, "running")

                        if current_status != "running":
                            if last_status == "running": # Phase 31: Only trigger on DOWN transition
                                print(f"⚠️ [PRESENCE_PULSE] Detected DOWN node: {name}. Triggering AI Diagnostic...")
                                payload = {
                                    "container": name,
                                    "project": c.labels.get('com.docker.compose.project', 'standalone'),
                                    "log": f"[SYSTEM_HEAL] Container state changed to: {current_status} (Detected via Heartbeat)",
                                    "timestamp": datetime.now(IST).isoformat()
                                }
                                producer.produce(KAFKA_TOPIC_LOGS, key=name, value=json.dumps(payload))
                                producer.flush()
                        
                        # Recovery Detection (Phase 15 & 31)
                        elif current_status == "running" and last_status != "running":
                            print(f"🌲 [RECOVERY] Node {name} has returned to running. Sending Resolve event...")
                            payload = {
                                "container": name,
                                "project": c.labels.get('com.docker.compose.project', 'standalone'),
                                "log": f"[SYSTEM_HEALED] Container has recovered to healthy state.",
                                "status": "resolved",
                                "timestamp": datetime.now(IST).isoformat()
                            }
                            producer.produce(KAFKA_TOPIC_LOGS, key=name, value=json.dumps(payload))
                            producer.flush()
                        
                        last_states[name] = current_status
                    except Exception as e:
                        if name not in last_states: last_states[name] = "running"
                        # Handle case where container is missing (deleted)
                        if "No such container" in str(e) and last_states.get(name) == "running":
                            print(f"🚨 [PRESENCE_PULSE] Node {name} GONE. Triggering Emergency Alert...")
                            payload = {
                                "container": name,
                                "project": "standalone",
                                "log": f"[SYSTEM_HEAL] Container was DELETED or REMOVED.",
                                "timestamp": datetime.now(IST).isoformat()
                            }
                            producer.produce(KAFKA_TOPIC_LOGS, key=name, value=json.dumps(payload))
                            producer.flush()
                            last_states[name] = "deleted"

                producer.flush()
                time.sleep(5) # Phase 31: 5s high-frequency health pulse
        except Exception as e:
            print(f"Ingestor Core Error: {e}. Reconnecting in 10s...")
            time.sleep(10)
        except KeyboardInterrupt:
            print("Shutting down...")
            break

def get_kafka_consumer_producer():
    # Helper to ensure we have a working producer
    return get_kafka_producer()

if __name__ == "__main__":
    main()
