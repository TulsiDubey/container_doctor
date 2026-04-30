import docker
import time
from datetime import datetime, timedelta, timezone
IST = timezone(timedelta(hours=5, minutes=30))
IST = timezone(timedelta(hours=5, minutes=30))
from shared.db import SessionLocal, Event

class CircuitBreaker:
    def __init__(self, threshold=3, window_minutes=60):
        self.threshold = threshold
        self.window = window_minutes
        self.history = {} # {container_name: [timestamps]}

    def is_open(self, container_name):
        """
        Check if the circuit is 'Open' (Actions Blocked).
        """
        now = datetime.now(IST)
        if container_name not in self.history:
            return False
            
        # Clean old timestamps
        cutoff = now - timedelta(minutes=self.window)
        self.history[container_name] = [t for t in self.history[container_name] if t > cutoff]
        
        return len(self.history[container_name]) >= self.threshold

    def record_attempt(self, container_name):
        self.history.setdefault(container_name, []).append(datetime.now(IST))

class RecoveryManager:
    def __init__(self):
        self.docker_client = docker.from_env()
        self.circuit_breaker = CircuitBreaker()

    def execute_remediation(self, container_name, diagnosis):
        """
        Execute safe remediation with Canary and Circuit Breaker logic.
        """
        # Phase 46: Controlled Self-Healing (Safety First)
        suggested_fix = diagnosis.get("suggested_fix", "").lower()
        safe_actions = ["restart", "docker restart", "docker-compose restart", "docker start"]
        is_safe = any(action in suggested_fix for action in safe_actions)
        
        if not is_safe:
            print(f"⚠️ [SAFETY] Remediation blocked for {container_name}: Action '{suggested_fix}' is not in the safe whitelist.")
            return False, "Remediation blocked: Action not in safe whitelist (Manual SRE intervention required)."

        if self.circuit_breaker.is_open(container_name):
            print(f"Recovery Halted: Circuit Breaker OPEN for {container_name}")
            return False, "Circuit breaker triggered due to flapping."

        self.circuit_breaker.record_attempt(container_name)

        # 1. Configuration Fix (if suggested)
        if diagnosis.get("config_suggestions"):
             # In a real system, we'd apply env vars or volume mounts
             pass

        # 2. Canary Restart (Simulated orchestration)
        try:
            container = self.docker_client.containers.get(container_name)
            print(f"Executing Canary Restart for {container_name}...")
            
            container.restart()
            
            # 3. Validation Phase (Wait for health)
            success = self.verify_health(container_name)
            if success:
                return True, "Remediation Successful"
            else:
                return False, "Canary health check failed."
                
        except Exception as e:
            return False, f"Recovery Error: {e}"

    def verify_health(self, container_name, timeout=30):
        """
        Wait for container to reach healthy status.
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                container = self.docker_client.containers.get(container_name)
                health = container.attrs.get('State', {}).get('Health', {}).get('Status', 'running')
                if container.status == "running" and health != "unhealthy":
                    return True
            except:
                pass
            time.sleep(2)
        return False
