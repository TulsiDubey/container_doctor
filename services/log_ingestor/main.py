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

def main():
    print("Log Ingestor Service Starting (Stability Shield: ON)...")
    
    while True:
        try:
            producer = get_kafka_consumer_producer()
            
            threads = []
            for name in TARGET_CONTAINERS:
                name = name.strip()
                if not name:
                    continue
                # Logs thread
                tl = threading.Thread(target=stream_container_logs, args=(name, producer), daemon=True)
                tl.start()
                threads.append(tl)

                # Metrics thread
                tm = threading.Thread(target=stream_container_stats, args=(name, producer), daemon=True)
                tm.start()
                threads.append(tm)
                
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
                            print(f"⚠️ [HEARTBEAT] Detected DOWN node: {name}. Triggering AI Diagnostic...")
                            payload = {
                                "container": name,
                                "project": c.labels.get('com.docker.compose.project', 'standalone'),
                                "log": f"[SYSTEM_HEAL] Container state changed to: {current_status}",
                                "timestamp": datetime.now(IST).isoformat()
                            }
                            producer.produce(KAFKA_TOPIC_LOGS, key=name, value=json.dumps(payload))
                        
                        # Recovery Detection (Phase 15)
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
                        
                        last_states[name] = current_status
                    except Exception as e:
                        print(f"Heartbeat error for {name}: {e}")

                producer.flush()
                time.sleep(10) # 10s health check interval
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
