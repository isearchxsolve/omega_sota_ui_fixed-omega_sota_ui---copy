"""
OMEGA Telemetry & Metrics
Monitors persona usage, stealth browser success rates, and obedience corrections.
"""
import logging
import json
import os
from collections import Counter
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TelemetryTracker:
    def __init__(self, log_dir: str = "/tmp/omega_telemetry"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        # In-memory metric stores
        self.persona_usage = Counter()
        self.stealth_operations = {"attempts": 0, "successes": 0, "captchas_detected": 0}
        self.obedience_metrics = {"total_checks": 0, "corrections_made": 0}
        
    def record_persona_switch(self, persona_name: str):
        """Log when a persona is dynamically activated."""
        self.persona_usage[persona_name] += 1
        
    def record_stealth_action(self, success: bool, captcha_detected: bool = False):
        """Log stealth browser navigation outcomes."""
        self.stealth_operations["attempts"] += 1
        if success:
            self.stealth_operations["successes"] += 1
        if captcha_detected:
            self.stealth_operations["captchas_detected"] += 1

    def record_obedience_check(self, was_corrected: bool):
        """Log how often the Obedience Engine has to rewrite LLM outputs."""
        self.obedience_metrics["total_checks"] += 1
        if was_corrected:
            self.obedience_metrics["corrections_made"] += 1

    def flush_to_disk(self):
        """Save current session metrics to a JSON log file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.log_dir, f"telemetry_{timestamp}.json")
        
        payload = {
            "timestamp": timestamp,
            "personas": dict(self.persona_usage),
            "stealth_stats": self.stealth_operations,
            "obedience_stats": self.obedience_metrics
        }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(payload, f, indent=4)
            logger.info(f"Telemetry flushed to {filepath}")
        except Exception as e:
            logger.error(f"Failed to flush telemetry: {e}")