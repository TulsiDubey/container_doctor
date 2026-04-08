import os
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta

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
        
        # Alert Cooldown: [Container_Name] -> Last_Alert_Time
        self.cooldowns = {}
        self.COOLDOWN_PERIOD = timedelta(minutes=15)

    def send_alert(self, container, diagnosis):
        severity = diagnosis.get("severity", "low").upper()
        if severity == "LOW": return # Silently log low-sev
        
        # Cooldown check
        last_alert = self.cooldowns.get(container)
        if last_alert and (datetime.utcnow() - last_alert) < self.COOLDOWN_PERIOD:
            print(f"🔔 Alert Cooldown Active for {container}. Skipping notification.")
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

        self.cooldowns[container] = datetime.utcnow()

    def _send_email(self, container, severity, msg):
        email_msg = MIMEText(msg)
        email_msg['Subject'] = f"[{severity}] Container Doctor: {container}"
        email_msg['From'] = self.smtp_user
        email_msg['To'] = self.alert_email

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.send_message(email_msg)
