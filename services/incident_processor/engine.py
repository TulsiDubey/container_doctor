import os
import json
import yaml
import time
import threading
from datetime import datetime
from confluent_kafka import Consumer, KafkaException
from sentence_transformers import SentenceTransformer
from shared.db import SessionLocal, Event, IncidentKnowledge, Metric, init_db
from sqlalchemy import text
import ollama
from groq import Groq

import google.generativeai as genai

from services.incident_processor.decision_engine import DecisionEngine
from services.incident_processor.recovery import RecoveryManager

# --- Config ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_LOGS = "container-logs"
KAFKA_TOPIC_METRICS = "container-metrics"
RAG_THRESHOLD = 0.85 # Cosine similarity threshold for RAG hits
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")

# Initialize models
embedder = SentenceTransformer('all-MiniLM-L6-v2')
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-1.5-flash")
decision_engine = DecisionEngine()
recovery_manager = RecoveryManager()

# Load rules
with open("rules/patterns.yaml", "r") as f:
    RULES = yaml.safe_load(f).get("rules", [])

def get_kafka_consumer():
    conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': 'incident_processor_group',
        'auto.offset.reset': 'earliest'
    }
    return Consumer(conf)

def run_rule_engine(log_msg):
    """
    Fast-path for known issues.
    """
    for rule in RULES:
        if rule["pattern"].lower() in log_msg.lower():
            return {
                "root_cause": rule["root_cause"],
                "severity": rule["severity"],
                "suggested_fix": rule["suggested_fix"],
                "auto_restart_safe": rule["auto_restart_safe"],
                "source": "rule_engine"
            }
    return None

def rag_lookup(log_msg, db_session):
    """
    Similarity search for historical incident signatures.
    """
    embedding = embedder.encode(log_msg).tolist()
    
    # PGVector cosine similarity search (1 - distance)
    # RAG using log signatures
    result = db_session.query(IncidentKnowledge).order_by(
        IncidentKnowledge.embedding.cosine_distance(embedding)
    ).limit(1).first()
    
    # We'd ideally compute distance here manually or using a subquery
    # For now, simplistic threshold checking
    if result:
        # Distance calculation
        # Simplified: if it exists, for now we pretend it's a match 
        # (in production, we'd check distance < 0.15)
        return {
            "root_cause": result.root_cause,
            "severity": "high", # Usually RAG is for known high-impact fixes
            "suggested_fix": result.suggested_fix,
            "auto_restart_safe": True,
            "source": "rag_cache"
        }
    return None

def multi_tier_llm(log_msg, container_name):
    """
    Ollama (Tier 1) -> Groq (Tier 2) switch policy.
    """
    prompt = f"Analyze this Docker log from {container_name} and return JSON (root_cause, severity, suggested_fix, confidence_score): {log_msg}"
    
    # TIER 1: OLLAMA
    try:
        response = ollama.generate(model='mistral', prompt=prompt)
        # Parse JSON... (omitted for brevity, assume valid for this mockup)
        diag = json.loads(response['response'])
        if diag.get("confidence_score", 0) > 80:
            diag["source"] = "tier1_ollama"
            return diag
    except:
        pass

    # TIER 2: GEMINI 1.5 FLASH (Primary Reasoning)
    try:
        # Use standard model ID
        model = genai.GenerativeModel("gemini-1.5-flash")
        res = model.generate_content(prompt)
        txt = res.text
        # Extract JSON from potential markdown markers
        diag = json.loads(txt[txt.find("{"):txt.rfind("}")+1])
        diag["source"] = "tier2_gemini_flash"
        return diag
    except Exception as e:
        print(f"Gemini Flash failed (Fallback to local or previous diag): {e}")
            
    return None

def process_log_packet(packet):
    """
    The Decision Engine pipeline.
    """
    log_msg = packet.get("log", "")
    container_name = packet.get("container", "unknown")
    
    with SessionLocal() as db:
        # 1. Rules
        diagnosis = run_rule_engine(log_msg)
        
        # 2. RAG
        if not diagnosis:
            diagnosis = rag_lookup(log_msg, db)
            
        # 3. Multi-tier LLM
        if not diagnosis:
            diagnosis = multi_tier_llm(log_msg, container_name)
            
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
                event_type="diagnosis",
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
                        event_type="remediation_attempt",
                        details={"success": success, "reason": rec_reason}
                    ))
                    db.add(event)
            db.commit()
            print(f"[{container_name}] {diagnosis['source']} -> {diagnosis['severity']} (Validated)")

def process_metric_packet(packet):
    """
    Persist high-frequency telemetry.
    """
    with SessionLocal() as db:
        metric = Metric(
            container=packet.get("container", "unknown"),
            cpu_percent=packet.get("cpu_percent", 0.0),
            mem_usage_mb=packet.get("mem_usage_mb", 0.0),
            timestamp=datetime.fromisoformat(packet.get("timestamp", datetime.utcnow().isoformat()))
        )
        db.add(metric)
        db.commit()

def main():
    print("Incident Processor Service Starting...")
    init_db()
    consumer = get_kafka_consumer()
    consumer.subscribe([KAFKA_TOPIC_LOGS, KAFKA_TOPIC_METRICS])
    
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None: continue
            if msg.error():
                if msg.error().code() == KafkaException._PARTITION_EOF: continue
                else: print(msg.error()); break
            
            topic = msg.topic()
            packet = json.loads(msg.value().decode('utf-8'))
            
            if topic == KAFKA_TOPIC_LOGS:
                process_log_packet(packet)
            elif topic == KAFKA_TOPIC_METRICS:
                process_metric_packet(packet)
            
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        consumer.close()

if __name__ == "__main__":
    main()
