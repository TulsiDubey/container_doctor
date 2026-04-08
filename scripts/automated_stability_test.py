import requests
import json
import time
import sys

BASE_URL = "http://localhost:8080"
TOKEN = None

def bold(text): return f"\033[1m{text}\033[0m"
def green(text): return f"\033[32m{text}\033[0m"
def red(text): return f"\033[31m{text}\033[0m"

def run_test(name, func):
    print(f"Testing {bold(name)}...", end=" ", flush=True)
    try:
        success, msg = func()
        if success:
            print(green("PASSED"))
        else:
            print(red(f"FAILED ({msg})"))
            # sys.exit(1) # Continue for full report
    except Exception as e:
        print(red(f"ERROR ({e})"))

def test_login():
    global TOKEN
    payload = {"username": "admin", "password": "password"}
    res = requests.post(f"{BASE_URL}/api/login", json=payload)
    if res.status_code == 200:
        TOKEN = res.json().get("token")
        return True, "Authenticated"
    return False, f"Status {res.status_code}"

def test_auth_perimeter():
    # Attempt projects without token
    res = requests.get(f"{BASE_URL}/projects")
    if res.status_code == 401:
        return True, "Verified 401 Unauthorized"
    return False, f"Bypassed auth (Status {res.status_code})"

def test_stats_endpoint():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    res = requests.get(f"{BASE_URL}/stats", headers=headers)
    if res.status_code == 200:
        data = res.json()
        keys = ["total_projects", "healthy_containers", "broken_containers"]
        if all(k in data for k in keys):
            return True, "Valid JSON Schema"
    return False, "Malformed response"

def test_projects_structure():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    res = requests.get(f"{BASE_URL}/projects", headers=headers)
    if res.status_code == 200:
        data = res.json()
        if isinstance(data, list) and len(data) > 0:
            # Check for rebranded keys
            group = data[0]
            if "namespace" in group and "projects" in group:
                return True, "Correct Hierarchy"
    return False, "Project list empty or invalid"

def test_history_audit():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    res = requests.get(f"{BASE_URL}/history", headers=headers)
    if res.status_code == 200:
        return True, "History online"
    return False, "Query failed"

def main():
    print(f"\n{bold('--- Container Doctor: Stability & Segregation Audit (FEAT) ---')}\n")
    
    run_test("JWT Identity Gate", test_login)
    run_test("Security Perimeter", test_auth_perimeter)
    run_test("Real-time Telemetry Service", test_stats_endpoint)
    run_test("Hierarchy Explorer (Rebranded)", test_projects_structure)
    run_test("Event Ledger (Audit Trail)", test_history_audit)
    
    print(f"\n{bold('Audit Status')}: {green('COMPLETE')}\n")

if __name__ == "__main__":
    main()
