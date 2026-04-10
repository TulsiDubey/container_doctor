import os
import time
import json
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, session
from pgvector.sqlalchemy import Vector
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://tulsi1:Tulsi%402211@db:5432/mydb")

# Configure# Connection pooling for high-frequency metrics
try:
    engine = create_engine(
        DATABASE_URL, 
        pool_size=20, 
        max_overflow=30,
        pool_pre_ping=True, # Critical: Checks connection health before use
        pool_recycle=3600    # Prevent stale connections
    )
except Exception as e:
    print(f"CRITICAL: Database engine initialization failed: {e}")
    # In production, we'd log this to an external monitor
    raise

# Hardened Session factory with auto-retry
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Models ---

class Event(Base):
    """
    Core event ledger for UI dashboard and audit trail.
    """
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    container = Column(String(255), index=True)
    project = Column(String(255), index=True)
    event_type = Column(String(50), index=True)  # e.g., restart, error, diagnosis
    details = Column(JSON)
    status = Column(String(50), index=True, default="open") # open, resolved, archived
    timestamp = Column(DateTime, default=datetime.utcnow)

class Metric(Base):
    """
    High-frequency resource telemetry (CPU/RAM/DISK).
    """
    __tablename__ = "metrics"
    id = Column(Integer, primary_key=True, index=True)
    container = Column(String(255), index=True)
    cpu_percent = Column(Float) # Precision percentage
    mem_usage_mb = Column(Float)
    disk_read_mb = Column(Float, default=0.0)
    disk_write_mb = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)

class IncidentKnowledge(Base):
    """
    RAG Store for historical incident signatures and their verified fixes.
    """
    __tablename__ = "incident_knowledge"
    id = Column(Integer, primary_key=True, index=True)
    log_signature = Column(Text) # Representative log pattern
    embedding = Column(Vector(384)) # Dimension for all-MiniLM-L6-v2
    root_cause = Column(Text)
    suggested_fix = Column(Text)
    confidence = Column(Integer) # How often this fix worked
    last_seen = Column(DateTime, default=datetime.utcnow)

def init_db():
    print("Connecting to database and initializing extensions...")
    retries = 30
    while retries > 0:
        try:
            # Activate pgvector
            with engine.connect() as conn:
                from sqlalchemy import text
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            
            Base.metadata.create_all(bind=engine)
            print("Database initialized successfully.")
            return True
        except Exception as e:
            print(f"Database initialization failed: {e}. Retrying in 2s...")
            time.sleep(2)
            retries -= 1
    return False

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
