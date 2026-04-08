import docker
import time
from shared.db import SessionLocal, Event

class DecisionEngine:
    def __init__(self):
        # Resilience: Retry connection to the Docker Engine socket
        self.docker_client = None
        for i in range(5):
            try:
                self.docker_client = docker.from_env()
                self.docker_client.version()
                break
            except Exception as e:
                print(f"Waiting for Docker Socket (Attempt {i+1}/5): {e}")
                time.sleep(2)
        
        if not self.docker_client:
            print("CRITICAL: Could not connect to Docker Socket. Diagnostics will be degraded.")

        self.safety_rules = {
            "max_restarts_per_hour": 3,
            "min_confidence": 75,
            "forbidden_fixes": ["rm -rf", "delete database", "drop table"]
        }

    def validate_diagnosis(self, diagnosis, container_name):
        """
        Policy-based validation of AI suggestions.
        """
        confidence = diagnosis.get("confidence_score", 100) # Default to 100 if rules/RAG
        
        # 1. Confidence Check
        if confidence < self.safety_rules["min_confidence"]:
            print(f"Decision Rejected: Confidence {confidence}% below threshold.")
            return False, "Low confidence score."

        # 2. Safety Check (Forbidden String matched)
        suggested_fix = diagnosis.get("suggested_fix", "").lower()
        for forbidden in self.safety_rules["forbidden_fixes"]:
            if forbidden in suggested_fix:
                print(f"Decision Rejected: Safety violation in suggested fix.")
                return False, f"Safety violation: {forbidden} detected."

        # 3. Dependency Check
        is_safe, reason = self.check_dependencies(container_name)
        if not is_safe:
            print(f"Decision Rejected: Dependency failure -> {reason}")
            return False, reason

        return True, "Validated"

    def check_dependencies(self, container_name):
        """
        Check if upstream dependencies are healthy before taking action.
        """
        try:
            container = self.docker_client.containers.get(container_name)
            # Fetch 'depends_on' from labels if injected, or use simple mapping
            # For this MVP, we use common patterns (API depends on DB)
            deps = []
            if "api" in container_name.lower():
                deps.append("db")
            if "web" in container_name.lower():
                deps.append("api")

            for dep_name in deps:
                try:
                    dep_container = self.docker_client.containers.get(dep_name)
                    # Use healthcheck status if available, else running status
                    health = dep_container.attrs.get('State', {}).get('Health', {}).get('Status', 'healthy')
                    status = dep_container.status
                    
                    if health == "unhealthy" or status != "running":
                        return False, f"Dependency '{dep_name}' is unhealthy ({status}/{health})"
                except docker.errors.NotFound:
                    return False, f"Dependency '{dep_name}' not found."

            return True, "Dependencies Healthy"
        except Exception as e:
            return True, f"Error checking dependencies: {e}"

    def record_decision(self, container_name, diagnosis, validated, reason):
        """
        Audit the decision process.
        """
        with SessionLocal() as db:
            event = Event(
                container=container_name,
                event_type="decision_audit",
                details={
                    "validated": validated,
                    "reason": reason,
                    "diagnosis_source": diagnosis.get("source"),
                    "suggested_fix": diagnosis.get("suggested_fix")
                }
            )
            db.add(event)
            db.commit()
