"""
Time-series pattern engine for generating realistic temporal data.

Supports: sine waves, random walks, step functions, sawtooth,
seasonal patterns, trend lines, and anomaly injection.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any


class TimeSeriesGenerator:
    """Generates time-series data points with configurable patterns."""

    def __init__(self, config: dict):
        self.pattern = config.get("pattern", "random_walk")
        self.start = self._parse_time(config.get("start", "now-24h"))
        self.end = self._parse_time(config.get("end", "now"))
        self.interval_seconds = config.get("interval_seconds", 60)
        self.base_value = config.get("base_value", 50.0)
        self.amplitude = config.get("amplitude", 25.0)
        self.noise = config.get("noise", 0.1)
        self.trend = config.get("trend", 0.0)  # Per-step trend
        self.anomaly_rate = config.get("anomaly_rate", 0.02)
        self.anomaly_magnitude = config.get("anomaly_magnitude", 3.0)
        self.labels = config.get("labels", {})
        self.metric_name = config.get("metric_name", "test_metric")
        self.period_seconds = config.get("period_seconds", 3600)  # For sine/seasonal
        self.steps = config.get("step_values", [20, 50, 80])  # For step function

    def generate(self) -> list[dict]:
        """Generate the full time-series as a list of {timestamp, value, labels} dicts."""
        points = []
        current = self.start
        step = 0
        total_steps = max(1, int((self.end - self.start).total_seconds() / self.interval_seconds))

        prev_value = self.base_value

        while current <= self.end:
            t = step / max(total_steps, 1)  # Normalized 0..1
            raw = self._pattern_value(step, t, prev_value)

            # Add noise
            noise_val = random.gauss(0, self.amplitude * self.noise)
            value = raw + noise_val

            # Add trend
            value += self.trend * step

            # Inject anomaly
            if random.random() < self.anomaly_rate:
                direction = random.choice([-1, 1])
                value += direction * self.amplitude * self.anomaly_magnitude

            value = round(value, 4)
            prev_value = value

            points.append({
                "timestamp": current.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "timestamp_epoch_ms": int(current.timestamp() * 1000),
                "value": value,
                "metric": self.metric_name,
                "labels": {**self.labels},
            })

            current += timedelta(seconds=self.interval_seconds)
            step += 1

        return points

    def _pattern_value(self, step: int, t: float, prev: float) -> float:
        """Compute the base pattern value at a given step."""
        if self.pattern == "sine":
            phase = (step * self.interval_seconds) / self.period_seconds * 2 * math.pi
            return self.base_value + self.amplitude * math.sin(phase)

        elif self.pattern == "random_walk":
            delta = random.gauss(0, self.amplitude * 0.05)
            value = prev + delta
            # Mean reversion
            value += (self.base_value - value) * 0.01
            return value

        elif self.pattern == "step":
            steps = self.steps
            idx = int(t * len(steps)) % len(steps)
            return steps[idx]

        elif self.pattern == "sawtooth":
            phase = (step * self.interval_seconds) % self.period_seconds
            return self.base_value + self.amplitude * (phase / self.period_seconds)

        elif self.pattern == "seasonal":
            # Daily pattern: low at night, peak during business hours
            hour = (self.start + timedelta(seconds=step * self.interval_seconds)).hour
            daily_factor = math.sin((hour - 6) / 24 * 2 * math.pi) * 0.5 + 0.5
            # Weekly pattern: lower on weekends
            weekday = (self.start + timedelta(seconds=step * self.interval_seconds)).weekday()
            weekly_factor = 0.6 if weekday >= 5 else 1.0
            return self.base_value + self.amplitude * daily_factor * weekly_factor

        elif self.pattern == "spike":
            # Mostly flat with periodic spikes
            if random.random() < 0.05:
                return self.base_value + self.amplitude * random.uniform(1.5, 3.0)
            return self.base_value + random.gauss(0, self.amplitude * 0.1)

        elif self.pattern == "decay":
            # Exponential decay from amplitude to base
            return self.base_value + self.amplitude * math.exp(-3 * t)

        else:  # constant
            return self.base_value

    @staticmethod
    def _parse_time(expr: str) -> datetime:
        """Parse time expression."""
        import re
        now = datetime.now(timezone.utc)
        if expr == "now":
            return now
        match = re.match(r"now([+-])(\d+)([smhdw])", expr)
        if match:
            sign = 1 if match.group(1) == '+' else -1
            amount = int(match.group(2))
            unit = match.group(3)
            mult = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
            return now + timedelta(seconds=sign * amount * mult.get(unit, 3600))
        try:
            return datetime.fromisoformat(expr.replace('Z', '+00:00'))
        except ValueError:
            return now - timedelta(hours=24)


def generate_metrics(config: dict) -> list[dict]:
    """Convenience function to generate time-series metrics."""
    gen = TimeSeriesGenerator(config)
    return gen.generate()


def generate_prometheus_metrics(config: dict) -> list[str]:
    """Generate metrics in Prometheus exposition format."""
    points = generate_metrics(config)
    lines = []
    metric = config.get("metric_name", "test_metric")
    help_text = config.get("help", f"Generated test metric {metric}")
    metric_type = config.get("type", "gauge")

    lines.append(f"# HELP {metric} {help_text}")
    lines.append(f"# TYPE {metric} {metric_type}")

    for point in points:
        labels = point.get("labels", {})
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        label_part = f"{{{label_str}}}" if label_str else ""
        lines.append(f"{metric}{label_part} {point['value']} {point['timestamp_epoch_ms']}")

    return lines


def generate_log_entries(config: dict) -> list[dict]:
    """Generate structured log entries with realistic patterns."""
    from faker import Faker
    fake = Faker()

    count = config.get("count", 100)
    start = TimeSeriesGenerator._parse_time(config.get("start", "now-1h"))
    end = TimeSeriesGenerator._parse_time(config.get("end", "now"))
    levels = config.get("levels", {"INFO": 60, "WARN": 20, "ERROR": 15, "DEBUG": 5})
    services = config.get("services", ["api-gateway", "auth-service", "db-proxy", "worker"])

    level_list = list(levels.keys())
    level_weights = list(levels.values())

    entries = []
    for i in range(count):
        t = i / max(count - 1, 1)
        ts = start + timedelta(seconds=t * (end - start).total_seconds())
        level = random.choices(level_list, weights=level_weights, k=1)[0]
        service = random.choice(services)

        msg_templates = {
            "INFO": [
                f"Request processed successfully in {random.randint(10, 500)}ms",
                f"User {fake.user_name()} authenticated from {fake.ipv4()}",
                f"Cache hit for key {fake.md5()[:12]}",
                f"Health check passed for {service}",
            ],
            "WARN": [
                f"Slow query detected: {random.randint(1000, 5000)}ms",
                f"Connection pool at {random.randint(80, 95)}% capacity",
                f"Rate limit approaching for client {fake.ipv4()}",
                f"Retry attempt {random.randint(2, 5)} for downstream call",
            ],
            "ERROR": [
                f"Failed to connect to database: timeout after {random.randint(5, 30)}s",
                f"HTTP 500 returned from {service}: internal server error",
                f"Authentication failed for user {fake.user_name()}: invalid token",
                f"Out of memory: allocated {random.randint(2, 16)}GB / {random.randint(8, 32)}GB",
            ],
            "DEBUG": [
                f"Entering function process_request with args: id={fake.md5()[:8]}",
                f"SQL: SELECT * FROM users WHERE id = '{fake.md5()[:8]}'",
                f"Response payload size: {random.randint(100, 50000)} bytes",
            ],
        }

        entries.append({
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": level,
            "service": service,
            "message": random.choice(msg_templates.get(level, msg_templates["INFO"])),
            "trace_id": fake.md5()[:16],
            "span_id": fake.md5()[:8],
            "host": f"{service}-{random.randint(1, 5)}.internal",
        })

    return entries
