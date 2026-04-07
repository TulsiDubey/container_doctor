import os
import time
import json
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, session
from pgvector.sqlalchemy import Vector
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://tulsi1:Tulsi%402211@db:5432/mydb")

# Use a connection pool for high-performance
engine = create_engine(
    DATABASE_URL, 
    pool_size=20, 
    max_overflow=0,
    pool_pre_ping=True
)
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
    timestamp = Column(DateTime, default=datetime.utcnow)

class Metric(Base):
    """
    High-frequency resource telemetry (CPU/RAM).
    """
    __tablename__ = "metrics"
    id = Column(Integer, primary_key=True, index=True)
    container = Column(String(255), index=True)
    cpu_percent = Column(JSON) # Storing as JSON for flexibility or float
    mem_usage_mb = Column(JSON)
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
