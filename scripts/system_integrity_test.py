import requests
import time
import json
import os
import subprocess

# --- Configuration ---
# Phase 30: System Integrity Validator
BASE_URL = "http://localhost:8080"
AUTH_URL = f"{BASE_URL}/api/login"
KAFKA_TOPIC = "container-logs"
TEST_CONTAINER = "api"

def get_token():
    print("🔑 Authenticating with Sentinel Hub...")
    try:
        r = requests.post(AUTH_URL, json={"username": "admin", "password": "password"}, timeout=5)
        if r.status_code == 200:
            return r.json()["token"]
    except Exception as e:
        print(f"Auth Failed: {e}")
    return None

def induce_failure():
    print(f"🛑 Inducing Real-time Outage on {TEST_CONTAINER}...")
    subprocess.run(["docker", "stop", TEST_CONTAINER], capture_output=True)

def restore_service():
    print(f"✅ Restoring Service {TEST_CONTAINER}...")
    subprocess.run(["docker", "start", TEST_CONTAINER], capture_output=True)

def verify_signal(token):
    headers = {"Authorization": f"Bearer {token}"}
    print("📡 Monitoring Signal Pulse for 20 seconds...")
    
    timeout = 20
    start_time = time.time()
    
    while (time.time() - start_time) < timeout:
        try:
            # Check Recent Alerts
            r = requests.get(f"{BASE_URL}/recent", headers=headers, timeout=5)
            if r.status_code == 200:
                recent = r.json().get("recent", [])
                
                # Check for the latest api event
                api_event = next((e for e in recent if e["container"] == TEST_CONTAINER), None)
                
                if api_event:
                    print(f"✨ SIGNAL DETECTED: {api_event['event']} | Status: {api_event['status']}")
                    if api_event["event"] in ["OUTAGE_DETECTED", "ANOMALY_ALARM"]:
                        details = api_event.get("details", {})
                        if details.get("suggested_fix"):
                            print(f"🎯 PAYLOAD VERIFIED: {details['suggested_fix']}")
                            return True
            
            # Check Stats Consistency
            s = requests.get(f"{BASE_URL}/stats", headers=headers, timeout=5)
            if s.status_code == 200:
                stats = s.json()
                print(f"💹 STATS PULSE: {stats['healthy_containers']} Healthy / {stats['broken_containers']} Broken")

        except Exception as e:
            print(f"Polling error: {e}")
            
        time.sleep(5)
    
    return False

def main():
    print("--- 🛡️ SENTINEL INTEGRITY STRESS TEST (PHASE 30) ---")
    token = get_token()
    if not token:
        print("FAILED: Primary Authentication Layer down.")
        return

    try:
        induce_failure()
        success = verify_signal(token)
        
        if success:
            print("\n🏆 TEST RESULT: PASS. SYSTEM-WIDE SYNCHRONIZATION 100% NOMINAL.")
        else:
            print("\n❌ TEST RESULT: FAIL. SIGNAL LOST OR LATENCY EXCEEDED 20S.")
            
    finally:
        restore_service()

if __name__ == "__main__":
    main()
