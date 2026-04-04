from flask import Flask, jsonify, request
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)

Base.metadata.create_all(bind=engine)

@app.route("/")
def home():
    return {"message": "API is online and functioning efficiently."}

@app.route("/items", methods=["GET"])
def read_items():
    db = SessionLocal()
    items = db.query(Item).all()
    res = [{"id": i.id, "name": i.name} for i in items]
    db.close()
    return jsonify(res)

@app.route("/items", methods=["POST"])
def create_item():
    data = request.json
    if not data or "name" not in data:
        return {"error": "Missing item name field"}, 400
    db = SessionLocal()
    item = Item(name=data["name"])
    db.add(item)
    db.commit()
    db.refresh(item)
    db.close()
    return {"id": item.id, "name": item.name}, 201

# Endpoint used manually to force a memory crash to trigger the doctor dynamically!
@app.route("/force_crash")
def force_crash():
    raise Exception("Manual Memory Limit Exceeded / OOM Killer Exception Triggered")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
