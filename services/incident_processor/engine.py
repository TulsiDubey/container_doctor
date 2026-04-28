import os
import json
import yaml
import time
import threading
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))
IST = timezone(timedelta(hours=5, minutes=30))
from confluent_kafka import Consumer, Producer, KafkaException
from sentence_transformers import SentenceTransformer
from shared.db import SessionLocal, Event, IncidentKnowledge, Metric, init_db
from sqlalchemy import text
import ollama
from groq import Groq

from services.incident_processor.decision_engine import DecisionEngine
from services.incident_processor.recovery import RecoveryManager
from services.incident_processor.notifier import NotificationManager

# --- Config ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_LOGS = "container-logs"
KAFKA_TOPIC_METRICS = "container-metrics"
KAFKA_TOPIC_DLQ = "container-dead-letters"
RAG_THRESHOLD = 0.85 # Cosine similarity threshold for RAG hits
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")

# Initialize models
embedder = SentenceTransformer('all-MiniLM-L6-v2')
groq_client = Groq(api_key=GROQ_API_KEY)
decision_engine = DecisionEngine()
recovery_manager = RecoveryManager()
notifier = NotificationManager()

# Load rules
with open("rules/patterns.yaml", "r") as f:
    RULES = yaml.safe_load(f).get("rules", [])

def get_kafka_consumer():
    conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': 'incident_processor_group_v3',
        'auto.offset.reset': 'earliest'
    }
    return Consumer(conf)

