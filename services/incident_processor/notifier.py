import os
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
IST = timezone(timedelta(hours=5, minutes=30))
IST = timezone(timedelta(hours=5, minutes=30))

class NotificationManager:
    """
    Production Alerting Service with Slack/SMTP integration and cooldown logic.
    """
    def __init__(self):
        self.slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("SMTP_PORT", "25"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.alert_email = os.getenv("ALERT_EMAIL", "admin@localhost")
        
        # Alert Memory: [Container_Name] -> {"timestamp": datetime, "cause": str}
        self.alert_memory = {}
        self.COOLDOWN_PERIOD = timedelta(minutes=15)

    def send_alert(self, container, diagnosis):
        severity = diagnosis.get("severity", "low").upper()
        root_cause = diagnosis.get("root_cause", "Anomaly")
        if severity == "LOW": return # Silently log low-sev
        
        # Deduplication & Cooldown check
        last_alert = self.alert_memory.get(container)
        if last_alert:
            time_since = (datetime.now(IST) - last_alert["timestamp"])
            is_same_cause = (last_alert["cause"] == root_cause)
            
            if is_same_cause and time_since < self.COOLDOWN_PERIOD:
                print(f"🔔 [DEDUPE] Alert for {container} with cause '{root_cause}' suppressed (Cooldown active).")
                return

        msg = f"🩺 *Container Doctor Alert*\n*Container*: {container}\n*Severity*: {severity}\n*Cause*: {diagnosis['root_cause']}\n*Action*: {diagnosis['suggested_fix']}\n*Confidence*: {diagnosis.get('llm_confidence', 0)}%"
        
        # 1. Slack
        if self.slack_url:
            try:
                requests.post(self.slack_url, json={"text": msg}, timeout=5)
            except Exception as e:
                print(f"Error sending Slack alert: {e}")

        # 2. SMTP (Email)
        if self.smtp_user and self.smtp_pass:
            try:
                self._send_email(container, severity, msg)
            except Exception as e:
                print(f"Error sending Email alert: {e}")

        self.alert_memory[container] = {"timestamp": datetime.now(IST), "cause": root_cause}

    def send_resolution_alert(self, container):
        """
        Phase 32: Closed-Loop Alerting. Notify when service is restored.
        """
        msg = f"🌲 *Container Doctor Recovery*\n*Container*: {container}\n*Status*: Service Restored & Stable.\n*Timestamp*: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}"
        
        if self.slack_url:
            try:
                requests.post(self.slack_url, json={"text": msg}, timeout=5)
            except Exception as e:
                print(f"Error sending Resolution alert: {e}")
        
        # Clear memory to allow new alerts for this container
        if container in self.alert_memory:
            del self.alert_memory[container]
