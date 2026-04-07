import docker
import json
import os
import threading
import time
from confluent_kafka import Producer
from datetime import datetime

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
                
            # Metadata injection
            payload = {
                "container": container_name,
                "project": container.labels.get('com.docker.compose.project', 'standalone'),
                "namespace": list(container.attrs.get('NetworkSettings', {}).get('Networks', {}).keys())[0] if container.attrs.get('NetworkSettings', {}).get('Networks') else "default",
                "log": log_line,
                "timestamp": datetime.utcnow().isoformat()
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
        time.sleep(5) # Backoff before retry
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

                payload = {
                    "container": container_name,
                    "cpu_percent": round(cpu_percent, 2),
                    "mem_usage_mb": round(mem_stats.get('usage', 0) / (1024 * 1024), 2),
                    "mem_limit_mb": round(mem_stats.get('limit', 1) / (1024 * 1024), 2),
                    "timestamp": datetime.utcnow().isoformat()
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
    print("Log Ingestor Service Starting...")
    producer = get_kafka_producer()
    
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
        
    try:
        while True:
            producer.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")

if __name__ == "__main__":
    main()