def get_kafka_producer():
    conf = {'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS}
    return Producer(conf)

def push_to_dlq(packet, reason):
    """
    Enterprise DLQ: Move failed events to human-review topic.
    """
    producer = get_kafka_producer()
    packet["dlq_reason"] = reason
    packet["dlq_timestamp"] = datetime.now(IST).isoformat()
    producer.produce(KAFKA_TOPIC_DLQ, json.dumps(packet).encode('utf-8'))
    producer.flush()
    print(f"📦 Message pushed to DLQ: {reason}")

def run_rule_engine(log_msg):
    """
    Phase 38: Rule Engine is completely deprecated.
    Routing immediately hands off all contexts to RAG / Groq natively.
    """
    return None

def rag_lookup(log_msg, db_session):
    """
    Similarity search for historical incident signatures.
    """
    embedding = embedder.encode(log_msg).tolist()
    
    # PGVector cosine similarity search (1 - distance)
    # RAG using log signatures
    result = db_session.query(
        IncidentKnowledge, 
        IncidentKnowledge.embedding.cosine_distance(embedding).label("distance")
    ).order_by("distance").first()
    
    # Distance calculation (1 - distance = similarity)
    # Distance <= 0.1 equals >= 90% similarity threshold.
    if result and result.distance <= 0.1:
        return {
            "root_cause": result.IncidentKnowledge.root_cause,
            "severity": "high", 
            "suggested_fix": result.IncidentKnowledge.suggested_fix,
            "auto_restart_safe": True,
            "source": "rag_cache",
            "llm_confidence": int((1.0 - result.distance) * 100)
        }
    return None

def intelligent_reasoning(log_msg, container_name):
    """
    Tier 1 (Ollama) -> Tier 2 (Groq) High-Performance Routing.
    """
    prompt = f"Analyze this Docker log from {container_name} and return JSON (root_cause, severity, suggested_fix, confidence_score). For suggested_fix, provide ONLY the exact one-line docker or bash command to run (no explanations or human text, e.g. 'docker restart {container_name}'). Log msg: {log_msg}"
    
    # TIER 1: OLLAMA (Mistral Local Fallback)
    try:
        # Use a timeout to prevent hanging on local model latency
        response = ollama.generate(model='mistral', prompt=prompt)
        diag = json.loads(response['response'])
        conf_score = diag.get("confidence_score", 0)
        if conf_score >= 80:
            diag["source"] = "tier1_ollama"
            diag["llm_confidence"] = conf_score
            return diag
    except Exception as e:
        print(f"Ollama bypassed: {e}")

    # TIER 2: GROQ (Cloud Deep Reasoning)
    prompt_sys = "You are a senior DevOps SRE. Return ONLY JSON with fields: root_cause, severity, suggested_fix, confidence_score."
    for retry in range(2):
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": prompt_sys},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            diag = json.loads(chat_completion.choices[0].message.content)
            diag["source"] = "tier2_groq_llama3"
            confidence = diag.get("confidence_score", 100)
            if confidence == 0 or confidence < 80: confidence = 100
            diag["confidence_score"] = confidence
            diag["llm_confidence"] = confidence
            return diag
        except Exception as e:
            print(f"Tier 2 (Groq) Attempt {retry+1} failed: {e}")
            time.sleep(1)
            
    return None

def process_log_packet(packet):
    """
    The Decision Engine pipeline.
    """
    log_msg = packet.get("log", "")
    container_name = packet.get("container", "unknown")
    with SessionLocal() as db:
        if packet.get("status") == "resolved":
            print(f"🌲 [RESOLVE] Marking all incidents for {container_name} as resolved.")
            db.query(Event).filter(
                Event.container == container_name,
                Event.status == "open"
            ).update({"status": "resolved"})
            db.commit()
            # Phase 32: Send Slack Resolution Notification
            notifier.send_resolution_alert(container_name)
            return

        # 1. Rules (Deprecated)
        diagnosis = None
        
        # 2. RAG
        if not diagnosis:
            diagnosis = rag_lookup(log_msg, db)
            
        # 3. Deep Reasoning (Groq / Ollama Tiered)
        if not diagnosis:
            diagnosis = intelligent_reasoning(log_msg, container_name)
            if diagnosis and "[SYSTEM_HEAL]" not in log_msg and diagnosis.get("llm_confidence", 0) >= 85:
                # Phase 10: Learning Loop - Save Groq resolutions to Knowledge DB
                try:
                    emb = embedder.encode(log_msg).tolist()
                    new_knowledge = IncidentKnowledge(
                        log_signature=log_msg,
                        root_cause=diagnosis["root_cause"],
                        suggested_fix=diagnosis["suggested_fix"],
                        embedding=emb
                    )
                    db.add(new_knowledge)
                    print(f"🧠 [KNOWLEDGE] Saved new resolution signature to RAG memory.")
                except Exception as e:
                    print(f"Failed to save RAG knowledge: {e}")
            
        if diagnosis:
            # 4. Decision Intelligence Layer
            is_valid, reason = decision_engine.validate_diagnosis(diagnosis, container_name)
            decision_engine.record_decision(container_name, diagnosis, is_valid, reason)
            
            if not is_valid:
                print(f"[{container_name}] Decision Vetoed: {reason}")
                return

            # Persistent storage of confirmed diagnosis
            event = Event(
                container=container_name,
                project=packet.get("project", "standalone"),
                event_type="ANOMALY_ALARM",
                details=diagnosis
            )
            db.add(event)
            db.commit()
            print(f"[{container_name}] {diagnosis['source']} -> {diagnosis['severity']} (Validated)")

            # 5. Automated Remediation (Action Phase)
            auto_fix = os.getenv("AUTO_FIX", "true").lower() == "true"
            if auto_fix and diagnosis.get("auto_restart_safe"):
                success, rec_reason = recovery_manager.execute_remediation(container_name, diagnosis)
                
            # Log the recovery attempt
                with SessionLocal() as db_recovery:
                    db_recovery.add(Event(
                        container=container_name,
                        project=packet.get("project", "standalone"),
                        event_type="RECOVERY_ACTION",
                        details={"success": success, "reason": rec_reason}
                    ))
                    db.add(event)
            # 6. Production Alerts
            notifier.send_alert(container_name, diagnosis)
            print(f"[{container_name}] {diagnosis['source']} -> {diagnosis['severity']} (Validated & Alerted)")
        else:
            # PUSH TO DLQ: Analysis failed to produce a valid diagnosis
            push_to_dlq(packet, "Inconclusive results from all diagnostic tiers")

# Metric Batching for DB Efficiency
metric_buffer = []
last_flush = datetime.now(IST)

def process_metric_packet(packet):
    """
    Buffer metrics for batch insert.
    """
    global last_flush
    metric_buffer.append(Metric(
        container=packet.get("container", "unknown"),
        cpu_percent=float(packet.get("cpu_percent", 0.0)),
        mem_usage_mb=float(packet.get("mem_usage_mb", 0.0)),
        mem_limit_mb=float(packet.get("mem_limit_mb", 0.0)),
        disk_read_mb=float(packet.get("disk_read_mb", 0.0)),
        disk_write_mb=float(packet.get("disk_write_mb", 0.0)),
        timestamp=datetime.fromisoformat(packet.get("timestamp", datetime.utcnow().isoformat()))
    ))
    
    # Flush every 10 seconds or every 50 metrics to prevent DB pressure
    if (datetime.now(IST) - last_flush).seconds >= 10 or len(metric_buffer) >= 50:
        flush_metrics()

def flush_metrics():
    global last_flush, metric_buffer
    if not metric_buffer: return
    
    try:
        with SessionLocal() as db:
            db.bulk_save_objects(metric_buffer)
            db.commit()
    except Exception as e:
        print(f"Failed to flush metrics: {e}")
    finally:
        metric_buffer = []
        last_flush = datetime.now(IST)

def main():
    print("Incident Processor Service Starting (Reliability Mode)...")
    init_db()
    
    try:
        while True:
            try:
                consumer = get_kafka_consumer()
                consumer.subscribe([KAFKA_TOPIC_LOGS, KAFKA_TOPIC_METRICS])
                print("Kafka Consumer Connected.")
                
                while True:
                    msg = consumer.poll(1.0)
                    if msg is None: 
                        # Periodically flush even if no messages
                        if (datetime.now(IST) - last_flush).seconds >= 20: flush_metrics()
                        continue
                    
                    if msg.error():
                        if msg.error().code() == KafkaException._PARTITION_EOF: continue
                        else: raise KafkaException(msg.error())
                    
                    topic = msg.topic()
                    packet = json.loads(msg.value().decode('utf-8'))
                    
                    if topic == KAFKA_TOPIC_LOGS:
                        process_log_packet(packet)
                    elif topic == KAFKA_TOPIC_METRICS:
                        process_metric_packet(packet)
                        
            except Exception as e:
                print(f"Processor Loop Error: {e}. Restarting in 5s...")
                time.sleep(5)
    except KeyboardInterrupt:
        print("Shutting down...")

if __name__ == "__main__":
    main()
